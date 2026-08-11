"""
Purpose: Bridge synchronous hosted Agents to the async WebSocket transport
LLM-Note:
  Dependencies: imports from [core.acp_wire, network.io, session.mode]
  Data flow: INPUT → Agent thread → WebSocketIO → async forwarder → OUTPUT/ERROR
  State/Effects: spawns Agent threads/tasks; updates the active-session registry
  Integration: start_agent(), resume_forwarding(), forward_agent_msgs_to_client()
  Performance: thread-per-INPUT (worker isolation) | one forward_task per WS connection
  Errors: owned failures stay public; unexpected failures log and become -32603
"""
import asyncio
import logging
import threading

from rich.console import Console

from ....core.acp_wire import (
    acp_notification_frame,
    acp_permission_request_frame,
)
from ...io import WebSocketIO
from ..session.mode import ModeTransactionError

console = Console()
logger = logging.getLogger(__name__)


class _AgentExecutionError(RuntimeError):
    """Private Agent failure marker with a fixed public representation."""

    def __init__(self):
        super().__init__("Unable to run agent")


def _acp_rollout_frame(event, session_id):
    if not session_id:
        return None
    try:
        return acp_notification_frame(event, session_id)
    except (TypeError, ValueError) as exc:
        console.print(
            f"[yellow]ACP mirror skipped; legacy event continues: {exc}[/yellow]"
        )
        return None


def _acp_permission_rollout_frame(event, session_id):
    if not session_id:
        return None
    try:
        return acp_permission_request_frame(event, session_id)
    except (TypeError, ValueError) as exc:
        console.print(
            f"[yellow]ACP permission mirror skipped; legacy request continues: {exc}[/yellow]"
        )
        return None


def _final_agent_event(result, session, chat_items):
    """Return a terminal answer with transport-neutral persisted identity."""
    if (
        not isinstance(result, str)
        or not result
        or not isinstance(session, dict)
    ):
        return None
    final_message = next(
        (
            message for message in reversed(session.get("messages", []))
            if message.get("role") == "assistant" and message.get("content")
        ),
        None,
    )
    if (
        final_message is None
        or final_message.get("content") != result
        or not isinstance(final_message.get("id"), str)
        or not final_message["id"]
    ):
        return None
    final_agent = next(
        (
            item for item in reversed(chat_items)
            if item.get("type") == "agent"
            and item.get("id") == final_message["id"]
            and item.get("content") == result
        ),
        None,
    )
    if final_agent is None:
        return None
    return {
        "type": "assistant",
        "id": final_message["id"],
        "content": result,
    }


async def _send_output(
    send_msg,
    *,
    result,
    session_id,
    duration_ms,
    session,
):
    """Send the additive ACP message mirror, then authoritative OUTPUT."""
    from ..session import session_to_chat_items

    chat_items = session_to_chat_items(session or {})
    final_event = _final_agent_event(result, session, chat_items)
    if final_event is not None:
        acp_frame = _acp_rollout_frame(final_event, session_id)
        if acp_frame is not None:
            await send_msg(acp_frame)
    await send_msg({
        "type": "OUTPUT",
        "result": result,
        "session_id": session_id,
        "duration_ms": duration_ms,
        "session": session,
        "chat_items": chat_items,
    })


def _agent_thread_body(route_handlers, storage, prompt, io, session, images, files, registry, session_id, result_holder, requester_address=None):
    """Thread target: run agent and store result. Calls io.mark_agent_done() when done."""
    try:
        result_holder[0] = route_handlers["ws_input"](storage, prompt, io, session, images, files,
                                                      requester_address=requester_address)
    except ModeTransactionError as exc:
        result_holder[0] = exc
    except Exception:
        logger.exception(
            "Hosted Agent execution failed for session %s", session_id
        )
        result_holder[0] = _AgentExecutionError()
    finally:
        # A failed run is finished too. Leaving it marked "running" routes the
        # next INPUT into a dead IO queue and creates another false ACK.
        registry.mark_session_connected(session_id)
        io.mark_agent_done()


async def forward_agent_msgs_to_client(send_msg, io, session_id, *, result_holder=None, conn=None, storage=None):
    """Forward agent events to client. Send OUTPUT (or ERROR) when agent finishes."""
    async for event in io.read_msgs_from_agent():
        if event.get("type") == "approval_needed":
            acp_request = _acp_permission_rollout_frame(event, session_id)
            io.register_permission_request(event, session_id, acp_request)
            if acp_request is not None:
                await send_msg(acp_request)
        acp_frame = (
            _acp_rollout_frame(event, session_id)
            if event.get("type") in {
                "tool_call", "tool_result", "mode_changed"
            }
            else None
        )
        if acp_frame is not None:
            await send_msg(acp_frame)
            # Rollout is dual-write: older clients still need the legacy event,
            # while new clients de-duplicate the matching logical transition.
        if session_id:
            event["session_id"] = session_id
        await send_msg(event)

    if result_holder and isinstance(result_holder[0], Exception):
        error = result_holder[0]
        if isinstance(error, ModeTransactionError):
            message = {
                "type": "ERROR",
                "code": error.code,
                "message": error.message,
            }
            if error.data:
                message.update(error.data)
        else:
            message = {
                "type": "ERROR",
                "code": -32603,
                "message": "Unable to run agent",
            }
        console.print(f"[red]✗ agent error:[/red] {message['message']}")
        await send_msg(message)
    elif result_holder and result_holder[0]:
        result = result_holder[0]
        session_data = result.get('session', {})
        if conn:
            conn["session"] = session_data
        await _send_output(
            send_msg,
            result=result["result"],
            session_id=session_id,
            duration_ms=result["duration_ms"],
            session=session_data,
        )
    elif storage:
        stored = storage.get(session_id)
        if stored and stored.status == "done":
            await _send_output(
                send_msg,
                result=stored.result,
                session_id=session_id,
                duration_ms=stored.duration_ms,
                session=stored.session,
            )
    else:
        await send_msg({"type": "ERROR", "message": "Agent completed without result"})

    # After the run, push the dashboard.html the agent may have rewritten. A run that
    # didn't touch it sends nothing (send_dashboard compares against what this
    # connection last saw), so an unchanged Home costs no bandwidth per turn.
    from .dashboard import send_dashboard
    await send_dashboard(send_msg, session_id, conn)


