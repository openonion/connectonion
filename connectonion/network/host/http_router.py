"""
Purpose: HTTP route handlers for agent hosting endpoints (POST /input, session/admin/health/info)
LLM-Note:
  Dependencies: imports from [network/host/session/ (Session, SessionStorage, merge_sessions, session_to_chat_items), network/asgi/http (read_body, send_json, send_html, send_text, CORS_HEADERS), network/trust/http_admin] | imported by [network/host/server.py, network/asgi/http.py] | tested by [tests/unit/test_host_routes.py]
  Data flow: input_handler() receives prompt+session → calls create_agent() factory → merges client+server session via merge_sessions() if stored exists → calls agent.input(prompt, session) → records 'running' shell + final 'done' to SessionStorage → returns {session_id, status, result, duration_ms, session, chat_items, server_newer}
  State/Effects: reads/writes SessionStorage via storage.save()/get() | factory creates fresh agent per request (prevents state bleeding) | session records carry TTL expiry
  Integration: exposes input_handler, session_handler, sessions_handler, health_handler, info_handler, admin_logs/sessions/trust/admins handlers | used by server.py and ASGI adapters
  Performance: factory creates fresh agent per request (thread-safe) | SessionStorage TTL auto-cleanup | session continuation via session_id provided by client
  Errors: input_handler raises ValueError if session_id missing | session_handler returns None if session_id not found | admin_logs_handler returns {"error": "..."} if log file missing

Session ID ownership:
  - Client generates UUID on first request (TypeScript SDK: generateUUID())
  - Server uses client's session_id for storage and reconnection
  - Security: session_id is a correlation ID, not credential. Ed25519 signature provides auth.
"""

import asyncio
import json
import hmac
import math
import os
import time
import uuid
from contextlib import nullcontext
from copy import deepcopy
from functools import partial
from pathlib import Path
from typing import Callable

from ..asgi.http import read_body, send_json, send_html, send_text, CORS_HEADERS
from ..trust.http_admin import handle_admin_routes
from .auth import (
    MAX_SESSION_ID_LENGTH,
    authenticate_bound_input,
    canonical_session_sha256,
)
from .session import (
    Session,
    SessionStorage,
    narrow_server_state,
    session_to_chat_items,
)


# ═══════════════════════════════════════════════════════
# Handlers
# ═══════════════════════════════════════════════════════

def _client_session_copy(session: dict | None) -> dict:
    """Copy round-trip state while removing server-only lookalike fields."""
    copied = deepcopy(session or {})
    copied.pop("owner_address", None)
    copied.pop("server_state", None)
    copied.pop("_trusted_server_state", None)
    return copied


def _public_session_dump(session: Session) -> dict:
    """Serialize a storage record without server-only capability state."""
    return session.model_dump(exclude={"owner_address", "server_state"})


def _preflight_session(
    storage,
    session: dict,
    agent_address: str | None,
) -> tuple[Session | None, bool]:
    """Validate a routed session before replay state or execution changes."""
    if not isinstance(session, dict):
        raise ValueError("invalid session")
    explicit_owner = session.get("owner_address")
    if explicit_owner is not None and explicit_owner != agent_address:
        raise PermissionError("session owner mismatch")
    session_id = session.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id required in session dict")
    if len(session_id) > MAX_SESSION_ID_LENGTH:
        raise ValueError("session_id is too long")

    get_stored = getattr(storage, "get", None)
    if not callable(get_stored):
        return None, False
    stored = get_stored(session_id)
    owner_matches = bool(
        stored
        and agent_address is not None
        and stored.owner_address == agent_address
    )
    if stored and stored.owner_address is None:
        raise PermissionError(
            "legacy ownerless session cannot be resumed; "
            "start a new session without the old session_id"
        )
    if stored and stored.owner_address is not None and not owner_matches:
        raise PermissionError("session owner mismatch")
    return stored, owner_matches


def input_handler(create_agent: Callable, storage: SessionStorage, prompt: str, result_ttl: int,
                  session: dict | None = None, connection=None, images: list[str] | None = None,
                  files: list[dict] | None = None, agent_address: str | None = None,
                  mode: str | None = None, session_id_authenticated: bool = False) -> dict:
    """POST /input (and WebSocket /ws) with session merge and UI conversion."""
    raw_session = {} if session is None else session
    if not isinstance(raw_session, dict):
        raise ValueError("invalid session")
    if not session_id_authenticated and mode in {"ulw", "accept_edits"}:
        raise PermissionError("signed session_id required for privileged mode")

    session_id = raw_session.get('session_id')
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id required in session dict")

    # Hold the per-sid reentrant lock through merge, execution, checkpoints,
    # and final persistence.  Two concurrent turns can no longer both restore
    # the same old ULW counter and let the later finisher roll it backwards.
    with storage.session_lock(session_id):
        stored, owner_matches = _preflight_session(
            storage, raw_session, agent_address
        )
        return _run_input(
            create_agent=create_agent,
            storage=storage,
            prompt=prompt,
            result_ttl=result_ttl,
            session=_client_session_copy(raw_session),
            connection=connection,
            images=images,
            files=files,
            agent_address=agent_address,
            mode=mode,
            session_id_authenticated=session_id_authenticated,
            stored=stored,
            owner_matches=owner_matches,
        )


