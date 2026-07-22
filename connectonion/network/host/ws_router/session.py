"""
Purpose: Run one client session — read loop, per-type dispatch, lifecycle of forward + ping tasks
LLM-Note:
  Dependencies: imports from [.connect (handle_connect), .agent_io (start_agent), .ping (ping_loop), ...trust.ws_admin (handle_admin_message, handle_onboard_submit), asyncio, uuid, rich.console] | imported by [.__init__ as the only public symbol]
  Data flow: recv_msg() → match data["type"] → dispatch | PONG → registry.update_ping | SESSION_STATUS → registry lookup + reply (inline) | CONNECT → handle_connect (auth + reattach) | INPUT → if running session: retryable ERROR before claim; else: start_agent | other types with active_io → active_io.send_to_agent | finally: cancel forward + ping tasks
  State/Effects: per-call local state — conn dict, active_io, forward_task, ping_task | mutates conn via handle_connect | spawns asyncio Tasks (forward + ping) cancelled in finally
  Integration: run_ws_session(send_msg, recv_msg, *, route_handlers, storage, registry, trust, blacklist=None, whitelist=None, enable_ping=True) | enable_ping=True on both direct and relay paths: the 30s client PING is forwarded through the relay to the client, since the relay's ANNOUNCE heartbeat only keeps the agent↔relay link alive and never reaches the client
  Performance: single-reader of recv_msg | O(1) per-message dispatch | bounded local state
  Errors: recv_msg returning None → exit loop normally | other exceptions propagate out (transport-level errors, programmer bugs)
"""
import asyncio
from rich.console import Console
from ...trust.ws_admin import handle_admin_message, handle_onboard_submit
from .connect import handle_connect, establish_connection
from .agent_io import start_agent
from ..auth import authenticate_bound_input
from .ping import ping_loop

console = Console()


