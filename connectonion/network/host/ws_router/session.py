"""
Purpose: Run one client session — read loop, per-type dispatch, lifecycle of forward + ping tasks
LLM-Note:
  Dependencies: imports from [.connect, .agent_io, .exec, .mode, .ping, ...trust.ws_admin, asyncio, uuid, rich.console] | imported by [.__init__ as the only public symbol]
  Data flow: recv → verify every v2 application command → first CONNECT auth or equivalent authenticated relay reattach → dispatch INPUT/EXEC/mode_change/INTERRUPT/admin/runtime frames → bounded response → cancel spawned tasks on close
  State/Effects: per-call local state — conn dict, active_io, forward_task, ping_task | mutates conn via handle_connect | spawns asyncio Tasks (forward + ping) cancelled in finally
  Integration: OIP mode_change uses .mode durable authority; interrupt requires registered active IO; signed-command clients execute only verified payload copies
  Performance: single-reader of recv_msg | O(1) per-message dispatch | bounded local state
  Errors: recv_msg returning None → exit loop normally | other exceptions propagate out (transport-level errors, programmer bugs)
"""
import asyncio
import uuid

from rich.console import Console

from ...trust.ws_admin import handle_admin_message, handle_onboard_submit
from .agent_io import start_agent
from .connect import establish_connection, handle_authenticated_reconnect, handle_connect
from .exec import run_exec
from .mode import handle_mode_change
from .ping import ping_loop

console = Console()


async def _send_provider_interrupt_ack(
    send_msg,
    *,
    request_id: str,
    invocation_id: str | None,
    accepted: bool,
    reason: str | None = None,
):
    """Reply to one modern scoped Stop without exposing provider internals."""
    frame = {
        "type": "PROVIDER_INTERRUPT_ACK",
        "requestId": request_id,
        "invocationId": invocation_id,
        "accepted": accepted,
    }
    if reason:
        frame["reason"] = reason
    await send_msg(frame)


