"""
Purpose: ASGI application factory for HTTP/WebSocket handling without framework overhead
LLM-Note:
  Dependencies: imports from [asgi/http.py, asgi/websocket.py, time, asyncio] | imported by [network/host/server.py, network/__init__.py] | tested by [tests/network/test_asgi.py]
  Data flow: create_app(route_handlers, storage, trust, blacklist, whitelist, on_startup, on_shutdown) → returns ASGI app callable → uvicorn calls app(scope, receive, send) → handles lifespan for startup/shutdown → routes to handle_http() or handle_websocket() based on scope type
  State/Effects: captures start_time for uptime | runs on_startup/on_shutdown callbacks during lifespan | relay connection runs as async task in same event loop
  Integration: exposes create_app() factory, handle_http(), handle_websocket(), _pump_messages(), CORS_HEADERS, read_body(), send_json(), send_html(), send_text() | raw ASGI (no FastAPI/Starlette) for protocol control | lifespan support for relay connection
  Performance: minimal overhead (direct ASGI protocol) | async I/O for concurrency | single event loop for HTTP, WebSocket, and relay
  Errors: none (errors handled in http.py/websocket.py)
ASGI application for HTTP and WebSocket handling.

Raw ASGI instead of Starlette/FastAPI for full protocol control.
Supports ASGI lifespan for startup/shutdown hooks (relay connection).
"""

import time
import asyncio
from typing import Callable, Awaitable

from .http import handle_http, send_json, send_html, send_text, read_body, CORS_HEADERS
from .websocket import handle_websocket, _pump_messages


def create_app(
    *,
    route_handlers: dict,
    storage,
    trust: str = "careful",
    trust_config: dict | None = None,
    blacklist: list | None = None,
    whitelist: list | None = None,
    on_startup: Callable[[], Awaitable[None]] | None = None,
    on_shutdown: Callable[[], Awaitable[None]] | None = None,
):
    """Create ASGI application with lifespan support.

    Args:
        route_handlers: Dict of route handler functions
        storage: SessionStorage instance
        trust: Trust level (open/careful/strict)
        trust_config: Parsed YAML config from trust policy (for /info onboard)
        blacklist: Blocked identities
        whitelist: Allowed identities
        on_startup: Async function to run on startup (e.g., start relay connection)
        on_shutdown: Async function to run on shutdown (e.g., close relay connection)

    Returns:
        ASGI application callable
    """
    start_time = time.time()

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            # Handle ASGI lifespan protocol
            # This runs startup/shutdown hooks in uvicorn's event loop
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    try:
                        if on_startup:
                            await on_startup()
                        await send({"type": "lifespan.startup.complete"})
                    except Exception as e:
                        await send({"type": "lifespan.startup.failed", "message": str(e)})
                        return
                elif message["type"] == "lifespan.shutdown":
                    try:
                        if on_shutdown:
                            await on_shutdown()
                        await send({"type": "lifespan.shutdown.complete"})
                    except Exception:
                        await send({"type": "lifespan.shutdown.complete"})
                    return

        elif scope["type"] == "http":
            await handle_http(
                scope,
                receive,
                send,
                route_handlers=route_handlers,
                storage=storage,
                trust=trust,
                trust_config=trust_config,
                start_time=start_time,
                blacklist=blacklist,
                whitelist=whitelist,
            )
        elif scope["type"] == "websocket":
            await handle_websocket(
                scope,
                receive,
                send,
                route_handlers=route_handlers,
                storage=storage,
                trust=trust,
                blacklist=blacklist,
                whitelist=whitelist,
            )

    return app


__all__ = [
    "create_app",
    "handle_http",
    "handle_websocket",
    "_pump_messages",
    "CORS_HEADERS",
    "read_body",
    "send_json",
    "send_html",
    "send_text",
]
