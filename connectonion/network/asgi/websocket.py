"""
WebSocket handling for ASGI with keep-alive and session recovery.

Protocol: CONNECT → CONNECTED → INPUT → streaming events → OUTPUT
See docs/network/websocket-protocol.md for full specification.

Client → Server:
- CONNECT          : Authenticate + find/create session. First message on every WS.
- INPUT            : Send prompt (after CONNECT)
- PONG             : Acknowledge keep-alive
- ASK_USER_RESPONSE, APPROVAL_RESPONSE, PLAN_REVIEW_RESPONSE, ULW_RESPONSE
- ONBOARD_SUBMIT   : Submit invite code or payment
- SESSION_STATUS   : Check if a session is alive
- ADMIN_*          : Admin actions (promote, demote, block, unblock)

Server → Client:
- CONNECTED        : Response to CONNECT { session_id, status: new/running/completed }
- OUTPUT           : Final result
- ERROR            : Error
- PING             : Keep-alive (every 30s)
- ONBOARD_REQUIRED, ONBOARD_SUCCESS
- Stream events    : thinking, tool_call, tool_result, ask_user, approval_needed, etc.
"""

import asyncio
import json
import queue
import threading
import uuid

from rich.console import Console
from ..io import WebSocketIO

console = Console()
# Import pydantic_json_encoder for serializing Pydantic models (e.g., TokenUsage) in WebSocket responses
from .http import pydantic_json_encoder


