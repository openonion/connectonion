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


async def run_native_egress_preflight(
    name: str,
    context: Any,
    *,
    timeout: float = 8.0,
    sentinel_factory: type[LoopbackSentinel] = LoopbackSentinel,
) -> None:
    """Prove the effective Chromium proxy path or fail with one stable code.

    A 403 response proves the authenticated gateway saw and denied the owned
    loopback main-frame request.  Zero sentinel accepts proves Chromium did not
    silently take its implicit localhost DIRECT path.  Representative
    subresource, WebSocket, and worker attempts repeat the zero-socket check.
    """
    if name != REMOTE_EGRESS_PREFLIGHT:
        raise NativeEgressPreflightError(_PREFLIGHT_MESSAGE)

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
            if response is None or response.status != 502:
                raise NativeEgressPreflightError(_PREFLIGHT_MESSAGE)
            loopback_response = await asyncio.wait_for(
                page.goto(
                    sentinel.origin + "/main-frame",
                    wait_until="commit",
                    timeout=max(1000, int(timeout * 500)),
                ),
                timeout=timeout,
            )
            if loopback_response is None or loopback_response.status != 403:
                raise NativeEgressPreflightError(_PREFLIGHT_MESSAGE)
            await asyncio.wait_for(
                _exercise_subresource_paths(page, sentinel.origin),
                timeout=timeout,
            )
            await asyncio.sleep(0.1)
            if sentinel.accepted_connections or sentinel.accepted_bytes:
                raise NativeEgressPreflightError(_PREFLIGHT_MESSAGE)
    except asyncio.CancelledError:
        raise
    except NativeEgressPreflightError:
        raise
    except BaseException:
        raise NativeEgressPreflightError(_PREFLIGHT_MESSAGE) from None
    finally:
        if page is not None:
            with contextlib.suppress(BaseException):
                await page.close()
