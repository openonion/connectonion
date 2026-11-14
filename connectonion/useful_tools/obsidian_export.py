"""
Purpose: Collect selected Obsidian notes into committed, incremental inbox records
LLM-Note:
  Dependencies: obsidian scope/Markdown readers, pathlib, hashlib, json, uuid, OS file locks | imported by rem/service.py for source logs
  Data flow: explicit vault/folders → complete selected scan → compare last committed content → daily JSONL → atomic manifest → local readers
  State/Effects: writes only the external source directory; never modifies a vault, grants consent, runs a model or updates Wiki pages
  Integration: sync_notes, source_directory, export_status, latest_snapshots, load_snapshots, source_log; source registration and REM consumption are separate stories
  Errors: ObsidianError for incomplete reads; ValueError for unsafe selections; ObsidianStoreError(stage, committed) for storage failures. A durability error after manifest replacement reports committed=True, never a fictitious rollback.
"""

import json
import os
import re
import stat
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Sequence

import yaml

from . import obsidian
from ._attachment_files import path_of_open_file

MANIFEST = ".state/manifest.json"
SCHEMA = "obsidian-note-change/1"
DAILY = re.compile(r"daily/[0-9]{4}/[0-9]{2}/[0-9]{2}\.jsonl")
SOURCE_ID = re.compile(r"obsidian:([0-9a-f]{32}):([0-9a-f]{32}):([0-9a-f]{32})")
HASH = re.compile(r"sha256:[0-9a-f]{64}")


class ObsidianStoreError(Exception):
    """A source store failure; committed means replacement preceded a durability error."""

    def __init__(self, message: str, *, stage: str, committed: bool = False):
        super().__init__(message)
        self.stage = stage
        self.committed = committed


def source_directory(vault_path: Path, *, notebook_root: Path) -> Path:
    """The inbox instance for one notebook/vault pair; no directories are created."""
    from ..inbox.store import default_home

    key = json.dumps(
        [
            os.path.normcase(str(Path(notebook_root).expanduser().resolve())),
            os.path.normcase(str(Path(vault_path).expanduser().resolve())),
        ]
    )
    instance = uuid.uuid5(uuid.NAMESPACE_URL, key).hex
    return default_home("obsidian") / instance


def sync_notes(
    vault_path: Path,
    source_dir: Path | None = None,
    *,
    folders: Sequence[str],
    notebook_root: Path | None = None,
    excluded_paths: Sequence[str] = (),
) -> dict:
    """Save added/modified/deleted notes, without changing the vault or running REM.

    The caller supplies an authorized scope; this function never creates a subscription
    or consent. The first pass records every selected Markdown file. Content hashes,
    not mtime, detect changes; a rename is deletion plus addition. A source directory
    is bound to its vault and notebook. Scope snapshots here are not editable policy.
    """
    notebook = Path(notebook_root or Path.home() / ".co/rem").expanduser().resolve()
    scope = obsidian._validate_scope(vault_path, folders)
    if any(
        part.casefold() in obsidian.EXCLUDED_DIRS
        for folder in scope.folders
        for part in folder.relative_to(scope.vault_path).parts
    ):
        raise ValueError("Obsidian system directories cannot be selected for collection.")
    excluded = _exclusions(excluded_paths)
    source = (
        Path(
            source_dir
            if source_dir is not None
            else source_directory(scope.vault_path, notebook_root=notebook)
        )
        .expanduser()
        .absolute()
    )
    _outside_vault(scope.vault_path, source, notebook)
    _mkdir(source)
    with _source_lock(source):
        state = _load_manifest(source)
        _binding(state, scope.vault_path, notebook)
        try:
            if state["source_instance_id"] is None:
                if _daily_files(source):
                    raise ObsidianStoreError(
                        "Daily material has no manifest; restore the manifest before collecting.",
                        stage="state",
                    )
                state.update(
                    source_instance_id=source_directory(scope.vault_path, notebook_root=notebook).name,
                    vault=str(scope.vault_path),
                    notebook_root=str(notebook),
                )
                _commit_manifest(source, state)
            _recover(source, state)
            started = _iso(_now())
            notes = _read_scope(scope, excluded)
            # Recheck scope and membership: a failed or shrinking scan is not a deletion.
            if obsidian._validate_scope(scope.vault_path, folders) != scope:
                raise obsidian.ObsidianError(
                    "Obsidian scope changed during collection; retry.", obsidian.HELP
                )
            if _paths(scope, excluded) != sorted(notes):
                raise obsidian.ObsidianError(
                    "Obsidian files changed during collection; retry.", obsidian.HELP
                )
            new_state, changes = _changes(state, notes, scope, excluded, started)
            if changes:
                _append_records(source, new_state, changes, started)
            new_state.update(cursor=started, last_success_at=_iso(_now()), last_failure=None)
            _commit_manifest(source, new_state)
        except (OSError, obsidian.ObsidianError, ValueError, ObsidianStoreError) as error:
            _fail(source, error)
        counts = {
            kind: sum(row["change_type"] == kind for row in changes)
            for kind in ("added", "modified", "deleted")
        }
        return {
            "source_instance_id": new_state["source_instance_id"],
            "source_dir": str(source),
            "scanned_notes": len(notes),
            "appended_records": len(changes),
            **counts,
            "source_ids": [row["source_id"] for row in changes],
            "cursor": new_state["cursor"],
        }


