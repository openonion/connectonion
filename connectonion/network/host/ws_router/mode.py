"""
Purpose: Dispatch acknowledged OIP Host mode commands
LLM-Note:
  Dependencies: imports from [host.session.mode] | imported by [.session]
  Data flow: run_ws_session routes mode_change here -> validate identity/session -> commit_host_session_mode() -> update conn only after append -> send mode_changed then any provider ceiling revisions
  State/Effects: tracks a bounded insertion-ordered map of consumed request IDs in conn; mutates conn['session'] only after durable success
  Integration: handle_mode_change accepts only the three canonical mode IDs
  Errors: policy failures retain their owned code; storage failure=-32603 without private exception details
"""

from __future__ import annotations

import asyncio
import logging

from ..session.mode import (
    ModeTransactionError,
    commit_host_session_mode_with_events,
)

logger = logging.getLogger(__name__)
async def handle_mode_change(
    frame, send_msg, conn, route_handlers, storage, registry
) -> None:
    """Commit an OIP permission-profile change through Host authority."""
    policy = route_handlers.get("session_modes")
    session_id = conn.get("session_id")
    if not conn.get("authenticated") or policy is None or not session_id:
        await send_msg({"type": "ERROR", "message": "mode change is unavailable"})
        return
    mode_id = frame.get("mode")
    try:
        record, provider_events = await asyncio.to_thread(
            commit_host_session_mode_with_events,
            storage,
            registry,
            session_id,
            conn.get("agent_address"),
            mode_id,
            policy,
            bool(conn.get("mode_is_admin")),
        )
    except ModeTransactionError as exc:
        error = {"type": "ERROR", "code": exc.code, "message": exc.message}
        if exc.data:
            error.update(exc.data)
        await send_msg(error)
        return
    except Exception:
        logger.exception(
            "OIP mode persistence failed for session %s", session_id
        )
        await send_msg({
            "type": "ERROR",
            "code": -32603,
            "message": "Unable to change session mode",
        })
        return

    conn["session"] = record.session
    await send_msg({
        "type": "mode_changed",
        "mode": record.session["mode"],
        "turns_left": record.session.get("turns_left"),
        "session_id": session_id,
    })
    # The durable transaction may have narrowed one or more completed Work
    # Rooms after the outer Host ceiling dropped. Stream only the lifecycle
    # revisions appended by that exact transaction so the connected client
    # cannot keep displaying broader authority until a later reconnect.
    for event in provider_events:
        await send_msg(event)
