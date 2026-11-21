"""Shared Granola personal-summary collection and versioned persistence.

Used by the standalone CLI and native REM; no CLI invocation or model calls.
"""
import json
from pathlib import Path

from .granola import GranolaIncompleteRead, MAX_SELECTED
from .adapter import AdapterResult, granola_notes_to_records, _granola_personal_folder

class _FolderNotFound(ValueError):
    """folder_id does not appear in the list of accessible folders."""


class _NotPersonalFolder(ValueError):
    """folder_id is accessible but belongs to a shared space (space_id != None).

    NOTE: space_id=None as the personal-folder marker follows the Granola API
    field definition (space_id is null when the folder has no parent space).
    This assumption has not yet been confirmed with official Granola documentation
    or a direct client/vendor response; treat it as provisional until verified.
    """


class _FolderHasChildren(ValueError):
    """The API recursively includes child folders outside this exact selection."""


class _NoteNotInSelectedFolder(ValueError):
    """note_id is not in the scoped, non-deleted list for the selected folder.

    Raised when the requested note_id does not appear in the list of active
    (deleted_at=null) notes for the selected personal folder.  No detail
    request is made and no files are written before this is raised.
    """


def _validate_personal_folder(folder_id: str, all_folders: list[dict], *, include_children=False) -> None:
    """Raise _FolderNotFound or _NotPersonalFolder before any notes fetch or file writes.

    Must be called before list_notes() and before any output is written so that
    rejection leaves no side effects on disk.
    """
    all_ids = {f["id"] for f in all_folders}
    personal_ids = {f["id"] for f in all_folders if "space_id" in f and f["space_id"] is None}
    if folder_id not in all_ids:
        raise _FolderNotFound(
            f"Folder {folder_id!r} was not found or is not accessible with this API key. "
            "Run 'co granola folders' to list your personal folder IDs."
        )
    if folder_id not in personal_ids:
        raise _NotPersonalFolder(
            f"Folder {folder_id!r} is in a shared space and is not a personal folder. "
            "Only personal folders (space_id: null) are supported. "
            "Run 'co granola folders' to list your personal folder IDs."
        )
    if not include_children and any(folder.get("parent_folder_id") == folder_id for folder in all_folders):
        raise _FolderHasChildren("Granola includes child folders in folder reads. Choose a subfolder directly, or explicitly enable include_children / --include-children.")



def personal_folder_paths(folder_id, all_folders, *, include_children=False):
    """A selected personal node, optionally its explicitly approved subtree."""
    if (not isinstance(all_folders, list) or any(not isinstance(folder, dict)
            or not isinstance(folder.get("id"), str) or not folder["id"] for folder in all_folders)
            or len({folder["id"] for folder in all_folders}) != len(all_folders)):
        raise ValueError("Granola folder metadata is malformed or ambiguous; retry folders metadata")
    _validate_personal_folder(folder_id, all_folders, include_children=include_children)
    paths = {folder_id: [folder_id]}
    queue = [folder_id] if include_children else []
    while queue:
        parent = queue.pop(0)
        for folder in all_folders:
            if folder.get("parent_folder_id") != parent:
                continue
            child = folder.get("id")
            if not child or child in paths:
                raise ValueError("Granola folder hierarchy is malformed or cyclic; retry folders metadata")
            if "space_id" not in folder or folder["space_id"] is not None:
                raise _NotPersonalFolder("A descendant is not explicitly personal; narrow the selected folder scope")
            paths[child] = [*paths[parent], child]
            if len(paths[child]) > MAX_SELECTED:
                raise ValueError("Granola folder hierarchy exceeds the supported depth; select a narrower folder")
            queue.append(child)
    return paths


def record_in_folder_scope(record, folder_id, include_children=False):
    extensions = record.get("extensions", {})
    actual = extensions.get("folder_id")
    if actual == folder_id:
        return True
    path = extensions.get("collection_folder_path")
    return bool(include_children and extensions.get("collection_root_folder_id") == folder_id
                and isinstance(path, list) and 2 <= len(path) <= MAX_SELECTED
                and all(isinstance(part, str) and part for part in path)
                and len(set(path)) == len(path) and path[0] == folder_id and path[-1] == actual)


