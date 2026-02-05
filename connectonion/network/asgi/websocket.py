"""
Purpose: WebSocket bidirectional communication for ASGI server with real-time agent I/O and keep-alive
LLM-Note:
  Dependencies: imports from [network/io/websocket.py, network/asgi/http.py pydantic_json_encoder, asyncio, json, queue, threading] | imported by [network/asgi/__init__.py] | tested by [tests/network/test_asgi_websocket.py]
  Data flow: handle_websocket() accepts connection → receives INPUT message with prompt+session → authenticates via route_handlers["auth"] → starts agent in background thread with WebSocketIO → sends PING every 30s for keep-alive → agent sends events via io.log()/send() → forwards to client via websocket.send → client responds with PONG to PING → client sends ASK_USER_RESPONSE for approvals → io receives via queue → agent resumes → returns OUTPUT with result+session_id → result saved to SessionStorage even if client disconnects
  State/Effects: maintains WebSocket connection during agent execution | runs agent in daemon thread (non-blocking) | uses queue.Queue for thread-safe I/O between agent and WebSocket | no persistent state (connection-scoped) | results persisted to .co/session_results.jsonl for 24h TTL
  Integration: exposes handle_websocket(scope, receive, send, route_handlers, storage, trust, blacklist, whitelist) | uses WebSocketIO for bidirectional I/O | supports session continuation (same as HTTP) | message types: INPUT (client), OUTPUT/ERROR (server), PING (server), PONG (client), ASK_USER_RESPONSE (client), trace events (server) | clients can poll GET /sessions/{id} to recover results after disconnect
  Performance: async WebSocket handling | agent runs in separate thread to avoid blocking | queue-based message passing | streams events in real-time (thinking, tool_result, approval_needed) | PING task keeps connection alive through proxies/firewalls
  Errors: sends ERROR message for invalid JSON, auth failures, missing prompt | closes connection with code 4004 for wrong path | catches exceptions in agent thread and sends ERROR | saves result to storage even on disconnect (enables polling recovery)
WebSocket handling for ASGI with keep-alive and session recovery.

ASGI Protocol Types (not our custom types - this is the ASGI spec):
- websocket.connect    : ASGI sends when client wants to connect
- websocket.accept     : We send to accept the connection
- websocket.receive    : ASGI sends when client sends a message
- websocket.send       : We send to deliver a message to client
- websocket.disconnect : ASGI sends when client disconnects
- websocket.close      : We send to close the connection

Our Application Types (sent inside websocket.send text payload):
- INPUT              : Client sends prompt with session_id
- OUTPUT             : Server sends final result with session_id
- ERROR              : Server sends error message
- PING               : Server keep-alive (every 30s)
- PONG               : Client acknowledges keep-alive
- ASK_USER_RESPONSE  : Client responds to approval request
- ONBOARD_REQUIRED   : Server sends when stranger needs to onboard
- ONBOARD_SUBMIT     : Client sends invite_code or payment
- ONBOARD_SUCCESS    : Server confirms onboard complete
- ADMIN_PROMOTE      : Client (admin) requests promote
- ADMIN_DEMOTE       : Client (admin) requests demote
- ADMIN_BLOCK        : Client (admin) requests block
- ADMIN_UNBLOCK      : Client (admin) requests unblock
- ADMIN_GET_LEVEL    : Client (admin) requests client level
- ADMIN_RESULT       : Server sends admin action result
- (trace events)     : thinking, tool_result, approval_needed, etc.
"""

