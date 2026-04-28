"""Transport-agnostic WebSocket protocol handler.

Both direct ASGI WebSocket and relay sessions use run_protocol()
with their own send_msg/recv_msg adapters, eliminating the need
for a loopback WebSocket connection in the relay path.
"""

import asyncio
import json
import queue
import threading
import uuid

from rich.console import Console
from .io import WebSocketIO

console = Console()


async def _pump_agent_events_to_client(send_msg, io, agent_finished, disconnected, session_id):
    """Drain agent outgoing queue and send each event to client."""
    loop = asyncio.get_event_loop()
    while not agent_finished.is_set() and not disconnected.is_set():
        try:
            event = await loop.run_in_executor(
                None, lambda: io._outgoing.get(timeout=0.05)
            )
            if session_id:
                event["session_id"] = session_id
            await send_msg(event)
        except queue.Empty:
            pass

    if not disconnected.is_set():
        while True:
            try:
                event = io._outgoing.get_nowait()
                if session_id:
                    event["session_id"] = session_id
                await send_msg(event)
            except queue.Empty:
                break


async def _pump_client_messages_to_agent(recv_msg, io, agent_finished, disconnected, registry, session_id):
    """Read client messages from transport and put into agent IO incoming queue."""
    while not agent_finished.is_set():
        try:
            data = await asyncio.wait_for(recv_msg(), timeout=0.1)
            if data is None:
                disconnected.set()
                io.close()
                break
            if registry and session_id:
                registry.update_ping(session_id)
            if data.get("type") != "PONG":
                io._incoming.put(data)
        except asyncio.TimeoutError:
            continue


async def _send_ping(send_msg, agent_finished, disconnected):
    """Send PING every 30s to keep connection alive."""
    while not agent_finished.is_set() and not disconnected.is_set():
        await asyncio.sleep(30)
        if not agent_finished.is_set() and not disconnected.is_set():
            try:
                await send_msg({"type": "PING"})
            except Exception:
                disconnected.set()
                break


async def _pipe_agent_io(send_msg, recv_msg, io, agent_finished, registry=None, session_id=None, enable_ping=True):
    """Bridge agent IO queues with transport. Returns True if client disconnected first."""
    disconnected = asyncio.Event()

    send_task = asyncio.create_task(_pump_agent_events_to_client(send_msg, io, agent_finished, disconnected, session_id))
    recv_task = asyncio.create_task(_pump_client_messages_to_agent(recv_msg, io, agent_finished, disconnected, registry, session_id))
    ping_task = asyncio.create_task(_send_ping(send_msg, agent_finished, disconnected)) if enable_ping else None

    while not agent_finished.is_set():
        await asyncio.sleep(0.05)

    recv_task.cancel()
    if ping_task:
        ping_task.cancel()
    try:
        await recv_task
    except asyncio.CancelledError:
        pass
    if ping_task:
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
    await send_task

    return disconnected.is_set()


def _run_agent_thread(route_handlers, storage, prompt, io, session, images, files, registry, session_id, result_holder, agent_finished):
    """Thread target: run agent and store result."""
    try:
        result_holder[0] = route_handlers["ws_input"](storage, prompt, io, session, images, files)
        registry.mark_connected(session_id)
    finally:
        agent_finished.set()


async def _handle_session_status(data, send_msg, registry):
    """Handle SESSION_STATUS message."""
    sid = (data.get("session") or {}).get("session_id")
    if not sid:
        await send_msg({"type": "SESSION_STATUS", "session_id": None, "status": "not_found"})
        return
    active = registry.get(sid)
    status = active.status if active else "not_found"
    await send_msg({"type": "SESSION_STATUS", "session_id": sid, "status": status})


async def _reattach_executing(send_msg, recv_msg, active, registry, session_id, storage, enable_ping):
    """Reattach to a running agent session and pipe remaining IO."""
    console.print(f"  [dim]↻ reattaching to running agent[/dim]")
    io = active.io
    agent_finished = active.agent_finished

    while not io._outgoing.empty():
        try:
            event = io._outgoing.get_nowait()
            await send_msg(event)
        except queue.Empty:
            break

    registry.update_ping(session_id)
    client_disconnected = await _pipe_agent_io(send_msg, recv_msg, io, agent_finished, registry, session_id, enable_ping)

    if client_disconnected:
        registry.mark_suspended(session_id)
    else:
        from .host.session import session_to_chat_items
        stored = storage.get(session_id)
        if stored and stored.status == "done":
            chat_items = session_to_chat_items(stored.session or {})
            await send_msg({
                "type": "OUTPUT",
                "result": stored.result,
                "session_id": session_id,
                "duration_ms": stored.duration_ms,
                "session": stored.session,
                "chat_items": chat_items,
            })