def export_status(source_dir: Path) -> dict:
    """Metadata only, read-only; never collected differs from an empty successful pass."""
    state = _load_manifest(Path(source_dir).expanduser().absolute())
    return {
        key: deepcopy(state[key])
        for key in (
            "source_instance_id",
            "vault",
            "notebook_root",
            "folders",
            "excluded_paths",
            "scope_revision",
            "cursor",
            "record_count",
            "last_success_at",
            "last_failure",
        )
    } | {"initialized": state["last_success_at"] is not None}


def latest_snapshots(source_dir: Path, *, include_deleted: bool = False) -> list[dict]:
    """Latest committed locators, without reading bodies; tombstones are opt-in."""
    state = _load_manifest(Path(source_dir).expanduser().absolute())
    entries = [
        state["events"][entry["source_id"]]
        for entry in state["notes"].values()
        if include_deleted or entry["change_type"] != "deleted"
    ]
    return sorted(deepcopy(entries), key=lambda entry: (entry["observed_at"], entry["path"]))


def committed_events(source_dir: Path) -> list[dict]:
    """All committed event locators in publication order; no daily bodies are opened.

    Consumers keep their own progress. The manifest, not the physical JSONL tail,
    determines which changes are visible, including historical versions and deletions.
    """
    state = _load_manifest(Path(source_dir).expanduser().absolute())
    return deepcopy(list(state["events"].values()))


def load_snapshots(source_dir: Path, selected: list[dict]) -> list[dict]:
    """Read only committed records named by the index, in the caller's order."""
    source = Path(source_dir).expanduser().absolute()
    state = _load_manifest(source)
    loaded = []
    for entry in selected:
        if not isinstance(entry, dict) or state["events"].get(entry.get("source_id")) != entry:
            raise ObsidianStoreError("Unknown or changed Obsidian snapshot locator.", stage="read")
        locator = entry["locator"]
        try:
            with _open_file(source, locator["file"], os.O_RDONLY) as stream:
                stream.seek(locator["offset"])
                raw = stream.read(locator["length"] + 1)
            if len(raw) != locator["length"] + 1 or not raw.endswith(b"\n"):
                raise ValueError("Truncated record")
            row = json.loads(raw.decode("utf-8"))
            if (
                row["source_id"] != entry["source_id"]
                or row["path"] != entry["path"]
                or row["note_id"] != entry["note_id"]
                or row["schema"] != SCHEMA
                or row["change_type"] != entry["change_type"]
                or row["content_hash"] != entry["content_hash"]
            ):
                raise ValueError("Record identity differs from its index")
            if row["change_type"] == "deleted":
                if row["note"] is not None:
                    raise ValueError("A tombstone cannot carry old note content")
            elif (
                "sha256:" + sha256(row["note"]["content"].encode("utf-8")).hexdigest() != row["content_hash"]
            ):
                raise ValueError("Note content differs from its committed hash")
            loaded.append(row)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
            raise ObsidianStoreError(
                "Cannot read the committed Obsidian record; restore source data.", stage="read"
            ) from error
    return loaded


