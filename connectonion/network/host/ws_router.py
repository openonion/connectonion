"""WebSocket message router.

run_session() drives one client session from connect to disconnect:
init state → loop reading messages → route each via route_message → cleanup.

Both direct ASGI WebSocket and relay paths invoke run_session with their
own send_msg/recv_msg adapters. run_session is the single reader of
recv_msg — no other function touches it.
"""

import asyncio
import json
import threading
import uuid

from rich.console import Console
from ..io import WebSocketIO
from ..trust.ws_admin import handle_admin_message, handle_onboard_submit, get_onboard_requirements

console = Console()


async def _ping_loop(send_msg):
    """Send PING every 30s to keep connection alive."""
    while True:
        await asyncio.sleep(30)
        await send_msg({"type": "PING"})


async def _forward_msgs_from_agent(send_msg, io, session_id, *, result_holder=None, conn=None, storage=None):
    """Forward agent events to client. Send OUTPUT when agent finishes."""
    from .session import session_to_chat_items

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


def _run_agent_thread(route_handlers, storage, prompt, io, session, images, files, registry, session_id, result_holder):
    """Thread target: run agent and store result. Calls io.finish() when done."""
    try:
        result_holder[0] = route_handlers["ws_input"](storage, prompt, io, session, images, files)
        registry.mark_session_connected(session_id)
    except Exception as e:
        result_holder[0] = e
    finally:
        io.finish()


async def _handle_session_status(data, send_msg, registry):
    """Handle SESSION_STATUS message."""
    sid = (data.get("session") or {}).get("session_id")
    if not sid:
        await send_msg({"type": "SESSION_STATUS", "session_id": None, "status": "not_found"})
        return
    active = registry.get(sid)
    status = active.status if active else "not_found"
    await send_msg({"type": "SESSION_STATUS", "session_id": sid, "status": status})


def _resume_connection(send_msg, active, registry, session_id, storage):
    """Resume forwarding from a running agent session. Returns (io, forward_task)."""
    console.print(f"  [dim]↻ resuming connection to running agent[/dim]")
    io = active.io
    registry.update_ping(session_id)
    task = asyncio.create_task(
        _forward_msgs_from_agent(send_msg, io, session_id, storage=storage)
    )
    return io, task


async def _handle_connect(data, send_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist):
    """Handle CONNECT message: auth, session merge, send CONNECTED. Returns (io, task) for reattach or None."""
    _, identity, sig_valid, err = route_handlers["auth"](
        data, trust, blacklist=blacklist, whitelist=whitelist
    )

    if err and "forbidden" in err.lower():
        trust_agent = route_handlers["trust_agent"]
        onboard_info = get_onboard_requirements(trust_agent)
        if onboard_info:
            await send_msg({"type": "ONBOARD_REQUIRED", "identity": identity, **onboard_info})
            return

    if err:
        console.print(f"[red]✗ CONNECT auth error:[/red] {err}")
        await send_msg({"type": "ERROR", "message": err})
        return

    conn["authenticated"] = True
    conn["identity"] = identity
    session_id = data.get("session_id") or str(uuid.uuid4())
    conn["session_id"] = session_id
    conn["session"] = data.get("session")
    server_newer = False

    if conn["session"]:
        msg_count = len(conn["session"].get("messages", []))
        console.print(f"  [dim]↑ client session: {msg_count} messages[/dim]")

    if session_id:
        from .session import merge_sessions
        stored = storage.get(session_id)
        if stored and stored.session:
            client = conn["session"] or {}
            conn["session"], server_newer = merge_sessions(client_session=client, server_session=stored.session)
            if server_newer:
                console.print(f"  [dim]↕ merged sessions (server newer)[/dim]")

    active = registry.get(session_id)
    if active and active.status == 'running':
        status = "running"
    elif active and active.status == 'connected':
        status = "connected"
        registry.update_ping(session_id)
    else:
        status = "new"

    console.print(f"[green]✓ CONNECT[/green] identity={identity[:16]}... session={session_id[:8]}... status={status}{' (server_newer)' if server_newer else ''}")

    connected_msg = {"type": "CONNECTED", "session_id": session_id, "status": status}
    if server_newer and conn["session"]:
        from .session import session_to_chat_items
        connected_msg["server_newer"] = True
        connected_msg["session"] = conn["session"]
        connected_msg["chat_items"] = session_to_chat_items(conn["session"])
    await send_msg(connected_msg)

    if status == "running":
        active.io.rewind_to(data.get("last_msg_id"))
        return _resume_connection(send_msg, active, registry, session_id, storage)


async def _try_runtime_input(data, send_msg, conn, registry):
    """If session has a running agent, route INPUT as mid-execution runtime input. Returns True if handled."""
    if not conn.get("authenticated"):
        return False
    session_id = conn.get("session_id")
    if not session_id:
        return False
    existing = registry.get(session_id)
    if not existing or existing.status != "running":
        return False
    prompt = data.get("prompt")
    if not prompt:
        await send_msg({"type": "ERROR", "message": "prompt required"})
        return True
    runtime_input_id = str(uuid.uuid4())
    existing.io.push_runtime_input({"type": "RUNTIME_INPUT", "id": runtime_input_id, "prompt": prompt})
    console.print(f"[yellow]↳ RUNTIME_INPUT[/yellow] session={session_id[:8]}... prompt={prompt[:50]}...")
    await send_msg({"type": "RUNTIME_INPUT_ACK", "session_id": session_id, "id": runtime_input_id})
    return True


