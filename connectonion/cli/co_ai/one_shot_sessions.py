"""Private, versioned snapshots for resumable ``co ai`` subprocess turns."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = 2
_LEGACY_SNAPSHOT_VERSION = 1
_TODO_STATUSES = {"pending", "in_progress", "completed"}
_TODO_PRIORITIES = {"high", "medium", "low"}


class SessionSnapshotError(ValueError):
    """A one-shot session cannot be safely saved or resumed."""


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


def acquire_session_lease(co_dir: Path, session_id: str) -> SessionLease:
    """Fail fast unless this process can exclusively own ``session_id``."""
    canonical = _canonical_id(session_id)
    directory = _session_dir(co_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(directory, 0o700)
    lock_path = directory / f"{canonical}.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError:
        raise SessionSnapshotError(
            f"Session {canonical} lock is unavailable."
        ) from None
    try:
        handle = os.fdopen(descriptor, "a+", encoding="utf-8")
        descriptor = -1
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise OSError("session lock is not a regular file")
        if hasattr(os, "fchmod"):
            os.fchmod(handle.fileno(), 0o600)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        else:
            handle.close()
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
        raise SessionSnapshotError(
            f"Session {canonical} is already running in another process."
        ) from None
    return SessionLease(canonical, handle)


@contextmanager
def session_lock(co_dir: Path, session_id: str):
    """Fail fast unless this process exclusively owns a resumed turn."""
    lease = acquire_session_lease(co_dir, session_id)
    try:
        yield
    finally:
        lease.close()


def save_snapshot(
    co_dir: Path,
    session: dict[str, Any],
    tool_state: dict[str, Any] | None = None,
    *,
    cwd: Path | str | None = None,
) -> None:
    """Atomically persist one completed Agent turn."""
    session_id = _canonical_id(session.get("session_id"))
    tools = {} if tool_state is None else tool_state
    _validate_tool_state(tools, session_id)
    _validate_session_plan(session, session_id)
    payload = {
        "version": SNAPSHOT_VERSION,
        "cwd": _resolved_cwd(cwd),
        "session": session,
        "tools": tools,
    }
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise SessionSnapshotError(
            f"Session {session_id} cannot be serialized: {exc}"
        ) from None

    directory = _session_dir(co_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(directory, 0o700)
    target = _session_path(co_dir, session_id)
    fd, temporary = tempfile.mkstemp(prefix=f".{session_id}.", dir=directory)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
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
) -> tuple[dict, dict]:
    """Load and validate the exact snapshot named by ``session_id``."""
    canonical = _canonical_id(session_id)
    path = _session_path(co_dir, canonical)
    if not path.is_file():
        raise SessionSnapshotError(f"Session {canonical} was not found.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
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
    if not isinstance(saved_cwd, str) or not Path(saved_cwd).is_absolute():
        raise SessionSnapshotError(f"Session {canonical} has an invalid working directory.")
    current_cwd = _resolved_cwd(cwd)
    if os.path.normcase(str(Path(saved_cwd).resolve())) != os.path.normcase(current_cwd):
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
    if version == _LEGACY_SNAPSHOT_VERSION and "plan" not in session:
        session = dict(session)
        session["plan"] = _plan_from_tool_state(tools)
    _validate_session_plan(session, canonical)
    return session, tools


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
            or not item["content"]
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
            {**item, "priority": "medium"}
            for item in state["todolist"]
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
