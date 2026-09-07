"""Share this computer's internet connection with an authorized remote agent.

A browser running on a server reaches the internet from a data-centre address.
Many sites treat that differently from an ordinary home connection, so the
Remote Browser product lets the caller lend its own connection instead:

    browser on the host  ──▶  this machine  ──▶  the internet (your IP)

This machine is usually behind NAT, so nothing can dial in. `ProxyShare` dials
*out* to the host over the ordinary direct WebSocket, attaches with a grant, and
then serves the host's resolve/connect requests as they come down that socket.
The host's browser gateway still speaks CORESOLVE and numeric CONNECT — to a
loopback endpoint in the host process whose last hop is this socket
(`host/proxy_channel.py`); `remote_proxy_dialer` and `remote_proxy_resolver`
below are that gateway's side of the conversation.

Lending a connection must not lend the network behind it. Every request the
host sends is decided by the same destination policy as the host-private egress
gateway, on this machine, before a socket is opened.

The grant issued by `connectonion.network.proxy` is the credential. Nothing
here reads a browser profile, a cookie, or a file: the tunnel carries bytes the
remote browser already decided to send, and TLS inside it stays end to end.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import ipaddress
import json
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .connect import RemoteAgent
from .host.egress_gateway import (
    EgressGateway,
    GatewayLimits,
    GatewayRefusal,
    NumericEndpoint,
    ProxyEndpoint,
)
from .proxy import issue_grant
from .proxy import stream as wire

# Ranges a shared connection must never reach on the sharer's behalf. The
# gateway's frozen table already denies these; naming them here is what makes
# the intent legible when someone widens the policy later.
SHARED_DENY_NETWORKS: tuple[str, ...] = ()

DEFAULT_TTL = 24 * 60 * 60
_RECONNECT_CEILING = 60.0
_REMOTE_HEADER_LIMIT = 16 * 1024
_REMOTE_IO_TIMEOUT = 10.0


@dataclass(frozen=True)
class ShareEndpoint:
    """Where the host's browser gateway connects, and what it must present."""

    host: str
    port: int
    username: str
    password: str

    @property
    def url(self) -> str:
        """The address as a URL; carries no credential."""
        return f"http://{self.host}:{self.port}"


class ProxyShareRefused(Exception):
    """The host would not accept this machine's share; retrying will not help."""


class _Stream:
    def __init__(self, stream_id: int, writer: asyncio.StreamWriter):
        self.id = stream_id
        self.writer = writer
        self.pump: asyncio.Task | None = None


