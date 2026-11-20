"""
Purpose: Read-only, explicitly scoped Granola meeting-notes source for co rem.
LLM-Note:
  Dependencies: imports from [os, re, time, httpx, importlib.metadata, datetime, yaml, pathlib] | imported by [cli/commands/granola_commands.py] | tested by [tests/unit/test_granola.py, tests/unit/test_granola_adapter.py]
  Data flow: GranolaClient methods → Bearer-token httpx.Client GET requests to BASE_URL → raw Granola API v1 JSON → returned as plain dicts/lists to the CLI/import layer; write_source_yaml() creates source.yaml under source_dir
  State/Effects: GRANOLA_API_KEY is read via setting() (process/file/encrypted store; never logged) | no writes to Granola (read-only) | write_source_yaml() creates source.yaml under source_dir
  Errors: GranolaConfigError (missing/invalid key or profile) | GranolaAuthError (HTTP 401) | GranolaPermissionError (HTTP 403) | GranolaIncompleteRead (5xx retries exhausted, carries partial raw pages)

Granola public-API client: verify key, list folders, list notes, get note.

Usage (Phase 2+):
    from connectonion.useful_tools.granola import GranolaClient, validate_profile
    client = GranolaClient()
    folders = client.list_folders()
    notes   = client.list_notes(folder_id="fld-abc", limit=50)
"""

import os
import math
from email.utils import parsedate_to_datetime
import re
import time

# ---------------------------------------------------------------------------
# Module-level constants — frozen here as part of the Phase-1 contract.
# ---------------------------------------------------------------------------

BASE_URL = "https://public-api.granola.ai/v1"
TIMEOUT = 30.0

#: Maximum number of cursor-advance pages before we stop and raise GranolaIncompleteRead.
MAX_PAGES = 1_000
#: Maximum total notes a single list_notes() call may return.
MAX_SELECTED = 1_000

#: Granola page_size upper bound (official maximum is 30).
_MAX_PAGE_SIZE = 30

#: HTTP statuses that warrant a limited automatic retry.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
#: Maximum number of retries for a single transient failure before giving up.
_MAX_RETRIES = 3

# Profile: 1–64 chars, ASCII alphanumeric + hyphen, must start and end with alphanumeric.
# Colons are excluded to prevent breakage of the composite record ID "granola:<profile>:<note_id>".
PROFILE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?$")

# ---------------------------------------------------------------------------
# Exceptions — all are ValueError subclasses so CLI can catch them uniformly.
# ---------------------------------------------------------------------------


class GranolaConfigError(ValueError):
    """Local configuration missing or invalid (GRANOLA_API_KEY / profile)."""


class GranolaAuthError(ValueError):
    """Granola returned HTTP 401 — API key is missing, expired, or invalid."""


class GranolaPermissionError(ValueError):
    """Granola returned HTTP 403 — this key cannot access the requested resource."""


class GranolaIncompleteRead(Exception):
    """Retry budget exhausted before all requested notes could be fetched.

    Carries the raw note batches successfully received before the failure
    and a safe, non-secret failure reason.  The import layer maps
    partial_pages to records and persists them; the CLI then marks the
    result complete:false and exits 1.

    Attributes:
        reason:        human-readable safe failure description (no credentials).
        partial_pages: list of raw note-batch lists, one entry per page fetched.
    """

    def __init__(self, reason: str, partial_pages: list):
        super().__init__(reason)
        self.reason = reason
        self.partial_pages: list[list[dict]] = partial_pages


# ---------------------------------------------------------------------------
# Profile validation (Phase-1 contract; used by CLI before any network call).
# ---------------------------------------------------------------------------


def validate_profile(profile: str) -> None:
    """Raise GranolaConfigError if *profile* is not a valid non-secret user label.

    Profile rules (frozen in Phase 1):
    - 1–64 characters
    - ASCII letters, digits, and hyphens only
    - Must start and end with a letter or digit (never a hyphen)
    - Must not contain a colon (colons break the compound record ID)

    The profile is a non-secret convenience label chosen by the user
    (e.g. ``work``, ``home-2024``).  It is not the API key or an email.
    """
    if not isinstance(profile, str) or not PROFILE_RE.fullmatch(profile):
        raise GranolaConfigError(
            f"Invalid profile {profile!r}: must be 1–64 ASCII letters/digits/hyphens, "
            "starting and ending with a letter or digit (e.g. 'work', 'home-2024').\n"
            "Repair: choose a profile that matches [A-Za-z0-9][A-Za-z0-9-]{0,62}[A-Za-z0-9]?$"
        )


