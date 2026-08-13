"""ACP-native events carried over the authenticated ConnectOnion socket.

The Host WebSocket also transports ConnectOnion authentication, onboarding,
session persistence, and dashboard frames, so it is not an ACP connection. An
``ACP_NOTIFICATION`` and ``ACP_REQUEST`` frames carry exact nested ACP JSON-RPC
messages without pretending that the surrounding socket negotiated ACP
capabilities.
"""

from __future__ import annotations

from typing import Any, Mapping

from acp import text_block, tool_content
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentRequest,
    AgentThoughtChunk,
    CancelNotification,
    CurrentModeUpdate,
    PermissionOption,
    RequestPermissionRequest,
    RequestPermissionResponse,
    SessionMode,
    SessionModeState,
    SessionNotification,
    SetSessionModeRequest,
    SetSessionModeResponse,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
)
from acp.schema import PlanEntry as ACPPlanEntry

from .approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    PERMISSION_PROFILE_IDS,
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
    legacy_permission_profile_id,
    permission_profile_id,
)
from .wire_events import normalize_wire_event

ACP_FRAME_TYPE = "ACP_NOTIFICATION"
ACP_REQUEST_FRAME_TYPE = "ACP_REQUEST"
ACP_RESPONSE_FRAME_TYPE = "ACP_RESPONSE"
ACP_SCHEMA_VERSION = "schema-v1.19.0"
ACP_SESSION_UPDATE_METHOD = "session/update"
ACP_PERMISSION_METHOD = "session/request_permission"
ACP_CANCEL_METHOD = "session/cancel"
ACP_SET_SESSION_MODE_METHOD = "session/set_mode"
ACP_SESSION_MODE_IDS = PERMISSION_PROFILE_IDS

ACP_SESSION_MODES = {
    READ_ONLY_PERMISSION_PROFILE: SessionMode(
        id=READ_ONLY_PERMISSION_PROFILE,
        name="Read only",
        description="Read freely; ask before edits, commands, or broader access.",
    ),
    WORKSPACE_PERMISSION_PROFILE: SessionMode(
        id=WORKSPACE_PERMISSION_PROFILE,
        name="Auto",
        description="Edit the workspace automatically; broader actions still ask.",
    ),
    DANGER_FULL_ACCESS_PERMISSION_PROFILE: SessionMode(
        id=DANGER_FULL_ACCESS_PERMISSION_PROFILE,
        name="Full access",
        description="Run without approval prompts within the Host launch ceiling.",
    ),
}


class ACPSessionMismatchError(ValueError):
    """A valid owned ACP message names a different Host session."""

ACP_PERMISSION_OPTIONS = (
    PermissionOption(
        option_id="allow_once",
        name="Allow this call",
        kind="allow_once",
    ),
    PermissionOption(
        option_id="allow_session",
        name="Allow for this session",
        kind="allow_always",
    ),
    PermissionOption(
        option_id="reject_soft",
        name="Reject this call and continue",
        kind="reject_once",
    ),
    PermissionOption(
        option_id="reject_hard",
        name="Reject and stop this turn",
        kind="reject_once",
    ),
    PermissionOption(
        option_id="reject_explain",
        name="Reject and explain first",
        kind="reject_once",
    ),
)
ACP_PERMISSION_OPTION_IDS = frozenset(
    option.option_id for option in ACP_PERMISSION_OPTIONS
)


def map_tool_event(
    event: Mapping[str, Any],
) -> ToolCallStart | ToolCallProgress | None:
    """Map one tool event to an official ACP v1.19 update model."""

    event_type = event.get("type")
    if event_type not in {"tool_call", "tool_result"}:
        return None

    normalized = normalize_wire_event(event)
    if event_type == "tool_call":
        return _tool_start(normalized)
    return _tool_update(normalized)


def map_message_event(
    event: Mapping[str, Any],
) -> AgentMessageChunk | None:
    """Map one complete Host assistant message to an ACP text chunk."""

    if event.get("type") != "assistant":
        return None
    return AgentMessageChunk(
        session_update="agent_message_chunk",
        message_id=_required_string(event, "id"),
        content=text_block(_required_string(event, "content")),
    )


