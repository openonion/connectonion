"""Private, versioned snapshots for resumable ``co ai`` subprocess turns."""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = 2
_LEGACY_SNAPSHOT_VERSION = 1
_TODO_STATUSES = {"pending", "in_progress", "completed"}
_TODO_PRIORITIES = {"high", "medium", "low"}
logger = logging.getLogger(__name__)


class SessionSnapshotError(ValueError):
    """A one-shot session cannot be safely saved or resumed."""


@dataclass(frozen=True)
class SnapshotStorageLimits:
    """Hard bounds for durable one-shot session snapshots."""

    max_sessions: int
    max_total_bytes: int
    max_snapshot_bytes: int


def new_session_id() -> str:
    """Return a canonical, filesystem-safe session ID."""
    return str(uuid.uuid4())


def _canonical_id(session_id: str) -> str:
    try:
        parsed = uuid.UUID(session_id)
    except (AttributeError, TypeError, ValueError):
        raise SessionSnapshotError("Provide a valid session ID from a previous run.") from None
    canonical = str(parsed)
    if session_id != canonical:
        raise SessionSnapshotError("Provide a valid session ID from a previous run.")
    return canonical


def _session_dir(co_dir: Path) -> Path:
    return Path(co_dir) / "ai" / "sessions"


def _session_path(co_dir: Path, canonical_id: str) -> Path:
    return _session_dir(co_dir) / f"{canonical_id}.json"


def _resolved_cwd(cwd: Path | str | None = None) -> str:
    return str((Path.cwd() if cwd is None else Path(cwd)).resolve())


def _snapshot_cwd(
    cwd: Path | str | None,
    virtual_cwd: str | None,
) -> str:
    if virtual_cwd is None:
        return _resolved_cwd(cwd)
    if cwd is not None or virtual_cwd != "/":
        raise SessionSnapshotError("Invalid virtual session working directory.")
    return virtual_cwd


class SessionLease:
    """Exclusive OS-backed ownership that can outlive one function call."""

    def __init__(self, session_id: str, handle: Any) -> None:
        self.session_id = session_id
        self._handle = handle

    @property
    def closed(self) -> bool:
        return self._handle is None

    def close(self) -> None:
        """Release ownership once; repeated shutdown paths are harmless."""
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        handle.close()

    def __enter__(self) -> SessionLease:
        return self

    def __exit__(self, *_exc_info: Any) -> None:
        self.close()


