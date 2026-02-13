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

from functools import partial
from pathlib import Path
from typing import Callable, Union

from rich.console import Console

from ..asgi import create_app as asgi_create_app
from ..trust import TrustAgent, get_default_trust_level, parse_policy, TRUST_LEVELS
from ..trust.factory import PROMPTS_DIR
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
    # Admin trust routes
    admin_trust_promote_handler,
    admin_trust_demote_handler,
    admin_trust_block_handler,
    admin_trust_unblock_handler,
    admin_trust_level_handler,
    # Super admin routes
    admin_admins_add_handler,
    admin_admins_remove_handler,
)


def _parse_trust_config(trust: Union[str, "Agent"]) -> dict | None:
    """Parse trust config from trust parameter.

    Returns YAML config dict if trust is a level or file path, None otherwise.
    Used to extract onboard info for /info endpoint.
    """
    if not isinstance(trust, str):
        return None

    # Check if it's a trust level
    if trust.lower() in TRUST_LEVELS:
        policy_path = PROMPTS_DIR / f"{trust.lower()}.md"
        if policy_path.exists():
            config, _ = parse_policy(policy_path.read_text(encoding='utf-8'))
            return config
        return None

    # Check if it's a file path
    path = Path(trust)
    if path.exists() and path.is_file():
        config, _ = parse_policy(path.read_text(encoding='utf-8'))
        return config

    # Inline policy text
    if trust.startswith('---'):
        config, _ = parse_policy(trust)
        return config

    return None


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


def _create_route_handlers(create_agent: Callable, agent_metadata: dict, result_ttl: int, trust_agent):
    """Create route handler dict for ASGI app.

    Args:
        create_agent: Factory function that returns a fresh Agent instance.
                      Called once per request for isolation.
        agent_metadata: Pre-extracted metadata (name, tools, address) - avoids
                        creating agents for health/info endpoints.
        result_ttl: How long to keep results on server in seconds
        trust_agent: TrustAgent instance for trust operations
    """
    agent_name = agent_metadata["name"]

    def handle_input(storage, prompt, session=None, connection=None, images=None):
        return input_handler(create_agent, storage, prompt, result_ttl, session, connection, images)

    def handle_ws_input(storage, prompt, connection, session=None, images=None):
        return input_handler(create_agent, storage, prompt, result_ttl, session, connection, images)

    def handle_health(start_time):
        return health_handler(agent_name, start_time)

    def handle_info(trust, trust_config=None):
        return info_handler(agent_metadata, trust, trust_config)

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
        # TrustAgent instance for direct access in http.py/websocket.py
        "trust_agent": trust_agent,
        # Admin trust routes (partial injects trust_agent as first arg)
        "admin_trust_promote": partial(admin_trust_promote_handler, trust_agent),
        "admin_trust_demote": partial(admin_trust_demote_handler, trust_agent),
        "admin_trust_block": partial(admin_trust_block_handler, trust_agent),
        "admin_trust_unblock": partial(admin_trust_unblock_handler, trust_agent),
        "admin_trust_level": partial(admin_trust_level_handler, trust_agent),
        # Super admin routes
        "admin_admins_add": partial(admin_admins_add_handler, trust_agent),
        "admin_admins_remove": partial(admin_admins_remove_handler, trust_agent),
    }


