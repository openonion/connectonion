"""
LLM-Note: Entry point for 'co ai' command - starts ConnectOnion AI coding agent web server.

This file provides the `start_server()` function that:
- Creates a coding agent via agent.create_coding_agent()
- Hosts it via connectonion.host() on specified port
- Opens web chat at chat.openonion.ai with agent address
- Loads global API keys from ~/.co/keys.env

Architecture:
- Uses agent factory pattern for stateless agent creation
- Trust level set to "careful" for web deployment
- Auto-approve mode for web usage (no terminal prompts)

Used by:
- CLI command: `co ai` (see cli/main.py)
- Web chat interface at chat.openonion.ai
"""

import logging
import webbrowser
import threading
import time
from pathlib import Path
from dotenv import load_dotenv
from connectonion import host, address

logging.basicConfig(
    level=logging.WARNING,
    format='[%(levelname)s] %(name)s: %(message)s'
)


# Note: .env files already loaded by __init__.py with fallback chain:
# 1. Current directory .env
# 2. Global ~/.co/keys.env
# No need to load again here (load_dotenv doesn't override existing env vars)


def start_server(
    port: int = 8000,
    model: str = "co/claude-opus-4-5",
    max_iterations: int = 20,
):
    """Start AI coding agent web server.

    Args:
        port: Port to run server on
        model: LLM model to use
        max_iterations: Max tool iterations

    The server will be accessible at:
    - POST http://localhost:{port}/input
    - WS ws://localhost:{port}/ws
    - GET http://localhost:{port}/health
    - GET http://localhost:{port}/info
    """
    from .agent import create_coding_agent

    def agent_factory():
        return create_coding_agent(
            model=model,
            max_iterations=max_iterations,
            auto_approve=True,  # Always auto-approve in web mode
        )

    # Use global ~/.co/ for consistent identity across all co ai sessions
    co_dir = Path.home() / '.co'
    addr_data = address.load(co_dir)

    # Open chat URL after agent successfully starts (2 second delay)
    if addr_data:
        def open_chat_delayed():
            time.sleep(2)
            webbrowser.open(f"https://chat.openonion.ai/{addr_data['address']}")

        threading.Thread(target=open_chat_delayed, daemon=True).start()

    # Start server with same co_dir (relay enabled by default for web chat)
    host(agent_factory, port=port, trust="careful", co_dir=co_dir)
