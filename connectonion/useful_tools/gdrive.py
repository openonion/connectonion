"""
Purpose: Google Drive integration tool for listing, searching, downloading, and uploading files via the Drive API
LLM-Note:
  Dependencies: imports from [io, mimetypes, os, pathlib, googleapiclient.discovery, googleapiclient.http, google.oauth2.credentials] | imported by [useful_tools/__init__.py] | requires OAuth tokens from 'co auth google' | tested by [tests/unit/test_gdrive.py]
  Data flow: Agent calls GDrive methods → _get_service() validates the ambient OpenOnion account and refreshes the access token via oo-api once per instance → Drive v3 API → returns file dicts or confirmations | list_files()/search_files() page through files().list() with 'trashed = false' | download() picks get_media() for binary files and export_media() for Google-native docs | upload() sends a MediaFileUpload
  State/Effects: reads GOOGLE_* env vars for OAuth tokens | makes HTTP calls to the Drive API | creates/overwrites local files on download and remote files on upload | token refresh rewrites ~/.co/keys.env
  Integration: exposes GDrive class with list_files(), search_files(), download(), upload(), delete() | private metadata/byte helpers let the Gmail CLI stage a Drive file without writing it locally | used as agent tool via Agent(tools=[GDrive()])
  Performance: network I/O per API call | listings page at 100/request | downloads stream in chunks
  Errors: raises ValueError if OAuth not configured, if the Drive scope is missing, on unknown file ids, and on Google-native types with no export format | HttpError from the Drive API propagates

Google Drive tool for managing files.

Usage:
    from connectonion import Agent, GDrive

    drive = GDrive()
    agent = Agent("assistant", tools=[drive])

    # Agent can now use:
    # - list_files(last)
    # - search_files(query, last)
    # - download(file_id, dest)
    # - upload(path, name)
    # - delete(file_id)

Example:
    from connectonion import Agent, GDrive

    agent = Agent(
        name="drive-assistant",
        system_prompt="You are a Google Drive assistant.",
        tools=[GDrive()]
    )

    agent.input("What did I change in Drive this week?")
"""

import io
import mimetypes
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from ..backend import backend_url
from ..credentials import require_ambient_api_key

# Everything under this prefix is a Google-native doc: it has no bytes of its
# own, so it must be exported to a real format rather than downloaded.
NATIVE_PREFIX = "application/vnd.google-apps."

