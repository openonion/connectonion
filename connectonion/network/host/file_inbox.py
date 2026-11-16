"""Files another agent sends to this one: FILE_OFFER, FILE_CHUNK, then verified.

`co send` on the sender's side drives this. The bytes travel on the sealed
direct socket and never through the relay: a multi-GB video is not something
the relay should carry, and on the relay it would be at the relay's limits.

    FILE_OFFER     sender → host   {sha256, size, name}
    FILE_ACCEPTED  host → sender   {sha256, received}     resume from here
    FILE_CHUNK     sender → host   {sha256, offset, chunk_sha256} signed, data: base64 beside it
    FILE_PROGRESS  host → sender   {sha256, received}
    FILE_STORED    host → sender   {sha256, size, name, path}

Layout under the Host's .co/inbox/files/:

    .partial/<sender>/<sha256>.part   the bytes so far; a dropped socket keeps them
    .partial/<sender>/<sha256>.json   the offer they belong to
    <YYYY-MM-DD>/<name>               verified; never overwrites what is there
    received.jsonl                    one line per verified file

A file is listed only after its size and sha256 match the offer. Who may send
is the same bar as lending a connection (ws_router/proxy.py): a contact,
a whitelisted address or an admin, on a direct socket.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import threading
import time
from datetime import date
from pathlib import Path

SEND_REQUIRES = ("admin", "whitelist", "contact")
CHUNK_BYTES = 1024 * 1024
# What a host accepts in one chunk; the sender uses CHUNK_BYTES.
MAX_CHUNK_BYTES = 4 * CHUNK_BYTES
# Room left on the disk after the file has landed. A full disk takes the
# Host's logs and sessions down with it.
DISK_MARGIN_BYTES = 1024 ** 3
# A staging copy nobody has resumed for this long is a send someone gave up on.
STALE_PARTIAL_SECONDS = 7 * 24 * 3600
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# The one receiver writing each staging file, keyed by its path. A resumed send
# opens a new socket while the old one may still be half alive; two writers on
# one .part interleave their bytes (seen on the first real 5 GB run).
_writers: dict = {}
_SEGMENT = re.compile(r"^[^/\\\x00-\x1f]{1,255}$")


class FileRefused(ValueError):
    """The offer or chunk is not accepted; `code` says which rule it broke."""

    def __init__(self, code: str, message: str, **detail):
        super().__init__(message)
        self.code = code
        self.detail = detail


def files_dir(co_dir: Path) -> Path:
    return Path(co_dir) / "inbox" / "files"


def safe_name(name) -> str:
    """A relative path of plain segments, or FileRefused. Folders keep their shape."""
    if not isinstance(name, str) or not name or name.startswith("/"):
        raise FileRefused("FILE_NAME", "a file name must be a relative path")
    segments = name.split("/")
    if len(segments) > 16 or any(
        part in (".", "..") or not _SEGMENT.fullmatch(part) for part in segments
    ):
        raise FileRefused("FILE_NAME", f"unsafe file name: {name!r}")
    return name


def _available(path: Path) -> Path:
    """A sibling that does not exist yet; what is already there stays."""
    if not path.exists() and not path.is_symlink():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise FileRefused("FILE_NAME", f"no free name for {path.name}")


def _folder(path: Path) -> Path:
    """`path`, or the first `path-N` that is a folder or free: a folder sent after
    a file of the same name lands together, under one new name."""
    if path.is_dir() or not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.name}-{index}")
        if candidate.is_dir() or not candidate.exists():
            return candidate
    raise FileRefused("FILE_NAME", f"no free name for {path.name}")


def _landing(base: Path, name: str) -> Path:
    """Where `name` lands under `base`; a folder segment that is already a file
    there no longer fails the mkdir on every retry."""
    *folders, leaf = name.split("/")
    here = base
    for folder in folders:
        here = _folder(here / folder)
    return _available(here / leaf)


def _remaining(writer) -> int:
    offer = writer.offer
    return offer["size"] - writer.received if offer else 0


def received(co_dir: Path) -> list[dict]:
    """Every verified file, oldest first."""
    log = files_dir(co_dir) / "received.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


class FileReceiver:
    """One socket's incoming files, one at a time."""

    def __init__(self, root: Path, sender: str):
        self.root = root
        self.sender = sender
        self.partial = root / ".partial" / sender
        self.offer = None
        self.handle = None
        self.digest = None
        self.received = 0
        self.superseded = False
        self.key = None
        # write() runs in a worker thread; take_over() closes another socket's
        # receiver from the event loop. One at a time.
        self.lock = threading.RLock()

    def take_over(self, sha256) -> None:
        """Become the only writer of this file's staging copy; the last offer wins."""
        if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
            raise FileRefused("FILE_OFFER", "sha256 must be 64 lowercase hex characters")
        self.close()
        self.key = self.partial / f"{sha256}.part"
        holder = _writers.get(self.key)
        if holder is not None:
            with holder.lock:
                holder.superseded = True
                holder.close()
        _writers[self.key] = self
        self.superseded = False
        # Here, on the event loop, so two offers never sweep the same folder.
        self._forget_stale(keep=self.key)

    def accept(self, offer: dict) -> dict:
        """Check an offer and open its staging file; say how much is already here.

        Call take_over(sha256) first, on the event loop.
        """
        sha256, size = offer.get("sha256"), offer.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise FileRefused("FILE_OFFER", "size must be a non-negative integer")
        name = safe_name(offer.get("name"))
        self.partial.mkdir(parents=True, exist_ok=True)
        part = self.partial / f"{sha256}.part"
        record = self.partial / f"{sha256}.json"
        held = part.stat().st_size if part.exists() else 0
        if held > size:
            part.unlink()
            held = 0
        # Other sends still in progress will need their room too.
        promised = sum(_remaining(w) for w in list(_writers.values()) if w is not self)
        free = shutil.disk_usage(self.partial).free - promised
        if size - held + DISK_MARGIN_BYTES > free:
            raise FileRefused(
                "FILE_NO_SPACE",
                f"{size - held} more bytes would leave less than 1 GB free on the receiver",
            )
        record.write_text(json.dumps({"sha256": sha256, "size": size, "name": name}))
        # Counted as promised from now on, before the rehash below takes its seconds.
        with self.lock:
            self.offer = {"sha256": sha256, "size": size, "name": name}
            self.received = held
        digest = hashlib.sha256()
        if held:
            with part.open("rb") as existing:
                for block in iter(lambda: existing.read(CHUNK_BYTES), b""):
                    digest.update(block)
        with self.lock:
            # Closed or taken over while rehashing: open nothing nobody will close.
            if self.superseded or self.offer is None:
                raise FileRefused("FILE_SUPERSEDED", "another send of this file took over")
            self.digest = digest
            self.handle = part.open("ab")
        return {"sha256": sha256, "received": held}

    def _forget_stale(self, keep: Path) -> None:
        cutoff = time.time() - STALE_PARTIAL_SECONDS
        for part in self.partial.glob("*.part"):
            if part != keep and part.stat().st_mtime < cutoff and _writers.get(part) is None:
                part.unlink()
                part.with_suffix(".json").unlink(missing_ok=True)

    def write(self, chunk: dict) -> dict:
        """Append one chunk at the offset the host expects; store when complete."""
        with self.lock:
            return self._write(chunk)

    def _write(self, chunk: dict) -> dict:
        if self.superseded:
            raise FileRefused("FILE_SUPERSEDED", "another send of this file took over")
        if self.offer is None or chunk.get("sha256") != self.offer["sha256"]:
            raise FileRefused("FILE_CHUNK", "no offer for this file (send FILE_OFFER first)")
        if chunk.get("offset") != self.received:
            raise FileRefused(
                "FILE_OFFSET", f"expected offset {self.received}", received=self.received,
            )
        try:
            data = base64.b64decode(chunk.get("data") or "", validate=True)
        except (binascii.Error, TypeError):
            raise FileRefused("FILE_CHUNK", "chunk data is not base64")
        if len(data) > MAX_CHUNK_BYTES or self.received + len(data) > self.offer["size"]:
            raise FileRefused("FILE_CHUNK", "chunk is larger than the offer allows")
        if not data and self.received < self.offer["size"]:
            raise FileRefused("FILE_CHUNK", "an empty chunk before the end of the file")
        if hashlib.sha256(data).hexdigest() != chunk.get("chunk_sha256"):
            raise FileRefused("FILE_CHUNK", "chunk does not match its signed sha256")
        self.handle.write(data)
        self.digest.update(data)
        self.received += len(data)
        if self.received < self.offer["size"]:
            return {"type": "FILE_PROGRESS", "sha256": self.offer["sha256"],
                    "received": self.received}
        return {"type": "FILE_STORED", **self._store()}

    def _store(self) -> dict:
        offer, part = self.offer, self.partial / f"{self.offer['sha256']}.part"
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.close()
        (self.partial / f"{offer['sha256']}.json").unlink()
        if self.digest.hexdigest() != offer["sha256"]:
            part.unlink()
            raise FileRefused("FILE_CORRUPT", "sha256 does not match the offer; send it again")
        target = _landing(self.root / date.today().isoformat(), offer["name"])
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(part, target)
        entry = {
            "from": self.sender, "name": offer["name"], "size": offer["size"],
            "sha256": offer["sha256"], "path": target.relative_to(self.root).as_posix(),
            "at": int(time.time()),
        }
        with (self.root / "received.jsonl").open("a") as log:
            log.write(json.dumps(entry) + "\n")
        self.digest = None
        return entry

    def close(self):
        with self.lock:
            if self.handle is not None:
                self.handle.close()
            if _writers.get(self.key) is self:
                del _writers[self.key]
            self.handle, self.offer = None, None


