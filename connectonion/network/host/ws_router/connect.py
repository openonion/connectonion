"""
Purpose: Handle the CONNECT message — Ed25519 signature auth, session merge, status decision, optional reattach to a still-running agent
LLM-Note:
  Dependencies: imports from [..session (merge_sessions, session_to_chat_items via lazy local import), ...trust.ws_admin (get_onboard_requirements), .agent_io (resume_forwarding), uuid, rich.console] | imported by [.session as part of CONNECT dispatch]
  Data flow: route_handlers["auth"] verifies sig → if forbidden + onboard methods configured: stash conn['pending_connect'] + send ONBOARD_REQUIRED | else if other err: send ERROR | else: establish_connection(): populate conn (authenticated/agent_address/session_id/session) → merge_sessions if stored exists → registry status check (running/connected/new) → send CONNECTED → if running: io.rewind_to(last_msg_id) + resume_forwarding (returns (io, task)) | establish_connection is also called by the session loop after a successful onboard, with the onboard-verified agent_address (no CONNECT replay — its signature may have aged past the 5-minute window)
  State/Effects: mutates conn dict in place (authenticated, agent_address, session_id, session) | calls registry.update_ping when reattaching to 'connected'
  Integration: handle_connect(data, send_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist) → returns (io, forward_task) for reattach or None
  Performance: one storage.get + optional merge_sessions per CONNECT | one registry.get for status decision
  Errors: auth errors surface to client as ERROR (let it crash for unexpected internals)
"""
import asyncio
import uuid
from copy import deepcopy

from rich.console import Console
from ...trust.ws_admin import get_onboard_requirements
from ..auth import canonical_session_sha256
from ..session.storage import MAX_SESSION_ID_LENGTH
from .agent_io import resume_forwarding

console = Console()


def _session_binding(data):
    """Return sid/session signature bindings for a CONNECT frame."""
    payload = data.get("payload") or {}
    if not isinstance(payload, dict):
        return None, False, False, "unauthorized: payload must be an object"
    top_session_id = data.get("session_id")
    signed_session_id_present = isinstance(payload, dict) and "session_id" in payload
    signed_session_id = payload.get("session_id") if signed_session_id_present else None

    if signed_session_id_present and signed_session_id != top_session_id:
        return None, False, False, "unauthorized: session_id mismatch"
    if top_session_id is not None and (
        not isinstance(top_session_id, str) or not top_session_id
    ):
        return None, False, False, "unauthorized: invalid session_id"
    if (
        isinstance(top_session_id, str)
        and len(top_session_id) > MAX_SESSION_ID_LENGTH
    ):
        return None, False, False, "unauthorized: session_id is too long"

    client_session = data.get("session")
    if client_session is not None and not isinstance(client_session, dict):
        return None, False, False, "invalid session"
    nested_session_id = (client_session or {}).get("session_id")
    if nested_session_id and nested_session_id != top_session_id:
        return None, False, False, "unauthorized: session_id mismatch"

    signed_session_digest = payload.get("session_sha256")
    session_authenticated = signed_session_digest is not None
    if session_authenticated and (
        not isinstance(signed_session_digest, str)
        or signed_session_digest != canonical_session_sha256(client_session)
    ):
        return None, False, False, "unauthorized: session snapshot mismatch"

    if top_session_id is None:
        return str(uuid.uuid4()), True, session_authenticated, None
    return top_session_id, signed_session_id_present, session_authenticated, None


def _round_trip_session(session):
    copied = deepcopy(session or {})
    copied.pop("owner_address", None)
    copied.pop("server_state", None)
    copied.pop("_trusted_server_state", None)
    return copied


async def handle_connect(data, send_msg, conn, route_handlers, storage, registry, trust, blacklist, whitelist):
    """Handle CONNECT message: auth, session merge, send CONNECTED. Returns (io, task) for reattach or None."""
    _, agent_address, sig_valid, err = route_handlers["auth"](
        data, trust, blacklist=blacklist, whitelist=whitelist
    )
    is_forbidden = bool(err and "forbidden" in err.lower())
    if err and not is_forbidden:
        console.print(f"[red]✗ CONNECT auth error:[/red] {err}")
        await send_msg({"type": "ERROR", "message": err})
        return

    # Validate the modern routing envelope before a trust-policy rejection can
    # stash it for onboarding. Authentication still runs first so an invalid
    # signature does not receive a more specific envelope oracle.
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    if "session_sha256" in payload:
        recipient = route_handlers.get("recipient_address")
        if payload.get("action") != "session.connect":
            await send_msg({"type": "ERROR", "message": "unauthorized: wrong signed action"})
            return
        if not recipient or payload.get("to") != recipient or data.get("to") != recipient:
            await send_msg({"type": "ERROR", "message": "unauthorized: wrong recipient"})
            return

    if is_forbidden:
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
        console.print(f"[red]✗ CONNECT auth error:[/red] {err}")
        await send_msg({"type": "ERROR", "message": err})
        return

    return await establish_connection(data, agent_address, send_msg, conn, storage, registry)


