"""
Purpose: Incremental Asana collection for co rem — the selected projects' changed tasks, each saved with its details and every story, as one daily JSONL line, and the committed index that readers use
LLM-Note:
  Dependencies: imports from [json, os, re, hashlib, datetime, pathlib, contextlib, useful_tools/asana.py (Asana, AsanaError)] | imported by [rem/asana.py (co rem sync)] | tested by [tests/unit/test_asana_export.py]
  Data flow: sync_tasks(client, S, project_gids) → lock S/.lock → read and validate S/state.json (daily material without a state.json stops here) → check the account → bind a new folder with a first state.json → cut every daily file back to its committed length, refusing symbolic links → for each project list_tasks(modified_since = checkpoint - overlap, or everything the first time) → get_task + list_stories per candidate → compare the content version and the selected projects it belongs to with the last committed record → append one JSON line per changed task to S/daily/YYYY/MM/DD.jsonl (UTC day) → atomically replace state.json (committed_bytes, latest, checkpoints) | export_status(S) reads state.json only | latest_snapshots(S, account, projects) reads the state index only | load_snapshots(S, selected) reads only the chosen committed byte ranges
  State/Effects: writes only under S (the caller passes inbox.store.default_home("asana")): state.json, .lock, daily/; never writes to Asana, never imports CLI or REM, never calls a model | readers never write or create directories
  Integration: exposes sync_tasks, export_status, latest_snapshots, load_snapshots, load_change, AsanaStoreError | records keep Asana's own task and story fields; change_id = asana:<account_gid>:<task_gid>:<daily relative path>:<byte offset> is unique because it names a committed position
  Errors: ValueError for an empty or non-numeric project selection, before anything is read | AsanaError from Asana passes through unchanged | AsanaStoreError(message, stage) for the lock, a damaged state.json, a daily file shorter than committed, another account, or a local write; a failure before state.json is replaced keeps the old checkpoints and records last_failure (not for a damaged state or daily folder; if recording also fails, the error says so); stage="durability" with committed=True means state.json was already replaced and only its sync to disk failed, so the new progress is in place | a read of a missing or linked daily file is AsanaStoreError(stage="read")
"""

import hashlib
import json
import os
import re
import sys
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .asana import AsanaError

STATE = "state.json"
LOCK = ".lock"
DAILY = "daily"
SCHEMA = "asana-task-snapshot/1"
STATE_VERSION = 1
# Re-read this much before each project's checkpoint: clocks differ a little, and
# Asana may index a change after the moment it happened. Duplicates are dropped by
# comparing content versions, so a wider window costs reads, never extra records.
OVERLAP = timedelta(minutes=5)
FAILURE_TEXT = 500                      # characters of an error message kept in last_failure

_GID = re.compile(r"[0-9]{1,64}")
_DAILY_FILE = re.compile(r"daily/[0-9]{4}/[0-9]{2}/[0-9]{2}\.jsonl")
_VERSION = re.compile(r"sha256:[0-9a-f]{64}")
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class AsanaStoreError(Exception):
    """A local problem with the Asana source folder: its lock, state.json, a daily file or a write.

    `stage` says where (lock, state, account, truncate, write, durability,
    record_failure, read); Asana's own errors stay AsanaError. `committed` is
    True only for durability: state.json was already replaced, so the new
    progress is in place even though the call failed.
    """

    def __init__(self, message: str, *, stage: str, committed: bool = False):
        super().__init__(message)
        self.stage = stage
        self.committed = committed


# -- public ----------------------------------------------------------------

