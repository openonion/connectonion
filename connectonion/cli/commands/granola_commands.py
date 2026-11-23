"""
Purpose: `co granola` -- verify the key, list personal folders and notes, and the REM JSON source commands.
LLM-Note:
  Dependencies: imports from [json, shlex, sys, rich, useful_tools/granola, useful_tools/granola_source] | imported by [cli/main.py] | tested by [tests/unit/test_granola_commands.py, tests/unit/test_granola_source.py]
  Data flow: CLI flags -> _granola() factory -> GranolaClient.verify()/list_folders()/list_notes() -> terminal or JSON; changes/show -> granola_source -> JSON on stdout
  State/Effects: read-only for Granola; writes no local files
  Errors: Granola errors -> stderr (or JSON) + exit 1; never prints the API key
"""

import json
import shlex
import sys
from pathlib import Path

from rich.markup import escape
from ...environment import selected_command
from .. import style
from .command_tips import mark_next_step_named, tips_enabled


def _print(text: str) -> None:
    if text.startswith("Next: "):
        _next(text.removeprefix("Next: "))
    else:
        style.console().print(escape(text), emoji=False)


def _next(command: str, *, error: bool = False) -> None:
    mark_next_step_named()
    if tips_enabled():
        style.console(stderr=error).print(style.next_line(selected_command(command)), emoji=False)


def _error(text: str, **options) -> None:
    if text.startswith("Next: "):
        # Recovery commands already carry the selected account prefix.
        mark_next_step_named()
        if tips_enabled():
            style.console(stderr=True).print(style.next_line(text[6:]), emoji=False)
    else:
        style.console(stderr=True).print(style.error(text), emoji=False)


def _granola():
    """Factory function patchable in unit tests."""
    from ...useful_tools.granola import GranolaClient
    return GranolaClient()


def _failure_details(exc: Exception) -> tuple[str, str]:
    from ...useful_tools.granola import (
        GranolaConfigError, GranolaAuthError, GranolaPermissionError, GranolaIncompleteRead,
    )
    from ...useful_tools.granola_source import GranolaSourceError
    if isinstance(exc, GranolaSourceError):
        if exc.code == "not_found":
            return "folder_not_found", "co granola folders"
        if exc.code == "out_of_scope":
            return "personal_folder_required", "co granola folders"
        return "invalid_response", "co granola --help"
    if isinstance(exc, GranolaIncompleteRead):
        return "transient_error", "co granola --help"
    if isinstance(exc, GranolaAuthError):
        return "reauth_required", "co granola verify --help"
    if isinstance(exc, GranolaPermissionError):
        return "permission_denied", "co granola folders"
    if isinstance(exc, GranolaConfigError):
        return "invalid_configuration", "co granola --help"
    return "request_failed", "co granola --help"


def _handle_error(exc: Exception, as_json: bool, *, scope: dict | None = None) -> None:
    msg = str(exc).strip()
    code, recovery = _failure_details(exc)
    recovery = selected_command(recovery)
    mark_next_step_named()
    result = {"error": msg, "exit_code": 1, "source": "granola", "scope": scope or {},
              "error_code": code, "recovery_action": recovery}
    if as_json:
        print(json.dumps(result))
    else:
        _error(f"Granola command failed (scope: {json.dumps(result['scope'])}).", markup=False)
        _error(msg, style="red", markup=False)
        _error(f"Next: {recovery}", markup=False)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Note stub helpers (for handle_granola_notes).
# ---------------------------------------------------------------------------