def resume_forwarding(send_msg, active, registry, session_id, storage, conn=None):
    """Restart the forward task on an existing running session's io. Returns (io, forward_task).

    Called when a client reconnects to a session whose agent thread is still
    alive. The io stayed live in ActiveSession across the WS drop; we just
    spawn a fresh task to pump it to the new client.
    """
    console.print("  [dim]↻ resuming forwarding to running agent[/dim]")
    io = active.io
    registry.update_ping(session_id)
    task = asyncio.create_task(
        forward_agent_msgs_to_client(send_msg, io, session_id, storage=storage, conn=conn)
    )
    return io, task


def verified_prompt(data: dict, route_handlers) -> tuple:
    """(prompt, error) -- the signed prompt when the frame carries a signature.

    The client signs the prompt into `payload`:

        payload = {"prompt": prompt, "timestamp": ...}
        input_msg["payload"] = payload
        input_msg["signature"] = ...

    and this read `data.get("prompt")`, the unsigned top-level field, checking
    only that the connection had authenticated. Measured against a live agent
    with the two saying different things:

        POST /input            signed: SIGNED   top-level: UNSIGNED  -> ran SIGNED
        INPUT over WebSocket   signed: SIGNED   top-level: UNSIGNED  -> ran UNSIGNED

    Same protocol, same client, two different guarantees -- and the client signs
    on both paths, which is what made this one look authenticated while the
    signature decided nothing. Reading the signed field is not enough on its own:
    an unverified payload can say anything. So the frame goes through the same
    verifier the HTTP path uses, which is also the one the admin messages use a
    few lines away in session.py.

    `"open"` here is about authentication, not authorisation: who may act was
    settled at CONNECT. This only establishes that the signature covers the
    prompt about to run.

    A frame with no signature keeps using the top-level field -- a client built
    without keys sends none, and its connection was authenticated by its CONNECT.
    Whether a signature should be *required* is the decision in #649, not this.
    """
    if not (data.get("signature") and isinstance(data.get("payload"), dict)):
        return data.get("prompt"), None

    prompt, _, sig_valid, err = route_handlers["auth"](data, "open")
    if not sig_valid:
        return None, err or "invalid signature"
    return prompt, None


async def start_agent(data, send_msg, conn, route_handlers, storage, registry):
    """Validate INPUT, spawn agent thread + forward task. Returns (io, forward_task) or None on error."""
    if not conn["authenticated"]:
        console.print("[red]✗ INPUT rejected:[/red] not authenticated (send CONNECT first)")
        await send_msg({"type": "ERROR", "message": "authenticate first (send CONNECT)"})
        return None

    prompt, sig_error = verified_prompt(data, route_handlers)
    if sig_error:
        console.print(f"[red]✗ INPUT rejected:[/red] {sig_error}")
        # extract_and_authenticate already prefixes its own errors; adding
        # another produced "unauthorized: unauthorized: invalid signature".
        await send_msg({"type": "ERROR", "message": sig_error})
        return None
    if not prompt:
        await send_msg({"type": "ERROR", "message": "prompt required"})
        return None

    session_id = conn["session_id"]
    existing = registry.get(session_id)
    # Defense in depth: dispatch already routes INPUT-during-running to runtime
    # input. If any future caller bypasses that, refuse to spawn a 2nd agent.
    if existing and existing.status == "running":
        await send_msg({"type": "ERROR", "message": "session already has a running agent", "session_id": session_id})
        return None

    agent_address = conn["agent_address"]
    console.print(f"[green]✓ INPUT[/green] agent_address={agent_address[:16] if agent_address else '?'}... session={session_id[:8] if session_id else '?'}... prompt={prompt[:50]}...")

    session = conn["session"] or data.get("session") or {}
    session["session_id"] = session_id
    images = data.get("images")
    files = data.get("files")
    attachments = []
    if images:
        attachments.append(f"{len(images)} images")
    if files:
        attachments.append(f"{len(files)} files")
    if attachments:
        console.print(f"  [dim]↑ {', '.join(attachments)}[/dim]")

    io = WebSocketIO()
    result_holder = [None]

    agent_thread = threading.Thread(
        target=_agent_thread_body,
        args=(route_handlers, storage, prompt, io, session, images, files, registry, session_id, result_holder,
              agent_address),
        daemon=True,
    )
    # Register BEFORE start: thread may complete before .start() returns control,
    # and _agent_thread_body calls registry.mark_session_connected() on completion.
    # If register runs after, mark_session_connected is a no-op and we end up
    # with a 'running' entry for an already-finished agent.
    if existing:
        registry.mark_session_running(session_id, io, agent_thread)
    else:
        registry.register(session_id, io, agent_thread, owner=agent_address)
    agent_thread.start()

    task = asyncio.create_task(
        forward_agent_msgs_to_client(send_msg, io, session_id, result_holder=result_holder, conn=conn)
    )
    return io, task
