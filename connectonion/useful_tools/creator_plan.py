"""Local media plans and confirmation receipts; never loads credentials."""

import hashlib
import hmac
import json
import mimetypes
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator


class CreatorError(ValueError):
    """A fixed, credential-free diagnostic safe for CLI output."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _digest(plan: dict) -> str:
    payload = {key: value for key, value in plan.items() if key != "confirmation"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def seal_plan(plan: dict) -> dict:
    """Bind the exact operation, target, metadata and file bytes for review."""
    return {**plan, "confirmation": _digest(plan)}


def confirm_plan(plan: dict, confirmation: str) -> None:
    """Refuse stale or edited plans, even if their stored digest was retained."""
    if not isinstance(confirmation, str) or not re.fullmatch(r"[a-f0-9]{64}", confirmation) or not hmac.compare_digest(_digest(plan), confirmation):
        raise CreatorError("confirmation_mismatch", "The confirmation does not match the current plan; preview it again.")


def media_file(path: str, sink: BinaryIO | None = None) -> dict:
    """Hash a regular video file; optionally copy the same bytes to a private snapshot."""
    source = Path(path).expanduser().resolve()
    mime = mimetypes.guess_type(source.name)[0] or ""
    if not mime.startswith("video/"):
        raise CreatorError("invalid_file", "Choose a local file with a video extension, such as .mp4 or .mov.")
    digest, size = hashlib.sha256(), 0
    try:
        # O_NONBLOCK prevents a FIFO called clip.mp4 from blocking before fstat.
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise CreatorError("invalid_file", "The media input must be a regular file.")
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > 256 * 1024**3:
                    raise CreatorError("invalid_file", "The media file exceeds the 256 GiB local limit.")
                digest.update(chunk)
                if sink is not None:
                    sink.write(chunk)
    except OSError:
        raise CreatorError("invalid_file", "Cannot read the local media file or create its private snapshot.") from None
    if size == 0:
        raise CreatorError("invalid_file", "The media file is empty.")
    return {"path": str(source), "size": size, "sha256": digest.hexdigest(), "mime_type": mime}


@contextmanager
def media_snapshot(path: str) -> Iterator[tuple[BinaryIO, dict]]:
    """Upload only a private copy whose bytes match the reviewed digest."""
    with tempfile.TemporaryFile(mode="w+b") as stream:
        info = media_file(path, sink=stream)
        stream.seek(0)
        yield stream, info


def claim_operation(confirmation: str) -> None:
    """Atomically consume a plan before a write, including ambiguous outcomes.

    Receipts contain only a hash. Keeping the claim after interruption prevents
    an automatic rerun from creating a duplicate upload. There is no reset verb.
    """
    directory = Path.home() / ".co" / "youtube_operations"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(directory / f"{confirmation}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise CreatorError("already_attempted", "This plan was already attempted. Inspect the channel before any new write.") from None
    with os.fdopen(descriptor, "w") as stream:
        json.dump({"confirmation": confirmation, "state": "attempted"}, stream)
        stream.flush()
        os.fsync(stream.fileno())