def _run_input(
    *,
    create_agent,
    storage,
    prompt,
    result_ttl,
    session,
    connection,
    images,
    files,
    agent_address,
    mode,
    session_id_authenticated,
    stored,
    owner_matches,
):
    """Execute one input while the caller holds the session lock."""
    agent = create_agent()
    agent.io = connection
    agent.storage = storage
    agent._session_owner_address = agent_address
    agent._session_id_authenticated = session_id_authenticated
    now = time.time()
    session_id = session['session_id']
    server_newer = False
    trusted_server_state = {}
    previous_server_state = {}

    if owner_matches:
        previous_server_state = narrow_server_state(stored.server_state)
        if stored.session is not None:
            # The persisted owner-bound transcript is authoritative.  A WS
            # relay can alter legacy CONNECT session/history fields, and the
            # per-INPUT signature intentionally does not re-sign that entire
            # snapshot.  Never let an iteration counter replace server truth.
            server_newer = session != stored.session
            session = deepcopy(stored.session)
            session = _client_session_copy(session)
        if session_id_authenticated:
            trusted_server_state = deepcopy(previous_server_state)

    # This is the only capability-bearing state exposed to the Agent.  It was
    # loaded from a server record after both owner and signed sid validation.
    agent._trusted_server_state = deepcopy(trusted_server_state)
    agent._trusted_server_state_binding = (
        (agent_address, session_id)
        if session_id_authenticated and trusted_server_state
        else None
    )

    record = Session(
        session_id=session_id,
        owner_address=agent_address,
        status="running",
        prompt=prompt,
        server_state=deepcopy(previous_server_state),
        created=now,
        expires=now + result_ttl,
    )
    storage.save(record)

    start = time.time()
    input_kwargs = {"session": session, "images": images, "files": files}
    if mode is not None:
        input_kwargs["mode"] = mode
    try:
        result = agent.input(prompt, **input_kwargs)
    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        runtime_session = (
            agent.current_session
            if isinstance(getattr(agent, 'current_session', None), dict)
            else session
        )
        runtime_session['updated'] = time.time()
        record.status = "error"
        record.result = str(exc)
        record.duration_ms = duration_ms
        record.server_state = _persisted_server_state(
            agent,
            previous_server_state,
            owner_matches=owner_matches,
            session_id_authenticated=session_id_authenticated,
        )
        record.session = _client_session_copy(runtime_session)
        storage.save(record)
        raise

    duration_ms = int((time.time() - start) * 1000)
    agent.current_session['updated'] = time.time()
    record.server_state = _persisted_server_state(
        agent,
        previous_server_state,
        owner_matches=owner_matches,
        session_id_authenticated=session_id_authenticated,
    )

    record.status = "done"
    record.result = result
    record.duration_ms = duration_ms
    round_trip_session = _client_session_copy(agent.current_session)
    record.session = round_trip_session
    storage.save(record)

    chat_items = session_to_chat_items(round_trip_session)

    return {
        "session_id": session_id,
        "status": "done",
        "result": result,
        "duration_ms": duration_ms,
        "session": round_trip_session,
        "chat_items": chat_items,
        "server_newer": server_newer,
    }


def _persisted_server_state(
    agent,
    previous_server_state,
    *,
    owner_matches,
    session_id_authenticated,
):
    """Narrow runtime controls without letting an unbound sid gain authority."""
    runtime_state = deepcopy(getattr(agent, "_trusted_server_state", {}) or {})
    current_session = getattr(agent, 'current_session', None)
    runtime_mode = current_session.get("mode") if isinstance(current_session, dict) else None
    if isinstance(runtime_mode, str) and runtime_mode:
        runtime_state["mode"] = runtime_mode

    if session_id_authenticated:
        return narrow_server_state(runtime_state, previous_server_state)
    if owner_matches and runtime_mode in {"safe", "plan"}:
        return {"mode": runtime_mode}
    return deepcopy(previous_server_state)