async def _handle_connect(data, send_msg, recv_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist, enable_ping):
    """Handle CONNECT message: auth, session merge, send CONNECTED."""
    _, identity, sig_valid, err = route_handlers["auth"](
        data, trust, blacklist=blacklist, whitelist=whitelist
    )

    if err and "forbidden" in err.lower():
        trust_agent = route_handlers["trust_agent"]
        onboard_info = _get_onboard_requirements(trust_agent)
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
        from .host.session import merge_sessions
        stored = storage.get(session_id)
        if stored and stored.session:
            client = conn["session"] or {}
            conn["session"], server_newer = merge_sessions(client_session=client, server_session=stored.session)
            if server_newer:
                console.print(f"  [dim]↕ merged sessions (server newer)[/dim]")

    active = registry.get(session_id)
    if active and active.status == 'executing':
        status = "executing"
    elif active and active.status in ('connected', 'suspended'):
        status = "connected"
        registry.update_ping(session_id)
    else:
        status = "new"

    console.print(f"[green]✓ CONNECT[/green] identity={identity[:16]}... session={session_id[:8]}... status={status}{' (server_newer)' if server_newer else ''}")

    connected_msg = {"type": "CONNECTED", "session_id": session_id, "status": status}
    if server_newer and conn["session"]:
        from .host.session import session_to_chat_items
        connected_msg["server_newer"] = True
        connected_msg["session"] = conn["session"]
        connected_msg["chat_items"] = session_to_chat_items(conn["session"])
    await send_msg(connected_msg)

    if status == "executing":
        await _reattach_executing(send_msg, recv_msg, active, registry, session_id, storage, enable_ping)


async def _handle_input(data, send_msg, recv_msg, conn, route_handlers, storage, registry, enable_ping):
    """Handle INPUT message: validate, run agent, send OUTPUT."""
    if not conn["authenticated"]:
        console.print(f"[red]✗ INPUT rejected:[/red] not authenticated (send CONNECT first)")
        await send_msg({"type": "ERROR", "message": "authenticate first (send CONNECT)"})
        return

    prompt = data.get("prompt")
    if not prompt:
        await send_msg({"type": "ERROR", "message": "prompt required"})
        return

    identity = conn["identity"]
    session_id = conn["session_id"]
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
    agent_finished = threading.Event()
    result_holder = [None]

    agent_thread = threading.Thread(
        target=_run_agent_thread,
        args=(route_handlers, storage, prompt, io, session, images, files, registry, session_id, result_holder, agent_finished),
        daemon=True,
    )
    agent_thread.start()
    registry.register(session_id, io, agent_thread, agent_finished)

    client_disconnected = await _pipe_agent_io(send_msg, recv_msg, io, agent_finished, registry, session_id, enable_ping)

    if client_disconnected:
        if session_id:
            registry.mark_suspended(session_id)
    elif result_holder[0]:
        from .host.session import session_to_chat_items
        result = result_holder[0]
        conn["session"] = result.get('session', {})
        chat_items = session_to_chat_items(conn["session"])
        await send_msg({
            "type": "OUTPUT",
            "result": result["result"],
            "session_id": session_id,
            "duration_ms": result["duration_ms"],
            "session": conn["session"],
            "chat_items": chat_items,
        })
    else:
        await send_msg({"type": "ERROR", "message": "Agent completed without result"})


def _get_onboard_requirements(trust_agent) -> dict | None:
    """Extract onboard requirements from trust config."""
    config = trust_agent.config
    onboard = config.get("onboard", {})
    if not onboard:
        return None

    result = {"methods": []}
    if "invite_code" in onboard:
        result["methods"].append("invite_code")
    if "payment" in onboard:
        result["methods"].append("payment")
        result["payment_amount"] = onboard["payment"]
        payment_address = trust_agent.get_self_address()
        if payment_address:
            result["payment_address"] = payment_address

    return result if result["methods"] else None


async def _handle_onboard_submit(data, send_msg, route_handlers):
    """Handle ONBOARD_SUBMIT message from client."""
    trust_agent = route_handlers["trust_agent"]

    _, identity, sig_valid, err = route_handlers["auth"](data, "open")
    if err or not sig_valid:
        await send_msg({"type": "ERROR", "message": err or "invalid signature"})
        return

    if trust_agent.is_blocked(identity):
        await send_msg({"type": "ERROR", "message": "forbidden: blocked"})
        return

    payload = data.get("payload", {})
    invite_code = payload.get("invite_code")
    payment = payload.get("payment", 0)

    if invite_code:
        if trust_agent.verify_invite(identity, invite_code):
            actual_level = trust_agent.get_level(identity)
            console.print(f"[green]✓[/green] Verified [bold]{identity[:16]}...[/bold] with invite code [cyan]{invite_code}[/cyan] → {actual_level}")
            await send_msg({
                "type": "ONBOARD_SUCCESS",
                "identity": identity,
                "level": actual_level,
                "message": f"Invite code verified. You are now a {actual_level}."
            })
            return
        else:
            console.print(f"[red]✗[/red] Invalid invite code [cyan]{invite_code}[/cyan] from {identity[:16]}...")
            await send_msg({"type": "ERROR", "message": "Invalid invite code"})
            return

    if payment > 0:
        if trust_agent.verify_payment(identity, payment):
            actual_level = trust_agent.get_level(identity)
            console.print(f"[green]✓[/green] Verified [bold]{identity[:16]}...[/bold] with payment [cyan]${payment}[/cyan] → {actual_level}")
            await send_msg({
                "type": "ONBOARD_SUCCESS",
                "identity": identity,
                "level": actual_level,
                "message": f"Payment verified. You are now a {actual_level}."
            })
            return
        else:
            console.print(f"[red]✗[/red] Insufficient payment [cyan]${payment}[/cyan] from {identity[:16]}...")
            await send_msg({"type": "ERROR", "message": "Insufficient payment"})
            return

    await send_msg({"type": "ERROR", "message": "invite_code or payment required"})