def sync_tasks(client, source_dir: Path, project_gids: list[str]) -> dict:
    """Collect every changed task of the selected projects, with details and stories; returns what happened.

    One line per task whose content changed since the last committed version;
    nothing is appended when nothing changed. Checkpoints and committed bytes
    move only after everything was read and written; on a failure they stay,
    last_failure is recorded, and the error is raised.
    """
    selected = _selection(project_gids)
    source_dir = Path(source_dir)
    source_dir.mkdir(parents=True, exist_ok=True)
    with _source_lock(source_dir):
        state = _load_state(source_dir)
        if not (source_dir / STATE).exists() and _has_material(source_dir):
            # Saved material without its index: never treat it as a first run and cut it away.
            raise AsanaStoreError(f"{source_dir / DAILY} holds saved material but {STATE} is missing; "
                                  "nothing was changed. Restore state.json or move the folder aside", stage="state")
        try:
            # Whose folder this is comes first: nothing on disk is touched for another account.
            account = _account(client, state)
            if not (source_dir / STATE).exists():
                # Bind the folder before the first line is written, so material can never
                # exist without a state.json (a crash in the first run stays recoverable).
                state = {**state, "account_gid": account}
                _commit_state(source_dir, state)
            _truncate_uncommitted(source_dir, state)
            started = _now()
            candidates = _collect_candidates(client, selected, state)
            changes = []
            for candidate in candidates:
                task = client.get_task(candidate["gid"])
                stories = client.list_stories(candidate["gid"])
                version = _content_version(task, stories)
                owners = _owning_projects(task, candidate["project_gids"], selected)
                previous = state["latest"].get(candidate["gid"])
                if (previous is not None and previous["content_version"] == version
                        and set(owners) == set(previous["project_gids"]) & set(selected)):
                    continue        # same content, same selected projects: a duplicate
                changes.append({"task": task, "stories": stories, "content_version": version,
                                "project_gids": owners})
            new_state = _append_changes(source_dir, changes, state, account=account, now=started) if changes \
                else deepcopy(state)
            new_state["account_gid"] = account
            new_state["project_gids"] = selected
            for project in selected:
                new_state["checkpoints"][project] = _iso(started)
            new_state["last_success_at"] = _iso(_now())
            new_state["last_failure"] = None
            _commit_state(source_dir, new_state)
        except (AsanaError, AsanaStoreError, OSError) as error:
            _fail(source_dir, error)
        return {"account_gid": account, "project_gids": selected, "scanned_tasks": len(candidates),
                "changed_tasks": len(changes), "appended_records": len(changes),
                "checkpoints": {p: new_state["checkpoints"][p] for p in selected},
                "last_success_at": new_state["last_success_at"]}


def export_status(source_dir: Path) -> dict:
    """What has been collected, from state.json alone: no network, no daily file, nothing written."""
    path = Path(source_dir) / STATE
    if not path.exists():
        return {"initialized": False, "account_gid": None, "project_gids": [], "checkpoints": {},
                "last_success_at": None, "last_failure": None, "record_count": 0}
    state = _load_state(Path(source_dir))
    return {"initialized": state["last_success_at"] is not None, "account_gid": state["account_gid"],
            "project_gids": list(state["project_gids"]), "checkpoints": dict(state["checkpoints"]),
            "last_success_at": state["last_success_at"], "last_failure": deepcopy(state["last_failure"]),
            "record_count": state["record_count"]}


def latest_snapshots(source_dir: Path, *, account_gid: str, project_gids: list[str]) -> list[dict]:
    """The newest committed snapshot of each task in the selected projects, from the state index only.

    Not initialized gives [] (export_status tells "never collected" from
    "nothing there"). Oldest collection first, then task gid.
    """
    selected = set(_selection(project_gids))
    path = Path(source_dir) / STATE
    if not path.exists():
        return []
    state = _load_state(Path(source_dir))
    if state["account_gid"] is not None and state["account_gid"] != account_gid:
        raise AsanaStoreError(f"The saved Asana material belongs to account {state['account_gid']}, "
                              f"not {account_gid}", stage="account")
    found = []
    for task_gid, entry in state["latest"].items():
        if not selected.intersection(entry["project_gids"]):
            continue
        locator = _checked_locator(entry["locator"], state)
        found.append({"change_id": _change_id(state["account_gid"], task_gid, locator),
                      "task_gid": task_gid, "project_gids": list(entry["project_gids"]),
                      "content_version": entry["content_version"], "collected_at": entry["collected_at"],
                      "locator": locator})
    return sorted(found, key=lambda item: (item["collected_at"], item["task_gid"]))