def map_thought_event(
    event: Mapping[str, Any],
) -> AgentThoughtChunk | None:
    """Map one persisted public application thought to ACP v1.19."""

    if event.get("type") != "thinking":
        return None
    kwargs: dict[str, Any] = {
        "session_update": "agent_thought_chunk",
        "message_id": _required_string(event, "id"),
        "content": text_block(_required_string(event, "content")),
    }
    kind = event.get("kind")
    if isinstance(kind, str) and kind:
        # Product presentation metadata is an extension, never authority.
        kwargs["field_meta"] = {"connectonion": {"kind": kind}}
    return AgentThoughtChunk(**kwargs)


def map_plan_event(event: Mapping[str, Any]) -> AgentPlanUpdate | None:
    """Map one canonical complete plan replacement to stable ACP v1.19."""
    if event.get("type") != "plan":
        return None
    raw_entries = event.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("Plan entries must be a list")
    entries = []
    for raw in raw_entries:
        if not isinstance(raw, Mapping) or set(raw) != {
            "content", "priority", "status"
        }:
            raise ValueError("Plan entries must use the canonical shape")
        priority = raw["priority"]
        status = raw["status"]
        if not isinstance(priority, str) or priority not in {
            "high", "medium", "low"
        }:
            raise ValueError(f"Unsupported plan priority: {priority!r}")
        if not isinstance(status, str) or status not in {
            "pending", "in_progress", "completed"
        }:
            raise ValueError(f"Unsupported plan status: {status!r}")
        entries.append(ACPPlanEntry(
            content=_required_nonempty(raw["content"], "content"),
            priority=priority,
            status=status,
        ))
    return AgentPlanUpdate(session_update="plan", entries=entries)


def session_mode_id(value: Any) -> str:
    """Return one canonical permission profile carried by ACP session mode."""

    return permission_profile_id(value)


def acp_session_mode_state(
    current_mode_id: Any, available_mode_ids: list[str] | tuple[str, ...]
) -> dict[str, Any]:
    """Serialize one exact official SessionModeState for CONNECTED."""

    current = session_mode_id(current_mode_id)
    available: list[SessionMode] = []
    seen: set[str] = set()
    for value in available_mode_ids:
        mode_id = session_mode_id(value)
        if mode_id in seen:
            raise ValueError(f"ACP session mode is duplicate: {mode_id!r}")
        seen.add(mode_id)
        available.append(ACP_SESSION_MODES[mode_id].model_copy(deep=True))
    if current not in seen:
        raise ValueError(f"Current ACP session mode is not advertised: {current!r}")
    state = SessionModeState(
        current_mode_id=current,
        available_modes=available,
    )
    return state.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    )


def acp_set_mode_request_id(frame: Mapping[str, Any]) -> str | None:
    """Return correlation identity only for this supported carrier method."""

    if (
        frame.get("type") != ACP_REQUEST_FRAME_TYPE
        or frame.get("acpSchema") != ACP_SCHEMA_VERSION
    ):
        return None
    message = frame.get("message")
    if not isinstance(message, Mapping):
        return None
    if message.get("method") != ACP_SET_SESSION_MODE_METHOD:
        return None
    request_id = message.get("id")
    return request_id if isinstance(request_id, str) and request_id else None


def acp_set_mode_request_frame(
    request_id: str, session_id: str, mode_id: Any
) -> dict[str, Any]:
    """Return one exact official session/set_mode client request carrier."""
    params = SetSessionModeRequest(
        session_id=_required_nonempty(session_id, "session_id"),
        mode_id=session_mode_id(mode_id),
    ).model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    )
    return {
        "type": ACP_REQUEST_FRAME_TYPE,
        "acpSchema": ACP_SCHEMA_VERSION,
        "message": {
            "jsonrpc": "2.0",
            "id": _required_nonempty(request_id, "request_id"),
            "method": ACP_SET_SESSION_MODE_METHOD,
            "params": params,
        },
    }


