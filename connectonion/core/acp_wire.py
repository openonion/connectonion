"""ACP-native events carried over the authenticated ConnectOnion socket.

The Host WebSocket also transports ConnectOnion authentication, onboarding,
session persistence, and dashboard frames, so it is not an ACP connection. An
``ACP_NOTIFICATION`` frame carries one exact ACP JSON-RPC notification without
pretending that the surrounding socket negotiated ACP capabilities.
"""

from __future__ import annotations

from typing import Any, Mapping

from acp import text_block, tool_content
from acp.schema import (
    AgentMessageChunk,
    SessionNotification,
    ToolCallProgress,
    ToolCallStart,
)

from .wire_events import normalize_wire_event

ACP_FRAME_TYPE = "ACP_NOTIFICATION"
ACP_SCHEMA_VERSION = "schema-v1.19.0"
ACP_SESSION_UPDATE_METHOD = "session/update"


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
