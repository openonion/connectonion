"""
Purpose: Read-only Granola public API v1 client and personal-folder scope checks for `co granola`
LLM-Note:
  Dependencies: imports from [datetime, email.utils, math, re, time, urllib.parse, httpx, environment.py, secret_store.py] | imported by [cli/commands/granola_commands.py] | tested by [tests/unit/test_granola.py, tests/unit/test_granola_commands.py]
  Data flow: credential() resolves GRANOLA_API_KEY (shell -> selected .env -> encrypted store) -> GranolaClient sends Bearer GETs to https://public-api.granola.ai/v1 -> personal-folder scope check (space_id is None, explicit --include-children when subfolders exist) -> sanitized note/folder dicts with credential-shaped text redacted
  State/Effects: read-only network GETs to Granola API; zero local writes, zero REM state coupling
  Errors: GranolaError(message, next_step, kind, detail) with machine-readable kind (unauthorized, forbidden, not_found, scope, rate_limited, incomplete, invalid)
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import re
import time
from urllib.parse import quote, urlsplit

import httpx

BASE_URL = "https://public-api.granola.ai/v1"
KEY = "GRANOLA_API_KEY"
SET_KEY = "co env set GRANOLA_API_KEY grn_... --secret"
TIMEOUT = 30.0
MAX_PAGES = 1_000
MAX_SELECTED = 1_000
MAX_PAGE_SIZE = 30
MAX_RETRIES = 3
MAX_WAIT_SECONDS = 30.0
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
WITHHELD = "[withheld: possible credential]"

# Matches high-signal credential prefixes so accidental keys in meeting titles or summaries are withheld.
KEY_SHAPES = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{16,}|ntn_[A-Za-z0-9]{20,}|"
    r"secret_[A-Za-z0-9]{24,}|AIza[0-9A-Za-z_-]{30,}|AKIA[0-9A-Z]{16}|grn_[A-Za-z0-9_-]{20,})\b"
)

_sleep = time.sleep


class GranolaError(ValueError):
    """Actionable Granola failure with a safe message, recovery command, and stable kind."""

    def __init__(self, message: str, next_step: str, kind: str = "invalid", detail: dict | None = None):
        super().__init__(message)
        self.next_step = next_step
        self.kind = kind
        self.detail = detail or {}


class Credential:
    """Active Granola key and where it came from ('shell' or 'key'), without exposing the token."""

    def __init__(self, token: str, source: str):
        self.token = token
        self.source = source

    @property
    def label(self) -> str:
        return f"the {KEY} exported in your shell" if self.source == "shell" else KEY


def _read_saved_key() -> str:
    from ..environment import setting
    from ..secret_store import SecretStoreError

    try:
        return setting(KEY) or ""
    except SecretStoreError:
        raise GranolaError(
            "Saved Granola key cannot be unlocked. Inspect co env (values hidden) or replace it in a local terminal.",
            "co env set GRANOLA_API_KEY --secret --prompt",
            "unauthorized",
        ) from None


def credential() -> Credential:
    """Resolve GRANOLA_API_KEY: shell environment first, then .env / encrypted secret store."""
    from ..environment import display_path, load_environment, process_environment, selected_env_file

    load_environment()
    exported = (process_environment().get(KEY) or "").strip()
    if exported:
        return Credential(exported, "shell")
    saved = _read_saved_key().strip()
    if saved:
        return Credential(saved, "key")
    raise GranolaError(
        f"Granola is not connected in {display_path(selected_env_file())}. "
        f"Create a personal API key in Granola settings and save it with {SET_KEY}.",
        SET_KEY,
        "unauthorized",
    )


def valid_id(value: str) -> bool:
    """True when value is a clean single-token Granola folder or note identifier."""
    return (
        isinstance(value, str)
        and 0 < len(value) <= 256
        and value.isascii()
        and value.isprintable()
        and not any(ch.isspace() or ch in "/\\" for ch in value)
        and not KEY_SHAPES.search(value)
    )


def redact_text(value: str | None) -> str:
    """Return text with credential-shaped substrings replaced by WITHHELD."""
    if not isinstance(value, str):
        return ""
    if KEY_SHAPES.search(value):
        return WITHHELD
    return value


def clean_link(url: object) -> str | None:
    """Keep clean https Granola links without query strings or fragments."""
    if not isinstance(url, str) or not url or KEY_SHAPES.search(url):
        return None
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
        return None
    return url


def parse_iso_utc(raw: str, *, flag_name: str = "--since") -> datetime:
    """Parse an ISO-8601 timestamp with explicit timezone into UTC."""
    if not isinstance(raw, str) or "T" not in raw:
        raise GranolaError(
            f"{flag_name} must be an ISO-8601 date and time with timezone, e.g. 2026-11-20T00:00:00Z.",
            "co granola changes --help",
            "invalid",
        )
    text = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise GranolaError(
            f"{flag_name} must be an ISO-8601 date and time with timezone, e.g. 2026-11-20T00:00:00Z.",
            "co granola changes --help",
            "invalid",
        ) from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise GranolaError(
            f"{flag_name} must include a timezone offset or Z, e.g. 2026-11-20T00:00:00Z.",
            "co granola changes --help",
            "invalid",
        )
    return dt.astimezone(timezone.utc)


def _retry_delay(retry_after_header: str | None, attempt: int) -> float:
    if retry_after_header:
        try:
            wait = float(retry_after_header)
        except ValueError:
            try:
                wait = parsedate_to_datetime(retry_after_header).timestamp() - time.time()
            except (TypeError, ValueError, OverflowError):
                return min(float(2**attempt), MAX_WAIT_SECONDS)
        if math.isfinite(wait) and wait >= 0:
            return wait
        if math.isinf(wait) and wait > 0:
            return wait
    return min(float(2**attempt), MAX_WAIT_SECONDS)


def _collection(data: object, name: str) -> list[dict]:
    rows = data.get(name) if isinstance(data, dict) else None
    if (
        not isinstance(rows, list)
        or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] for row in rows)
        or not isinstance(data.get("hasMore", False), bool)  # type: ignore[union-attr]
        or any(data.get(key) for key in ("error", "errors", "warnings"))  # type: ignore[union-attr]
    ):
        raise GranolaError(
            f"Granola returned malformed {name} pagination data.",
            "co granola check",
            "incomplete",
        )
    return rows


class GranolaClient:
    """Read-only Granola API v1 client: check connection, list personal folders, list/read notes."""

    def __init__(self, *, _base_url: str = BASE_URL, _http: httpx.Client | None = None) -> None:
        self._base_url = _base_url.rstrip("/")
        if _http is not None:
            self.credential = Credential("injected", "key")
            self._http = _http
        else:
            self.credential = credential()
            self._http = httpx.Client(
                headers={"Authorization": f"Bearer {self.credential.token}"},
                timeout=TIMEOUT,
            )

    def _request(self, path: str, *, params: dict | None = None) -> dict:
        url = self._base_url + path
        last_status: int | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._http.get(url, params=params)
            except httpx.TimeoutException:
                last_status = None
                if attempt < MAX_RETRIES:
                    _sleep(min(float(2**attempt), MAX_WAIT_SECONDS))
                    continue
                raise GranolaError(
                    f"Request to Granola API timed out after {TIMEOUT:g}s.",
                    "co granola check",
                    "incomplete",
                ) from None
            except httpx.RequestError:
                last_status = None
                if attempt < MAX_RETRIES:
                    _sleep(min(float(2**attempt), MAX_WAIT_SECONDS))
                    continue
                raise GranolaError(
                    "Network error while reaching Granola API.",
                    "co granola check",
                    "incomplete",
                ) from None

            status = response.status_code
            if status == 401:
                raise GranolaError(
                    "Granola rejected GRANOLA_API_KEY (HTTP 401: missing, expired, or invalid).",
                    SET_KEY,
                    "unauthorized",
                )
            if status == 403:
                raise GranolaError(
                    "Granola denied access to this resource (HTTP 403).",
                    "co granola check",
                    "forbidden",
                )
            if status == 404:
                raise GranolaError(
                    "Granola note or folder was not found (HTTP 404: deleted, inaccessible, or still processing).",
                    "co granola folders",
                    "not_found",
                )
            if status in RETRY_STATUSES:
                last_status = status
                delay = _retry_delay(response.headers.get("Retry-After"), attempt)
                if delay > MAX_WAIT_SECONDS:
                    raise GranolaError(
                        f"Granola rate-limited the request (HTTP {status}) with Retry-After > {MAX_WAIT_SECONDS:g}s; retry later.",
                        "co granola check",
                        "rate_limited" if status == 429 else "incomplete",
                    )
                if attempt < MAX_RETRIES:
                    _sleep(delay)
                    continue
                raise GranolaError(
                    f"Granola returned HTTP {status} on {MAX_RETRIES + 1} consecutive attempts.",
                    "co granola check",
                    "rate_limited" if status == 429 else "incomplete",
                )
            if status >= 400:
                raise GranolaError(
                    f"Granola returned unexpected HTTP {status}.",
                    "co granola check",
                    "incomplete",
                )
            try:
                body = response.json()
            except ValueError:
                raise GranolaError(
                    f"Granola returned non-JSON body (HTTP {status}).",
                    "co granola check",
                    "incomplete",
                ) from None
            if not isinstance(body, dict):
                raise GranolaError(
                    "Granola returned an unexpected JSON shape.",
                    "co granola check",
                    "incomplete",
                )
            return body

        raise GranolaError(
            f"Granola request failed (last status: {last_status}).",
            "co granola check",
            "incomplete",
        )

    def check(self) -> dict:
        """Verify API key with a single-note read and count accessible personal folders."""
        data = self._request("/notes", params={"page_size": 1})
        notes = _collection(data, "notes")
        sample = redact_text(notes[0].get("title")) if notes else ""
        folders = self.list_folders()
        return {
            "verified_read": True,
            "credential_source": self.credential.source,
            "credential_label": self.credential.label,
            "sample_title": sample or "(no notes yet)",
            "personal_folders": len(folders["personal"]),
            "shared_skipped": folders["shared_count"],
        }

    def _raw_folders(self) -> list[dict]:
        all_folders: list[dict] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        pages_fetched = 0

        while True:
            params: dict = {"page_size": MAX_PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor
            data = self._request("/folders", params=params)
            batch = _collection(data, "folders")
            all_folders.extend(batch)
            pages_fetched += 1

            if not data.get("hasMore", False):
                break
            next_cursor = data.get("cursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                raise GranolaError("Granola folders API set hasMore=true without a cursor.", "co granola check", "incomplete")
            if next_cursor in seen_cursors:
                raise GranolaError("Granola folders API repeated a pagination cursor.", "co granola check", "incomplete")
            if pages_fetched >= MAX_PAGES:
                raise GranolaError(f"Granola folders pagination exceeded {MAX_PAGES} pages.", "co granola check", "incomplete")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        return all_folders

    def list_folders(self) -> dict:
        """Return personal folders (space_id is None) with child counts, plus count of skipped shared folders."""
        raw = self._raw_folders()
        children_by_parent: dict[str, list[dict]] = {}
        for f in raw:
            parent = f.get("parent_folder_id")
            if isinstance(parent, str) and parent:
                children_by_parent.setdefault(parent, []).append(f)

        personal: list[dict] = []
        shared_count = 0
        for f in raw:
            if "space_id" not in f:
                raise GranolaError("Granola folder entry omitted space_id; refusing ambiguous scope.", "co granola check", "incomplete")
            if f.get("space_id") is not None:
                shared_count += 1
                continue
            fid = f["id"]
            personal.append({
                "id": fid,
                "name": redact_text(f.get("name") or "(untitled)"),
                "parent_folder_id": f.get("parent_folder_id"),
                "child_count": len(children_by_parent.get(fid, [])),
            })

        return {"personal": personal, "shared_count": shared_count, "_all": raw}

    def resolve_personal_folder(self, folder_id: str, include_children: bool = False) -> dict:
        """Verify folder_id is a personal folder and enforce child-folder consent & personal-only descendants."""
        if not valid_id(folder_id):
            raise GranolaError("Folder ID is invalid.", "co granola folders", "invalid")

        raw = self._raw_folders()
        by_id = {f["id"]: f for f in raw if isinstance(f.get("id"), str)}
        target = by_id.get(folder_id)
        if target is None:
            raise GranolaError(
                f"Folder {folder_id} was not found in your Granola account.",
                "co granola folders",
                "not_found",
            )
        if "space_id" not in target or target.get("space_id") is not None:
            raise GranolaError(
                f"Folder {folder_id} belongs to a shared Granola space; co granola reads personal folders only.",
                "co granola folders",
                "scope",
            )

        children_map: dict[str, list[str]] = {}
        for f in raw:
            parent = f.get("parent_folder_id")
            if isinstance(parent, str) and parent:
                children_map.setdefault(parent, []).append(f["id"])

        descendants: set[str] = set()
        stack = list(children_map.get(folder_id, []))
        while stack:
            cid = stack.pop()
            if cid in descendants:
                continue
            descendants.add(cid)
            stack.extend(children_map.get(cid, []))

        if descendants and not include_children:
            raise GranolaError(
                f"Folder {folder_id} has {len(descendants)} child folder(s), and Granola includes child folders when listing a parent. "
                f"Re-run with --include-children to include them, or pick a leaf folder.",
                f"co granola notes {folder_id} --include-children",
                "scope",
            )

        for cid in descendants:
            child = by_id.get(cid)
            if not child or "space_id" not in child or child.get("space_id") is not None:
                raise GranolaError(
                    f"Child folder {cid} under {folder_id} belongs to a shared space; select a personal leaf folder instead.",
                    "co granola folders",
                    "scope",
                )

        return {
            "folder_id": folder_id,
            "name": redact_text(target.get("name") or "(untitled)"),
            "allowed_ids": {folder_id, *descendants},
            "include_children": include_children,
        }

    def list_notes(
        self,
        folder_id: str,
        *,
        include_children: bool = False,
        limit: int = 20,
        updated_after: str | None = None,
    ) -> list[dict]:
        """List non-deleted notes in one verified personal folder."""
        if not (1 <= limit <= MAX_SELECTED):
            raise GranolaError(f"--limit must be between 1 and {MAX_SELECTED}.", "co granola notes --help", "invalid")

        self.resolve_personal_folder(folder_id, include_children=include_children)

        all_notes: list[dict] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        pages_fetched = 0

        while len(all_notes) < limit:
            page_size = min(MAX_PAGE_SIZE, limit - len(all_notes))
            params: dict = {"folder_id": folder_id, "page_size": page_size}
            if cursor:
                params["cursor"] = cursor
            if updated_after:
                params["updated_after"] = updated_after

            data = self._request("/notes", params=params)
            batch = _collection(data, "notes")
            for row in batch:
                if row.get("deleted_at") is None:
                    all_notes.append(row)
                    if len(all_notes) >= limit:
                        break
            pages_fetched += 1

            if not data.get("hasMore", False):
                break
            next_cursor = data.get("cursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                raise GranolaError("Granola notes API set hasMore=true without a cursor.", "co granola check", "incomplete")
            if next_cursor in seen_cursors:
                raise GranolaError("Granola notes API repeated a pagination cursor.", "co granola check", "incomplete")
            if pages_fetched >= MAX_PAGES:
                raise GranolaError(f"Granola notes pagination exceeded {MAX_PAGES} pages.", "co granola check", "incomplete")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        return all_notes

    def list_changes(self, *, since: datetime, folder_id: str, include_children: bool = False) -> list[dict]:
        """List notes in a personal folder updated after `since` (oldest update first, capped at MAX_SELECTED)."""
        self.resolve_personal_folder(folder_id, include_children=include_children)
        iso_since = since.isoformat().replace("+00:00", "Z")

        changed: list[tuple[datetime, dict]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        pages_fetched = 0

        while True:
            params: dict = {"folder_id": folder_id, "page_size": MAX_PAGE_SIZE, "updated_after": iso_since}
            if cursor:
                params["cursor"] = cursor
            data = self._request("/notes", params=params)
            batch = _collection(data, "notes")
            pages_fetched += 1

            for row in batch:
                if row.get("deleted_at") is not None:
                    continue
                nid = row.get("id", "")
                if not valid_id(nid):
                    raise GranolaError("Granola returned an invalid note ID.", "co granola check", "incomplete")
                raw_time = row.get("updated_at")
                if not isinstance(raw_time, str):
                    raise GranolaError(f"Granola note {nid} omitted updated_at.", "co granola check", "incomplete")
                updated_dt = parse_iso_utc(raw_time, flag_name="updated_at")
                if updated_dt <= since:
                    continue
                changed.append((
                    updated_dt,
                    {
                        "id": nid,
                        "version": raw_time,
                        "time": raw_time,
                        "title": redact_text(row.get("title") or "(untitled)"),
                        "link": clean_link(row.get("web_url")),
                    },
                ))
                if len(changed) >= MAX_SELECTED and data.get("hasMore", False):
                    raise GranolaError(
                        f"More than {MAX_SELECTED} notes changed since {iso_since}; pass a more recent --since.",
                        f"co granola changes --since {iso_since} --folder {folder_id}",
                        "incomplete",
                    )

            if not data.get("hasMore", False):
                break
            next_cursor = data.get("cursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                raise GranolaError("Granola notes API set hasMore=true without a cursor.", "co granola check", "incomplete")
            if next_cursor in seen_cursors:
                raise GranolaError("Granola notes API repeated a pagination cursor.", "co granola check", "incomplete")
            if pages_fetched >= MAX_PAGES:
                raise GranolaError(f"Granola notes pagination exceeded {MAX_PAGES} pages.", "co granola check", "incomplete")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        changed.sort(key=lambda pair: (pair[0], pair[1]["id"]))
        return [item for _, item in changed]

    def get_note(self, note_id: str, *, folder_id: str | None = None, include_children: bool = False) -> dict:
        """Fetch one live Granola note, drop private fields, and verify personal-folder scope."""
        clean_id = note_id[len("granola:"):] if isinstance(note_id, str) and note_id.startswith("granola:") else note_id
        if not valid_id(clean_id):
            raise GranolaError("Note ID is invalid.", "co granola folders", "invalid")

        scope_ids: set[str] | None = None
        if folder_id is not None:
            scope = self.resolve_personal_folder(folder_id, include_children=include_children)
            scope_ids = scope["allowed_ids"]

        raw = self._request(f"/notes/{quote(clean_id, safe='')}")
        if raw.get("id") != clean_id:
            raise GranolaError("Granola returned a mismatched note ID.", "co granola check", "incomplete")
        if raw.get("deleted_at") is not None:
            raise GranolaError(f"Granola note {clean_id} was deleted.", "co granola folders", "not_found")
        if raw.get("space_id") is not None:
            raise GranolaError(
                f"Note {clean_id} belongs to a shared Granola space; co granola reads personal notes only.",
                "co granola folders",
                "scope",
            )

        membership_ids: set[str] = set()
        if isinstance(raw.get("folder_id"), str) and raw["folder_id"]:
            membership_ids.add(raw["folder_id"])
        if isinstance(raw.get("folder_membership"), list):
            for entry in raw["folder_membership"]:
                if isinstance(entry, dict):
                    if entry.get("space_id") is not None:
                        raise GranolaError(
                            f"Note {clean_id} is filed in a shared space; co granola reads personal notes only.",
                            "co granola folders",
                            "scope",
                        )
                    if isinstance(entry.get("id"), str) and entry["id"]:
                        membership_ids.add(entry["id"])

        if scope_ids is not None and not (membership_ids & scope_ids):
            raise GranolaError(
                f"Note {clean_id} is outside selected personal folder {folder_id}.",
                f"co granola notes {folder_id}",
                "scope",
            )

        summary_obj = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
        summary_md = raw.get("summary_markdown") or summary_obj.get("markdown")
        summary_txt = raw.get("summary_text") or summary_obj.get("plain_text")
        body = summary_md if isinstance(summary_md, str) and summary_md.strip() else (summary_txt if isinstance(summary_txt, str) else "")

        event = raw.get("calendar_event") if isinstance(raw.get("calendar_event"), dict) else {}
        cal_clean = {
            k: event[k]
            for k in ("scheduled_start", "scheduled_end", "scheduled_start_time", "scheduled_end_time")
            if isinstance(event.get(k), str)
        }
        meeting_time = cal_clean.get("scheduled_start") or cal_clean.get("scheduled_start_time") or raw.get("created_at")
        updated_at = raw.get("updated_at") or raw.get("created_at") or ""

        out = {
            "id": clean_id,
            "version": updated_at,
            "time": updated_at,
            "created": raw.get("created_at"),
            "meeting_time": meeting_time,
            "title": redact_text(raw.get("title") or "(untitled)"),
            "text": redact_text(body),
            "author": None,
            "link": clean_link(raw.get("web_url")),
            "folder_id": raw.get("folder_id") or ( sorted(membership_ids)[0] if membership_ids else None ),
        }
        if cal_clean:
            out["calendar_event"] = cal_clean
        return out