def acp_set_mode_request(
    frame: Mapping[str, Any], *, expected_session_id: str
) -> tuple[str, str]:
    """Validate one exact owned ACP session/set_mode request."""

    if frame.get("type") != ACP_REQUEST_FRAME_TYPE:
        raise ValueError("Unsupported ACP request carrier")
    if frame.get("acpSchema") != ACP_SCHEMA_VERSION:
        raise ValueError("Unsupported ACP carrier schema")
    message = _required_mapping(frame, "message")
    if set(message) != {"jsonrpc", "id", "method", "params"}:
        raise ValueError("ACP set mode must be an exact JSON-RPC request")
    if message.get("jsonrpc") != "2.0":
        raise ValueError("ACP request jsonrpc must be '2.0'")
    request_id = _required_string(message, "id")
    if message.get("method") != ACP_SET_SESSION_MODE_METHOD:
        raise ValueError("Unsupported ACP client request method")
    params = _required_mapping(message, "params")
    if not set(params).issubset({"sessionId", "modeId", "_meta"}):
        raise ValueError("ACP set mode params contain unsupported fields")
    parsed = SetSessionModeRequest.model_validate(params)
    if parsed.session_id != expected_session_id:
        raise ACPSessionMismatchError(
            "ACP mode request belongs to another session"
        )
    # A rolling-upgrade client may still send an old mode ID. Normalize it at
    # this one compatibility boundary; all committed and emitted state is
    # canonical.
    return request_id, legacy_permission_profile_id(parsed.mode_id)


def host_session_mode_state(connected: Mapping[str, Any]) -> dict[str, Any] | None:
    """Read an exact advertised Host SessionModeState or return unsupported."""
    capabilities = connected.get("carrier_capabilities")
    if not isinstance(capabilities, Mapping):
        return None
    acp = capabilities.get("acp")
    if not isinstance(acp, Mapping) or acp.get("schema") != ACP_SCHEMA_VERSION:
        return None
    requests = acp.get("client_requests")
    if not isinstance(requests, list) or ACP_SET_SESSION_MODE_METHOD not in requests:
        return None
    raw_state = connected.get("session_modes")
    if not isinstance(raw_state, Mapping):
        return None
    if not set(raw_state).issubset({"currentModeId", "availableModes", "_meta"}):
        return None
    try:
        state = SessionModeState.model_validate(raw_state)
        current = legacy_permission_profile_id(state.current_mode_id)
        seen: set[str] = set()
        available: list[SessionMode] = []
        for mode in state.available_modes:
            mode_id = legacy_permission_profile_id(mode.id)
            if mode_id in seen or not mode.name:
                return None
            seen.add(mode_id)
            canonical = ACP_SESSION_MODES[mode_id].model_copy(deep=True)
            available.append(canonical)
        if current not in seen:
            return None
    except (TypeError, ValueError):
        return None
    normalized = SessionModeState(
        current_mode_id=current,
        available_modes=available,
    )
    return normalized.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    )


def acp_set_mode_response_frame(
    request_id: str, session_id: str
) -> dict[str, Any]:
    """Return the exact empty official set-mode success response."""

    result = SetSessionModeResponse().model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    )
    return {
        "type": ACP_RESPONSE_FRAME_TYPE,
        "acpSchema": ACP_SCHEMA_VERSION,
        "sessionId": _required_nonempty(session_id, "session_id"),
        "message": {
            "jsonrpc": "2.0",
            "id": _required_nonempty(request_id, "request_id"),
            "result": result,
        },
    }


def acp_set_mode_error_frame(
    request_id: str,
    session_id: str,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    """Return one correlated JSON-RPC error in the Host ACP carrier."""

    if isinstance(code, bool) or not isinstance(code, int):
        raise ValueError("ACP error code must be an integer")
    error: dict[str, Any] = {
        "code": code,
        "message": _required_nonempty(message, "error_message"),
    }
    if data is not None:
        error["data"] = data
    return {
        "type": ACP_RESPONSE_FRAME_TYPE,
        "acpSchema": ACP_SCHEMA_VERSION,
        "sessionId": _required_nonempty(session_id, "session_id"),
        "message": {
            "jsonrpc": "2.0",
            "id": _required_nonempty(request_id, "request_id"),
            "error": error,
        },
    }


def acp_set_mode_response(
    frame: Mapping[str, Any], *, expected_request_id: str,
    expected_session_id: str,
) -> dict[str, Any]:
    """Decode one complete owned set-mode response for a Host client."""
    if frame.get("type") != ACP_RESPONSE_FRAME_TYPE:
        raise ValueError("Unsupported ACP response carrier")
    if frame.get("acpSchema") != ACP_SCHEMA_VERSION:
        raise ValueError("Unsupported ACP carrier schema")
    if frame.get("sessionId") != expected_session_id:
        raise ValueError("ACP mode response belongs to another session")
    message = _required_mapping(frame, "message")
    if message.get("jsonrpc") != "2.0":
        raise ValueError("ACP response jsonrpc must be '2.0'")
    if message.get("id") != expected_request_id:
        raise ValueError("ACP mode response belongs to another request")
    has_result = "result" in message
    has_error = "error" in message
    if has_result == has_error:
        raise ValueError("ACP mode response needs exactly one result or error")
    expected_keys = {"jsonrpc", "id", "result" if has_result else "error"}
    if set(message) != expected_keys:
        raise ValueError("ACP mode response has unexpected fields")
    if has_result:
        raw_result = _required_mapping(message, "result")
        if not set(raw_result).issubset({"_meta"}):
            raise ValueError("ACP mode result has unexpected fields")
        result = SetSessionModeResponse.model_validate(raw_result)
        return {"result": result.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude_unset=True
        )}

    error = _required_mapping(message, "error")
    if not set(error).issubset({"code", "message", "data"}):
        raise ValueError("ACP mode error has unexpected fields")
    code = error.get("code")
    text = error.get("message")
    if isinstance(code, bool) or not isinstance(code, int):
        raise ValueError("ACP mode error code must be an integer")
    if not isinstance(text, str) or not text:
        raise ValueError("ACP mode error message must be non-empty")
    decoded: dict[str, Any] = {"code": code, "message": text}
    if "data" in error:
        decoded["data"] = error["data"]
    return {"error": decoded}