import asyncio
import json
import queue
import threading

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
    trust: str,
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

    # ASGI message loop
    while True:
        msg = await receive()  # ASGI: wait for next message
        if msg["type"] == "websocket.disconnect":  # ASGI: client disconnected
            break
        if msg["type"] == "websocket.receive":  # ASGI: client sent a message
            try:
                data = json.loads(msg.get("text", "{}"))  # Our app data is inside "text"
            except json.JSONDecodeError:
                await send({"type": "websocket.send",  # ASGI: send message to client
                           "text": json.dumps({"type": "ERROR", "message": "Invalid JSON"})})
                continue

            msg_type = data.get("type")

            # Handle ONBOARD_SUBMIT (stranger submitting invite code or payment)
            if msg_type == "ONBOARD_SUBMIT":
                await _handle_onboard_submit(data, send, route_handlers)
                continue

            # Handle ADMIN messages (promote, demote, block, unblock, get_level)
            if msg_type and msg_type.startswith("ADMIN_"):
                await _handle_admin_message(data, send, route_handlers)
                continue

            if msg_type == "INPUT":  # Our app type: client wants to run agent
                prompt, identity, sig_valid, err = route_handlers["auth"](
                    data, trust, blacklist=blacklist, whitelist=whitelist
                )

                # Check if stranger needs onboarding
                if err and "forbidden" in err.lower():
                    # Get onboard requirements from trust config
                    trust_agent = route_handlers["trust_agent"]
                    onboard_info = _get_onboard_requirements(trust_agent)
                    if onboard_info:
                        await send({"type": "websocket.send",
                                   "text": json.dumps({
                                       "type": "ONBOARD_REQUIRED",
                                       "identity": identity,
                                       **onboard_info
                                   })})
                        continue

                if err:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": err})})
                    continue
                if not prompt:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": "prompt required"})})
                    continue

                # Extract session for conversation continuation (same as HTTP)
                session = data.get("session")

                # Create IO for bidirectional communication
                io = WebSocketIO()
                agent_done = threading.Event()
                result_holder = [None]
                error_holder = [None]

                def run_agent():
                    try:
                        result_holder[0] = route_handlers["ws_input"](storage, prompt, io, session)
                    except Exception as e:
                        error_holder[0] = str(e)
                    agent_done.set()

                # Start agent in thread
                agent_thread = threading.Thread(target=run_agent, daemon=True)
                agent_thread.start()

                # Pump messages between WebSocket and IO
                # TODO: If client disconnects mid-request, result is still saved to SessionStorage.
                # Client could check GET /sessions/{session_id} on reconnect to fetch pending results.
                # For now, we just skip sending if client disconnected.
                client_disconnected = await _pump_messages(receive, send, io, agent_done)

                # Send error or final result (skip if client disconnected)
                if client_disconnected:
                    pass  # Client gone, result saved to storage, nothing to send
                elif error_holder[0]:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": error_holder[0]})})
                elif result_holder[0]:
                    result = result_holder[0]
                    await send({"type": "websocket.send",
                               "text": json.dumps({
                                   "type": "OUTPUT",
                                   "result": result["result"],
                                   "session_id": result["session_id"],
                                   "duration_ms": result["duration_ms"],
                                   "session": result["session"]
                               }, default=pydantic_json_encoder)})
                else:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": "Agent completed without result"})})


async def _pump_messages(ws_receive, ws_send, io: WebSocketIO, agent_done: threading.Event) -> bool:
    """Pump messages between WebSocket and IO queues with keep-alive.

    Runs until agent completes. Handles:
    - Outgoing: io._outgoing queue -> WebSocket (agent events)
    - Incoming: WebSocket -> io._incoming queue (approval responses, PONG)
    - Keep-alive: PING messages every 30s to detect dead connections

    Returns:
        True if client disconnected before agent completed, False otherwise.
        When True, caller should skip sending final OUTPUT (client is gone,
        but result is already saved to SessionStorage for polling recovery).

    Keep-alive mechanism:
        - send_ping() task sends PING every 30s
        - Client responds with PONG (handled in receive_incoming)
        - Keeps connection alive through proxies/firewalls
        - Client can detect dead connection if no PING for 60s

    Implementation note:
        Uses asyncio.Event for signaling disconnect between nested async functions.
        This is preferred over `nonlocal` boolean because:
        - No risk of forgetting `nonlocal` keyword (which would create local var)
        - Clearer intent: Event.set()/is_set() vs boolean reassignment
        - Thread-safe if needed in future
    """
    loop = asyncio.get_event_loop()

    # Signal for client disconnect - shared between send/receive tasks
    # Using Event instead of boolean avoids `nonlocal` complexity
    disconnected = asyncio.Event()

    async def send_outgoing():
        """Send outgoing messages from IO to WebSocket."""
        while not agent_done.is_set() and not disconnected.is_set():
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
        while not agent_done.is_set():
            try:
                msg = await asyncio.wait_for(ws_receive(), timeout=0.1)
                if msg["type"] == "websocket.receive":
                    try:
                        data = json.loads(msg.get("text", "{}"))
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
        while not agent_done.is_set() and not disconnected.is_set():
            await asyncio.sleep(30)  # Send ping every 30 seconds
            if not agent_done.is_set() and not disconnected.is_set():
                try:
                    await ws_send({"type": "websocket.send", "text": json.dumps({"type": "PING"})})
                except Exception:
                    # Connection likely closed, stop pinging
                    break

    send_task = asyncio.create_task(send_outgoing())
    recv_task = asyncio.create_task(receive_incoming())
    ping_task = asyncio.create_task(send_ping())

    while not agent_done.is_set():
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