async def establish_connection(data, agent_address, send_msg, conn, storage, registry):
    """Post-auth half of CONNECT: populate conn, merge sessions, send CONNECTED.

    Called by handle_connect and, after a successful onboard, with the stashed
    pending CONNECT — the agent_address is then the one verified on ONBOARD_SUBMIT.
    """
    (
        session_id,
        session_id_authenticated,
        session_authenticated,
        binding_error,
    ) = _session_binding(data)
    if binding_error:
        await send_msg({"type": "ERROR", "message": binding_error})
        return

    client_session = data.get("session") or {}
    explicit_owner = client_session.get("owner_address", data.get("owner_address"))
    if explicit_owner is not None and explicit_owner != agent_address:
        await send_msg({"type": "ERROR", "message": "forbidden: session owner mismatch"})
        return

    # A running agent holds the per-session storage lock for its whole turn,
    # including while it waits for approval. Reconnect must therefore resolve
    # against the owner-bound in-memory registry before touching storage, or it
    # can deadlock waiting for the agent that is itself waiting for this client.
    active = registry.get(session_id)
    if active and active.owner_address != agent_address:
        await send_msg({"type": "ERROR", "message": "forbidden: session owner mismatch"})
        return
    if active and active.status == 'running':
        if not session_id_authenticated:
            await send_msg({
                "type": "ERROR",
                "message": "unauthorized: signed session_id required to resume active session",
            })
            return

        # A reconnecting client cannot replace the transcript of an execution
        # that is already running. The next fresh turn reloads the completed
        # owner-bound snapshot from storage; until then an empty local view is
        # safer than retaining a client-supplied history.
        merged_session = {}
        conn["authenticated"] = True
        conn["agent_address"] = agent_address
        conn["session_id"] = session_id
        conn["session_id_authenticated"] = True
        conn["session_authenticated"] = session_authenticated
        conn["session"] = merged_session

        await send_msg({"type": "CONNECTED", "session_id": session_id, "status": "running"})
        active.io.rewind_to(data.get("last_msg_id"))
        return resume_forwarding(
            send_msg, active, registry, session_id, storage, agent_address
        )

    stored = await asyncio.to_thread(storage.get, session_id)
    if stored and stored.owner_address is None:
        await send_msg({
            "type": "ERROR",
            "message": (
                "forbidden: legacy ownerless session cannot be resumed; "
                "start a new session without the old session_id"
            ),
        })
        return
    owner_matches = bool(
        stored
        and stored.owner_address is not None
        and stored.owner_address == agent_address
    )
    if stored and stored.owner_address is not None and not owner_matches:
        await send_msg({"type": "ERROR", "message": "forbidden: session owner mismatch"})
        return

    merged_session = _round_trip_session(client_session)
    server_newer = False

    if merged_session:
        msg_count = len(merged_session.get("messages", []))
        console.print(f"  [dim]↑ client session: {msg_count} messages[/dim]")

    if owner_matches and stored.session is not None:
        # Persistence is the server's transcript of record. A signature proves
        # who supplied a client snapshot; it does not authorize that snapshot
        # to replace already-persisted history (even when the persisted value
        # is an intentionally empty dict).
        authoritative_session = _round_trip_session(stored.session)
        server_newer = authoritative_session != merged_session
        merged_session = authoritative_session
        if server_newer:
            console.print(f"  [dim]↕ merged sessions (server newer)[/dim]")

    # Only a signature-bound sid can reattach to a live execution.  Legacy
    # CONNECT signatures remain accepted, but status as a fresh connection.
    owned_active = (
        active
        if session_id_authenticated and active and active.owner_address == agent_address
        else None
    )
    if owned_active and owned_active.status == 'running':
        status = "running"
    elif owned_active and owned_active.status == 'connected':
        status = "connected"
        registry.update_ping(session_id, agent_address)
    else:
        status = "new"

    conn["authenticated"] = True
    conn["agent_address"] = agent_address
    conn["session_id"] = session_id
    conn["session_id_authenticated"] = session_id_authenticated
    conn["session_authenticated"] = session_authenticated
    conn["session"] = merged_session

    console.print(f"[green]✓ CONNECT[/green] agent_address={agent_address[:16]}... session={session_id[:8]}... status={status}{' (server_newer)' if server_newer else ''}")

    connected_msg = {"type": "CONNECTED", "session_id": session_id, "status": status}
    if server_newer:
        from ..session import session_to_chat_items
        connected_msg["server_newer"] = True
        connected_msg["session"] = merged_session
        connected_msg["chat_items"] = session_to_chat_items(merged_session)
    await send_msg(connected_msg)

    if status == "running":
        owned_active.io.rewind_to(data.get("last_msg_id"))
        return resume_forwarding(
            send_msg, owned_active, registry, session_id, storage, agent_address
        )
