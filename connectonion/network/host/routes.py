"""
Purpose: HTTP/WebSocket route handlers for agent hosting endpoints
LLM-Note:
  Dependencies: imports from [network/host/session.py, connectonion/__init__.py] | imported by [network/host/server.py, network/asgi/http.py, network/asgi/websocket.py] | tested by [tests/network/test_host_routes.py]
  Data flow: receives HTTP request → input_handler() calls create_agent() for fresh instance → server generates session_id (new) or uses existing (continuation) → calls agent.input(prompt, session) → stores result in SessionStorage → returns {session_id, status, result, duration_ms, session}
  State/Effects: reads/writes SessionStorage via storage.save()/get()/list() | factory creates fresh agent per request (prevents state bleeding) | writes session records with TTL expiry | session_id always server-generated
  Integration: exposes input_handler(create_agent, storage, prompt, result_ttl, session, connection), session_handler(storage, session_id), sessions_handler(storage), health_handler(agent_name, start_time), info_handler(agent_metadata, trust), admin_logs_handler(agent_name), admin_sessions_handler() | used by server.py and ASGI adapters
  Performance: factory creates fresh agent per request (thread-safe, no deep copy issues) | SessionStorage TTL auto-cleanup | session continuation via session dict (multi-turn conversations)
  Errors: session_handler returns None if session_id not found | admin_logs_handler returns {"error": "..."} if log file missing
Route handlers for hosted agents.
"""

import time
import uuid
from pathlib import Path
from typing import Callable

from .session import Session, SessionStorage


def input_handler(create_agent: Callable, storage: SessionStorage, prompt: str, result_ttl: int,
                  session: dict | None = None, connection=None) -> dict:
    """POST /input (and WebSocket /ws)

    Args:
        create_agent: Factory function that returns a fresh Agent instance
        storage: SessionStorage for persisting results
        prompt: The user's prompt
        result_ttl: How long to keep the result on server
        session: Optional conversation session for continuation
        connection: WebSocket connection for bidirectional I/O (None for HTTP)
    """
    agent = create_agent()  # Fresh instance per request
    agent.io = connection  # WebSocket connection or None for HTTP
    now = time.time()

    # Server generates session_id (new session) or uses existing (continuation)
    # NOTE: We mutate `session` dict here, but it's safe - the dict is created
    # fresh from json.loads() per request, not shared anywhere.
    session = session or {}
    session_id = session.get('session_id') or str(uuid.uuid4())
    session['session_id'] = session_id

    # Create storage record
    record = Session(
        session_id=session_id,
        status="running",
        prompt=prompt,
        created=now,
        expires=now + result_ttl,
    )
    storage.save(record)

    # TODO: If agent.input() throws, record stays "running" until TTL expires.
    # This is acceptable: client gets 500 error, record expires naturally.
    start = time.time()
    result = agent.input(prompt, session=session)
    duration_ms = int((time.time() - start) * 1000)

    record.status = "done"
    record.result = result
    record.duration_ms = duration_ms
    storage.save(record)

    # Return result with updated session for client to continue conversation
    return {
        "session_id": session_id,
        "status": "done",
        "result": result,
        "duration_ms": duration_ms,
        "session": agent.current_session
    }


def session_handler(storage: SessionStorage, session_id: str) -> dict | None:
    """GET /sessions/{id}"""
    session = storage.get(session_id)
    return session.model_dump() if session else None


def sessions_handler(storage: SessionStorage) -> dict:
    """GET /sessions"""
    return {"sessions": [s.model_dump() for s in storage.list()]}


def health_handler(agent_name: str, start_time: float) -> dict:
    """GET /health"""
    return {"status": "healthy", "agent": agent_name, "uptime": int(time.time() - start_time)}


def info_handler(agent_metadata: dict, trust, trust_config: dict | None = None) -> dict:
    """GET /info

    Returns pre-extracted metadata including onboard requirements.

    Args:
        agent_metadata: Agent name, address, tools
        trust: TrustAgent instance (trust level extracted via .trust attribute)
        trust_config: Parsed YAML config from trust policy (optional)
    """
    from ... import __version__

    result = {
        "name": agent_metadata["name"],
        "address": agent_metadata["address"],
        "tools": agent_metadata["tools"],
        "trust": trust.trust,  # Extract level string from TrustAgent
        "version": __version__,
    }

    # Add onboard info if available
    if trust_config:
        onboard = trust_config.get("onboard", {})
        if onboard:
            result["onboard"] = {
                "invite_code": "invite_code" in onboard,
                "payment": onboard.get("payment"),
            }

    return result


