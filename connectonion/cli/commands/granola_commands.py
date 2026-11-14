"""
Purpose: `co granola` — verify key, list folders, list notes, import meeting notes as co rem records.
LLM-Note:
  Dependencies: imports from [sys, json, pathlib, rich, useful_tools/granola, useful_tools/adapter] | imported by [cli/main.py] | tested by [tests/unit/test_granola_commands.py]
  Data flow: CLI flags -> _granola() factory -> GranolaClient.verify()/list_folders()/list_notes()/get_note() -> raw dicts -> granola_notes_to_records() -> place_records() / write_source_yaml()
  State/Effects: import writes source.yaml and daily JSONL under the output dir; Granola itself is always read-only; all auth/key validation in tool layer
  Errors: GranolaConfigError/GranolaAuthError/GranolaPermissionError -> stderr + exit 1; GranolaIncompleteRead -> partial records retained, exit 1 with complete:false; never exposes API key
"""

import json
import shlex
import sys
from pathlib import Path

from rich.markup import escape
from ...environment import selected_command
from .. import style
from ...rem.files import RemError
from .command_tips import mark_next_step_named, tips_enabled


from ...useful_tools.granola_collection import (
    _FolderNotFound, _NotPersonalFolder, _NoteNotInSelectedFolder, _FolderHasChildren,
    _validate_personal_folder, _place_records, _stored_versions,
)

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


_DEFAULT_PROFILE = "default"


# ---------------------------------------------------------------------------
# Private validation exceptions used only within this module.
# ---------------------------------------------------------------------------









def _granola():
    """Factory function patchable in unit tests."""
    from ...useful_tools.granola import GranolaClient
    return GranolaClient()


def _failure_details(exc: Exception) -> tuple[str, str]:
    from ...useful_tools.granola import (
        GranolaConfigError, GranolaAuthError, GranolaPermissionError, GranolaIncompleteRead,
    )
    if isinstance(exc, (OSError, RemError)):
        return "storage_error", "co granola import --help"
    if isinstance(exc, _NoteNotInSelectedFolder):
        return "note_not_in_selected_folder", "co granola notes --help"
    if isinstance(exc, _FolderHasChildren):
        return "folder_has_children", "co granola folders --help"
    if isinstance(exc, _NotPersonalFolder):
        return "personal_folder_required", "co granola folders"
    if isinstance(exc, _FolderNotFound):
        return "folder_not_found", "co granola folders"
    if isinstance(exc, GranolaIncompleteRead):
        return "transient_error", "co granola --help"
    if isinstance(exc, GranolaAuthError):
        return "reauth_required", "co granola verify --help"
    if isinstance(exc, GranolaPermissionError):
        return "permission_denied", "co granola folders"
    if isinstance(exc, GranolaConfigError):
        return "invalid_configuration", "co granola --help"
    return "import_failed", "co granola import --help"


def _handle_error(exc: Exception, as_json: bool, *, scope: dict | None = None) -> None:
    msg = ("Could not read or write local Granola source files. "
           "Check --output and directory permissions.") if isinstance(exc, OSError) else str(exc).strip()
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
    folders only (space_id is null), matching the single-personal-folder import scope.

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
        _validate_personal_folder(folder_id, client.list_folders(), include_children=True)

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
            GranolaIncompleteRead, _FolderNotFound, _NotPersonalFolder, ValueError) as exc:
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
    _next(shlex.join(["co", "granola", "import", folder_id, "--note-id", str(active[0]["id"])]))