def _print_host_banner(
    port: int,
    address: str,
    relay_url: str | None,
    trust: str,
    trust_config: dict | None,
    co_dir: Path = None,
):
    """Print clean host startup banner focused on server info.

    Agent info (name, model, tools, balance) is shown by Agent's print_banner().
    Host banner only shows: URL, endpoints, address, relay, trust/invite.
    """
    console = Console()
    base_url = f"http://localhost:{port}"
    prefix = "[magenta]\\[host][/magenta]"
    indent = "       "  # 7 spaces to align with [host]

    # Build relay status
    relay_status = "[green]✓[/green] relay" if relay_url else "[dim]no relay[/dim]"

    # Header with [host] prefix
    console.print()
    console.print(f"{prefix} [dim]{'─' * 35}[/dim]")
    console.print(f"{indent}[cyan]{base_url}[/cyan]")
    console.print(f"{indent}[bold]POST[/bold] /input · [bold]WS[/bold] /ws · [dim]GET /docs[/dim]")
    console.print()

    # Full address + clickable chat link hint
    chat_url = f"https://chat.openonion.ai/{address}"
    console.print(f"{indent}[cyan]{address}[/cyan]")
    console.print(f"{indent}[link={chat_url}][dim]↳ chat.openonion.ai ↗[/dim][/link]")
    console.print(f"{indent}{relay_status}")
    console.print(f"{indent}[dim]{co_dir}[/dim]")

    # Trust/Invite (belongs to host layer)
    if trust_config and isinstance(trust, str) and trust.lower() in TRUST_LEVELS:
        onboard = trust_config.get("onboard", {})
        invite_codes = onboard.get("invite_code", [])
        if invite_codes:
            codes = invite_codes if isinstance(invite_codes, list) else [invite_codes]
            codes_str = ", ".join(codes)
            console.print(f"{indent}[bold yellow]Invite: {codes_str}[/bold yellow]")

    console.print()


def _create_relay_lifespan(create_agent: Callable, relay_url: str, addr_data: dict, summary: str, port: int):
    """Create relay startup/shutdown callbacks for ASGI lifespan.

    The relay connection runs in uvicorn's event loop alongside HTTP/WebSocket,
    allowing the agent to be discovered via P2P network.

    Args:
        create_agent: Factory function that returns a fresh Agent instance
        relay_url: WebSocket URL for P2P relay
        addr_data: Agent address data (public key, address)
        summary: Summary text for relay announcement
        port: HTTP port for endpoint discovery

    Returns:
        Tuple of (on_startup, on_shutdown) async callbacks
    """
    import asyncio
    from .. import announce, relay

    console = Console()
    host_prefix = "[magenta]\\[host][/magenta]"

    # State shared between startup and shutdown
    relay_task = None

    async def on_startup():
        nonlocal relay_task

        # Discover endpoints and create ANNOUNCE message
        endpoints = announce.get_endpoints(port)
        announce_msg = announce.create_announce_message(addr_data, summary, endpoints=endpoints, relay=relay_url)

        # Task handler - fresh instance for each request
        # Runs agent.input() in thread pool to avoid blocking event loop
        async def task_handler(prompt: str) -> str:
            agent = create_agent()
            # Run synchronous agent.input() in thread pool
            return await asyncio.to_thread(agent.input, prompt)

        async def relay_loop():
            while True:
                try:
                    ws = await relay.connect(relay_url)
                    # Relay status shown in banner - no log needed on first connect
                    await relay.serve_loop(ws, announce_msg, task_handler, addr_data=addr_data)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    console.print(f"{host_prefix} [yellow]Relay error: {e}, reconnecting...[/yellow]")
                    await asyncio.sleep(5)

        # Start relay as background task in same event loop
        relay_task = asyncio.create_task(relay_loop())

    async def on_shutdown():
        nonlocal relay_task
        if relay_task:
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                pass

    return on_startup, on_shutdown


