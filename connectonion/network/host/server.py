"""
Purpose: Host agent as HTTP/WebSocket server with trust-based access control
LLM-Note:
  Dependencies: imports from [network/asgi/, network/trust/, network/host/session.py, network/host/auth.py, network/host/routes.py] | imported by [network/__init__.py as host()] | tested by [tests/network/test_host.py]
  Data flow: host(create_agent, port, trust) → _create_route_handlers() wraps all routes → asgi_create_app() creates FastAPI/Starlette app → uvicorn.run() starts server → each request calls create_agent() for fresh instance → executes via input_handler()/ws_input() → returns result + session | trust enforcement via extract_and_authenticate() at request boundary
  State/Effects: starts HTTP server on specified port | creates .co/logs/ directory | stores sessions in SessionStorage (in-memory with TTL) | optionally announces to relay server | each request gets fresh agent instance (no state bleeding)
  Integration: exposes host(create_agent, port=8000, trust=None, result_ttl=3600, relay_url=None) | creates ASGI app with routes: POST /input, GET /sessions, GET /sessions/{id}, GET /health, GET /info, WebSocket /ws, admin endpoints | trust accepts: "open"/"careful"/"strict" (level), markdown string (policy), or Agent (custom verifier)
  Performance: factory pattern creates fresh agent per request (thread-safe) | SessionStorage auto-expires old results via TTL | WebSocket supports real-time bidirectional I/O | relay connection runs in background thread
  Errors: trust errors return 401/403 via extract_and_authenticate() | missing sessions return None (404) | raises if port already in use
Host an agent over HTTP/WebSocket.

Trust enforcement happens at the host level, not in the Agent.
This provides clean separation: Agent does work, host controls access.

Trust parameter accepts three forms:
1. Level (string): "open", "careful", "strict"
2. Policy (string): Natural language or file path
3. Agent: Custom Agent instance for verification

All forms create a trust agent behind the scenes.

Worker Isolation:
Each request calls the create_agent factory to get a fresh agent instance.
This ensures complete isolation - tools with state (like BrowserTool)
don't interfere between concurrent requests.
"""

import os
from pathlib import Path
from typing import Callable, Union

from rich.console import Console
from rich.panel import Panel

from ..asgi import create_app as asgi_create_app
from ..trust import get_default_trust_level
from .session import SessionStorage
from .auth import extract_and_authenticate
from .routes import (
    input_handler,
    session_handler,
    sessions_handler,
    health_handler,
    info_handler,
    admin_logs_handler,
    admin_sessions_handler,
)


def get_default_trust() -> str:
    """Get default trust based on environment.

    Returns:
        Trust level based on CONNECTONION_ENV, defaults to 'careful'
    """
    return get_default_trust_level() or "careful"


def _extract_agent_metadata(create_agent: Callable) -> tuple[dict, object]:
    """Extract metadata from a sample agent instance.

    Returns:
        (metadata dict, sample_agent) - sample_agent for additional extraction
    """
    sample = create_agent()
    metadata = {
        "name": sample.name,
        "tools": sample.tools.names(),
    }
    return metadata, sample


def _create_route_handlers(create_agent: Callable, agent_metadata: dict, result_ttl: int):
    """Create route handler dict for ASGI app.

    Args:
        create_agent: Factory function that returns a fresh Agent instance.
                      Called once per request for isolation.
        agent_metadata: Pre-extracted metadata (name, tools, address) - avoids
                        creating agents for health/info endpoints.
        result_ttl: How long to keep results on server in seconds
    """
    agent_name = agent_metadata["name"]

    def handle_input(storage, prompt, session=None, connection=None):
        return input_handler(create_agent, storage, prompt, result_ttl, session, connection)

    def handle_ws_input(storage, prompt, connection, session=None):
        return input_handler(create_agent, storage, prompt, result_ttl, session, connection)

    def handle_health(start_time):
        return health_handler(agent_name, start_time)

    def handle_info(trust):
        return info_handler(agent_metadata, trust)

    def handle_admin_logs():
        return admin_logs_handler(agent_name)

    return {
        "input": handle_input,
        "session": session_handler,
        "sessions": sessions_handler,
        "health": handle_health,
        "info": handle_info,
        "auth": extract_and_authenticate,
        "ws_input": handle_ws_input,
        "admin_logs": handle_admin_logs,
        "admin_sessions": admin_sessions_handler,
    }


