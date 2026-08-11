"""
Purpose: HTTP routes for hosted agents, atomic prompt claims, and policy restore
LLM-Note:
  Dependencies: imports from [host/session, session.mode, asgi/http, trust/http_admin]
  Data flow: claim durable session → create/disarm Agent → input → normalize → save
  State/Effects: reads/writes append-only SessionStorage; rejects busy/foreign claims
  Integration: route handlers used by server.py and ASGI adapters
  Performance: creates one isolated Agent per request; storage applies TTL cleanup
  Errors: missing session IDs are invalid; missing sessions return None

Session ID ownership:
  - A frontend client (normally @connectonion/react) generates a UUID on first request
  - Server uses client's session_id for storage and reconnection
  - Security: session_id is a correlation ID, not credential. Ed25519 signature provides auth.
"""

import copy
import json
import logging
import time
import uuid
from functools import partial
from pathlib import Path
from typing import Callable

from ...project import project_co_dir
from ..asgi.http import CORS_HEADERS, read_body, send_html, send_json, send_text
from ..trust.http_admin import handle_admin_routes
from .session import SessionStorage, session_to_chat_items
from .session.mode import SERVER_OWNED_SESSION_KEYS as SERVER_OWNED_SESSION_KEYS
from .session.mode import (
    HostModePolicy,
    ModeTransactionError,
    claim_host_prompt,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# Handlers
# ═══════════════════════════════════════════════════════

def input_handler(create_agent: Callable, storage: SessionStorage, prompt: str, result_ttl: int,
                  session: dict | None = None, connection=None, images: list[str] | None = None,
                  files: list[dict] | None = None, requester: dict | None = None,
                  mode_policy: HostModePolicy | None = None,
                  is_admin: bool = False) -> dict:
    """POST /input (and WebSocket /ws) with session merge and UI conversion."""
    session = session or {}
    session_id = session.get('session_id')
    if not session_id:
        raise ValueError("session_id required in session dict")

    # Preserve the legacy internal/scheduler order when no Host policy is in
    # play. Network routes always pass a policy and must claim before factory
    # side effects; standalone callers historically construct first.
    agent = create_agent() if mode_policy is None else None
    record, server_newer = claim_host_prompt(
        storage,
        session_id,
        prompt,
        result_ttl,
        session,
        requester=requester,
        policy=mode_policy,
        is_admin=is_admin,
    )
    session = record.session

    start = time.time()
    try:
        if agent is None:
            agent = create_agent()
        agent.io = connection
        agent.storage = storage
        if mode_policy is not None:
            if hasattr(agent, "_yolo_turns"):
                agent._yolo_turns = None
            if hasattr(agent, "_yolo_needs_activation"):
                agent._yolo_needs_activation = False
            agent._host_ulw_turns_ceiling = mode_policy.ulw_turns

        result = agent.input(
            prompt, session=session, images=images, files=files
        )
        duration_ms = int((time.time() - start) * 1000)

        if mode_policy is not None:
            agent.current_session = _normalized_host_result(
                agent.current_session,
                requester=requester,
                mode_policy=mode_policy,
                is_admin=is_admin,
            )

        agent.current_session['updated'] = time.time()

        record.status = "done"
        record.result = result
        record.duration_ms = duration_ms
        record.session = agent.current_session
        storage.save(record)
    except Exception:
        # The claim is already durable. Always terminate it so a factory/model
        # exception cannot leave this session busy until Host restarts.
        record.status = "failed"
        record.duration_ms = int((time.time() - start) * 1000)
        if mode_policy is not None:
            record.session = _normalized_host_result(
                record.session,
                requester=requester,
                mode_policy=mode_policy,
                is_admin=is_admin,
            )
        try:
            storage.save(record)
        except Exception:
            logger.exception(
                "Unable to persist failed Host prompt %s", session_id
            )
        raise

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


def _normalized_host_result(
    session: dict,
    *,
    requester: dict | None,
    mode_policy: HostModePolicy,
    is_admin: bool,
) -> dict:
    """Restore verified identity and fail invalid Agent policy state to Safe."""
    final_session = copy.deepcopy(session)
    if requester is not None:
        final_session["requester"] = copy.deepcopy(requester)
    else:
        final_session.pop("requester", None)
    try:
        return mode_policy.normalized(final_session, is_admin=is_admin)
    except ModeTransactionError:
        logger.exception(
            "Agent produced invalid Host session policy; downgrading to Safe"
        )
        return mode_policy.apply(final_session, "safe", is_admin=is_admin)


def exec_handler(create_agent: Callable, permissions: dict, tool_name: str, args: dict) -> dict:
    """Direct tool execution (WS EXEC) — run one registered tool by name, no LLM loop.

    The terminal-style fast path: the client names a tool and its arguments,
    the tool runs immediately, and the raw result (text, or base64 image for
    screenshot tools) goes straight back. No thinking, no session, no history.

    Gated by the SAME permission whitelist the LLM approval flow uses — the
    .co/host.yaml `permissions` block. Before running, the call is checked with
    is_tool_permitted(); a command that isn't whitelisted is refused. So there is
    one list to maintain, and "safe to run without a human" means the same thing
    whether the LLM or a remote client initiates.

    Tool errors are returned as data, not raised — same contract as the LLM
    loop, where tool failures are reported back to the caller for retry.

    NOTE — this runs the tool DIRECTLY: no LLM, and no event/plugin hooks
    (before_each_tool etc.) fire. Anything a plugin does per tool call is skipped
    here. That matters for the browser: the in-process BrowserAutomation relies
    on the bind_browser_session plugin (a before_each_tool hook) to route each
    session to its own tab, and that hook does NOT run for exec. So do NOT expose
    the in-process browser tool names for direct exec. Browser remote-control
    goes through the `co browser` CLI instead — `co browser <verb>` drives the
    persistent browser DAEMON, a separate process that handles tab arbitration
    and lifecycle on its own. See docs/network/remote-call.md.
    """
    from ...useful_plugins.tool_approval.approval import is_tool_permitted

    allowed, reason = is_tool_permitted(tool_name, args, permissions)
    if not allowed:
        return {"status": "error",
                "error": f"blocked: {reason}. Allow it by adding a rule to .co/host.yaml permissions."}

    agent = create_agent()
    tool = agent.tools.get(tool_name)
    if tool is None:
        return {"status": "error",
                "error": f"unknown tool '{tool_name}' (available: {agent.tools.names()})"}

    # Same injection as tool_executor: tools that declare 'agent' get it at call
    # time (never exposed to the caller's args).
    if getattr(tool, '_needs_agent', False):
        args = {**args, "agent": agent}

    start = time.time()
    try:
        result = tool(**args)
    except Exception as e:
        return {"status": "error",
                "error": f"{type(e).__name__}: {e}",
                "duration_ms": int((time.time() - start) * 1000)}

    return {"status": "success",
            "result": str(result),
            "duration_ms": int((time.time() - start) * 1000)}


def session_handler(storage: SessionStorage, session_id: str,
                    caller: str | None = None) -> dict | None:
    """GET /sessions/{id} — the caller's own, or nothing.

    Owner recorded by #698. A session stored before that has none and stays
    readable: silently orphaning existing history on upgrade is a worse
    surprise than the status quo for data that predates the check.
    """
    from .session import session_owner

    session = storage.get(session_id)
    owner = session_owner(session)
    if owner and owner != caller:
        return None
    return session.model_dump() if session else None


def sessions_handler(storage: SessionStorage, caller: str | None = None) -> dict:
    """GET /sessions — the caller's own.

    This returned every conversation on the agent, to anyone who could reach
    the port (#683), and was where #696's attack got its session ids.
    """
    from .session import session_owner

    mine = [s for s in storage.list()
            if (session_owner(s) or caller) == caller]
    return {"sessions": [s.model_dump() for s in mine]}


def health_handler(agent_name: str, start_time: float) -> dict:
    """GET /health"""
    return {"status": "healthy", "agent": agent_name, "uptime": int(time.time() - start_time)}


def info_handler(agent_metadata: dict, trust, trust_config: dict | None = None,
                 host_config: dict | None = None) -> dict:
    """GET /info"""
    from ... import __version__
    from .config import DEFAULT_FILE_LIMITS

    file_config = host_config or DEFAULT_FILE_LIMITS

    # /info is unauthenticated: anyone who can reach the agent can read it, and on a
    # deployed agent that is the whole internet. Publish the same skill subset the
    # relay directory does, from the same constant, so the two answers to "what is
    # public" cannot drift apart. The operator's own toolboxes — user (~/.co/skills)
    # and claude-user (~/.claude/skills) — are not shipped with the agent and must not
    # be advertised by it; a full list here leaks which tools, SaaS accounts and
    # internal workflows the operator has on their machine.
    #
    # The complete list goes to authenticated clients over the WebSocket instead, in
    # the AGENT_PROFILE frame sent once CONNECT has passed the trust gate.
    from ...useful_plugins.skills import PUBLISHED_SKILL_LOCATIONS

    result = {
        "name": agent_metadata["name"],
        "address": agent_metadata["address"],
        "tools": agent_metadata["tools"],
        "model": agent_metadata.get("model", "unknown"),
        "trust": trust.trust,
        "version": __version__,
        "skills": [
            s for s in agent_metadata.get("skills", [])
            if s.get("location") in PUBLISHED_SKILL_LOCATIONS
        ],
        "accepted_inputs": {
            "text": True,
            "images": True,
            "files": {
                "max_file_size_mb": file_config.get("max_file_size", DEFAULT_FILE_LIMITS["max_file_size"]),
                "max_files_per_request": file_config.get(
                    "max_files_per_request",
                    DEFAULT_FILE_LIMITS["max_files_per_request"],
                ),
            },
        },
    }

    # The balance is deliberately not here. /info needs no credentials, so on a
    # deployed agent this response is readable by the whole internet, and the
    # operator's account balance is both commercially revealing on its own and a
    # targeting signal — credits are money, and an agent holding a lot of them is
    # worth more effort than one holding none.
    #
    # It still reaches authenticated clients: AGENT_PROFILE after CONNECT, and
    # the CONNECTED frame. That is where the chat UI reads it, and what
    # connectonion-react already documents — "the public /info answer is
    # deliberately narrower".

    # The same rule the CONNECT path applies, on this handler's own input.
    # Deciding it separately is how this came to publish an invite code that no
    # value opens: `trust_config` holds the *unexpanded* `$CO_INVITE_CODE`, so
    # `"invite_code" in onboard` was true on an agent with none set. /info needs
    # no credentials, so that answer went to the whole internet.
    from ..trust.ws_admin import doors_that_open

    offered = doors_that_open((trust_config or {}).get("onboard", {}),
                              trust.get_self_address()) if trust_config else None
    if offered:
        result["onboard"] = {
            "invite_code": "invite_code" in offered["methods"],
            "payment": offered.get("payment_amount"),
        }

    return result


def admin_logs_handler(log_path) -> dict:
    """GET /admin/logs

    Takes the path, not a name to rebuild one from. It used to take the agent's
    display name, which is host.yaml's name and not the Agent's -- so it looked
    for a file the logger never writes. `Logger(log=...)` was unreachable too,
    whatever the names.
    """
    log_path = Path(log_path)
    if log_path.exists():
        return {"content": log_path.read_text(encoding="utf-8")}
    return {"error": "No logs found"}


def admin_sessions_handler() -> dict:
    """GET /admin/sessions"""
    import yaml
    sessions_dir = project_co_dir() / "evals"
    if not sessions_dir.exists():
        return {"sessions": []}

    sessions = []
    for session_file in sessions_dir.glob("*.yaml"):
        with open(session_file, encoding="utf-8") as f:
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
    http=None,
):
    """Route HTTP requests to handler functions."""
    method, path = scope["method"], scope["path"]

    if method == "OPTIONS":
        headers = CORS_HEADERS + [[b"content-length", b"0"]]
        await send({"type": "http.response.start", "status": 204, "headers": headers})
        await send({"type": "http.response.body", "body": b""})
        return

    if http is not None:
        matched = http.match(method, path)
        if matched:
            from .http_routes import dispatch_http_route

            route, path_params = matched
            await dispatch_http_route(
                route, path_params, scope, receive, send,
                trust_agent=trust,
                recipient_address=route_handlers["agent_metadata"]["address"],
                blacklist=blacklist,
                whitelist=whitelist,
                replay_check=route_handlers.get("replay"),
            )
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
            result = route_handlers["input"](
                storage,
                prompt,
                session,
                images=images,
                files=files,
                requester_address=agent_address,
            )
        except ModeTransactionError as exc:
            status = 404 if exc.code == -32002 else 409 if exc.code == -32000 else 400
            body = {"error": exc.message, "code": exc.code}
            if exc.data:
                body["data"] = exc.data
            await send_json(send, body, status)
            return
        except ValueError as e:
            await send_json(send, {"error": str(e)}, 400)
            return
        await send_json(send, result)

    elif method == "GET" and (path == "/sessions" or path.startswith("/sessions/")):
        # Signed, like everything else that reads conversation content. A GET
        # has no body, so the signature is in headers over {method, path,
        # timestamp} and is verified by the same _authenticate_signed as every
        # other frame -- same freshness window, same blacklist (#683).
        from .auth import _authenticate_signed, request_from_headers

        headers = {k.decode(): v.decode() for k, v in scope.get("headers") or []}
        _, caller, err = _authenticate_signed(
            request_from_headers(headers, method, path), blacklist=blacklist)
        if err:
            await send_json(send, {"error": err},
                            401 if err.startswith("unauthorized") else 403)
            return

        if path == "/sessions":
            await send_json(send, route_handlers["sessions"](storage, caller))
        else:
            result = route_handlers["session"](storage, path[10:], caller)
            await send_json(send, result or {"error": "not found"},
                            404 if not result else 200)

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
