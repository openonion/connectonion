"""Notebook-local, immutable Obsidian snapshots and atomic collection progress.

Explicit local collection reuses the configured single-vault selection. These
functions do not grant model consent. The selected-source dispatcher checks approval
before collecting for a model or exposing saved material to it.
"""

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import uuid

from . import obsidian
from .files import RemError, WRITE_WAIT_SECONDS, maintenance_lock, material_lock, state_path


DATABASE = "obsidian-snapshots.db"
SCHEMA_VERSION = 1
SCHEMA = (
    "CREATE TABLE snapshots (source_id TEXT PRIMARY KEY, vault TEXT NOT NULL, path TEXT NOT NULL, "
    "digest TEXT NOT NULL, note TEXT NOT NULL, collected_at TEXT NOT NULL)",
    "CREATE TABLE heads (path TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES snapshots(source_id))",
    "CREATE TABLE changes (sequence INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
    "source_id TEXT NOT NULL REFERENCES snapshots(source_id), observed_at TEXT NOT NULL)",
    "CREATE TABLE selection (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
    "notebook TEXT NOT NULL, vault TEXT NOT NULL, folders TEXT NOT NULL)",
)


class SnapshotUnavailable(RemError):
    """The current selection cannot expose this snapshot through a citation."""


def _selection(root: Path, expected: dict | None = None) -> obsidian.Selection:
    sources = obsidian._subscriptions(root)
    if "obsidian" not in sources:
        raise SnapshotUnavailable("Select an Obsidian vault and folders before collecting or reading snapshots")
    source = sources["obsidian"]
    selected = obsidian._saved_selection(source)
    if not source.get("enabled") or source.get("unsubscribed"):
        raise SnapshotUnavailable("The Obsidian source is disabled")
    if expected is not None:
        requested = obsidian._saved_selection(expected)
        if (requested != selected or not source.get("consented")
                or not expected.get("consented") or not expected.get("enabled")
                or expected.get("unsubscribed")):
            raise SnapshotUnavailable("Obsidian selection or approval changed; reload the selected source")
        from .source_hooks import approved
        if not approved(root, "obsidian", source):
            raise SnapshotUnavailable("Obsidian approval receipt changed; run co rem start again")
    # Saved selections are canonicalized at registration. Offline reads must
    # not resolve/stat a live vault which may now be unavailable or redirected.
    if root.resolve().is_relative_to(selected.vault):
        raise RemError("The snapshot notebook must be outside the Obsidian vault")
    return selected


def _connect(root: Path, *, create: bool) -> sqlite3.Connection:
    path = state_path(root, DATABASE)
    for suffix in ("-journal", "-wal", "-shm"):
        state_path(root, DATABASE + suffix)
    if path.exists() and not path.is_file():
        raise RemError("The Obsidian snapshot store must be a regular file")
    if create:
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(descriptor)
        path.chmod(0o600)
    mode = "rw" if create else "ro"
    connection = sqlite3.connect(path.absolute().as_uri() + f"?mode={mode}", uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if create:
        connection.execute("PRAGMA synchronous = FULL")
    return connection


def _schema(connection: sqlite3.Connection, *, create: bool) -> bool:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return True
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    if version != 0 or tables:
        raise RemError("Unsupported Obsidian snapshot store; preserve it for diagnosis")
    if not create:
        return False
    for statement in SCHEMA:
        connection.execute(statement)
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return True


def _bound(connection: sqlite3.Connection, root: Path) -> None:
    row = connection.execute("SELECT notebook FROM selection WHERE singleton = 1").fetchone()
    if row is not None and row["notebook"] != str(root.resolve()):
        raise RemError("The Obsidian snapshot store belongs to another notebook")


def _in_scope(selection: obsidian.Selection, vault: str, path: str) -> bool:
    relative = PurePosixPath(path)
    return (vault == str(selection.vault) and not relative.is_absolute() and ".." not in relative.parts
            and not any(part in obsidian.vault_reader.EXCLUDED_DIRS for part in relative.parts)
            and any(relative.is_relative_to(PurePosixPath(folder)) for folder in selection.folders))


def _record_change(connection, kind: str, source_id: str, observed_at: str) -> dict:
    cursor = connection.execute(
        "INSERT INTO changes (kind, source_id, observed_at) VALUES (?, ?, ?)",
        (kind, source_id, observed_at),
    )
    return {"sequence": cursor.lastrowid, "kind": kind, "source_id": source_id}


def _save_note(connection, root: Path, selection, note: dict, previous, observed_at: str) -> dict | None:
    digest = sha256(note["content"].encode("utf-8")).hexdigest()
    if previous is not None and previous["vault"] == str(selection.vault) and previous["digest"] == digest:
        return None
    instance = uuid.uuid5(uuid.NAMESPACE_URL, json.dumps([str(root.resolve()), str(selection.vault)]))
    identity = uuid.uuid5(instance, note["path"])
    source_id = f"obsidian:{instance.hex}:{identity.hex}:{uuid.uuid4().hex}"
    connection.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?, ?)", (
        source_id, str(selection.vault), note["path"], digest, json.dumps(note, ensure_ascii=False), observed_at,
    ))
    connection.execute("INSERT OR REPLACE INTO heads VALUES (?, ?)", (note["path"], source_id))
    kind = "modified" if previous is not None and previous["vault"] == str(selection.vault) else "added"
    return _record_change(connection, kind, source_id, observed_at)


