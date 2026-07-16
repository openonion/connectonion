"""
Purpose: Agent thread orchestration + io → client streaming — the bridge between the sync agent and the async transport
LLM-Note:
  Dependencies: imports from [...io (WebSocketIO), ..session (session_to_chat_items via lazy import), asyncio, threading, rich.console] | imported by [.session (start_agent), .connect (resume_forwarding)]
  Data flow: start_agent: validate INPUT → create WebSocketIO → register in registry BEFORE thread.start (race-safe) → spawn _agent_thread_body (thread target running route_handlers["ws_input"]) → spawn forward_task = forward_agent_msgs_to_client → return (io, task) | resume_forwarding: same forward_task spawn but on existing active.io | forward_agent_msgs_to_client: read_msgs_from_agent → send_msg loop → on agent finish read result_holder → emit OUTPUT (success) / ERROR (exception)
  State/Effects: spawns daemon Thread + asyncio.Task | mutates registry (register / mark_session_running) | calls io.mark_agent_done() in finally
  Integration: start_agent(data, send_msg, conn, route_handlers, storage, registry) → (io, forward_task) | None | resume_forwarding(send_msg, active, registry, session_id, storage) → (io, forward_task) | forward_agent_msgs_to_client(send_msg, io, session_id, *, result_holder, conn, storage) — async, runs until io marked done
  Performance: thread-per-INPUT (worker isolation) | one forward_task per WS connection
  Errors: agent thread exceptions captured in result_holder[0]; surfaced as ERROR frame by the forwarder (threads don't propagate exceptions natively)
"""
import asyncio
import inspect
import threading
from copy import deepcopy

from rich.console import Console
from ...io import WebSocketIO
from ..auth import authenticate_bound_input

console = Console()


def _supported_kwargs(handler, values):
    """Pass new trusted context to legacy-compatible handler signatures."""
    try:
        parameters = inspect.signature(handler).parameters
    except (TypeError, ValueError):
        return values
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return values
    return {name: value for name, value in values.items() if name in parameters}


def _agent_thread_body(
    route_handlers,
    storage,
    prompt,
    io,
    session,
    images,
    files,
    registry,
    session_id,
    owner_address,
    mode,
    session_id_authenticated,
    result_holder,
):
    """Thread target: run agent and store result. Calls io.mark_agent_done() when done."""
    try:
        handler = route_handlers["ws_input"]
        trusted_context = _supported_kwargs(handler, {
            "agent_address": owner_address,
            "mode": mode,
            "session_id_authenticated": session_id_authenticated,
        })
        result_holder[0] = handler(
            storage, prompt, io, session, images, files, **trusted_context
        )
    except Exception as e:
        result_holder[0] = e
    finally:
        # An exception is still a completed turn.  Leaving the registry in
        # `running` forever prevents the owner from starting a recovery turn.
        registry.mark_session_connected(
            session_id,
            owner_address,
            expected_thread=threading.current_thread(),
        )
        io.mark_agent_done()


async def forward_agent_msgs_to_client(
    send_msg,
    io,
    session_id,
    *,
    result_holder=None,
    conn=None,
    storage=None,
    owner_address=None,
):
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
        stored = await asyncio.to_thread(storage.get, session_id)
        owner_matches = bool(
            stored
            and owner_address is not None
            and stored.owner_address == owner_address
        )
        if owner_matches and stored.status == "done":
            await send_msg({
                "type": "OUTPUT",
                "result": stored.result,
                "session_id": session_id,
                "duration_ms": stored.duration_ms,
                "session": stored.session,
                "chat_items": session_to_chat_items(stored.session or {}),
            })
        elif owner_matches and stored.status == "error":
            await send_msg({
                "type": "ERROR",
                "message": stored.result or "Agent failed",
                "session_id": session_id,
            })
        else:
            # Missing/expired, foreign-owner, and non-terminal records share
            # one response so reconnects terminate without leaking state.
            await send_msg({
                "type": "ERROR",
                "message": "Session result unavailable",
                "session_id": session_id,
            })
    else:
        await send_msg({"type": "ERROR", "message": "Agent completed without result"})


def resume_forwarding(send_msg, active, registry, session_id, storage, owner_address):
    """Restart the forward task on an existing running session's io. Returns (io, forward_task).

    Called when a client reconnects to a session whose agent thread is still
    alive. The io stayed live in ActiveSession across the WS drop; we just
    spawn a fresh task to pump it to the new client.
    """
    console.print(f"  [dim]↻ resuming forwarding to running agent[/dim]")
    io = active.io
    registry.update_ping(session_id, owner_address)
    task = asyncio.create_task(
        forward_agent_msgs_to_client(
            send_msg,
            io,
            session_id,
            storage=storage,
            owner_address=owner_address,
        )
    )
    return io, task