def map_mode_event(
    event: Mapping[str, Any],
) -> CurrentModeUpdate | None:
    """Map an authoritative Host mode observation to ACP v1.19."""

    if event.get("type") != "mode_changed":
        return None
    return CurrentModeUpdate(
        session_update="current_mode_update",
        current_mode_id=session_mode_id(event.get("mode")),
    )


def _tool_start(event: Mapping[str, Any]) -> ToolCallStart:
    return ToolCallStart(
        session_update="tool_call",
        tool_call_id=_required_string(event, "tool_id"),
        title=_required_string(event, "name"),
        status=event["status"],
        raw_input=event.get("args"),
    )


def _tool_update(event: Mapping[str, Any]) -> ToolCallProgress:
    kwargs: dict[str, Any] = {
        "session_update": "tool_call_update",
        "tool_call_id": _required_string(event, "tool_id"),
        "status": event["status"],
        "content": [
            tool_content(text_block(_required_string(event, "result")))
        ],
    }
    if event.get("raw_output") is not None:
        kwargs["raw_output"] = event["raw_output"]
    if isinstance(event.get("timing_ms"), (int, float)) and not isinstance(
        event["timing_ms"], bool
    ):
        kwargs["field_meta"] = {
            "connectonion": {"timingMs": event["timing_ms"]}
        }
    return ToolCallProgress(**kwargs)


def acp_notification_frame(
    event: Mapping[str, Any], session_id: str
) -> dict[str, Any] | None:
    """Return a detached ConnectOnion carrier for one supported ACP update."""

    update = (
        map_tool_event(event)
        or map_message_event(event)
        or map_thought_event(event)
        or map_plan_event(event)
        or map_mode_event(event)
    )
    if update is None:
        return None
    notification = SessionNotification(session_id=session_id, update=update)
    params = notification.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    )
    return {
        "type": ACP_FRAME_TYPE,
        "acpSchema": ACP_SCHEMA_VERSION,
        "message": {
            "jsonrpc": "2.0",
            "method": ACP_SESSION_UPDATE_METHOD,
            "params": params,
        },
    }


def acp_permission_request_frame(
    event: Mapping[str, Any], session_id: str
) -> dict[str, Any]:
    """Carry one exact ACP permission request beside the legacy Host event."""

    if event.get("type") != "approval_needed":
        raise ValueError("ACP permission source must be approval_needed")
    arguments = _required_mapping(event, "arguments")
    params = RequestPermissionRequest(
        session_id=_required_nonempty(session_id, "session_id"),
        tool_call=ToolCallUpdate(
            tool_call_id=_required_string(event, "tool_call_id"),
            title=_required_string(event, "tool"),
            status="pending",
            raw_input=dict(arguments),
        ),
        options=[option.model_copy(deep=True) for option in ACP_PERMISSION_OPTIONS],
    )
    request = AgentRequest(
        id=_required_string(event, "id"),
        method=ACP_PERMISSION_METHOD,
        params=params,
    )
    message = request.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    )
    return {
        "type": ACP_REQUEST_FRAME_TYPE,
        "acpSchema": ACP_SCHEMA_VERSION,
        "message": {"jsonrpc": "2.0", **message},
    }