def source_log(source_dir: Path, source_id: str, *, notebook_root: Path) -> dict:
    """Trace one collected version without exposing its body or claiming REM ingestion."""
    state = _load_manifest(Path(source_dir).expanduser().absolute())
    if state["notebook_root"] != str(Path(notebook_root).expanduser().resolve()):
        raise ObsidianStoreError("This Obsidian source belongs to another notebook.", stage="binding")
    entry = state["events"].get(source_id)
    if entry is None:
        raise ObsidianStoreError(
            "Unknown Obsidian source ID; use an ID returned by collection.", stage="read"
        )
    return {key: deepcopy(value) for key, value in entry.items() if key != "locator"} | {
        "collected_at": entry["observed_at"],
        "ingested_at": None,
        "status": "collected",
        "ingestion_status": "not recorded; REM consumption is not connected",
    }


# -- explicit scope -------------------------------------------------------


def _exclusions(paths) -> list[str]:
    if not isinstance(paths, (list, tuple, set, frozenset)):
        raise ValueError("Excluded notes must be a sequence of vault-relative .md paths.")
    return sorted({_note_path(path) for path in paths})


def _note_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ValueError("Choose a vault-relative Markdown path using forward slashes.")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or PureWindowsPath(value).drive
        or ".." in path.parts
        or path.suffix.lower() != ".md"
        or any(part.casefold() in obsidian.EXCLUDED_DIRS for part in path.parts)
    ):
        raise ValueError("Unsafe or excluded Markdown path.")
    return path.as_posix()


def _outside_vault(vault: Path, source: Path, notebook: Path) -> None:
    if source.resolve().is_relative_to(vault) or notebook.is_relative_to(vault):
        raise ValueError("Obsidian inbox and REM output must be outside the original vault.")
    if vault.is_relative_to(source.resolve()):
        raise ValueError("The vault cannot be inside its export directory.")


def _paths(scope, excluded) -> list[str]:
    return sorted(
        path.relative_to(scope.vault_path).as_posix()
        for path in obsidian._scan_markdown(scope)
        if path.relative_to(scope.vault_path).as_posix() not in excluded
        and not any(
            part.casefold() in obsidian.EXCLUDED_DIRS for part in path.relative_to(scope.vault_path).parts
        )
    )


def _read_scope(scope, excluded) -> dict:
    """Filter before reading, parse original text once, and fail the whole pass on any bad note."""
    notes, failed = {}, []
    for key in _paths(scope, excluded):
        try:
            path = scope.vault_path / key
            if not path.stat().st_mode & 0o444:
                raise OSError("Unreadable note")
            content, mtime = obsidian._read_markdown(scope, path)
            note = obsidian._parse_markdown(content, key, mtime)
            note["content_hash"] = "sha256:" + sha256(content.encode("utf-8")).hexdigest()
            notes[key] = note
        except (OSError, UnicodeError, ValueError, yaml.YAMLError, obsidian.ObsidianError, RecursionError):
            failed.append(key)
    if failed:
        raise obsidian.ObsidianError(
            "Cannot collect Obsidian notes: " + ", ".join(failed), obsidian.HELP, failed_paths=failed
        )
    return notes


def _binding(state, vault, notebook):
    if state["vault"] is not None and (
        state["vault"] != str(vault) or state["notebook_root"] != str(notebook)
    ):
        raise ObsidianStoreError(
            "This export directory belongs to another vault or notebook.", stage="binding"
        )


