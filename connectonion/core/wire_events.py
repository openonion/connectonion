"""Normalize public IO events without rewriting canonical session traces.

ConnectOnion keeps its historical trace statuses for persistence and evals, but
uses OIP's four-state tool lifecycle on the live wire. Provider adapters and
protocol bridges therefore share one vocabulary while old trace files remain
readable and stable.
"""

from __future__ import annotations

from typing import Any, Mapping

_TOOL_START_STATUSES = {
    "pending": "pending",
    "running": "in_progress",
    "in_progress": "in_progress",
}
_TOOL_RESULT_STATUSES = {
    "success": "completed",
    "done": "completed",
    "completed": "completed",
    "error": "failed",
    "failed": "failed",
    "not_found": "failed",
    "interrupted": "failed",
}


def normalize_wire_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached event with OIP tool lifecycle statuses.

    Only tool lifecycle statuses change.  Event names, IDs, fields, and the
    canonical object supplied by the caller stay untouched so this can sit at
    both Agent trace and provider ``IO.log`` boundaries.
    """

    normalized = dict(event)
    event_type = normalized.get("type")
    if event_type == "tool_call":
        status = normalized.get("status", "in_progress")
        normalized["status"] = _normalize_status(
            status, _TOOL_START_STATUSES
        )
    elif event_type == "tool_result":
        normalized["status"] = _normalize_status(
            normalized.get("status"), _TOOL_RESULT_STATUSES
        )
    return normalized


def _normalize_status(value: Any, statuses: Mapping[str, str]) -> str:
    if not isinstance(value, str) or value not in statuses:
        raise ValueError(f"Unsupported tool event status: {value!r}")
    return statuses[value]