def legacy_approval_response_from_acp(
    frame: Mapping[str, Any],
    *,
    expected_session_id: str,
    expected_request_id: str,
) -> dict[str, Any]:
    """Validate one bound ACP response and return the existing policy input."""

    if frame.get("type") != ACP_RESPONSE_FRAME_TYPE:
        raise ValueError("Unsupported ACP permission response carrier")
    if frame.get("acpSchema") != ACP_SCHEMA_VERSION:
        raise ValueError("Unsupported ACP carrier schema")
    if frame.get("sessionId") != expected_session_id:
        raise ValueError("ACP permission response belongs to another session")
    message = _required_mapping(frame, "message")
    _require_exact_fields(
        message,
        {"jsonrpc", "id", "result"},
        "ACP permission response",
    )
    if message.get("jsonrpc") != "2.0":
        raise ValueError("ACP response jsonrpc must be '2.0'")
    if message.get("id") != expected_request_id:
        raise ValueError("ACP permission response belongs to another request")
    raw_result = _required_mapping(message, "result")
    _require_exact_fields(
        raw_result, {"outcome", "_meta"}, "ACP permission result"
    )
    raw_outcome = _required_mapping(raw_result, "outcome")
    outcome_fields = {"outcome"}
    if raw_outcome.get("outcome") == "selected":
        outcome_fields.update({"optionId", "_meta"})
    _require_exact_fields(
        raw_outcome, outcome_fields, "ACP permission outcome"
    )
    result = RequestPermissionResponse.model_validate(raw_result)
    outcome = result.outcome
    if outcome.outcome == "cancelled":
        return _hard_rejection()

    option_id = outcome.option_id
    if option_id not in ACP_PERMISSION_OPTION_IDS:
        raise ValueError("ACP permission response selected an unknown option")
    if option_id == "allow_once":
        return {"approved": True, "scope": "once"}
    if option_id == "allow_session":
        return {"approved": True, "scope": "session"}

    response = {
        "approved": False,
        "scope": "once",
        "mode": option_id,
    }
    feedback = _permission_feedback(result.field_meta)
    if feedback:
        response["feedback"] = feedback
    return response


def legacy_interrupt_from_acp_cancel(
    frame: Mapping[str, Any], *, expected_session_id: str
) -> dict[str, str]:
    """Validate one exact ACP cancel notification and map it to Host IO."""

    if frame.get("type") != ACP_FRAME_TYPE:
        raise ValueError("Unsupported ACP cancel carrier")
    if frame.get("acpSchema") != ACP_SCHEMA_VERSION:
        raise ValueError("Unsupported ACP carrier schema")
    message = _required_mapping(frame, "message")
    if set(message) != {"jsonrpc", "method", "params"}:
        raise ValueError("ACP cancel must be a JSON-RPC notification")
    if message.get("jsonrpc") != "2.0":
        raise ValueError("ACP cancel jsonrpc must be '2.0'")
    if message.get("method") != ACP_CANCEL_METHOD:
        raise ValueError("Unsupported ACP client notification method")
    params = _required_mapping(message, "params")
    _require_exact_fields(
        params, {"sessionId", "_meta"}, "ACP cancel params"
    )
    if not isinstance(params.get("sessionId"), str):
        raise ValueError("ACP cancel sessionId must be a string")
    cancel = CancelNotification.model_validate(params)
    if cancel.session_id != expected_session_id:
        raise ValueError("ACP cancel belongs to another session")
    return {"type": "INTERRUPT"}


def _hard_rejection() -> dict[str, Any]:
    return {"approved": False, "scope": "once", "mode": "reject_hard"}


def _permission_feedback(field_meta: Any) -> str | None:
    if not isinstance(field_meta, Mapping):
        return None
    connectonion = field_meta.get("connectonion")
    if not isinstance(connectonion, Mapping):
        return None
    feedback = connectonion.get("feedback")
    return feedback if isinstance(feedback, str) and feedback else None


