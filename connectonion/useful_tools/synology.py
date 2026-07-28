"""
Purpose: Synology NAS integration tool for listing, searching, downloading, uploading, and sharing File Station files
LLM-Note:
  Dependencies: imports from [json, os, pathlib, httpx] | imported by [useful_tools/__init__.py] | requires SYNOLOGY_* env vars from 'co syno login' | tested by [tests/unit/test_synology.py]
  Data flow: Agent calls Synology methods → _request() attaches the cached sid and hits /webapi/<path> → DSM returns {"success":bool,"data":...} → returns file dicts or confirmations | list_files() uses SYNO.FileStation.List (list_share at the root, list inside a share) | search_files() runs the Search start→poll→clean dance | download() streams bytes | upload() posts multipart with the file part last
  State/Effects: reads SYNOLOGY_URL/ACCOUNT/PASSWORD/SID env vars | makes HTTP calls to the NAS | re-login on an expired session rewrites SYNOLOGY_SID in ~/.co/keys.env | download() writes local files, upload() writes remote ones
  Integration: exposes Synology class with list_files(), search_files(), download(), upload(), share() | resolve_quickconnect() turns a QuickConnect ID into ordered base-URL candidates | used as agent tool via Agent(tools=[Synology()])
  Performance: network I/O per call | QuickConnect relay is throttled, so the LAN candidate is probed first | search polls at 0.3s intervals
  Errors: raises ValueError when not configured, on failed login, and on any DSM error code (decoded via ERRORS) | httpx errors propagate except while probing connection candidates, where an unreachable candidate falls through to the next

Synology File Station tool for managing NAS files.

Usage:
    from connectonion import Agent, Synology

    nas = Synology()
    agent = Agent("assistant", tools=[nas])

    # Agent can now use:
    # - list_files(path, last)
    # - search_files(query, path, last)
    # - download(path, dest)
    # - upload(local_path, path)
    # - share(path)
"""

import os
import time
from pathlib import Path

import httpx

# DSM answers every call with {"success": bool, "error": {"code": N}}. These are
# the codes worth naming — the rest surface as a bare number.
ERRORS = {
    100: "Unknown error",
    101: "No parameter of API, method or version",
    102: "The requested API does not exist",
    103: "The requested method does not exist",
    104: "The requested version does not support the functionality",
    105: "The logged in session does not have permission",
    106: "Session timeout",
    107: "Session interrupted by duplicate login",
    119: "SID not found",
    400: "No such account or incorrect password",
    401: "Account disabled",
    402: "Permission denied",
    403: "2-step verification code required",
    404: "Failed to authenticate 2-step verification code",
    407: "Operation not permitted",
    408: "No such file or directory",
    1805: "Destination file exists and no overwrite was given",
}

# A dead session, not a real failure — the fix is to log in again and retry once.
STALE_SESSION = {106, 107, 119}

QUICKCONNECT_GLOBAL = "https://global.quickconnect.to/Serv.php"


def _payload(command: str, server_id: str) -> dict:
    """Build a QuickConnect Serv.php request body."""
    return {
        "version": 1,
        "command": command,
        "stop_when_error": False,
        "stop_when_success": False,
        "id": "dsm_portal_https",
        "serverID": server_id,
    }


def resolve_quickconnect(server_id: str) -> list:
    """Turn a QuickConnect ID into base URLs to try, fastest route first.

    QuickConnect is not one address but several: the NAS may be on this LAN, may
    be reachable at a DDNS name or forwarded port, and can always be reached
    through a Synology-hosted relay. The relay is heavily throttled, so it is
    the last resort rather than the default — which is where the common Python
    clients stop.

    Args:
        server_id: The QuickConnect ID (the name in quickconnect.to/<ID>)

    Returns:
        Ordered list of base URLs — LAN, then DDNS/external, then relay
    """
    reply = httpx.post(QUICKCONNECT_GLOBAL, json=_payload("get_server_info", server_id), timeout=15)
    info = reply.json()

    if info.get("errno"):
        raise ValueError(
            f"QuickConnect ID '{server_id}' not found (errno {info['errno']}).\n"
            "Check Control Panel → External Access → QuickConnect on your NAS."
        )

    server = info.get("server", {})
    port = server.get("port") or 5001
    candidates = []

    # Same-network addresses: full speed, and the reason to probe at all.
    for interface in server.get("interface", []):
        if interface.get("ip"):
            candidates.append(f"https://{interface['ip']}:{port}")

    ddns = server.get("ddns")
    if ddns and ddns != "NULL":
        candidates.append(f"https://{ddns}:{port}")

    external = server.get("external", {}).get("ip")
    if external:
        candidates.append(f"https://{external}:{port}")

    relay = info.get("service", {}).get("relay_ip") or info.get("relay_ip")
    if relay:
        candidates.append(f"https://{relay}")
    # The relay hostname form always exists even when the tunnel fields don't.
    candidates.append(f"https://{server_id}.quickconnect.to")

    return candidates


