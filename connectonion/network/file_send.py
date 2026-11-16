"""Send one file to another agent's Host: the sender half of host/file_inbox.py.

The file is hashed first, offered by its sha256, and sent in signed chunks on
the sealed direct socket. The relay is never used for the bytes: if the
receiver cannot be reached directly, the send stops and says so.

A dropped connection is not the end of a transfer. The receiver keeps what
arrived under the file's sha256, and the next offer is answered with how much
that is, so the send continues from there instead of from zero.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
import uuid
from pathlib import Path

from .. import address as addr
from .host.file_inbox import CHUNK_BYTES

# Bytes in flight before the sender waits for the receiver to catch up.
WINDOW_BYTES = 8 * CHUNK_BYTES
REPLY_TIMEOUT = 120
RETRIES = 20


class SendRefused(Exception):
    """The receiver said no, or cannot be reached directly. Retrying will not help."""


class _Resync(Exception):
    """The receiver holds a different offset than we sent from; offer again."""


def sha256_of(path: Path, on_progress=None) -> str:
    digest, done, size = hashlib.sha256(), 0, path.stat().st_size
    with path.open("rb") as source:
        for block in iter(lambda: source.read(CHUNK_BYTES), b""):
            digest.update(block)
            done += len(block)
            if on_progress:
                on_progress("hashing", done, size)
    return digest.hexdigest()


def _signed(remote, message: dict) -> dict:
    """A v2 command frame without the top-level copies: a chunk is sent once."""
    command = {**message, "timestamp": int(time.time()), "nonce": uuid.uuid4().hex,
               "to": remote.address}
    canonical = json.dumps(command, sort_keys=True, separators=(",", ":")).encode()
    return {"type": message["type"], "payload": command, "from": remote._keys["address"],
            "signature": addr.sign(remote._keys, canonical).hex()}


def _chunk(remote, sha256: str, offset: int, data: bytes) -> str:
    """One FILE_CHUNK: the signature covers the chunk's digest, the bytes ride beside it."""
    frame = _signed(remote, {"type": "FILE_CHUNK", "sha256": sha256, "offset": offset,
                             "chunk_sha256": hashlib.sha256(data).hexdigest()})
    frame["data"] = base64.b64encode(data).decode()
    return json.dumps(frame)


async def _reply(ws) -> dict:
    """The receiver's next answer; PINGs are answered on the way."""
    while True:
        event = json.loads(await asyncio.wait_for(ws.recv(), timeout=REPLY_TIMEOUT))
        if event.get("type") == "PING":
            await ws.send(json.dumps({"type": "PONG"}))
        elif event.get("type") == "ERROR":
            if event.get("code") == "FILE_OFFSET":
                raise _Resync()
            raise SendRefused(event.get("message", "the receiver refused the file"))
        elif event.get("type", "").startswith("FILE_"):
            return event


async def _send_once(remote, path: Path, name: str, size: int, sha256: str, on_progress):
    import websockets

    await remote._try_resolve_endpoint()
    connection, is_direct = await remote._open_best_connection(websockets)
    async with connection as ws:
        if not is_direct:
            raise SendRefused(
                f"{remote.address[:10]}… is not reachable directly from here, only through "
                "the relay, which does not carry files. Send from the same network, or give "
                "the receiver a public address (AGENT_PUBLIC_DOMAIN)."
            )
        await ws.send(json.dumps(remote._build_connect_message(True)))
        refused = await remote._wait_for_direct_command_connected(ws)
        if refused:
            raise SendRefused(refused)
        await ws.send(json.dumps(_signed(remote, {
            "type": "FILE_OFFER", "sha256": sha256, "size": size, "name": name,
        })))
        sent = acked = (await _reply(ws))["received"]
        with path.open("rb") as source:
            source.seek(sent)
            if sent == size:
                await ws.send(_chunk(remote, sha256, sent, b""))
            while True:
                while sent < size and sent - acked < WINDOW_BYTES:
                    data = source.read(CHUNK_BYTES)
                    await ws.send(_chunk(remote, sha256, sent, data))
                    sent += len(data)
                reply = await _reply(ws)
                if reply["type"] == "FILE_STORED":
                    return reply
                acked = reply["received"]
                if on_progress:
                    on_progress("sending", acked, size)


async def send_file(remote, path: Path, name: str, on_progress=None) -> dict:
    """Send `path` to `remote` as `name`; the receiver's FILE_STORED record."""
    import websockets

    if not remote._keys:
        raise SendRefused("no identity to sign with: run `co init` first")
    size = path.stat().st_size
    sha256 = await asyncio.to_thread(sha256_of, path, on_progress)
    for attempt in range(RETRIES + 1):
        try:
            return await _send_once(remote, path, name, size, sha256, on_progress)
        except (OSError, asyncio.TimeoutError, websockets.ConnectionClosed, _Resync):
            if attempt == RETRIES:
                raise
            wait = min(30, 2 ** attempt)
            if on_progress:
                on_progress(f"connection lost, resuming in {wait}s", 0, size)
            await asyncio.sleep(wait)
            remote._forget_direct_endpoint()