def validate_source_identity(source_dir, folder_id: str, profile: str) -> None:
    """Refuse to reuse a Granola output directory for another source identity."""
    import yaml
    from pathlib import Path

    target = Path(source_dir) / "source.yaml"
    if not target.exists():
        return
    try:
        existing = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GranolaConfigError(
            f"Cannot read existing source.yaml at {target}: {exc}. "
            "Choose a separate --output directory or repair this file."
        ) from exc
    if isinstance(existing, dict) and existing.get("credential_binding"):
        import hashlib
        from ..environment import setting
        from ..secret_store import SecretStoreError
        try:
            key = setting("GRANOLA_API_KEY") or ""
        except SecretStoreError:
            raise GranolaConfigError("Saved Granola key cannot be unlocked. Inspect co env and reconnect.") from None
        if not key or hashlib.sha256(key.encode()).hexdigest() != existing["credential_binding"]:
            raise GranolaConfigError("This source is bound to another Granola key. Preserve it and use a separate notebook/profile.")
    scope = existing.get("scope") if isinstance(existing, dict) else None
    if (
        not isinstance(scope, dict)
        or existing.get("driver") != "granola"
        or existing.get("account") != profile
        or scope.get("folder_id") != folder_id
    ):
        raise GranolaConfigError(
            f"Existing source.yaml at {target} belongs to a different source, "
            "profile, or personal folder. Choose a separate --output directory."
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _TransientError(Exception):
    """Raised internally by _request_once() for 429/5xx — triggers the retry loop."""

    def __init__(self, status: int, retry_after: str | None = None):
        super().__init__(f"Transient HTTP {status}")
        self.status = status
        self.retry_after = retry_after


def _retry_delay(retry_after_header: str | None, attempt: int) -> float:
    """Honor server delays, including HTTP-date, without blocking indefinitely."""
    if retry_after_header:
        try:
            wait = float(retry_after_header)
        except ValueError:
            try:
                wait = parsedate_to_datetime(retry_after_header).timestamp() - time.time()
            except (TypeError, ValueError, OverflowError):
                return min(float(2 ** attempt), 30.0)
        if math.isfinite(wait) and wait >= 0:
            return wait
        if math.isinf(wait) and wait > 0:
            return wait
    return min(float(2 ** attempt), 30.0)


def _collection(data, name: str, partial_pages=None) -> list[dict]:
    """Malformed collections are failed reads, never successful empty results."""
    rows = data.get(name) if isinstance(data, dict) else None
    if (not isinstance(rows, list) or any(not isinstance(row, dict) or
            not isinstance(row.get("id"), str) or not row["id"] for row in rows)
            or not isinstance(data.get("hasMore", False), bool)
            or any(data.get(key) for key in ("error", "errors", "warnings"))):
        raise GranolaIncompleteRead(f"Granola returned malformed {name} pagination data.", partial_pages or [])
    return rows


# ---------------------------------------------------------------------------
# GranolaClient — Phase-2 implementation.
# ---------------------------------------------------------------------------


class GranolaClient:
    """Read-only Granola API client: verify key, list folders, list notes, get note.

    Reads GRANOLA_API_KEY using the existing process/file/encrypted store.  The key is transmitted via
    Authorization: Bearer header and is never logged, stored, or returned.

    Methods raise GranolaConfigError / GranolaAuthError / GranolaPermissionError
    on non-transient failures; transient 429/5xx failures are retried up to
    _MAX_RETRIES times before raising GranolaIncompleteRead.
    """

    def __init__(self, *, _base_url: str = BASE_URL, _http=None) -> None:
        """Read GRANOLA_API_KEY from the environment; raise GranolaConfigError if absent.

        Args:
            _base_url: Override the API base URL (tests; internal use only).
            _http:     Inject a pre-built httpx.Client (tests; internal use only).
                       When None, a new client is created with the Bearer key from env.
        """
        import httpx

        from ..environment import setting
        from ..secret_store import SecretStoreError
        try:
            key = setting("GRANOLA_API_KEY") or ""
        except SecretStoreError:
            raise GranolaConfigError("Saved Granola key cannot be unlocked. Inspect co env (values hidden); "
                                     "repair with co env set GRANOLA_API_KEY --secret --prompt in a local terminal.") from None
        if not key:
            raise GranolaConfigError(
                "GRANOLA_API_KEY environment variable is missing or empty.\n"
                "Set it to your personal Granola API key before using GranolaClient."
            )
        self._base_url = _base_url.rstrip("/")
        if _http is not None:
            self._http = _http
        else:
            self._http = httpx.Client(
                headers={"Authorization": f"Bearer {key}"},
                timeout=TIMEOUT,
            )

    # ------------------------------------------------------------------
    # Private request helpers
    # ------------------------------------------------------------------

    def _request_once(self, path: str, *, params: dict | None = None) -> dict:
        """Single GET attempt; raises typed errors, never returns None.

        Raises:
            GranolaAuthError:      on HTTP 401.
            GranolaPermissionError: on HTTP 403.
            ValueError:            on HTTP 404 or non-JSON body.
            GranolaConfigError:    on network / timeout error or unexpected status.
            _TransientError:       on HTTP 429 / 5xx (caught by _request).
        """
        import httpx

        url = self._base_url + path
        try:
            response = self._http.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise GranolaIncompleteRead(f"Request to Granola API timed out after {TIMEOUT}s.", []) from exc
        except httpx.RequestError as exc:
            raise GranolaIncompleteRead("Network error while reaching Granola API.", []) from exc

        status = response.status_code
        if status == 401:
            raise GranolaAuthError(
                "Granola API returned 401 — API key is missing, expired, or invalid."
            )
        if status == 403:
            raise GranolaPermissionError(
                "Granola API returned 403 — this key cannot access the requested resource."
            )
        if status == 404:
            raise ValueError(
                "Granola API returned 404 — note not found, deleted, or not yet processed."
            )
        if status in _RETRY_STATUSES:
            raise _TransientError(status, retry_after=response.headers.get("Retry-After"))
        if status >= 400:
            raise GranolaConfigError(f"Granola API returned unexpected HTTP {status}.")

        try:
            return response.json()
        except Exception as exc:
            raise ValueError(
                f"Granola API returned non-JSON response (HTTP {status})."
            ) from exc

    def _request(
        self, path: str, *, params: dict | None = None, partial_pages: list | None = None
    ) -> dict:
        """GET with automatic retry on transient failures.

        Calls _request_once up to (_MAX_RETRIES + 1) times.  Raises
        GranolaIncompleteRead (with partial_pages accumulated so far) after all
        retry attempts are exhausted on consecutive transient failures.
        """
        last_exc: _TransientError | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return self._request_once(path, params=params)
            except GranolaIncompleteRead as exc:
                raise GranolaIncompleteRead(exc.reason, partial_pages or exc.partial_pages) from exc
            except _TransientError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = _retry_delay(exc.retry_after, attempt)
                    if delay > 30:
                        raise GranolaIncompleteRead(
                            f"Granola Retry-After for HTTP {exc.status} exceeds the 30s automatic wait limit; "
                            "wait before retrying and honor the server delay.", partial_pages or []) from exc
                    time.sleep(delay)

        raise GranolaIncompleteRead(
            reason=(
                f"Granola API returned transient HTTP {last_exc.status} "  # type: ignore[union-attr]
                f"on {_MAX_RETRIES + 1} consecutive attempts."
            ),
            partial_pages=partial_pages or [],
        )

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def verify(self) -> dict:
        """Probe the API with a minimal single-note request.

        Returns {"verified_read": True, "note": "..."} on success.
        Only proves the key can perform the smallest read; does not prove
        full folder/space access or account identity.
        Never exposes the key in the return value or logs.
        """
        data = self._request("/notes", params={"page_size": 1})
        notes = _collection(data, "notes")
        note_summary = notes[0].get("title", "(untitled)") if notes else "(no notes yet)"
        return {"verified_read": True, "note": note_summary}

    def list_folders(self) -> list[dict]:
        """Return all personal folders accessible with this key.

        Paginates automatically until hasMore is False or MAX_PAGES is reached.
        An empty list is a valid response (no folders created yet).
        HTTP 403 is GranolaPermissionError, not an inference about key type.

        Raises:
            GranolaIncompleteRead: if retries exhaust or pagination guard trips;
                                   carries partial_pages of folder batches received.
        """
        all_folders: list[dict] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        pages_fetched = 0
        partial_pages: list[list[dict]] = []

        while True:
            params: dict = {"page_size": _MAX_PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor

            data = self._request("/folders", params=params, partial_pages=partial_pages)
            batch = _collection(data, "folders", partial_pages)
            partial_pages.append(batch)
            all_folders.extend(batch)
            pages_fetched += 1

            has_more = data.get("hasMore", False)
            if not has_more:
                break

            next_cursor = data.get("cursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                raise GranolaIncompleteRead(
                    reason="Folders API returned hasMore=true but cursor is absent or empty.",
                    partial_pages=partial_pages,
                )
            if next_cursor in seen_cursors:
                raise GranolaIncompleteRead(
                    reason="Folders API repeated a cursor — pagination loop detected.",
                    partial_pages=partial_pages,
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor

            if pages_fetched >= MAX_PAGES:
                raise GranolaIncompleteRead(
                    reason=f"Folders pagination exceeded MAX_PAGES={MAX_PAGES} without completing.",
                    partial_pages=partial_pages,
                )

        return all_folders

    def list_notes(
        self,
        *,
        folder_id: str | None = None,
        limit: int | None = None,
        created_after: str | None = None,
        updated_after: str | None = None,
        created_before: str | None = None,
    ) -> list[dict]:
        """Fetch notes from the specified personal folder.

        Args:
            folder_id:      Personal folder ID (required for MVP; use list_folders()).
            limit:          Maximum total notes to return, 1–MAX_SELECTED.
                            The tool layer maintains `remaining = limit - fetched`
                            and uses page_size = min(_MAX_PAGE_SIZE, remaining) per request.
                            If None, defaults to MAX_SELECTED (hard cap on total notes returned).
            created_after:  ISO-8601 timestamp; return only notes created after this time.
            updated_after:  ISO-8601 timestamp; return only notes updated after this time.
            created_before: ISO-8601 timestamp; return only notes created before this time.

        Raises:
            GranolaConfigError:    if limit is out of range or folder_id is missing.
            GranolaAuthError:      on HTTP 401.
            GranolaPermissionError: on HTTP 403.
            GranolaIncompleteRead: if retries exhaust before all pages are fetched;
                                   carries partial_pages and a safe failure reason.

        Returns raw note dicts as returned by the API; adapter maps them to records.
        """
        if folder_id is None:
            raise GranolaConfigError(
                "folder_id is required for list_notes() in MVP scope.\n"
                "Use list_folders() to discover available folder IDs."
            )
        if limit is not None and not (1 <= limit <= MAX_SELECTED):
            raise GranolaConfigError(
                f"limit must be between 1 and {MAX_SELECTED}; got {limit!r}."
            )

        effective_limit = limit if limit is not None else MAX_SELECTED
        all_notes: list[dict] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        pages_fetched = 0
        partial_pages: list[list[dict]] = []

        while True:
            remaining = effective_limit - len(all_notes)
            page_size = min(_MAX_PAGE_SIZE, remaining)

            params: dict = {"folder_id": folder_id, "page_size": page_size}
            if cursor:
                params["cursor"] = cursor
            if created_after:
                params["created_after"] = created_after
            if updated_after:
                params["updated_after"] = updated_after
            if created_before:
                params["created_before"] = created_before

            data = self._request("/notes", params=params, partial_pages=partial_pages)
            batch = _collection(data, "notes", partial_pages)
            partial_pages.append(batch)
            all_notes.extend(batch)
            pages_fetched += 1

            has_more = data.get("hasMore", False)
            if not has_more:
                break

            next_cursor = data.get("cursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                raise GranolaIncompleteRead(
                    reason="API returned hasMore=true but cursor is absent or empty.",
                    partial_pages=partial_pages,
                )
            if next_cursor in seen_cursors:
                raise GranolaIncompleteRead(
                    reason="API repeated a cursor — pagination loop detected.",
                    partial_pages=partial_pages,
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor

            if len(all_notes) >= effective_limit:
                break
            if pages_fetched >= MAX_PAGES:
                raise GranolaIncompleteRead(
                    reason=f"Pagination exceeded MAX_PAGES={MAX_PAGES} without completing.",
                    partial_pages=partial_pages,
                )

        return all_notes[:effective_limit]

    def get_note(self, note_id: str) -> dict:
        """Fetch a single note by ID.

        Raises:
            GranolaAuthError:       on HTTP 401.
            GranolaPermissionError: on HTTP 403.
            ValueError:             on HTTP 404 (deleted, inaccessible, or still processing).
        """
        from urllib.parse import quote
        if not isinstance(note_id, str) or not note_id:
            raise GranolaConfigError("A nonempty note ID is required.")
        result = self._request(f"/notes/{quote(note_id, safe='')}")
        if not isinstance(result, dict) or result.get("id") != note_id:
            raise GranolaIncompleteRead("Granola returned mismatched or malformed note detail.", [])
        # The vendor's detail response can contain private notes/people/media.
        # Drop them at the client boundary, before collection or model material.
        allowed = {"id", "title", "created_at", "updated_at", "deleted_at", "web_url",
                   "summary_text", "summary_markdown", "space_id", "folder_id"}
        clean = {key: result[key] for key in allowed if key in result}
        if isinstance(result.get("folder_membership"), list):
            clean["folder_membership"] = [
                {key: folder[key] for key in ("id", "name", "space_id", "parent_folder_id") if key in folder}
                for folder in result["folder_membership"] if isinstance(folder, dict)]
        if isinstance(result.get("summary"), dict):
            clean["summary"] = {key: result["summary"][key] for key in ("plain_text", "markdown") if key in result["summary"]}
        if isinstance(result.get("calendar_event"), dict):
            event = result["calendar_event"]
            clean["calendar_event"] = {key: event[key] for key in (
                "scheduled_start", "scheduled_end", "scheduled_start_time", "scheduled_end_time") if key in event}
        return clean

    def hydrate_notes(self, notes: list[dict]) -> list[dict]:
        """Fetch raw detail objects for lightweight list-note results."""
        details: list[dict] = []
        for note in notes:
            note_id = str(note.get("id") or "") if isinstance(note, dict) else ""
            if not note_id:
                raise GranolaConfigError("Granola list response included a note without an id.")
            try:
                details.append(self.get_note(note_id))
            except (GranolaIncompleteRead, ValueError) as exc:
                raise GranolaIncompleteRead(
                    reason=f"Could not fetch detail for note {note_id}: {str(exc)}",
                    partial_pages=[details],
                ) from exc
        return details

    def write_source_yaml(
        self,
        source_dir,
        folder_id: str,
        profile: str,
        *,
        limit: int | None = None,
        complete: bool = True,
        note_id: str | None = None,
        export_id: str | None = None,
        include_children: bool = False,
    ) -> None:
        """Write source_dir/source.yaml with scope, account, retention, and validated_with.

        Args:
            source_dir:  Directory under ~/.co/rem/docs/granola (or --output).
            folder_id:   The personal folder ID selected for import.
            profile:     Non-secret user label used as the record account component.
            limit:       Effective note limit used; None means MAX_SELECTED was used.
                         For precise imports (note_id given), this is always 1.
            complete:    False when the read was interrupted (GranolaIncompleteRead);
                         recorded in the file so downstream tools know the data is partial.
            note_id:     When set, records this note ID in the scope for traceability.
                         Precise imports always set limit=1 alongside note_id.

        Token and API key never appear in the written file.
        Raises ValueError if profile is invalid (via validate_profile).
        """
        import importlib.metadata
        import datetime
        import yaml

        validate_profile(profile)
        validate_source_identity(source_dir, folder_id, profile)

        from pathlib import Path as _Path
        source_dir = _Path(source_dir)
        source_dir.mkdir(parents=True, exist_ok=True)
        version = importlib.metadata.version("connectonion")
        scope: dict = {
            "folder_id": folder_id,
            "limit": limit if limit is not None else MAX_SELECTED,
        }
        if note_id is not None:
            scope["note_id"] = note_id
        if include_children:
            scope["include_children"] = True
        doc = {
            "driver": "granola",
            "account": profile,
            "scope": scope,
            "retention": "90d",
            "media_policy": "metadata_only",
            "complete": complete,
            "validated_with": {
                "connectonion_version": version,
                "command": _import_command(folder_id, profile, limit, note_id, source_dir, export_id, include_children),
                "path": str(source_dir / "source.yaml"),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        }
        target = source_dir / "source.yaml"
        if target.is_file():
            previous = yaml.safe_load(target.read_text(encoding="utf-8"))
            if isinstance(previous, dict) and previous.get("credential_binding"):
                doc["credential_binding"] = previous["credential_binding"]
        from ..rem.files import atomic_write
        atomic_write(target, yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))


def _import_command(folder_id, profile, limit, note_id, source_dir, export_id, include_children=False):
    import shlex
    from ..environment import selected_command
    args = ["co", "granola", "import", folder_id, "--profile", profile]
    if note_id is not None:
        args.extend(["--note-id", note_id])
    elif limit is not None:
        args.extend(["--limit", str(limit)])
    if include_children:
        args.append("--include-children")
    args.extend(["--output", str(source_dir)])
    if export_id is not None:
        args.extend(["--export", export_id])
    return selected_command(shlex.join(args))