def _collect(connection, root: Path, selection, notes: list[dict]) -> dict:
    _schema(connection, create=True)
    _bound(connection, root)
    old = {row["path"]: row for row in connection.execute(
        "SELECT s.path, s.vault, s.digest, s.source_id FROM heads h JOIN snapshots s USING (source_id)"
    )}
    current = {note["path"] for note in notes}
    observed_at = datetime.now(timezone.utc).isoformat()
    changes = []
    for path, previous in old.items():
        if previous["vault"] != str(selection.vault) or path not in current:
            kind = "deleted"
            if previous["vault"] != str(selection.vault):
                kind = "vault_replaced"
            elif not _in_scope(selection, previous["vault"], path):
                kind = "scope_removed"
            changes.append(_record_change(connection, kind, previous["source_id"], observed_at))
            connection.execute("DELETE FROM heads WHERE path = ?", (path,))
    for note in notes:
        change = _save_note(connection, root, selection, note, old.get(note["path"]), observed_at)
        if change is not None:
            changes.append(change)
    connection.execute("INSERT OR REPLACE INTO selection VALUES (1, ?, ?, ?)", (
        str(root.resolve()), str(selection.vault), json.dumps(selection.folders),
    ))
    cursor = connection.execute("SELECT COALESCE(MAX(sequence), 0) FROM changes").fetchone()[0]
    counts = {kind: sum(change["kind"] == kind for change in changes)
              for kind in ("added", "modified", "deleted", "scope_removed", "vault_replaced")}
    return {**counts, "unchanged": len(notes) - counts["added"] - counts["modified"],
            "cursor": cursor, "changes": changes}


