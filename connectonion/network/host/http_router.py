"""
Purpose: HTTP route handlers for agent hosting endpoints (POST /input, session/admin/health/info)
LLM-Note:
  Dependencies: imports from [network/host/session/ (Session, SessionStorage, merge_sessions, session_to_chat_items), network/asgi/http (read_body, send_json, send_html, send_text, CORS_HEADERS), network/trust/http_admin] | imported by [network/host/server.py, network/asgi/http.py] | tested by [tests/unit/test_host_routes.py]
  Data flow: input_handler() receives prompt+session → calls create_agent() factory → exposes an isolated trusted server-session snapshot to plugins → merges client+server session via merge_sessions() if stored exists → calls agent.input(prompt, session) → records 'running' shell + final 'done' to SessionStorage → returns {session_id, status, result, duration_ms, session, chat_items, server_newer}
  State/Effects: reads/writes SessionStorage via storage.save()/get() | factory creates fresh agent per request (prevents state bleeding) | session records carry TTL expiry
  Integration: exposes input_handler, session_handler, sessions_handler, health_handler, info_handler, admin_logs/sessions/trust/admins handlers | used by server.py and ASGI adapters
  Performance: factory creates fresh agent per request (thread-safe) | SessionStorage TTL auto-cleanup | session continuation via session_id provided by client
  Errors: input_handler raises ValueError if session_id missing | session_handler returns None if session_id not found | admin_logs_handler returns {"error": "..."} if log file missing

Session ID ownership:
  - Client generates UUID on first request (TypeScript SDK: generateUUID())
  - Server uses client's session_id for storage and reconnection
  - Security: session_id is a correlation ID, not credential. Ed25519 signature provides auth.
"""

import json
import time
import uuid
from copy import deepcopy
from functools import partial
from pathlib import Path
from typing import Callable

from ..asgi.http import read_body, send_json, send_html, send_text, CORS_HEADERS
from ..trust.http_admin import handle_admin_routes
from .session import Session, SessionStorage, merge_sessions, session_to_chat_items


# ═══════════════════════════════════════════════════════
# Handlers
# ═══════════════════════════════════════════════════════

