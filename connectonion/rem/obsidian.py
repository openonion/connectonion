"""Single-vault configuration and scoped local reads for the selected REM source.

Selections live in the notebook's existing subscriptions file. Live readers take
an explicit selection and revalidate it on every call. The selected-source
dispatcher checks notebook consent before exposing material to a model. Direct Python readers take explicit scope rather than grant approval.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

from ..useful_tools import obsidian as vault_reader
from .files import RemError, WRITE_WAIT_SECONDS, maintenance_lock, read_json, state_path, write_json


SOURCE_ID = re.compile(r"obsidian:([0-9a-f]{32}):([0-9a-f]{32}):([0-9a-f]{32})")


class ScopeChanged(RemError):
    """The live filesystem no longer represents the saved canonical selection."""


@dataclass(frozen=True)
class Selection:
    """One vault and an explicit set of vault-relative folders."""

    vault: Path
    folders: tuple[str, ...]


def validate_selection(vault: Path, folders: Sequence[str]) -> Selection:
    """Reuse the CLI's scope validation, exclusions and overlap normalization."""
    scope = vault_reader._validate_scope(vault, folders)
    relative = tuple(folder.relative_to(scope.vault_path).as_posix() for folder in scope.folders)
    return Selection(scope.vault_path, relative)


def _subscriptions(root: Path) -> dict:
    sources = read_json(state_path(root, "subscriptions.json"), {})
    if not isinstance(sources, dict):
        raise RemError("Invalid subscriptions file; preserve it for diagnosis")
    for name, source in sources.items():
        if name != "obsidian" and (
            name.startswith("obsidian-") or isinstance(source, dict) and source.get("kind") == "obsidian"
        ):
            raise RemError("This notebook has named Obsidian sources; migrate to one vault before editing it")
    return sources


def _saved_selection(source: dict) -> Selection:
    """Validate stored data without opening the vault or scanning any directory."""
    if not isinstance(source, dict) or source.get("kind") != "obsidian":
        raise RemError("Invalid Obsidian subscription; preserve it for diagnosis")
    if source.get("excluded_paths"):
        raise RemError("This Obsidian selection has saved exclusions; migrate its scope before reading or editing it")
    vault, folders = source.get("vault"), source.get("folders")
    if not isinstance(vault, str) or not vault or "\x00" in vault or not Path(vault).is_absolute():
        raise RemError("The saved Obsidian vault must be an absolute path")
    if not isinstance(folders, list) or not folders or any(not isinstance(folder, str) for folder in folders):
        raise RemError("The saved Obsidian selection must contain explicit folders")
    for folder in folders:
        path = Path(folder)
        if not folder.strip() or "\x00" in folder or path.root or path.drive or ".." in path.parts:
            raise RemError("The saved Obsidian folders must be vault-relative without traversal")
    for flag in ("enabled", "consented", "unsubscribed"):
        if flag in source and type(source[flag]) is not bool:
            raise RemError(f"Invalid Obsidian {flag} flag; preserve it for diagnosis")
    return Selection(Path(vault), tuple(folders))


def load_selection(root: Path) -> Selection | None:
    """Inspect saved scope even when the vault is offline; perform no live reads."""
    sources = _subscriptions(root)
    return _saved_selection(sources["obsidian"]) if "obsidian" in sources else None


def save_selection(root: Path, vault: Path, folders: Sequence[str], *, replace: bool = False) -> Selection:
    """Register one vault, replacing its folder selection as a whole.

    Selecting a different vault requires replace=True. Any scope change or
    re-enabling clears consent. An identical enabled selection is a no-op.
    Existing REM approval records are retained; the shared dispatcher compares
    their scope with this selection before granting access.
    """
    selection = validate_selection(vault, folders)
    with maintenance_lock(root, wait=WRITE_WAIT_SECONDS):
        sources = _subscriptions(root)
        previous = sources.get("obsidian")
        old = _saved_selection(previous) if "obsidian" in sources else None
        if old is not None and old.vault != selection.vault and not replace:
            raise RemError("A different Obsidian vault is already selected; use replace=True to switch vaults")
        if old == selection and previous.get("enabled") and not previous.get("unsubscribed"):
            return selection
        sources["obsidian"] = {
            "id": "obsidian", "kind": "obsidian", "vault": str(selection.vault),
            "folders": list(selection.folders), "enabled": True, "consented": False,
            "unsubscribed": False,
        }
        write_json(state_path(root, "subscriptions.json"), sources)
    return selection