def _changes(state, notes, scope, excluded, observed):
    new = deepcopy(state)
    folders = sorted(path.relative_to(scope.vault_path).as_posix() for path in scope.folders)
    if folders != state["folders"] or excluded != state["excluded_paths"]:
        new["scope_revision"] += 1
    new.update(folders=folders, excluded_paths=excluded)
    changes = []
    for key in sorted(set(notes) | set(state["notes"])):
        previous = state["notes"].get(key)
        note = notes.get(key)
        if note is None:
            if previous["change_type"] == "deleted":
                continue
            reason = (
                "excluded"
                if key in excluded
                else (
                    "scope_removed"
                    if not obsidian._in_scope(scope, scope.vault_path / key)
                    else "source_deleted"
                )
            )
            if reason == "source_deleted":
                current = scope.vault_path
                for part in PurePosixPath(key).parts:
                    current /= part
                    if current.is_symlink():
                        raise obsidian.ObsidianError(
                            "A tracked note became a symlink; collection stopped.", obsidian.HELP
                        )
            kind = "deleted"
        else:
            if (
                previous
                and previous["change_type"] != "deleted"
                and previous["content_hash"] == note["content_hash"]
            ):
                continue
            reason = None
            kind = "added" if previous is None or previous["change_type"] == "deleted" else "modified"
        note_id = previous["note_id"] if previous else uuid.uuid4().hex
        event = uuid.uuid4().hex
        source_id = f"obsidian:{state['source_instance_id']}:{note_id}:{event}"
        row = {
            "schema": SCHEMA,
            "source_instance_id": state["source_instance_id"],
            "note_id": note_id,
            "event_id": event,
            "source_id": source_id,
            "path": key,
            "change_type": kind,
            "reason": reason,
            "observed_at": observed,
            "source_modified_at": note["modified_at"] if note else None,
            "scope_revision": new["scope_revision"],
            "previous_source_id": previous["source_id"] if previous else None,
            "content_hash": note["content_hash"] if note else None,
            "note": note,
            "ingested_at": None,
        }
        changes.append(row)
    return new, changes


# -- committed store ------------------------------------------------------


def _empty_manifest():
    return {
        "version": 1,
        "source_instance_id": None,
        "vault": None,
        "notebook_root": None,
        "folders": [],
        "excluded_paths": [],
        "scope_revision": 0,
        "cursor": None,
        "committed_bytes": {},
        "notes": {},
        "events": {},
        "record_count": 0,
        "last_success_at": None,
        "last_failure": None,
    }


def _load_manifest(source):
    try:
        _no_links(source)
        if source.exists() and not source.is_dir():
            raise OSError("Obsidian source must be a directory")
        if not (source / MANIFEST).exists():
            return _empty_manifest()
        with _open_file(source, MANIFEST, os.O_RDONLY) as stream:
            state = json.load(stream)
        _validate_manifest(state)
        return state
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise ObsidianStoreError(
            "Invalid Obsidian manifest; preserve it and restore from backup.", stage="state"
        ) from error


def _count(value):
    return type(value) is int and value >= 0


def _time(value):
    return isinstance(value, str) and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None


