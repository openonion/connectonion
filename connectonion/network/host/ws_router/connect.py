"""
Purpose: Handle the CONNECT message — Ed25519 signature auth, session merge, status decision, optional reattach to a still-running agent
LLM-Note:
  Dependencies: imports from [..session (merge_sessions, session_to_chat_items via lazy local import), ...trust.ws_admin (get_onboard_requirements), .agent_io (resume_forwarding), uuid, rich.console] | imported by [.session as part of CONNECT dispatch]
  Data flow: route_handlers["auth"] verifies sig → if forbidden + onboard methods configured: stash conn['pending_connect'] + send ONBOARD_REQUIRED | else if other err: send ERROR | else: establish_connection(): populate conn (authenticated/identity/session_id/session) → merge_sessions if stored exists → registry status check (running/connected/new) → send CONNECTED → if running: io.rewind_to(last_msg_id) + resume_forwarding (returns (io, task)) | establish_connection is also called by the session loop after a successful onboard, with the onboard-verified identity (no CONNECT replay — its signature may have aged past the 5-minute window)
  State/Effects: mutates conn dict in place (authenticated, identity, session_id, session) | calls registry.update_ping when reattaching to 'connected'
  Integration: handle_connect(data, send_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist) → returns (io, forward_task) for reattach or None
  Performance: one storage.get + optional merge_sessions per CONNECT | one registry.get for status decision
  Errors: auth errors surface to client as ERROR (let it crash for unexpected internals)
"""
import uuid

from rich.console import Console
from ...trust.ws_admin import get_onboard_requirements
from .agent_io import resume_forwarding

console = Console()


async def handle_connect(data, send_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist):
    """Handle CONNECT message: auth, session merge, send CONNECTED. Returns (io, task) for reattach or None."""
    _, identity, sig_valid, err = route_handlers["auth"](
        data, trust, blacklist=blacklist, whitelist=whitelist
    )

    if err and "forbidden" in err.lower():
        trust_agent = route_handlers["trust_agent"]
        onboard_info = get_onboard_requirements(trust_agent)
        if onboard_info:
            # Stash the CONNECT so a successful onboard can finish establishing
            # this connection (establish_connection) — the client must not need
            # a second CONNECT, whose signature may have aged past the 5-minute
            # window by the time an invite code or payment lands.
            conn["pending_connect"] = data
            await send_msg({"type": "ONBOARD_REQUIRED", "identity": identity, **onboard_info})
            return

    if err:
        console.print(f"[red]✗ CONNECT auth error:[/red] {err}")
        await send_msg({"type": "ERROR", "message": err})
        return

    return await establish_connection(data, identity, send_msg, conn, storage, registry)


async def establish_connection(data, identity, send_msg, conn, storage, registry):
    """Post-auth half of CONNECT: populate conn, merge sessions, send CONNECTED.

    Called by handle_connect and, after a successful onboard, with the stashed
    pending CONNECT — the identity is then the one verified on ONBOARD_SUBMIT.
    """
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
        from ..session import merge_sessions
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
        from ..session import session_to_chat_items
        connected_msg["server_newer"] = True
        connected_msg["session"] = conn["session"]
        connected_msg["chat_items"] = session_to_chat_items(conn["session"])
    await send_msg(connected_msg)

    if status == "running":
        active.io.rewind_to(data.get("last_msg_id"))
        return resume_forwarding(send_msg, active, registry, session_id, storage)
