"""Raw ASGI utilities for HTTP/WebSocket handling.

This module contains the protocol-level code for handling HTTP and WebSocket
requests. Separated from host.py for better testing and smaller file size.

Design decision: Raw ASGI instead of Starlette/FastAPI for full protocol control.
See: docs/design-decisions/022-raw-asgi-implementation.md
"""
import hmac
import json
import os
from pathlib import Path

from pydantic import BaseModel


def _json_default(obj):
    """Handle non-serializable objects like Pydantic models.

    This enables native JSON serialization for Pydantic BaseModel instances
    nested in API response dicts, following FastAPI's pattern.
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def read_body(receive) -> bytes:
    """Read complete request body from ASGI receive."""
    body = b""
    while True:
        m = await receive()
        body += m.get("body", b"")
        if not m.get("more_body"):
            break
    return body


# CORS headers for cross-origin requests (e.g., frontend at o.openonion.ai
# calling deployed agents at *.agents.openonion.ai)
CORS_HEADERS = [
    [b"access-control-allow-origin", b"*"],
    [b"access-control-allow-methods", b"GET, POST, OPTIONS"],
    [b"access-control-allow-headers", b"authorization, content-type"],
]


async def send_json(send, data: dict, status: int = 200):
    """Send JSON response via ASGI send."""
    body = json.dumps(data, default=_json_default).encode()
    headers = [[b"content-type", b"application/json"]] + CORS_HEADERS
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def send_html(send, html: bytes, status: int = 200):
    """Send HTML response via ASGI send."""
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [[b"content-type", b"text/html; charset=utf-8"]],
    })
    await send({"type": "http.response.body", "body": html})


async def send_text(send, text: str, status: int = 200):
    """Send plain text response via ASGI send."""
    headers = [[b"content-type", b"text/plain; charset=utf-8"]] + CORS_HEADERS
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": text.encode()})


async def handle_http(
    scope,
    receive,
    send,
    *,
    handlers: dict,
    storage,
    trust: str,
    result_ttl: int,
    start_time: float,
    blacklist: list | None = None,
    whitelist: list | None = None,
):
    """Route HTTP requests to handlers.

    Args:
        scope: ASGI scope dict (method, path, headers, etc.)
        receive: ASGI receive callable
        send: ASGI send callable
        handlers: Dict of handler functions (input, session, sessions, health, info, auth)
        storage: SessionStorage instance
        trust: Trust level (open/careful/strict)
        result_ttl: How long to keep results in seconds
        start_time: Server start time
        blacklist: Blocked identities
        whitelist: Allowed identities
    """
    method, path = scope["method"], scope["path"]

    # Handle CORS preflight requests
    if method == "OPTIONS":
        headers = CORS_HEADERS + [[b"content-length", b"0"]]
        await send({"type": "http.response.start", "status": 204, "headers": headers})
        await send({"type": "http.response.body", "body": b""})
        return

    # Admin endpoints require API key auth
    if path.startswith("/admin"):
        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()
        expected = os.environ.get("OPENONION_API_KEY", "")
        if not expected or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], expected):
            await send_json(send, {"error": "unauthorized"}, 401)
            return

        if method == "GET" and path == "/admin/logs":
            result = handlers["admin_logs"]()
            if "error" in result:
                await send_json(send, result, 404)
            else:
                await send_text(send, result["content"])
            return

        if method == "GET" and path == "/admin/sessions":
            await send_json(send, handlers["admin_sessions"]())
            return

        await send_json(send, {"error": "not found"}, 404)
        return

    if method == "POST" and path == "/input":
        body = await read_body(receive)
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            await send_json(send, {"error": "Invalid JSON"}, 400)
            return

        prompt, identity, sig_valid, err = handlers["auth"](
            data, trust, blacklist=blacklist, whitelist=whitelist
        )
        if err:
            status = 401 if err.startswith("unauthorized") else 403 if err.startswith("forbidden") else 400
            await send_json(send, {"error": err}, status)
            return

        # Extract session for conversation continuation
        session = data.get("session")
        result = handlers["input"](storage, prompt, result_ttl, session)
        await send_json(send, result)

    elif method == "GET" and path.startswith("/sessions/"):
        result = handlers["session"](storage, path[10:])
        await send_json(send, result or {"error": "not found"}, 404 if not result else 200)

    elif method == "GET" and path == "/sessions":
        await send_json(send, handlers["sessions"](storage))

    elif method == "GET" and path == "/health":
        await send_json(send, handlers["health"](start_time))

    elif method == "GET" and path == "/info":
        await send_json(send, handlers["info"](trust))

    elif method == "GET" and path == "/docs":
        # Serve static docs page
        try:
            base = Path(__file__).resolve().parent
            html_path = base / "static" / "docs.html"
            html = html_path.read_bytes()
        except Exception:
            html = b"<html><body><h1>ConnectOnion Docs</h1><p>Docs not found.</p></body></html>"
        await send_html(send, html)

    else:
        await send_json(send, {"error": "not found"}, 404)


async def handle_websocket(
    scope,
    receive,
    send,
    *,
    handlers: dict,
    trust: str,
    blacklist: list | None = None,
    whitelist: list | None = None,
):
    """Handle WebSocket connections at /ws.

    Args:
        scope: ASGI scope dict
        receive: ASGI receive callable
        send: ASGI send callable
        handlers: Dict with 'ws_input' and 'auth' handlers
        trust: Trust level
        blacklist: Blocked identities
        whitelist: Allowed identities
    """
    if scope["path"] != "/ws":
        await send({"type": "websocket.close", "code": 4004})
        return

    await send({"type": "websocket.accept"})

    while True:
        msg = await receive()
        if msg["type"] == "websocket.disconnect":
            break
        if msg["type"] == "websocket.receive":
            try:
                data = json.loads(msg.get("text", "{}"))
            except json.JSONDecodeError:
                await send({"type": "websocket.send",
                           "text": json.dumps({"type": "ERROR", "message": "Invalid JSON"})})
                continue

            if data.get("type") == "INPUT":
                prompt, identity, sig_valid, err = handlers["auth"](
                    data, trust, blacklist=blacklist, whitelist=whitelist
                )
                if err:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": err})})
                    continue
                if not prompt:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": "prompt required"})})
                    continue
                result = handlers["ws_input"](prompt)
                await send({"type": "websocket.send",
                           "text": json.dumps({"type": "OUTPUT", "result": result})})


def create_app(
    *,
    handlers: dict,
    storage,
    trust: str = "careful",
    result_ttl: int = 86400,
    blacklist: list | None = None,
    whitelist: list | None = None,
):
    """Create ASGI application.

    Args:
        handlers: Dict of handler functions
        storage: SessionStorage instance
        trust: Trust level (open/careful/strict)
        result_ttl: How long to keep results in seconds
        blacklist: Blocked identities
        whitelist: Allowed identities

    Returns:
        ASGI application callable
    """
    import time
    start_time = time.time()

    async def app(scope, receive, send):
        if scope["type"] == "http":
            await handle_http(
                scope,
                receive,
                send,
                handlers=handlers,
                storage=storage,
                trust=trust,
                result_ttl=result_ttl,
                start_time=start_time,
                blacklist=blacklist,
                whitelist=whitelist,
            )
        elif scope["type"] == "websocket":
            await handle_websocket(
                scope,
                receive,
                send,
                handlers=handlers,
                trust=trust,
                blacklist=blacklist,
                whitelist=whitelist,
            )

    return app