def acquire_session_lease(
    co_dir: Path,
    session_id: str,
    *,
    exclusive_create: bool = False,
) -> SessionLease:
    """Fail fast unless this process can exclusively own ``session_id``."""
    canonical = _canonical_id(session_id)
    directory = _session_dir(co_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(directory, 0o700)
    lock_path = directory / f"{canonical}.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    if exclusive_create:
        flags |= os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError:
        raise SessionSnapshotError(
            f"Session {canonical} lock is unavailable."
        ) from None
    opened_identity: tuple[int, int] | None = None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("session lock is not a regular file")
        opened_identity = (opened.st_dev, opened.st_ino)
        if exclusive_create and 0 in opened_identity:
            opened_identity = None
            raise OSError("session lock identity is unavailable")
        handle = os.fdopen(descriptor, "a+", encoding="utf-8")
        descriptor = -1
        if hasattr(os, "fchmod"):
            os.fchmod(handle.fileno(), 0o600)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        else:
            handle.close()
        if exclusive_create:
            _unlink_created_lock(lock_path, opened_identity)
        raise SessionSnapshotError(
            f"Session {canonical} lock is unavailable."
        ) from None
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        if exclusive_create:
            _unlink_created_lock(lock_path, opened_identity)
        raise SessionSnapshotError(
            f"Session {canonical} is already running in another process."
        ) from None
    return SessionLease(canonical, handle)


def _unlink_created_lock(
    lock_path: Path,
    opened_identity: tuple[int, int] | None,
) -> None:
    """Remove only the lease pathname exclusively created by this attempt."""

    if opened_identity is None or 0 in opened_identity:
        return
    try:
        current = lock_path.lstat()
    except OSError:
        return
    if not stat.S_ISREG(current.st_mode):
        return
    if (
        current.st_dev,
        current.st_ino,
    ) != opened_identity:
        return
    try:
        lock_path.unlink()
    except OSError:
        pass


@contextmanager
def session_lock(co_dir: Path, session_id: str):
    """Fail fast unless this process exclusively owns a resumed turn."""
    lease = acquire_session_lease(co_dir, session_id)
    try:
        yield
    finally:
        lease.close()


def discard_unpublished_session(
    co_dir: Path,
    session_id: str,
    lease: SessionLease,
) -> None:
    """Remove a newly committed session whose ID was never returned to a client."""

    canonical = _canonical_id(session_id)
    try:
        with _snapshot_storage_lock(co_dir):
            directory = _session_dir(co_dir)
            snapshot_path = directory / f"{canonical}.json"
            lock_path = directory / f"{canonical}.lock"
            try:
                snapshot_stat = snapshot_path.lstat()
            except FileNotFoundError:
                pass
            except OSError:
                raise SessionSnapshotError("Session storage is unavailable.") from None
            else:
                if not stat.S_ISREG(snapshot_stat.st_mode):
                    raise SessionSnapshotError("Session storage is unavailable.")
                try:
                    snapshot_path.unlink()
                except OSError:
                    raise SessionSnapshotError("Session storage is unavailable.") from None
            # Keep the per-session lease held until the snapshot is gone. A
            # resume preflight shares the quota lock, so nobody can observe the
            # unpublished file and then acquire ownership between deletion and
            # lease release.
            lease.close()
            try:
                lock_stat = lock_path.lstat()
            except FileNotFoundError:
                return
            except OSError:
                raise SessionSnapshotError("Session storage is unavailable.") from None
            if not stat.S_ISREG(lock_stat.st_mode):
                raise SessionSnapshotError("Session storage is unavailable.")
            try:
                lock_path.unlink()
            except OSError:
                raise SessionSnapshotError("Session storage is unavailable.") from None
    finally:
        # Lock acquisition and validation can fail before the context body.
        # Ownership must never outlive unpublished-session cleanup.
        lease.close()


def save_snapshot(
    co_dir: Path,
    session: dict[str, Any],
    tool_state: dict[str, Any] | None = None,
    *,
    cwd: Path | str | None = None,
    virtual_cwd: str | None = None,
    storage_limits: SnapshotStorageLimits | None = None,
) -> None:
    """Atomically persist one completed Agent turn."""
    session_id = _canonical_id(session.get("session_id"))
    tools = {} if tool_state is None else tool_state
    _validate_tool_state(tools, session_id)
    _validate_session_plan(session, session_id)
    _validate_plan_matches_tools(session, tools, session_id)
    payload = {
        "version": SNAPSHOT_VERSION,
        "cwd": _snapshot_cwd(cwd, virtual_cwd),
        "session": session,
        "tools": tools,
    }
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, UnicodeEncodeError, ValueError) as exc:
        raise SessionSnapshotError(
            f"Session {session_id} cannot be serialized: {exc}"
        ) from None

    if storage_limits is None:
        directory = _session_dir(co_dir)
        _ensure_private_directory(directory)
        _write_snapshot(directory, session_id, encoded)
        return

    _validate_storage_limits(storage_limits)
    directory = prepare_snapshot_storage(co_dir)
    if len(encoded) > storage_limits.max_snapshot_bytes:
        logger.warning(
            "Session snapshot exceeds quota: bytes=%d/%d",
            len(encoded),
            storage_limits.max_snapshot_bytes,
        )
        raise SessionSnapshotError("Session snapshot exceeds the storage limit.")
    with _snapshot_storage_lock(co_dir):
        stored_sessions, stored_bytes, target_bytes, target_counted = (
            _snapshot_storage_usage(
                directory,
                session_id,
                max_sessions=storage_limits.max_sessions,
                max_total_bytes=storage_limits.max_total_bytes,
            )
        )
        candidate_sessions = stored_sessions + (0 if target_counted else 1)
        candidate_bytes = stored_bytes - (target_bytes or 0) + len(encoded)
        if (
            candidate_sessions > storage_limits.max_sessions
            or candidate_bytes > storage_limits.max_total_bytes
        ):
            logger.warning(
                "Session storage quota exceeded: sessions=%d/%d bytes=%d/%d",
                candidate_sessions,
                storage_limits.max_sessions,
                candidate_bytes,
                storage_limits.max_total_bytes,
            )
            raise SessionSnapshotError("Session storage quota exceeded.")
        _write_snapshot(directory, session_id, encoded)


