"""Sealed direct channel: end-to-end encryption for a direct OIP socket.

Purpose: Let a client and a host talk over a plaintext ws:// socket without
TLS, so a self-hosted agent needs one open port and no domain or certificate.
LLM-Note:
  Dependencies: imports from [nacl.public, nacl.signing, connectonion.address,
  network/host/replay.SIGNATURE_EXPIRY_SECONDS] | imported by
  [network/connect.py (client side), network/asgi/websocket.py (host side)] |
  tested by [tests/unit/test_a_direct_socket_is_sealed.py]
  Data flow: client_hello() -> SEAL frame (signed by the client's long-term
  Ed25519 key, carrying a one-time X25519 key) -> host_accept() verifies,
  answers SEALED_OK (signed by the host, carrying its own one-time key) ->
  both sides derive one NaCl Box from the two one-time keys -> every later
  frame travels as {"type": "SEALED", "n": <counter>, "c": <base64>}.
  State/Effects: no I/O here; the socket wrappers in connect.py / websocket.py
  own the sockets. A channel keeps two counters (sent, last received).
  Integration: SealedChannel.seal(obj) / open(frame); SealedSocket wraps a
  websockets connection so callers keep using send()/recv().
  Errors: SealRefused for a bad or stale handshake; SealError for a frame
  that does not decrypt or arrives out of order — both are terminal for the
  connection, never silently skipped.

Why not TLS: a signed CONNECT on a plaintext link can be captured and, within
its freshness window, replayed (#649). TLS fixed that by making the link
private, at the price of a domain, a certificate and Caddy on every host. This
fixes it in the protocol instead: the two one-time keys are signed by the long
term identities the address already is, so a captured frame is neither
readable nor replayable, and the relay stays a forwarder of control frames.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Dict, Optional, Tuple

from nacl.public import Box, PrivateKey, PublicKey

from .. import address as addr
from .host.replay import SIGNATURE_EXPIRY_SECONDS

SEAL = "SEAL"
SEALED_OK = "SEALED_OK"
SEALED = "SEALED"
HANDSHAKE_TIMEOUT = 10

_NONCE_BYTES = 24
_CLIENT_TO_HOST = b"c2h"
_HOST_TO_CLIENT = b"h2c"


class SealRefused(Exception):
    """The handshake did not check out; the connection must not be used."""


class SealError(Exception):
    """A sealed frame did not open; the connection must not be used."""


def _canonical(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _hex(raw: bytes) -> str:
    return raw.hex()


def _nonce(tag: bytes, counter: int) -> bytes:
    return tag + counter.to_bytes(_NONCE_BYTES - len(tag), "big")


def client_hello(keys: Dict[str, Any], host_address: str, now: Optional[float] = None) -> Tuple[Dict[str, Any], PrivateKey]:
    """The client's opening frame and the one-time key it must keep."""
    ephemeral = PrivateKey.generate()
    payload = {
        "type": SEAL,
        "to": host_address,
        "from": keys["address"],
        "ephemeral": _hex(bytes(ephemeral.public_key)),
        "timestamp": int(now if now is not None else time.time()),
    }
    frame = dict(payload)
    frame["signature"] = addr.sign(keys, _canonical(payload)).hex()
    return frame, ephemeral


def host_accept(frame: Dict[str, Any], identity: Dict[str, Any], now: Optional[float] = None) -> Tuple[Dict[str, Any], "SealedChannel"]:
    """Check the client's SEAL, answer it, and return the host's channel."""
    if frame.get("type") != SEAL:
        raise SealRefused("not a SEAL frame")
    for field in ("to", "from", "ephemeral", "timestamp", "signature"):
        if field not in frame:
            raise SealRefused(f"SEAL is missing {field}")
    if frame["to"] != identity["address"]:
        raise SealRefused("SEAL is addressed to another host")
    timestamp = frame["timestamp"]
    if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool):
        raise SealRefused("SEAL timestamp is not a number")
    current = now if now is not None else time.time()
    if abs(current - timestamp) > SIGNATURE_EXPIRY_SECONDS:
        raise SealRefused("SEAL is stale")
    payload = {k: frame[k] for k in ("type", "to", "from", "ephemeral", "timestamp")}
    if not addr.verify(frame["from"], _canonical(payload), bytes.fromhex(frame["signature"])):
        raise SealRefused("SEAL signature does not verify")

    ephemeral = PrivateKey.generate()
    reply_payload = {
        "type": SEALED_OK,
        "to": frame["from"],
        "from": identity["address"],
        "ephemeral": _hex(bytes(ephemeral.public_key)),
        "client_ephemeral": frame["ephemeral"],
    }
    reply = dict(reply_payload)
    reply["signature"] = addr.sign(identity, _canonical(reply_payload)).hex()
    box = Box(ephemeral, PublicKey(bytes.fromhex(frame["ephemeral"])))
    return reply, SealedChannel(box, send_tag=_HOST_TO_CLIENT, recv_tag=_CLIENT_TO_HOST)