def legacy_tool_event_from_acp(
    frame: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Decode an ACP tool notification for the legacy Python UI mapper."""

    decoded = _session_update_from_acp(frame)
    if decoded is None:
        return None
    _, update = decoded
    return _legacy_tool_event(update)


def legacy_stream_event_from_acp(
    frame: Mapping[str, Any],
    *,
    expected_session_id: str | None,
) -> dict[str, Any] | None:
    """Decode one ACP notification for the legacy Python stream handler."""

    decoded = _session_update_from_acp(frame)
    if decoded is None:
        return None
    session_id, update = decoded
    if update.get("sessionUpdate") == "current_mode_update":
        if expected_session_id is None or session_id != expected_session_id:
            raise ValueError("ACP mode update belongs to another session")
        return {
            "type": "mode_changed",
            "mode": legacy_permission_profile_id(update.get("currentModeId")),
        }
    return _legacy_tool_event(update)


def _session_update_from_acp(
    frame: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]] | None:
    if frame.get("type") != ACP_FRAME_TYPE:
        return None
    if frame.get("acpSchema") != ACP_SCHEMA_VERSION:
        raise ValueError("Unsupported ACP carrier schema")
    message = _required_mapping(frame, "message")
    if message.get("jsonrpc") != "2.0":
        raise ValueError("ACP notification jsonrpc must be '2.0'")
    if message.get("method") != ACP_SESSION_UPDATE_METHOD:
        raise ValueError("Unsupported ACP notification method")
    params = _required_mapping(message, "params")
    session_id = _required_string(params, "sessionId")
    update = _required_mapping(params, "update")
    return session_id, update


def _legacy_tool_event(update: Mapping[str, Any]) -> dict[str, Any]:
    update_type = update.get("sessionUpdate")
    if update_type == "tool_call":
        event = {
            "type": "tool_call",
            "tool_id": _required_string(update, "toolCallId"),
            "name": _required_string(update, "title"),
        }
        return _with_optional_tool_fields(event, update)
    if update_type == "tool_call_update":
        event = {
            "type": "tool_call_update",
            "tool_id": _required_string(update, "toolCallId"),
        }
        return _with_optional_tool_fields(
            event, update, allow_unknown_status=True
        )
    raise ValueError(f"Unsupported ACP session update: {update_type!r}")


def _with_optional_tool_fields(
    event: dict[str, Any],
    update: Mapping[str, Any],
    *,
    allow_unknown_status: bool = False,
) -> dict[str, Any]:
    status = update.get("status")
    if status is not None:
        event["status"] = _tool_status(
            status, allow_unknown=allow_unknown_status
        )
    title = update.get("title")
    if title is not None:
        if not isinstance(title, str) or not title:
            raise ValueError("ACP tool title must be a non-empty string")
        event["name"] = title
    if "rawInput" in update:
        event["args"] = update["rawInput"]
    result = _tool_result_text(update)
    if result is not None:
        event["result"] = result
    event.update(_timing(update))
    return event


def _tool_status(value: Any, *, allow_unknown: bool) -> str:
    allowed = {"pending", "in_progress", "completed", "failed"}
    if not isinstance(value, str):
        raise ValueError(f"Unsupported ACP tool status: {value!r}")
    if value not in allowed:
        if allow_unknown:
            return "unknown"
        raise ValueError(f"Unsupported ACP tool status: {value!r}")
    return value


def _tool_result_text(update: Mapping[str, Any]) -> str | None:
    texts: list[str] = []
    content = update.get("content")
    if content is not None and not isinstance(content, list):
        raise ValueError("ACP tool content must be an array")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, Mapping) or item.get("type") != "content":
                continue
            block = item.get("content")
            if (
                isinstance(block, Mapping)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ):
                texts.append(block["text"])
    if texts:
        return "\n".join(texts)
    raw_output = update.get("rawOutput")
    if isinstance(raw_output, str):
        return raw_output
    return None


def _timing(update: Mapping[str, Any]) -> dict[str, int | float]:
    field_meta = update.get("_meta")
    if not isinstance(field_meta, Mapping):
        return {}
    connectonion = field_meta.get("connectonion")
    if not isinstance(connectonion, Mapping):
        return {}
    timing = connectonion.get("timingMs")
    if isinstance(timing, (int, float)) and not isinstance(timing, bool):
        return {"timing_ms": timing}
    return {}


def _required_mapping(
    value: Mapping[str, Any], field: str
) -> Mapping[str, Any]:
    item = value.get(field)
    if not isinstance(item, Mapping):
        raise ValueError(f"ACP notification field {field!r} must be an object")
    return item


def _require_exact_fields(
    value: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    if not set(value).issubset(allowed):
        raise ValueError(f"{context} contains unsupported fields")


def _required_string(value: Mapping[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise ValueError(f"ACP event field {field!r} must be a non-empty string")
    return item


def _required_nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"ACP event field {field!r} must be a non-empty string")
    return value