def _truncate(s: str, max_len: int) -> str:
    """Truncate to max_len chars with ASCII ... suffix if needed."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _fmt_date(iso: str) -> str:
    """Format ISO 8601 timestamp to YYYY-MM-DD HH:MM UTC."""
    if not iso:
        return ""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso[:16] + " UTC" if len(iso) >= 16 else iso


def _note_stub_json(stub: dict) -> dict:
    """Return the safe stub fields for JSON output (full title, ISO 8601 timestamps)."""
    return {
        "id": str(stub.get("id") or ""),
        "title": str(stub.get("title") or ""),
        "created_at": str(stub.get("created_at") or ""),
        "updated_at": str(stub.get("updated_at") or ""),
    }


def _print_notes_table(stubs: list[dict]) -> None:
    """Print a human-readable table: full ID, title (max 28 chars), formatted date."""
    for stub in stubs:
        note_id = str(stub.get("id") or "")
        title = " ".join(str(stub.get("title") or "(untitled)").split())
        created = _fmt_date(str(stub.get("created_at") or ""))
        _print(f"Note ID: {note_id}  Title: {title}  Created: {created}")


# ---------------------------------------------------------------------------
# Public command handlers
# ---------------------------------------------------------------------------

# Added to every successful verify response (JSON + terminal) per Canvas spec:
# "success JSON must state verified_read: true AND that this only validates a
# minimal read request, not all folders/spaces/notes."
_VERIFY_SCOPE_NOTE = (
    "This verifies only a minimal /v1/notes?page_size=1 read. "
    "It does not confirm access to all folders, spaces, or notes."
)


def handle_granola_verify(*, as_json: bool = False) -> None:
    """Verify the Granola API key with a minimal read.

    JSON output: {"verified_read": true, "note": "<first note title or sentinel>",
                  "verify_scope": "<scope caveat>"}.
    Terminal output also prints the scope caveat so the user knows the limits of
    this check.  The API key is never included in any output.
    """
    from ...useful_tools.granola import (
        GranolaConfigError, GranolaAuthError, GranolaPermissionError, GranolaIncompleteRead,
    )
    try:
        result = _granola().verify()
    except (GranolaConfigError, GranolaAuthError, GranolaPermissionError, GranolaIncompleteRead, ValueError) as exc:
        _handle_error(exc, as_json)
        return
    if as_json:
        result["verify_scope"] = _VERIFY_SCOPE_NOTE
        print(json.dumps(result))
        return
    title = " ".join(str(result.get("note") or "(no notes yet)").split())
    _print(f"Verified: {title}")
    _print(f"Note: {_VERIFY_SCOPE_NOTE}")
    _print("Next: co granola folders")


def handle_granola_folders(*, as_json: bool = False) -> None:
    """List personal Granola folders (space_id: null) accessible with this API key.

    The Granola API returns all accessible folders; this command filters to personal
    folders only (space_id is null), matching the single-personal-folder approval scope.

    JSON output: {"folders": [{"id": ..., "name": ..., "space_id": null}, ...]}.
    Empty result: {"folders": []} valid when no personal folders exist.
    Errors: exit 1; JSON includes error, exit_code, source, scope, error_code, recovery_action.
    """
    from ...useful_tools.granola import (
        GranolaConfigError, GranolaAuthError, GranolaPermissionError, GranolaIncompleteRead,
    )
    try:
        all_folders = _granola().list_folders()
    except (GranolaConfigError, GranolaAuthError, GranolaPermissionError, GranolaIncompleteRead, ValueError) as exc:
        _handle_error(exc, as_json)
        return
    # Only expose personal folders (not in a shared space).
    folders = [f for f in all_folders if f.get("space_id") is None]
    if as_json:
        print(json.dumps({"folders": folders}))
        return
    if not folders:
        _print("No personal folders found.")
        _print("Next: co granola verify")
        return
    for folder in folders:
        name = " ".join(str(folder.get("name") or folder.get("title") or "(untitled)").split())
        _print(f"Folder ID: {folder.get('id', '')}  Name: {name}")
    _next(shlex.join(["co", "granola", "notes", str(folders[0]["id"])]))


def handle_granola_notes(
    folder_id: str,
    *,
    limit: int = 100,
    as_json: bool = False,
) -> None:
    """List safe note metadata (id, title, created_at, updated_at) from a personal folder.

    Step 1: validate personal folder (space_id=None) via list_folders().
    Step 2: list_notes(folder_id, limit) to get lightweight stubs.
    Step 3: filter out deleted notes (deleted_at not null/empty).
    Step 4: display as table or JSON.

    On GranolaIncompleteRead from list_folders(): standard error JSON (no notes array), exit 1.
    On GranolaIncompleteRead from list_notes(): partial notes JSON with complete:false, exit 1,
      no files written.

    JSON success output: {"notes": [...], "complete": true}.
    JSON partial output: {"notes": [...], "complete": false, "error_code": "transient_error",
      "recovery_action": "..."}.
    """
    from ...useful_tools.granola import (
        GranolaConfigError, GranolaAuthError, GranolaPermissionError, GranolaIncompleteRead,
    )

    scope: dict = {"folder_id": folder_id, "limit": limit}

    try:
        client = _granola()
        # list_folders() GranolaIncompleteRead -> caught by outer except -> standard error JSON.
        from ...useful_tools.granola_source import allowed_folders
        allowed_folders(folder_id, client.list_folders(), include_children=True)

        complete = True
        failure_reason: str = ""
        try:
            stubs = client.list_notes(folder_id=folder_id, limit=limit)
        except GranolaIncompleteRead as exc:
            # Partial stubs: flatten all partial pages received before the failure.
            stubs = [note for page in exc.partial_pages for note in page]
            complete = False
            failure_reason = exc.reason

    except (GranolaConfigError, GranolaAuthError, GranolaPermissionError,
            GranolaIncompleteRead, ValueError) as exc:
        _handle_error(exc, as_json, scope=scope)
        return

    # Filter out deleted stubs (deleted_at not null/empty).
    active = [s for s in stubs if not s.get("deleted_at")]

    if not complete:
        recovery = selected_command(shlex.join(["co", "granola", "notes", folder_id, "--limit", str(limit)]))
        mark_next_step_named()
        if as_json:
            print(json.dumps({
                "notes": [_note_stub_json(s) for s in active],
                "complete": False,
                "error_code": "transient_error",
                "recovery_action": recovery,
            }))
        else:
            _print_notes_table(active)
            _error(
                f"Granola notes (scope: {json.dumps(scope)}): partial result: {failure_reason}",
                markup=False,
            )
            _error(f"Next: {recovery}", markup=False)
        sys.exit(1)

    if as_json:
        print(json.dumps({"notes": [_note_stub_json(s) for s in active], "complete": True}))
        return

    if not active:
        _print("No notes found in this folder.")
        _next("co granola folders")
        return

    _print_notes_table(active)
    _next("co granola changes --help")


# ---------------------------------------------------------------------------
# REM CLI JSON source contract (#3249): changes and show
# ---------------------------------------------------------------------------

def handle_granola_source(command: str, value: str, root: Path | None, output_json: bool) -> None:
    """Print `changes` rows or one `show` note as JSON on stdout; errors exit 1 on stderr."""
    from ...rem.schedule import default_root
    from ...useful_tools.granola_source import GranolaSourceError, note_changes, show_note

    read = note_changes if command == "changes" else show_note
    try:
        output = read((root or default_root()).expanduser(), value)
    except GranolaSourceError as error:
        if output_json:
            print(json.dumps({"error": {"code": error.code, "message": str(error)}}), file=sys.stderr)
        else:
            _error(str(error))
            _error("Next: " + selected_command("co granola " + command + " --help"))
        sys.exit(1)
    print(json.dumps(output, ensure_ascii=False, indent=None if output_json else 2))
    if not output_json:
        _next("co granola show --help" if command == "changes" else "co granola changes --help", error=True)
