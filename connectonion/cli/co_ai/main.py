"""
LLM-Note: Entry point for 'co ai' command - starts ConnectOnion AI coding agent web server.

This file provides the `start_server()` function that:
- Hosts a provided coding agent via connectonion.host() on specified port
- Opens web chat at chat.openonion.ai with agent address
- Loads global API keys from ~/.co/keys.env

Architecture:
- Uses one hosted coding agent for the web chat session
- Trust level set to "careful" for web deployment
- Host-acknowledged permission profiles for network sessions

Used by:
- CLI command: `co ai` (see cli/main.py)
- Web chat interface at chat.openonion.ai
"""

import hashlib
import logging
import threading
import time
import webbrowser
from pathlib import Path

from connectonion import address, host

logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(name)s: %(message)s")


# Note: .env files already loaded by __init__.py with fallback chain:
# 1. Current directory .env
# 2. Global ~/.co/keys.env
# No need to load again here (load_dotenv doesn't override existing env vars)


def start_server(
    agent,
    port: int = 8000,
    *,
    model: str | None = None,
    max_iterations: int | None = None,
    yolo: bool = False,
    yolo_turns: int = 100,
):
    """Start AI coding agent web server.

    Args:
        agent: Agent instance to host
        port: Port to run server on
        model: Model for per-connection ACP coding agents
        max_iterations: Tool iteration limit for ACP coding agents
        yolo: Whether an administrator may select bounded Full access
        yolo_turns: Maximum Full access turns before a checkpoint

    The server will be accessible at:
    - POST http://localhost:{port}/input
    - WS ws://localhost:{port}/ws
    - ACP WS ws://localhost:{port}/acp
    - GET http://localhost:{port}/health
    - GET http://localhost:{port}/info
    """
    from ...network.host.config import load_host_config
    from .acp_server import capture_network_workspace, create_acp_agent

    network_workspace = capture_network_workspace(Path.cwd())
    try:
        # Use global ~/.co/ for consistent identity across all co ai sessions
        co_dir = Path.home() / ".co"
        input_limits = load_host_config(co_dir)
        addr_data = address.load(co_dir)

        # Open chat URL after agent successfully starts (2 second delay)
        if addr_data:

            def open_chat_delayed():
                time.sleep(2)
                webbrowser.open(f"https://chat.openonion.ai/{addr_data['address']}")

            threading.Thread(target=open_chat_delayed, daemon=True).start()

        # ACP needs one isolated lifecycle adapter per authenticated connection.
        # @connectonion/react selects /acp from exact discovery; /ws remains the
        # bounded compatibility path only when that descriptor is absent. Both
        # doors share the host's signature and trust boundary.
        acp_model = model or getattr(getattr(agent, "llm", None), "model", None)
        acp_model = acp_model or "co/claude-opus-4-5"
        acp_max_iterations = max_iterations if max_iterations is not None else getattr(agent, "max_iterations", 100)

        def create_network_acp_agent(principal):
            # A session ID is a routing value, never a credential. Keep persistent
            # network sessions in a stable namespace selected only from the
            # authenticated connection principal so copied IDs cross no boundary.
            owner = "\0".join(
                (
                    "v1",
                    principal.recipient,
                    principal.address,
                    principal.origin or "",
                    principal.auth_method,
                    network_workspace.namespace_key,
                )
            )
            owner_id = hashlib.sha256(owner.encode("utf-8")).hexdigest()
            session_co_dir = co_dir / "acp-principals" / owner_id
            return create_acp_agent(
                model=acp_model,
                max_iterations=acp_max_iterations,
                # --yolo is an operator ceiling, not authority delegated to every
                # trusted remote caller. Only the authenticated administrator can
                # receive the Full access profile on this direct endpoint.
                yolo=yolo and principal.level == "admin",
                yolo_turns=yolo_turns,
                session_co_dir=session_co_dir,
                network_workspace=network_workspace,
                input_limits=input_limits,
            )

        # Start server with same co_dir (relay enabled by default for web chat).
        # co ai keeps one Agent instance so browser/tool state can persist across
        # continued inputs in the same local web server.
        host(
            agent,
            port=port,
            trust="careful",
            co_dir=co_dir,
            acp_agent_factory=create_network_acp_agent,
        )
    finally:
        network_workspace.close()
