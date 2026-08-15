"""
Purpose: Authenticate CONNECT, bind session ownership, initialize durable Host mode policy, advertise capabilities, and optionally reattach running work
LLM-Note:
  Dependencies: imports from [..session (merge_sessions, session_to_chat_items via lazy local import), ...trust.ws_admin (get_onboard_requirements), .agent_io (resume_forwarding), uuid, rich.console] | imported by [.session as part of CONNECT dispatch]
  Data flow: verify identity/trust → bind/replace session ID by owner → merge conversation → ensure durable Safe/current policy → derive identity-bounded SessionModeState → CONNECTED → optional running-agent rewind/resume
  State/Effects: mutates authenticated connection state; may append initial/normalized durable session; refreshes registry ping when reattaching
  Integration: handle_connect(data, send_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist) → returns (io, forward_task) for reattach or None
  Performance: one ownership read plus one atomic mode-state initialization and registry checks per CONNECT
  Errors: auth/policy/storage initialization failures surface as bounded ERROR frames; private storage exceptions are not sent
"""
import asyncio
import logging
import uuid

from rich.console import Console

from ...trust.ws_admin import get_onboard_requirements
from .agent_io import resume_forwarding

console = Console()
logger = logging.getLogger(__name__)


async def handle_connect(data, send_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist):
    """Handle CONNECT message: auth, session merge, send CONNECTED. Returns (io, task) for reattach or None."""
    from ..auth import authenticate_connect, signature_already_used

    metadata = route_handlers.get("agent_metadata") or {}
    auth_kwargs = {"blacklist": blacklist, "whitelist": whitelist}
    if metadata.get("address"):
        auth_kwargs["recipient_address"] = metadata["address"]
    connect_auth = route_handlers.get("connect_auth")
    if connect_auth is None:
        _, agent_address, sig_valid, err = authenticate_connect(
            data, trust,
            replay_check=route_handlers.get("replay", signature_already_used),
            **auth_kwargs,
        )
    else:
        _, agent_address, sig_valid, err = connect_auth(
            data, trust, **auth_kwargs
        )

    if err and "forbidden" in err.lower():
        trust_agent = route_handlers["trust_agent"]
        onboard_info = get_onboard_requirements(trust_agent)
        if onboard_info:
            # Stash the raw CONNECT frame on the connection state. WHY it exists:
            # the trust gate interrupts CONNECT right here — auth returned
            # "forbidden, must onboard" BEFORE conn was authenticated — so the
            # session_id / session payload the client sent would otherwise be lost.
            # We can't just ask for a second CONNECT either: its signature could age
            # past the 5-minute window while a human types an invite code or pays.
            #
            # Data flow: stashed here at ONBOARD_REQUIRED → popped in session.py on a
            # successful ONBOARD_SUBMIT → replayed through establish_connection() with
            # the onboard-verified agent_address → CONNECTED → the client's queued
            # INPUT resumes. Cleared on pop; a failed onboard leaves it for a retry.
            conn["pending_connect"] = data
            await send_msg({"type": "ONBOARD_REQUIRED", "identity": agent_address, **onboard_info})
            return

    if err:
        console.print(f"[red]✗ CONNECT auth error:[/red] {err}")
        await send_msg({"type": "ERROR", "message": err})
        return

    return await establish_connection(
        data, agent_address, send_msg, conn, storage, registry, route_handlers
    )