def _start_relay_background(create_agent: Callable, relay_url: str, addr_data: dict, agent_summary: str):
    """Start relay connection in background thread.

    The relay connection runs alongside the HTTP server, allowing the agent
    to be discovered via P2P network while also serving HTTP requests.

    Args:
        create_agent: Factory function that returns a fresh Agent instance
        relay_url: WebSocket URL for P2P relay
        addr_data: Agent address data (public key, address)
        agent_summary: Summary text for relay announcement
    """
    import asyncio
    import threading
    from .. import announce, relay

    # Create ANNOUNCE message
    announce_msg = announce.create_announce_message(addr_data, agent_summary, endpoints=[])

    # Task handler - fresh instance for each request
    # NOTE: agent.input() is synchronous inside async function, but this runs in
    # a separate thread with its own event loop (not uvicorn's). Only blocks the
    # relay thread, not the HTTP server. Could use asyncio.to_thread() if relay
    # needs concurrent task handling or heartbeat during execution.
    async def task_handler(prompt: str) -> str:
        agent = create_agent()
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
    create_agent: Callable,
    port: int = None,
    trust: Union[str, "Agent"] = "careful",
    result_ttl: int = 86400,
    workers: int = 1,
    reload: bool = False,
    *,
    relay_url: str = "wss://oo.openonion.ai",
    blacklist: list | None = None,
    whitelist: list | None = None,
):
    """
    Host an agent over HTTP/WebSocket with optional P2P relay discovery.

    Each request calls create_agent() to get a fresh Agent instance.
    This ensures complete isolation between concurrent requests.

    State Control via Closure:
        # Isolated state (default, safest) - create inside:
        def create_agent():
            browser = BrowserTool()  # Fresh per request
            return Agent("assistant", tools=[browser])

        # Shared state (advanced) - create outside, capture via closure:
        browser = BrowserTool()  # Shared across all requests
        def create_agent():
            return Agent("assistant", tools=[browser])

    Args:
        create_agent: Function that returns a fresh Agent instance.
                      Called once per request. Define tools inside for isolation,
                      or outside for shared state.
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
    from ... import address

    # Use PORT env var if port not specified (for container deployments)
    if port is None:
        port = int(os.environ.get("PORT", 8000))

    # Extract metadata once at startup
    agent_metadata, sample = _extract_agent_metadata(create_agent)
    agent_summary = sample.system_prompt[:1000] if sample.system_prompt else f"{agent_metadata['name']} agent"

    # Load or generate agent identity
    co_dir = Path.cwd() / '.co'
    addr_data = address.load(co_dir)

    if addr_data is None:
        addr_data = address.generate()
        address.save(addr_data, co_dir)

    agent_metadata["address"] = addr_data['address']

    storage = SessionStorage()
    route_handlers = _create_route_handlers(create_agent, agent_metadata, result_ttl)
    app = asgi_create_app(
        route_handlers=route_handlers,
        storage=storage,
        trust=trust,
        blacklist=blacklist,
        whitelist=whitelist,
    )

    # Start relay connection in background (if enabled)
    if relay_url:
        _start_relay_background(create_agent, relay_url, addr_data, agent_summary)

    # Display startup info
    relay_status = f"[green]✓[/] {relay_url}" if relay_url else "[dim]disabled[/]"
    Console().print(Panel(
        f"[bold]POST[/] http://localhost:{port}/input\n"
        f"[dim]GET  /sessions/{{id}} · /sessions · /health · /info[/]\n"
        f"[dim]WS   ws://localhost:{port}/ws\n"
        f"[dim]UI   http://localhost:{port}/docs[/]\n\n"
        f"[bold]Address:[/] {agent_metadata['address']}\n"
        f"[bold]Relay:[/]   {relay_status}",
        title=f"[green]Agent '{agent_metadata['name']}'[/]"
    ))

    uvicorn.run(app, host="0.0.0.0", port=port, workers=workers, reload=reload, log_level="warning")


def create_app(create_agent: Callable, storage=None, trust="careful", result_ttl=86400, *, blacklist=None, whitelist=None):
    """Create ASGI app for external uvicorn/gunicorn usage.

    Each request calls create_agent() to get a fresh Agent instance.

    Usage:
        from connectonion.network import create_app

        def create_agent():
            return Agent("assistant", tools=[search])

        app = create_app(create_agent)
        # uvicorn myagent:app --workers 4
    """
    from .auth import get_agent_address

    if storage is None:
        storage = SessionStorage()

    # Extract metadata once at startup
    agent_metadata, sample = _extract_agent_metadata(create_agent)
    agent_metadata["address"] = get_agent_address(sample)

    route_handlers = _create_route_handlers(create_agent, agent_metadata, result_ttl)
    return asgi_create_app(
        route_handlers=route_handlers,
        storage=storage,
        trust=trust,
        blacklist=blacklist,
        whitelist=whitelist,
    )