def admin_logs_handler(agent_name: str) -> dict:
    """GET /admin/logs - return plain text activity log file."""
    log_path = Path(f".co/logs/{agent_name}.log")
    if log_path.exists():
        return {"content": log_path.read_text()}
    return {"error": "No logs found"}


def admin_sessions_handler() -> dict:
    """GET /admin/sessions - return raw session YAML files as JSON.

    Returns session files as-is (converted from YAML to JSON). Each session
    contains: name, created, updated, total_cost, total_tokens, turns array.
    Frontend handles the display logic.
    """
    import yaml
    sessions_dir = Path(".co/evals")
    if not sessions_dir.exists():
        return {"sessions": []}

    sessions = []
    for session_file in sessions_dir.glob("*.yaml"):
        with open(session_file) as f:
            session_data = yaml.safe_load(f)
            if session_data:
                sessions.append(session_data)

    # Sort by updated date descending (newest first)
    sessions.sort(key=lambda s: s.get("updated", s.get("created", "")), reverse=True)
    return {"sessions": sessions}


# === Admin Trust Routes ===
# These receive TrustAgent instance from route_handlers

def admin_trust_promote_handler(trust_agent, client_id: str) -> dict:
    """POST /admin/trust/promote - Promote client to next level."""
    level = trust_agent.get_level(client_id)
    if level == "stranger":
        result = trust_agent.promote_to_contact(client_id)
    elif level == "contact":
        result = trust_agent.promote_to_whitelist(client_id)
    elif level == "whitelist":
        return {"error": "Already at highest level", "level": level}
    elif level == "blocked":
        return {"error": "Client is blocked. Unblock first.", "level": level}
    else:
        return {"error": f"Unknown level: {level}"}

    return {"success": True, "message": result, "level": trust_agent.get_level(client_id)}


def admin_trust_demote_handler(trust_agent, client_id: str) -> dict:
    """POST /admin/trust/demote - Demote client to previous level."""
    level = trust_agent.get_level(client_id)
    if level == "whitelist":
        result = trust_agent.demote_to_contact(client_id)
    elif level == "contact":
        result = trust_agent.demote_to_stranger(client_id)
    elif level == "stranger":
        return {"error": "Already at lowest level", "level": level}
    elif level == "blocked":
        return {"error": "Client is blocked. Unblock first.", "level": level}
    else:
        return {"error": f"Unknown level: {level}"}

    return {"success": True, "message": result, "level": trust_agent.get_level(client_id)}


def admin_trust_block_handler(trust_agent, client_id: str, reason: str = "") -> dict:
    """POST /admin/trust/block - Block a client."""
    result = trust_agent.block(client_id, reason)
    return {"success": True, "message": result, "level": trust_agent.get_level(client_id)}


def admin_trust_unblock_handler(trust_agent, client_id: str) -> dict:
    """POST /admin/trust/unblock - Unblock a client."""
    result = trust_agent.unblock(client_id)
    return {"success": True, "message": result, "level": trust_agent.get_level(client_id)}


def admin_trust_level_handler(trust_agent, client_id: str) -> dict:
    """GET /admin/trust/level/{client_id} - Get client's trust level."""
    return {"client_id": client_id, "level": trust_agent.get_level(client_id)}


# === Super Admin Routes (admin management) ===

def admin_admins_add_handler(trust_agent, admin_id: str) -> dict:
    """POST /superadmin/add - Add an admin. Super admin only."""
    result = trust_agent.add_admin(admin_id)
    return {"success": True, "message": result}


def admin_admins_remove_handler(trust_agent, admin_id: str) -> dict:
    """POST /superadmin/remove - Remove an admin. Super admin only."""
    result = trust_agent.remove_admin(admin_id)
    return {"success": True, "message": result}