def host(
    create_agent: Callable,
    port: int = None,
    trust: Union[str, "Agent"] = None,
    result_ttl: int = None,
    workers: int = None,
    reload: bool = None,
    *,
    relay_url: str = None,
    blacklist: list | None = None,
    whitelist: list | None = None,
    co_dir: Path = None,
    summary: str = None,
    examples: list = None,
):
    """
    Host an agent over HTTP/WebSocket with optional P2P relay discovery.

    Configuration: .co/host.yaml (required) with code param overrides.
    Run 'co init' to generate the config file.

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
        port: HTTP port (default: 8000 or from .co/host.yaml)
        trust: Trust level, policy, or Agent (default: from .co/host.yaml or "careful")
            - Level: "open", "careful", "strict"
            - Policy: Natural language or file path
            - Agent: Custom trust agent
        result_ttl: How long to keep results in seconds (default: 86400 or from config)
        workers: Number of worker processes (default: 1 or from config)
        reload: Auto-reload on code changes (default: False or from config)
        relay_url: P2P relay URL (default: wss://oo.openonion.ai or from config)
            - Set to None to disable relay
        blacklist: Blocked identities (default: from .co/blacklist.txt)
        whitelist: Allowed identities (default: from .co/whitelist.txt)
        co_dir: Path to .co directory for agent identity (default: ~/.co/)
        summary: Agent description (default: from config or agent.system_prompt)
        examples: Example prompts (default: from config or auto-generated)

    Endpoints:
        POST /input          - Submit prompt, get result
        GET  /sessions/{id}  - Get session by ID
        GET  /sessions       - List all sessions
        GET  /health         - Health check
        GET  /info           - Agent info (includes summary, examples)
        WS   /ws             - WebSocket
        GET  /admin/logs     - Activity log (requires OPENONION_API_KEY)
        GET  /admin/sessions - Activity sessions (requires OPENONION_API_KEY)
    """
    import uvicorn
    from ... import address
    from .config import load_host_config, load_list_file

    # Resolve co_dir: explicit > cwd/.co (project default)
    if co_dir is None:
        co_dir = Path.cwd() / '.co'

    # Load config: host.yaml (optional) → code param overrides
    config = load_host_config(
        co_dir,
        port=port, trust=trust, result_ttl=result_ttl,
        workers=workers, reload=reload, relay_url=relay_url,
        summary=summary, examples=examples,
    )

    # Extract final values from config
    port = config.get('port', 8000)
    trust = config.get('trust', 'careful')
    result_ttl = config.get('result_ttl', 86400)
    workers = config.get('workers', 1)
    reload = config.get('reload', False)
    relay_url = config.get('relay_url')
    summary = config.get('summary')
    examples = config.get('examples')

    # Extract metadata once at startup
    agent_metadata, sample = _extract_agent_metadata(create_agent)

    # Auto-generate summary from system_prompt if not set
    if summary is None:
        summary = sample.system_prompt[:1000] if sample.system_prompt else f"{agent_metadata['name']} agent"

    agent_metadata['summary'] = summary
    agent_metadata['examples'] = examples

    # Load whitelist/blacklist: code param (list) takes priority, else load from YAML file path
    if whitelist is None:
        whitelist = load_list_file(config.get('whitelist'))

    if blacklist is None:
        blacklist = load_list_file(config.get('blacklist'))

    # Load or generate agent identity
    addr_data = address.load(co_dir)

    if addr_data is None:
        addr_data = address.generate()
        address.save(addr_data, co_dir)

    agent_metadata["address"] = addr_data['address']

    storage = SessionStorage()

    # Create TrustAgent instance - the single interface for all trust operations
    # Users can subclass TrustAgent to customize (e.g., database-backed admin storage)
    if isinstance(trust, TrustAgent):
        trust_agent = trust
    else:
        trust_agent = TrustAgent(trust if isinstance(trust, str) else "careful")

    route_handlers = _create_route_handlers(create_agent, agent_metadata, result_ttl, trust_agent)

    # Parse trust config for /info onboard info
    trust_config = _parse_trust_config(trust)

    # Create relay lifespan callbacks (runs in same event loop as HTTP/WebSocket)
    on_startup, on_shutdown = None, None
    if relay_url:
        on_startup, on_shutdown = _create_relay_lifespan(
            create_agent, relay_url, addr_data, summary, port
        )

    app = asgi_create_app(
        route_handlers=route_handlers,
        storage=storage,
        trust=trust_agent,  # Pass resolved TrustAgent, not raw trust
        trust_config=trust_config,
        blacklist=blacklist,
        whitelist=whitelist,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
    )

    # Display host startup banner (agent info shown separately by Agent class)
    _print_host_banner(
        port=port,
        address=agent_metadata["address"],
        relay_url=relay_url,
        trust=trust,
        trust_config=trust_config,
        co_dir=co_dir,
    )

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

    # Create TrustAgent instance
    if isinstance(trust, TrustAgent):
        trust_agent = trust
    else:
        trust_agent = TrustAgent(trust if isinstance(trust, str) else "careful")

    route_handlers = _create_route_handlers(create_agent, agent_metadata, result_ttl, trust_agent)
    return asgi_create_app(
        route_handlers=route_handlers,
        storage=storage,
        trust=trust_agent,  # Pass resolved TrustAgent, not raw trust
        blacklist=blacklist,
        whitelist=whitelist,
    )
