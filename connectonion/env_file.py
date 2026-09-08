"""Serialized, atomic updates to the existing dotenv store."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import time

from .environment import EnvironmentError, parse_env_file


@contextmanager
def env_lock(path: Path, timeout: float = 30.0):
    """Serialize readers that refresh and writers, including separate CLI processes."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "a+b") as lock:
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    lock.seek(0)
                    if not lock.read(1):
                        lock.write(b"\0")
                        lock.flush()
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, PermissionError):
                if time.monotonic() >= deadline:
                    raise EnvironmentError("Credential file is busy. Next: co status") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def _encode(value: str) -> str:
    if not value or any(char.isspace() or char in "'\"\\#$" for char in value):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_env_unlocked(path: Path, updates: dict, *, strip_prefix: str | None = None,
                       initial_comments: str = "", remove: frozenset | set = frozenset()) -> None:
    """Replace a complete file atomically; callers must hold env_lock(path).

    `remove` names keys to drop. A broken file is never rewritten: the parse
    error names the line, and rewriting around it would silently drop whatever
    that line was meant to say.
    """
    updates = {key: str(value) for key, value in updates.items() if value is not None}
    lines, found = ([] if path.exists() or not initial_comments else [initial_comments]), set()
    if path.exists():
        bindings = parse_env_file(path)
        for item in bindings:
            if strip_prefix and item.key and item.key.startswith(strip_prefix):
                continue
            if item.key in remove:
                continue
            if item.key in updates:
                if item.key not in found:
                    lines.append(f"{item.key}={_encode(updates[item.key])}\n")
                    found.add(item.key)
            else:
                lines.append(item.original.string)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.extend(f"{key}={_encode(value)}\n" for key, value in updates.items() if key not in found)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("".join(lines))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def upsert_env(path: Path, updates: dict, *, strip_prefix: str | None = None,
               initial_comments: str = "", remove: frozenset | set = frozenset()) -> None:
    """Preserve unrelated settings, serialize updates and replace with mode 0600."""
    path = Path(path).resolve()
    with env_lock(path):
        write_env_unlocked(path, updates, strip_prefix=strip_prefix,
                           initial_comments=initial_comments, remove=remove)
