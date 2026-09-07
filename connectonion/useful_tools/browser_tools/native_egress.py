"""Effective-runtime preflight for the Host-private browser boundary.

The launch policy is only a request to Chromium.  This module verifies the
result: the real browser must reach the authenticated gateway for a loopback
request, while an owned loopback sentinel observes zero direct sockets.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
from typing import Any

REMOTE_EGRESS_PREFLIGHT = "remote-egress-v1"
PREFLIGHT_FAILED = "EGRESS_PREFLIGHT_FAILED"
_PREFLIGHT_MESSAGE = (
    f"{PREFLIGHT_FAILED}: native browser egress boundary could not be proven"
)


class NativeEgressPreflightError(RuntimeError):
    """Stable, non-secret failure returned when effective egress is uncertain."""


def native_egress_failure() -> NativeEgressPreflightError:
    """Construct the one public error for private launch or preflight uncertainty."""
    return NativeEgressPreflightError(_PREFLIGHT_MESSAGE)


class LoopbackSentinel:
    """Owned HTTP sentinel whose accepted sockets prove a proxy bypass."""

    def __init__(self) -> None:
        self.accepted_connections = 0
        self.accepted_bytes = 0
        self._server: asyncio.AbstractServer | None = None
        self._tasks: set[asyncio.Task] = set()
        self._writers: set[asyncio.StreamWriter] = set()

    @property
    def origin(self) -> str:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("loopback sentinel is not started")
        host, port = self._server.sockets[0].getsockname()[:2]
        return f"http://{host}:{port}"

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("loopback sentinel is already started")
        self._server = await asyncio.start_server(
            self._accept,
            host="127.0.0.1",
            port=0,
            family=socket.AF_INET,
        )
        sockets = self._server.sockets or ()
        if len(sockets) != 1 or sockets[0].getsockname()[0] != "127.0.0.1":
            await self.stop()
            raise RuntimeError("loopback sentinel escaped IPv4 loopback")

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        self._writers.add(writer)
        self.accepted_connections += 1
        try:
            with contextlib.suppress(asyncio.TimeoutError):
                data = await asyncio.wait_for(reader.read(4096), timeout=0.5)
                self.accepted_bytes += len(data)
            writer.write(
                b"HTTP/1.1 204 No Content\r\n"
                b"Content-Length: 0\r\n"
                b"Connection: close\r\n\r\n"
            )
            with contextlib.suppress(
                BrokenPipeError, ConnectionResetError, asyncio.TimeoutError
            ):
                await asyncio.wait_for(writer.drain(), timeout=0.5)
        finally:
            writer.close()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                await writer.wait_closed()
            self._writers.discard(writer)
            if task is not None:
                self._tasks.discard(task)

    async def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
            await server.wait_closed()
        for writer in tuple(self._writers):
            writer.close()
        tasks = tuple(task for task in self._tasks if not task.done())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._writers.clear()
        self._tasks.clear()

    async def __aenter__(self) -> "LoopbackSentinel":
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.stop()


async def _exercise_subresource_paths(page: Any, origin: str) -> None:
    """Start representative browser-owned transports and bound every wait."""
    await page.set_content("<!doctype html><meta charset=utf-8><title>egress preflight</title>")
    await page.evaluate(
        """
        async (origin) => {
          const deadline = (ms) => new Promise(resolve => setTimeout(resolve, ms));
          const bounded = promise => Promise.race([promise, deadline(1500)]);
          const image = new Promise(resolve => {
            const node = new Image();
            node.onload = node.onerror = resolve;
            node.src = origin + "/image";
          });
          const websocket = new Promise(resolve => {
            let socket;
            try {
              socket = new WebSocket(origin.replace(/^http/, "ws") + "/websocket");
              socket.onopen = () => { socket.close(); resolve(); };
              socket.onerror = socket.onclose = resolve;
            } catch (_) {
              resolve();
            }
          });
          const worker = new Promise(resolve => {
            const source = `fetch(${JSON.stringify(origin + "/worker")})`
              + `.catch(() => {}).finally(() => postMessage("done"));`;
            const url = URL.createObjectURL(new Blob([source], {type: "text/javascript"}));
            const instance = new Worker(url);
            instance.onmessage = instance.onerror = () => {
              instance.terminate();
              URL.revokeObjectURL(url);
              resolve();
            };
          });
          await Promise.all([
            bounded(fetch(origin + "/fetch", {mode: "no-cors"}).catch(() => {})),
            bounded(image),
            bounded(websocket),
            bounded(worker),
          ]);
        }
        """,
        origin,
    )


GATEWAY_WITNESS_HEADER = "x-connectonion-error"


def _require_gateway_denial(response: Any) -> None:
    """Require a denial that this gateway, authenticated, produced.

    Two independent things have to hold and neither implies the other. The
    header proves the answer came from this gateway — no origin, captive
    portal or intermediary on this path emits it, and a bare status would
    accept a 403 from whatever the browser happened to reach. The status
    proves the request was decided rather than turned away at the door: a 407
    also carries the header, and it means the credential never arrived, which
    is a misconfigured browser reported as a proven one.
    """
    if response is None:
        raise native_egress_failure()
    try:
        headers = response.headers
        witness = headers.get(GATEWAY_WITNESS_HEADER) if headers else None
        status = response.status
    except Exception:
        raise native_egress_failure() from None
    if not witness or status != 403:
        raise native_egress_failure()


def _gateway_request_count(gateway: Any) -> int | None:
    """Read the gateway's own decision count, when the caller supplied one."""
    count = getattr(gateway, "handled_requests", None)
    return count if isinstance(count, int) else None