class ProxyShare:
    """This machine's internet connection, lent to one host it dials itself."""

    def __init__(
        self,
        remote_address: str,
        *,
        keys: dict,
        ttl: int = DEFAULT_TTL,
        relay_url: str | None = None,
        allowed_ports=(80, 443, 8080, 8443),
        deny_networks=SHARED_DENY_NETWORKS,
        limits: GatewayLimits | None = None,
        resolver=None,
        dialer=None,
        on_state=None,
    ):
        overrides = {}
        if resolver is not None:
            overrides["resolver"] = resolver
        if dialer is not None:
            overrides["dialer"] = dialer
        # Never started: the gateway is the destination policy, not a listener.
        self._policy = EgressGateway(
            allowed_ports=allowed_ports,
            deny_networks=deny_networks,
            limits=limits,
            **overrides,
        )
        self.remote = RemoteAgent(remote_address, keys=keys, relay_url=relay_url)
        self._keys = keys
        # One expiry for the life of this share. A reconnect mints a fresh
        # grant, and a fresh grant must not quietly outlive the ttl asked for.
        self.expires_at = time.time() + ttl
        self.state = "connecting"
        self.handled_requests = 0
        self._on_state = on_state or (lambda state, detail: None)
        self._ws = None
        self._send_lock = asyncio.Lock()
        self._streams: dict[int, _Stream] = {}
        self._tasks: set[asyncio.Task] = set()

    async def serve(self, stop: asyncio.Event) -> None:
        """Stay attached until `stop`; dial again with backoff when it drops."""
        import websockets

        backoff = 1.0
        while not stop.is_set():
            self._set_state("connecting", self.remote.address)
            try:
                attached = await self._session(stop)
            except (OSError, asyncio.TimeoutError, websockets.exceptions.WebSocketException) as dropped:
                attached, detail = False, str(dropped) or type(dropped).__name__
            else:
                detail = "the host closed the connection"
            if stop.is_set() or time.time() >= self.expires_at:
                break
            backoff = 1.0 if attached else min(backoff * 2, _RECONNECT_CEILING)
            self._set_state("reconnecting", f"{detail}; retrying in {backoff:.0f}s")
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=backoff)
        self._set_state("stopped", "")

    async def _session(self, stop: asyncio.Event) -> bool:
        """One socket: dial, attach, serve until it drops. True once attached."""
        import websockets

        await self.remote._try_resolve_endpoint()
        connection, is_direct = await self.remote._open_best_connection(websockets)
        async with connection as ws:
            if not is_direct:
                # The relay would carry every byte of every page through
                # oo.openonion.ai. A share only exists on a direct socket.
                raise OSError("the host is not reachable directly")
            self._ws = ws
            await ws.send(json.dumps(self.remote._build_connect_message(True)))
            error = await self.remote._wait_for_direct_command_connected(ws)
            if error:
                raise ProxyShareRefused(error)
            await self._send({"type": wire.ATTACH, "grant": self._grant()})
            reply = await self._attach_reply(ws)
            if reply["type"] != wire.ATTACHED:
                raise ProxyShareRefused(reply.get("message", "attach refused"))
            self._set_state("attached", self.remote.address)
            reader = asyncio.create_task(self._read_frames(ws))
            stopper = asyncio.create_task(stop.wait())
            try:
                await asyncio.wait({reader, stopper}, return_when=asyncio.FIRST_COMPLETED)
                if reader.done():
                    reader.result()
            finally:
                stopper.cancel()
                reader.cancel()
                await self._abandon_streams()
                self._ws = None
        return True

    def _grant(self) -> dict:
        expires = datetime.fromtimestamp(self.expires_at, timezone.utc)
        return issue_grant(
            self._keys,
            holder=self.remote.address,
            expires_at=expires.isoformat().replace("+00:00", "Z"),
        )

    async def _next_frame(self, ws) -> dict:
        while True:
            frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            if frame.get("type") == "PING":
                await ws.send(json.dumps({"type": "PONG"}))
                continue
            return frame

    async def _attach_reply(self, ws) -> dict:
        """The host's answer to PROXY_ATTACH, past whatever else it pushes.

        A real host follows CONNECTED with AGENT_PROFILE and the like; only
        PROXY_ATTACHED or ERROR says whether the share is up.
        """
        while True:
            frame = await self._next_frame(ws)
            if frame.get("type") in {wire.ATTACHED, "ERROR"}:
                return frame

    async def _read_frames(self, ws) -> None:
        async for raw in ws:
            frame = json.loads(raw)
            kind = frame.get("type")
            if kind == "PING":
                await ws.send(json.dumps({"type": "PONG"}))
            elif kind == wire.STREAM:
                await self._handle(frame)
            elif kind == "ERROR":
                self._on_state("error", frame.get("message", ""))

    # ---- requests coming down from the host ----

    async def _handle(self, frame: dict) -> None:
        stream_id = wire.stream_id_of(frame)
        op = frame["op"]
        if op in {"resolve", "connect"}:
            self.handled_requests += 1
            self._spawn(self._answer(stream_id, op, frame))
            return
        stream = self._streams.get(stream_id)
        if stream is None:
            return
        if op == "data":
            await self._write(stream, wire.decode_data(frame))
        elif op == "eof":
            with contextlib.suppress(NotImplementedError, OSError):
                stream.writer.write_eof()
        else:
            self._forget(stream)

    async def _answer(self, stream_id: int, op: str, frame: dict) -> None:
        host, port = frame.get("host") or frame.get("address"), frame.get("port")
        if not isinstance(host, str) or isinstance(port, bool) or not isinstance(port, int):
            await self._send(wire.stream_frame(stream_id, "error", code="EGRESS_INVALID"))
            return
        try:
            if op == "resolve":
                endpoints = await self._policy.resolve_destination(host, port)
                addresses = [endpoint.address for endpoint in endpoints]
                await self._send(wire.stream_frame(stream_id, "resolve", addresses=addresses))
                return
            reader, writer = await self._policy.connect_destination(host, port)
        except GatewayRefusal as refused:
            await self._send(wire.stream_frame(stream_id, "error", code=refused.code))
            return
        if stream_id in self._streams or len(self._streams) >= wire.MAX_STREAMS:
            writer.close()
            await self._send(wire.stream_frame(stream_id, "error", code="EGRESS_OVERLOADED"))
            return
        stream = _Stream(stream_id, writer)
        self._streams[stream_id] = stream
        await self._send(wire.stream_frame(stream_id, "connect"))
        stream.pump = self._spawn(self._pump_up(stream, reader))

    async def _pump_up(self, stream: _Stream, reader: asyncio.StreamReader) -> None:
        """Bytes from the destination become data frames until it stops."""
        try:
            while True:
                chunk = await reader.read(wire.CHUNK_BYTES)
                if not chunk:
                    await self._send(wire.stream_frame(stream.id, "eof"))
                    return
                await self._send(wire.data_frame(stream.id, chunk))
        except OSError:
            # The destination reset the socket; the host learns the stream is
            # gone rather than waiting on an EOF that will never come.
            if self._streams.get(stream.id) is stream:
                self._forget(stream)
                await self._send(wire.stream_frame(stream.id, "close"))

    async def _write(self, stream: _Stream, payload: bytes) -> None:
        stream.writer.write(payload)
        try:
            await stream.writer.drain()
        except OSError:
            self._forget(stream)
            await self._send(wire.stream_frame(stream.id, "close"))

    def _forget(self, stream: _Stream) -> None:
        self._streams.pop(stream.id, None)
        if stream.pump is not None:
            stream.pump.cancel()
        stream.writer.close()

    async def _abandon_streams(self) -> None:
        for stream in list(self._streams.values()):
            self._forget(stream)
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def _spawn(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._reap)
        return task

    def _reap(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            # A stream task that died is not the share dying, but the operator
            # should see it rather than an "exception was never retrieved" at
            # garbage-collection time.
            self._on_state("error", repr(task.exception()))

    async def _send(self, frame: dict) -> None:
        # Signed, because the host verifies every command frame against the
        # CONNECT identity; one lock so frames of a stream leave in order.
        signed = self.remote._build_command_message(frame, True)
        async with self._send_lock:
            await self._ws.send(json.dumps(signed))

    def _set_state(self, state: str, detail: str) -> None:
        self.state = state
        self._on_state(state, detail)


def remote_proxy_dialer(share: ShareEndpoint):
    """Dial approved destinations through a shared connection, not directly.

    Returned in the shape `EgressGateway` expects for its `dialer`, which is
    the whole integration: the host still resolves, classifies and pins a
    numeric address itself, and only the last hop changes. The host asks the
    sharer for that exact numeric address — never a hostname — so lending a
    connection cannot widen what the host was willing to reach.
    """

    async def dial(endpoint: NumericEndpoint, timeout: float):
        authority = (
            f"[{endpoint.address}]:{endpoint.port}"
            if endpoint.family == socket.AF_INET6
            else f"{endpoint.address}:{endpoint.port}"
        )
        token = base64.b64encode(
            f"{share.username}:{share.password}".encode("ascii")
        ).decode("ascii")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                share.host, share.port, limit=_REMOTE_HEADER_LIMIT + 1
            ),
            timeout=timeout,
        )
        try:
            writer.write(
                (
                    f"CONNECT {authority} HTTP/1.1\r\n"
                    f"Host: {authority}\r\n"
                    f"Proxy-Authorization: Basic {token}\r\n\r\n"
                ).encode("ascii")
            )
            await asyncio.wait_for(writer.drain(), timeout=timeout)
            head = await asyncio.wait_for(
                reader.readuntil(b"\r\n\r\n"), timeout=timeout
            )
            if len(head) > _REMOTE_HEADER_LIMIT:
                raise OSError("shared connection returned an invalid response")
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            asyncio.TimeoutError,
        ) as exc:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            raise OSError("shared connection returned an invalid response") from exc
        except BaseException:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            raise
        status = head.split(b" ")[1:2]
        if status != [b"200"]:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            # The sharer refused. Its reason is its own business — surfacing it
            # would let a remote caller probe someone else's network policy.
            raise OSError("shared connection refused this destination")
        return reader, writer

    return dial