def input_handler(create_agent: Callable, storage: SessionStorage, prompt: str, result_ttl: int,
                  session: dict | None = None, connection=None, images: list[str] | None = None,
                  files: list[dict] | None = None) -> dict:
    """POST /input (and WebSocket /ws) with session merge and UI conversion."""
    agent = create_agent()
    agent.io = connection
    agent.storage = storage
    now = time.time()

    session = session or {}
    session_id = session.get('session_id')
    if not session_id:
        raise ValueError("session_id required in session dict")
    server_newer = False

    stored = storage.get(session_id)
    trusted_server_session = None
    if stored and stored.session:
        # Expose an isolated server-owned snapshot to plugins. Plugins decide
        # which state they own; core never needs plugin-specific restore logic.
        trusted_server_session = deepcopy(stored.session)

        session, server_newer = merge_sessions(
            client_session=session,
            server_session=stored.session
        )

    agent._trusted_server_session = trusted_server_session

    record = Session(
        session_id=session_id,
        status="running",
        prompt=prompt,
        created=now,
        expires=now + result_ttl,
    )
    storage.save(record)

    start = time.time()
    result = agent.input(prompt, session=session, images=images, files=files)
    duration_ms = int((time.time() - start) * 1000)

    agent.current_session['updated'] = time.time()

    record.status = "done"
    record.result = result
    record.duration_ms = duration_ms
    record.session = agent.current_session
    storage.save(record)

    chat_items = session_to_chat_items(agent.current_session)

    return {
        "session_id": session_id,
        "status": "done",
        "result": result,
        "duration_ms": duration_ms,
        "session": agent.current_session,
        "chat_items": chat_items,
        "server_newer": server_newer,
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


def info_handler(agent_metadata: dict, trust, trust_config: dict | None = None,
                 host_config: dict | None = None) -> dict:
    """GET /info"""
    from ... import __version__
    from .config import DEFAULT_FILE_LIMITS

    file_config = host_config or DEFAULT_FILE_LIMITS

    result = {
        "name": agent_metadata["name"],
        "address": agent_metadata["address"],
        "tools": agent_metadata["tools"],
        "model": agent_metadata.get("model", "unknown"),
        "trust": trust.trust,
        "version": __version__,
        "skills": agent_metadata.get("skills", []),
        "accepted_inputs": {
            "text": True,
            "images": True,
            "files": {
                "max_file_size_mb": file_config.get("max_file_size", DEFAULT_FILE_LIMITS["max_file_size"]),
                "max_files_per_request": file_config.get("max_files_per_request", DEFAULT_FILE_LIMITS["max_files_per_request"]),
            },
        },
    }

    if trust_config:
        onboard = trust_config.get("onboard", {})
        if onboard:
            result["onboard"] = {
                "invite_code": "invite_code" in onboard,
                "payment": onboard.get("payment"),
            }

    return result


def admin_logs_handler(agent_name: str) -> dict:
    """GET /admin/logs"""
    log_path = Path(f".co/logs/{agent_name}.log")
    if log_path.exists():
        return {"content": log_path.read_text()}
    return {"error": "No logs found"}


def admin_sessions_handler() -> dict:
    """GET /admin/sessions"""
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

    sessions.sort(key=lambda s: s.get("updated", s.get("created", "")), reverse=True)
    return {"sessions": sessions}


def admin_trust_promote_handler(trust_agent, client_id: str) -> dict:
    """POST /admin/trust/promote"""
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
    """POST /admin/trust/demote"""
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
    """POST /admin/trust/block"""
    result = trust_agent.block(client_id, reason)
    return {"success": True, "message": result, "level": trust_agent.get_level(client_id)}


def admin_trust_unblock_handler(trust_agent, client_id: str) -> dict:
    """POST /admin/trust/unblock"""
    result = trust_agent.unblock(client_id)
    return {"success": True, "message": result, "level": trust_agent.get_level(client_id)}


def admin_trust_level_handler(trust_agent, client_id: str) -> dict:
    """GET /admin/trust/level/{client_id}"""
    return {"client_id": client_id, "level": trust_agent.get_level(client_id)}


def admin_admins_add_handler(trust_agent, admin_id: str) -> dict:
    """POST /superadmin/add"""
    result = trust_agent.add_admin(admin_id)
    return {"success": True, "message": result}


def admin_admins_remove_handler(trust_agent, admin_id: str) -> dict:
    """POST /superadmin/remove"""
    result = trust_agent.remove_admin(admin_id)
    return {"success": True, "message": result}


# ═══════════════════════════════════════════════════════
# Router
# ═══════════════════════════════════════════════════════

async def handle_http(
    scope,
    receive,
    send,
    *,
    route_handlers: dict,
    storage,
    trust: str,
    trust_config: dict | None = None,
    start_time: float,
    blacklist: list | None = None,
    whitelist: list | None = None,
):
    """Route HTTP requests to handler functions."""
    method, path = scope["method"], scope["path"]

    if method == "OPTIONS":
        headers = CORS_HEADERS + [[b"content-length", b"0"]]
        await send({"type": "http.response.start", "status": 204, "headers": headers})
        await send({"type": "http.response.body", "body": b""})
        return

    if path.startswith("/admin") or path.startswith("/superadmin"):
        await handle_admin_routes(
            method, path, scope, receive, route_handlers,
            send_json=partial(send_json, send),
            send_text=partial(send_text, send),
            read_body=read_body,
        )
        return

    if method == "POST" and path == "/input":
        body = await read_body(receive)
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            await send_json(send, {"error": "Invalid JSON"}, 400)
            return

        prompt, agent_address, sig_valid, err = route_handlers["auth"](
            data, trust, blacklist=blacklist, whitelist=whitelist
        )
        if err:
            status = 401 if err.startswith("unauthorized") else 403 if err.startswith("forbidden") else 400
            await send_json(send, {"error": err}, status)
            return

        session = data.get("session") or {}
        if not session.get("session_id"):
            session["session_id"] = str(uuid.uuid4())
        images = data.get("images")
        files = data.get("files")
        try:
            result = route_handlers["input"](storage, prompt, session, images=images, files=files)
        except ValueError as e:
            await send_json(send, {"error": str(e)}, 400)
            return
        await send_json(send, result)

    elif method == "GET" and path.startswith("/sessions/"):
        result = route_handlers["session"](storage, path[10:])
        await send_json(send, result or {"error": "not found"}, 404 if not result else 200)

    elif method == "GET" and path == "/sessions":
        await send_json(send, route_handlers["sessions"](storage))

    elif method == "GET" and path == "/health":
        await send_json(send, route_handlers["health"](start_time))

    elif method == "GET" and path == "/info":
        await send_json(send, route_handlers["info"](trust, trust_config))

    elif method == "GET" and path == "/docs":
        base = Path(__file__).resolve().parent.parent
        html_path = base / "static" / "docs.html"
        html = html_path.read_bytes()
        await send_html(send, html)

    else:
        await send_json(send, {"error": "not found"}, 404)