async def _start_agent(data, send_msg, conn, route_handlers, storage, registry):
    """Validate INPUT, start agent thread. Returns (io, forward_task) or None on error."""
    if not conn["authenticated"]:
        console.print(f"[red]✗ INPUT rejected:[/red] not authenticated (send CONNECT first)")
        await send_msg({"type": "ERROR", "message": "authenticate first (send CONNECT)"})
        return None

    prompt = data.get("prompt")
    if not prompt:
        await send_msg({"type": "ERROR", "message": "prompt required"})
        return None

    session_id = conn["session_id"]
    existing = registry.get(session_id)
    # Defense in depth: route_message routes INPUT-during-running to
    # _try_runtime_input first; if any future caller bypasses that, refuse to
    # spawn a second agent thread on the same session.
    if existing and existing.status == "running":
        await send_msg({"type": "ERROR", "message": "session already has a running agent", "session_id": session_id})
        return None

    identity = conn["identity"]
    console.print(f"[green]✓ INPUT[/green] identity={identity[:16] if identity else '?'}... session={session_id[:8] if session_id else '?'}... prompt={prompt[:50]}...")

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
        target=_run_agent_thread,
        args=(route_handlers, storage, prompt, io, session, images, files, registry, session_id, result_holder),
        daemon=True,
    )
    # Register BEFORE start: thread may complete before .start() returns control,
    # and _run_agent_thread calls registry.mark_session_connected() on completion.
    # If register runs after, mark_session_connected is a no-op and we end up
    # with a 'running' entry for an already-finished agent.
    if existing:
        registry.mark_session_running(session_id, io, agent_thread)
    else:
        registry.register(session_id, io, agent_thread)
    agent_thread.start()

    task = asyncio.create_task(
        _forward_msgs_from_agent(send_msg, io, session_id, result_holder=result_holder, conn=conn)
    )
    return io, task


def _init_session(send_msg, enable_ping):
    """Per-session mutable state: auth/identity, current agent IO, async tasks."""
    return {
        "conn": {"authenticated": False, "identity": None, "session_id": None, "session": None},
        "active_io": None,
        "forward_task": None,
        "ping_task": asyncio.create_task(_ping_loop(send_msg)) if enable_ping else None,
    }


async def _cleanup_session(state):
    """Cancel forward + ping tasks at session end and let their CancelledError unwind."""
    # asyncio cancel idiom: cancel() only signals; await ensures the task
    # actually unwinds before we return. The CancelledError surfaced by
    # that await is the expected exit signal — not a bug, swallow it.
    forward_task = state.get("forward_task")
    if forward_task and not forward_task.done():
        forward_task.cancel()
        try:
            await forward_task
        except asyncio.CancelledError:
            pass
    ping_task = state.get("ping_task")
    if ping_task:
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass


async def route_message(data, state, send_msg, route_handlers, storage, registry, trust, blacklist, whitelist):
    """Route one client message to the right handler. Mutates state in place."""
    conn = state["conn"]
    msg_type = data.get("type")

    # Anything outside the hot path (CONNECT/INPUT/SESSION_STATUS/PONG) is
    # logged for visibility — these are rare and useful to see.
    if msg_type not in ("CONNECT", "INPUT", "SESSION_STATUS", "PONG"):
        console.print(f"[dim]← recv: {msg_type}[/dim]")

    if msg_type == "PONG":
        # Heartbeat from client — refresh registry ping so cleanup_expired won't reap us.
        if conn.get("session_id"):
            registry.update_ping(conn["session_id"])
    elif msg_type == "SESSION_STATUS":
        await _handle_session_status(data, send_msg, registry)
    elif msg_type == "ONBOARD_SUBMIT":
        await handle_onboard_submit(data, send_msg, route_handlers)
    elif msg_type and msg_type.startswith("ADMIN_"):
        await handle_admin_message(data, send_msg, route_handlers)
    elif msg_type == "CONNECT":
        # First message: auth + session merge + maybe reattach to a running agent.
        result = await _handle_connect(data, send_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist)
        if result:
            state["active_io"], state["forward_task"] = result
    elif msg_type == "INPUT":
        # If a running agent already owns this session, treat as runtime input
        # (mid-execution interjection). Otherwise spawn a fresh agent thread.
        if not await _try_runtime_input(data, send_msg, conn, registry):
            result = await _start_agent(data, send_msg, conn, route_handlers, storage, registry)
            if result:
                state["active_io"], state["forward_task"] = result
    elif state["active_io"]:
        # Anything else (ASK_USER_RESPONSE, APPROVAL_RESPONSE, mode_change, ...)
        # → forward to the running agent's input mailbox.
        state["active_io"].send_to_agent(data)


async def run_session(send_msg, recv_msg, *, route_handlers, storage, registry, trust, blacklist=None, whitelist=None, enable_ping=True):
    """Run one client session from connect to disconnect.

    Owns the read loop and per-session lifecycle: init state → loop on recv_msg
    → dispatch each message via route_message → cleanup on close.

    Used by both the direct ASGI WebSocket path and the relay-routed path,
    each providing its own send_msg/recv_msg adapters.
    """
    state = _init_session(send_msg, enable_ping)
    try:
        while True:
            data = await recv_msg()
            if data is None:
                # recv_msg returns None on client close or relay-side timeout.
                break
            await route_message(data, state, send_msg, route_handlers, storage, registry, trust, blacklist, whitelist)
    finally:
        await _cleanup_session(state)
