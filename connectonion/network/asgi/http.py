"""
Purpose: HTTP request/response handling for ASGI server with Pydantic serialization
LLM-Note:
  Dependencies: imports from [pydantic.BaseModel, json, hmac, os, pathlib] | imported by [network/asgi/__init__.py] | tested by [tests/network/test_asgi_http.py]
  Data flow: handle_http() receives ASGI scope/receive/send → reads body via read_body() → parses JSON → routes to handlers (POST /input, GET /sessions, etc.) → sends response via send_json()/send_text()/send_html() | pydantic_json_encoder() serializes Pydantic models (e.g., TokenUsage) in responses | OPTIONS requests return CORS headers
  State/Effects: reads request body from ASGI receive channel | writes response to ASGI send channel | no persistent state (stateless handler)
  Integration: exposes read_body(receive) → bytes, send_json(send, data, status), send_text(send, text, status), send_html(send, html, status), handle_http(scope, receive, send, route_handlers, storage, trust, start_time, blacklist, whitelist) | pydantic_json_encoder(obj) as default for json.dumps() | CORS_HEADERS for cross-origin requests
  Performance: streams body reading via ASGI receive | JSON encoding with custom Pydantic serializer | CORS headers allow browser clients
  Errors: returns 401 for auth failures | 403 for trust violations | 404 for missing sessions/routes | 500 for handler exceptions | OPTIONS requests return 200 with CORS
HTTP request handling for ASGI.

This module provides HTTP request/response utilities for the ASGI server,
including JSON serialization with Pydantic model support.
"""

import hmac
import json
import os
from pathlib import Path

from pydantic import BaseModel