async def run_native_egress_preflight(
    name: str,
    context: Any,
    *,
    timeout: float = 8.0,
    sentinel_factory: type[LoopbackSentinel] = LoopbackSentinel,
    gateway: Any = None,
) -> None:
    """Prove the effective Chromium proxy path or fail with one stable code.

    Each probe must be answered by *this* gateway, identified by the
    ``X-ConnectOnion-Error`` header no other party on the path produces.
    Matching a bare status would accept a 403 from anything the browser could
    reach.  Zero sentinel accepts then proves Chromium did not take its
    implicit localhost DIRECT path.

    Zero is also what "the request was never made" looks like, so the gateway's
    own request count is read before and after: an absence is only evidence
    once the thing that would have produced a presence is known to have run.
    """
    if name != REMOTE_EGRESS_PREFLIGHT:
        raise native_egress_failure()

    page = None
    try:
        async with sentinel_factory() as sentinel:
            page = await context.new_page()
            # .invalid is reserved never to resolve.  A 502 response therefore
            # proves this exact browser reached the authenticated gateway and
            # let the gateway own DNS; a direct browser path fails locally under
            # the fixed host-resolver rule and cannot manufacture that response.
            response = await asyncio.wait_for(
                page.goto(
                    "http://remote-browser-preflight.invalid/",
                    wait_until="commit",
                    # Let the driver report first; the outer deadline is only a
                    # guard against a driver call that never resolves.
                    timeout=max(1000, int(timeout * 500)),
                ),
                timeout=timeout,
            )
            # `.invalid` is reserved never to resolve, and the destination
            # policy denies it by name before DNS is consulted at all — so the
            # gateway answers HOST_DENIED, not the DNS witness an earlier
            # revision expected. What proves the browser got here is the
            # header: a direct path fails locally under the fixed host-resolver
            # rule and cannot manufacture it.
            _require_gateway_denial(response)
            loopback_response = await asyncio.wait_for(
                page.goto(
                    sentinel.origin + "/main-frame",
                    wait_until="commit",
                    timeout=max(1000, int(timeout * 500)),
                ),
                timeout=timeout,
            )
            _require_gateway_denial(loopback_response)
            before = _gateway_request_count(gateway)
            await asyncio.wait_for(
                _exercise_subresource_paths(page, sentinel.origin),
                timeout=timeout,
            )
            await asyncio.sleep(0.1)
            if sentinel.accepted_connections or sentinel.accepted_bytes:
                raise native_egress_failure()
            # The subresource probes are wrapped in a bounded race that
            # swallows their own errors, so a probe that silently did nothing —
            # a wrong URL, a blocked API, an await that resolves on the timer —
            # leaves exactly the zero-socket reading a correctly proxied one
            # leaves. Requiring the gateway to have decided at least one more
            # request separates "denied" from "never attempted".
            if before is not None and _gateway_request_count(gateway) <= before:
                raise native_egress_failure()
    except asyncio.CancelledError:
        raise
    except NativeEgressPreflightError:
        raise
    except BaseException:
        raise native_egress_failure() from None
    finally:
        if page is not None:
            with contextlib.suppress(BaseException):
                await page.close()
