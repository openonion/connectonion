"""Private, versioned snapshots for resumable ``co ai`` subprocess turns."""

import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = 1


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


def _resolved_cwd() -> str:
    return str(Path.cwd().resolve())


@contextmanager
def session_lock(co_dir: Path, session_id: str):
    """Fail fast unless this process exclusively owns a resumed turn."""
    canonical = _canonical_id(session_id)
    directory = _session_dir(co_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(directory, 0o700)
    lock_path = directory / f"{canonical}.lock"
    handle = lock_path.open("a+", encoding="utf-8")
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
    try:
        yield
    finally:
        handle.close()


def save_snapshot(
    co_dir: Path,
    session: dict[str, Any],
    tool_state: dict[str, Any] | None = None,
) -> None:
    """Atomically persist one completed Agent turn."""
    session_id = _canonical_id(session.get("session_id"))
    payload = {
        "version": SNAPSHOT_VERSION,
        "cwd": _resolved_cwd(),
        "session": session,
        "tools": tool_state or {},
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
        if os.name != "nt":
            os.chmod(target, 0o600)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_snapshot(co_dir: Path, session_id: str) -> tuple[dict, dict]:
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
    if version != SNAPSHOT_VERSION:
        raise SessionSnapshotError(
            f"Session {canonical} uses unsupported snapshot version {version}."
        )
    saved_cwd = payload.get("cwd")
    if not isinstance(saved_cwd, str) or not Path(saved_cwd).is_absolute():
        raise SessionSnapshotError(f"Session {canonical} has an invalid working directory.")
    current_cwd = _resolved_cwd()
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
    return session, tools


def capture_tool_state(agent) -> dict[str, Any]:
    """Capture only tool state with an explicit, private snapshot contract."""
    todo = agent.tools.get_instance("todolist")
    return {"todolist": todo._dump_state()} if todo is not None else {}


def restore_tool_state(agent, state: dict[str, Any]) -> None:
    """Restore supported tool state without deserializing arbitrary objects."""
    if "todolist" not in state:
        return
    todo = agent.tools.get_instance("todolist")
    if todo is None:
        raise SessionSnapshotError("This co ai build cannot restore TodoList state.")
    todo._load_state(state["todolist"])