# What each native type becomes on download, and the extension to give it.
EXPORT_FORMATS = {
    "application/vnd.google-apps.document": ("text/markdown", ".md"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.drawing": ("application/pdf", ".pdf"),
}

# Drive returns only id/name/mimeType/kind unless asked; and in a list request
# the file fields have to be nested under files(...).
FILE_FIELDS = "id, name, mimeType, modifiedTime, size, webViewLink"
LIST_FIELDS = f"nextPageToken, files({FILE_FIELDS})"


class GDrive:
    """Google Drive tool for listing, searching, downloading, and uploading files."""

    def __init__(self):
        """Initialize the Drive tool.

        Validates that Google OAuth is configured with the Drive scope.
        Raises ValueError if it is missing.
        """
        scopes = os.getenv("GOOGLE_SCOPES", "")
        if "drive" not in scopes:
            raise ValueError(
                "Missing 'drive' scope.\n"
                f"Current scopes: {scopes}\n"
                "Please authorize Google Drive access:\n"
                "  co auth google"
            )

        self._service = None

    def _get_service(self):
        """Get the Drive API service, refreshing the access token once per instance.

        Same contract as the Gmail tool: an access token lives an hour, so a
        cached one is almost always stale by the next run — refresh up front
        rather than doing expiry arithmetic that can silently skip.
        """
        if self._service:
            return self._service

        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

        if not os.getenv("GOOGLE_ACCESS_TOKEN") or not refresh_token:
            raise ValueError(
                "Google OAuth credentials not found.\n"
                "Run: co auth google"
            )

        access_token = self._refresh_via_backend(refresh_token)

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=None,
            client_secret=None,
            scopes=["https://www.googleapis.com/auth/drive"]
        )

        self._service = build('drive', 'v3', credentials=creds)
        return self._service

    def _refresh_via_backend(self, refresh_token: str) -> str:
        """Refresh the access token via the backend and persist it.

        Args:
            refresh_token: The refresh token

        Returns:
            New access token
        """
        import httpx

        selected_backend = backend_url()
        api_key = require_ambient_api_key()

        response = httpx.post(
            f"{selected_backend}/api/v1/oauth/google/refresh",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"refresh_token": refresh_token}
        )

        if response.status_code != 200:
            raise ValueError("Failed to refresh Google authorization via backend")

        data = response.json()
        new_access_token = data["access_token"]
        expires_at = data["expires_at"]

        os.environ["GOOGLE_ACCESS_TOKEN"] = new_access_token
        os.environ["GOOGLE_TOKEN_EXPIRES_AT"] = expires_at

        from ..cli.commands.project_cmd_lib import upsert_env
        env_file = Path(os.getenv("AGENT_CONFIG_PATH", os.path.expanduser("~/.co"))) / "keys.env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        values = {
            "GOOGLE_ACCESS_TOKEN": new_access_token,
            "GOOGLE_TOKEN_EXPIRES_AT": expires_at,
        }
        if data.get("refresh_token"):
            values["GOOGLE_REFRESH_TOKEN"] = data["refresh_token"]
        if "scopes" in data:
            values["GOOGLE_SCOPES"] = data["scopes"]
        os.environ.update(values)
        upsert_env(env_file, values)
        env_file.chmod(0o600)

        return new_access_token

    @staticmethod
    def _file_dict(item: dict) -> dict:
        """Normalize a Drive file resource to the CLI/agent file shape."""
        return {
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "type": item.get("mimeType", ""),
            "modified": item.get("modifiedTime", ""),
            # Folders, shortcuts and native docs report no size.
            "size": int(item["size"]) if item.get("size") else 0,
            "link": item.get("webViewLink", ""),
        }

    def _list(self, query: str, last: int) -> list:
        """Page through files().list() until `last` files are collected."""
        service = self._get_service()
        files = []
        page_token = None

        while len(files) < last:
            result = service.files().list(
                q=query,
                orderBy="modifiedTime desc",
                pageSize=min(last - len(files), 100),
                fields=LIST_FIELDS,
                pageToken=page_token,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            ).execute()

            files.extend(self._file_dict(item) for item in result.get("files", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return files[:last]

    # === Listing ===

    def list_files(self, last: int = 20) -> list:
        """List recently modified Drive files as dicts (id, name, type, modified, size, link).

        Args:
            last: Number of files to retrieve (default: 20)

        Returns:
            List of file dicts, most recently modified first
        """
        if last < 1:
            return []
        return self._list("trashed = false", last)

    def search_files(self, query: str, last: int = 20) -> list:
        """Find Drive files by name.

        Drive matches `name contains` on token prefixes, not arbitrary
        substrings: on "HelloWorld", 'Hello' matches and 'World' does not.

        Args:
            query: Text to look for in file names
            last: Number of matches to return (default: 20)

        Returns:
            List of file dicts, most recently modified first
        """
        needle = query.strip()
        if not needle or last < 1:
            return []

        # A quote or backslash in the name would otherwise break out of the
        # query literal and make Drive reject the whole request.
        escaped = needle.replace("\\", "\\\\").replace("'", "\\'")
        return self._list(f"name contains '{escaped}' and trashed = false", last)

    def format_files(self, files: list) -> str:
        """Format file dicts into a readable list."""
        if not files:
            return "No files found."

        output = [f"Found {len(files)} file(s):\n"]
        for i, item in enumerate(files, 1):
            output.append(f"{i}. {item['name']}")
            output.append(f"   Type: {item['type']}")
            output.append(f"   Modified: {item['modified']}")
            output.append(f"   ID: {item['id']}\n")

        return "\n".join(output)

    def list_recent(self, last: int = 20) -> str:
        """List recent Drive files as readable text (agent-facing counterpart of list_files)."""
        return self.format_files(self.list_files(last=last))

    def search(self, query: str, last: int = 20) -> str:
        """Search Drive by file name and return readable text."""
        files = self.search_files(query, last=last)
        if not files:
            return f"No files found matching: {query}"
        return self.format_files(files)

    # === Transfer ===

    def _get_meta(self, file_id: str) -> dict:
        """Fetch one file's metadata, resolving shortcuts to their target."""
        service = self._get_service()
        item = service.files().get(
            fileId=file_id,
            fields=f"{FILE_FIELDS}, shortcutDetails",
            supportsAllDrives=True,
        ).execute()

        shortcut = item.get("shortcutDetails")
        if shortcut:
            return self._get_meta(shortcut["targetId"])
        return item

    def _get_file(self, file_id: str) -> dict:
        """Get one Drive file's normalized metadata without downloading it."""
        return self._file_dict(self._get_meta(file_id))

    def _read_file(self, file_id: str, max_bytes: int | None = None) -> dict:
        """Read a Drive file for another provider, exporting native docs.

        This is the in-memory counterpart of download(). It never writes a
        local file and can fail before or during download when `max_bytes` is
        exceeded.
        """
        item = self._get_meta(file_id)
        name, mime = item["name"], item["mimeType"]
        if max_bytes is not None and item.get("size") and int(item["size"]) > max_bytes:
            raise ValueError(f"Drive file exceeds the {max_bytes}-byte attachment limit.")

        service = self._get_service()
        if mime.startswith(NATIVE_PREFIX):
            if mime not in EXPORT_FORMATS:
                raise ValueError(
                    f"'{name}' is a {mime.replace(NATIVE_PREFIX, '')} — Drive has "
                    "no export format for it, so it cannot be downloaded or attached."
                )
            mime, suffix = EXPORT_FORMATS[mime]
            request = service.files().export_media(fileId=item["id"], mimeType=mime)
            name = f"{name}{suffix}"
        else:
            request = service.files().get_media(fileId=item["id"], supportsAllDrives=True)

        buffer = io.BytesIO()
        # The library default is a 100 MB chunk, which would defeat the
        # attachment limit for sizeless Google-native exports. Keep memory
        # bounded to at most roughly one small chunk beyond max_bytes.
        chunk_size = min(1024 * 1024, max_bytes + 1) if max_bytes is not None else 1024 * 1024
        downloader = MediaIoBaseDownload(buffer, request, chunksize=chunk_size)
        done = False
        while not done:
            _, done = downloader.next_chunk()
            if max_bytes is not None and buffer.tell() > max_bytes:
                raise ValueError(f"Drive file exceeds the {max_bytes}-byte attachment limit.")

        return {
            "id": item["id"],
            "name": name,
            "type": mime,
            "size": len(buffer.getvalue()),
            "link": item.get("webViewLink", ""),
            "data": buffer.getvalue(),
        }

    def download(self, file_id: str, dest: str = ".") -> str:
        """Download a Drive file, exporting Google-native docs to a real format.

        Args:
            file_id: Drive file id
            dest: Destination directory, or a full file path (default: cwd)

        Returns:
            Confirmation with the path written
        """
        item = self._read_file(file_id)
        name = item["name"]

        path = Path(dest).expanduser()
        if path.is_dir():
            path = path / name

        path.write_bytes(item["data"])
        return f"Downloaded to {path}"

    def upload(self, path: str, name: str = None) -> dict:
        """Upload a local file to Drive.

        Args:
            path: Local file path
            name: Name to give it in Drive (default: the file's own name)

        Returns:
            File dict for the created file
        """
        local = Path(path).expanduser()
        if not local.is_file():
            raise ValueError(f"File not found: {path}")

        service = self._get_service()
        media = MediaFileUpload(
            str(local),
            mimetype=mimetypes.guess_type(local.name)[0] or "application/octet-stream",
            resumable=True,
        )
        created = service.files().create(
            body={"name": name or local.name},
            media_body=media,
            fields=FILE_FIELDS,
            supportsAllDrives=True,
        ).execute()

        return self._file_dict(created)

    def delete(self, file_id: str) -> str:
        """Move a Drive file to the trash.

        Trashing rather than deleting outright — an agent calling this by
        mistake should be recoverable from the Drive UI.

        Args:
            file_id: Drive file id

        Returns:
            Confirmation message
        """
        service = self._get_service()
        service.files().update(
            fileId=file_id,
            body={"trashed": True},
            supportsAllDrives=True,
        ).execute()
        return f"Moved to trash: {file_id}"