def _write_snapshot(directory: Path, session_id: str, encoded: bytes) -> None:
    """Replace one private snapshot after every fallible check has passed."""

    target = directory / f"{session_id}.json"
    fd, temporary = tempfile.mkstemp(prefix=f".{session_id}.", dir=directory)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(encoded)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def load_snapshot(
    co_dir: Path,
    session_id: str,
    *,
    cwd: Path | str | None = None,
    virtual_cwd: str | None = None,
    storage_limits: SnapshotStorageLimits | None = None,
) -> tuple[dict, dict]:
    """Load and validate the exact snapshot named by ``session_id``."""
    canonical = _canonical_id(session_id)
    path = _session_path(co_dir, canonical)
    if storage_limits is None:
        encoded = _read_snapshot(path, canonical)
    else:
        _validate_storage_limits(storage_limits)
        directory = prepare_snapshot_storage(co_dir)
        with _snapshot_storage_lock(co_dir):
            stored_sessions, stored_bytes, target_bytes, _target_counted = (
                _snapshot_storage_usage(
                    directory,
                    canonical,
                    max_sessions=storage_limits.max_sessions,
                    max_total_bytes=storage_limits.max_total_bytes,
                )
            )
            if target_bytes is None:
                raise SessionSnapshotError(f"Session {canonical} was not found.")
            if (
                stored_sessions > storage_limits.max_sessions
                or stored_bytes > storage_limits.max_total_bytes
                or target_bytes > storage_limits.max_snapshot_bytes
            ):
                raise SessionSnapshotError("Session storage quota exceeded.")
            encoded = _read_snapshot(
                path,
                canonical,
                max_bytes=storage_limits.max_snapshot_bytes,
                require_stable_identity=True,
            )
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionSnapshotError(f"Session {canonical} is unreadable: {exc}") from None

    version = payload.get("version") if isinstance(payload, dict) else None
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version not in {_LEGACY_SNAPSHOT_VERSION, SNAPSHOT_VERSION}
    ):
        raise SessionSnapshotError(
            f"Session {canonical} uses unsupported snapshot version {version}."
        )
    saved_cwd = payload.get("cwd")
    if not isinstance(saved_cwd, str):
        raise SessionSnapshotError(f"Session {canonical} has an invalid working directory.")
    current_cwd = _snapshot_cwd(cwd, virtual_cwd)
    if virtual_cwd is None:
        if not Path(saved_cwd).is_absolute():
            raise SessionSnapshotError(f"Session {canonical} has an invalid working directory.")
        saved_cwd = str(Path(saved_cwd).resolve())
    if os.path.normcase(saved_cwd) != os.path.normcase(current_cwd):
        raise SessionSnapshotError(
            f"Session {canonical} belongs to {saved_cwd}; resume it from that directory."
        )
    session = payload.get("session")
    tools = payload.get("tools", {})
    if not isinstance(session, dict) or not isinstance(tools, dict):
        raise SessionSnapshotError(f"Session {canonical} has an invalid snapshot shape.")
    if session.get("session_id") != canonical:
        raise SessionSnapshotError(f"Session {canonical} has a mismatched ID.")
    if not isinstance(session.get("messages"), list):
        raise SessionSnapshotError(f"Session {canonical} has invalid messages.")
    if not isinstance(session.get("trace"), list):
        raise SessionSnapshotError(f"Session {canonical} has an invalid trace.")
    if not isinstance(session.get("turn"), int):
        raise SessionSnapshotError(f"Session {canonical} has an invalid turn counter.")
    _validate_tool_state(tools, canonical, version=version)
    tools = _migrate_tool_state(tools, version)
    if version == _LEGACY_SNAPSHOT_VERSION:
        session = dict(session)
        session["plan"] = _plan_from_tool_state(tools)
    _validate_session_plan(session, canonical)
    _validate_plan_matches_tools(session, tools, canonical)
    return session, tools


