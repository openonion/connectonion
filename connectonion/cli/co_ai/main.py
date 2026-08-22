"""
LLM-Note: Entry point for 'co ai' command - starts ConnectOnion AI coding agent web server.

This file provides the `start_server()` function that:
- Hosts a provided coding agent via connectonion.host() on specified port
- Opens web chat at chat.openonion.ai with agent address
- Loads global API keys from ~/.co/keys.env

Architecture:
- Uses one hosted coding agent for the web chat session
- Trust level set to "careful" for web deployment
- Host-acknowledged modes for network sessions

Used by:
- CLI command: `co ai` (see cli/main.py)
- Web chat interface at chat.openonion.ai
"""

import logging
import os
import threading
import time
import webbrowser
from contextlib import contextmanager
from pathlib import Path

from dotenv import dotenv_values

from connectonion import address, host

logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(name)s: %(message)s")


# Note: .env files already loaded by __init__.py with fallback chain:
# 1. Current directory .env
# 2. Global ~/.co/keys.env
# No need to load again here (load_dotenv doesn't override existing env vars)


@contextmanager
def _owner_invite_lock(co_dir: Path):
    """Serialize the one-time invite mint across simultaneous ``co ai`` starts."""
    co_dir.mkdir(parents=True, exist_ok=True)
    lock_path = co_dir / "owner-invite.lock"
    with lock_path.open("a+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            lock_path.chmod(0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _ensure_owner_invite(co_dir: Path) -> bool:
    """Load or mint the private invite used by the careful onboarding policy.

    The process environment wins because it may have come from the current
    project's ``.env``. Otherwise the global value is loaded into this process
    (dotenv loading happened before ``co ai`` reached this module), or one is
    minted once and written with owner-only permissions.
    """
    if os.environ.get("CO_INVITE_CODE"):
        return False

    from ..commands.project_cmd_lib import mint_invite_code, upsert_env

    with _owner_invite_lock(co_dir):
        keys_env = co_dir / "keys.env"
        existing = dotenv_values(keys_env, interpolate=False).get("CO_INVITE_CODE")
        if existing:
            os.environ["CO_INVITE_CODE"] = existing
            return False

        invite = mint_invite_code()
        upsert_env(keys_env, {"CO_INVITE_CODE": invite})
        os.environ["CO_INVITE_CODE"] = invite
        return True


def _prepare_owner_onboarding(co_dir: Path) -> bool:
    """Ensure the global identity and its private owner invite exist."""
    from ..commands.project_cmd_lib import ensure_global_config

    ensure_global_config()
    return _ensure_owner_invite(co_dir)


def start_server(
    agent,
    port: int = 8000,
    *,
    model: str | None = None,
    max_iterations: int | None = None,
    full_access: bool = False,
    full_access_turns: int = 100,
    agent_factory=None,
    invite_code: str = None,
):
    """Start AI coding agent web server.

    Args:
        agent: Agent instance to host
        port: Port to run server on
        model: Model used by the hosted coding agent
        max_iterations: Tool iteration limit for the hosted coding agent
        full_access: Whether bounded Full access is configured
        full_access_turns: User-driven turns before Full access expires
        agent_factory: Reserved configured factory for hosted sessions
        invite_code: Optional in-memory invite for this server invocation

    The server will be accessible at:
    - POST http://localhost:{port}/input
    - WS ws://localhost:{port}/ws
    - GET http://localhost:{port}/health
    - GET http://localhost:{port}/info
    """
    from ...network.host.config import load_host_config

    # Use global ~/.co/ for consistent identity across all co ai sessions.
    co_dir = Path.home() / ".co"
    if invite_code is None and _prepare_owner_onboarding(co_dir):
        from ..commands.project_cmd_lib import console

        console.print(
            "[green]Owner invite created.[/green] Run [bold]co keys --reveal[/bold] when onboarding your client."
        )
    elif invite_code is not None:
        from ..commands.project_cmd_lib import ensure_global_config

        ensure_global_config()
    load_host_config(co_dir)
    addr_data = address.load(co_dir)

    if full_access:
        from ...useful_plugins.full_access import offer_full_access

        # Web sessions still begin in Auto. This configures only the Host-owned
        # ceiling that makes Full access selectable after CONNECT.
        offer_full_access(agent, full_access_turns)

    # Open chat URL after agent successfully starts (2 second delay)
    if addr_data:

        def open_chat_delayed():
            time.sleep(2)
            webbrowser.open(f"https://chat.openonion.ai/{addr_data['address']}")
        threading.Thread(target=open_chat_delayed, daemon=True).start()

    # The first-party browser speaks OIP over /ws. Native Codex and Claude Code
    # delegation stay inside the Agent as provider adapters.
    trust = "careful"
    if invite_code is not None:
        from ...network.trust import TrustAgent

        trust = TrustAgent("careful", invite_code=invite_code, co_dir=co_dir)
    host(agent, port=port, trust=trust, co_dir=co_dir)