async def run_ws_session(send_msg, recv_msg, *, route_handlers, storage, registry, trust, blacklist=None, whitelist=None, enable_ping=True, transport="unknown"):
    """Run one client session from connect to disconnect.

    Reads frames, dispatches by type, cleans up on close. Used by both the
    direct ASGI WebSocket path and the relay-routed path, each providing its
    own send_msg/recv_msg adapters.
    """
    conn = {"authenticated": False, "agent_address": None, "session_id": None,
            "session": None, "signed_commands": False, "recipient_address": None,
            "transport": transport}
    active_io = None
    forward_task = None
    exec_tasks = set()
    ping_task = asyncio.create_task(ping_loop(send_msg)) if enable_ping else None

    try:
        while True:
            data = await recv_msg()
            if data is None:
                # recv_msg returns None on client close or relay-side timeout.
                break

            msg_type = data.get("type")

            # CONNECT establishes the identity and protocol capabilities for
            # this socket. Letting a second CONNECT overwrite that state makes
            # it possible to downgrade an authenticated v2 connection to v1
            # and then inject unsigned commands. Reauthentication belongs on a
            # fresh transport, with fresh per-connection state.
            if msg_type == "CONNECT" and conn.get("authenticated"):
                await handle_authenticated_reconnect(
                    data, send_msg, conn, route_handlers, storage, registry,
                    trust, blacklist, whitelist,
                )
                continue

            # A v2 CONNECT signs the capability that enables this gate. Keep the
            # few transport/authentication frames outside it; every application
            # command, including approval and ask-user responses forwarded below,
            # must be signed and is replaced with the verified payload before use.
            exempt = {"CONNECT", "PONG", "SESSION_STATUS", "ONBOARD_SUBMIT"}
            if (conn.get("authenticated") and conn.get("signed_commands")
                    and msg_type not in exempt):
                from ..auth import authenticated_command_payload

                signed_frame = data
                verified, command_error = authenticated_command_payload(
                    data, conn["agent_address"], conn.get("recipient_address"),
                    route_handlers.get("replay"),
                )
                if command_error:
                    await send_msg({"type": "ERROR", "message": command_error})
                    continue
                # ADMIN handlers independently authenticate their frame. Preserve
                # that envelope while replacing every actionable top-level field
                # with its verified copy. Other handlers only need the payload.
                if (msg_type or "").startswith("ADMIN_"):
                    data = {
                        **verified,
                        "payload": verified,
                        "from": signed_frame.get("from"),
                        "signature": signed_frame.get("signature"),
                    }
                else:
                    data = verified
                msg_type = data.get("type")
            if msg_type not in ("CONNECT", "INPUT", "SESSION_STATUS", "PONG"):
                console.print(f"[dim]← recv: {msg_type}[/dim]")

            if msg_type == "PONG":
                # Client heartbeat — refresh registry's last-active timestamp.
                if conn.get("session_id"):
                    registry.update_ping(conn["session_id"])

            elif msg_type == "SESSION_STATUS":
                # A live connection already has a verified identity. A temporary
                # status-only socket must independently sign the query as a v2
                # command. In either case, a caller only sees its own active
                # session; every other case has the same not_found answer so the
                # endpoint is not an existence oracle (#766).
                requester = conn.get("agent_address") if conn.get("authenticated") else None
                sid = (data.get("session") or {}).get("session_id")
                if requester is None:
                    from ..auth import authenticated_command_payload

                    metadata = route_handlers.get("agent_metadata") or {}
                    verified, status_error = authenticated_command_payload(
                        data, data.get("from"), metadata.get("address"),
                        route_handlers.get("replay"),
                    )
                    if (status_error or "").startswith("misconfigured:"):
                        await send_msg({"type": "ERROR", "message": status_error})
                        continue
                    if status_error is None:
                        requester = data.get("from")
                        sid = verified.get("session_id")

                active = registry.get(sid) if requester and sid else None
                owner = getattr(active, "owner", None) if active else None
                status = active.status if active and owner == requester else "not_found"
                await send_msg({"type": "SESSION_STATUS", "session_id": sid, "status": status})

            elif msg_type == "ONBOARD_SUBMIT":
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
                            # Finish the CONNECT the trust gate interrupted: the client
                            # is a contact now and resumes its input once CONNECTED lands.
                            result = await establish_connection(
                                pending_connect, agent_address, send_msg, conn, storage, registry,
                                route_handlers
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
                        accepted = existing.io.push_runtime_input({
                            "type": "RUNTIME_INPUT", "id": rid, "prompt": prompt,
                        })
                        if accepted is not False:
                            console.print(f"[yellow]↳ RUNTIME_INPUT[/yellow] session={sid[:8]}... prompt={prompt[:50]}...")
                            await send_msg({"type": "RUNTIME_INPUT_ACK", "session_id": sid, "id": rid})
                        else:
                            await send_msg({
                                "type": "ERROR",
                                "code": "RUNTIME_INPUT_REJECTED",
                                "message": "running turn is not accepting runtime input; retry after OUTPUT",
                                "session_id": sid,
                                "retryable": True,
                            })
                else:
                    result = await start_agent(data, send_msg, conn, route_handlers, storage, registry)
                    if result:
                        active_io, forward_task = result

            elif msg_type == "EXEC":
                # Direct tool execution — no LLM, no session. Auth is the same
                # gate as INPUT; each EXEC runs as its own task so a slow tool
                # (long shell command) never blocks this read loop or other EXECs.
                if not conn["authenticated"]:
                    await send_msg({"type": "ERROR", "message": "authenticate first (send CONNECT)"})
                else:
                    # conn has held the caller's address since CONNECT. Nothing
                    # asked it, so any authenticated connection could run any
                    # whitelisted tool (#653).
                    task = asyncio.create_task(
                        run_exec(data, send_msg, route_handlers, conn["agent_address"]))
                    exec_tasks.add(task)
                    task.add_done_callback(exec_tasks.discard)

            elif msg_type == "mode_change":
                await handle_mode_change(
                    data, send_msg, conn, route_handlers, storage, registry
                )

            elif msg_type == "INTERRUPT":
                sid = conn.get("session_id")
                registered = registry.get(sid) if sid else None
                if (
                    not active_io
                    or not registered
                    or registered.status != "running"
                    or registered.io is not active_io
                ):
                    await send_msg({
                        "type": "ERROR",
                        "message": "interrupt requires an active turn",
                    })
                    continue
                request_interrupt = getattr(active_io, "request_interrupt", None)
                if request_interrupt is None:
                    active_io.send_to_agent(data)
                else:
                    request_interrupt()

            elif msg_type == "PROVIDER_INTERRUPT":
                invocation_id = data.get("invocationId")
                request_id = data.get("requestId")
                # Older browser clients used the unacknowledged frame. Keep
                # their existing behavior during a rolling upgrade, but require
                # a bounded correlation id before claiming an acknowledgement.
                legacy_request = request_id is None
                if not legacy_request and (
                    not isinstance(request_id, str)
                    or not request_id
                    or len(request_id) > 128
                ):
                    await _send_provider_interrupt_ack(
                        send_msg,
                        request_id="",
                        invocation_id=invocation_id if isinstance(invocation_id, str) else None,
                        accepted=False,
                        reason="invalid_request",
                    )
                    continue
                sid = conn.get("session_id")
                registered = registry.get(sid) if sid else None
                if (
                    not isinstance(invocation_id, str)
                    or not invocation_id
                    or len(invocation_id) > 512
                    or not active_io
                    or not registered
                    or registered.status != "running"
                    or registered.io is not active_io
                ):
                    if legacy_request:
                        await send_msg({
                            "type": "ERROR",
                            "message": "provider stop requires the exact active provider run",
                        })
                    else:
                        await _send_provider_interrupt_ack(
                            send_msg,
                            request_id=request_id,
                            invocation_id=invocation_id if isinstance(invocation_id, str) else None,
                            accepted=False,
                            reason="not_active",
                        )
                    continue
                request_provider_interrupt = getattr(
                    active_io, "request_provider_interrupt", None,
                )
                accepted = bool(
                    request_provider_interrupt(invocation_id)
                    if callable(request_provider_interrupt)
                    else False
                )
                if legacy_request:
                    if not accepted:
                        await send_msg({
                            "type": "ERROR",
                            "message": "provider stop requires the exact active provider run",
                        })
                    continue
                await _send_provider_interrupt_ack(
                    send_msg,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    accepted=accepted,
                    reason=None if accepted else "not_active",
                )

            elif msg_type == "APPROVAL_RESPONSE" and active_io:
                resolver = getattr(active_io, "resolve_legacy_permission", None)
                if resolver is None:
                    active_io.send_to_agent(data)
                elif not resolver(data):
                    await send_msg({
                        "type": "ERROR",
                        "message": "unknown or stale approval response",
                    })

            elif active_io:
                # Anything else (ASK_USER_RESPONSE, APPROVAL_RESPONSE, mode_change, ...)
                # → forward to the running agent's input mailbox.
                active_io.send_to_agent(data)

            else:
                # No handler and no agent to forward to. This used to fall off
                # the end of the chain: no reply, no log, nothing — and a client
                # waiting for an answer waited until its own timeout, then
                # reported something unrelated to the cause. Silence is the
                # answer #434 was about, and every other branch here sends an
                # ERROR frame.
                #
                # It matters most for a long-term release: an agent from this
                # version will meet clients of many versions, and the first
                # symptom of version skew should be "I do not know that
                # message", not a connection that looks fine and never answers.
                await send_msg({
                    "type": "ERROR",
                    "message": f"unknown message type: {msg_type!r}",
                })
    finally:
        # asyncio cancel idiom: cancel() only signals; await ensures the task
        # actually unwinds before we return. The CancelledError surfaced by
        # that await is the expected exit signal — not a bug, swallow it.
        for task in (forward_task, ping_task, *exec_tasks):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
