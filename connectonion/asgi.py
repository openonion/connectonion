"""Raw ASGI utilities for HTTP/WebSocket handling.

This module contains the protocol-level code for handling HTTP and WebSocket
requests. Separated from host.py for better testing and smaller file size.

Design decision: Raw ASGI instead of Starlette/FastAPI for full protocol control.
See: docs/design-decisions/022-raw-asgi-implementation.md
"""
import json
from pathlib import Path


async def read_body(receive) -> bytes:
    """Read complete request body from ASGI receive."""
    body = b""
    while True:
        m = await receive()
        body += m.get("body", b"")
        if not m.get("more_body"):
            break
    return body


async def send_json(send, data: dict, status: int = 200):
    """Send JSON response via ASGI send."""
    body = json.dumps(data).encode()
    await send({"type": "http.response.start", "status": status,
               "headers": [[b"content-type", b"application/json"]]})
    await send({"type": "http.response.body", "body": body})


async def send_html(send, html: bytes, status: int = 200):
    """Send HTML response via ASGI send."""
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [[b"content-type", b"text/html; charset=utf-8"]],
    })
    await send({"type": "http.response.body", "body": html})


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
