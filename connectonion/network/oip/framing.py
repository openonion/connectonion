"""Length-delimited OIP 0.2 Protocol Buffers framing.

The file size is deliberately not part of the frame limit. Large artifacts are
split into bounded StreamData frames and can continue until policy, disk space,
or the sender ends the stream.
"""

from __future__ import annotations

import struct
from asyncio import IncompleteReadError

from google.protobuf.message import DecodeError

from . import browser_daemon_pb2 as wire

MAGIC = b"OIP2"
PROTOCOL_VERSION = 2
CHUNK_BYTES = 256 * 1024
MAX_FRAME_BYTES = CHUNK_BYTES + 64 * 1024
_HEADER = struct.Struct(">4sI")


class ProtocolError(ValueError):
    """The peer sent a frame that cannot be processed safely."""


def _validate(frame: wire.Envelope) -> None:
    if frame.protocol_version != PROTOCOL_VERSION:
        raise ProtocolError(
            f"unsupported OIP version {frame.protocol_version}; expected {PROTOCOL_VERSION}"
        )
    if not frame.request_id:
        raise ProtocolError("request_id is required")
    if len(frame.request_id.encode("utf-8")) > 128:
        raise ProtocolError("request_id exceeds 128 bytes")
    kind = frame.WhichOneof("frame")
    if kind is None:
        raise ProtocolError("frame payload is required")
    if kind == "stream_data" and len(frame.stream_data.payload) > CHUNK_BYTES:
        raise ProtocolError(
            f"artifact chunk exceeds the {CHUNK_BYTES}-byte limit"
        )
    if kind == "command":
        argv = frame.command.argv
        if not argv or len(argv) > 128:
            raise ProtocolError("browser command requires 1 to 128 argv entries")
        encoded_size = 0
        for value in argv:
            encoded = value.encode("utf-8")
            if b"\x00" in encoded or len(encoded) > 64 * 1024:
                raise ProtocolError("browser argv contains an invalid value")
            encoded_size += len(encoded)
        if encoded_size > 128 * 1024:
            raise ProtocolError("browser argv exceeds 128 KiB")
    if kind == "result" and frame.result.artifact_count > 16:
        raise ProtocolError("BrowserResult declares too many artifacts")
    if kind == "stream_open":
        opened = frame.stream_open
        if not opened.artifact_id or len(opened.artifact_id.encode("utf-8")) > 128:
            raise ProtocolError("artifact_id is missing or too long")
        if len(opened.proposed_name.encode("utf-8")) > 255:
            raise ProtocolError("artifact proposed_name exceeds 255 bytes")
        if len(opened.media_type.encode("utf-8")) > 127:
            raise ProtocolError("artifact media_type exceeds 127 bytes")
        if len(opened.sha256) != 32:
            raise ProtocolError("artifact descriptor requires a SHA-256 digest")
    if kind in {"stream_fin", "stream_commit"}:
        digest = (
            frame.stream_fin.sha256
            if kind == "stream_fin"
            else frame.stream_commit.sha256
        )
        if len(digest) != 32:
            raise ProtocolError(f"{kind} requires a SHA-256 digest")
    if kind in {"stream_open", "stream_data", "stream_fin", "stream_commit"}:
        if frame.stream_id == 0:
            raise ProtocolError("artifact frames require a non-zero stream_id")


def encode_frame(frame: wire.Envelope) -> bytes:
    """Encode exactly one OIP envelope with its transport-independent prefix."""
    _validate(frame)
    payload = frame.SerializeToString(deterministic=True)
    if len(payload) > MAX_FRAME_BYTES:
        raise ProtocolError(
            f"frame exceeds the {MAX_FRAME_BYTES}-byte metadata limit"
        )
    return _HEADER.pack(MAGIC, len(payload)) + payload


def decode_frame(data: bytes) -> wire.Envelope:
    """Decode exactly one complete OIP envelope and reject trailing bytes."""
    if len(data) < _HEADER.size:
        raise ProtocolError("truncated OIP frame header")
    magic, size = _HEADER.unpack_from(data)
    if magic != MAGIC:
        raise ProtocolError("missing OIP2 frame prefix")
    if size > MAX_FRAME_BYTES:
        raise ProtocolError(
            f"frame declares {size} bytes; maximum is {MAX_FRAME_BYTES}"
        )
    if len(data) != _HEADER.size + size:
        raise ProtocolError("OIP frame length does not match its payload")
    frame = wire.Envelope()
    try:
        frame.ParseFromString(data[_HEADER.size :])
    except DecodeError as exc:
        raise ProtocolError("invalid Protocol Buffers envelope") from exc
    _validate(frame)
    return frame


def frame_size_from_header(header: bytes) -> int:
    """Validate an eight-byte header before a reader allocates its payload."""
    if len(header) != _HEADER.size:
        raise ProtocolError("truncated OIP frame header")
    magic, size = _HEADER.unpack(header)
    if magic != MAGIC:
        raise ProtocolError("missing OIP2 frame prefix")
    if size > MAX_FRAME_BYTES:
        raise ProtocolError(
            f"frame declares {size} bytes; maximum is {MAX_FRAME_BYTES}"
        )
    return size


def recv_socket_frame(sock) -> wire.Envelope:
    """Read one frame from a stream socket without waiting for EOF."""
    header = _recv_exact(sock, _HEADER.size)
    size = frame_size_from_header(header)
    return decode_frame(header + _recv_exact(sock, size))


def _recv_exact(sock, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise ProtocolError("peer closed during an OIP frame")
        chunks.extend(chunk)
    return bytes(chunks)


async def read_async_frame(reader) -> wire.Envelope:
    """Read one frame from an asyncio StreamReader without waiting for EOF."""
    try:
        header = await reader.readexactly(_HEADER.size)
        size = frame_size_from_header(header)
        payload = await reader.readexactly(size)
    except IncompleteReadError as exc:
        raise ProtocolError("peer closed during an OIP frame") from exc
    return decode_frame(header + payload)
