"""
Purpose: ASGI HTTP transport utilities — body reading, response sending, JSON encoding with Pydantic support
LLM-Note:
  Dependencies: imports from [pydantic.BaseModel, json] | imported by [network/host/http_router.py, network/asgi/__init__.py] | tested by [tests/unit/test_asgi_http.py]
  Data flow: read_body(receive) drains ASGI receive channel into bytes, raising RequestBodyTooLarge past the cap | send_json/send_text/send_html() write status line + headers + body via ASGI send channel | pydantic_json_encoder() serializes Pydantic models for json.dumps()'s default=
  State/Effects: stateless — pure transport helpers, no module-level state
  Integration: exposes read_body, send_json, send_text, send_html, CORS_HEADERS, pydantic_json_encoder | routing logic lives in host/http_router.py
  Performance: read_body joins chunks once (linear) and stops at MAX_HTTP_BODY_BYTES | JSON encoding with custom Pydantic serializer
  Errors: send_* helpers don't catch exceptions — caller handles | CORS_HEADERS allow cross-origin browser clients
"""

import json

from pydantic import BaseModel

from ..transport_limits import MAX_WEBSOCKET_MESSAGE_BYTES


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
    [
        b"access-control-allow-headers",
        b"authorization, content-type, x-co-from, x-co-signature, x-co-timestamp, x-co-to, x-co-request-id",
    ],
]


# The body is read before any signature can be checked, so whoever can reach
# the port decides how much of it there is. `body += chunk` copied everything
# read so far on every chunk -- quadratic, and 128 MB cost 23 s of event-loop
# CPU with nothing authenticated yet (#1752). The cap is the WebSocket's own
# message limit: POST /input carries what an INPUT frame carries (prompt,
# base64 images and files), so neither transport accepts what the other would
# refuse. Read at call time so an operator or a test can lower it.
MAX_HTTP_BODY_BYTES = MAX_WEBSOCKET_MESSAGE_BYTES


class RequestBodyTooLarge(ValueError):
    """The request body is over the cap; answered with 413 by handle_http."""


async def read_body(receive, max_bytes: int | None = None) -> bytes:
    """Read the complete request body, refusing one larger than the cap."""
    limit = MAX_HTTP_BODY_BYTES if max_bytes is None else max_bytes
    chunks, size = [], 0
    while True:
        m = await receive()
        chunk = m.get("body", b"")
        size += len(chunk)
        if size > limit:
            raise RequestBodyTooLarge(f"request body over {limit} bytes")
        chunks.append(chunk)
        if not m.get("more_body"):
            break
    return b"".join(chunks)


def declared_length_too_large(scope) -> bool:
    """True when Content-Length already says the body is over the cap.

    Lets the host answer 413 without reading a byte of it. A missing or
    malformed header proves nothing; read_body's own count still applies.
    """
    for key, value in scope.get("headers") or []:
        if key.lower() == b"content-length":
            try:
                return int(value) > MAX_HTTP_BODY_BYTES
            except ValueError:
                return False
    return False


async def send_json(
    send,
    data: dict,
    status: int = 200,
    extra_headers: list[list[bytes]] | None = None,
):
    """Send JSON response via ASGI send."""
    # Use pydantic_json_encoder to handle Pydantic models (e.g., TokenUsage) in response
    body = json.dumps(data, default=pydantic_json_encoder).encode()
    headers = [[b"content-type", b"application/json"]] + CORS_HEADERS
    if extra_headers:
        headers += extra_headers
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