def handle_granola_import(
    folder_id: str,
    *,
    profile: str = _DEFAULT_PROFILE,
    limit: int | None = None,
    output_dir: Path | None = None,
    as_json: bool = False,
    export_id: str | None = None,
    note_id: str | None = None,
    include_children: bool = False,
) -> None:
    """Validate personal folder, list notes, map to records, write source.yaml and daily records.

    Full workflow: list_folders -> validate personal folder (space_id=None) ->
    list_notes(folder_id, limit) -> granola_notes_to_records ->
    write_source_yaml -> append_daily_jsonl (ongoing) or write_export (one-off with --export).
    Folder validation runs before any notes fetch or file writes; rejection has no side effects.

    When --note-id is given:
      - --limit is rejected with exit 1 before any network call (mutually exclusive).
      - A scoped lookup (list_notes up to MAX_SELECTED) is performed.
      - Deleted stubs (deleted_at not null) are excluded from the scoped list.
      - If note_id is not in the active scoped list, exits 1 with note_not_in_selected_folder.
      - Otherwise calls get_note(note_id) for full detail, then maps one record.
      - source.yaml records note_id and limit: 1 for traceability.

    On GranolaIncompleteRead: completed note details are mapped and retained;
    when valid records exist source.yaml is written with complete:false;
    the result carries complete:false and exits 1.  When --export is given and the read
    is incomplete, the export manifest also records complete:false and the failure reason.

    JSON output: {"written": source_yaml_path, "placement": "daily"|"export", "jsonl": path,
    "folder_id": ..., "profile": ..., "notes": collected, "mapped": valid_records,
    "appended": newly_added, "complete": true|false, "rejected": {"granola:<id>": reason}}.
    """
    from ...useful_tools.granola import (
        GranolaConfigError, GranolaAuthError, GranolaPermissionError, GranolaIncompleteRead,
        MAX_SELECTED, validate_source_identity, validate_profile,
    )
    from ...useful_tools.adapter import (
        granola_notes_to_records, export_target,
    )

    if output_dir is None:
        output_dir = Path.home() / ".co" / "rem" / "docs" / "granola"

    scope: dict = {"folder_id": folder_id, "profile": profile, "limit": limit}
    if note_id is not None:
        scope["note_id"] = note_id
    if include_children:
        scope["include_children"] = True

    # --note-id and --limit are mutually exclusive; reject before any network call.
    if note_id is not None and limit is not None:
        msg = "--note-id and --limit cannot be used together."
        recovery = selected_command("co granola import --help")
        mark_next_step_named()
        result = {
            "error": msg, "exit_code": 1, "source": "granola",
            "scope": scope, "error_code": "invalid_configuration",
            "recovery_action": recovery,
        }
        if as_json:
            print(json.dumps(result))
        else:
            _error(msg, markup=False)
            _error(f"Next: {recovery}", markup=False)
        sys.exit(1)

    try:
        validate_profile(profile)
        if export_id is not None:
            export_target(output_dir, export_id)
        # Reject another folder or profile before reading remote data or writing records.
        validate_source_identity(output_dir, folder_id, profile)
        _stored_versions(output_dir, folder_id, profile, **({"include_children": True} if include_children else {}))
        client = _granola()
        from ...useful_tools.granola_collection import collect_summaries
        adapter_result, notes, complete, failure_reason = collect_summaries(
            client, folder_id, profile, limit=limit, note_id=note_id, include_children=include_children)

        # Write source metadata only alongside valid committed records.
        # complete=False is recorded so callers know the read was partial.
        # Compute the limit that source.yaml and the export manifest must both record.
        # write_source_yaml() maps None → MAX_SELECTED internally, so we mirror that here
        # so the manifest scope is consistent with source.yaml for every import path.
        effective_limit = 1 if note_id is not None else (limit if limit is not None else MAX_SELECTED)
        scope["limit"] = effective_limit
        source_yaml, jsonl_path, appended = None, None, 0
        if adapter_result.records:
            from ...rem.files import maintenance_lock
            with maintenance_lock(output_dir):
                validate_source_identity(output_dir, folder_id, profile)
                _stored_versions(output_dir, folder_id, profile, **({"include_children": True} if include_children else {}))
                if export_id is not None:
                    export_target(output_dir, export_id)
                export_scope = scope if complete else {**scope, "complete": False, "failure_reason": failure_reason}
                jsonl_path, appended = _place_records(adapter_result.records, output_dir, export_id, export_scope)
                # Never replace the prior declaration before records are committed.
                client.write_source_yaml(output_dir, folder_id, profile,
                    limit=effective_limit, complete=complete, note_id=note_id,
                    **({"include_children": True} if include_children else {}),
                    **({"export_id": export_id} if export_id is not None else {}))
                source_yaml = str(output_dir / "source.yaml")

    except (GranolaConfigError, GranolaAuthError, GranolaPermissionError,
            GranolaIncompleteRead, _NoteNotInSelectedFolder, ValueError, OSError, RemError) as exc:
        _handle_error(exc, as_json, scope=scope)
        return

    rejected = adapter_result.errors
    mapped = len(adapter_result.records)
    collected = len(notes)

    if rejected or not complete:
        _report_partial(
            rejected, as_json, scope, source_yaml, jsonl_path,
            collected, mapped, appended, complete, failure_reason, export_id,
        )
        return

    if as_json:
        print(json.dumps({
            "written": source_yaml,
            "placement": "export" if export_id else "daily",
            "jsonl": str(jsonl_path) if jsonl_path else None,
            "folder_id": folder_id,
            "profile": profile,
            "notes": collected,
            "mapped": mapped,
            "appended": appended,
            "complete": True,
            "rejected": rejected,
        }))
    else:
        if source_yaml:
            _print(f"Wrote {source_yaml}")
        if jsonl_path:
            _print(f"Saved to: {jsonl_path}")
        _print(f"Folder: {folder_id}  Profile: {profile}  "
              f"Notes collected: {collected}  Records mapped: {mapped}  Records appended: {appended}")
        _print("Local source records only; REM processing and Reader updates are not automatic.")
        _next(_repeat_command(folder_id, profile, limit, output_dir, note_id, include_children))




