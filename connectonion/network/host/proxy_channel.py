"""A laptop's attached share, seen from the browser host.

The laptop is behind NAT, so it dials the host and stays on the socket. This
module is what the host keeps for that socket: a `ProxyChannel` that turns the
gateway's resolver/dialer calls into PROXY_STREAM frames going down to the
laptop, and a registry keyed by the laptop's address so a `start` request from
that same identity can find its own exit.

The host-private browser gateway is unchanged. It still speaks CORESOLVE and
numeric CONNECT to a "share endpoint"; that endpoint is now a second gateway on
loopback in the host process whose last hop is this channel.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import time
from datetime import datetime

from ..proxy import stream as wire
from ..proxy_egress import ShareEndpoint
from .egress_gateway import EgressGateway, NumericEndpoint


class _Stream:
    def __init__(self, stream_id: int):
        self.id = stream_id
        self.reader = asyncio.StreamReader()
        self.reply: asyncio.Future = asyncio.get_running_loop().create_future()
        self.closing = False
        self.pending = b""
        self.shutdown: asyncio.Task | None = None


class _ChannelWriter:
    """The StreamWriter half the gateway sees; bytes become data frames."""

    def __init__(self, channel: "ProxyChannel", stream: _Stream):
        self._channel = channel
        self._stream = stream

    def write(self, data: bytes) -> None:
        if not self._stream.closing:
            self._stream.pending += data

    async def drain(self) -> None:
        await self._channel._flush(self._stream)

    def can_write_eof(self) -> bool:
        return True

    def write_eof(self) -> None:
        self._later("eof")

    def is_closing(self) -> bool:
        return self._stream.closing

    def close(self) -> None:
        if self._stream.closing:
            return
        self._stream.closing = True
        self._later("close")

    async def wait_closed(self) -> None:
        if self._stream.shutdown is not None:
            await self._stream.shutdown

    def _later(self, op: str) -> None:
        # write_eof/close are synchronous on a StreamWriter; the frame goes out
        # on a task, after whatever is still buffered. The task is kept so
        # wait_closed() can await the close frame actually leaving.
        self._stream.shutdown = asyncio.create_task(
            self._channel._flush_then(self._stream, op)
        )


class ProxyChannel:
    """One attached laptop: resolve and dial through it, receive its frames."""

    def __init__(self, send, claims: dict, *, clock=time.time):
        self._send = send
        self.claims = claims
        self.owner = claims["grantor"]
        self._expires_at = datetime.fromisoformat(
            claims["expires_at"].replace("Z", "+00:00")
        ).timestamp()
        self._max_bytes = claims["max_bytes"]
        self._clock = clock
        self.bytes_used = 0
        self._streams: dict[int, _Stream] = {}
        self._next_id = 1
        self._send_lock = asyncio.Lock()
        self.closed = False
        self.gateway = EgressGateway(
            resolver=self.resolve,
            dialer=self.dial,
            username="connectonion-proxy",
            allow_remote_resolution=True,
        )

    @property
    def endpoint(self) -> ShareEndpoint:
        """Where the host's browser gateway reaches this laptop: loopback."""
        inner = self.gateway.endpoint
        return ShareEndpoint(inner.host, inner.port, inner.username, inner.password)

    # ---- the Resolver and Dialer the gateway calls ----

    async def resolve(self, host: str, port: int):
        stream = self._open("resolve")
        await self._send_stream(stream, "resolve", host=host, port=port)
        reply = await self._answer(stream)
        self._forget(stream)
        addresses = reply.get("addresses")
        if not isinstance(addresses, list) or not addresses:
            raise OSError("share returned no DNS answers")
        # Canonicalize before the gateway's own classifier sees the answer.
        return tuple(str(ipaddress.ip_address(value)) for value in addresses)

    async def dial(self, endpoint: NumericEndpoint, timeout: float):
        stream = self._open("connect")
        await self._send_stream(
            stream, "connect", address=endpoint.address, port=endpoint.port
        )
        await self._answer(stream)
        return stream.reader, _ChannelWriter(self, stream)

    # ---- frames coming up from the laptop ----

    async def receive(self, frame: dict) -> None:
        stream_id = wire.stream_id_of(frame)
        op = frame["op"]
        stream = self._streams.get(stream_id)
        if stream is None:
            if op != "close":
                await self._send(wire.stream_frame(stream_id, "close"))
            return
        if op in {"resolve", "connect"}:
            self._settle(stream, frame)
        elif op == "error":
            self._settle(stream, frame)
            self._forget(stream)
        elif op == "data":
            payload = wire.decode_data(frame)
            self._spend(len(payload))
            stream.reader.feed_data(payload)
        elif op == "eof":
            stream.reader.feed_eof()
        else:
            stream.reader.feed_eof()
            self._forget(stream)

    async def close(self) -> None:
        """The socket is gone: every stream on it is too."""
        self.closed = True
        for stream in list(self._streams.values()):
            stream.reader.feed_eof()
            self._settle(stream, wire.stream_frame(stream.id, "error", code="PROXY_DETACHED"))
        self._streams.clear()
        await self.gateway.stop()

    # ---- internals ----

    def _open(self, purpose: str) -> _Stream:
        if self.closed:
            raise OSError("share is detached")
        if self._clock() >= self._expires_at:
            raise OSError("share grant expired")
        if self._max_bytes is not None and self.bytes_used >= self._max_bytes:
            raise OSError("share byte budget spent")
        if len(self._streams) >= wire.MAX_STREAMS:
            raise OSError(f"share has {wire.MAX_STREAMS} streams open")
        stream = _Stream(self._next_id)
        self._next_id += 1
        self._streams[stream.id] = stream
        return stream

    async def _answer(self, stream: _Stream) -> dict:
        try:
            reply = await stream.reply
        except BaseException:
            self._forget(stream)
            raise
        if reply["op"] == "error":
            raise OSError(f"share refused: {reply.get('code', 'PROXY_REFUSED')}")
        return reply

    def _settle(self, stream: _Stream, frame: dict) -> None:
        if not stream.reply.done():
            stream.reply.set_result(frame)

    def _forget(self, stream: _Stream) -> None:
        stream.closing = True
        self._streams.pop(stream.id, None)

    def _spend(self, count: int) -> None:
        self.bytes_used += count
        if self._max_bytes is not None and self.bytes_used > self._max_bytes:
            raise OSError("share byte budget spent")

    async def _send_stream(self, stream: _Stream, op: str, **fields) -> None:
        if self.closed:
            raise OSError("share is detached")
        # One lock for the whole channel: frames of one stream leave in the
        # order they were written, and no two coroutines interleave a send.
        async with self._send_lock:
            await self._send(wire.stream_frame(stream.id, op, **fields))

    async def _flush(self, stream: _Stream) -> None:
        while stream.pending:
            chunk, stream.pending = (
                stream.pending[: wire.CHUNK_BYTES],
                stream.pending[wire.CHUNK_BYTES :],
            )
            self._spend(len(chunk))
            async with self._send_lock:
                await self._send(wire.data_frame(stream.id, chunk))

    async def _flush_then(self, stream: _Stream, op: str) -> None:
        with contextlib.suppress(OSError):
            await self._flush(stream)
            if stream.id in self._streams or op == "close":
                await self._send_stream(stream, op)
        if op == "close":
            self._forget(stream)


class ProxyChannelRegistry:
    """Attached channels by the laptop address that attached them.

    Read from `RemoteBrowserService.handle`, which runs on a worker thread,
    so lookups are plain dict reads and every mutation happens on the loop.
    """

    def __init__(self):
        self._channels: dict[str, ProxyChannel] = {}

    def attach(self, channel: ProxyChannel) -> ProxyChannel | None:
        """Register; returns the channel this one displaces, if any."""
        displaced = self._channels.get(channel.owner)
        self._channels[channel.owner] = channel
        return displaced

    def detach(self, channel: ProxyChannel) -> None:
        if self._channels.get(channel.owner) is channel:
            del self._channels[channel.owner]

    def get(self, address: str) -> ProxyChannel | None:
        return self._channels.get(address)

    def endpoint_for(self, address: str) -> ShareEndpoint | None:
        channel = self._channels.get(address)
        return None if channel is None else channel.endpoint