def _live_scope(selection: Selection):
    # Registration saves canonical paths. Check parents before descendants so
    # even a newly introduced symlink loop is a scope failure, not an outage.
    for path in (*reversed(selection.vault.parents), selection.vault):
        if path.is_symlink():
            raise ScopeChanged("The selected Obsidian vault path now contains a symlink")
    try:
        scope = vault_reader._validate_scope(selection.vault, selection.folders)
    except ValueError as error:
        raise ScopeChanged("The selected Obsidian paths no longer have a valid scope") from error
    expected = tuple(selection.vault / folder for folder in selection.folders)
    if scope.vault_path != selection.vault or scope.folders != expected:
        raise ScopeChanged("The selected Obsidian paths resolve outside their saved scope")
    return scope


def list_notes(selection: Selection) -> list[dict]:
    """Read live selected notes locally; return the CLI's parsed note records.

    Selection represents scope, not model consent. REM callers must enforce
    approval separately when the shared source interface is connected.
    """
    # Read the validated scope itself: resolving the vault again could switch
    # to an unapproved directory after a parent is replaced by a symlink.
    scope = _live_scope(selection)
    try:
        notes = vault_reader._load_scope_notes(scope)
    except vault_reader.ObsidianError:
        _live_scope(selection)  # Classify a concurrent scope change before retry policy.
        raise
    _live_scope(selection)
    return notes


def read_note(selection: Selection, reference: str) -> dict:
    """Read a live note by title or relative path within the explicit selection."""
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("Choose a note path or filename title.")
    scope = _live_scope(selection)
    if "/" in reference or "\\" in reference or reference.lower().endswith(".md") or Path(reference).is_absolute():
        reference = vault_reader._resolve_note_path(scope, reference)
    return vault_reader._select_note(list_notes(selection), reference)


def record_of(source_id: str) -> str | None:
    """Return a version's notebook/vault and note identity without doing any I/O.

    This recognizes ID syntax. Existence and version ordering require the store.
    """
    if not isinstance(source_id, str) or SOURCE_ID.fullmatch(source_id) is None:
        return None
    return source_id.rsplit(":", 1)[0]


def cited(root: Path, source_id: str, *, expected: dict | None = None) -> dict | None:
    """Adapt an exact saved version to the reader context shape proposed in #3055.

    Missing, disabled and out-of-scope versions return None. Store corruption
    and programming errors propagate. Shared dispatch must enforce model consent
    before calling this adapter. Supplying expected also checks the current
    subscription's scope and consent under the store lock. Private material is omitted because
    the proposed two-argument hook carries no owner-only display flag.
    """
    if record_of(source_id) is None:
        return None
    from .obsidian_store import SnapshotUnavailable, read_snapshot
    try:
        snapshot = (read_snapshot(root, source_id) if expected is None
                    else read_snapshot(root, source_id, expected=expected))
    except SnapshotUnavailable:
        return None
    return _snapshot_context(snapshot)


def _snapshot_context(snapshot: dict) -> dict | None:
    """A saved note's public context; check privacy before any truncation."""
    from .reader_model import PRIVATE

    note = snapshot["note"]
    if PRIVATE.search(note["content"]) or PRIVATE.search(note["path"]):
        return None
    return {
        "excerpt": note["content"], "truncated": False, "time": note["modified_at"],
        "sender": "", "thread": "", "source": "obsidian", "subject": note["path"],
        "captured_at": snapshot["collected_at"],
        "input_scope": "One saved Obsidian note version within the currently selected folders. "
                       "Collection time is not the date of its claims.",
    }