def load_snapshots(source_dir: Path, selected: list[dict]) -> list[dict]:
    """Read only the chosen snapshots (items from latest_snapshots), inside the committed bytes.

    Returns {change_id, task, stories, collected_at, project_gids} per item,
    in the given order. A locator past the committed end, a line that is not
    one JSON record, or a record for another task or change is an error.
    """
    source_dir = Path(source_dir)
    state = _load_state(source_dir)
    loaded = []
    for item in selected:
        if not isinstance(item, dict):
            raise AsanaStoreError(f"Not a snapshot from latest_snapshots: {item!r}", stage="read")
        locator = _checked_locator(item.get("locator"), state)
        try:
            _no_links(source_dir, locator["file"])
            fd = os.open(source_dir / locator["file"], os.O_RDONLY | _NOFOLLOW)
            with os.fdopen(fd, "rb") as handle:
                handle.seek(locator["offset"])
                raw = handle.read(locator["length"])
        except OSError as error:
            raise AsanaStoreError(f"Cannot read {locator['file']}: {error.strerror or error}", stage="read") from None
        if len(raw) != locator["length"]:
            raise AsanaStoreError(f"{locator['file']} ends before byte {locator['offset'] + locator['length']}",
                                  stage="read")
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise AsanaStoreError(f"{locator['file']} at byte {locator['offset']} is not one JSON record",
                                  stage="read") from None
        if (not isinstance(record, dict) or record.get("change_id") != item.get("change_id")
                or record.get("task_gid") != item.get("task_gid")
                or not isinstance(record.get("task"), dict) or record["task"].get("gid") != item.get("task_gid")):
            raise AsanaStoreError(f"{locator['file']} at byte {locator['offset']} is not the saved snapshot of "
                                  f"task {item.get('task_gid')}", stage="read")
        loaded.append({"change_id": record["change_id"], "task": record["task"], "stories": record["stories"],
                       "collected_at": record["collected_at"], "project_gids": record["project_gids"]})
    return loaded


_CHANGE_ID = re.compile(r"asana:([0-9]{1,64}):([0-9]{1,64}):(daily/[0-9]{4}/[0-9]{2}/[0-9]{2}\.jsonl):([0-9]{1,20})")
# One saved line is one task with its stories; a line longer than this is not one snapshot.
MAX_RECORD_BYTES = 8 * 1024 * 1024