async def handle_websocket(
    scope,
    receive,
    send,
    *,
    route_handlers: dict,
    storage,
    registry,  # ActiveSessionRegistry for reconnection
    trust,
    blacklist: list | None = None,
    whitelist: list | None = None,
):
    """Handle WebSocket connections at /ws.

    Supports bidirectional communication via IO interface:
    - Agent sends events via agent.io.log() / agent.io.send()
    - Agent requests approval via agent.io.request_approval()
    - Client responds to approval requests

    Session support (same as HTTP):
    - Accept session_id in INPUT message for conversation continuation
    - Return session_id and session in OUTPUT message
    """
    if scope["path"] != "/ws":
        # ASGI: close connection with custom code
        await send({"type": "websocket.close", "code": 4004})
        return

    # ASGI: accept the WebSocket connection
    await send({"type": "websocket.accept"})
    client_ip = scope.get('client', ('?',))[0]
    console.print(f"[dim]⚡ ws+[/dim] [green]{client_ip}[/green] [dim]({registry.count()} active)[/dim]")

    # Connection-level state (set by CONNECT, used by subsequent INPUTs)
    conn_authenticated = False
    conn_identity = None
    conn_session_id = None
    conn_session = None

    # ASGI message loop
    while True:
        msg = await receive()  # ASGI: wait for next message
        if msg["type"] == "websocket.disconnect":  # ASGI: client disconnected
            console.print(f"[dim]⚡ ws-[/dim] [dim]({registry.count()} active)[/dim]")
            break
        if msg["type"] == "websocket.receive":  # ASGI: client sent a message
            try:
                data = json.loads(msg.get("text", "{}"))  # Our app data is inside "text"
            except json.JSONDecodeError:
                await send({"type": "websocket.send",
                           "text": json.dumps({"type": "ERROR", "message": "Invalid JSON"})})
                continue

            msg_type = data.get("type")
            # Routine types already print their own status lines — skip the generic log
            if msg_type not in ("CONNECT", "INPUT", "SESSION_STATUS", "PONG"):
                console.print(f"[dim]← WS recv: {msg_type}[/dim]")

            # Handle SESSION_STATUS (client checking if session is alive)
            if msg_type == "SESSION_STATUS":
                sid = (data.get("session") or {}).get("session_id")
                if not sid:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "SESSION_STATUS", "session_id": None, "status": "not_found"})})
                    continue
                active = registry.get(sid)
                if active:
                    status = active.status  # 'executing' | 'connected' | 'suspended'
                else:
                    status = "not_found"
                await send({"type": "websocket.send",
                           "text": json.dumps({"type": "SESSION_STATUS", "session_id": sid, "status": status})})
                continue

            # Handle ONBOARD_SUBMIT (stranger submitting invite code or payment)
            if msg_type == "ONBOARD_SUBMIT":
                await _handle_onboard_submit(data, send, route_handlers)
                continue

            # Handle ADMIN messages (promote, demote, block, unblock, get_level)
            if msg_type and msg_type.startswith("ADMIN_"):
                await _handle_admin_message(data, send, route_handlers)
                continue

            # Handle CONNECT — authenticate + find/create session
            # Server decides status based on session state
            if msg_type == "CONNECT":
                _, identity, sig_valid, err = route_handlers["auth"](
                    data, trust, blacklist=blacklist, whitelist=whitelist
                )

                if err and "forbidden" in err.lower():
                    trust_agent = route_handlers["trust_agent"]
                    onboard_info = _get_onboard_requirements(trust_agent)
                    if onboard_info:
                        await send({"type": "websocket.send",
                                   "text": json.dumps({"type": "ONBOARD_REQUIRED", "identity": identity, **onboard_info})})
                        continue

                if err:
                    console.print(f"[red]✗ CONNECT auth error:[/red] {err}")
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": err})})
                    continue

                conn_authenticated = True
                conn_identity = identity
                session_id = data.get("session_id") or str(uuid.uuid4())
                conn_session_id = session_id

                # Accept session (conversation history) from client
                conn_session = data.get("session")
                server_newer = False

                if conn_session:
                    msg_count = len(conn_session.get("messages", []))
                    console.print(f"  [dim]↑ client session: {msg_count} messages[/dim]")

                # Merge with server-stored session if available
                if session_id:
                    from ..host.session import merge_sessions, session_to_chat_items
                    stored = storage.get(session_id)
                    if stored and stored.session:
                        client = conn_session or {}
                        conn_session, server_newer = merge_sessions(
                            client_session=client,
                            server_session=stored.session
                        )
                        if server_newer:
                            console.print(f"  [dim]↕ merged sessions (server newer)[/dim]")

                # Look up session state — server decides
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
                if server_newer and conn_session:
                    connected_msg["server_newer"] = True
                    connected_msg["session"] = conn_session
                    connected_msg["chat_items"] = session_to_chat_items(conn_session)
                await send({"type": "websocket.send",
                           "text": json.dumps(connected_msg, default=pydantic_json_encoder)})

                # If agent is executing, reattach IO and pipe events
                if status == "executing":
                    console.print(f"  [dim]↻ reattaching to running agent[/dim]")
                    io = active.io
                    agent_finished = active.agent_finished

                    while not io._outgoing.empty():
                        try:
                            event = io._outgoing.get_nowait()
                            await send({"type": "websocket.send",
                                       "text": json.dumps(event, default=pydantic_json_encoder)})
                        except queue.Empty:
                            break

                    registry.update_ping(session_id)

                    client_disconnected = await _pipe_ws_io(receive, send, io, agent_finished, registry, session_id)

                    if client_disconnected:
                        registry.mark_suspended(session_id)
                    else:
                        from ..host.session import session_to_chat_items
                        stored = storage.get(session_id)
                        if stored and stored.status == "done":
                            chat_items = session_to_chat_items(stored.session or {})
                            await send({"type": "websocket.send",
                                       "text": json.dumps({
                                           "type": "OUTPUT",
                                           "result": stored.result,
                                           "session_id": session_id,
                                           "duration_ms": stored.duration_ms,
                                           "session": stored.session,
                                           "chat_items": chat_items,
                                       }, default=pydantic_json_encoder)})
                continue

            if msg_type == "INPUT":
                if not conn_authenticated:
                    console.print(f"[red]✗ INPUT rejected:[/red] not authenticated (send CONNECT first)")
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": "authenticate first (send CONNECT)"})})
                    continue

                prompt = data.get("prompt")
                if not prompt:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": "prompt required"})})
                    continue

                console.print(f"[green]✓ INPUT[/green] identity={conn_identity[:16] if conn_identity else '?'}... session={conn_session_id[:8] if conn_session_id else '?'}... prompt={prompt[:50]}...")

                # Session from CONNECT, fallback to INPUT for old clients
                session = conn_session or data.get("session") or {}
                images = data.get("images")
                files = data.get("files")
                attachments = []
                if images:
                    attachments.append(f"{len(images)} images")
                if files:
                    attachments.append(f"{len(files)} files")
                if attachments:
                    console.print(f"  [dim]↑ {', '.join(attachments)}[/dim]")
                session_id = conn_session_id

                from ..host.session import session_to_chat_items

                io = WebSocketIO()
                agent_finished = threading.Event()
                result_holder = [None]
                error_holder = [None]

                def run_agent():
                    result_holder[0] = route_handlers["ws_input"](storage, prompt, io, session, images, files)
                    registry.mark_connected(session_id)
                    agent_finished.set()

                agent_thread = threading.Thread(target=run_agent, daemon=True)
                agent_thread.start()
                registry.register(session_id, io, agent_thread, agent_finished)

                client_disconnected = await _pipe_ws_io(receive, send, io, agent_finished, registry, session_id)

                if client_disconnected:
                    if session_id:
                        registry.mark_suspended(session_id)
                elif error_holder[0]:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": error_holder[0]})})
                elif result_holder[0]:
                    result = result_holder[0]
                    # Update conn_session for next INPUT on same WS
                    conn_session = result.get('session', {})
                    chat_items = session_to_chat_items(conn_session)
                    await send({"type": "websocket.send",
                               "text": json.dumps({
                                   "type": "OUTPUT",
                                   "result": result["result"],
                                   "session_id": result["session_id"],
                                   "duration_ms": result["duration_ms"],
                                   "session": conn_session,
                                   "chat_items": chat_items,
                               }, default=pydantic_json_encoder)})
                else:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": "Agent completed without result"})})


