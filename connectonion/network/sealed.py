"""Sealed channel: end-to-end encryption for an OIP socket, direct or relayed.

Purpose: Let a client and a host talk privately over any socket — a plaintext
ws:// port with no certificate, or the relay, which terminates TLS and would
otherwise read every frame.
LLM-Note:
  Dependencies: imports from [nacl.public, nacl.signing, connectonion.address,
  network/host/replay.SIGNATURE_EXPIRY_SECONDS] | imported by
  [network/connect.py (client side), network/asgi/websocket.py and
  network/relay.py (host side)] | tested by
  [tests/unit/test_a_direct_socket_is_sealed.py,
  tests/unit/test_the_relay_path_is_sealed.py]
  Data flow: client_hello() -> SEAL frame (signed by the client's long-term
  Ed25519 key, carrying a one-time X25519 key) -> host_accept() verifies,
  answers SEALED_OK (signed by the host, carrying its own one-time key) ->
  both sides derive one NaCl Box from the two one-time keys -> every later
  frame travels as {"type": "SEALED", "n": <counter>, "c": <base64>}.
  State/Effects: no I/O here; the socket wrappers in connect.py / websocket.py
  / relay.py own the sockets. A channel keeps two counters (sent, last
  received). host_seal_or_pass() is the one host-side entry both transports
  share; it reports who sealed so the session can bind CONNECT to them.
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
readable nor replayable.

Why the relay too: TLS to the relay is private only up to the relay. The oo-api
proxy reads `to` from the first frame and forwards everything after it verbatim,
and SEAL carries `to`, so the same handshake makes a relayed session opaque to
the relay without a relay change. Inside a seal, a replay is impossible for
anyone who did not complete the handshake, which is what lets the host stop
consulting its replay ledger there (#1402) — the ledger's SQLite file is what
took the Melbourne rental host down for 2h44m on 2026-09-03 (#1403).
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


# Frames the relay itself sends the client, in the clear, holding no key:
# its 30s keepalive and "Agent not connected". They carry nothing a peer
# said, so they are handed up as-is; anything else on a sealed socket must
# open. An intermediary that forges one of these can only end the session,
# which it could do by dropping the socket anyway.
_RELAY_CONTROL_FRAMES = ("PING", "ERROR")


async def host_seal_or_pass(send_msg, recv_msg, identity, *, default=None):
    """Seal a host-side session if its first frame is SEAL; pass an older client through.

    The first frame decides. SEAL is answered with SEALED_OK and from then on
    both adapters carry sealed frames, so the router never sees the
    difference. Anything else is handed to the router unchanged, as the first
    frame it reads. A SEAL that does not verify ends the session: an
    unauthenticated stranger gets no second try at a plaintext CONNECT.

    Returns (send, recv, sealed_by). sealed_by is the address that signed the
    SEAL, or None for an unsealed session; (None, None, None) means the
    session must not run at all. The same function serves the direct ASGI
    socket and a relay session, which differ only in their adapters.
    """
    first = await recv_msg()
    if first is None:
        return None, None, None
    if first.get("type") != SEAL:
        async def recv_with_first():
            nonlocal first
            if first is not None:
                frame, first = first, None
                return frame
            return await recv_msg()
        return send_msg, recv_with_first, None

    if identity is None or identity.get("signing_key") is None:
        await send_msg({"type": "ERROR", "message": "this host cannot seal"})
        return None, None, None
    try:
        reply, channel = host_accept(first, identity)
    except SealRefused as refused:
        await send_msg({"type": "ERROR", "message": f"seal refused: {refused}"})
        return None, None, None
    await send_msg(reply)

    async def send_sealed(data):
        await send_msg(channel.seal(data, default=default))

    async def recv_sealed():
        frame = await recv_msg()
        if frame is None:
            return None
        try:
            return channel.open(frame)
        except SealError as failed:
            # A frame that does not open is a break-in or a bug; either way
            # the session ends here rather than guessing.
            await send_msg({"type": "ERROR", "message": f"sealed frame rejected: {failed}"})
            return None

    return send_sealed, recv_sealed, first["from"]


class SealedSocket:
    """A websockets connection whose send()/recv() carry sealed frames."""

    def __init__(self, ws, channel: SealedChannel):
        self._ws = ws
        self._channel = channel

    async def send(self, raw: str) -> None:
        await self._ws.send(json.dumps(self._channel.seal(json.loads(raw))))

    async def recv(self) -> str:
        frame = json.loads(await self._ws.recv())
        if frame.get("type") in _RELAY_CONTROL_FRAMES and "c" not in frame:
            return json.dumps(frame)
        return json.dumps(self._channel.open(frame))

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