def client_finish(reply: Dict[str, Any], hello: Dict[str, Any], ephemeral: PrivateKey) -> "SealedChannel":
    """Check the host's SEALED_OK against the hello it answers, return the client's channel."""
    if reply.get("type") != SEALED_OK:
        raise SealRefused(f"expected {SEALED_OK}, got {reply.get('type')!r}")
    for field in ("to", "from", "ephemeral", "client_ephemeral", "signature"):
        if field not in reply:
            raise SealRefused(f"{SEALED_OK} is missing {field}")
    if reply["from"] != hello["to"]:
        raise SealRefused("SEALED_OK is not from the host that was dialed")
    if reply["to"] != hello["from"]:
        raise SealRefused("SEALED_OK is addressed to someone else")
    if reply["client_ephemeral"] != hello["ephemeral"]:
        # A SEALED_OK captured from another session names another key.
        raise SealRefused("SEALED_OK answers a different SEAL")
    payload = {k: reply[k] for k in ("type", "to", "from", "ephemeral", "client_ephemeral")}
    if not addr.verify(reply["from"], _canonical(payload), bytes.fromhex(reply["signature"])):
        raise SealRefused("SEALED_OK signature does not verify")
    box = Box(ephemeral, PublicKey(bytes.fromhex(reply["ephemeral"])))
    return SealedChannel(box, send_tag=_CLIENT_TO_HOST, recv_tag=_HOST_TO_CLIENT)


class SealedChannel:
    """One direction pair of counters over one Box."""

    def __init__(self, box: Box, *, send_tag: bytes, recv_tag: bytes):
        self._box = box
        self._send_tag = send_tag
        self._recv_tag = recv_tag
        self._sent = 0
        self._received = 0

    def seal(self, message: Dict[str, Any], default=None) -> Dict[str, Any]:
        self._sent += 1
        clear = json.dumps(message, default=default).encode()
        cipher = self._box.encrypt(clear, _nonce(self._send_tag, self._sent)).ciphertext
        return {"type": SEALED, "n": self._sent, "c": base64.b64encode(cipher).decode("ascii")}

    def open(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        if frame.get("type") != SEALED:
            raise SealError(f"expected a {SEALED} frame, got {frame.get('type')!r}")
        counter = frame.get("n")
        if not isinstance(counter, int) or isinstance(counter, bool) or counter <= self._received:
            # A replayed or reordered frame; the counter only ever goes up.
            raise SealError("sealed frame out of order")
        try:
            clear = self._box.decrypt(base64.b64decode(frame["c"]), _nonce(self._recv_tag, counter))
        except Exception as failed:
            raise SealError("sealed frame does not open") from failed
        self._received = counter
        return json.loads(clear)


class SealedSocket:
    """A websockets connection whose send()/recv() carry sealed frames."""

    def __init__(self, ws, channel: SealedChannel):
        self._ws = ws
        self._channel = channel

    async def send(self, raw: str) -> None:
        await self._ws.send(json.dumps(self._channel.seal(json.loads(raw))))

    async def recv(self) -> str:
        return json.dumps(self._channel.open(json.loads(await self._ws.recv())))

    async def close(self, *args, **kwargs) -> None:
        await self._ws.close(*args, **kwargs)

    def __aiter__(self):
        # A websockets connection iterates its frames; the share's reader
        # does `async for raw in ws`. The first two-machine run on the sealed
        # build died here with "requires an object with __aiter__".
        return self

    async def __anext__(self) -> str:
        try:
            return await self.recv()
        except Exception as closed:
            if type(closed).__name__ == "ConnectionClosedOK":
                raise StopAsyncIteration from closed
            raise

    async def __aenter__(self):
        await self._ws.__aenter__()
        return self

    async def __aexit__(self, *exc):
        return await self._ws.__aexit__(*exc)

    def __getattr__(self, name):
        return getattr(self._ws, name)