def _place_records(
    records: list[dict],
    output_dir: Path,
    export_id: str | None,
    scope: dict,
) -> tuple[Path | None, int]:
    from .adapter import append_daily_jsonl, write_export, _snapshot_hash
    if export_id is None:
        first = records[0] if records else {}
        saved = _stored_versions(output_dir, scope.get("folder_id") or first.get("extensions", {}).get("folder_id"),
                                  scope.get("profile") or first.get("account"), include_children=scope.get("include_children", False))
        fresh = [record for record in records if _snapshot_hash(record) not in saved]
        if not fresh:
            return None, 0
        return append_daily_jsonl(fresh, output_dir, keep_versions=True, atomic=True)
    return write_export(records, output_dir, export_id, scope) / "records.jsonl", len(records)


def _stored_versions(output_dir, folder_id, profile, *, include_children=False):
    from .adapter import validate_record, _snapshot_hash
    versions = set()
    for path in sorted(output_dir.glob("daily/*/*/*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                raise ValueError(f"Corrupt daily record at {path.name}:{line_number}; preserve it and use a separate --output.") from None
            if (validate_record(record) or record.get("source") != "granola" or record.get("account") != profile
                    or not record_in_folder_scope(record, folder_id, include_children)):
                raise ValueError("Existing daily records are invalid or belong to another source/profile/folder; "
                                 "preserve them and choose a separate --output.")
            versions.add(_snapshot_hash(record))
    return versions


def collect_summaries(client, folder_id, profile, *, limit=None, note_id=None, include_children=False):
    if note_id is not None and limit is not None:
        raise ValueError("--note-id and --limit cannot be used together")
    paths = personal_folder_paths(folder_id, client.list_folders(), include_children=include_children)
    complete = True
    failure_reason: str = ""

    if note_id is not None:
        # Precise single-note import: scoped lookup then targeted detail fetch.
        scoped_incomplete = False
        scoped_failure_reason = ""
        try:
            scoped_stubs = client.list_notes(folder_id=folder_id, limit=MAX_SELECTED)
        except GranolaIncompleteRead as exc:
            scoped_stubs = [n for page in exc.partial_pages for n in page]
            scoped_incomplete = True
            scoped_failure_reason = exc.reason

        active_ids = {
            str(s.get("id") or "")
            for s in scoped_stubs
            if not s.get("deleted_at")
        }
        if note_id not in active_ids:
            if scoped_incomplete:
                # Note absent from partial pages: it may be on an un-fetched page.
                # Report transient error rather than "not found" to avoid a false rejection.
                raise GranolaIncompleteRead(
                    reason=(
                        f"Scoped lookup for folder {folder_id!r} was incomplete "
                        f"({scoped_failure_reason}); cannot confirm whether note "
                        f"{note_id!r} exists. Retry when the API recovers."
                    ),
                    partial_pages=[],
                )
            raise _NoteNotInSelectedFolder(
                f"Note {note_id!r} was not found in the active notes for folder {folder_id!r}. "
                "It may have been deleted, moved, or not yet processed. "
                "Run 'co granola notes <folder-id> --json' to list available note IDs."
            )
        try:
            notes = client.hydrate_notes([{"id": note_id}])
        except GranolaIncompleteRead as exc:
            notes = [note for page in exc.partial_pages for note in page]
            complete = False
            failure_reason = exc.reason
        if scoped_incomplete:
            # Scoped lookup was partial but note was found; retain it with complete=False.
            complete = False
            failure_reason = scoped_failure_reason
    else:
        try:
            stubs = client.list_notes(folder_id=folder_id, limit=limit)
        except GranolaIncompleteRead as exc:
            stubs = [note for page in exc.partial_pages for note in page]
            complete = False
            failure_reason = exc.reason
        try:
            notes = client.hydrate_notes([note for note in stubs if not note.get("deleted_at")])
        except GranolaIncompleteRead as exc:
            # These are completed detail objects, not list stubs: never refetch.
            notes = [note for page in exc.partial_pages for note in page]
            complete = False
            failure_reason = "; ".join(filter(None, [failure_reason, exc.reason]))

    if not include_children:
        adapter_result = granola_notes_to_records(notes, profile, selected_folder_id=folder_id)
    else:
        adapter_result = AdapterResult()
        for note in notes:
            selected = next((identity for identity in sorted(paths, key=lambda identity: (len(paths[identity]), identity))
                             if _granola_personal_folder(note, identity)), folder_id) if isinstance(note, dict) else folder_id
            mapped = granola_notes_to_records([note], profile, selected_folder_id=selected)
            for record in mapped.records:
                if selected != folder_id:
                    record["extensions"].update(collection_root_folder_id=folder_id,
                                                 collection_folder_path=paths[selected])
            adapter_result.records.extend(mapped.records)
            adapter_result.errors.update(mapped.errors)
    return adapter_result, notes, complete, failure_reason