async def establish_connection(data, agent_address, send_msg, conn, storage, registry,
                               route_handlers=None):
    """Post-auth half of CONNECT: populate conn, merge sessions, send CONNECTED.

    Called by handle_connect and, after a successful onboard, with the stashed
    pending CONNECT — the agent_address is then the one verified on ONBOARD_SUBMIT.

    ``route_handlers`` is optional so a caller that only needs the session half can
    omit it; without it no AGENT_PROFILE is sent.
    """
    # A second CONNECT on the same socket must not inherit the first identity
    # while durable policy initialization is in flight or after it fails.
    conn["authenticated"] = False
    for key in (
        "agent_address", "signed_commands", "recipient_address", "session_id",
        "session", "mode_is_admin",
    ):
        conn.pop(key, None)

    signed_commands = (
        data.get("payload", {}).get("signed_commands") == 1
    )
    recipient_address = data.get("payload", {}).get("to")
    session_id = data.get("session_id") or str(uuid.uuid4())
    client_session = data.get("session")
    server_newer = False

    if client_session:
        msg_count = len(client_session.get("messages", []))
        console.print(f"  [dim]↑ client session: {msg_count} messages[/dim]")

    if session_id:
        from ..session import merge_sessions, session_owner
        stored = storage.get(session_id)
        active_for_id = registry.get(session_id)
        # A session belongs to whoever started it. The id arrives on the
        # client's frame and used to be the whole credential, so a second
        # identity that named it was handed the first one's conversation --
        # and `GET /sessions` gives the ids out wholesale (#683, #696).
        #
        # They get a *different* id, not an empty session under this one.
        # Reusing it was the first version of this fix, and it meant the
        # squatter's turn saved a record under the owner's id -- storage is
        # append-only, last entry wins -- so the owner came back to an empty
        # conversation. Measured: "A LOST their conversation". That trades a
        # disclosure for a destruction, which is not a trade.
        #
        # A new id is also the honest answer: it is what CONNECTED reports, so
        # the client knows which session it is actually in.
        owner = session_owner(stored) or (active_for_id and active_for_id.owner)
        if owner and owner != agent_address:
            console.print(f"  [dim]↩ session {session_id[:8]}… belongs to another "
                          f"caller — starting a new one[/dim]")
            stored = None
            session_id = str(uuid.uuid4())
        if stored and stored.session:
            client = client_session or {}
            client_session, server_newer = merge_sessions(
                client_session=client, server_session=stored.session
            )
            if server_newer:
                console.print("  [dim]↕ merged sessions (server newer)[/dim]")

    # The live half, and the worse one: resume_forwarding rewinds and streams
    # the output of a turn already in progress. A caller who does not own it was
    # given a fresh id above, so this lookup finds nothing for them.
    active = registry.get(session_id)
    if active and active.status == 'running':
        status = "running"
    elif active and active.status == 'connected':
        status = "connected"
        registry.update_ping(session_id)
    else:
        status = "new"

    mode_state = None
    mode_policy = (
        route_handlers.get("session_modes") if route_handlers is not None else None
    )
    mode_is_admin = None
    if mode_policy is not None:
        from ..session.mode import (
            ModeTransactionError,
            ensure_host_mode_session,
            session_with_durable_policy,
        )

        trust_agent = route_handlers["trust_agent"]
        is_admin = trust_agent.is_admin(agent_address)
        level = "admin" if is_admin else trust_agent.get_level(agent_address)
        try:
            mode_record = await asyncio.to_thread(
                ensure_host_mode_session,
                storage,
                session_id,
                requester={"address": agent_address, "level": level},
                result_ttl=route_handlers["result_ttl"],
                policy=mode_policy,
                is_admin=is_admin,
            )
            client_session = session_with_durable_policy(
                client_session, mode_record.session
            )
            mode_state = mode_policy.state(
                mode_record.session, is_admin=is_admin
            )
        except ModeTransactionError as exc:
            logger.warning(
                "Host mode initialization rejected for session %s: %s",
                session_id,
                exc,
            )
            await send_msg({"type": "ERROR", "message": exc.message})
            return None
        except Exception:
            logger.exception(
                "Host mode initialization failed for session %s", session_id
            )
            await send_msg({
                "type": "ERROR",
                "message": "Unable to initialize session mode",
            })
            return None
        mode_is_admin = is_admin

    # Publish the verified identity only after every durable initialization and
    # policy derivation above has succeeded.
    conn.update({
        "authenticated": True,
        "agent_address": agent_address,
        "signed_commands": signed_commands,
        "recipient_address": recipient_address,
        "session_id": session_id,
        "session": client_session,
    })
    if mode_is_admin is not None:
        conn["mode_is_admin"] = mode_is_admin

    console.print(f"[green]✓ CONNECT[/green] agent_address={agent_address[:16]}... session={session_id[:8]}... status={status}{' (server_newer)' if server_newer else ''}")

    connected_msg = {
        "type": "CONNECTED",
        "session_id": session_id,
        "status": status,
        "protocol": {"name": "oip", "version": "0.1"},
    }
    if mode_state is not None:
        connected_msg["session_modes"] = mode_state
    if server_newer and client_session:
        from ..session import session_to_chat_items
        connected_msg["server_newer"] = True
        connected_msg["session"] = client_session
        connected_msg["chat_items"] = session_to_chat_items(client_session)
    await send_msg(connected_msg)

    # This socket is now past signature verification and the trust gate, so it is the
    # one channel entitled to the agent's full picture. /info and the relay directory
    # are unauthenticated and deliberately carry the published subset; everything the
    # agent actually has — including skills that live only on the operator's machine —
    # goes here and nowhere else.
    if route_handlers is not None:
        metadata = route_handlers.get("agent_metadata")
        if metadata:
            await send_msg({
                "type": "AGENT_PROFILE",
                "session_id": session_id,
                "name": metadata.get("name"),
                "address": metadata.get("address"),
                "model": metadata.get("model"),
                "tools": metadata.get("tools", []),
                "skills": metadata.get("skills", []),
                **({"balance_usd": metadata["balance_usd"]}
                   if metadata.get("balance_usd") is not None else {}),
            })

    # Push the current dashboard.html so Home paints immediately, before any input.
    # This connection has seen nothing yet, so it always sends when a file exists.
    from .dashboard import send_dashboard
    await send_dashboard(send_msg, session_id, conn)

    if status == "running":
        active.io.rewind_to(data.get("last_msg_id"))
        return resume_forwarding(send_msg, active, registry, session_id, storage, conn)