def pick_reachable(candidates: list, timeout: float = 3.0) -> str:
    """Return the first candidate whose DSM answers, or raise if none do.

    Args:
        candidates: Base URLs from resolve_quickconnect()
        timeout: Seconds to wait per candidate before moving on

    Returns:
        The winning base URL
    """
    for base in candidates:
        # A candidate that is simply not on this network is expected, not
        # exceptional — fall through to the next rather than failing the run.
        try:
            reply = httpx.get(
                f"{base}/webapi/query.cgi",
                params={"api": "SYNO.API.Info", "version": 1, "method": "query", "query": "SYNO.API.Auth"},
                timeout=timeout,
                verify=False,
            )
        except httpx.RequestError:
            continue
        if reply.status_code == 200 and reply.json().get("success"):
            return base

    raise ValueError(
        "Could not reach your NAS on any known address.\n"
        "If you are off your home network, try: co syno login --url https://<host>:5001"
    )


class Synology:
    """Synology File Station tool for listing, searching, downloading, uploading, and sharing files."""

    def __init__(self, url: str = None, account: str = None, password: str = None):
        """Initialize the Synology tool from arguments or SYNOLOGY_* env vars."""
        self.url = (url or os.getenv("SYNOLOGY_URL", "")).rstrip("/")
        self.account = account or os.getenv("SYNOLOGY_ACCOUNT", "")
        self.password = password or os.getenv("SYNOLOGY_PASSWORD", "")
        self.sid = os.getenv("SYNOLOGY_SID", "")

        if not self.url:
            raise ValueError("Synology NAS not configured.\nRun: co syno login")

        self._paths = {}

    # === Plumbing ===

    def _client(self) -> httpx.Client:
        """An HTTP client for this NAS. Certificate checks are off because DSM ships a self-signed cert by default."""
        return httpx.Client(base_url=self.url, timeout=60, verify=False, follow_redirects=True)

    def _path_for(self, api: str) -> str:
        """Look up an API's CGI path, querying SYNO.API.Info once per instance.

        DSM moves these paths and bumps max versions between releases, so asking
        the NAS beats hardcoding 'entry.cgi' and hoping.
        """
        if not self._paths:
            with self._client() as client:
                reply = client.get(
                    "/webapi/query.cgi",
                    params={"api": "SYNO.API.Info", "version": 1, "method": "query", "query": "all"},
                )
            self._paths = reply.json()["data"]

        return self._paths.get(api, {}).get("path", "entry.cgi")

    def _login(self):
        """Log in and cache the session id, persisting it for the next command."""
        if not self.account or not self.password:
            raise ValueError("Synology credentials missing.\nRun: co syno login")

        with self._client() as client:
            # POST, not the GET the official examples show: a password in a query
            # string ends up in proxy and server logs.
            reply = client.post(
                f"/webapi/{self._path_for('SYNO.API.Auth')}",
                data={
                    "api": "SYNO.API.Auth",
                    "version": 3,
                    "method": "login",
                    "account": self.account,
                    "passwd": self.password,
                    "session": "FileStation",
                    "format": "sid",
                },
            )

        body = reply.json()
        if not body.get("success"):
            code = body.get("error", {}).get("code", 0)
            raise ValueError(f"Synology login failed: {ERRORS.get(code, f'error {code}')}")

        self.sid = body["data"]["sid"]
        save_credentials(sid=self.sid)

    def _request(self, api: str, method: str, version: int = 2, **params) -> dict:
        """Call a File Station API, logging in first and retrying once if the session died."""
        if not self.sid:
            self._login()

        body = self._call(api, method, version, params)

        if not body.get("success") and body.get("error", {}).get("code") in STALE_SESSION:
            # Sessions expire after 7 days, and a duplicate login elsewhere kills
            # them sooner — re-auth silently rather than making the user care.
            self._login()
            body = self._call(api, method, version, params)

        if not body.get("success"):
            code = body.get("error", {}).get("code", 0)
            raise ValueError(f"Synology {api}.{method} failed: {ERRORS.get(code, f'error {code}')}")

        return body.get("data", {})

    def _call(self, api: str, method: str, version: int, params: dict) -> dict:
        """Issue one API request and return the decoded body."""
        query = {"api": api, "version": version, "method": method, "_sid": self.sid}
        query.update({k: v for k, v in params.items() if v is not None})

        with self._client() as client:
            reply = client.get(f"/webapi/{self._path_for(api)}", params=query)
        return reply.json()

    @staticmethod
    def _file_dict(item: dict) -> dict:
        """Normalize a File Station entry to the CLI/agent file shape."""
        extra = item.get("additional", {})
        return {
            "path": item.get("path", ""),
            "name": item.get("name", ""),
            "type": "dir" if item.get("isdir") else "file",
            "size": extra.get("size", 0) or 0,
            "modified": extra.get("time", {}).get("mtime", 0) or 0,
        }

    # === Listing ===

    def list_files(self, path: str = None, last: int = 20) -> list:
        """List shared folders, or the contents of one folder.

        Args:
            path: Folder path starting with a shared folder, e.g. /home/photos.
                  Omit to list the shared folders themselves.
            last: How many entries to return (default: 20)

        Returns:
            List of file dicts (path, name, type, size, modified)
        """
        if last < 1:
            return []

        if not path:
            data = self._request("SYNO.FileStation.List", "list_share", limit=last)
        else:
            data = self._request(
                "SYNO.FileStation.List",
                "list",
                folder_path=path,
                limit=last,
                sort_by="mtime",
                sort_direction="desc",
                additional='["size","time"]',
            )

        entries = data.get("shares") or data.get("files") or []
        return [self._file_dict(item) for item in entries]

    def search_files(self, query: str, path: str = "/", last: int = 20) -> list:
        """Search for files by name under a folder.

        File Station search is non-blocking: start a task, poll until it reports
        finished, then clean up the temporary result database.

        Args:
            query: Glob or plain substring to match against file names
            path: Folder to search under (default: everything)
            last: How many matches to return (default: 20)

        Returns:
            List of file dicts, matching files only
        """
        needle = query.strip()
        if not needle or last < 1:
            return []

        started = self._request(
            "SYNO.FileStation.Search", "start", folder_path=path, pattern=needle, recursive=True
        )
        task = started["taskid"]

        # Results stream in as the task walks the tree; poll until DSM says done.
        for _ in range(100):
            found = self._request("SYNO.FileStation.Search", "list", taskid=task, limit=last)
            if found.get("finished"):
                break
            time.sleep(0.3)

        self._request("SYNO.FileStation.Search", "clean", taskid=task)
        return [self._file_dict(item) for item in found.get("files", [])]

    # === Transfer ===

    def download(self, path: str, dest: str = ".") -> str:
        """Download a file from the NAS.

        Args:
            path: Full NAS path, e.g. /home/photos/cat.jpg
            dest: Destination directory or full local path (default: cwd)

        Returns:
            Confirmation with the path written
        """
        if not self.sid:
            self._login()

        target = Path(dest).expanduser()
        if target.is_dir():
            target = target / Path(path).name

        query = {
            "api": "SYNO.FileStation.Download",
            "version": 2,
            "method": "download",
            "path": f'["{path}"]',
            "mode": "download",
            "_sid": self.sid,
        }

        with self._client() as client:
            with client.stream("GET", f"/webapi/{self._path_for('SYNO.FileStation.Download')}", params=query) as reply:
                # DSM signals failure with a JSON body instead of an HTTP status.
                if reply.headers.get("content-type", "").startswith("application/json"):
                    reply.read()
                    code = reply.json().get("error", {}).get("code", 0)
                    raise ValueError(f"Synology download failed: {ERRORS.get(code, f'error {code}')}")

                with open(target, "wb") as out:
                    for chunk in reply.iter_bytes():
                        out.write(chunk)

        return f"Downloaded to {target}"

    def upload(self, local_path: str, path: str, overwrite: bool = False) -> str:
        """Upload a local file to a NAS folder.

        Args:
            local_path: Local file to send
            path: Destination folder on the NAS, e.g. /home/photos
            overwrite: Replace an existing file of the same name (default: skip)

        Returns:
            Confirmation with the destination
        """
        local = Path(local_path).expanduser()
        if not local.is_file():
            raise ValueError(f"File not found: {local_path}")

        if not self.sid:
            self._login()

        # RFC 1867 with a DSM constraint: the binary part must come last. httpx
        # writes every `data` field before any `files` entry, which satisfies it.
        fields = {
            "api": "SYNO.FileStation.Upload",
            "version": "2",
            "method": "upload",
            "path": path,
            "create_parents": "true",
            # Always explicit: DSM returns error 1805 rather than a default when
            # the destination exists and this is missing.
            "overwrite": "true" if overwrite else "false",
            "_sid": self.sid,
        }

        with self._client() as client:
            with open(local, "rb") as handle:
                reply = client.post(
                    f"/webapi/{self._path_for('SYNO.FileStation.Upload')}",
                    data=fields,
                    files={"file": (local.name, handle, "application/octet-stream")},
                )

        body = reply.json()
        if not body.get("success"):
            code = body.get("error", {}).get("code", 0)
            raise ValueError(f"Synology upload failed: {ERRORS.get(code, f'error {code}')}")

        return f"Uploaded to {path}/{local.name}"

    def share(self, path: str) -> str:
        """Create a public sharing link for a file or folder.

        Args:
            path: Full NAS path to share

        Returns:
            The sharing URL
        """
        data = self._request("SYNO.FileStation.Sharing", "create", version=3, path=path)
        links = data.get("links", [])
        if not links:
            raise ValueError(f"Synology returned no sharing link for {path}")
        return links[0]["url"]


def save_credentials(**values):
    """Persist SYNOLOGY_* values to ~/.co/keys.env and the current environment."""
    from ..cli.commands.project_cmd_lib import upsert_env

    env_file = Path(os.getenv("AGENT_CONFIG_PATH", os.path.expanduser("~/.co"))) / "keys.env"
    env_file.parent.mkdir(parents=True, exist_ok=True)

    updates = {f"SYNOLOGY_{key.upper()}": str(value) for key, value in values.items()}
    os.environ.update(updates)
    upsert_env(env_file, updates)