def pydantic_json_encoder(obj):
    """Custom JSON encoder that serializes Pydantic models to dictionaries.

    Used as the `default` parameter for json.dumps() to handle Pydantic models
    that would otherwise raise TypeError during JSON serialization.

    This is needed because agent responses may contain Pydantic models like
    TokenUsage, and we need to serialize them to JSON for HTTP/WebSocket responses.

    Args:
        obj: The object to serialize. If it's a Pydantic BaseModel,
             returns obj.model_dump(). Otherwise raises TypeError.

    Returns:
        dict: The serialized Pydantic model as a dictionary.

    Raises:
        TypeError: If obj is not a Pydantic BaseModel.

    Example:
        >>> json.dumps({"usage": TokenUsage(input=10, output=5)},
        ...            default=pydantic_json_encoder)
        '{"usage": {"input": 10, "output": 5}}'
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    # Fallback: convert unknown objects to string representation
    # Log warning to help debug where non-serializable objects come from
    import logging
    logging.getLogger(__name__).warning(f"Non-JSON-serializable object: {type(obj).__name__}")
    return f"<{type(obj).__name__}>"


# CORS headers for cross-origin requests
CORS_HEADERS = [
    [b"access-control-allow-origin", b"*"],
    [b"access-control-allow-methods", b"GET, POST, OPTIONS"],
    [b"access-control-allow-headers", b"authorization, content-type"],
]


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
    # Use pydantic_json_encoder to handle Pydantic models (e.g., TokenUsage) in response
    body = json.dumps(data, default=pydantic_json_encoder).encode()
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
    route_handlers: dict,
    storage,
    trust: str,
    trust_config: dict | None = None,
    start_time: float,
    blacklist: list | None = None,
    whitelist: list | None = None,
):
    """Route HTTP requests to route handlers.

    Args:
        scope: ASGI scope dict (method, path, headers, etc.)
        receive: ASGI receive callable
        send: ASGI send callable
        route_handlers: Dict of route handler functions (input, session, sessions, health, info, auth)
        storage: SessionStorage instance
        trust: Trust level (open/careful/strict)
        trust_config: Parsed YAML config from trust policy (for /info onboard)
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

    # Admin endpoints
    if path.startswith("/admin"):
        # Legacy admin endpoints (Bearer token auth)
        if path in ["/admin/logs", "/admin/sessions"]:
            headers_dict = dict(scope.get("headers", []))
            auth = headers_dict.get(b"authorization", b"").decode()
            expected = os.environ.get("OPENONION_API_KEY", "")
            if not expected or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], expected):
                await send_json(send, {"error": "unauthorized"}, 401)
                return

            if method == "GET" and path == "/admin/logs":
                result = route_handlers["admin_logs"]()
                if "error" in result:
                    await send_json(send, result, 404)
                else:
                    await send_text(send, result["content"])
                return

            if method == "GET" and path == "/admin/sessions":
                await send_json(send, route_handlers["admin_sessions"]())
                return

        # Admin trust routes (signed request + admin check)
        if path.startswith("/admin/trust/") or path.startswith("/superadmin/"):
            trust_agent = route_handlers["trust_agent"]

            # For GET requests, allow auth via headers (bodies often stripped by proxies)
            headers_dict = dict(scope.get("headers", []))
            header_from = headers_dict.get(b"x-from", b"").decode()
            header_sig = headers_dict.get(b"x-signature", b"").decode()
            header_ts = headers_dict.get(b"x-timestamp", b"").decode()

            if method == "GET" and header_from and header_sig and header_ts:
                # Build signed request from headers
                try:
                    data = {
                        "payload": {"timestamp": float(header_ts)},
                        "from": header_from,
                        "signature": header_sig
                    }
                except ValueError:
                    await send_json(send, {"error": "Invalid X-Timestamp header"}, 400)
                    return
            else:
                # Read from body (POST or GET without headers)
                body = await read_body(receive)
                try:
                    data = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    await send_json(send, {"error": "Invalid JSON"}, 400)
                    return

            # Authenticate signed request (reuse same auth as /input, but with "open" trust)
            _, identity, sig_valid, err = route_handlers["auth"](data, "open")
            if err or not sig_valid:
                await send_json(send, {"error": err or "unauthorized: invalid signature"}, 401)
                return

            # Check admin permission
            if path.startswith("/superadmin/"):
                # Super admin only (self address)
                if not trust_agent.is_super_admin(identity):
                    await send_json(send, {"error": "forbidden: super admin only"}, 403)
                    return
            else:
                # Any admin
                if not trust_agent.is_admin(identity):
                    await send_json(send, {"error": "forbidden: admin only"}, 403)
                    return

            payload = data.get("payload", {})
            client_id = payload.get("client_id")

            # Route to handlers
            if method == "POST" and path == "/admin/trust/promote":
                if not client_id:
                    await send_json(send, {"error": "client_id required"}, 400)
                    return
                await send_json(send, route_handlers["admin_trust_promote"](client_id))
                return

            if method == "POST" and path == "/admin/trust/demote":
                if not client_id:
                    await send_json(send, {"error": "client_id required"}, 400)
                    return
                await send_json(send, route_handlers["admin_trust_demote"](client_id))
                return

            if method == "POST" and path == "/admin/trust/block":
                if not client_id:
                    await send_json(send, {"error": "client_id required"}, 400)
                    return
                reason = payload.get("reason", "")
                await send_json(send, route_handlers["admin_trust_block"](client_id, reason))
                return

            if method == "POST" and path == "/admin/trust/unblock":
                if not client_id:
                    await send_json(send, {"error": "client_id required"}, 400)
                    return
                await send_json(send, route_handlers["admin_trust_unblock"](client_id))
                return

            if method == "GET" and path.startswith("/admin/trust/level/"):
                client_id = path[len("/admin/trust/level/"):]
                await send_json(send, route_handlers["admin_trust_level"](client_id))
                return

            if method == "POST" and path == "/superadmin/add":
                admin_id = payload.get("admin_id")
                if not admin_id:
                    await send_json(send, {"error": "admin_id required"}, 400)
                    return
                await send_json(send, route_handlers["admin_admins_add"](admin_id))
                return

            if method == "POST" and path == "/superadmin/remove":
                admin_id = payload.get("admin_id")
                if not admin_id:
                    await send_json(send, {"error": "admin_id required"}, 400)
                    return
                await send_json(send, route_handlers["admin_admins_remove"](admin_id))
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

        prompt, identity, sig_valid, err = route_handlers["auth"](
            data, trust, blacklist=blacklist, whitelist=whitelist
        )
        if err:
            status = 401 if err.startswith("unauthorized") else 403 if err.startswith("forbidden") else 400
            await send_json(send, {"error": err}, status)
            return

        # Extract session for conversation continuation
        session = data.get("session")
        result = route_handlers["input"](storage, prompt, session)
        await send_json(send, result)

    elif method == "GET" and path.startswith("/sessions/"):
        result = route_handlers["session"](storage, path[10:])
        await send_json(send, result or {"error": "not found"}, 404 if not result else 200)

    elif method == "GET" and path == "/sessions":
        await send_json(send, route_handlers["sessions"](storage))

    elif method == "GET" and path == "/health":
        await send_json(send, route_handlers["health"](start_time))

    elif method == "GET" and path == "/info":
        await send_json(send, route_handlers["info"](trust, trust_config))

    elif method == "GET" and path == "/docs":
        # Serve static docs page
        try:
            base = Path(__file__).resolve().parent.parent
            html_path = base / "static" / "docs.html"
            html = html_path.read_bytes()
        except Exception:
            html = b"<html><body><h1>ConnectOnion Docs</h1><p>Docs not found.</p></body></html>"
        await send_html(send, html)

    else:
        await send_json(send, {"error": "not found"}, 404)