def _sender_allowed(conn, route_handlers, offer: bool) -> str | None:
    """Why this socket may not send files, or None.

    Trust is read on the offer; a chunk only lands for an accepted offer, and a
    revoked sender loses the socket in session.py. Reading the trust files on
    every chunk was 5,000 reads for 5 GB, on the event loop.
    """
    # Unsigned commands on a bare socket can be injected by whoever is on the
    # path; ws_router/proxy.py refuses them for the same reason.
    if not conn["authenticated"] or not conn["signed_commands"]:
        return "authenticate first (send a signed CONNECT)"
    if conn["transport"] != "direct":
        return "files travel over a direct connection, not the relay"
    if not offer:
        return None
    trust = route_handlers["trust_agent"]
    address = conn["agent_address"]
    level = "admin" if trust.is_admin(address) else trust.get_level(address)
    if level not in SEND_REQUIRES:
        return f"sending files requires a contact or admin; the sender is {level}"
    return None


async def receive_file(data, send_msg, conn, route_handlers, receiver):
    """Handle FILE_OFFER or FILE_CHUNK; return the socket's receiver for the next frame."""
    import asyncio

    refused = _sender_allowed(conn, route_handlers, data.get("type") == "FILE_OFFER")
    if refused:
        await send_msg({"type": "ERROR", "code": "FILE_FORBIDDEN", "message": refused})
        return receiver
    if receiver is None:
        receiver = FileReceiver(route_handlers["files_dir"], conn["agent_address"])
    try:
        if data.get("type") == "FILE_OFFER":
            receiver.take_over(data.get("sha256"))
            # Resuming rehashes what is already on disk: off the event loop.
            reply = {"type": "FILE_ACCEPTED", **await asyncio.to_thread(receiver.accept, data)}
        else:
            # A 4 MB write, and the fsync of a whole file at the end, block;
            # the Host's other sessions keep running meanwhile.
            reply = await asyncio.to_thread(receiver.write, data)
    except FileRefused as refused:
        await send_msg({"type": "ERROR", "code": refused.code, "message": str(refused),
                        **refused.detail})
        return receiver
    await send_msg(reply)
    return receiver
