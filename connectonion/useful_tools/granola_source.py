"""
Purpose: `co granola changes` and `co granola show` -- the REM CLI JSON source contract (#3249) for Granola.
LLM-Note:
  Dependencies: imports from [datetime, urllib.parse, rem/files, useful_tools/granola] | imported by [cli/commands/granola_commands.py] | tested by [tests/unit/test_granola_source.py]
  Data flow: REM approval in .state/subscriptions.json -> approved personal folder (and optional note) -> GranolaClient list/detail GETs -> {id, version, time, title} rows or one note's allowed fields
  State/Effects: reads the approval file only; no local writes and no Granola writes. Approval is checked before the API key is read or any request is made
  Errors: GranolaSourceError(code, message); codes are stable for callers (approval_required, invalid_scope, invalid_since, not_configured, auth_failed, permission_denied, not_found, out_of_scope, rate_limited, incomplete, too_many_changes, invalid_response, unavailable)
"""

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from ..rem.files import KEY_SHAPES, RemError, read_json, state_path
from .granola import (
    MAX_SELECTED, GranolaAuthError, GranolaConfigError, GranolaIncompleteRead, GranolaPermissionError,
)

SELECTION_KEYS = {"folder_id", "include_children", "note_id", "profile", "limit"}
WITHHELD = "[withheld: possible credential]"


class GranolaSourceError(ValueError):
    """An error whose code and message are safe to print in JSON diagnostics."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Approval and personal-folder scope
# ---------------------------------------------------------------------------

def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


def _id(value) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 256 and value.isascii() and value.isprintable()
            and not any(ch.isspace() or ch in "/\\" for ch in value) and not KEY_SHAPES.search(value))


def approved_scope(root: Path) -> dict:
    """The approved selection, or an error. Reads no credential and makes no request."""
    try:
        saved = read_json(state_path(root, "subscriptions.json"), {})
    except (RemError, OSError, ValueError, TypeError):
        raise GranolaSourceError("invalid_scope", "Cannot read REM source approval.") from None
    source = _object(_object(saved).get("granola"))
    if (source.get("enabled") is not True or source.get("consented") is not True
            or source.get("unsubscribed") is True):
        raise GranolaSourceError("approval_required", "Turn on and approve Granola in co rem sources first.")
    selection = _object(_object(source.get("remote")).get("selection"))
    include = selection.get("include_children", False)
    note = selection.get("note_id")
    if (set(selection) - SELECTION_KEYS or not _id(selection.get("folder_id"))
            or type(include) is not bool or (note is not None and not _id(note))):
        raise GranolaSourceError("invalid_scope", "Granola approval needs one personal folder ID, "
                                 "optionally one note ID.")
    return {"folder_id": selection["folder_id"], "include_children": include, "note_id": note}


def allowed_folders(folder_id: str, folders: list, *, include_children: bool) -> set[str]:
    """The selected personal folder, plus its personal descendants when explicitly approved."""
    if (not isinstance(folders, list) or any(not isinstance(row, dict) or not _id(row.get("id")) for row in folders)
            or len({row["id"] for row in folders}) != len(folders)):
        raise GranolaSourceError("invalid_response", "Granola returned malformed folder metadata. Retry later.")
    by_id = {row["id"]: row for row in folders}
    selected = by_id.get(folder_id)
    if selected is None:
        raise GranolaSourceError("not_found", "The Granola folder is missing or inaccessible with this key.")
    if "space_id" not in selected or selected["space_id"] is not None:
        raise GranolaSourceError("out_of_scope", "The Granola folder is in a shared space, not a personal folder.")
    children = [row for row in folders if row.get("parent_folder_id") == folder_id]
    if children and not include_children:
        # Granola returns child-folder notes in a parent folder read; never widen silently.
        raise GranolaSourceError("out_of_scope", "The Granola folder has child folders, which a folder read "
                                 "includes. Approve a child folder directly, or approve include_children.")
    allowed, queue = {folder_id}, [folder_id] if include_children else []
    while queue:
        parent = queue.pop(0)
        for row in folders:
            if row.get("parent_folder_id") != parent:
                continue
            if row["id"] in allowed or len(allowed) >= MAX_SELECTED:
                raise GranolaSourceError("invalid_response", "Granola folder hierarchy is cyclic or too large.")
            if "space_id" not in row or row["space_id"] is not None:
                raise GranolaSourceError("out_of_scope", "A child of the approved folder is not personal.")
            allowed.add(row["id"])
            queue.append(row["id"])
    return allowed


# ---------------------------------------------------------------------------
# Field normalisation
# ---------------------------------------------------------------------------

def parse_since(value) -> datetime:
    try:
        if not isinstance(value, str) or "T" not in value:
            raise ValueError
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise GranolaSourceError("invalid_since", "Use an ISO 8601 timestamp with a timezone for --since.") from None


def _time(value) -> str:
    """Granola's updated_at as UTC ISO 8601 with Z, or an invalid_response error."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or "T" not in str(value):
            raise ValueError
    except (ValueError, OverflowError):
        raise GranolaSourceError("invalid_response", "Granola did not return a valid update time.") from None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe(value) -> str:
    text = value if isinstance(value, str) else ""
    return WITHHELD if KEY_SHAPES.search(text) else text


