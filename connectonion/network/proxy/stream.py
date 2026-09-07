"""Wire shape of a Laptop Proxy share: one WebSocket carrying many TCP streams.

The laptop dials the browser host over the ordinary direct WebSocket, attaches
with a grant, and from then on the host sends work *down* that socket:

    PROXY_ATTACH    laptop → host   {"grant": {...}}            signed
    PROXY_ATTACHED  host → laptop   {"expires_at", "max_bytes"}
    PROXY_STREAM    both ways       {"id": int, "op": ..., ...}

Every stream frame names the stream it belongs to; `op` says what happened:

    resolve   host asks {host, port}; laptop answers {addresses: [ip, ...]}
    connect   host asks {address, port}; laptop answers {} once connected
    data      either side, {data: base64}; at most CHUNK_BYTES before encoding
    eof       either side: no more bytes this way, the other way stays open
    close     either side: the stream is gone
    error     laptop → host: the request was refused, {code}

The laptop signs what it sends because the host checks every command frame
against the CONNECT identity. Frames from host to laptop carry no signature:
they travel inside TLS to an endpoint the laptop resolved and verified
before attaching, so the transport already says who is speaking.
"""

from __future__ import annotations

import base64
import binascii

ATTACH = "PROXY_ATTACH"
ATTACHED = "PROXY_ATTACHED"
STREAM = "PROXY_STREAM"

OPS = frozenset({"resolve", "connect", "data", "eof", "close", "error"})

# Raw bytes per data frame. Small enough that one frame signs and parses in
# well under a millisecond, large enough that a page load is not thousands of
# them.
CHUNK_BYTES = 32 * 1024
# What a peer will accept in one data frame after decoding; a frame beyond
# this is malformed, not merely large.
MAX_DATA_BYTES = CHUNK_BYTES
# Streams one attached share may have open at once, on either side.
MAX_STREAMS = 64


def stream_frame(stream_id: int, op: str, **fields) -> dict:
    return {"type": STREAM, "id": stream_id, "op": op, **fields}


def data_frame(stream_id: int, payload: bytes) -> dict:
    return stream_frame(
        stream_id, "data", data=base64.b64encode(payload).decode("ascii")
    )


def stream_id_of(frame: dict) -> int:
    """The stream a frame belongs to, or ValueError if it names none."""
    stream_id = frame.get("id")
    if isinstance(stream_id, bool) or not isinstance(stream_id, int) or stream_id < 1:
        raise ValueError("stream frame has no stream id")
    if frame.get("op") not in OPS:
        raise ValueError("stream frame has no op")
    return stream_id


def decode_data(frame: dict) -> bytes:
    """The bytes a data frame carries, or ValueError if it is not a bounded one."""
    encoded = frame.get("data")
    if not isinstance(encoded, str) or len(encoded) > MAX_DATA_BYTES * 2:
        raise ValueError("data frame is not bounded base64")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except binascii.Error as exc:
        raise ValueError("data frame is not base64") from exc
    if len(payload) > MAX_DATA_BYTES:
        raise ValueError("data frame exceeds the chunk bound")
    return payload