def _ensure_private_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        directory_stat = directory.lstat()
    except OSError as exc:
        raise SessionSnapshotError("Session storage is unavailable.") from exc
    if not stat.S_ISDIR(directory_stat.st_mode) or directory.is_symlink():
        raise SessionSnapshotError("Session storage is unavailable.")
    if os.name != "nt":
        os.chmod(directory, 0o700)


def prepare_snapshot_storage(co_dir: Path) -> Path:
    """Create and validate every controlled directory in a bounded store."""

    root = Path(co_dir)
    _ensure_private_directory(root)
    _ensure_private_directory(root / "ai")
    directory = root / "ai" / "sessions"
    _ensure_private_directory(directory)
    return directory


def _open_regular_lock(path: Path, *, message: str):
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError:
        raise SessionSnapshotError(message) from None
    handle = None
    try:
        handle = os.fdopen(descriptor, "a+b")
        descriptor = -1
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise OSError("lock is not a regular file")
        if hasattr(os, "fchmod"):
            os.fchmod(handle.fileno(), 0o600)
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX)
        return handle
    except OSError:
        if handle is not None:
            handle.close()
        raise SessionSnapshotError(message) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@contextmanager
def _snapshot_storage_lock(co_dir: Path):
    """Serialize principal-wide snapshot accounting across processes."""

    root = Path(co_dir)
    prepare_snapshot_storage(root)
    handle = _open_regular_lock(
        root / "sessions.lock",
        message="Session storage is unavailable.",
    )
    try:
        yield
    finally:
        handle.close()


def _snapshot_storage_usage(
    directory: Path,
    target_session_id: str,
    *,
    max_sessions: int,
    max_total_bytes: int,
) -> tuple[int, int, int | None, bool]:
    """Return exact committed usage and remove only abandoned writer temp files."""

    stored_session_ids: set[str] = set()
    stored_bytes = 0
    target_bytes = None
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                name = entry.name
                if _is_snapshot_temporary(name):
                    entry_stat = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(entry_stat.st_mode):
                        raise OSError("unexpected session snapshot temporary")
                    Path(entry.path).unlink()
                    continue
                suffix = Path(name).suffix
                if suffix not in {".json", ".lock"}:
                    raise OSError("unexpected session storage entry")
                session_id = name[:-5]
                try:
                    canonical = _canonical_id(session_id)
                except SessionSnapshotError:
                    raise OSError("unexpected session storage name") from None
                if canonical != session_id:
                    raise OSError("unexpected session storage name")
                entry_stat = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(entry_stat.st_mode):
                    raise OSError("session storage entry is not a regular file")
                stored_session_ids.add(session_id)
                if len(stored_session_ids) > max_sessions:
                    logger.warning(
                        "Session storage quota exceeded during scan: "
                        "sessions>%d",
                        max_sessions,
                    )
                    raise SessionSnapshotError("Session storage quota exceeded.")
                if suffix == ".json":
                    stored_bytes += entry_stat.st_size
                    if stored_bytes > max_total_bytes:
                        logger.warning(
                            "Session storage quota exceeded during scan: "
                            "bytes>%d",
                            max_total_bytes,
                        )
                        raise SessionSnapshotError("Session storage quota exceeded.")
                    if session_id == target_session_id:
                        target_bytes = entry_stat.st_size
    except SessionSnapshotError:
        raise
    except OSError:
        raise SessionSnapshotError("Session storage is unavailable.") from None
    return (
        len(stored_session_ids),
        stored_bytes,
        target_bytes,
        target_session_id in stored_session_ids,
    )


