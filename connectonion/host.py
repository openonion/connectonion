"""Host an agent over HTTP/WebSocket.

Trust enforcement happens at the host level, not in the Agent.
This provides clean separation: Agent does work, host controls access.

Trust parameter accepts three forms:
1. Level (string): "open", "careful", "strict"
2. Policy (string): Natural language or file path
3. Agent: Custom Agent instance for verification

All forms create a trust agent behind the scenes.

Worker Isolation:
Each request gets a fresh deep copy of the agent template.
This ensures complete isolation - tools with state (like BrowserTool)
don't interfere between concurrent requests.
"""
import copy
import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel

from .asgi import create_app as asgi_create_app
from .trust import create_trust_agent, get_default_trust_level, TRUST_LEVELS


def get_default_trust() -> str:
    """Get default trust based on environment.

    Returns:
        Trust level based on CONNECTONION_ENV, defaults to 'careful'
    """
    return get_default_trust_level() or "careful"


# === Types ===

class Session(BaseModel):
    """Session record for tracking agent requests.

    Uses Pydantic BaseModel for:
    - Native JSON serialization via .model_dump()
    - Type validation
    - API response compatibility
    """
    session_id: str
    status: str
    prompt: str
    result: Optional[str] = None
    created: Optional[float] = None
    expires: Optional[float] = None
    duration_ms: Optional[int] = None


# === Storage ===

