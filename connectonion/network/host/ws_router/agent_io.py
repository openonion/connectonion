"""
Purpose: Agent thread orchestration + io → client streaming — the bridge between the sync agent and the async transport
LLM-Note:
  Dependencies: imports from [...io (WebSocketIO), ..session (session_to_chat_items via lazy import), asyncio, threading, rich.console] | imported by [.session (start_agent), .connect (resume_forwarding)]
  Data flow: start_agent: validate INPUT → create WebSocketIO → register in registry BEFORE thread.start (race-safe) → spawn _agent_thread_body (thread target running route_handlers["ws_input"]) → spawn forward_task = forward_agent_msgs_to_client → return (io, task) | resume_forwarding: same forward_task spawn but on existing active.io | forward_agent_msgs_to_client: read_msgs_from_agent → send_msg loop → on agent finish read result_holder → emit OUTPUT (success) / ERROR (exception)
  State/Effects: spawns daemon Thread + asyncio.Task | mutates registry (register / mark_session_running) | calls io.mark_agent_done() in finally
  Integration: start_agent(data, send_msg, conn, route_handlers, storage, registry) → (io, forward_task) | None | resume_forwarding(send_msg, active, registry, session_id, storage, conn) → (io, forward_task) | forward_agent_msgs_to_client(send_msg, io, session_id, *, result_holder, conn, storage) — async, runs until io marked done
  Performance: thread-per-INPUT (worker isolation) | one forward_task per WS connection
  Errors: agent thread exceptions captured in result_holder[0]; surfaced as ERROR frame by the forwarder (threads don't propagate exceptions natively)
"""
import asyncio
import threading

from rich.console import Console
from ...io import WebSocketIO

console = Console()


def _agent_thread_body(route_handlers, storage, prompt, io, session, images, files, registry, session_id, result_holder, requester_address=None):
    """Thread target: run agent and store result. Calls io.mark_agent_done() when done."""
    try:
        result_holder[0] = route_handlers["ws_input"](storage, prompt, io, session, images, files,
                                                      requester_address=requester_address)
        registry.mark_session_connected(session_id)
    except Exception as e:
        result_holder[0] = e
    finally:
        io.mark_agent_done()


async def forward_agent_msgs_to_client(send_msg, io, session_id, *, result_holder=None, conn=None, storage=None):
    """Forward agent events to client. Send OUTPUT (or ERROR) when agent finishes."""
    from ..session import session_to_chat_items

    async for event in io.read_msgs_from_agent():
        if session_id:
            event["session_id"] = session_id
        await send_msg(event)

    if result_holder and isinstance(result_holder[0], Exception):
        console.print(f"[red]✗ agent error:[/red] {result_holder[0]}")
        await send_msg({"type": "ERROR", "message": str(result_holder[0])})
    elif result_holder and result_holder[0]:
        result = result_holder[0]
        session_data = result.get('session', {})
        if conn:
            conn["session"] = session_data
        await send_msg({
            "type": "OUTPUT",
            "result": result["result"],
            "session_id": session_id,
            "duration_ms": result["duration_ms"],
            "session": session_data,
            "chat_items": session_to_chat_items(session_data),
        })
    elif storage:
        stored = storage.get(session_id)
        if stored and stored.status == "done":
            await send_msg({
                "type": "OUTPUT",
                "result": stored.result,
                "session_id": session_id,
                "duration_ms": stored.duration_ms,
                "session": stored.session,
                "chat_items": session_to_chat_items(stored.session or {}),
            })
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
    console.print(f"  [dim]↻ resuming forwarding to running agent[/dim]")
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
        console.print(f"[red]✗ INPUT rejected:[/red] not authenticated (send CONNECT first)")
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