def session_handler(
    storage: SessionStorage,
    session_id: str,
    owner_address: str | None = None,
    *,
    is_admin: bool = False,
) -> dict | None:
    """Return one session only to its owner (or an authenticated admin)."""
    session = storage.get(session_id)
    if not session:
        return None
    if not is_admin and (
        owner_address is None or session.owner_address != owner_address
    ):
        return None
    return _public_session_dump(session)


def sessions_handler(
    storage: SessionStorage,
    owner_address: str | None = None,
    *,
    is_admin: bool = False,
) -> dict:
    """List owner-scoped sessions; only admins can list every owner."""
    sessions = storage.list()
    if not is_admin:
        sessions = [s for s in sessions if (
            owner_address is not None and s.owner_address == owner_address
        )]
    return {"sessions": [_public_session_dump(s) for s in sessions]}


def _has_admin_bearer(scope) -> bool:
    headers = dict(scope.get("headers", []))
    authorization = headers.get(b"authorization", b"").decode()
    expected = os.environ.get("OPENONION_API_KEY", "")
    return bool(
        expected
        and authorization.startswith("Bearer ")
        and hmac.compare_digest(authorization[7:], expected)
    )


def _signed_get_request(
    scope,
    *,
    action: str,
    recipient_address: str | None,
    session_id: str | None = None,
):
    """Build signed GET auth data from headers, binding it to this action."""
    headers = dict(scope.get("headers", []))
    agent_address = headers.get(b"x-from", b"").decode()
    signature = headers.get(b"x-signature", b"").decode()
    timestamp = headers.get(b"x-timestamp", b"").decode()
    if not agent_address or not signature or not timestamp:
        return None, "unauthorized: signed session request required"
    if not recipient_address:
        return None, "unauthorized: host recipient unavailable"
    if session_id is not None and len(session_id) > MAX_SESSION_ID_LENGTH:
        return None, "invalid session_id: too long"
    try:
        parsed_timestamp = json.loads(timestamp)
    except (json.JSONDecodeError, TypeError):
        return None, "invalid X-Timestamp header"
    if (not isinstance(parsed_timestamp, (int, float))
            or isinstance(parsed_timestamp, bool)
            or not math.isfinite(parsed_timestamp)):
        return None, "invalid X-Timestamp header"
    payload = {
        "action": action,
        "timestamp": parsed_timestamp,
        "to": recipient_address,
    }
    if session_id is not None:
        payload["session_id"] = session_id
    return {
        "payload": payload,
        "from": agent_address,
        "signature": signature,
    }, None


async def _authenticate_session_get(
    scope,
    path,
    route_handlers,
    trust,
    *,
    blacklist,
    whitelist,
):
    session_id = path[len("/sessions/"):] if path.startswith("/sessions/") else None
    action = "session.get" if session_id is not None else "session.list"
    recipient_address = route_handlers.get("recipient_address")
    data, error = _signed_get_request(
        scope,
        action=action,
        recipient_address=recipient_address,
        session_id=session_id,
    )
    if error:
        return None, error
    _, agent_address, sig_valid, error = await asyncio.to_thread(
        route_handlers["auth"],
        data,
        trust,
        blacklist=blacklist,
        whitelist=whitelist,
        recipient_address=recipient_address,
    )
    if error or not sig_valid:
        return None, error or "unauthorized: invalid signature"
    return agent_address, None


class _DuplicateRequestError(Exception):
    """A fully validated signed request has already been executed."""