async def start_agent(
    data,
    send_msg,
    conn,
    route_handlers,
    storage,
    registry,
    *,
    input_binding=None,
    request_claimed=False,
):
    """Validate INPUT, spawn agent thread + forward task. Returns (io, forward_task) or None on error."""
    if not conn["authenticated"]:
        console.print(f"[red]✗ INPUT rejected:[/red] not authenticated (send CONNECT first)")
        await send_msg({"type": "ERROR", "message": "authenticate first (send CONNECT)"})
        return None

    session_id = conn["session_id"]
    if input_binding is None:
        input_binding, binding_error = authenticate_bound_input(
            data,
            recipient_address=route_handlers.get("recipient_address"),
            expected_session_id=session_id,
        )
        if binding_error:
            await send_msg({"type": "ERROR", "message": binding_error})
            return None
    if input_binding is not None:
        if input_binding["agent_address"] != conn.get("agent_address"):
            await send_msg({"type": "ERROR", "message": "unauthorized: identity mismatch"})
            return None

    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    requested_modes = [
        source.get("mode")
        for source in (data, payload)
        if "mode" in source
    ]
    if any(not isinstance(mode, str) for mode in requested_modes):
        await send_msg({"type": "ERROR", "message": "mode must be a string"})
        return None
    if len(set(requested_modes)) > 1:
        await send_msg({"type": "ERROR", "message": "unauthorized: mode mismatch"})
        return None
    if input_binding is None and requested_modes and requested_modes[0] != "safe":
        await send_msg({
            "type": "ERROR",
            "message": "fully signed INPUT required for non-safe mode",
        })
        return None

    mode = input_binding["mode"] if input_binding is not None else "safe"
    capabilities_authenticated = bool(
        input_binding is not None and conn.get("session_authenticated")
    )
    if (
        mode in {"ulw", "accept_edits"}
        and not conn.get("session_authenticated")
    ):
        await send_msg({
            "type": "ERROR",
            "message": "signed session snapshot required for privileged mode",
        })
        return None

    prompt = input_binding["prompt"] if input_binding is not None else data.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        await send_msg({
            "type": "ERROR",
            "message": "prompt must be a non-empty string",
        })
        return None

    existing = registry.get(session_id)
    agent_address = conn["agent_address"]
    if existing and existing.owner_address != agent_address:
        await send_msg({
            "type": "ERROR",
            "message": "forbidden: session owner mismatch",
            "session_id": session_id,
        })
        return None
    if existing and existing.status == "running" and input_binding is None:
        await send_msg({
            "type": "ERROR",
            "message": "fully signed INPUT required while session is running",
            "session_id": session_id,
        })
        return None
    # Defense in depth: dispatch already rejects INPUT during a running turn.
    # If any future caller bypasses that, refuse to spawn a second agent.
    if existing and existing.status == "running":
        await send_msg({"type": "ERROR", "message": "session already has a running agent", "session_id": session_id})
        return None

    # CONNECT is the only frame allowed to supply a conversation snapshot.
    # In particular, an empty CONNECT transcript is authoritative: using `or`
    # here would let an INPUT inject messages/mode through its top-level
    # `session` field whenever conn["session"] is an empty dict.
    session = deepcopy(conn["session"])
    if existing and existing.status == "connected":
        stored = await asyncio.to_thread(storage.get, session_id)
        if stored and stored.owner_address != agent_address:
            await send_msg({
                "type": "ERROR",
                "message": "forbidden: session owner mismatch",
                "session_id": session_id,
            })
            return None
        if stored and stored.session is not None:
            session = deepcopy(stored.session)
            session.pop("owner_address", None)
            session.pop("server_state", None)
            session.pop("_trusted_server_state", None)
    if not isinstance(session, dict):
        await send_msg({"type": "ERROR", "message": "invalid connected session"})
        return None
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
        args=(
            route_handlers,
            storage,
            prompt,
            io,
            session,
            images,
            files,
            registry,
            session_id,
            agent_address,
            mode,
            capabilities_authenticated,
            result_holder,
        ),
        daemon=True,
    )
    # Reserve the execution generation before claiming replay state. The CAS
    # rejects concurrent sockets and cleanup races, so a losing valid request
    # remains retryable with its original request ID.
    try:
        if existing:
            registry.mark_session_running(session_id, io, agent_thread, agent_address)
        else:
            registry.register(session_id, io, agent_thread, agent_address)
    except (PermissionError, RuntimeError) as exc:
        await send_msg({"type": "ERROR", "message": str(exc), "session_id": session_id})
        return None

    # claim_request is an in-memory lock-protected operation. Keep it
    # synchronous here so no other coroutine can observe this reserved but
    # unstarted generation between CAS and replay claim.
    if input_binding is not None and not request_claimed:
        try:
            claimed = storage.claim_request(
                conn["agent_address"],
                session_id,
                input_binding["request_id"],
                input_binding["timestamp"],
            )
        except ValueError as exc:
            registry.mark_session_connected(
                session_id,
                agent_address,
                expected_thread=agent_thread,
            )
            await send_msg({"type": "ERROR", "message": str(exc)})
            return None
        if not claimed:
            registry.mark_session_connected(
                session_id,
                agent_address,
                expected_thread=agent_thread,
            )
            await send_msg({"type": "ERROR", "message": "duplicate request"})
            return None

    console.print(f"[green]✓ INPUT[/green] agent_address={agent_address[:16] if agent_address else '?'}... session={session_id[:8] if session_id else '?'}... prompt={prompt[:50]}...")
    agent_thread.start()

    task = asyncio.create_task(
        forward_agent_msgs_to_client(
            send_msg,
            io,
            session_id,
            result_holder=result_holder,
            conn=conn,
            owner_address=agent_address,
        )
    )
    return io, task
