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
import sys
import threading
import time
import webbrowser
from contextlib import contextmanager
from pathlib import Path

from connectonion import address, host
from connectonion.environment import explicit_env_file, publish_values, read_env_file

logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(name)s: %(message)s")


# Package startup loads the selected global env; the CLI applies --env-file
# before entering this module. Working directory does not select credentials.


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

    The inherited process environment wins. Otherwise the selected value is loaded into this process
    (dotenv loading happened before ``co ai`` reached this module), or one is
    minted once and written with owner-only permissions.
    """
    if os.environ.get("CO_INVITE_CODE"):
        return False

    from ..commands.project_cmd_lib import mint_invite_code, upsert_env

    keys_env = explicit_env_file() or co_dir / "keys.env"
    with _owner_invite_lock(keys_env.parent):
        existing = read_env_file(keys_env).get("CO_INVITE_CODE")
        if existing:
            publish_values({"CO_INVITE_CODE": existing})
            return False

        invite = mint_invite_code()
        upsert_env(keys_env, {"CO_INVITE_CODE": invite})
        publish_values({"CO_INVITE_CODE": invite})
        return True


def _prepare_owner_onboarding(co_dir: Path) -> bool:
    """Ensure the global identity and its private owner invite exist."""
    from ..commands.project_cmd_lib import ensure_global_config

    ensure_global_config()
    return _ensure_owner_invite(co_dir)


def show_owner_card(agent_address: str, stream=None) -> None:
    """What the owner needs to connect: the address, the invite code, the link.

    Owner, 2026-09-29: on a fresh laptop `co ai` said "Owner invite created.
    Run co keys --reveal" and nothing else, so whoever set it up could not
    connect a client. The code is shown in the owner's own terminal. When
    stdout is not a terminal -- a deployed host, where stdout is the system
    log, readable by anyone on the box and kept with the logs -- it says where
    the code is instead of what it is.
    """
    stream = stream or sys.stdout
    invite = os.environ.get("CO_INVITE_CODE", "")
    lines = ["", "  Your agent is starting", f"  Address  {agent_address}"]
    if invite and stream.isatty():
        lines += [f"  Invite   {invite}   (give it only to people you let in)",
                  f"  Open     https://chat.openonion.ai/{agent_address}"]
    elif invite:
        lines += ["  Invite   run `co keys --reveal` to see it"]
    stream.write("\n".join(lines) + "\n\n")
    stream.flush()


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
    launch: bool = True,
):
    """Start AI coding agent web server.

    Args:
        agent: Agent instance to host
        port: Port to run server on
        model: Model used by the hosted coding agent
        max_iterations: Tool iteration limit for the hosted coding agent
        full_access: Whether bounded Full access is configured
        full_access_turns: User-driven turns before Full access expires
        agent_factory: Builds a fresh Agent per hosted request; preferred over `agent`
        invite_code: Optional in-memory invite for this server invocation

    The server will be accessible at:
    - POST http://localhost:{port}/input
    - WS ws://localhost:{port}/ws
    - GET http://localhost:{port}/health
    - GET http://localhost:{port}/info
    """
    # Use global ~/.co/ for consistent identity across all co ai sessions.
    from connectonion.project import selected_identity_dir

    from ...network.host.config import load_host_config
    co_dir = selected_identity_dir()
    if invite_code is None:
        _prepare_owner_onboarding(co_dir)
    else:
        from ..commands.project_cmd_lib import ensure_global_config

        ensure_global_config()
    config = load_host_config(co_dir)
    addr_data = address.load(co_dir)
    if invite_code is None and addr_data:
        show_owner_card(addr_data["address"])

    def configured(new_agent):
        if full_access:
            from ...useful_plugins.full_access import offer_full_access

            # Web sessions still begin in Auto. This configures only the Host-owned
            # ceiling that makes Full access selectable after CONNECT.
            offer_full_access(new_agent, full_access_turns)
        return new_agent

    # Each request gets an Agent built from scratch, so two sessions never
    # share one object's conversation state. The instance form is kept for
    # callers that pass no factory.
    if agent_factory is not None:
        def create():
            return configured(agent_factory(model, max_iterations, False, full_access_turns))
    else:
        agent = configured(agent)
        create = agent

    # Open chat URL after agent successfully starts (2 second delay)
    if addr_data and launch:

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
    if agent_factory is None:
        host(create, port=port, trust=trust, co_dir=co_dir, rem_root=Path.home() / ".co/rem")
        return

    from ...network.host.session import SessionStorage
    from ...network.host.session.mode import HostPermissionPolicy, ModeTransactionError
    from ...network.host.session.turn import input_handler
    from .session_watch import SessionBusy, SessionWatchRuntime, SessionWatchStore

    store = SessionWatchStore(co_dir)
    storage = SessionStorage(co_dir / "session_results.jsonl")
    storage.reconcile_interrupted()

    def session_agent():
        # Every hosted conversation still gets its own Agent (#1874); the
        # watch store is the one thing they share, so a watch registered in
        # one turn is visible to the runtime that calls the session back.
        created = create()
        created._watch_store = store
        return created

    def run_watch_turn(event):
        record = storage.get(event["session_id"])
        if record is None:
            raise ValueError("Watch target session no longer exists")
        requester = (record.session or {}).get("requester") or {}
        if requester.get("address") != event["owner"] or requester.get("level") != "admin":
            raise PermissionError("Watch target session owner changed")
        try:
            input_handler(
                session_agent, storage, event["content"],
                config.get("result_ttl", 86400), session=record.session,
                requester=requester,
                mode_policy=HostPermissionPolicy(
                    full_access_turns=full_access_turns if full_access else None),
                is_admin=True, watch_event=event["metadata"],
            )
        except ModeTransactionError as exc:
            if exc.code == -32000:
                raise SessionBusy() from exc
            raise

    runtime = SessionWatchRuntime(store, storage, run_watch_turn)

    from ...handoff import watch as handoff_watch
    handoff_stop = []

    async def start_watches():
        runtime.start()
        handoff_stop.append(handoff_watch.start())   # acceptances/questions on handoffs we sent

    async def stop_watches():
        runtime.stop()
        for stop in handoff_stop:
            stop.set()

    host(session_agent, port=port, trust=trust, co_dir=co_dir,
         rem_root=Path.home() / ".co/rem",
         on_agent_startup=start_watches, on_agent_shutdown=stop_watches)
