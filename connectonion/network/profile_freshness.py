"""Durable monotonic state for publisher profile attestations.

The relay is not a freshness authority. Publishers and subscribers therefore
keep small local watermarks and only use the relay to transport signed values.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

MAX_PROFILE_REVISION = (1 << 63) - 1


def validate_revision(value) -> int:
    """Return a valid signed profile revision or raise a useful error."""
    if type(value) is not int or value <= 0 or value > MAX_PROFILE_REVISION:
        raise ValueError("publisher profile revision must be a positive 64-bit integer")
    return value


def read_state(path: Path) -> dict | None:
    """Read one watermark. Missing is first install; malformed fails closed."""
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"profile freshness state is unreadable: {path}; restore it before syncing"
        ) from exc
    if not isinstance(state, dict):
        raise ValueError(f"profile freshness state is invalid: {path}")
    validate_revision(state.get("revision"))
    signature = state.get("signature")
    if signature is not None and not isinstance(signature, str):
        raise ValueError(f"profile freshness state is invalid: {path}")
    return state


def write_state(path: Path, revision: int, signature: str | None = None) -> None:
    """Atomically advance a watermark without ever writing a lower value."""
    revision = validate_revision(revision)
    current = read_state(path)
    if current and current["revision"] > revision:
        raise ValueError("refusing to lower the local profile revision watermark")

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"revision": revision}
    if signature is not None:
        payload["signature"] = signature

    fd, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def next_revision(path: Path) -> int:
    """Use wall-clock nanoseconds as a cross-device monotonic candidate."""
    current = read_state(path)
    previous = current["revision"] if current else 0
    return validate_revision(max(time.time_ns(), previous + 1))


@contextmanager
def revision_lock(path: Path, *, timeout: float = 30.0, stale_after: float = 300.0):
    """Serialize local operations for one publisher on every supported OS."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    deadline = time.monotonic() + timeout

    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(f"{os.getpid()} {time.time()}\n")
            break
        except FileExistsError:
            try:
                stale = time.time() - lock.stat().st_mtime > stale_after
            except FileNotFoundError:
                continue
            if stale:
                try:
                    lock.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"another profile operation still holds {lock}")
            time.sleep(0.05)

    try:
        yield
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
