"""Pure ConnectOnion event mapping for ACP 0.12 session updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from acp import text_block, tool_content
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    StopReason,
    ToolCallProgress,
    ToolCallStart,
    Usage,
)

ACPUpdate = AgentMessageChunk | AgentThoughtChunk | ToolCallStart | ToolCallProgress
STREAMED_AGENT_EVENT_TYPES = frozenset({
    "assistant",
    "thinking",
    "tool_call",
    "tool_result",
    "turn_result",
})


@dataclass(frozen=True)
class ACPTerminal:
    """Protocol terminal state derived from one canonical Agent turn."""

    stop_reason: StopReason | None
    usage: Usage | None


@dataclass(frozen=True)
class ACPEventMapping:
    """Side-effect-free result of mapping one internal event."""

    updates: tuple[ACPUpdate, ...] = ()
    terminal: ACPTerminal | None = None


def map_agent_event(event: Mapping[str, Any]) -> ACPEventMapping:
    """Map one immutable internal event to exact ACP 0.12 models."""

    event_type = event.get("type")
    if event_type == "tool_call":
        return ACPEventMapping(updates=(_tool_start(event),))
    if event_type == "tool_result":
        return ACPEventMapping(updates=(_tool_progress(event),))
    if event_type == "thinking":
        return ACPEventMapping(updates=(_thought(event),))
    if event_type == "assistant":
        return ACPEventMapping(updates=(_assistant(event),))
    if event_type == "turn_result":
        return ACPEventMapping(terminal=_terminal(event))
    return ACPEventMapping()


def _tool_start(event: Mapping[str, Any]) -> ToolCallStart:
    return ToolCallStart(
        session_update="tool_call",
        tool_call_id=_required_string(event, "tool_id"),
        title=_required_string(event, "name"),
        status="in_progress",
        raw_input=event.get("args"),
    )


def _tool_progress(event: Mapping[str, Any]) -> ToolCallProgress:
    status = event.get("status")
    if status == "success":
        acp_status = "completed"
    elif status in {"error", "not_found", "interrupted"}:
        acp_status = "failed"
    else:
        raise ValueError(f"Unsupported tool result status: {status!r}")

    kwargs: dict[str, Any] = {
        "session_update": "tool_call_update",
        "tool_call_id": _required_string(event, "tool_id"),
        "status": acp_status,
        "content": [tool_content(text_block(_required_string(event, "result")))],
    }
    raw_output = event.get("raw_output")
    if raw_output is not None:
        kwargs["raw_output"] = raw_output
    return ToolCallProgress(**kwargs)


def _thought(event: Mapping[str, Any]) -> AgentThoughtChunk:
    return AgentThoughtChunk(
        session_update="agent_thought_chunk",
        message_id=_required_string(event, "id"),
        content=text_block(_required_string(event, "content")),
    )


def _assistant(event: Mapping[str, Any]) -> AgentMessageChunk:
    return AgentMessageChunk(
        session_update="agent_message_chunk",
        message_id=_required_string(event, "message_id"),
        content=text_block(_required_string(event, "content")),
    )


def _terminal(event: Mapping[str, Any]) -> ACPTerminal:
    reason = event.get("reason")
    stop_reasons: dict[str, StopReason | None] = {
        "natural": "end_turn",
        "max_iterations": "max_turn_requests",
        "interrupted": "cancelled",
        "stopped": "refusal",
        "error": None,
    }
    if reason not in stop_reasons:
        raise ValueError(f"Unsupported Agent turn reason: {reason!r}")
    return ACPTerminal(
        stop_reason=stop_reasons[reason],
        usage=_usage(event.get("usage")),
    )


def _usage(value: Any) -> Usage | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Agent turn usage must be a dictionary or null")
    return Usage(
        total_tokens=value.get("total_tokens", 0),
        input_tokens=value.get("input_tokens", 0),
        output_tokens=value.get("output_tokens", 0),
        cached_read_tokens=value.get("cached_tokens", 0),
        cached_write_tokens=value.get("cache_write_tokens", 0),
    )


def _required_string(event: Mapping[str, Any], field: str) -> str:
    value = event.get(field)
    if not isinstance(value, str):
        raise ValueError(f"ACP event field {field!r} must be a string")
    return value
