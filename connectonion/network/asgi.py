"""Raw ASGI utilities for HTTP/WebSocket handling.

This module contains the protocol-level code for handling HTTP and WebSocket
requests. Separated from host.py for better testing and smaller file size.

Design decision: Raw ASGI instead of Starlette/FastAPI for full protocol control.
See: docs/design-decisions/022-raw-asgi-implementation.md
"""
import asyncio
import hmac
import json
import os
import queue
import threading
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel

from .connection import Connection


class AsyncToSyncConnection(Connection):
    """Bridge async WebSocket to sync Connection interface.

    Uses queues to communicate between async WebSocket handler and sync agent code.
    The agent runs in a thread, sending/receiving via queues.
    The async handler pumps messages between WebSocket and queues.
    """

    def __init__(self):
        self._outgoing: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._incoming: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._closed = False

    def send(self, event: Dict[str, Any]) -> None:
        """Queue event to be sent to client."""
        if not self._closed:
            self._outgoing.put(event)

    def receive(self) -> Dict[str, Any]:
        """Block until response from client."""
        return self._incoming.get()

    def close(self):
        """Mark connection as closed."""
        self._closed = True
        # Unblock any waiting receive
        self._incoming.put({"type": "connection_closed"})


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

    Supports bidirectional communication via Connection interface:
    - Agent sends events via connection.log() / connection.send()
    - Agent requests approval via connection.request_approval()
    - Client responds to approval requests

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

                # Create connection for bidirectional communication
                connection = AsyncToSyncConnection()
                agent_done = threading.Event()
                result_holder = [None]

                def run_agent():
                    result_holder[0] = handlers["ws_input"](prompt, connection)
                    agent_done.set()

                # Start agent in thread
                agent_thread = threading.Thread(target=run_agent, daemon=True)
                agent_thread.start()

                # Pump messages between WebSocket and connection
                await _pump_messages(receive, send, connection, agent_done)

                # Send final result
                await send({"type": "websocket.send",
                           "text": json.dumps({"type": "OUTPUT", "result": result_holder[0]})})


async def _pump_messages(ws_receive, ws_send, connection: AsyncToSyncConnection, agent_done: threading.Event):
    """Pump messages between WebSocket and connection queues.

    Runs until agent completes. Handles:
    - Outgoing: connection._outgoing queue → WebSocket
    - Incoming: WebSocket → connection._incoming queue (for approval responses)
    """
    loop = asyncio.get_event_loop()

    async def send_outgoing():
        """Send outgoing messages from connection to WebSocket."""
        while not agent_done.is_set():
            # Use run_in_executor for blocking queue.get
            try:
                event = await loop.run_in_executor(
                    None, lambda: connection._outgoing.get(timeout=0.05)
                )
                await ws_send({"type": "websocket.send", "text": json.dumps(event)})
            except queue.Empty:
                pass

        # Drain remaining
        while True:
            try:
                event = connection._outgoing.get_nowait()
                await ws_send({"type": "websocket.send", "text": json.dumps(event)})
            except queue.Empty:
                break

    async def receive_incoming():
        """Receive incoming messages from WebSocket to connection."""
        while not agent_done.is_set():
            try:
                msg = await asyncio.wait_for(ws_receive(), timeout=0.1)
                if msg["type"] == "websocket.receive":
                    try:
                        data = json.loads(msg.get("text", "{}"))
                        connection._incoming.put(data)
                    except json.JSONDecodeError:
                        pass
                elif msg["type"] == "websocket.disconnect":
                    connection.close()
                    break
            except asyncio.TimeoutError:
                continue

    # Run both tasks concurrently
    send_task = asyncio.create_task(send_outgoing())
    recv_task = asyncio.create_task(receive_incoming())

    # Wait for agent to complete
    while not agent_done.is_set():
        await asyncio.sleep(0.05)

    # Cancel receive task and wait for send to finish draining
    recv_task.cancel()
    try:
        await recv_task
    except asyncio.CancelledError:
        pass
    await send_task


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