def _validate_manifest(state):
    if not isinstance(state, dict) or set(state) != set(_empty_manifest()) or state["version"] != 1:
        raise ValueError("Unknown manifest version or fields")
    if not all(_count(state[key]) for key in ("record_count", "scope_revision")):
        raise ValueError("Invalid counters")
    if not all(isinstance(state[key], dict) for key in ("committed_bytes", "notes", "events")):
        raise ValueError("Invalid index")
    for relative, length in state["committed_bytes"].items():
        if not isinstance(relative, str) or not DAILY.fullmatch(relative) or not _count(length):
            raise ValueError("Invalid committed boundary")
    for key in ("cursor", "last_success_at"):
        if state[key] is not None and not _time(state[key]):
            raise ValueError("Invalid timestamp")
    for key in ("folders", "excluded_paths"):
        if not isinstance(state[key], list) or any(not isinstance(p, str) for p in state[key]):
            raise ValueError("Invalid scope snapshot")
    instance = state["source_instance_id"]
    if not isinstance(instance, str) or not re.fullmatch("[0-9a-f]{32}", instance):
        raise ValueError("Invalid instance identity")
    if not all(
        isinstance(state[key], str) and Path(state[key]).is_absolute() for key in ("vault", "notebook_root")
    ):
        raise ValueError("Invalid binding")
    for source_id, entry in state["events"].items():
        match = SOURCE_ID.fullmatch(source_id) if isinstance(source_id, str) else None
        if not isinstance(entry, dict):
            raise ValueError("Invalid event index")
        if (
            not match
            or match[1] != instance
            or entry["source_id"] != source_id
            or entry["note_id"] != match[2]
        ):
            raise ValueError("Invalid event identity")
        _note_path(entry["path"])
        if entry["change_type"] not in ("added", "modified", "deleted") or not _time(entry["observed_at"]):
            raise ValueError("Invalid event metadata")
        digest = entry["content_hash"]
        if (entry["change_type"] == "deleted" and digest is not None) or (
            entry["change_type"] != "deleted" and (not isinstance(digest, str) or not HASH.fullmatch(digest))
        ):
            raise ValueError("Invalid event content hash")
        locator = entry["locator"]
        if (
            not isinstance(locator, dict)
            or not isinstance(locator.get("file"), str)
            or not DAILY.fullmatch(locator["file"])
            or not _count(locator["offset"])
            or not _count(locator["length"])
            or not locator["length"]
            or locator["offset"] + locator["length"] + 1 > state["committed_bytes"].get(locator["file"], 0)
        ):
            raise ValueError("Invalid record locator")
    if state["record_count"] != len(state["events"]):
        raise ValueError("Record count differs from index")
    for path, entry in state["notes"].items():
        _note_path(path)
        event = state["events"][entry["source_id"]]
        if (
            event["path"] != path
            or event["note_id"] != entry["note_id"]
            or event["change_type"] != entry["change_type"]
        ):
            raise ValueError("Invalid latest index")
        if entry["content_hash"] != event["content_hash"]:
            raise ValueError("Invalid content hash")
    failure = state["last_failure"]
    if failure is not None and (
        not isinstance(failure, dict) or not _time(failure["at"]) or not isinstance(failure["stage"], str)
    ):
        raise ValueError("Invalid failure record")


def _recover(source, state):
    """Only unpublished bytes may be removed; committed short/missing files are damage."""
    files = _daily_files(source)
    if any(size and relative not in files for relative, size in state["committed_bytes"].items()):
        raise ObsidianStoreError(
            "Committed Obsidian data is missing; restore it before collecting.", stage="recover"
        )
    for relative in files:
        with _open_file(source, relative, os.O_RDWR) as stream:
            size = os.fstat(stream.fileno()).st_size
            committed = state["committed_bytes"].get(relative, 0)
            if size < committed:
                raise ObsidianStoreError(
                    "Obsidian data is shorter than its committed boundary.", stage="recover"
                )
            if size > committed:
                stream.truncate(committed)
                stream.flush()
                os.fsync(stream.fileno())


def _append_records(source, state, changes, started):
    relative = f"daily/{datetime.fromisoformat(started):%Y/%m/%d}.jsonl"
    _mkdir(source / PurePosixPath(relative).parent)
    offset = state["committed_bytes"].get(relative, 0)
    with _open_file(source, relative, os.O_WRONLY | os.O_CREAT | os.O_APPEND) as stream:
        if os.fstat(stream.fileno()).st_size != offset:
            raise ObsidianStoreError("Daily data changed before append; retry collection.", stage="write")
        for row in changes:
            line = json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
            stream.write(line + b"\n")
            entry = {
                key: row[key]
                for key in (
                    "source_id",
                    "note_id",
                    "path",
                    "change_type",
                    "reason",
                    "observed_at",
                    "source_modified_at",
                    "previous_source_id",
                    "content_hash",
                )
            }
            entry["locator"] = {"file": relative, "offset": offset, "length": len(line)}
            state["events"][row["source_id"]] = entry
            state["notes"][row["path"]] = {
                key: row[key] for key in ("source_id", "note_id", "change_type", "content_hash")
            }
            offset += len(line) + 1
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory((source / relative).parent)
    state["committed_bytes"][relative] = offset
    state["record_count"] += len(changes)


