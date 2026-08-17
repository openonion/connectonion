"""Direct, owned Codex Work Room continuation for a hosted OIP session.

This module is deliberately narrower than a generic tool-execution endpoint:
it can resume only a Codex thread already recorded in the caller's own durable
session.  The browser supplies text and correlation IDs, never a local path,
provider session ID, model, sandbox, or tool name.  The configured agent plugin
continues to own those execution boundaries.
"""

from __future__ import annotations

import copy
import time
from typing import Any, Callable

from .session import SessionStorage, session_owner


_TERMINAL_PROVIDER_STATUSES = {"completed", "failed", "cancelled"}
_MAX_INPUT_LENGTH = 12_000


class _ProviderWorkroomUnavailable(RuntimeError):
    """The requested owned Codex continuation cannot be claimed."""


def prepare_provider_workroom_turn(
    create_agent: Callable,
    storage: SessionStorage,
    session_id: str,
    invocation_id: object,
    text: object,
    request_id: object,
    requester_address: object,
    *,
    host_full_access_turns_ceiling: int | None = None,
) -> dict[str, Any]:
    """Claim an owned terminal Codex thread and return a native-only runner."""
    if not _valid_id(invocation_id) or not _valid_id(request_id):
        return {"reason": "invalid_request"}
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text) > _MAX_INPUT_LENGTH
        or not isinstance(requester_address, str)
        or not requester_address
    ):
        return {"reason": "invalid_request"}
    source: dict[str, Any] = {}

    def claim(current):
        nonlocal source
        if current is None:
            # ``atomic_update`` requires an actual Session replacement.  Raise
            # inside its lock rather than accidentally treating a missing
            # session as a valid no-op record.
            raise _ProviderWorkroomUnavailable
        if (
            session_owner(current) != requester_address
            or current.status in SessionStorage.UNFINISHED
        ):
            return current
        source = _codex_source(current.session, invocation_id)
        if not source:
            return current
        return current.model_copy(update={"status": "running"})

    try:
        record = storage.atomic_update(session_id, claim)
    except _ProviderWorkroomUnavailable:
        return {"reason": "not_active"}
    if not source or record.status != "running":
        return {"reason": "not_active"}

    source_session_id = source["sessionId"]
    workroom_id = source.get("workroomId") or invocation_id
    source_revision = source.get("stateRevision")

    def run(io) -> None:
        started = time.time()
        agent = None
        try:
            agent = create_agent()
            agent.io = io
            agent.storage = storage
            if hasattr(agent, "_yolo_turns"):
                agent._yolo_turns = None
            if hasattr(agent, "_yolo_needs_activation"):
                agent._yolo_needs_activation = False
            agent._host_full_access_turns_ceiling = host_full_access_turns_ceiling
            agent.current_session = _direct_session(
                session_id,
                record.session or {},
                workroom_id,
                invocation_id,
                text.strip(),
                request_id,
                source_revision,
            )
            agent.execute_tool("codex", {
                "prompt": text.strip(),
                "cwd": "",
                "session_id": source_session_id,
            })
        finally:
            _persist_direct_provider_trace(
                storage,
                session_id,
                requester_address,
                getattr(agent, "current_session", None),
                int((time.time() - started) * 1000),
            )

    return {"run": run, "stateRevision": source_revision}


def _codex_source(session: object, invocation_id: str) -> dict[str, Any]:
    if not isinstance(session, dict):
        return {}
    trace = session.get("trace")
    if not isinstance(trace, list):
        return {}
    candidates = [
        event for event in trace
        if isinstance(event, dict)
        and event.get("type") == "provider_invocation"
        and event.get("invocationId") == invocation_id
        and event.get("provider") == "codex"
        and event.get("status") in _TERMINAL_PROVIDER_STATUSES
        and _valid_id(event.get("sessionId"))
    ]
    if not candidates:
        return {}
    source = max(
        candidates,
        key=lambda event: event.get("stateRevision")
        if isinstance(event.get("stateRevision"), int) else 0,
    )
    revision = source.get("stateRevision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        return {}
    return source


def _direct_session(
    session_id: str,
    source_session: dict[str, Any],
    workroom_id: str,
    continuation_of: str,
    text: str,
    request_id: str,
    state_revision: int,
) -> dict[str, Any]:
    """Construct the minimum session a configured native tool needs to run."""
    return {
        "messages": [],
        "trace": [],
        "turn": 0,
        "iteration": 1,
        "session_id": session_id,
        "mode": source_session.get("mode"),
        "requester": copy.deepcopy(source_session.get("requester")),
        "_provider_workroom_id": workroom_id,
        "_provider_continuation_of": continuation_of,
        "_provider_direct_message": text,
        "_provider_direct_message_id": request_id,
        # The browser's pending composer is correlated to the terminal source
        # invocation. Keep that exact durable revision so only a successful
        # native ``turn/start`` can acknowledge the original request.
        "_provider_direct_state_revision": state_revision,
    }


def _persist_direct_provider_trace(
    storage: SessionStorage,
    session_id: str,
    requester_address: str,
    direct_session: object,
    duration_ms: int,
) -> None:
    """Append only typed provider events; no private direct-run session leaks."""
    trace = direct_session.get("trace") if isinstance(direct_session, dict) else None
    provider_events = [
        copy.deepcopy(event) for event in trace or []
        if isinstance(event, dict) and event.get("type") in {
            "provider_invocation",
            "provider_activity",
            "provider_artifact",
            "provider_message",
        }
    ]

    def finish(current):
        if current is None or session_owner(current) != requester_address:
            return current
        session = copy.deepcopy(current.session or {})
        history = session.setdefault("trace", [])
        if isinstance(history, list):
            history.extend(provider_events)
        return current.model_copy(update={
            "status": "done",
            "session": session,
            "duration_ms": duration_ms,
        })

    storage.atomic_update(session_id, finish)


def _valid_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 512
        and value.isascii()
        and all(character.isalnum() or character in "._:-" for character in value)
    )