def load_change(source_dir: Path, change_id: str) -> dict | None:
    """The one snapshot a change_id names, in that version, not necessarily the newest.

    A page cites the version it was written from; a later sync may have saved
    a newer one, and the citation still means the older words. Read only inside
    the committed bytes, never through a link, and only when the line there is
    exactly that change: another account, a position past what was committed or
    a different record gives None. Same shape as load_snapshots' items.
    """
    match = _CHANGE_ID.fullmatch(change_id or "")
    if not match:
        return None
    account, task_gid, relative, offset = match.group(1), match.group(2), match.group(3), int(match.group(4))
    source_dir = Path(source_dir)
    if not (source_dir / STATE).exists():
        return None
    state = _load_state(source_dir)
    if state["account_gid"] != account:
        return None
    committed = state["committed_bytes"].get(relative, 0)
    if offset >= committed:
        return None
    try:
        _no_links(source_dir, relative)
        fd = os.open(source_dir / relative, os.O_RDONLY | _NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            handle.seek(offset)
            chunk = handle.read(min(committed - offset, MAX_RECORD_BYTES + 1))
    except OSError as error:
        raise AsanaStoreError(f"Cannot read {relative}: {error.strerror or error}", stage="read") from None
    if offset and not _starts_line(source_dir / relative, offset):
        return None
    end = chunk.find(b"\n")
    if end <= 0:
        return None
    try:
        record = json.loads(chunk[:end].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if (not isinstance(record, dict) or record.get("change_id") != change_id
            or record.get("task_gid") != task_gid or not isinstance(record.get("task"), dict)
            or record["task"].get("gid") != task_gid):
        return None
    return {"change_id": record["change_id"], "task": record["task"], "stories": record.get("stories") or [],
            "collected_at": record.get("collected_at"), "project_gids": list(record.get("project_gids") or [])}


def _starts_line(path: Path, offset: int) -> bool:
    """A cited offset is the start of a line: the byte before it is a newline."""
    fd = os.open(path, os.O_RDONLY | _NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        handle.seek(offset - 1)
        return handle.read(1) == b"\n"


# -- the source folder ------------------------------------------------------

@contextmanager
def _source_lock(source_dir: Path):
    """One writer per source folder; a second sync fails at once instead of interleaving lines."""
    fd = os.open(source_dir / LOCK, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise AsanaStoreError("Another Asana collection is writing this folder; try again when it ends",
                                  stage="lock") from None
        yield
    finally:
        os.close(fd)


def _empty_state() -> dict:
    return {"version": STATE_VERSION, "account_gid": None, "project_gids": [], "checkpoints": {},
            "committed_bytes": {}, "latest": {}, "record_count": 0,
            "last_success_at": None, "last_failure": None}


def _load_state(source_dir: Path) -> dict:
    """state.json as saved, or a fresh state when there is none; a damaged one is an error, never a reset."""
    path = source_dir / STATE
    if not path.exists():
        return _empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise AsanaStoreError(f"{path} cannot be read as JSON; it was left as it is", stage="state") from None
    if not _is_state(state):
        raise AsanaStoreError(f"{path} is not an Asana source state this version understands; "
                              "it was left as it is", stage="state")
    return state


def _is_state(state) -> bool:
    """Every field state.json may hold, checked before any of it is used: gids, times, locators, counts."""
    if not (isinstance(state, dict) and state.get("version") == STATE_VERSION
            and set(_empty_state()) <= set(state)):
        return False
    count = lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 0  # noqa: E731
    gid = lambda v: isinstance(v, str) and _GID.fullmatch(v) is not None  # noqa: E731
    gids = lambda v: isinstance(v, list) and all(gid(x) for x in v)  # noqa: E731
    committed = state["committed_bytes"]
    if not (isinstance(committed, dict)
            and all(isinstance(k, str) and _DAILY_FILE.fullmatch(k) and count(v) for k, v in committed.items())):
        return False

    def entry_ok(task_gid, entry):
        if not (gid(task_gid) and isinstance(entry, dict) and isinstance(entry.get("content_version"), str)
                and _VERSION.fullmatch(entry["content_version"]) and _is_time(entry.get("collected_at"))
                and gids(entry.get("project_gids"))):
            return False
        try:
            _checked_locator(entry.get("locator"), state)
        except AsanaStoreError:
            return False
        return True

    failure = state["last_failure"]
    return ((state["account_gid"] is None or gid(state["account_gid"])) and gids(state["project_gids"])
            and isinstance(state["checkpoints"], dict)
            and all(gid(k) and _is_time(v) for k, v in state["checkpoints"].items())
            and isinstance(state["latest"], dict) and all(entry_ok(k, v) for k, v in state["latest"].items())
            and count(state["record_count"])
            and (state["last_success_at"] is None or _is_time(state["last_success_at"]))
            and (failure is None or (isinstance(failure, dict) and _is_time(failure.get("at"))
                                     and isinstance(failure.get("stage"), str)
                                     and isinstance(failure.get("message"), str))))


def _is_time(value) -> bool:
    """An ISO time with its zone, as this module writes them."""
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _no_links(source_dir: Path, relative: str) -> None:
    """No part of S/<relative> below S may be a symbolic link."""
    path = source_dir
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise OSError(f"{path} is a symbolic link")


def _truncate_uncommitted(source_dir: Path, state: dict) -> None:
    """Cut every daily file back to its committed length; a file not in the state is cut to 0.

    What a crash left after the committed end (half a line, half a batch, or a
    whole batch whose state.json was never replaced) was never visible to a
    reader, so cutting it loses nothing. A file shorter than committed is damage.
    """
    present = _daily_files(source_dir)
    for relative, committed in state["committed_bytes"].items():
        if committed and relative not in present:
            raise AsanaStoreError(f"{relative} is missing but {committed} bytes of it were committed", stage="truncate")
    for relative, path in present.items():
        committed = state["committed_bytes"].get(relative, 0)
        try:
            fd = os.open(path, os.O_RDWR | _NOFOLLOW)
        except OSError as error:
            raise AsanaStoreError(f"Cannot open {relative}: {error.strerror or error}", stage="truncate") from None
        try:
            size = os.fstat(fd).st_size
            if size < committed:
                raise AsanaStoreError(f"{relative} is shorter ({size} bytes) than what was committed ({committed})",
                                      stage="truncate")
            if size > committed:
                os.ftruncate(fd, committed)
                os.fsync(fd)
        finally:
            os.close(fd)


def _daily_files(source_dir: Path) -> dict[str, Path]:
    """Every .jsonl under S/daily, refusing any symbolic link or path that leaves S.

    Recovery cuts files, so it must only ever touch regular files inside the
    source folder: a link (to a file or a folder) is an error, not something to follow.
    """
    daily = source_dir / DAILY
    if daily.is_symlink():
        raise AsanaStoreError(f"{daily} is a symbolic link; refusing to recover through it", stage="truncate")
    if not daily.exists():
        return {}
    root = source_dir.resolve()
    found = {}
    for folder, dirs, files in os.walk(daily, followlinks=False):
        for name in dirs + files:
            path = Path(folder) / name
            if path.is_symlink():
                raise AsanaStoreError(f"{path} is a symbolic link; refusing to recover through it", stage="truncate")
        for name in files:
            path = Path(folder) / name
            if not path.name.endswith(".jsonl"):
                continue
            if not path.resolve().is_relative_to(root) or not path.is_file():
                raise AsanaStoreError(f"{path} is not a regular file inside {source_dir}", stage="truncate")
            found[path.relative_to(source_dir).as_posix()] = path
    return found


def _has_material(source_dir: Path) -> bool:
    """Whether S/daily holds anything at all (a file, a link or a folder)."""
    daily = source_dir / DAILY
    return daily.is_symlink() or (daily.exists() and any(daily.iterdir()))


def _append_changes(source_dir: Path, changes: list[dict], state: dict, *, account: str, now: datetime) -> dict:
    """Append one line per change to today's file after its committed end; returns the new state, not yet committed."""
    relative = f"{DAILY}/{now:%Y/%m/%d}.jsonl"
    path = source_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    new_state = deepcopy(state)
    offset = new_state["committed_bytes"].get(relative, 0)
    collected_at = _iso(now)
    try:
        _no_links(source_dir, relative)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | _NOFOLLOW, 0o600)
        with os.fdopen(fd, "ab") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() != offset:
                raise AsanaStoreError(f"{relative} does not end where it was committed", stage="write")
            for change in changes:
                task_gid = change["task"]["gid"]
                locator = {"file": relative, "offset": offset}
                record = {"schema": SCHEMA, "change_id": None, "account_gid": account, "task_gid": task_gid,
                          "project_gids": change["project_gids"], "content_version": change["content_version"],
                          "collected_at": collected_at, "task": change["task"], "stories": change["stories"]}
                record["change_id"] = _change_id(account, task_gid, {**locator, "length": 0})
                line = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                handle.write(line + b"\n")
                locator["length"] = len(line)
                new_state["latest"][task_gid] = {"content_version": change["content_version"],
                                                 "collected_at": collected_at,
                                                 "project_gids": change["project_gids"], "locator": locator}
                offset += len(line) + 1
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except OSError as error:
        raise AsanaStoreError(f"Could not write {relative}: {error.strerror or error}", stage="write") from None
    new_state["committed_bytes"][relative] = offset
    new_state["record_count"] += len(changes)
    return new_state


def _commit_state(source_dir: Path, state: dict) -> None:
    """Replace state.json in one step; only now do the new lines become visible to readers."""
    temporary = source_dir / f".{STATE}.tmp"
    target = source_dir / STATE
    if target.is_symlink():
        raise AsanaStoreError(f"{target} is a symbolic link; it is never written through", stage="state")
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError as error:
        # Not replaced: the previous state.json, and every reader's view, is unchanged.
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise AsanaStoreError(f"Could not save {STATE}: {error.strerror or error}", stage="write") from None
    try:
        _sync_directory(source_dir)
    except OSError as error:
        # Replaced but not confirmed durable: the new progress is visible now and may or
        # may not survive a power loss. Neither "unchanged" nor a rollback is true here.
        raise AsanaStoreError(f"{STATE} was replaced, but saving it to disk could not be confirmed "
                              f"({error.strerror or error}); the new progress is in place now and may be lost "
                              "after a crash. Check co rem sources before collecting again",
                              stage="durability", committed=True) from None


def _record_failure(source_dir: Path, *, stage: str, message: str) -> None:
    """Keep the last success and every checkpoint; only last_failure changes."""
    state = _load_state(source_dir)
    state["last_failure"] = {"at": _iso(_now()), "stage": stage, "message": message[:FAILURE_TEXT]}
    _commit_state(source_dir, state)


def _fail(source_dir: Path, error: Exception):
    """Record why a collection stopped, then raise it; say so when even that could not be saved."""
    if isinstance(error, OSError) and not isinstance(error, AsanaStoreError):
        error = AsanaStoreError(f"Local file error: {error.strerror or error}", stage="write")
    stage = getattr(error, "stage", None) or ("asana" if isinstance(error, AsanaError) else "write")
    if stage in ("state", "truncate") or getattr(error, "committed", False):
        # A damaged state.json or daily folder cannot safely take one more write; and a
        # state already replaced by this run must not be overwritten with a failure.
        raise error
    try:
        _record_failure(source_dir, stage=stage, message=str(error))
    except (AsanaStoreError, OSError) as unsaved:
        raise AsanaStoreError(f"{error} (the failure could not be recorded either: {unsaved})",
                              stage="record_failure") from error
    raise error


# -- Asana ------------------------------------------------------------------

def _account(client, state: dict) -> str:
    """The token's account; material saved for another account is never mixed in."""
    gid = client.get_user()["gid"]
    if state["account_gid"] is not None and state["account_gid"] != gid:
        raise AsanaStoreError(f"This folder holds material for Asana account {state['account_gid']}, "
                              f"but the token acts as {gid}", stage="account")
    return gid


def _collect_candidates(client, project_gids: list[str], state: dict) -> list[dict]:
    """Every task changed since each project's checkpoint (all of a new project's tasks), once each.

    Completed tasks are included: completing a task is a change. A project
    added to the selection has no checkpoint, so its whole current list is read.
    """
    found: dict[str, list[str]] = {}
    for project in project_gids:
        checkpoint = state["checkpoints"].get(project) if state["account_gid"] is not None else None
        since = _parse(checkpoint) - OVERLAP if checkpoint else None
        for task in client.list_tasks(project, modified_since=since):
            found.setdefault(task["gid"], [])
            if project not in found[task["gid"]]:
                found[task["gid"]].append(project)
    return [{"gid": gid, "project_gids": projects} for gid, projects in found.items()]


def _owning_projects(task: dict, listed_in: list[str], selected: list[str]) -> list[str]:
    """The selected projects this task belongs to now: its own projects field, plus where it was listed."""
    own = {p.get("gid") for p in task.get("projects") or [] if isinstance(p, dict)}
    return [p for p in selected if p in own or p in listed_in]


def _content_version(task: dict, stories: list[dict]) -> str:
    """A digest of the task and its stories; the order Asana happens to send them in does not count.

    Computed on a normalised copy only (the saved record keeps Asana's own
    order): stories by time then gid, and every list of gid records in the task
    (projects, followers, custom_fields, memberships, tags) by gid, since those
    are sets. Key order never counts either.
    """
    ordered = sorted((_unordered(s) for s in stories), key=lambda s: (str(s.get("created_at")), str(s.get("gid"))))
    text = json.dumps({"task": _unordered(task), "stories": ordered}, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _unordered(value):
    """A copy in which every list made only of records with a gid is sorted by gid; other lists keep their order."""
    if isinstance(value, dict):
        return {key: _unordered(item) for key, item in value.items()}
    if isinstance(value, list):
        items = [_unordered(item) for item in value]
        if items and all(isinstance(item, dict) and isinstance(item.get("gid"), str) for item in items):
            return sorted(items, key=lambda item: (item["gid"], json.dumps(item, sort_keys=True, ensure_ascii=False)))
        return items
    return value


# -- small helpers ------------------------------------------------------------

def _selection(project_gids) -> list[str]:
    if isinstance(project_gids, str) or not isinstance(project_gids, (list, tuple)):
        raise ValueError("Give the selected Asana project gids as a list")
    selected = []
    for gid in project_gids:
        if not isinstance(gid, str) or not _GID.fullmatch(gid):
            raise ValueError(f"Not an Asana project gid: {gid!r}")
        if gid not in selected:
            selected.append(gid)
    if not selected:
        raise ValueError("Select at least one Asana project")
    return selected


def _checked_locator(locator, state: dict) -> dict:
    """A locator that names a daily file under the source folder and stays inside its committed bytes."""
    if not (isinstance(locator, dict) and isinstance(locator.get("file"), str)
            and _DAILY_FILE.fullmatch(locator["file"])
            and all(isinstance(locator.get(k), int) and not isinstance(locator.get(k), bool) for k in ("offset", "length"))
            and locator["offset"] >= 0 and locator["length"] > 0):
        raise AsanaStoreError(f"Not a saved Asana snapshot location: {locator!r}", stage="read")
    committed = state["committed_bytes"].get(locator["file"], 0)
    if locator["offset"] + locator["length"] + 1 > committed:
        raise AsanaStoreError(f"{locator['file']} at byte {locator['offset']} is past what was committed",
                              stage="read")
    return {"file": locator["file"], "offset": locator["offset"], "length": locator["length"]}


def _change_id(account: str, task_gid: str, locator: dict) -> str:
    return f"asana:{account}:{task_gid}:{locator['file']}:{locator['offset']}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _sync_directory(path: Path) -> None:
    """A new file's name is durable only when its directory is synced (POSIX)."""
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
