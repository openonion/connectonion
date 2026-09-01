"""Daemon staging and caller-owned materialization for browser artifacts."""

from __future__ import annotations

import hashlib
import math
import mimetypes
import os
import re
import stat
import uuid
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import Iterable, Iterator

from connectonion.network.oip import browser_daemon_pb2 as wire
from connectonion.network.oip.framing import CHUNK_BYTES, PROTOCOL_VERSION

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,199}$")
_MEDIA_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/octet-stream": ".bin",
}


class ArtifactTransferError(ValueError):
    """An artifact failed validation and was not committed."""


def _sha256(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.digest()


def _safe_name(proposed: str, artifact_id: str, media_type: str) -> str:
    if (
        proposed
        and Path(proposed).name == proposed
        and proposed not in {".", ".."}
        and _SAFE_NAME.fullmatch(proposed)
    ):
        return proposed
    extension = _MEDIA_EXTENSIONS.get(media_type)
    if extension is None:
        extension = mimetypes.guess_extension(media_type or "") or ".bin"
    return f"artifact-{artifact_id[:12]}{extension}"


def _available_path(path: Path) -> Path:
    """Return a non-existing sibling; downloads never overwrite caller data."""
    if not path.exists() and not path.is_symlink():
        return path
    stem, suffix = path.stem, path.suffix
    for index in range(1, 10_000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise ArtifactTransferError("could not allocate a collision-free artifact name")


@dataclass
class StagedArtifact:
    path: Path
    request_id: str
    stream_id: int
    artifact_id: str
    proposed_name: str
    media_type: str
    size: int
    digest: bytes
    sensitive: bool = False
    chunk_count: int = 0

    def open_frame(self) -> wire.Envelope:
        return wire.Envelope(
            protocol_version=PROTOCOL_VERSION,
            request_id=self.request_id,
            stream_id=self.stream_id,
            sequence=0,
            offset=0,
            stream_open=wire.StreamOpen(
                artifact_id=self.artifact_id,
                proposed_name=self.proposed_name,
                media_type=self.media_type,
                expected_size=self.size,
                sha256=self.digest,
                sensitive=self.sensitive,
            ),
        )

    def data_frames(self) -> Iterator[wire.Envelope]:
        offset = 0
        sequence = 1
        with self.path.open("rb") as source:
            while chunk := source.read(CHUNK_BYTES):
                yield wire.Envelope(
                    protocol_version=PROTOCOL_VERSION,
                    request_id=self.request_id,
                    stream_id=self.stream_id,
                    sequence=sequence,
                    offset=offset,
                    stream_data=wire.StreamData(payload=chunk),
                )
                offset += len(chunk)
                sequence += 1
                self.chunk_count += 1

    def fin_frame(self) -> wire.Envelope:
        data_frame_count = math.ceil(self.size / CHUNK_BYTES)
        return wire.Envelope(
            protocol_version=PROTOCOL_VERSION,
            request_id=self.request_id,
            stream_id=self.stream_id,
            sequence=data_frame_count + 1,
            offset=self.size,
            stream_fin=wire.StreamFin(actual_size=self.size, sha256=self.digest),
        )

    def discard(self) -> None:
        self.path.unlink(missing_ok=True)
        try:
            self.path.parent.rmdir()
        except OSError:
            pass


class ArtifactStager:
    """Own files only until the authenticated caller commits their stream."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def reserve(self, request_id: str, suffix: str = ".png") -> Path:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        directory = self.root / request_id
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        return directory / f"artifact-{uuid.uuid4().hex}{suffix}"

    def adopt(
        self,
        path: str | Path,
        *,
        proposed_name: str,
        media_type: str,
        request_id: str = "req-1",
        stream_id: int = 1,
        sensitive: bool = False,
    ) -> StagedArtifact:
        source = Path(path)
        try:
            source.resolve(strict=True).relative_to(self.root.resolve(strict=True))
        except (FileNotFoundError, ValueError) as exc:
            raise ArtifactTransferError(
                "daemon artifacts must come from the private staging root"
            ) from exc
        details = source.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            raise ArtifactTransferError("daemon artifact must be a regular file")
        return StagedArtifact(
            path=source,
            request_id=request_id,
            stream_id=stream_id,
            artifact_id=uuid.uuid4().hex,
            proposed_name=proposed_name,
            media_type=media_type,
            size=details.st_size,
            digest=_sha256(source),
            sensitive=sensitive,
        )


class ArtifactReceiver:
    """Verify a stream into a private partial file, then atomically expose it."""

    def __init__(self, root: str | Path, *, max_bytes: int | None = None):
        self.root = Path(root)
        self.max_bytes = max_bytes

    def receive(
        self,
        opened: wire.Envelope,
        chunks: Iterable[wire.Envelope],
        finished: wire.Envelope,
        *,
        destination: str | Path | None = None,
    ) -> Path:
        final, _finished = self.receive_stream(
            opened, chain(chunks, [finished]), destination=destination
        )
        return final

    def receive_stream(
        self,
        opened: wire.Envelope,
        frames: Iterable[wire.Envelope],
        *,
        destination: str | Path | None = None,
    ) -> tuple[Path, wire.Envelope]:
        """Consume frames through StreamFin without buffering the artifact."""
        if opened.WhichOneof("frame") != "stream_open":
            raise ArtifactTransferError("stream must begin with StreamOpen")
        descriptor = opened.stream_open
        if self.max_bytes is not None and descriptor.expected_size > self.max_bytes:
            raise ArtifactTransferError("artifact exceeds the caller's configured quota")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        if destination is None:
            final = self.root / _safe_name(
                descriptor.proposed_name, descriptor.artifact_id, descriptor.media_type
            )
        else:
            final = Path(destination).expanduser()
            final.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        final = _available_path(final)
        partial = final.with_name(f".{final.name}.part-{uuid.uuid4().hex}")
        written = 0
        sequence = 1
        digest = hashlib.sha256()
        try:
            with partial.open("xb") as output:
                os.chmod(partial, 0o600)
                finished = None
                for frame in frames:
                    kind = frame.WhichOneof("frame")
                    if kind == "stream_fin":
                        finished = frame
                        break
                    if kind != "stream_data":
                        raise ArtifactTransferError("expected StreamData or StreamFin")
                    if frame.request_id != opened.request_id or frame.stream_id != opened.stream_id:
                        raise ArtifactTransferError("artifact stream identity changed")
                    if frame.sequence != sequence:
                        raise ArtifactTransferError("artifact sequence is not contiguous")
                    if frame.offset != written:
                        raise ArtifactTransferError("artifact offset is not contiguous")
                    payload = frame.stream_data.payload
                    if len(payload) > CHUNK_BYTES:
                        raise ArtifactTransferError("artifact chunk exceeds the frame limit")
                    written += len(payload)
                    if self.max_bytes is not None and written > self.max_bytes:
                        raise ArtifactTransferError("artifact exceeds the caller's configured quota")
                    output.write(payload)
                    digest.update(payload)
                    sequence += 1
                output.flush()
                os.fsync(output.fileno())
            if finished is None:
                raise ArtifactTransferError("stream ended without StreamFin")
            if finished.request_id != opened.request_id or finished.stream_id != opened.stream_id:
                raise ArtifactTransferError("artifact stream identity changed")
            if finished.sequence != sequence or finished.offset != written:
                raise ArtifactTransferError("artifact final offset or sequence is invalid")
            expected_hash = bytes(finished.stream_fin.sha256)
            if finished.stream_fin.actual_size != written or descriptor.expected_size != written:
                raise ArtifactTransferError("artifact size does not match its descriptor")
            if digest.digest() != expected_hash or bytes(descriptor.sha256) != expected_hash:
                raise ArtifactTransferError("artifact SHA-256 does not match")
            try:
                os.link(partial, final)
            except FileExistsError as exc:
                raise ArtifactTransferError(
                    "artifact destination appeared during commit; nothing was overwritten"
                ) from exc
            partial.unlink()
            return final, finished
        except Exception:
            partial.unlink(missing_ok=True)
            raise

    @staticmethod
    def commit_frame(
        opened: wire.Envelope, finished: wire.Envelope
    ) -> wire.Envelope:
        return wire.Envelope(
            protocol_version=PROTOCOL_VERSION,
            request_id=opened.request_id,
            stream_id=opened.stream_id,
            sequence=finished.sequence + 1,
            offset=finished.stream_fin.actual_size,
            stream_commit=wire.StreamCommit(
                actual_size=finished.stream_fin.actual_size,
                sha256=finished.stream_fin.sha256,
            ),
        )