def acquire_bounded_new_session_lease(
    co_dir: Path,
    session_id: str,
    storage_limits: SnapshotStorageLimits,
) -> SessionLease:
    """Atomically reserve one new network session against principal quota."""

    canonical = _canonical_id(session_id)
    _validate_storage_limits(storage_limits)
    directory = prepare_snapshot_storage(co_dir)
    with _snapshot_storage_lock(co_dir):
        stored_sessions, stored_bytes, _target_bytes, target_counted = (
            _snapshot_storage_usage(
                directory,
                canonical,
                max_sessions=storage_limits.max_sessions,
                max_total_bytes=storage_limits.max_total_bytes,
            )
        )
        if target_counted:
            raise SessionSnapshotError("Session storage is unavailable.")
        if (
            stored_sessions >= storage_limits.max_sessions
            or stored_bytes >= storage_limits.max_total_bytes
        ):
            logger.warning(
                "Session storage quota exceeded during admission: "
                "sessions=%d/%d bytes=%d/%d",
                stored_sessions,
                storage_limits.max_sessions,
                stored_bytes,
                storage_limits.max_total_bytes,
            )
            raise SessionSnapshotError("Session storage quota exceeded.")
        # Creating the canonical lease while the namespace lock is held makes
        # this reservation visible before a competing admission can scan.
        return acquire_session_lease(
            co_dir,
            canonical,
            exclusive_create=True,
        )


def _is_snapshot_temporary(name: str) -> bool:
    if not name.startswith("."):
        return False
    session_id, separator, suffix = name[1:].partition(".")
    if not separator or not suffix:
        return False
    try:
        return _canonical_id(session_id) == session_id
    except SessionSnapshotError:
        return False


def _read_snapshot(
    path: Path,
    session_id: str,
    *,
    max_bytes: int | None = None,
    require_stable_identity: bool = False,
) -> bytes:
    """Read one regular snapshot without following a symbolic link."""

    try:
        before = path.lstat()
    except FileNotFoundError:
        raise SessionSnapshotError(f"Session {session_id} was not found.") from None
    except OSError:
        raise SessionSnapshotError(f"Session {session_id} is unreadable.") from None
    if not stat.S_ISREG(before.st_mode):
        raise SessionSnapshotError(f"Session {session_id} is unreadable.")
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as file:
            opened = os.fstat(file.fileno())
            before_identity = (before.st_dev, before.st_ino)
            opened_identity = (opened.st_dev, opened.st_ino)
            if (
                not stat.S_ISREG(opened.st_mode)
                or before_identity != opened_identity
                or (
                    require_stable_identity
                    and (0 in before_identity or 0 in opened_identity)
                )
            ):
                raise OSError("session snapshot changed during open")
            if max_bytes is not None and opened.st_size > max_bytes:
                raise SessionSnapshotError("Session snapshot exceeds the storage limit.")
            encoded = file.read(None if max_bytes is None else max_bytes + 1)
    except SessionSnapshotError:
        raise
    except OSError:
        raise SessionSnapshotError(f"Session {session_id} is unreadable.") from None
    if max_bytes is not None and len(encoded) > max_bytes:
        raise SessionSnapshotError("Session snapshot exceeds the storage limit.")
    return encoded


def _validate_storage_limits(limits: SnapshotStorageLimits) -> None:
    if (
        isinstance(limits.max_sessions, bool)
        or not isinstance(limits.max_sessions, int)
        or limits.max_sessions <= 0
        or isinstance(limits.max_total_bytes, bool)
        or not isinstance(limits.max_total_bytes, int)
        or limits.max_total_bytes <= 0
        or isinstance(limits.max_snapshot_bytes, bool)
        or not isinstance(limits.max_snapshot_bytes, int)
        or limits.max_snapshot_bytes <= 0
        or limits.max_snapshot_bytes > limits.max_total_bytes
    ):
        raise ValueError("Snapshot storage limits must be positive and consistent.")