async def _pipe_ws_io(ws_receive, ws_send, io: WebSocketIO, agent_finished: threading.Event,
                      registry=None, session_id=None) -> bool:
    """Pipe messages between WebSocket and IO queues with keep-alive.

    Runs until agent completes. Handles:
    - Outgoing: io._outgoing queue -> WebSocket (agent events)
    - Incoming: WebSocket -> io._incoming queue (approval responses, PONG)
    - Keep-alive: PING messages every 30s to detect dead connections

    Returns:
        True if client disconnected before agent completed, False otherwise.
        When True, caller should skip sending final OUTPUT (client is gone,
        but result is already saved to SessionStorage for polling recovery).
    """
    loop = asyncio.get_event_loop()

    disconnected = asyncio.Event()

    async def send_outgoing():
        """Send outgoing messages from IO to WebSocket."""
        while not agent_finished.is_set() and not disconnected.is_set():
            try:
                event = await loop.run_in_executor(
                    None, lambda: io._outgoing.get(timeout=0.05)
                )
                await ws_send({"type": "websocket.send", "text": json.dumps(event, default=pydantic_json_encoder)})
            except queue.Empty:
                pass

        # Drain remaining messages (only if client still connected)
        if not disconnected.is_set():
            while True:
                try:
                    event = io._outgoing.get_nowait()
                    await ws_send({"type": "websocket.send", "text": json.dumps(event, default=pydantic_json_encoder)})
                except queue.Empty:
                    break

    async def receive_incoming():
        """Receive incoming messages from WebSocket to IO."""
        while not agent_finished.is_set():
            try:
                msg = await asyncio.wait_for(ws_receive(), timeout=0.1)
                if msg["type"] == "websocket.receive":
                    try:
                        data = json.loads(msg.get("text", "{}"))
                        # Update ping timestamp in registry
                        if registry and session_id:
                            registry.update_ping(session_id)
                        # Handle PONG responses (client responding to PING)
                        if data.get("type") == "PONG":
                            pass  # Just acknowledge, no action needed
                        else:
                            io._incoming.put(data)
                    except json.JSONDecodeError:
                        pass
                elif msg["type"] == "websocket.disconnect":
                    disconnected.set()
                    io.close()
                    break
            except asyncio.TimeoutError:
                continue

    async def send_ping():
        """Send PING messages every 30 seconds to keep connection alive."""
        while not agent_finished.is_set() and not disconnected.is_set():
            await asyncio.sleep(30)  # Send ping every 30 seconds
            if not agent_finished.is_set() and not disconnected.is_set():
                try:
                    await ws_send({"type": "websocket.send", "text": json.dumps({"type": "PING"})})
                except Exception:
                    # Connection likely closed, stop pinging
                    break

    send_task = asyncio.create_task(send_outgoing())
    recv_task = asyncio.create_task(receive_incoming())
    ping_task = asyncio.create_task(send_ping())

    while not agent_finished.is_set():
        await asyncio.sleep(0.05)

    # Cancel all tasks
    recv_task.cancel()
    ping_task.cancel()
    try:
        await recv_task
    except asyncio.CancelledError:
        pass
    try:
        await ping_task
    except asyncio.CancelledError:
        pass
    await send_task

    return disconnected.is_set()


