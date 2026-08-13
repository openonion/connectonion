"""
Purpose: Dispatch acknowledged ACP and bounded legacy Host mode commands
LLM-Note:
  Dependencies: imports from [core.acp_wire, host.session.mode, rich.console] | imported by [.session] | tested by [tests/unit/test_acp_host_set_mode.py]
  Data flow: run_ws_session routes ACP_REQUEST/mode_change here -> validate request identity/session -> commit_host_session_mode() -> update conn only after append -> send ACP_RESPONSE or legacy mode_changed
  State/Effects: tracks a bounded insertion-ordered map of consumed request IDs in conn; mutates conn['session'] only after durable success
  Integration: handle_acp_mode_request returns False for an unsupported schema/method so session.py can reject without forwarding; handle_legacy_mode_change maps the historical plan alias to :read-only
  Errors: policy failures retain their owned JSON-RPC code; malformed params=-32602, storage failure=-32603 without private exception details
"""

from __future__ import annotations

import asyncio
import logging

from ....core.acp_wire import (
    ACPSessionMismatchError,
    acp_set_mode_error_frame,
    acp_set_mode_request,
    acp_set_mode_request_id,
    acp_set_mode_response_frame,
)
from ....core.approval_modes import READ_ONLY_PERMISSION_PROFILE
from ..session.mode import ModeTransactionError, commit_host_session_mode

logger = logging.getLogger(__name__)
_MAX_REQUEST_IDS = 256


async def handle_acp_mode_request(
    frame, send_msg, conn, route_handlers, storage, registry
) -> bool:
    """Handle this supported ACP method; return False for another method."""
    request_id = acp_set_mode_request_id(frame)
    policy = route_handlers.get("session_modes")
    if request_id is None or policy is None:
        return False
    session_id = conn.get("session_id")
    if not conn.get("authenticated") or not session_id:
        await send_msg({"type": "ERROR", "message": "authenticate first (send CONNECT)"})
        return True
    if _request_id_was_seen(conn, request_id):
        await send_msg(acp_set_mode_error_frame(
            request_id, session_id, -32602, "Duplicate request ID"
        ))
        return True

    try:
        _, mode_id = acp_set_mode_request(
            frame, expected_session_id=session_id
        )
        record = await asyncio.to_thread(
            commit_host_session_mode,
            storage,
            registry,
            session_id,
            conn.get("agent_address"),
            mode_id,
            policy,
            bool(conn.get("mode_is_admin")),
        )
    except ModeTransactionError as exc:
        await _send_owned_error(send_msg, request_id, session_id, exc)
        return True
    except ACPSessionMismatchError as exc:
        await send_msg(acp_set_mode_error_frame(
            request_id, session_id, -32002, str(exc)
        ))
        return True
    except (TypeError, ValueError) as exc:
        await send_msg(acp_set_mode_error_frame(
            request_id, session_id, -32602, str(exc)
        ))
        return True
    except Exception:
        logger.exception(
            "ACP mode persistence failed for session %s", session_id
        )
        await send_msg(acp_set_mode_error_frame(
            request_id, session_id, -32603, "Unable to change session mode"
        ))
        return True

    conn["session"] = record.session
    await send_msg(acp_set_mode_response_frame(request_id, session_id))
    return True


async def handle_legacy_mode_change(
    frame, send_msg, conn, route_handlers, storage, registry
) -> None:
    """Commit the rolling-compatibility setter through the same authority."""
    policy = route_handlers.get("session_modes")
    session_id = conn.get("session_id")
    if not conn.get("authenticated") or policy is None or not session_id:
        await send_msg({"type": "ERROR", "message": "mode change is unavailable"})
        return
    mode_id = (
        READ_ONLY_PERMISSION_PROFILE
        if frame.get("mode") == "plan"
        else frame.get("mode")
    )
    try:
        record = await asyncio.to_thread(
            commit_host_session_mode,
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
            "Legacy mode persistence failed for session %s", session_id
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
        "session_id": session_id,
    })


def _request_id_was_seen(conn: dict, request_id: str) -> bool:
    seen = conn.setdefault("mode_request_ids", {})
    if request_id in seen:
        return True
    seen[request_id] = None
    if len(seen) > _MAX_REQUEST_IDS:
        seen.pop(next(iter(seen)))
    return False


async def _send_owned_error(
    send_msg, request_id: str, session_id: str, error: ModeTransactionError
) -> None:
    await send_msg(acp_set_mode_error_frame(
        request_id,
        session_id,
        error.code,
        error.message,
        error.data,
    ))