def collect(root: Path, *, expected: dict | None = None) -> dict:
    """Collect the currently configured scope locally in one transaction.

    A complete scan precedes any snapshot write. Note content determines change;
    touching a file does not create a version. Renames are deletion plus addition.
    Changes, immutable versions and current heads commit together. A retry after
    rollback compares against the last committed collection.
    """
    _selection(root, expected)
    with maintenance_lock(root, wait=WRITE_WAIT_SECONDS):
        selection = _selection(root, expected)
        if root.resolve().is_relative_to(selection.vault.resolve()):
            raise RemError("The snapshot notebook must be outside the Obsidian vault")
        notes = obsidian.list_notes(selection)
        with closing(_connect(root, create=True)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            return _collect(connection, root, selection, notes)


def _decode(row, selection: obsidian.Selection) -> dict:
    note = json.loads(row["note"])
    if note["path"] != row["path"] or sha256(note["content"].encode("utf-8")).hexdigest() != row["digest"]:
        raise RemError("Obsidian snapshot integrity check failed; preserve the store for diagnosis")
    for link in note["links"]:
        if link["resolved_path"] and not _in_scope(selection, row["vault"], link["resolved_path"]):
            link.update(resolved_path=None, resolution="out_of_scope")
    note["backlinks"] = [link for link in note["backlinks"]
                         if _in_scope(selection, row["vault"], link["source_path"])]
    return {"source_id": row["source_id"], "collected_at": row["collected_at"], "note": note}


def latest_snapshots(root: Path) -> list[dict]:
    """Read current saved notes within the current enabled scope, including offline vaults."""
    _selection(root)
    with material_lock(root):
        selection = _selection(root)
        if not state_path(root, DATABASE).exists():
            return []
        with closing(_connect(root, create=False)) as connection:
            if not _schema(connection, create=False):
                return []
            _bound(connection, root)
            output = []
            for row in connection.execute(
                "SELECT s.* FROM heads h JOIN snapshots s USING (source_id) WHERE s.vault = ? ORDER BY s.path",
                (str(selection.vault),),
            ):
                if _in_scope(selection, row["vault"], row["path"]):
                    output.append(_decode(row, selection))
            return output


def read_snapshot(root: Path, source_id: str, *, expected: dict | None = None) -> dict:
    """Resolve an exact saved version while enforcing the current source selection."""
    unavailable = "Snapshot unavailable in the current Obsidian selection"
    _selection(root, expected)
    with material_lock(root):
        selection = _selection(root, expected)
        if not state_path(root, DATABASE).exists():
            raise SnapshotUnavailable(unavailable)
        with closing(_connect(root, create=False)) as connection:
            if not _schema(connection, create=False):
                raise SnapshotUnavailable(unavailable)
            _bound(connection, root)
            row = connection.execute("SELECT * FROM snapshots WHERE source_id = ?", (source_id,)).fetchone()
            if row is None or not _in_scope(selection, row["vault"], row["path"]):
                raise SnapshotUnavailable(unavailable)
            return _decode(row, selection)


@contextmanager
def _saved_store(root: Path, expected: dict):
    """An approved, scope-checked offline read; caller closes before taking another lock."""
    _selection(root, expected)
    with material_lock(root):
        selection = _selection(root, expected)
        if not state_path(root, DATABASE).exists():
            raise SnapshotUnavailable("No Obsidian snapshots collected; acquire snapshots before reading a batch")
        with closing(_connect(root, create=False)) as connection:
            if not _schema(connection, create=False):
                raise SnapshotUnavailable("No Obsidian snapshots collected; retry snapshot acquisition")
            _bound(connection, root)
            yield selection, connection


def iter_changes(root: Path, after: int, *, expected: dict):
    """Stream checkpoints and current snapshots, not stale queued bodies.

    Removed, superseded and out-of-scope events advance the cursor without
    returning their paths or content. Historical versions remain citable.
    History is streamed without a page cap so skipped events cannot produce
    a false empty batch before an eligible note. Close this generator when
    stopping early to release its connection/lock.
    """
    if type(after) is not int or after < 0:
        raise RemError("Invalid Obsidian checkpoint; preserve it for diagnosis")
    with _saved_store(root, expected) as (selection, connection):
        latest = connection.execute("SELECT COALESCE(MAX(sequence), 0) FROM changes").fetchone()[0]
        if after > latest:
            raise RemError("Obsidian checkpoint is ahead of the snapshot store; preserve it for diagnosis")
        rows = connection.execute(
            "SELECT c.*, s.vault, s.path, h.source_id AS current_id FROM changes c "
            "JOIN snapshots s USING (source_id) LEFT JOIN heads h ON h.path = s.path "
            "WHERE c.sequence > ? ORDER BY c.sequence", (after,))
        for row in rows:
            if row["kind"] not in {"added", "modified", "deleted", "scope_removed", "vault_replaced"}:
                raise RemError("Unknown Obsidian snapshot change; preserve the store for diagnosis")
            snapshot = None
            if (row["kind"] in {"added", "modified"} and row["current_id"] == row["source_id"]
                    and _in_scope(selection, row["vault"], row["path"])):
                stored = connection.execute("SELECT * FROM snapshots WHERE source_id = ?", (row["source_id"],)).fetchone()
                snapshot = _decode(stored, selection)
            yield {"sequence": row["sequence"], "snapshot": snapshot}


def iter_latest(root: Path, *, expected: dict):
    """Stream current scoped versions offline; close the generator on early exit."""
    with _saved_store(root, expected) as (selection, connection):
        rows = connection.execute(
            "SELECT s.* FROM heads h JOIN snapshots s USING (source_id) WHERE s.vault = ? ORDER BY s.path",
            (str(selection.vault),))
        for row in rows:
            if _in_scope(selection, row["vault"], row["path"]):
                yield _decode(row, selection)


def pending_metadata(root: Path, after: int, *, expected: dict) -> dict:
    """Count eligible current versions from the index; never decode note bodies."""
    with material_lock(root):
        selection = _selection(root, expected)
        if not state_path(root, DATABASE).exists():
            return {"initialized": False, "pending_notes": None, "body_reads": False,
                    "note": "No snapshots yet; co rem sync collects the selected folders"}
        with _saved_store(root, expected) as (selection, connection):
            latest = connection.execute("SELECT COALESCE(MAX(sequence), 0) FROM changes").fetchone()[0]
            if type(after) is not int or after < 0 or after > latest:
                raise RemError("Invalid Obsidian checkpoint; preserve it for diagnosis")
            rows = connection.execute(
                "SELECT s.vault, s.path FROM changes c JOIN heads h USING (source_id) "
                "JOIN snapshots s USING (source_id) WHERE c.sequence > ? "
                "AND c.kind IN ('added', 'modified')", (after,))
            count = sum(_in_scope(selection, row["vault"], row["path"]) for row in rows)
            return {"initialized": True, "pending_notes": count, "body_reads": False}