async def _handle_admin_message(data, send_msg, route_handlers):
    """Handle ADMIN_* messages from client."""
    trust_agent = route_handlers["trust_agent"]
    msg_type = data.get("type")

    _, identity, sig_valid, err = route_handlers["auth"](data, "open")
    if err or not sig_valid:
        await send_msg({"type": "ERROR", "message": err or "invalid signature"})
        return

    if not trust_agent.is_admin(identity):
        await send_msg({"type": "ERROR", "message": "forbidden: admin only"})
        return

    payload = data.get("payload", {})
    client_id = payload.get("client_id")

    if msg_type == "ADMIN_PROMOTE":
        if not client_id:
            await send_msg({"type": "ERROR", "message": "client_id required"})
            return
        result = route_handlers["admin_trust_promote"](client_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "promote", **result})

    elif msg_type == "ADMIN_DEMOTE":
        if not client_id:
            await send_msg({"type": "ERROR", "message": "client_id required"})
            return
        result = route_handlers["admin_trust_demote"](client_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "demote", **result})

    elif msg_type == "ADMIN_BLOCK":
        if not client_id:
            await send_msg({"type": "ERROR", "message": "client_id required"})
            return
        reason = payload.get("reason", "")
        result = route_handlers["admin_trust_block"](client_id, reason)
        await send_msg({"type": "ADMIN_RESULT", "action": "block", **result})

    elif msg_type == "ADMIN_UNBLOCK":
        if not client_id:
            await send_msg({"type": "ERROR", "message": "client_id required"})
            return
        result = route_handlers["admin_trust_unblock"](client_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "unblock", **result})

    elif msg_type == "ADMIN_GET_LEVEL":
        if not client_id:
            await send_msg({"type": "ERROR", "message": "client_id required"})
            return
        result = route_handlers["admin_trust_level"](client_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "get_level", **result})

    elif msg_type == "ADMIN_ADD":
        if not trust_agent.is_super_admin(identity):
            await send_msg({"type": "ERROR", "message": "forbidden: super admin only"})
            return
        admin_id = payload.get("admin_id")
        if not admin_id:
            await send_msg({"type": "ERROR", "message": "admin_id required"})
            return
        result = route_handlers["admin_admins_add"](admin_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "add_admin", **result})

    elif msg_type == "ADMIN_REMOVE":
        if not trust_agent.is_super_admin(identity):
            await send_msg({"type": "ERROR", "message": "forbidden: super admin only"})
            return
        admin_id = payload.get("admin_id")
        if not admin_id:
            await send_msg({"type": "ERROR", "message": "admin_id required"})
            return
        result = route_handlers["admin_admins_remove"](admin_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "remove_admin", **result})

    else:
        await send_msg({"type": "ERROR", "message": f"Unknown admin action: {msg_type}"})


async def run_protocol(send_msg, recv_msg, *, route_handlers, storage, registry, trust, blacklist=None, whitelist=None, enable_ping=True):
    """Run the WebSocket protocol message loop.

    Transport-agnostic — works with any send_msg/recv_msg pair.
    """
    conn = {"authenticated": False, "identity": None, "session_id": None, "session": None}

    while True:
        data = await recv_msg()
        if data is None:
            break

        msg_type = data.get("type")
        if msg_type not in ("CONNECT", "INPUT", "SESSION_STATUS", "PONG"):
            console.print(f"[dim]← recv: {msg_type}[/dim]")

        if msg_type == "SESSION_STATUS":
            await _handle_session_status(data, send_msg, registry)
        elif msg_type == "ONBOARD_SUBMIT":
            await _handle_onboard_submit(data, send_msg, route_handlers)
        elif msg_type and msg_type.startswith("ADMIN_"):
            await _handle_admin_message(data, send_msg, route_handlers)
        elif msg_type == "CONNECT":
            await _handle_connect(data, send_msg, recv_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist, enable_ping)
        elif msg_type == "INPUT":
            await _handle_input(data, send_msg, recv_msg, conn, route_handlers, storage, registry, enable_ping)
