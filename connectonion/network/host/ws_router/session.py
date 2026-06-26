"""
Purpose: Run one client session — read loop, per-type dispatch, lifecycle of forward + ping tasks
LLM-Note:
  Dependencies: imports from [.connect (handle_connect), .agent_io (start_agent), .ping (ping_loop), ...trust.ws_admin (handle_admin_message, handle_onboard_submit), asyncio, uuid, rich.console] | imported by [.__init__ as the only public symbol]
  Data flow: recv_msg() → match data["type"] → dispatch | PONG → registry.update_ping | SESSION_STATUS → registry lookup + reply (inline) | CONNECT → handle_connect (auth + reattach) | INPUT → if running session: push_runtime_input + RUNTIME_INPUT_ACK (inline); else: start_agent | other types with active_io → active_io.send_to_agent | finally: cancel forward + ping tasks
  State/Effects: per-call local state — conn dict, active_io, forward_task, ping_task | mutates conn via handle_connect | spawns asyncio Tasks (forward + ping) cancelled in finally
  Integration: run_ws_session(send_msg, recv_msg, *, route_handlers, storage, registry, trust, blacklist=None, whitelist=None, enable_ping=True) | enable_ping=True on both direct and relay paths: the 30s client PING is forwarded through the relay to the client, since the relay's ANNOUNCE heartbeat only keeps the agent↔relay link alive and never reaches the client
  Performance: single-reader of recv_msg | O(1) per-message dispatch | bounded local state
  Errors: recv_msg returning None → exit loop normally | other exceptions propagate out (transport-level errors, programmer bugs)
"""
import asyncio
import uuid

from rich.console import Console
from ...trust.ws_admin import handle_admin_message, handle_onboard_submit
from .connect import handle_connect, establish_connection
from .agent_io import start_agent
from .ping import ping_loop

console = Console()


async def run_ws_session(send_msg, recv_msg, *, route_handlers, storage, registry, trust, blacklist=None, whitelist=None, enable_ping=True):
    """Run one client session from connect to disconnect.

    Reads frames, dispatches by type, cleans up on close. Used by both the
    direct ASGI WebSocket path and the relay-routed path, each providing its
    own send_msg/recv_msg adapters.
    """
    conn = {"authenticated": False, "identity": None, "session_id": None, "session": None}
    active_io = None
    forward_task = None
    ping_task = asyncio.create_task(ping_loop(send_msg)) if enable_ping else None

    try:
        while True:
            data = await recv_msg()
            if data is None:
                # recv_msg returns None on client close or relay-side timeout.
                break

            msg_type = data.get("type")
            if msg_type not in ("CONNECT", "INPUT", "SESSION_STATUS", "PONG"):
                console.print(f"[dim]← recv: {msg_type}[/dim]")

            if msg_type == "PONG":
                # Client heartbeat — refresh registry's last-active timestamp.
                if conn.get("session_id"):
                    registry.update_ping(conn["session_id"])

            elif msg_type == "SESSION_STATUS":
                # SESSION_STATUS query: lookup by sid, reply with current registry status.
                sid = (data.get("session") or {}).get("session_id")
                active = registry.get(sid) if sid else None
                status = active.status if active else "not_found"
                await send_msg({"type": "SESSION_STATUS", "session_id": sid, "status": status})

            elif msg_type == "ONBOARD_SUBMIT":
                identity = await handle_onboard_submit(data, send_msg, route_handlers)
                # Pop the stashed CONNECT only on a successful onboard: a failed one
                # (e.g. wrong invite code) keeps it so a retry on the same socket can
                # still complete the interrupted CONNECT.
                if identity:
                    # The onboard verified a fresh signature and promoted the identity, but
                    # the host blacklist is an absolute deny, not a trust LEVEL, and onboarding
                    # must not bypass it — a blacklisted client could otherwise pass the trust
                    # gate by submitting a valid invite/payment (handle_onboard_submit checks
                    # trust_agent.is_blocked, a different list from the host blacklist param).
                    # Re-apply it (the signature is already verified) before finishing CONNECT.
                    # whitelist is an allow-bypass (auth.py grants an instant allow on a match
                    # but never denies non-members), so it is correctly absent here: a non-
                    # whitelisted client that onboarded to "contact" should be admitted.
                    if blacklist and identity in blacklist:
                        await send_msg({"type": "ERROR", "message": "forbidden: blacklisted"})
                    else:
                        pending_connect = conn.pop("pending_connect", None)
                        if pending_connect:
                            # Finish the CONNECT the trust gate interrupted: the client
                            # is a contact now and resumes its input once CONNECTED lands.
                            result = await establish_connection(
                                pending_connect, identity, send_msg, conn, storage, registry
                            )
                            if result:
                                active_io, forward_task = result
            elif msg_type and msg_type.startswith("ADMIN_"):
                await handle_admin_message(data, send_msg, route_handlers)

            elif msg_type == "CONNECT":
                # First message: auth + session merge + maybe reattach to a running agent.
                result = await handle_connect(data, send_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist)
                if result:
                    active_io, forward_task = result

            elif msg_type == "INPUT":
                # If a running agent already owns this session, route INPUT as
                # mid-execution runtime input. Otherwise spawn a fresh agent.
                sid = conn.get("session_id")
                existing = registry.get(sid) if conn.get("authenticated") and sid else None
                if existing and existing.status == "running":
                    prompt = data.get("prompt")
                    if not prompt:
                        await send_msg({"type": "ERROR", "message": "prompt required"})
                    else:
                        rid = str(uuid.uuid4())
                        existing.io.push_runtime_input({"type": "RUNTIME_INPUT", "id": rid, "prompt": prompt})
                        console.print(f"[yellow]↳ RUNTIME_INPUT[/yellow] session={sid[:8]}... prompt={prompt[:50]}...")
                        await send_msg({"type": "RUNTIME_INPUT_ACK", "session_id": sid, "id": rid})
                else:
                    result = await start_agent(data, send_msg, conn, route_handlers, storage, registry)
                    if result:
                        active_io, forward_task = result

            elif active_io:
                # Anything else (ASK_USER_RESPONSE, APPROVAL_RESPONSE, mode_change, ...)
                # → forward to the running agent's input mailbox.
                active_io.send_to_agent(data)
    finally:
        # asyncio cancel idiom: cancel() only signals; await ensures the task
        # actually unwinds before we return. The CancelledError surfaced by
        # that await is the expected exit signal — not a bug, swallow it.
        for task in (forward_task, ping_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