def remote_proxy_resolver(share: ShareEndpoint):
    """Resolve browser destinations on the Laptop that owns the shared exit.

    The server-side browser and operating system never resolve the target.  A
    small authenticated request asks the Laptop's already-bounded egress
    service for its complete answer set; the server classifies that set again
    before selecting one numeric address, and the Laptop classifies the chosen
    address once more when CONNECT arrives.
    """

    async def resolve(host: str, port: int):
        encoded = base64.urlsafe_b64encode(host.encode("utf-8")).decode("ascii").rstrip(
            "="
        )
        token = base64.b64encode(
            f"{share.username}:{share.password}".encode("ascii")
        ).decode("ascii")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                share.host, share.port, limit=_REMOTE_HEADER_LIMIT + 1
            ),
            timeout=_REMOTE_IO_TIMEOUT,
        )
        try:
            writer.write(
                (
                    f"CORESOLVE {encoded}:{port} HTTP/1.1\r\n"
                    f"Proxy-Authorization: Basic {token}\r\n\r\n"
                ).encode("ascii")
            )
            await asyncio.wait_for(writer.drain(), timeout=_REMOTE_IO_TIMEOUT)
            head = await asyncio.wait_for(
                reader.readuntil(b"\r\n\r\n"), timeout=_REMOTE_IO_TIMEOUT
            )
            if len(head) > _REMOTE_HEADER_LIMIT:
                raise OSError("shared connection returned invalid DNS response")
            status = head.split(b" ")[1:2]
            if status != [b"200"]:
                raise OSError("shared connection refused remote DNS")
            length = None
            for line in head.split(b"\r\n")[1:]:
                name, separator, value = line.partition(b":")
                if separator and name.lower() == b"content-length":
                    length = int(value.strip())
                    break
            if length is None or not 0 < length <= 4096:
                raise OSError("shared connection returned invalid DNS response")
            body = await asyncio.wait_for(
                reader.readexactly(length), timeout=_REMOTE_IO_TIMEOUT
            )
            answers = tuple(line for line in body.decode("ascii").splitlines() if line)
            if not answers:
                raise OSError("shared connection returned no DNS answers")
            # Canonicalize before returning into EgressGateway's independent
            # frozen classifier.  A malformed Laptop response cannot reach a
            # dial call or turn into a second hostname lookup.
            return tuple(str(ipaddress.ip_address(answer)) for answer in answers)
        except (
            ValueError,
            UnicodeError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            asyncio.TimeoutError,
        ) as exc:
            raise OSError("shared connection returned invalid DNS response") from exc
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    return resolve


def shared_egress_gateway(
    share: ShareEndpoint,
    **kwargs,
) -> EgressGateway:
    """A host-private gateway whose last hop is the caller's own connection."""
    if "resolver" in kwargs or "dialer" in kwargs:
        raise ValueError("shared egress owns its resolver and dialer")
    return EgressGateway(
        resolver=remote_proxy_resolver(share),
        dialer=remote_proxy_dialer(share),
        **kwargs,
    )


__all__ = [
    "DEFAULT_TTL",
    "ProxyEndpoint",
    "ProxyShare",
    "ProxyShareRefused",
    "ShareEndpoint",
    "remote_proxy_dialer",
    "remote_proxy_resolver",
    "shared_egress_gateway",
]
