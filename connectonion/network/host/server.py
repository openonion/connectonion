"""
Purpose: Host agent as HTTP/WebSocket server with trust-based access control
LLM-Note:
  Dependencies: imports from [network/asgi/, network/host/ws_router/ (run_ws_session), network/trust/, network/host/session/, network/host/auth.py, network/host/http_router.py, network/announce.py, network/relay.py] | imported by [network/__init__.py as host()] | tested by [tests/e2e/test_host.py]
  Data flow: host(create_agent, port, trust) → _create_route_handlers() wraps all routes → asgi_create_app() creates FastAPI/Starlette app → uvicorn.run() starts server → each request calls create_agent() for fresh instance → executes via input_handler()/ws_input() → returns result + session | trust enforcement via extract_and_authenticate() at request boundary
  State/Effects: starts HTTP server on specified port | creates .co/logs/ directory | stores sessions in SessionStorage (in-memory with TTL) | refreshes managed-key balance metadata every minute | optionally announces a display profile to the relay (alias/tools/model + project-level skills only — user/builtin skills stay private) | each request gets fresh agent instance (no state bleeding)
  Integration: exposes host(create_agent, port=8000, trust=None, result_ttl=3600, relay_url=UNSET) | omitted relay resolves from host.yaml then the shared backend selector | creates ASGI app with routes: POST /input, GET /sessions, GET /sessions/{id}, GET /health, GET /info, WebSocket /ws, admin endpoints | trust accepts: "open"/"careful"/"strict" (level), markdown string (policy), or Agent (custom verifier)
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

import asyncio
import random
from functools import partial
import os
from pathlib import Path
import json
from typing import Callable, Optional, Union

import uvicorn
import websockets
from rich.console import Console

from ... import address
from ...backend import DEFAULT_BACKEND_WS_URL
from .. import announce, relay
from ..asgi import create_app as asgi_create_app
from .ws_router import run_ws_session
from .schedule import create_schedule_lifespan
from ..trust import TrustAgent, parse_policy, TRUST_LEVELS
from ..trust.factory import PROMPTS_DIR
from .auth import authenticate_connect, extract_and_authenticate
from .replay import SignatureReplayStore
from .config import load_host_config, load_list_file, validate_files, validate_images, project_co_dir, DEFAULT_FILE_LIMITS
from .session import SessionStorage, ActiveSessionRegistry, start_cleanup_job
from .session.mode import HostPermissionPolicy
from .http_router import (
    input_handler,
    exec_handler,
    session_handler,
    sessions_handler,
    health_handler,
    info_handler,
    admin_logs_handler,
    admin_sessions_handler,
    admin_trust_promote_handler,
    admin_trust_demote_handler,
    admin_trust_block_handler,
    admin_trust_unblock_handler,
    admin_trust_level_handler,
    admin_admins_add_handler,
    admin_admins_remove_handler,
)
from .provider_workroom import prepare_provider_workroom_turn


EXEC_REQUIRES = ("admin", "whitelist", "contact")


def _make_ws_exec(create_agent, exec_permissions, trust_agent):
    """Direct tool execution, gated on who is asking as well as what they ask.

    EXEC used to take neither the caller's address nor their level:

        def handle_ws_exec(tool_name, args):
            return exec_handler(create_agent, exec_permissions, tool_name, args)

    while the INPUT handler beside it resolved both and carried them down. So
    the permission whitelist was the only gate, and any authenticated
    connection could run any whitelisted tool. #653 measured what that costs on
    default settings: a stranger submits an invite code, becomes a contact, and
    runs `whoami` as the operator. The session loop's comment said "Auth is the
    same gate as INPUT" -- the authentication was; the authorisation was not.

    EXEC is the terminal-style fast path: no LLM, no session, and no approval
    hook. It remains limited to the operator's server-side permission whitelist.
    An invite grants contact status, so a contact may use those pre-authorised
    tools just like an admin; it does not grant permission to anything absent
    from that whitelist.
    """
    def handle_ws_exec(tool_name, args, requester_address=None):
        if not requester_address:
            return {"status": "error",
                    "error": "forbidden: exec requires an authenticated caller"}

        level = ('admin' if trust_agent.is_admin(requester_address)
                 else trust_agent.get_level(requester_address))
        if level not in EXEC_REQUIRES:
            return {"status": "error",
                    "error": f"forbidden: exec requires a contact or admin, "
                             f"you are {level}"}

        return exec_handler(create_agent, exec_permissions, tool_name, args)

    return handle_ws_exec


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
            config, _ = parse_policy(policy_path.read_text(encoding='utf-8'),
                                     source=str(policy_path))
            return config
        return None

    # Check if it's a file path
    path = Path(trust)
    if path.exists() and path.is_file():
        config, _ = parse_policy(path.read_text(encoding='utf-8'), source=str(path))
        return config

    # Inline policy text
    if trust.startswith('---'):
        config, _ = parse_policy(trust)
        return config

    return None


def _extract_agent_metadata(create_agent: Callable,
                            name: Optional[str] = None) -> tuple[dict, object]:
    """Extract metadata from a sample agent instance.

    Returns:
        (metadata dict, sample_agent) - sample_agent for additional extraction
    """
    sample = create_agent()
    raw_skills = getattr(sample, 'skills', [])
    metadata = {
        # host.yaml's name, when it has one. The Agent object's name is whatever
        # the code that built it chose — the co-ai template hardcodes "oo" — so
        # every agent from that template introduced itself as "oo" on the relay,
        # in /info and in the directory, whatever the operator had named their
        # project. The name in host.yaml is the one they chose and the one the
        # deploy already uses for the directory, the unit and the hostname.
        "name": name or sample.name,
        "tools": sample.tools.names(),
        "model": sample.llm.model,
        "skills": [{"name": s.name, "description": s.description, "location": s.location}
                   for s in raw_skills],
    }
    # Managed-key (co/*) agents have an OpenOnion account balance; publish it so
    # chat clients can show the agent's balance. Clients can't fetch it themselves
    # — it's gated by the agent's private key — so the agent is the only party that
    # can report it. The lifespan refresher keeps this startup value current.
    # Agents on their own provider keys have no such balance, so get_balance is
    # absent and the field is simply omitted.
    get_balance = getattr(sample.llm, "get_balance", None)
    if callable(get_balance):
        balance = get_balance()
        if balance is not None:
            metadata["balance_usd"] = balance
    return metadata, sample


def _build_agent_profile(agent_metadata: dict) -> dict:
    """Build the publishable display profile sent with relay ANNOUNCEs.

    Carries display fields only — alias, tool names, model, and the names+descriptions
    of project-scoped skills. The operator's personal skills and builtin skills are
    filtered out. Skill bodies are never inlined here; subscribers fetch them by name
    from the relay.

    (The agent's prompt summary is broadcast separately via the top-level ANNOUNCE
    `summary` field — it is not part of this profile and not made private by it.)
    """
    profile = {"alias": agent_metadata["name"]}
    if agent_metadata.get("tools"):
        profile["tools"] = agent_metadata["tools"]
    if agent_metadata.get("model"):
        profile["model"] = agent_metadata["model"]
    # Refreshed balance for co/* managed-key agents (see _create_balance_lifespan).
    # Public for now — a later admin/subscriber tier can gate it.
    if agent_metadata.get("balance_usd") is not None:
        profile["balance_usd"] = agent_metadata["balance_usd"]
    # skill.location (useful_plugins/skills.py) is a 5-value discovery category. Publish
    # only the two that ship inside the project tree — project (.co/skills) and
    # claude-project (.claude/skills). user (~/.co/skills), claude-user (~/.claude/skills)
    # are the operator's personal toolboxes and builtin is framework noise; none may leak
    # into the public directory. Allowlist, so an unknown future category stays private.
    # Every client-facing skill list (this profile, the starter dashboard) draws from it,
    # so a dashboard button can't name a skill the client will refuse to run.
    from ...useful_plugins.skills import PUBLISHED_SKILL_LOCATIONS
    profile["skills"] = [
        {"name": s["name"], "description": s.get("description", "")}
        for s in agent_metadata.get("skills", [])
        if s.get("location") in PUBLISHED_SKILL_LOCATIONS
    ]
    return profile


def _create_route_handlers(
    create_agent: Callable,
    agent_metadata: dict,
    result_ttl: int,
    trust_agent,
    config: dict,
    exec_permissions: dict | None = None,
    replay_check=None,
    mode_policy: HostPermissionPolicy | None = None,
):
    """Create route handler dict for ASGI app.

    Args:
        create_agent: Factory function that returns a fresh Agent instance.
                      Called once per request for isolation.
        agent_metadata: Pre-extracted metadata (name, tools, address) - avoids
                        creating agents for health/info endpoints.
        result_ttl: How long to keep results on server in seconds
        trust_agent: TrustAgent instance for trust operations
        config: Host config dict (includes file upload limits)
        exec_permissions: The .co/host.yaml permission whitelist that gates WS
                          EXEC (direct tool execution). Same list the LLM
                          approval flow uses; empty dict → nothing runs directly.
        replay_check: Atomic one-use signature guard for this hosted project.
    """
    agent_name = agent_metadata["name"]
    exec_permissions = exec_permissions or {}
    mode_policy = mode_policy or HostPermissionPolicy()
    if replay_check is None:
        from .auth import signature_already_used
        replay_check = signature_already_used

    def requester_for(requester_address):
        if not requester_address:
            return None
        level = (
            "admin" if trust_agent.is_admin(requester_address)
            else trust_agent.get_level(requester_address)
        )
        requester = {'address': requester_address, 'level': level}
        return requester

    def handle_input(storage, prompt, session=None, connection=None, images=None,
                     files=None, requester_address=None):
        validate_files(files, config)
        validate_images(images, config)
        requester = requester_for(requester_address)
        return input_handler(
            create_agent, storage, prompt, result_ttl, session, connection,
            images, files, requester=requester, mode_policy=mode_policy,
            is_admin=bool(requester and requester["level"] == "admin"),
        )

    def handle_ws_input(storage, prompt, connection, session=None, images=None,
                        files=None, requester_address=None):
        validate_files(files, config)
        validate_images(images, config)
        # Resolved here, not carried in the session — see input_handler.
        # `admin` is not one of get_level's answers — it returns stranger /
        # contact / whitelist / blocked. The operator is whoever is in
        # .co/admins.txt, which is a separate question, and conflating them
        # would have refused the owner as loudly as everyone else.
        requester = requester_for(requester_address)
        return input_handler(create_agent, storage, prompt, result_ttl, session,
                             connection, images, files, requester=requester,
                             mode_policy=mode_policy,
                             is_admin=bool(requester and requester["level"] == "admin"))

    handle_ws_exec = _make_ws_exec(create_agent, exec_permissions, trust_agent)

    def handle_prepare_provider_workroom_turn(
        storage,
        session_id,
        invocation_id,
        text,
        request_id,
        requester_address,
    ):
        return prepare_provider_workroom_turn(
            create_agent,
            storage,
            session_id,
            invocation_id,
            text,
            request_id,
            requester_address,
            host_full_access_turns_ceiling=mode_policy.full_access_turns,
        )

    def handle_health(start_time):
        return health_handler(agent_name, start_time)

    def handle_info(trust, trust_config=None):
        return info_handler(agent_metadata, trust, trust_config, config)

    def handle_admin_logs():
        # Where the log actually is, asked of the logger that writes it. Rebuilt
        # from agent_metadata["name"] this looked for the *display* name --
        # host.yaml's, deliberately (see _extract_agent_metadata) -- while the
        # file is named after the Agent. `co init` makes those differ by default.
        return admin_logs_handler(create_agent().logger.log_file_path)

    return {
        "input": handle_input,
        "session": session_handler,
        "sessions": sessions_handler,
        "health": handle_health,
        "info": handle_info,
        "auth": extract_and_authenticate,
        "connect_auth": partial(authenticate_connect, replay_check=replay_check),
        "replay": replay_check,
        "ws_input": handle_ws_input,
        "ws_exec": handle_ws_exec,
        "prepare_provider_workroom_turn": handle_prepare_provider_workroom_turn,
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
        # Full metadata for the AGENT_PROFILE frame. /info and the relay directory are
        # unauthenticated and carry the published subset only; this is the copy a client
        # gets after CONNECT has passed the trust gate.
        "agent_metadata": agent_metadata,
        "result_ttl": result_ttl,
        "session_modes": mode_policy,
    }


def _host_mode_policy(sample) -> HostPermissionPolicy:
    """Capture only an explicitly configured positive Full access ceiling."""
    turns = getattr(sample, "_yolo_turns", None)
    if (
        isinstance(turns, bool)
        or not isinstance(turns, int)
        or turns <= 0
    ):
        turns = None
    return HostPermissionPolicy(full_access_turns=turns)


def resolve_agent_identity(co_dir: Path) -> dict:
    """The keypair this agent serves under — the same one `co status` reports.

    A project with no key of its own used to get two different answers. `co status`
    falls back to the machine's identity:

        co_dir = Path(".co")
        if not (co_dir.exists() and (co_dir / "keys" / "agent.key").exists()):
            co_dir = Path.home() / ".co"

    and this did not, so it minted a third one. Measured in a project created by
    1.5.x, whose `co init` pointed at the global ~/.co and wrote no local key:

        co status says   0x10e68f6dff39ab1c50cc48ea…
        host served as   0x3910103910d99954443e42a3…

    The operator reads one address, hands it out, and nothing reaches the agent.
    The project's identity changes on the way past, too: whatever was whitelisted
    or announced under the configured address is now somebody else.

    Generating stays for a machine with no identity at all — an agent has to have
    an address. What goes is inventing one while a configured identity sits unused.
    """
    own = address.load(co_dir)
    if own:
        return own

    inherited = address.load(Path.home() / ".co")
    if inherited:
        return inherited

    fresh = address.generate()
    address.save(fresh, co_dir)
    return fresh


SERVED_BY_FILE = "served_by.json"


def claim_identity(co_dir: Path, identity: dict, name: str) -> Optional[str]:
    """Record that this agent serves under this key, or say who already does.

    One address, one agent. #642 caught two of them sharing `0x10e68f6d…` —
    `oo` on this laptop with bash and write, and `naturewill` on the deployed
    box with the contract-ledger tools — because every 1.5.x `co init` wrote
    `AGENT_CONFIG_PATH=~/.co` and a project with no key of its own inherits the
    global one on purpose. Since #643 a client resolves an endpoint directly
    and picks by proximity, so a call meant for the deployed agent reaches the
    local coding agent instead. `/info` verification cannot catch that: the
    address genuinely matches.

    The record goes beside the key rather than in the project, because the
    whole problem is several projects sharing one identity directory.

    Returns a warning, not a refusal. The agent whose address this is may be
    the one restarting, and an operator who cannot start their agent because of
    a stale claim is worse off than one who is told the truth. `co deploy` is
    where refusing belongs — that is the moment a second permanent copy is
    made.
    """
    source = Path(identity.get("source") or co_dir)
    if not source.is_dir():
        # A freshly generated identity is saved into a directory that may not
        # exist yet, and a hint about who is serving is not worth failing a
        # start over. No directory, no claim, no warning.
        return None
    record = source / SERVED_BY_FILE
    mine = {"name": name, "project": str(co_dir.parent), "address": identity["address"]}

    existing = None
    if record.exists():
        try:
            existing = json.loads(record.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # A warning aid, not a gate. An unreadable record costs a warning,
            # not a start.
            existing = None

    record.write_text(json.dumps(mine, indent=2), encoding="utf-8")

    if not existing or existing.get("project") == mine["project"]:
        return None       # nobody else, or the same project restarting/renamed

    # Only advice that works. Saying "point AGENT_CONFIG_PATH at this project's
    # .co" would be wrong for the case that produces this warning: the project
    # has no key there, which is why it inherited one. Nothing today mints a
    # local identity for a project that already exists — that gap is what makes
    # this a warning rather than a refusal, and it is filed separately.
    return (
        f"{identity['address'][:10]}… is already served by "
        f"'{existing.get('name')}' in {existing.get('project')}, using the same "
        f"key from {source}. Two agents on one address means whichever is "
        f"nearest answers the call, and the tools they answer with differ. A "
        f"project created by `co create` gets its own identity and does not "
        f"share."
    )


def usable_uvicorn_options(workers, reload) -> tuple:
    """What uvicorn can actually be given, and a word about the difference.

    `host()` hands uvicorn an app *object*. Uvicorn can only fork workers or
    watch files when it is given an import string, and handed an object it
    refuses both and returns without ever serving. Both values are written into
    every generated host.yaml, under a header that says to edit them:

        workers: 1
        reload: false

    Changing either one used to print the whole startup banner -- address, URL,
    "POST /input" -- and then exit, leaving one uvicorn warning underneath and
    nothing listening on the port the banner named.

    What blocks it now is only the app object. The scheduler no longer is: it
    takes one lock per tick, so under several processes exactly one of them
    runs a due entry (#640). This paragraph used to name that as the second
    reason, and the message below said so out loud -- kept in sync here because
    a stale reason in an operator-facing line is how someone concludes the
    limitation is bigger than it is.

    Keep the agent running and say what was not honoured -- silently running
    one worker is a smaller lie than dying behind a banner that says otherwise.
    """
    if workers and workers > 1:
        print(f"[host] workers: {workers} not honoured — running one worker "
              f"(uvicorn needs an import string to fork; `co host` hands it an "
              f"app object)")
    if reload:
        print("[host] reload: true not honoured — running without reload "
              "(uvicorn needs an import string to watch files)")
    return 1, False


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
    Host banner shows: URL, endpoints, address, relay, config, logs, trust/invite.
    """
    console = Console()
    base_url = f"http://localhost:{port}"
    prefix = "[magenta]\\[host][/magenta]"
    indent = "       "  # 7 spaces to align with [host]

    # What relay this agent will announce on — a statement of configuration, not
    # of success. This printed "✓ relay" whenever a URL was set, before any
    # connection was attempted, so an unreachable relay still got a green tick
    # and the operator was told their agent was reachable. Whether it connected
    # is said by the lines that know: `relay connection error …`, `relay
    # reconnected`, and the ♥ in a terminal.
    from urllib.parse import urlparse

    if relay_url:
        relay_host = urlparse(relay_url).netloc or relay_url
        relay_status = f"[dim]relay:[/dim] {relay_host}"
    else:
        relay_status = "[dim]no relay[/dim]"

    # Get absolute paths for config and logs
    base = co_dir or project_co_dir()
    config_file = (base / "host.yaml").resolve()
    logs_dir = (base / "logs").resolve()

    # Header with [host] prefix
    console.print()
    console.print(f"{prefix} [dim]{'─' * 35}[/dim]")
    console.print(f"{indent}[cyan]{base_url}[/cyan]")
    endpoints = "[bold]POST[/bold] /input · [bold]WS[/bold] /ws"
    console.print(f"{indent}{endpoints} · [dim]GET /docs[/dim]")
    console.print()

    # Full address, and the chat site — but only when this agent announces on the
    # relay that site reads. The link was unconditional, which was accidentally
    # true while every agent was on the public relay; an agent on a private one
    # was being sent to a site that has never heard of it.
    console.print(f"{indent}[cyan]{address}[/cyan]")
    if relay_url == DEFAULT_RELAY_URL:
        chat_url = f"https://chat.openonion.ai/{address}"
        console.print(f"{indent}[link={chat_url}][dim]↳ chat.openonion.ai ↗[/dim][/link]")
    console.print(f"{indent}{relay_status}")
    console.print()

    # Config and logs info (absolute paths)
    console.print(f"{indent}[dim]config:[/dim] {config_file}")
    console.print(f"{indent}[dim]logs:[/dim] {logs_dir}")
    console.print()

    # Trust/Invite (belongs to host layer)
    if trust_config and isinstance(trust, str) and trust.lower() in TRUST_LEVELS:
        line = _invite_line(trust_config)
        if line:
            console.print(f"{indent}[bold yellow]{line}[/bold yellow]")
            console.print()

    console.print()


def _invite_line(trust_config) -> str | None:
    """One line about the agent's door, or nothing.

    Three things it must not do.

    **Print the code.** It is a password, and this line goes to stdout, which on
    a deployed agent is journalctl — readable by anyone with the box, kept as
    long as the logs are kept, and copied into every paste of a startup dump.
    Saying a door exists is not the same as publishing its key.

    **Print the placeholder.** `$CO_INVITE_CODE` rendered verbatim reads as the
    code to anyone who has not seen the policy file.

    **Say nothing when nobody can get in.** A policy that declares
    `$CO_INVITE_CODE` on a machine where it is unset refuses every code. That is
    the safe direction, and it is the one an upgrade produces on any deployment
    that relied on the old shipped constant — so it has to be said out loud, or
    the operator learns it from a person who could not get in.
    """
    onboard = (trust_config or {}).get("onboard") or {}
    declared = onboard.get("invite_code") or []
    declared = declared if isinstance(declared, list) else [declared]
    if not declared:
        return None

    from ..trust.fast_rules import _resolve_codes
    from_env = [str(c)[1:] for c in declared if str(c).startswith("$")]
    literals = [c for c in declared if not str(c).startswith("$")]
    live = _resolve_codes(declared)

    if live:
        # Say *where* the code is, not just that there is one. Telling an
        # operator whose code is a literal in trust.md to "get it from .env"
        # sends them looking for something that is not there.
        resolved_from_env = [n for n in from_env if os.environ.get(n, "").strip()]
        if resolved_from_env and literals:
            where = f"{', '.join(resolved_from_env)} in .env, and one in the trust policy"
        elif resolved_from_env:
            where = f"{', '.join(resolved_from_env)} in .env"
        else:
            where = "in the trust policy"
        dead = [n for n in from_env if not os.environ.get(n, "").strip()]
        note = f" ({', '.join(dead)} is declared but unset)" if dead else ""
        return f"Invite: set — {where}, not printed here{note}"

    if from_env:
        return (f"Invite: no one can onboard — {', '.join(from_env)} is not set. "
                f"Add it to .env, or run `co init` to mint one.")
    return None


def _both(first, second):
    """Run two lifespan callbacks as one, in order.

    The ASGI app takes a single on_startup and a single on_shutdown, and there
    are now two things that want them — the relay and the schedule. Either may
    be absent, so this also has to handle None.
    """
    if first is None:
        return second
    if second is None:
        return first

    async def run_both():
        await first()
        await second()

    return run_both


BALANCE_REFRESH_INTERVAL = 60


async def _refresh_published_balance(sample, agent_metadata: dict,
                                     profile: dict | None = None) -> None:
    """Refresh the managed-key balance without blocking the ASGI event loop."""
    get_balance = getattr(getattr(sample, "llm", None), "get_balance", None)
    if not callable(get_balance):
        return
    try:
        balance = await asyncio.to_thread(get_balance)
    except Exception:
        # Display metadata is non-critical. Keep the last known value during a
        # transient API failure and try again on the next interval.
        return
    if balance is None:
        return
    agent_metadata["balance_usd"] = balance
    if profile is not None:
        profile["balance_usd"] = balance


def _create_balance_lifespan(sample, agent_metadata: dict,
                             profile: dict | None = None):
    """Refresh /info, authenticated profile, and relay profile once a minute."""
    if not callable(getattr(getattr(sample, "llm", None), "get_balance", None)):
        return None, None

    task = None

    async def refresh_loop():
        while True:
            await asyncio.sleep(BALANCE_REFRESH_INTERVAL)
            await _refresh_published_balance(sample, agent_metadata, profile)

    async def on_startup():
        nonlocal task
        task = asyncio.create_task(refresh_loop())

    async def on_shutdown():
        nonlocal task
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return on_startup, on_shutdown



class _Unset:
    """Distinguishes "the caller said nothing" from "the caller said None"."""

    def __repr__(self):
        return "UNSET"

    def __bool__(self):
        return False


UNSET = _Unset()


def resolve_relay_url(param, config: dict) -> str | None:
    """Which relay this agent announces on.

    Every other host() parameter defaults to None, which load_host_config reads
    as "not specified" so the file wins. relay_url defaulted to
    DEFAULT_RELAY_URL — a real string — so `host(agent)`, which is what every
    generated agent.py calls, passed it as an explicit override and the file
    never won.

    That line is in every project's host.yaml, under a header that says "edit
    these values". Editing it did nothing: an agent pointed at a private relay
    announced on the public one, with a ✓ in the banner and no error anywhere,
    because as far as the process was concerned nothing had gone wrong.

    UNSET rather than None as the default, because None already means something
    here — no relay at all — and the two must not collapse into each other.
    """
    if param is not UNSET:
        return param or None          # explicit, including None for "off"

    from ...backend import backend_ws_url
    from_file = config.get("relay_url", UNSET)
    if from_file is UNSET:
        return backend_ws_url()       # nothing said anywhere
    # Older generated host.yaml files wrote the production relay as if the
    # operator had chosen it. Treat that one legacy template value as a default
    # so CONNECTONION_BACKEND_URL can move an existing project as a whole.
    # A genuinely custom/private relay remains an explicit override.
    if from_file == DEFAULT_RELAY_URL:
        return backend_ws_url()
    return from_file or None          # an empty value in the file means off

def _create_relay_lifespan(relay_url: str, addr_data: dict, summary: str, port: int, relay_session_runner, *, profile: dict | None = None):
    """Create relay startup/shutdown callbacks for ASGI lifespan.

    Args:
        relay_url: WebSocket URL for P2P relay
        addr_data: Agent address data (public key, address)
        summary: Summary text for relay announcement
        port: HTTP port for endpoint discovery
        relay_session_runner: async (send_msg, recv_msg) -> None, runs protocol for one relay session
        profile: mutable publishable display info, sent initially and with
                 heartbeat ANNOUNCEs so refreshed fields reach the directory

    Returns:
        Tuple of (on_startup, on_shutdown) async callbacks
    """
    relay_task = None

    async def on_startup():
        nonlocal relay_task
        endpoints = announce.get_endpoints(port)

        async def relay_loop():
            # Long-lived supervisor: keep the agent registered on the relay across ANY
            # transient failure. serve_loop returns on a clean disconnect, but connect()
            # or serve_loop can also RAISE — a network blip surfaces as OSError, the relay
            # redeploys, DNS hiccups, a frame is malformed. For a connection meant to live
            # for days those are normal operation, not bugs. So catch everything except
            # cancellation, log, back off, and reconnect. Without this, the first
            # non-ConnectionClosed error escapes the loop and silently kills relay_task:
            # the agent keeps serving DIRECT connections but never announces again, so its
            # relay registration goes stale and it becomes unreachable via the relay until
            # the process is restarted.
            relay_console = Console()
            failures = 0
            while True:
                try:
                    # serve_once owns the socket's whole life. Opening it here
                    # and dropping it on either exit path left one in
                    # CLOSE-WAIT per reconnect (#548). The announce message is
                    # built by callback, after the connection, because it is
                    # signed and has to be fresh for the socket it announces on.
                    await relay.serve_once(
                        relay_url,
                        lambda: announce.create_announce_message(
                            addr_data, summary, endpoints=endpoints,
                            relay=relay_url, profile=profile,
                        ),
                        addr_data=addr_data, session_handler=relay_session_runner,
                    )
                    if failures:
                        # Say so. The log printed `Relay disconnected` and then
                        # nothing, so a journal read as a permanent outage when
                        # the truth was a three-second blip — telling them apart
                        # meant inspecting sockets on the box.
                        relay_console.print(
                            f"[magenta]\\[host][/magenta] [dim]relay reconnected[/dim]"
                        )
                    failures = 0  # clean disconnect — next reconnect is immediate
                except asyncio.CancelledError:
                    raise  # shutdown — propagate so on_shutdown can await it cleanly
                except Exception as exc:
                    # Survive any transient fault, but don't HIDE a persistent one. Back off
                    # (capped at 30s) so a dead relay isn't a 1/s reconnect+log storm, and add
                    # jitter from the 2nd attempt on so a recovering relay doesn't get a
                    # thundering herd. The first retry stays an exact 1s for fast single-blip
                    # recovery. Escalate the log after several consecutive failures so a
                    # permanent problem (revoked key, decommissioned relay, a real bug) is
                    # surfaced loudly instead of buried in a dim 1s loop forever.
                    failures += 1
                    delay = min(2 ** min(failures - 1, 5), 30)
                    if failures > 1:
                        delay += random.uniform(0, 1.0)
                    if failures >= 5:
                        relay_console.print(
                            f"[red]\\[host][/red] relay still unreachable after {failures} attempts "
                            f"({exc!r}); retrying in {delay:.0f}s"
                        )
                    else:
                        relay_console.print(
                            f"[magenta]\\[host][/magenta] [dim]relay connection error ({exc!r}); reconnecting in {delay:.0f}s[/dim]"
                        )
                    await asyncio.sleep(delay)
                    continue
                await asyncio.sleep(1)

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


DEFAULT_RELAY_URL = DEFAULT_BACKEND_WS_URL


def host(
    create_agent: Callable,
    port: int = None,
    trust: Union[str, "Agent"] = None,
    result_ttl: int = None,
    workers: int = None,
    reload: bool = None,
    *,
    relay_url: str | None = UNSET,
    blacklist: list | None = None,
    whitelist: list | None = None,
    co_dir: Path = None,
    summary: str = None,
    examples: list = None,
    http=None,
):
    """
    Host an agent over HTTP/WebSocket with P2P relay discovery (enabled by default).

    Configuration: .co/host.yaml (required) with code param overrides.
    Run 'co init' to generate the config file.

    Passing an Agent instance is the simple path and shares that instance.
    Passing a factory creates a fresh Agent for each request.

    State Control:
        # Simple/default: share one configured agent and expensive tool setup:
        agent = Agent("assistant", tools=[BrowserTool()])
        host(agent)

        # Per-request isolation: create everything inside a factory:
        def create_agent():
            browser = BrowserTool()  # Fresh per request
            return Agent("assistant", tools=[browser])
        host(create_agent)

        # Shared state (advanced) - create outside, capture via closure:
        browser = BrowserTool()  # Shared across all requests
        def create_agent():
            return Agent("assistant", tools=[browser])

    Args:
        create_agent: Agent instance for shared state, or a function that returns
                      a fresh Agent per request. A factory isolates state but also
                      pays the full construction cost on every request.
        port: HTTP port (default: 8000 or from .co/host.yaml)
        trust: Trust level, policy, or Agent (default: from .co/host.yaml or "careful")
            - Level: "open", "careful", "strict"
            - Policy: Natural language or file path
            - Agent: Custom trust agent
        result_ttl: How long to keep results in seconds (default: 86400 or from config)
        workers: Number of worker processes (default: 1 or from config)
        reload: Auto-reload on code changes (default: False or from config)
        relay_url: P2P relay URL (default: the configured backend)
            - Set to None or "" to disable relay and run local-only
        blacklist: Blocked identities (default: from .co/blacklist.txt)
        whitelist: Allowed identities (default: from .co/whitelist.txt)
        co_dir: Path to .co directory for agent identity (default: ~/.co/)
        summary: Agent description (default: from config or agent.system_prompt)
        examples: Example prompts (default: from config or auto-generated)
        http: Optional HTTPRouter with publisher-defined resource routes

    Direct execution (WS EXEC):
        Clients can run a tool directly, bypassing the LLM, via
        RemoteAgent.call("bash", command="co status"). This is gated by the
        SAME .co/host.yaml `permissions` whitelist the LLM approval flow uses —
        only whitelisted commands run. Nothing to enable: edit the whitelist.

    Endpoints:
        POST /input          - Submit prompt, get result
        GET  /sessions/{id}  - Get session by ID
        GET  /sessions       - List all sessions
        GET  /health         - Health check
        GET  /info           - Agent info (includes summary, examples)
        WS   /ws             - WebSocket
        GET  /admin/logs     - Activity log (signed admin or admin token)
        GET  /admin/sessions - Activity sessions (signed admin or admin token)
    """
    if http is not None:
        from .http_routes import HTTPRouter
        if not isinstance(http, HTTPRouter):
            raise TypeError("http must be an HTTPRouter")

    # Accept the documented simple path directly: host(agent). A factory remains
    # available when per-request isolation is worth its construction cost.
    if not callable(create_agent):
        _agent_instance = create_agent
        create_agent = lambda: _agent_instance

    # Resolve co_dir: explicit > the project's .co, found by walking up.
    # Not `Path.cwd() / '.co'`: an agent started one directory down found no
    # host.yaml and ran on defaults -- a project that says `trust: strict` came
    # up as `careful`, admitting contacts and accepting an invite code while its
    # configuration said whitelist only.
    if co_dir is None:
        co_dir = project_co_dir()

    # A server can host more than one agent, and only the port stops it: two of
    # them defaulting to 8000 means the second dies on "address already in use"
    # while systemd keeps restarting it. `co deploy --to` picks a free port on
    # the machine and passes it here, so the operator's agent.py needs no change
    # and no knowledge of what else lives on that box. An explicit port in code
    # or host.yaml still wins — this only replaces the default.
    if port is None and os.getenv("AGENT_PORT"):
        port = int(os.environ["AGENT_PORT"])

    # Load config: host.yaml (optional) → code param overrides
    # relay_url is resolved separately: load_host_config drops a None code
    # param as "not specified", and None is a meaningful answer here.
    config = load_host_config(
        co_dir,
        port=port, trust=trust, result_ttl=result_ttl,
        workers=workers, reload=reload,
        summary=summary, examples=examples,
    )

    # Extract final values from config
    port = config.get('port', 8000)
    trust = config.get('trust', 'careful')
    result_ttl = config.get('result_ttl', 86400)
    workers = config.get('workers', 1)
    reload = config.get('reload', False)
    relay_url = resolve_relay_url(relay_url, config)
    summary = config.get('summary')
    examples = config.get('examples')

    # Extract metadata once at startup
    agent_metadata, sample = _extract_agent_metadata(create_agent, config.get("name"))

    # Auto-generate summary from system_prompt if not set
    # An operator-written summary is the only thing worth putting on the Home page
    # as a tagline: the fallback below is prompt text, addressed to the agent in
    # the second person, and reads as a mistake when shown to a person.
    if summary is not None:
        agent_metadata['tagline'] = summary
    else:
        summary = sample.system_prompt[:1000] if sample.system_prompt else f"{agent_metadata['name']} agent"

    agent_metadata['summary'] = summary
    agent_metadata['examples'] = examples

    # Load whitelist/blacklist: code param (list) takes priority, else load from YAML file path
    if whitelist is None:
        whitelist = load_list_file(config.get('whitelist'))

    if blacklist is None:
        blacklist = load_list_file(config.get('blacklist'))

    # Load or generate agent identity -- the one `co status` reports, not a new one
    addr_data = resolve_agent_identity(co_dir)

    # Said before the banner, where the address is about to be printed as if it
    # belonged to this agent alone.
    collision = claim_identity(co_dir, addr_data, agent_metadata["name"])
    if collision:
        print(f"[host] {collision}")

    agent_metadata["address"] = addr_data['address']
    agent_metadata["trust"] = trust if isinstance(trust, str) else "custom"

    # Rendered here and not earlier: the Home shows the address and the trust
    # level, and neither exists until this point. Called above, it rendered a
    # page missing both and nothing said so.
    from .ws_router.dashboard import ensure_dashboard
    ensure_dashboard(agent_metadata)

    # co_dir, not the default: host(co_dir=...) must put the sessions there too.
    storage = SessionStorage(co_dir / "session_results.jsonl")

    # Any session still marked `running` belongs to a process that is gone —
    # this one just started and owns none. Left alone they are permanent, since
    # `running` is exempt from TTL, and every mid-turn restart adds one (#545).
    storage.reconcile_interrupted()
    # And drop what no reader can see: superseded records, and sessions past
    # their TTL that are not running. The file is append-only otherwise, and a
    # live agent was at 17 MB for 222 sessions — every dashboard open reparses
    # all of it.
    storage.compact()

    # Create Active Session Registry for WebSocket reconnection
    registry = ActiveSessionRegistry()
    start_cleanup_job(registry)  # Start background cleanup

    # Create TrustAgent instance - the single interface for all trust operations
    # Users can subclass TrustAgent to customize (e.g., database-backed admin storage)
    if isinstance(trust, TrustAgent):
        trust_agent = trust
    else:
        trust_agent = TrustAgent(
            trust if isinstance(trust, str) else "careful",
            co_dir=co_dir,
        )

    # Load the permission whitelist that gates direct execution (WS EXEC).
    # Same list the LLM approval flow reads: template safe defaults + this
    # project's .co/host.yaml permissions block.
    from ...useful_plugins.tool_approval.approval import load_permission_patterns
    exec_permissions = load_permission_patterns(co_dir)

    replay_store = SignatureReplayStore(co_dir / "replay.sqlite3")
    route_handlers = _create_route_handlers(
        create_agent, agent_metadata, result_ttl, trust_agent, config,
        exec_permissions, replay_store.already_used,
        mode_policy=_host_mode_policy(sample),
    )

    # Parse trust config for /info onboard info
    trust_config = _parse_trust_config(trust)

    # Create relay lifespan callbacks (runs in same event loop as HTTP/WebSocket)
    on_startup, on_shutdown = None, None
    relay_profile = _build_agent_profile(agent_metadata)
    if relay_url:
        # Pre-bind run_ws_session's host-wide deps so relay only needs to pass
        # (send_msg, recv_msg). Each call = one client session full lifecycle
        # (auth → INPUT/OUTPUT cycles → disconnect). enable_ping=True: the 30s PING
        # is the CLIENT-session keepalive — it's forwarded through the relay to the
        # browser so the SDK's 60s-silence monitor doesn't declare the connection
        # dead and reconnect. The relay's ANNOUNCE heartbeat is a different thing
        # (it only keeps the agent↔relay link alive; it never reaches the client),
        # so it can't substitute for the PING. Without this, idle relay sessions
        # churn (silence → reconnect) every ~60s.
        relay_session_runner = partial(run_ws_session,
            route_handlers=route_handlers,
            storage=storage,
            registry=registry,
            trust=trust_agent,
            blacklist=blacklist,
            whitelist=whitelist,
            enable_ping=True,
            transport="relay",
        )
        on_startup, on_shutdown = _create_relay_lifespan(
            relay_url, addr_data, summary, port, relay_session_runner,
            profile=relay_profile,
        )

    balance_startup, balance_shutdown = _create_balance_lifespan(
        sample, agent_metadata, relay_profile
    )
    on_startup = _both(on_startup, balance_startup)
    on_shutdown = _both(balance_shutdown, on_shutdown)

    # The schedule is not conditional on the relay. An agent reachable only on
    # localhost still has recurring work to do, and tying its clock to whether
    # it happens to be announced would make "it stopped running at night" a
    # networking question.
    sched_startup, sched_shutdown = create_schedule_lifespan(
        co_dir, create_agent, storage, result_ttl, console=Console(),
    )
    on_startup = _both(on_startup, sched_startup)
    on_shutdown = _both(sched_shutdown, on_shutdown)   # stop the clock first

    app = asgi_create_app(
        route_handlers=route_handlers,
        storage=storage,
        registry=registry,  # Active session registry for reconnection
        trust=trust_agent,  # Pass resolved TrustAgent, not raw trust
        trust_config=trust_config,
        blacklist=blacklist,
        whitelist=whitelist,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        http=http,
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

    workers, reload = usable_uvicorn_options(workers, reload)
    uvicorn.run(app, host="0.0.0.0", port=port, workers=workers, reload=reload, log_level="warning")


def create_app(create_agent: Callable, storage=None, trust="careful", result_ttl=86400, *, blacklist=None, whitelist=None, name=None, http=None):
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
    from .http_routes import HTTPRouter

    if http is not None and not isinstance(http, HTTPRouter):
        raise TypeError("http must be an HTTPRouter")

    if storage is None:
        storage = SessionStorage()
    storage.reconcile_interrupted()      # see the note at the other call site
    storage.compact()

    # Create Active Session Registry for WebSocket reconnection
    registry = ActiveSessionRegistry()
    start_cleanup_job(registry)

    # Extract metadata once at startup. `name` is host.yaml's, when the caller
    # has read it — host() does; a bare ASGI caller may not, and then the
    # Agent's own name stands as before.
    agent_metadata, sample = _extract_agent_metadata(create_agent, name)
    agent_metadata["address"] = get_agent_address(sample)
    agent_metadata["trust"] = trust if isinstance(trust, str) else "custom"

    # Give the agent a polished Home on day zero (no-op if dashboard.html exists).
    from .ws_router.dashboard import ensure_dashboard
    ensure_dashboard(agent_metadata)

    # The storage directory is the project boundary available to create_app().
    # Resolve it before trust construction so authorization and replay state
    # cannot land in different projects when custom storage is supplied.
    storage_path = getattr(storage, "path", None)
    replay_dir = Path(storage_path).parent if storage_path else project_co_dir()

    # Create TrustAgent instance
    if isinstance(trust, TrustAgent):
        trust_agent = trust
    else:
        trust_agent = TrustAgent(
            trust if isinstance(trust, str) else "careful",
            co_dir=replay_dir,
        )

    from ...useful_plugins.tool_approval.approval import load_permission_patterns
    replay_store = SignatureReplayStore(replay_dir / "replay.sqlite3")
    route_handlers = _create_route_handlers(
        create_agent, agent_metadata, result_ttl, trust_agent,
        DEFAULT_FILE_LIMITS, load_permission_patterns(),
        replay_store.already_used,
        mode_policy=_host_mode_policy(sample),
    )
    balance_startup, balance_shutdown = _create_balance_lifespan(
        sample, agent_metadata
    )
    return asgi_create_app(
        route_handlers=route_handlers,
        storage=storage,
        registry=registry,
        trust=trust_agent,  # Pass resolved TrustAgent, not raw trust
        blacklist=blacklist,
        whitelist=whitelist,
        on_startup=balance_startup,
        on_shutdown=balance_shutdown,
        http=http,
    )