def _summary(note: dict) -> dict:
    title = note.get("title")
    if title is not None and not isinstance(title, str):
        raise GranolaSourceError("invalid_response", "Granola did not return a valid note title.")
    time = _time(note.get("updated_at"))
    # updated_at is the only revision marker the public API documents.
    return {"id": note["id"], "version": time, "time": time, "title": _safe(title or "")}


def _link(note: dict) -> str:
    value = note.get("web_url")
    if isinstance(value, str) and not any(ord(ch) < 33 for ch in value) and not KEY_SHAPES.search(value):
        try:
            parsed = urlsplit(value)
        except ValueError:
            parsed = None
        host = (parsed.hostname or "") if parsed else ""
        if (parsed and parsed.scheme == "https" and (host == "granola.ai" or host.endswith(".granola.ai"))
                and parsed.username is None and parsed.password is None and parsed.port in (None, 443)):
            return value
    raise GranolaSourceError("invalid_response", "Granola did not return a usable original note link.")


def _text(note: dict) -> str:
    summary = _object(note.get("summary"))
    for value in (note.get("summary_markdown"), summary.get("markdown"),
                  note.get("summary_text"), summary.get("plain_text")):
        if isinstance(value, str) and value.strip():
            return _safe(value)
    return ""


# ---------------------------------------------------------------------------
# The two commands
# ---------------------------------------------------------------------------

def _provider_error(error: Exception) -> GranolaSourceError:
    if isinstance(error, GranolaAuthError):
        return GranolaSourceError("auth_failed", "Granola rejected the API key. Check GRANOLA_API_KEY.")
    if isinstance(error, GranolaPermissionError):
        return GranolaSourceError("permission_denied", "Granola denied access to the approved scope.")
    if isinstance(error, GranolaIncompleteRead):
        if "429" in error.reason:
            return GranolaSourceError("rate_limited", "Granola limited requests. Retry later.")
        return GranolaSourceError("incomplete", "The Granola read did not complete. Retry later.")
    if isinstance(error, GranolaConfigError):
        return GranolaSourceError("unavailable", "Granola returned an unexpected response. Retry later.")
    return GranolaSourceError("invalid_response", "Granola returned an invalid response. Retry later.")


def _client():
    from .granola import GranolaClient
    try:
        return GranolaClient()
    except GranolaConfigError:
        raise GranolaSourceError("not_configured", "Granola has no usable API key. "
                                 "Save it with co env set GRANOLA_API_KEY <key> --secret.") from None


def note_changes(root: Path, since: str) -> list[dict]:
    """Approved notes updated after `since`: id, version, time and title. No summaries are fetched."""
    cutoff = parse_since(since)
    scope = approved_scope(root)
    client = _client()
    try:
        allowed_folders(scope["folder_id"], client.list_folders(), include_children=scope["include_children"])
        rows = client.list_notes(folder_id=scope["folder_id"], limit=MAX_SELECTED,
                                 updated_after=cutoff.isoformat().replace("+00:00", "Z"))
    except GranolaSourceError:
        raise
    except (ValueError, GranolaIncompleteRead) as error:
        raise _provider_error(error) from None
    if len(rows) >= MAX_SELECTED:
        raise GranolaSourceError("too_many_changes", f"{MAX_SELECTED} or more notes changed. Use a later --since.")
    changes = [_summary(row) for row in rows
               if not row.get("deleted_at") and scope["note_id"] in (None, row["id"])]
    changes = [row for row in changes if parse_since(row["time"]) > cutoff]
    return sorted(changes, key=lambda row: (row["time"], row["id"]))


def show_note(root: Path, note_id: str) -> dict:
    """One approved note: generated summary, title, times and the original Granola link."""
    scope = approved_scope(root)
    if not _id(note_id) or scope["note_id"] not in (None, note_id):
        raise GranolaSourceError("out_of_scope", "This note ID is outside the approved Granola selection.")
    client = _client()
    try:
        allowed = allowed_folders(scope["folder_id"], client.list_folders(),
                                  include_children=scope["include_children"])
        note = client.get_note(note_id)
    except GranolaSourceError:
        raise
    except (GranolaAuthError, GranolaPermissionError, GranolaIncompleteRead, GranolaConfigError) as error:
        raise _provider_error(error) from None
    except ValueError:
        raise GranolaSourceError("not_found", "The Granola note is missing, deleted or still processing.") from None
    if note.get("deleted_at"):
        raise GranolaSourceError("not_found", "The Granola note was deleted.")
    folders = [row for row in note.get("folder_membership") or [] if isinstance(row, dict)]
    if not any(row.get("id") in allowed and row.get("space_id") is None for row in folders):
        raise GranolaSourceError("out_of_scope", "This note is not in the approved personal folder.")
    event = _object(note.get("calendar_event"))
    meeting = event.get("scheduled_start_time") or event.get("scheduled_start")
    return {**_summary(note), "text": _text(note), "author": None, "link": _link(note),
            "meeting_time": _time(meeting) if meeting else None}
