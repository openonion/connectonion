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
    AgentRequest,
    PermissionOption,
    RequestPermissionRequest,
    RequestPermissionResponse,
    SessionNotification,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
)

from .wire_events import normalize_wire_event

ACP_FRAME_TYPE = "ACP_NOTIFICATION"
ACP_REQUEST_FRAME_TYPE = "ACP_REQUEST"
ACP_RESPONSE_FRAME_TYPE = "ACP_RESPONSE"
ACP_SCHEMA_VERSION = "schema-v1.19.0"
ACP_SESSION_UPDATE_METHOD = "session/update"
ACP_PERMISSION_METHOD = "session/request_permission"

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

    update = map_tool_event(event) or map_message_event(event)
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
    if message.get("jsonrpc") != "2.0":
        raise ValueError("ACP response jsonrpc must be '2.0'")
    if message.get("id") != expected_request_id:
        raise ValueError("ACP permission response belongs to another request")
    result = RequestPermissionResponse.model_validate(
        _required_mapping(message, "result")
    )
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
    _required_string(params, "sessionId")
    update = _required_mapping(params, "update")
    return _legacy_tool_event(update)


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


def _required_string(value: Mapping[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise ValueError(f"ACP event field {field!r} must be a non-empty string")
    return item


def _required_nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"ACP event field {field!r} must be a non-empty string")
    return value