def _validate_tool_state(
    state: Any,
    session_id: str,
    *,
    version: int = SNAPSHOT_VERSION,
) -> None:
    """Validate every supported tool snapshot before constructing an Agent."""

    if not isinstance(state, dict) or set(state) - {"todolist"}:
        raise SessionSnapshotError(
            f"Session {session_id} contains unsupported tool state."
        )
    if "todolist" not in state:
        return
    todos = state["todolist"]
    if not isinstance(todos, list):
        raise SessionSnapshotError(
            f"Session {session_id} has invalid TodoList state."
        )
    required = {"content", "status", "active_form"}
    if version == SNAPSHOT_VERSION:
        required.add("priority")
    for item in todos:
        if (
            not isinstance(item, dict)
            or set(item) != required
            or not isinstance(item["content"], str)
            or (version == SNAPSHOT_VERSION and not item["content"])
            or not isinstance(item["status"], str)
            or item["status"] not in _TODO_STATUSES
            or not isinstance(item["active_form"], str)
            or (
                version == SNAPSHOT_VERSION
                and (
                    not isinstance(item["priority"], str)
                    or item["priority"] not in _TODO_PRIORITIES
                )
            )
        ):
            raise SessionSnapshotError(
                f"Session {session_id} has invalid TodoList state."
            )


def _migrate_tool_state(state: dict[str, Any], version: int) -> dict[str, Any]:
    if version != _LEGACY_SNAPSHOT_VERSION or "todolist" not in state:
        return state
    return {
        **state,
        "todolist": [
            {
                **item,
                "content": item["content"] or f"Untitled legacy task {index + 1}",
                "priority": "medium",
            }
            for index, item in enumerate(state["todolist"])
        ],
    }


def _plan_from_tool_state(state: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "content": item["content"],
            "priority": item["priority"],
            "status": item["status"],
        }
        for item in state.get("todolist", [])
    ]


def _validate_session_plan(session: Any, session_id: str) -> None:
    if not isinstance(session, dict) or "plan" not in session:
        return
    plan = session["plan"]
    if not isinstance(plan, list):
        raise SessionSnapshotError(f"Session {session_id} has invalid plan state.")
    for entry in plan:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"content", "priority", "status"}
            or not isinstance(entry["content"], str)
            or not entry["content"]
            or not isinstance(entry["priority"], str)
            or entry["priority"] not in _TODO_PRIORITIES
            or not isinstance(entry["status"], str)
            or entry["status"] not in _TODO_STATUSES
        ):
            raise SessionSnapshotError(
                f"Session {session_id} has invalid plan state."
            )


def _validate_plan_matches_tools(
    session: dict[str, Any],
    tools: dict[str, Any],
    session_id: str,
) -> None:
    if "todolist" not in tools:
        return
    if session.get("plan") != _plan_from_tool_state(tools):
        raise SessionSnapshotError(
            f"Session {session_id} has inconsistent plan and TodoList state."
        )


def capture_tool_state(agent) -> dict[str, Any]:
    """Capture only tool state with an explicit, private snapshot contract."""
    tools = getattr(agent, "tools", None)
    get_instance = getattr(tools, "get_instance", None)
    todo = get_instance("todolist") if callable(get_instance) else None
    return {"todolist": todo._dump_state()} if todo is not None else {}


def restore_tool_state(agent, state: dict[str, Any]) -> None:
    """Restore supported tool state without deserializing arbitrary objects."""
    if "todolist" not in state:
        return
    tools = getattr(agent, "tools", None)
    get_instance = getattr(tools, "get_instance", None)
    todo = get_instance("todolist") if callable(get_instance) else None
    if todo is None:
        raise SessionSnapshotError("This co ai build cannot restore TodoList state.")
    todo._load_state(state["todolist"])
