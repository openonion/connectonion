"""
Purpose: ASGI application factory for HTTP/WebSocket handling without framework overhead
LLM-Note:
  Dependencies: imports from [asgi/http.py, asgi/websocket.py, time] | imported by [network/host/server.py, network/__init__.py] | tested by [tests/network/test_asgi.py]
  Data flow: create_app(route_handlers, storage, trust, blacklist, whitelist) → returns ASGI app callable → uvicorn calls app(scope, receive, send) → routes to handle_http() or handle_websocket() based on scope type
  State/Effects: captures start_time for uptime | no other persistent state
  Integration: exposes create_app() factory, handle_http(), handle_websocket(), _pump_messages(), CORS_HEADERS, read_body(), send_json(), send_html(), send_text() | raw ASGI (no FastAPI/Starlette) for protocol control
  Performance: minimal overhead (direct ASGI protocol) | async I/O for concurrency
  Errors: none (errors handled in http.py/websocket.py)
ASGI application for HTTP and WebSocket handling.

Raw ASGI instead of Starlette/FastAPI for full protocol control.
"""

import time

from .http import handle_http, send_json, send_html, send_text, read_body, CORS_HEADERS
from .websocket import handle_websocket, _pump_messages


def create_app(
    *,
    route_handlers: dict,
    storage,
    trust: str = "careful",
    blacklist: list | None = None,
    whitelist: list | None = None,
):
    """Create ASGI application.

    Args:
        route_handlers: Dict of route handler functions
        storage: SessionStorage instance
        trust: Trust level (open/careful/strict)
        blacklist: Blocked identities
        whitelist: Allowed identities

    Returns:
        ASGI application callable
    """
    start_time = time.time()

    async def app(scope, receive, send):
        if scope["type"] == "http":
            await handle_http(
                scope,
                receive,
                send,
                route_handlers=route_handlers,
                storage=storage,
                trust=trust,
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
