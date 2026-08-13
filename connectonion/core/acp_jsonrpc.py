"""Exact JSON-RPC envelope rules shared by native ACP transports.

Method-specific ACP schemas remain owned by the pinned SDK. This module only
keeps stdio and WebSocket from disagreeing about request, notification, and
response envelope families before those schemas run.
"""

from __future__ import annotations

from typing import Any


def is_acp_request_id(value: Any) -> bool:
    """Return whether value is a supported ACP correlation ID."""

    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def acp_request_id(message: Any) -> str | int | None:
    """Return a reflectable correlation ID from an arbitrary message."""

    if not isinstance(message, dict):
        return None
    request_id = message.get("id")
    return request_id if is_acp_request_id(request_id) else None


def is_acp_json_rpc_message(message: Any) -> bool:
    """Validate one exact JSON-RPC envelope family, not method semantics."""

    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return False
    if "method" in message:
        if not set(message).issubset({"jsonrpc", "id", "method", "params"}):
            return False
        if not isinstance(message["method"], str):
            return False
        if "id" in message and not is_acp_request_id(message["id"]):
            return False
        return "params" not in message or isinstance(message["params"], (dict, list))

    has_result = "result" in message
    has_error = "error" in message
    if "id" not in message or has_result == has_error:
        return False
    expected = {"jsonrpc", "id", "result" if has_result else "error"}
    return set(message) == expected and is_acp_request_id(message["id"])