def _execute_http_input(
    route_handler,
    storage,
    prompt,
    session,
    *,
    images,
    files,
    agent_address,
    mode,
    binding,
):
    """Preflight, claim, and execute one HTTP INPUT in one lock domain."""
    input_kwargs = {
        "images": images,
        "files": files,
        "agent_address": agent_address,
        "mode": mode,
        "session_id_authenticated": binding is not None,
    }
    if binding is None:
        return route_handler(storage, prompt, session, **input_kwargs)

    session_id = session["session_id"]
    session_lock = getattr(storage, "session_lock", None)
    lock = session_lock(session_id) if callable(session_lock) else nullcontext()
    with lock:
        _preflight_session(storage, session, agent_address)
        claimed = storage.claim_request(
            agent_address,
            session_id,
            binding["request_id"],
            binding["timestamp"],
        )
        if not claimed:
            raise _DuplicateRequestError
        return route_handler(storage, prompt, session, **input_kwargs)


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

        prompt, agent_address, sig_valid, err = await asyncio.to_thread(
            route_handlers["auth"],
            data,
            trust,
            blacklist=blacklist,
            whitelist=whitelist,
            recipient_address=route_handlers.get("recipient_address"),
        )
        if err:
            status = 401 if err.startswith("unauthorized") else 403 if err.startswith("forbidden") else 400
            await send_json(send, {"error": err}, status)
            return

        raw_session = data.get("session")
        session = deepcopy({} if raw_session is None else raw_session)
        if not isinstance(session, dict):
            await send_json(send, {"error": "invalid session"}, 400)
            return
        raw_payload = data.get("payload")
        payload = {} if raw_payload is None else raw_payload
        if not isinstance(payload, dict):
            await send_json(send, {"error": "invalid payload"}, 400)
            return
        signed_session_id = payload.get("session_id") if "session_id" in payload else None
        client_session_id = session.get("session_id")
        if signed_session_id is not None:
            if not isinstance(signed_session_id, str) or not signed_session_id:
                await send_json(send, {"error": "unauthorized: invalid session_id in payload"}, 401)
                return
            if client_session_id and client_session_id != signed_session_id:
                await send_json(send, {"error": "unauthorized: session_id mismatch"}, 401)
                return
            session["session_id"] = signed_session_id
        elif client_session_id:
            pass
        else:
            session["session_id"] = str(uuid.uuid4())

        session_id = session["session_id"]
        binding, binding_error = authenticate_bound_input(
            data,
            recipient_address=route_handlers.get("recipient_address"),
            expected_session_id=session_id,
        )
        if binding_error:
            semantic_errors = {
                "mode must be a string",
                "unsupported mode",
                "prompt must be a non-empty string",
            }
            status = 400 if binding_error in semantic_errors else 401
            await send_json(send, {"error": binding_error}, status)
            return

        if binding is not None:
            if binding["agent_address"] != agent_address:
                await send_json(
                    send, {"error": "unauthorized: identity mismatch"}, 401
                )
                return
            signed_snapshot = payload.get("session_sha256")
            if signed_snapshot is None:
                binding = None
            elif (
                not isinstance(signed_snapshot, str)
                or signed_snapshot != canonical_session_sha256(session)
            ):
                await send_json(
                    send,
                    {"error": "unauthorized: session snapshot mismatch"},
                    401,
                )
                return

        requested_modes = [
            value
            for source in (data, payload)
            if "mode" in source
            for value in [source.get("mode")]
        ]
        if any(not isinstance(value, str) for value in requested_modes):
            await send_json(send, {"error": "mode must be a string"}, 400)
            return
        if len(set(requested_modes)) > 1:
            await send_json(send, {"error": "unauthorized: mode mismatch"}, 401)
            return

        mode = binding["mode"] if binding is not None else "safe"
        if binding is None and requested_modes and requested_modes[0] != "safe":
            await send_json(send, {
                "error": "fully signed INPUT required for non-safe mode",
            }, 403)
            return

        images = data.get("images")
        files = data.get("files")
        try:
            result = await asyncio.to_thread(
                _execute_http_input,
                route_handlers["input"],
                storage,
                prompt,
                session,
                images=images,
                files=files,
                agent_address=agent_address,
                mode=mode,
                binding=binding,
            )
        except _DuplicateRequestError:
            await send_json(send, {"error": "duplicate request"}, 409)
            return
        except PermissionError as e:
            await send_json(send, {"error": str(e)}, 403)
            return
        except ValueError as e:
            await send_json(send, {"error": str(e)}, 400)
            return
        await send_json(send, result)

    elif method == "GET" and path.startswith("/sessions/"):
        session_id = path[10:]
        if len(session_id) > MAX_SESSION_ID_LENGTH:
            await send_json(send, {"error": "invalid session_id: too long"}, 400)
            return
        is_admin = _has_admin_bearer(scope)
        owner_address = None
        if not is_admin:
            owner_address, error = await _authenticate_session_get(
                scope,
                path,
                route_handlers,
                trust,
                blacklist=blacklist,
                whitelist=whitelist,
            )
            if error:
                status = (
                    400 if error.startswith("invalid ")
                    else 403 if error.startswith("forbidden")
                    else 401
                )
                await send_json(send, {"error": error}, status)
                return
        result = await asyncio.to_thread(
            route_handlers["session"],
            storage,
            session_id,
            owner_address,
            is_admin=is_admin,
        )
        await send_json(send, result or {"error": "not found"}, 404 if not result else 200)

    elif method == "GET" and path == "/sessions":
        is_admin = _has_admin_bearer(scope)
        owner_address = None
        if not is_admin:
            owner_address, error = await _authenticate_session_get(
                scope,
                path,
                route_handlers,
                trust,
                blacklist=blacklist,
                whitelist=whitelist,
            )
            if error:
                status = (
                    400 if error.startswith("invalid ")
                    else 403 if error.startswith("forbidden")
                    else 401
                )
                await send_json(send, {"error": error}, status)
                return
        result = await asyncio.to_thread(
            route_handlers["sessions"],
            storage,
            owner_address,
            is_admin=is_admin,
        )
        await send_json(send, result)

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
