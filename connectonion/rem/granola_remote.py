"""Opt-in automatic collection of personal-folder generated summaries only."""
import hashlib

import yaml

from ..environment import setting
from .files import RemError, atomic_write
from .remote_sources import directory

CREDENTIALS = ("GRANOLA_API_KEY",)


def validate(value):
    from ..useful_tools.granola import MAX_SELECTED, validate_profile
    allowed = {"folder_id", "profile", "limit", "note_id", "include_children"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise RemError("Granola selection accepts folder_id, profile, limit or note_id, and include_children; no key")
    folder, profile, note = value.get("folder_id"), value.get("profile", "personal"), value.get("note_id")
    if not isinstance(folder, str) or not folder.strip():
        raise RemError("Select a personal folder_id from co granola folders")
    validate_profile(profile)
    limit = value.get("limit", MAX_SELECTED)
    if type(limit) is not int or not 1 <= limit <= MAX_SELECTED:
        raise RemError("Granola limit must be between 1 and the supported note limit")
    if note is not None and (not isinstance(note, str) or not note.strip() or "limit" in value):
        raise RemError("Granola note_id must be nonempty and cannot be combined with limit")
    if type(value.get("include_children", False)) is not bool:
        raise RemError("Granola include_children must be true or false")
    return {"folder_id": folder, "profile": profile, "include_children": value.get("include_children", False),
            **({"note_id": note} if note is not None else {"limit": limit})}


def binding():
    from .remote_sources import require_saved
    require_saved("GRANOLA_API_KEY")
    return hashlib.sha256((setting("GRANOLA_API_KEY") or "").encode()).hexdigest()


def configure(root, chosen):
    from ..useful_tools.granola import GranolaClient, GranolaIncompleteRead, MAX_SELECTED, validate_source_identity
    from ..useful_tools.granola_collection import personal_folder_paths
    from .granola_imports import identity
    target, key_id = directory(root, "granola"), binding()
    validate_source_identity(target, chosen["folder_id"], chosen["profile"])
    previous = target / "source.yaml"
    saved = yaml.safe_load(previous.read_text()) if previous.exists() else {}
    if saved.get("credential_binding") not in (None, key_id):
        raise RemError("Granola key changed; API has no verified account ID. Use a separate notebook/profile")
    expected = {"folder_id": chosen["folder_id"], "limit": 1 if "note_id" in chosen else chosen["limit"]}
    if "note_id" in chosen:
        expected["note_id"] = chosen["note_id"]
    if chosen["include_children"]:
        expected["include_children"] = True
    if saved and saved.get("scope") != expected:
        raise RemError("Granola scope changed; preserve old imports and use a separate notebook/profile")
    client = GranolaClient()
    try:
        personal_folder_paths(chosen["folder_id"], client.list_folders(), include_children=chosen["include_children"])
        if "note_id" in chosen:
            listed = client.list_notes(folder_id=chosen["folder_id"], limit=MAX_SELECTED)
            if chosen["note_id"] not in {row["id"] for row in listed if not row.get("deleted_at")}:
                raise RemError("Selected Granola note is not in this personal folder; inspect co granola notes")
    except GranolaIncompleteRead:
        raise RemError("Granola folder metadata read incomplete; retry co granola folders before connecting") from None
    client.write_source_yaml(target, chosen["folder_id"], chosen["profile"],
                             limit=1 if "note_id" in chosen else chosen["limit"],
                             note_id=chosen.get("note_id"), complete=False, include_children=chosen["include_children"])
    doc = yaml.safe_load(previous.read_text())
    doc["credential_binding"] = key_id  # non-secret binding, never model evidence
    atomic_write(previous, yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))
    return identity(root)


def refresh(root, subscription, chosen):
    from ..useful_tools.granola import GranolaClient, GranolaIncompleteRead, validate_source_identity
    from ..useful_tools.granola_collection import collect_summaries, _stored_versions, _place_records
    target = directory(root, "granola")
    declared = subscription["import_identity"]
    if declared.get("credential_binding") != binding():
        raise RemError("Granola key changed; reconnect before reading summaries")
    expected = {"folder_id": chosen["folder_id"], "limit": 1 if "note_id" in chosen else chosen["limit"]}
    if "note_id" in chosen:
        expected["note_id"] = chosen["note_id"]
    if chosen["include_children"]:
        expected["include_children"] = True
    if declared.get("scope") != expected or declared["account"] != chosen["profile"]:
        raise RemError("Granola selection differs from its approved declaration; reconnect")
    validate_source_identity(target, chosen["folder_id"], chosen["profile"])
    _stored_versions(target, chosen["folder_id"], chosen["profile"], include_children=chosen["include_children"])
    client = GranolaClient()
    try:
        result, notes, complete, reason = collect_summaries(client, chosen["folder_id"], chosen["profile"],
            limit=chosen.get("limit"), note_id=chosen.get("note_id"), include_children=chosen["include_children"])
    except GranolaIncompleteRead:
        return {"complete": False, "written": 0, "error_type": "metadata_incomplete"}
    # REM owns the lock already. CLI imports use the same collector/storage
    # under their own lock; nesting maintenance_lock would deadlock globally.
    scope = {**expected, "profile": chosen["profile"]}
    _, written = _place_records(result.records, target, None, scope)
    client.write_source_yaml(target, chosen["folder_id"], chosen["profile"], limit=expected["limit"],
                             note_id=chosen.get("note_id"), complete=complete and not result.errors, include_children=chosen["include_children"])
    return {"complete": complete and not result.errors, "written": written}


def _choose_scope():
    """Choose an explicit personal folder and bounded summary scope."""
    import typer
    from click import IntRange
    from ..useful_tools.granola import GranolaClient, MAX_SELECTED
    from ..useful_tools.granola_collection import personal_folder_paths
    from .remote_wizard import pick
    client = GranolaClient()
    folders = client.list_folders()
    personal = [row for row in folders if "space_id" in row and row["space_id"] is None]
    folder = pick(personal, "Granola personal folder (child folders may be selected directly)")
    children = any(row.get("parent_folder_id") == folder for row in folders)
    include = typer.confirm("Include current and future personal child folders?", default=False) if children else False
    personal_folder_paths(folder, folders, include_children=include)
    profile = typer.prompt("Local profile label (not verified account identity)", default="personal")
    chosen = {"folder_id": folder, "profile": profile, "include_children": include}
    if typer.confirm("Select one note instead of a bounded folder read?", default=False):
        notes = client.list_notes(folder_id=folder, limit=MAX_SELECTED)
        typer.echo("Choose from the bounded note metadata list; summaries have not been fetched.")
        chosen["note_id"] = pick(notes, "Granola note", title="title")
    else:
        chosen["limit"] = typer.prompt("Maximum notes per read (bounded coverage)", default=1000,
                                       type=IntRange(1, MAX_SELECTED))
    return chosen


def choose_scope():
    from ..useful_tools.granola import GranolaIncompleteRead
    try:
        return _choose_scope()
    except GranolaIncompleteRead:
        raise RemError("Granola metadata listing is incomplete; retry co granola folders before selecting scope") from None
