"""JSON-RPC boundary rules shared by ConnectOnion ACP transports.

Method-specific validation remains owned by the pinned SDK. This module keeps
stdio and WebSocket aligned on envelope families, preserves canonical wire
names, and blocks metadata keys that the pinned SDK router would otherwise
promote over validated request fields.
"""

from __future__ import annotations

from typing import Any

from acp import AGENT_METHODS, CLIENT_METHODS
from acp.schema import (
    CancelNotification,
    CloseSessionRequest,
    InitializeRequest,
    NewSessionRequest,
    PromptRequest,
    RequestPermissionRequest,
    ResumeSessionRequest,
    SessionNotification,
    SetSessionModeRequest,
)

_ROUTED_PARAM_MODELS = {
    AGENT_METHODS["initialize"]: InitializeRequest,
    AGENT_METHODS["session_new"]: NewSessionRequest,
    AGENT_METHODS["session_resume"]: ResumeSessionRequest,
    AGENT_METHODS["session_set_mode"]: SetSessionModeRequest,
    AGENT_METHODS["session_prompt"]: PromptRequest,
    AGENT_METHODS["session_close"]: CloseSessionRequest,
    AGENT_METHODS["session_cancel"]: CancelNotification,
    CLIENT_METHODS["session_update"]: SessionNotification,
    CLIENT_METHODS["session_request_permission"]: RequestPermissionRequest,
}
_ROUTED_PARAM_NAMES = {
    method: frozenset(model.model_fields) - {"field_meta"}
    for method, model in _ROUTED_PARAM_MODELS.items()
}
_ROUTED_WIRE_PARAM_NAMES = {
    method: frozenset(
        field.alias or name
        for name, field in model.model_fields.items()
    )
    for method, model in _ROUTED_PARAM_MODELS.items()
}
ACP_META_SHADOW_ERROR_DETAILS = "ACP _meta cannot override request parameters"
ACP_WIRE_PARAM_ERROR_DETAILS = "ACP params must use protocol field names"


def is_acp_request_id(value: Any) -> bool:
    """Return whether value is a supported ACP correlation ID."""

    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def acp_request_id(message: Any) -> str | int | None:
    """Return a reflectable correlation ID from an arbitrary message."""

    if not isinstance(message, dict):
        return None
    request_id = message.get("id")
    return request_id if is_acp_request_id(request_id) else None


def acp_meta_shadows_request_params(message: Any) -> bool:
    """Detect metadata keys that the pinned SDK would promote over ACP fields."""

    if not isinstance(message, dict):
        return False
    reserved = _ROUTED_PARAM_NAMES.get(message.get("method"))
    params = message.get("params")
    if reserved is None or not isinstance(params, dict):
        return False
    metadata = params.get("_meta")
    return isinstance(metadata, dict) and not reserved.isdisjoint(metadata)


def acp_params_use_protocol_field_names(message: Any) -> bool:
    """Return whether routed params use only pinned protocol field names."""

    if not isinstance(message, dict):
        return True
    allowed = _ROUTED_WIRE_PARAM_NAMES.get(message.get("method"))
    params = message.get("params")
    if allowed is None or not isinstance(params, dict):
        return True
    return set(params).issubset(allowed)


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