def _get_onboard_requirements(trust_agent) -> dict | None:
    """Get onboard requirements from trust config."""
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
        # Include agent's address for payment transfer
        payment_address = trust_agent.get_self_address()
        if payment_address:
            result["payment_address"] = payment_address

    return result if result["methods"] else None


async def _handle_onboard_submit(data: dict, send, route_handlers: dict):
    """Handle ONBOARD_SUBMIT message from client."""
    trust_agent = route_handlers["trust_agent"]

    # Authenticate the request (signature check only, open trust)
    _, identity, sig_valid, err = route_handlers["auth"](data, "open")
    if err or not sig_valid:
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ERROR", "message": err or "invalid signature"})})
        return

    # Check if blocked BEFORE onboarding (don't waste invite codes/payments)
    if trust_agent.is_blocked(identity):
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ERROR", "message": "forbidden: blocked"})})
        return

    payload = data.get("payload", {})
    invite_code = payload.get("invite_code")
    payment = payload.get("payment", 0)

    # Try invite code
    if invite_code:
        if trust_agent.verify_invite(identity, invite_code):
            # Get actual level after promotion (may differ if already promoted)
            actual_level = trust_agent.get_level(identity)
            # Log to server console for auditing
            console.print(f"[green]✓[/green] Verified [bold]{identity[:16]}...[/bold] with invite code [cyan]{invite_code}[/cyan] → {actual_level}")
            await send({"type": "websocket.send",
                       "text": json.dumps({
                           "type": "ONBOARD_SUCCESS",
                           "identity": identity,
                           "level": actual_level,
                           "message": f"Invite code verified. You are now a {actual_level}."
                       })})
            return
        else:
            console.print(f"[red]✗[/red] Invalid invite code [cyan]{invite_code}[/cyan] from {identity[:16]}...")
            await send({"type": "websocket.send",
                       "text": json.dumps({"type": "ERROR", "message": "Invalid invite code"})})
            return

    # Try payment
    if payment > 0:
        if trust_agent.verify_payment(identity, payment):
            # Get actual level after promotion
            actual_level = trust_agent.get_level(identity)
            # Log to server console for auditing
            console.print(f"[green]✓[/green] Verified [bold]{identity[:16]}...[/bold] with payment [cyan]${payment}[/cyan] → {actual_level}")
            await send({"type": "websocket.send",
                       "text": json.dumps({
                           "type": "ONBOARD_SUCCESS",
                           "identity": identity,
                           "level": actual_level,
                           "message": f"Payment verified. You are now a {actual_level}."
                       })})
            return
        else:
            console.print(f"[red]✗[/red] Insufficient payment [cyan]${payment}[/cyan] from {identity[:16]}...")
            await send({"type": "websocket.send",
                       "text": json.dumps({"type": "ERROR", "message": "Insufficient payment"})})
            return

    await send({"type": "websocket.send",
               "text": json.dumps({"type": "ERROR", "message": "invite_code or payment required"})})