class SessionStorage:
    """JSONL file storage. Append-only, last entry wins."""

    def __init__(self, path: str = ".co/session_results.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(exist_ok=True)

    def save(self, session: Session):
        with open(self.path, "a") as f:
            f.write(session.model_dump_json() + "\n")

    def get(self, session_id: str) -> Session | None:
        if not self.path.exists():
            return None
        now = time.time()
        with open(self.path) as f:
            lines = f.readlines()
        for line in reversed(lines):
            data = json.loads(line)
            if data["session_id"] == session_id:
                session = Session(**data)
                # Return if running or not expired
                if session.status == "running" or not session.expires or session.expires > now:
                    return session
                return None  # Expired
        return None

    def list(self) -> list[Session]:
        if not self.path.exists():
            return []
        sessions = {}
        now = time.time()
        with open(self.path) as f:
            for line in f:
                data = json.loads(line)
                sessions[data["session_id"]] = Session(**data)
        # Filter out expired non-running sessions
        valid = [s for s in sessions.values()
                 if s.status == "running" or not s.expires or s.expires > now]
        # Sort by created desc (newest first)
        return sorted(valid, key=lambda s: s.created or 0, reverse=True)


# === Handlers (pure functions) ===

def input_handler(agent_template, storage: SessionStorage, prompt: str, result_ttl: int,
                  session: dict | None = None) -> dict:
    """POST /input

    Args:
        agent_template: The agent template (deep copied per request for isolation)
        storage: SessionStorage for persisting results
        prompt: The user's prompt
        result_ttl: How long to keep the result on server
        session: Optional conversation session for continuation
    """
    agent = copy.deepcopy(agent_template)
    now = time.time()

    # Get or generate session_id
    session_id = session.get('session_id') if session else None
    if not session_id:
        session_id = str(uuid.uuid4())
        # If session was provided but missing session_id, add it
        if session:
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


def health_handler(agent, start_time: float) -> dict:
    """GET /health"""
    return {"status": "healthy", "agent": agent.name, "uptime": int(time.time() - start_time)}


def info_handler(agent, trust: str) -> dict:
    """GET /info"""
    from . import __version__
    tools = agent.tools.list_names() if hasattr(agent.tools, "list_names") else []
    return {
        "name": agent.name,
        "address": get_agent_address(agent),
        "tools": tools,
        "trust": trust,
        "version": __version__,
    }


# === Auth Helpers ===

# Signature expiry window (5 minutes)
SIGNATURE_EXPIRY_SECONDS = 300


def verify_signature(payload: dict, signature: str, public_key: str) -> bool:
    """Verify Ed25519 signature.

    Args:
        payload: The payload that was signed
        signature: Hex-encoded signature (with or without 0x prefix)
        public_key: Hex-encoded public key (with or without 0x prefix)

    Returns:
        True if signature is valid, False otherwise
    """
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError

    # Remove 0x prefix if present
    sig_hex = signature[2:] if signature.startswith("0x") else signature
    key_hex = public_key[2:] if public_key.startswith("0x") else public_key

    # Canonicalize payload (deterministic JSON)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    try:
        verify_key = VerifyKey(bytes.fromhex(key_hex))
        verify_key.verify(canonical.encode(), bytes.fromhex(sig_hex))
        return True
    except (BadSignatureError, ValueError):
        # BadSignatureError: invalid signature
        # ValueError: invalid hex encoding
        return False


def extract_and_authenticate(data: dict, trust, *, blacklist=None, whitelist=None, agent_address=None):
    """Extract prompt and authenticate request.

    ALL requests must be signed - this is a protocol requirement.

    Required format (Ed25519 signed):
        {
            "payload": {"prompt": "...", "to": "0xAgentAddress", "timestamp": 123},
            "from": "0xCallerPublicKey",
            "signature": "0xEd25519Signature..."
        }

    Trust levels control additional policies AFTER signature verification:
        - "open": Any valid signer allowed
        - "careful": Warnings for unknown signers (default)
        - "strict": Whitelist only
        - Custom policy/Agent: LLM evaluation

    Returns: (prompt, identity, sig_valid, error)
    """
    # Protocol requirement: ALL requests must be signed
    if "payload" not in data or "signature" not in data:
        return None, None, False, "unauthorized: signed request required"

    # Verify signature (protocol level - always required)
    prompt, identity, error = _authenticate_signed(
        data, blacklist=blacklist, whitelist=whitelist, agent_address=agent_address
    )
    if error:
        return prompt, identity, False, error

    # Trust level: additional policies AFTER signature verification
    if trust == "strict" and whitelist and identity not in whitelist:
        return None, identity, True, "forbidden: not in whitelist"

    # Custom trust policy/agent evaluation
    if is_custom_trust(trust):
        trust_agent = create_trust_agent(trust)
        accepted, reason = evaluate_with_trust_agent(trust_agent, prompt, identity, True)
        if not accepted:
            return None, identity, True, f"rejected: {reason}"

    return prompt, identity, True, None


def _authenticate_signed(data: dict, *, blacklist=None, whitelist=None, agent_address=None):
    """Authenticate signed request with Ed25519 - ALWAYS REQUIRED.

    Protocol-level signature verification. All requests must be signed.

    Returns: (prompt, identity, error) - error is None on success
    """
    payload = data.get("payload", {})
    identity = data.get("from")
    signature = data.get("signature")

    prompt = payload.get("prompt", "")
    timestamp = payload.get("timestamp")
    to_address = payload.get("to")

    # Check blacklist first
    if blacklist and identity in blacklist:
        return None, identity, "forbidden: blacklisted"

    # Check whitelist (bypass signature check - trusted caller)
    if whitelist and identity in whitelist:
        return prompt, identity, None

    # Validate required fields
    if not identity:
        return None, None, "unauthorized: 'from' field required"
    if not signature:
        return None, identity, "unauthorized: signature required"
    if not timestamp:
        return None, identity, "unauthorized: timestamp required in payload"

    # Check timestamp expiry (5 minute window)
    now = time.time()
    if abs(now - timestamp) > SIGNATURE_EXPIRY_SECONDS:
        return None, identity, "unauthorized: signature expired"

    # Optionally verify 'to' matches agent address
    if agent_address and to_address and to_address != agent_address:
        return None, identity, "unauthorized: wrong recipient"

    # Verify signature
    if not verify_signature(payload, signature, identity):
        return None, identity, "unauthorized: invalid signature"

    return prompt, identity, None


def get_agent_address(agent) -> str:
    """Generate deterministic address from agent name."""
    h = hashlib.sha256(agent.name.encode()).hexdigest()
    return f"0x{h[:40]}"


def evaluate_with_trust_agent(trust_agent, prompt: str, identity: str, sig_valid: bool) -> tuple[bool, str]:
    """Evaluate request using a custom trust agent (policy or Agent).

    Only called when trust is a policy string or custom Agent - NOT for simple levels.

    Args:
        trust_agent: The trust agent created from policy or custom Agent
        prompt: The request prompt
        identity: The requester's identity/address
        sig_valid: Whether the signature is valid

    Returns:
        (accepted, reason) tuple
    """
    from pydantic import BaseModel
    from .llm_do import llm_do

    class TrustDecision(BaseModel):
        accept: bool
        reason: str

    request_info = f"""Evaluate this request:
- prompt: {prompt[:200]}{'...' if len(prompt) > 200 else ''}
- identity: {identity or 'anonymous'}
- signature_valid: {sig_valid}"""

    decision = llm_do(
        request_info,
        output=TrustDecision,
        system_prompt=trust_agent.system_prompt,
    )
    return decision.accept, decision.reason


def is_custom_trust(trust) -> bool:
    """Check if trust needs a custom agent (policy or Agent, not a level)."""
    if not isinstance(trust, str):
        return True  # It's an Agent
    return trust not in TRUST_LEVELS  # It's a policy string


# === Admin Handlers ===

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
    sessions_dir = Path(".co/sessions")
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


# === Entry Point ===

def _create_handlers(agent_template, result_ttl: int):
    """Create handler dict for ASGI app."""
    def ws_input(prompt: str) -> str:
        agent = copy.deepcopy(agent_template)
        return agent.input(prompt)

    return {
        "input": lambda storage, prompt, ttl, session=None: input_handler(agent_template, storage, prompt, ttl, session),
        "session": session_handler,
        "sessions": sessions_handler,
        "health": lambda start_time: health_handler(agent_template, start_time),
        "info": lambda trust: info_handler(agent_template, trust),
        "auth": extract_and_authenticate,
        "ws_input": ws_input,
        # Admin endpoints (auth required via OPENONION_API_KEY)
        "admin_logs": lambda: admin_logs_handler(agent_template.name),
        "admin_sessions": admin_sessions_handler,
    }


def _start_relay_background(agent_template, relay_url: str, addr_data: dict):
    """Start relay connection in background thread.

    The relay connection runs alongside the HTTP server, allowing the agent
    to be discovered via P2P network while also serving HTTP requests.
    """
    import asyncio
    import threading
    from . import announce, relay

    # Create ANNOUNCE message
    summary = agent_template.system_prompt[:1000] if agent_template.system_prompt else f"{agent_template.name} agent"
    announce_msg = announce.create_announce_message(addr_data, summary, endpoints=[])

    # Task handler - deep copy for each request
    async def task_handler(prompt: str) -> str:
        agent = copy.deepcopy(agent_template)
        return agent.input(prompt)

    async def relay_loop():
        ws = await relay.connect(relay_url)
        await relay.serve_loop(ws, announce_msg, task_handler)

    def run():
        asyncio.run(relay_loop())

    thread = threading.Thread(target=run, daemon=True, name="relay-connection")
    thread.start()
    return thread


def host(
    agent,
    port: int = None,
    trust: Union[str, "Agent"] = "careful",
    result_ttl: int = 86400,
    workers: int = 1,
    reload: bool = False,
    *,
    relay_url: str = "wss://oo.openonion.ai/ws/announce",
    blacklist: list | None = None,
    whitelist: list | None = None,
):
    """
    Host an agent over HTTP/WebSocket with optional P2P relay discovery.

    Args:
        agent: Agent to host
        port: HTTP port (default: PORT env var or 8000)
        trust: Trust level, policy, or Agent:
            - Level: "open", "careful", "strict"
            - Policy: Natural language or file path
            - Agent: Custom trust agent
        result_ttl: How long to keep results on server in seconds (default 24h)
        workers: Number of worker processes
        reload: Auto-reload on code changes
        relay_url: P2P relay URL (default: production relay)
            - Set to None to disable relay
        blacklist: Blocked identities
        whitelist: Allowed identities

    Endpoints:
        POST /input         - Submit prompt, get result
        GET  /sessions/{id} - Get session by ID
        GET  /sessions      - List all sessions
        GET  /health        - Health check
        GET  /info          - Agent info
        WS   /ws            - WebSocket
        GET  /logs          - Activity log (requires OPENONION_API_KEY)
        GET  /logs/sessions - Activity sessions (requires OPENONION_API_KEY)
    """
    import uvicorn
    from . import address

    # Use PORT env var if port not specified (for container deployments)
    if port is None:
        port = int(os.environ.get("PORT", 8000))

    # Load or generate agent identity
    co_dir = Path.cwd() / '.co'
    addr_data = address.load(co_dir)

    if addr_data is None:
        addr_data = address.generate()
        address.save(addr_data, co_dir)

    agent_address = addr_data['address']

    storage = SessionStorage()
    handlers = _create_handlers(agent, result_ttl)
    app = asgi_create_app(
        handlers=handlers,
        storage=storage,
        trust=trust,
        result_ttl=result_ttl,
        blacklist=blacklist,
        whitelist=whitelist,
    )

    # Start relay connection in background (if enabled)
    if relay_url:
        _start_relay_background(agent, relay_url, addr_data)

    # Display startup info
    relay_status = f"[green]✓[/] {relay_url}" if relay_url else "[dim]disabled[/]"
    Console().print(Panel(
        f"[bold]POST[/] http://localhost:{port}/input\n"
        f"[dim]GET  /sessions/{{id}} · /sessions · /health · /info[/]\n"
        f"[dim]WS   ws://localhost:{port}/ws\n"
        f"[dim]UI   http://localhost:{port}/docs[/]\n\n"
        f"[bold]Address:[/] {agent_address}\n"
        f"[bold]Relay:[/]   {relay_status}",
        title=f"[green]Agent '{agent.name}'[/]"
    ))

    uvicorn.run(app, host="0.0.0.0", port=port, workers=workers, reload=reload, log_level="warning")


# === Export ASGI App ===

def _make_app(agent, trust: Union[str, "Agent"] = "careful", result_ttl=86400, *, blacklist=None, whitelist=None):
    """Create ASGI app for external uvicorn/gunicorn usage.

    Args:
        agent: Agent to host
        trust: Trust level, policy, or Agent
        result_ttl: How long to keep results on server in seconds
        blacklist: Blocked identities
        whitelist: Allowed identities

    Usage:
        # myagent.py
        from connectonion import Agent, host
        agent = Agent("translator", tools=[translate])
        app = host.app(agent)

        # Then run with:
        # uvicorn myagent:app --workers 4
    """
    storage = SessionStorage()
    handlers = _create_handlers(agent, result_ttl)
    return asgi_create_app(
        handlers=handlers,
        storage=storage,
        trust=trust,
        result_ttl=result_ttl,
        blacklist=blacklist,
        whitelist=whitelist,
    )


# Attach app factory to host function
host.app = _make_app


# Backward-compatible create_app (use host.app() for new code)
def create_app_compat(agent, storage, trust="careful", result_ttl=86400, *, blacklist=None, whitelist=None):
    """Create ASGI app (backward-compatible wrapper).

    Prefer using host.app(agent) for new code.
    """
    handlers = _create_handlers(agent, result_ttl)
    return asgi_create_app(
        handlers=handlers,
        storage=storage,
        trust=trust,
        result_ttl=result_ttl,
        blacklist=blacklist,
        whitelist=whitelist,
    )


# Re-export for backward compatibility
create_app = create_app_compat
