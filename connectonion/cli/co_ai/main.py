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

import logging
import os
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
    agent_factory=None,
):
    """Start AI coding agent web server.

    Args:
        agent: Agent instance to host
        port: Port to run server on
        model: Model used by the hosted coding agent
        max_iterations: Tool iteration limit for the hosted coding agent
        yolo: Whether an administrator may select bounded Full access
        yolo_turns: Maximum Full access turns before a checkpoint
        agent_factory: Reserved configured factory for hosted sessions

    The server will be accessible at:
    - POST http://localhost:{port}/input
    - WS ws://localhost:{port}/ws
    - GET http://localhost:{port}/health
    - GET http://localhost:{port}/info
    """
    from ...network.host.config import load_host_config
    # Use global ~/.co/ for consistent identity across all co ai sessions.
    co_dir = Path.home() / ".co"
    _ensure_invite_code(co_dir)
    load_host_config(co_dir)
    addr_data = address.load(co_dir)

        # Open chat URL after agent successfully starts (2 second delay)
    if addr_data:

        def open_chat_delayed():
            time.sleep(2)
            webbrowser.open(f"https://chat.openonion.ai/{addr_data['address']}")

        threading.Thread(target=open_chat_delayed, daemon=True).start()

    # The first-party browser speaks OIP over /ws. Native Codex and Claude Code
    # delegation stay inside the Agent as provider adapters.
    host(agent, port=port, trust="careful", co_dir=co_dir)


def _ensure_invite_code(co_dir: Path) -> Path | None:
    """Provision one private, stable invite for a bare ``co ai`` installation."""
    if os.environ.get("CO_INVITE_CODE"):
        return None

    from ..commands.project_cmd_lib import mint_invite_code

    invite_file = co_dir / "co-ai-invite.env"
    co_dir.mkdir(parents=True, exist_ok=True)
    if invite_file.exists():
        line = invite_file.read_text(encoding="utf-8").strip()
        key, separator, code = line.partition("=")
        if key != "CO_INVITE_CODE" or not separator or not code:
            raise ValueError(f"Invalid co ai invite file: {invite_file}")
    else:
        code = mint_invite_code()
        invite_file.write_text(f"CO_INVITE_CODE={code}\n", encoding="utf-8")
        if os.name != "nt":
            invite_file.chmod(0o600)
        print(f"[co ai] Created a private invite code in {invite_file}")

    os.environ["CO_INVITE_CODE"] = code
    return invite_file