def _report_partial(
    rejected: dict,
    as_json: bool,
    scope: dict,
    source_yaml: str | None,
    jsonl_path: Path | None,
    collected: int,
    mapped: int,
    appended: int,
    complete: bool,
    failure_reason: str,
    export_id: str | None,
) -> None:
    if not complete:
        message = (
            f"Granola read was incomplete: {failure_reason} "
            f"Valid records retained: {mapped}." if mapped else
            f"Granola read was incomplete: {failure_reason} No valid records were processed."
        )
    elif mapped:
        message = "Some selected Granola notes could not be imported; valid results are retained."
    else:
        message = "No valid Granola records were processed; no new import files were written."

    recovery = selected_command("co granola import --help")
    mark_next_step_named()
    report = {
        "error": message,
        "exit_code": 1,
        "source": "granola",
        "scope": scope,
        "error_code": "partial_read" if not complete else ("partial_import" if mapped else "processing_failed"),
        "recovery_action": recovery,
        "written": source_yaml,
        "placement": "export" if export_id else "daily",
        "jsonl": str(jsonl_path) if jsonl_path else None,
        "folder_id": scope.get("folder_id", ""),
        "profile": scope.get("profile", ""),
        "notes": collected,
        "mapped": mapped,
        "appended": appended,
        "complete": complete,
        "rejected": rejected,
    }
    if as_json:
        print(json.dumps(report))
    else:
        _error(f"Granola import (scope: {json.dumps(scope)}).", markup=False)
        _error(message, markup=False)
        if jsonl_path and mapped:
            _error(
                f"Valid records retained: {mapped}; newly appended: {appended}. Saved to: {jsonl_path}",
                markup=False,
            )
        if rejected:
            _error(f"{len(rejected)} note(s) were rejected and not written:", markup=False)
            for label, reason in rejected.items():
                _error(f"  Rejected {label}: {reason}", markup=False)
        _error(f"Next: {recovery}", markup=False)
    sys.exit(1)


def _repeat_command(folder_id, profile, limit, output, note_id, include_children=False):
    args = ["co", "granola", "import", folder_id, "--profile", profile, "--output", str(output)]
    if note_id is not None:
        args.extend(["--note-id", note_id])
    elif limit is not None:
        args.extend(["--limit", str(limit)])
    if include_children:
        args.append("--include-children")
    return shlex.join(args)
