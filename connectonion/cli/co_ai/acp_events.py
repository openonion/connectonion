"""Pure ConnectOnion event mapping for ACP 0.12 session updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from acp import text_block
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    CurrentModeUpdate,
    StopReason,
    ToolCallProgress,
    ToolCallStart,
    Usage,
)

from ...core.approval_modes import approval_mode_id

from ...core.acp_wire import map_plan_event, map_tool_event

ACPUpdate = (
    AgentMessageChunk
    | AgentPlanUpdate
    | AgentThoughtChunk
    | CurrentModeUpdate
    | ToolCallStart
    | ToolCallProgress
)
STREAMED_AGENT_EVENT_TYPES = frozenset({
    "assistant",
    "mode_changed",
    "plan",
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
    if event_type in {"tool_call", "tool_result"}:
        update = map_tool_event(event)
        assert update is not None
        return ACPEventMapping(updates=(update,))
    if event_type == "thinking":
        return ACPEventMapping(updates=(_thought(event),))
    if event_type == "assistant":
        return ACPEventMapping(updates=(_assistant(event),))
    if event_type == "mode_changed":
        return ACPEventMapping(updates=(_current_mode(event),))
    if event_type == "plan":
        update = map_plan_event(event)
        assert update is not None
        return ACPEventMapping(updates=(update,))
    if event_type == "turn_result":
        return ACPEventMapping(terminal=_terminal(event))
    return ACPEventMapping()


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


def _current_mode(event: Mapping[str, Any]) -> CurrentModeUpdate:
    value = _required_string(event, "mode")
    try:
        mode = approval_mode_id(value)
    except ValueError:
        raise ValueError(f"Unsupported Agent mode: {value!r}") from None
    return CurrentModeUpdate(
        session_update="current_mode_update",
        current_mode_id=mode,
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
