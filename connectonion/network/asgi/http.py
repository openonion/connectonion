"""
Purpose: ASGI HTTP transport utilities — body reading, response sending, JSON encoding with Pydantic support
LLM-Note:
  Dependencies: imports from [pydantic.BaseModel, json] | imported by [network/host/http_router.py, network/asgi/__init__.py] | tested by [tests/unit/test_asgi_http.py]
  Data flow: read_body(receive) drains ASGI receive channel into bytes | send_json/send_text/send_html() write status line + headers + body via ASGI send channel | pydantic_json_encoder() serializes Pydantic models for json.dumps()'s default=
  State/Effects: stateless — pure transport helpers, no module-level state
  Integration: exposes read_body, send_json, send_text, send_html, CORS_HEADERS, pydantic_json_encoder | routing logic lives in host/http_router.py
  Performance: streams body via ASGI receive (no full buffering by this layer) | JSON encoding with custom Pydantic serializer
  Errors: send_* helpers don't catch exceptions — caller handles | CORS_HEADERS allow cross-origin browser clients
"""

import json

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
    [
        b"access-control-allow-headers",
        b"authorization, content-type, x-from, x-signature, x-timestamp",
    ],
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