def _commit_manifest(source, state):
    """Atomic replacement publishes an entire pass; no reader sees a staged batch."""
    _validate_manifest(state)
    _mkdir(source / ".state")
    relative = f".state/.manifest-{uuid.uuid4().hex}.tmp"
    published = False
    try:
        with _open_file(source, relative, os.O_WRONLY | os.O_CREAT | os.O_EXCL) as stream:
            stream.write((json.dumps(state, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        _no_links(source / MANIFEST)
        os.replace(source / relative, source / MANIFEST)
        published = True
        _sync_directory(source / ".state")
    except OSError as error:
        raise ObsidianStoreError(
            (
                "Manifest was published but durability is uncertain; inspect export_status before retrying."
                if published
                else "Cannot publish the Obsidian manifest; retry after fixing storage."
            ),
            stage="durability" if published else "write",
            committed=published,
        ) from error
    finally:
        (source / relative).unlink(missing_ok=True)


def _fail(source, error):
    if getattr(error, "committed", False) or getattr(error, "stage", "") in ("state", "recover", "binding"):
        raise error
    try:
        state = _load_manifest(source)
        if state["source_instance_id"] is not None:
            # Keep paths and stage, never copy note contents from a parser exception.
            state["last_failure"] = {
                "at": _iso(_now()),
                "stage": getattr(error, "stage", "read"),
                "message": "Collection failed; the previous committed pass is unchanged.",
            }
            _commit_manifest(source, state)
    except (OSError, ValueError, ObsidianStoreError) as failure:
        raise ObsidianStoreError(
            "Collection failed and its failure status could not be saved.", stage="record_failure"
        ) from failure
    if isinstance(error, OSError):
        raise ObsidianStoreError(
            "Cannot read or write the Obsidian export directory.", stage="write"
        ) from error
    raise error


# -- local filesystem -----------------------------------------------------


def _no_links(path):
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise OSError("Obsidian export paths cannot contain symlinks")


def _mkdir(path):
    path = path.absolute()
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise OSError("Obsidian export paths cannot contain symlinks")
        if not current.exists():
            current.mkdir(mode=0o700)
            _sync_directory(current.parent)
        elif not current.is_dir():
            raise OSError("Obsidian export paths must be directories")


@contextmanager
def _open_file(source, relative, flags):
    path = source / relative
    _no_links(path)
    with obsidian._open_directory(path.parent) as parent:
        fd = os.open(
            path.name if parent is not None else path,
            flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0),
            0o600,
            dir_fd=parent,
        )
        with os.fdopen(fd, "rb" if flags == os.O_RDONLY else "r+b") as stream:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or path_of_open_file(stream) != path:
                raise OSError("Export handle is not the selected regular file")
            yield stream


@contextmanager
def _source_lock(source):
    with _open_file(source, ".lock", os.O_CREAT | os.O_RDWR) as stream:
        try:
            if os.name == "nt":
                import msvcrt

                stream.write(b"\0")
                stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ObsidianStoreError(
                "Another collection owns this Obsidian source; retry when it finishes.", stage="lock"
            ) from error
        yield


def _daily_files(source):
    daily = source / "daily"
    _no_links(daily)
    if not daily.exists():
        return []
    found = []

    def failed(error):
        raise error

    for folder, directories, files in os.walk(daily, followlinks=False, onerror=failed):
        for name in directories + files:
            if (Path(folder) / name).is_symlink():
                raise ObsidianStoreError("Linked daily material cannot be recovered safely.", stage="recover")
        for name in files:
            relative = (Path(folder) / name).relative_to(source).as_posix()
            if not DAILY.fullmatch(relative):
                raise ObsidianStoreError(
                    "Unknown file in daily material; preserve it for diagnosis.", stage="recover"
                )
            found.append(relative)
    return found


def _sync_directory(path):
    if os.name == "posix":
        with obsidian._open_directory(path) as fd:
            if fd is not None:
                os.fsync(fd)


def _now():
    return datetime.now(timezone.utc)


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat()