async def run_ws_session(send_msg, recv_msg, *, route_handlers, storage, registry, trust, blacklist=None, whitelist=None, enable_ping=True):
    """Run one client session from connect to disconnect.

    Reads frames, dispatches by type, cleans up on close. Used by both the
    direct ASGI WebSocket path and the relay-routed path, each providing its
    own send_msg/recv_msg adapters.
    """
    conn = {
        "authenticated": False,
        "agent_address": None,
        "session_id": None,
        "session_id_authenticated": False,
        "session_authenticated": False,
        "session": None,
    }
    active_io = None
    forward_task = None
    ping_task = asyncio.create_task(ping_loop(send_msg)) if enable_ping else None
    connect_seen = False

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
                if conn.get("authenticated") and conn.get("session_id"):
                    registry.update_ping(conn["session_id"], conn.get("agent_address"))

            elif msg_type == "SESSION_STATUS":
                # Status is owner-scoped.  Before CONNECT there is no verified
                # identity and no active-session information is disclosed.
                if not conn.get("authenticated"):
                    await send_msg({
                        "type": "ERROR",
                        "message": "authenticate first (send CONNECT)",
                    })
                    continue
                sid = data.get("session_id") or (data.get("session") or {}).get("session_id")
                active = (
                    registry.get_for_owner(sid, conn["agent_address"])
                    if sid
                    else None
                )
                status = active.status if active else "not_found"
                await send_msg({"type": "SESSION_STATUS", "session_id": sid, "status": status})

            elif msg_type == "ONBOARD_SUBMIT":
                pending_connect = conn.get("pending_connect")
                if (
                    pending_connect
                    and pending_connect.get("from") != data.get("from")
                ):
                    # Comparing the claimed identities here can only reject;
                    # the successful path still verifies ONBOARD_SUBMIT below
                    # and compares the authenticated signer again before use.
                    await send_msg({
                        "type": "ERROR",
                        "message": "unauthorized: onboarding identity mismatch",
                    })
                    continue
                agent_address = await handle_onboard_submit(data, send_msg, route_handlers)
                # Pop the stashed CONNECT only on a successful onboard: a failed one
                # (e.g. wrong invite code) keeps it so a retry on the same socket can
                # still complete the interrupted CONNECT.
                if agent_address:
                    # The onboard verified a fresh signature and promoted the caller, but
                    # the host blacklist is an absolute deny, not a trust LEVEL, and onboarding
                    # must not bypass it — a blacklisted client could otherwise pass the trust
                    # gate by submitting a valid invite/payment (handle_onboard_submit checks
                    # trust_agent.is_blocked, a different list from the host blacklist param).
                    # Re-apply it (the signature is already verified) before finishing CONNECT.
                    # whitelist is an allow-bypass (auth.py grants an instant allow on a match
                    # but never denies non-members), so it is correctly absent here: a non-
                    # whitelisted client that onboarded to "contact" should be admitted.
                    if blacklist and agent_address in blacklist:
                        await send_msg({"type": "ERROR", "message": "forbidden: blacklisted"})
                    else:
                        pending_connect = conn.pop("pending_connect", None)
                        if pending_connect:
                            if pending_connect.get("from") != agent_address:
                                await send_msg({
                                    "type": "ERROR",
                                    "message": "unauthorized: onboarding identity mismatch",
                                })
                                continue
                            # Finish the CONNECT the trust gate interrupted: the client
                            # is a contact now and resumes its input once CONNECTED lands.
                            result = await establish_connection(
                                pending_connect, agent_address, send_msg, conn, storage, registry
                            )
                            if result:
                                active_io, forward_task = result
            elif msg_type and msg_type.startswith("ADMIN_"):
                await handle_admin_message(data, send_msg, route_handlers)

            elif msg_type == "CONNECT":
                # First message: auth + session merge + maybe reattach to a running agent.
                if connect_seen:
                    await send_msg({
                        "type": "ERROR",
                        "message": "CONNECT already established for this socket",
                    })
                    continue
                connect_seen = True
                result = await handle_connect(data, send_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist)
                if result:
                    active_io, forward_task = result

            elif msg_type == "INPUT":
                if not conn.get("authenticated") or not conn.get("session_id"):
                    await send_msg({
                        "type": "ERROR",
                        "message": "authenticate first (send CONNECT)",
                    })
                    continue
                payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
                binding, binding_error = authenticate_bound_input(
                    data,
                    recipient_address=route_handlers.get("recipient_address"),
                    expected_session_id=conn["session_id"],
                )
                if binding_error:
                    await send_msg({"type": "ERROR", "message": binding_error})
                    continue
                if binding is not None and (
                    binding["agent_address"] != conn.get("agent_address")
                ):
                    await send_msg({
                        "type": "ERROR",
                        "message": "unauthorized: identity mismatch",
                    })
                    continue

                requested_modes = [
                    source.get("mode")
                    for source in (data, payload)
                    if "mode" in source
                ]
                if any(not isinstance(mode, str) for mode in requested_modes):
                    await send_msg({"type": "ERROR", "message": "mode must be a string"})
                    continue
                if len(set(requested_modes)) > 1:
                    await send_msg({
                        "type": "ERROR",
                        "message": "unauthorized: mode mismatch",
                    })
                    continue
                if binding is None and requested_modes and requested_modes[0] != "safe":
                    await send_msg({
                        "type": "ERROR",
                        "message": "fully signed INPUT required for non-safe mode",
                    })
                    continue
                if (
                    binding is not None
                    and binding["mode"] in {"ulw", "accept_edits"}
                    and not conn.get("session_authenticated")
                ):
                    await send_msg({
                        "type": "ERROR",
                        "message": "signed session snapshot required for privileged mode",
                    })
                    continue

                # A running agent already owns this session generation. Reject
                # INPUT without claiming it; otherwise spawn a fresh agent.
                sid = conn.get("session_id")
                existing = (
                    registry.get_for_owner(sid, conn["agent_address"])
                    if (conn.get("authenticated") and sid)
                    else None
                )
                if existing and existing.status == "running":
                    if binding is None:
                        await send_msg({
                            "type": "ERROR",
                            "message": "fully signed INPUT required while session is running",
                        })
                        continue
                    # A running Agent may be blocked in generic io.receive()
                    # (approval, ask_user, or an ULW checkpoint). Splitting a
                    # signed INPUT across that mailbox and the runtime-input
                    # queue can make the mode frame impersonate an interaction
                    # response and then lose the prompt when the turn ends.
                    # Reject before replay claim/ACK so the exact signed request
                    # remains retryable after the current turn completes.
                    await send_msg({
                        "type": "ERROR",
                        "message": "session is running; retry INPUT after current turn",
                        "retryable": True,
                        "session_id": sid,
                        "request_id": binding["request_id"],
                    })
                    continue
                else:
                    result = await start_agent(
                        data,
                        send_msg,
                        conn,
                        route_handlers,
                        storage,
                        registry,
                        input_binding=binding,
                        request_claimed=False,
                    )
                    if result:
                        active_io, forward_task = result

            elif active_io:
                # Anything else (ASK_USER_RESPONSE, APPROVAL_RESPONSE, mode_change, ...)
                # → forward to the running agent's input mailbox.
                raw_mode_control = (
                    msg_type == "mode_change"
                    or data.get("action") == "switch_mode"
                )
                raw_mode = data.get("mode")
                if raw_mode_control and not isinstance(raw_mode, str):
                    await send_msg({
                        "type": "ERROR",
                        "message": "mode must be a string",
                    })
                    continue
                modern_persistent_control = (
                    (
                        msg_type == "mode_change"
                        and raw_mode in ("ulw", "accept_edits")
                    )
                    or msg_type == "prompt_update"
                    or data.get("action") == "continue"
                    or (
                        data.get("action") == "switch_mode"
                        and raw_mode not in ("safe", "plan")
                    )
                )
                if (
                    conn.get("session_authenticated")
                    and modern_persistent_control
                ):
                    # Modern sessions persist capability state across turns, so
                    # raw mailbox frames may only downgrade/stop or satisfy the
                    # existing interactive approval/ask-user protocol. A signed
                    # INPUT is the current authenticated path for capability or
                    # persistent-intent changes. Legacy sessions keep their live
                    # controls, but their unbound state is never restored later.
                    await send_msg({
                        "type": "ERROR",
                        "message": "signed INPUT or authenticated control protocol required",
                    })
                    continue
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