async def _handle_admin_message(data: dict, send, route_handlers: dict):
    """Handle ADMIN_* messages from client."""
    trust_agent = route_handlers["trust_agent"]
    msg_type = data.get("type")

    # Authenticate the request
    _, identity, sig_valid, err = route_handlers["auth"](data, "open")
    if err or not sig_valid:
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ERROR", "message": err or "invalid signature"})})
        return

    # Check admin permission
    if not trust_agent.is_admin(identity):
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ERROR", "message": "forbidden: admin only"})})
        return

    payload = data.get("payload", {})
    client_id = payload.get("client_id")

    # Handle each admin action
    if msg_type == "ADMIN_PROMOTE":
        if not client_id:
            await send({"type": "websocket.send",
                       "text": json.dumps({"type": "ERROR", "message": "client_id required"})})
            return
        result = route_handlers["admin_trust_promote"](client_id)
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ADMIN_RESULT", "action": "promote", **result})})

    elif msg_type == "ADMIN_DEMOTE":
        if not client_id:
            await send({"type": "websocket.send",
                       "text": json.dumps({"type": "ERROR", "message": "client_id required"})})
            return
        result = route_handlers["admin_trust_demote"](client_id)
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ADMIN_RESULT", "action": "demote", **result})})

    elif msg_type == "ADMIN_BLOCK":
        if not client_id:
            await send({"type": "websocket.send",
                       "text": json.dumps({"type": "ERROR", "message": "client_id required"})})
            return
        reason = payload.get("reason", "")
        result = route_handlers["admin_trust_block"](client_id, reason)
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ADMIN_RESULT", "action": "block", **result})})

    elif msg_type == "ADMIN_UNBLOCK":
        if not client_id:
            await send({"type": "websocket.send",
                       "text": json.dumps({"type": "ERROR", "message": "client_id required"})})
            return
        result = route_handlers["admin_trust_unblock"](client_id)
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ADMIN_RESULT", "action": "unblock", **result})})

    elif msg_type == "ADMIN_GET_LEVEL":
        if not client_id:
            await send({"type": "websocket.send",
                       "text": json.dumps({"type": "ERROR", "message": "client_id required"})})
            return
        result = route_handlers["admin_trust_level"](client_id)
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ADMIN_RESULT", "action": "get_level", **result})})

    elif msg_type == "ADMIN_ADD":
        # Super admin only
        if not trust_agent.is_super_admin(identity):
            await send({"type": "websocket.send",
                       "text": json.dumps({"type": "ERROR", "message": "forbidden: super admin only"})})
            return
        admin_id = payload.get("admin_id")
        if not admin_id:
            await send({"type": "websocket.send",
                       "text": json.dumps({"type": "ERROR", "message": "admin_id required"})})
            return
        result = route_handlers["admin_admins_add"](admin_id)
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ADMIN_RESULT", "action": "add_admin", **result})})

    elif msg_type == "ADMIN_REMOVE":
        # Super admin only
        if not trust_agent.is_super_admin(identity):
            await send({"type": "websocket.send",
                       "text": json.dumps({"type": "ERROR", "message": "forbidden: super admin only"})})
            return
        admin_id = payload.get("admin_id")
        if not admin_id:
            await send({"type": "websocket.send",
                       "text": json.dumps({"type": "ERROR", "message": "admin_id required"})})
            return
        result = route_handlers["admin_admins_remove"](admin_id)
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ADMIN_RESULT", "action": "remove_admin", **result})})

    else:
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "ERROR", "message": f"Unknown admin action: {msg_type}"})})
