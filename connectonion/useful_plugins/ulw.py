"""
Purpose: ULW (Ultra Light Work) plugin - autonomous agent mode with turn-based checkpoints
LLM-Note:
  Dependencies: imports from [core/events.py, tool_approval/constants.py] | imported by [useful_plugins/__init__.py]
  Data flow: trusted mode control → server-owned ULW lease → on_complete continues until checkpoint
  State/Effects: owns agent._trusted_server_state['ulw']; mirrors progress to plugin_state['ulw'] for UI only
  Integration: communicates with tool_approval through server-derived runtime mode='ulw'
  Errors: malformed trusted leases fail closed to safe mode; agent.input() failures propagate

ULW Mode - Ultra Light Work.

When in ULW mode:
1. All tool approvals are skipped while the trusted runtime mode is 'ulw'
2. Agent keeps working until its server-owned turn lease is exhausted
3. At checkpoint, user can continue, switch mode, or stop

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import tool_approval, ulw

    agent = Agent("worker", plugins=[tool_approval, ulw])
"""

import inspect
import uuid
from typing import TYPE_CHECKING

from ..core.events import (
    after_user_input,
    before_iteration,
    before_llm,
    on_agent_ready,
    on_complete,
)
from .tool_approval.constants import DEFAULT_MODE, VALID_MODES

if TYPE_CHECKING:
    from ..core.agent import Agent


ULW_DEFAULT_TURNS = 100
ULW_MAX_TURNS = 1000
ULW_MAX_PROMPT_CHARS = 32_768
ULW_STATE_KEY = 'ulw'

ULW_CONTINUE_PROMPT = """Review what you've done so far. Consider:
- Are there edge cases not handled?
- Could the code be cleaner or simpler?
- Are there missing tests or documentation?
- Any obvious improvements?

Continue improving, or say "genuinely complete" if nothing meaningful left to do."""


def _log(agent: 'Agent', message: str) -> None:
    """Log message via agent's logger if available."""
    if hasattr(agent, 'logger') and agent.logger:
        agent.logger.print(message)


def _server_state(agent: 'Agent') -> dict:
    """Return the owner-bound state injected/persisted by the host."""
    state = getattr(agent, '_trusted_server_state', None)
    if not isinstance(state, dict):
        state = {}
        agent._trusted_server_state = state
    return state


def _plugin_state(agent: 'Agent') -> dict:
    """Return the untrusted client-visible plugin-state container."""
    state = agent.current_session.get('plugin_state')
    if not isinstance(state, dict):
        state = {}
        agent.current_session['plugin_state'] = state
    return state


def _valid_turn_count(value: object) -> bool:
    """Accept bounded integers only; bool is an int subclass and is rejected."""
    return type(value) is int and 1 <= value <= ULW_MAX_TURNS


def _valid_generation(value: object) -> bool:
    """Recognize generations created by ``uuid.uuid4().hex``."""
    return (
        isinstance(value, str)
        and len(value) == 32
        and all(char in '0123456789abcdef' for char in value)
    )


def _validated_lease(raw: object) -> dict | None:
    """Parse a server-owned ULW lease using an explicit schema."""
    if not isinstance(raw, dict):
        return None
    turns = raw.get('turns')
    turns_used = raw.get('turns_used')
    if not _valid_turn_count(turns):
        return None
    if type(turns_used) is not int or not 0 <= turns_used <= turns:
        return None

    lease = {'turns': turns, 'turns_used': turns_used}
    if 'generation' in raw:
        generation = raw['generation']
        if not _valid_generation(generation):
            return None
        lease['generation'] = generation
    if 'prompt' in raw:
        prompt = raw['prompt']
        if not isinstance(prompt, str) or len(prompt) > ULW_MAX_PROMPT_CHARS:
            return None
        lease['prompt'] = prompt
    return lease


def _new_lease(turns: int = ULW_DEFAULT_TURNS) -> dict:
    return {
        'turns': turns,
        'turns_used': 0,
        'generation': uuid.uuid4().hex,
    }


def _drop_legacy_capabilities(agent: 'Agent') -> None:
    """Remove obsolete client-visible state, especially the generic bypass flag."""
    for key in ('skip_tool_approval', 'ulw_turns', 'ulw_turns_used', 'ulw_prompt'):
        agent.current_session.pop(key, None)


def _mirror_lease(agent: 'Agent', lease: dict) -> None:
    """Publish a non-authoritative progress snapshot for clients/UI."""
    _plugin_state(agent)[ULW_STATE_KEY] = dict(lease)


def _checkpoint_server_state(agent: 'Agent') -> None:
    """Persist capability state before more privileged work can happen."""
    storage = getattr(agent, 'storage', None)
    session = getattr(agent, 'current_session', None)
    if not storage or not isinstance(session, dict) or not session.get('session_id'):
        return

    checkpoint = storage.checkpoint
    context = {
        'owner_address': getattr(agent, '_session_owner_address', None),
        'server_state': _server_state(agent),
        'status': 'running',
    }
    try:
        parameters = inspect.signature(checkpoint).parameters
    except (TypeError, ValueError):
        parameters = {}
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        supported = context
    else:
        supported = {key: value for key, value in context.items() if key in parameters}
    checkpoint(session, **supported)


def _remove_injected_prompt(agent: 'Agent') -> None:
    messages = agent.current_session.get('messages', [])
    if messages and messages[0].get('role') == 'system':
        messages[0]['content'] = messages[0].get('content', '').split('\n\n[Prompt]')[0]


def _bind_server_state(agent: 'Agent') -> None:
    """Bind capability state to the current owner/session when it is persistent."""
    bind = getattr(agent, '_bind_trusted_server_state', None)
    if callable(bind):
        bind()
        return
    session = getattr(agent, 'current_session', None)
    session_id = session.get('session_id') if isinstance(session, dict) else None
    if isinstance(session_id, str) and session_id:
        agent._trusted_server_state_binding = (
            getattr(agent, '_session_owner_address', None),
            session_id,
        )


def _set_authoritative_ulw(agent: 'Agent', lease: dict) -> None:
    """Install a normalized server-owned lease and its client-visible mirror."""
    normalized = dict(lease)
    server = _server_state(agent)
    server['mode'] = 'ulw'
    server[ULW_STATE_KEY] = normalized
    _bind_server_state(agent)
    agent.current_session['mode'] = 'ulw'
    _drop_legacy_capabilities(agent)
    _mirror_lease(agent, normalized)


def clear_ulw_state(agent: 'Agent', new_mode: str = DEFAULT_MODE) -> None:
    """Revoke ULW authority and remove all ULW client-visible state."""
    if new_mode not in VALID_MODES:
        new_mode = DEFAULT_MODE
    server = _server_state(agent)
    server['mode'] = new_mode
    server.pop(ULW_STATE_KEY, None)
    _bind_server_state(agent)
    _plugin_state(agent).pop(ULW_STATE_KEY, None)
    _drop_legacy_capabilities(agent)
    _remove_injected_prompt(agent)
    agent.current_session['mode'] = new_mode
    _checkpoint_server_state(agent)


def _restore_trusted_lease(agent: 'Agent') -> bool:
    """Restore ULW only from owner-bound server state, never client session data."""
    server = _server_state(agent)
    if server.get('mode') != 'ulw':
        return False
    lease = _validated_lease(server.get(ULW_STATE_KEY))
    if lease is None or lease['turns_used'] >= lease['turns']:
        clear_ulw_state(agent)
        return False
    _set_authoritative_ulw(agent, lease)
    return True


@on_agent_ready
def enable_ulw_plugin(agent: 'Agent') -> None:
    """Mark that bounded ULW lifecycle hooks are installed on this Agent."""
    agent._ulw_plugin_enabled = True


def is_ulw_active(agent: 'Agent') -> bool:
    """Return whether the current turn holds a consumed, bounded ULW lease."""
    session = getattr(agent, 'current_session', None)
    server = _server_state(agent)
    lease = _validated_lease(server.get(ULW_STATE_KEY))
    active = bool(
        getattr(agent, '_ulw_plugin_enabled', False)
        and isinstance(session, dict)
        and session.get('mode') == 'ulw'
        and server.get('mode') == 'ulw'
        and lease is not None
        and 0 < lease['turns_used'] <= lease['turns']
    )
    if not active and isinstance(session, dict) and (
        session.get('mode') == 'ulw' or server.get('mode') == 'ulw'
    ):
        clear_ulw_state(agent)
    return active


@after_user_input
def restore_ulw_state(agent: 'Agent') -> None:
    """Initialize explicit ULW or restore an owner-bound server lease."""
    explicit_mode = getattr(agent, '_input_mode', None)
    if explicit_mode == 'ulw':
        _set_authoritative_ulw(agent, _new_lease())
        return
    if explicit_mode in VALID_MODES:
        clear_ulw_state(agent, explicit_mode)
        return
    if _restore_trusted_lease(agent):
        return

    trusted_mode = _server_state(agent).get('mode')
    if trusted_mode in VALID_MODES or agent.current_session.get('mode') == 'ulw':
        clear_ulw_state(agent, trusted_mode or DEFAULT_MODE)
        return
    _plugin_state(agent).pop(ULW_STATE_KEY, None)
    _drop_legacy_capabilities(agent)
    _remove_injected_prompt(agent)


@after_user_input
def consume_ulw_turn(agent: 'Agent') -> None:
    """Consume and persist one leased turn before the LLM can do work."""
    server = _server_state(agent)
    if server.get('mode') != 'ulw' or agent.current_session.get('mode') != 'ulw':
        return
    lease = _validated_lease(server.get(ULW_STATE_KEY))
    if lease is None or lease['turns_used'] >= lease['turns']:
        clear_ulw_state(agent)
        return
    lease['turns_used'] += 1
    _set_authoritative_ulw(agent, lease)
    _checkpoint_server_state(agent)


def _reconcile_ulw_mode(agent: 'Agent') -> None:
    """Revoke a trusted ULW lease after runtime mode switches away."""
    if _server_state(agent).get('mode') != 'ulw':
        return
    runtime_mode = agent.current_session.get('mode')
    if runtime_mode in VALID_MODES:
        clear_ulw_state(agent, runtime_mode)


@before_iteration
def reconcile_ulw_mode(agent: 'Agent') -> None:
    """Persist an authenticated WebSocket switch away from ULW."""
    _reconcile_ulw_mode(agent)


@before_llm
def reconcile_ulw_mode_before_llm(agent: 'Agent') -> None:
    """Recheck after all before_iteration handlers, independent of plugin order."""
    _reconcile_ulw_mode(agent)


def handle_ulw_mode_change(agent: 'Agent', turns: int = None) -> None:
    """Handle an authenticated mode change to ULW.

    Args:
        agent: Agent instance.
        turns: Trusted turn budget for this lease (default 100, maximum 1000).
    """
    if turns is None:
        turns = ULW_DEFAULT_TURNS
    if not _valid_turn_count(turns):
        return

    old_mode = agent.current_session.get('mode', DEFAULT_MODE)
    old_lease = _validated_lease(_server_state(agent).get(ULW_STATE_KEY))
    lease = _new_lease(turns)
    if old_lease and 'prompt' in old_lease:
        lease['prompt'] = old_lease['prompt']
    # This handler runs during before_iteration, after after_user_input's normal
    # consume hook. Count the already-started turn before it gains ULW authority.
    lease['turns_used'] = 1
    _set_authoritative_ulw(agent, lease)
    _checkpoint_server_state(agent)

    if agent.io:
        agent.io.send({'type': 'mode_changed', 'mode': 'ulw', 'triggered_by': 'user'})
    _log(agent, f"[cyan]Mode changed: {old_mode} → ulw ({turns} turns)[/cyan]")


def _exit_ulw_mode(agent: 'Agent', new_mode: str = DEFAULT_MODE) -> None:
    """Exit ULW mode and notify the connected frontend."""
    clear_ulw_state(agent, new_mode)
    new_mode = agent.current_session['mode']

    if agent.io:
        agent.io.send({
            'type': 'mode_changed',
            'mode': new_mode,
            'triggered_by': 'ulw_checkpoint',
        })
    _log(agent, f"[cyan]Exited ULW mode → {new_mode}[/cyan]")


def _extend_lease(agent: 'Agent', lease: dict, extend: object) -> bool:
    if not _valid_turn_count(extend):
        return False
    if lease['turns'] + extend > ULW_MAX_TURNS:
        return False
    lease['turns'] += extend
    _set_authoritative_ulw(agent, lease)
    _checkpoint_server_state(agent)
    return True


def _schedule_continuation(agent: 'Agent') -> None:
    schedule = getattr(agent, '_schedule_input', None)
    if callable(schedule):
        schedule(ULW_CONTINUE_PROMPT)
    else:
        # Compatibility for lightweight Agent test doubles and older embedders.
        agent.input(ULW_CONTINUE_PROMPT)


@on_complete
def ulw_keep_working(agent: 'Agent') -> None:
    """If trusted ULW mode has turns remaining, start another turn."""
    if getattr(agent, '_turn_stopped', False):
        if hasattr(agent, '_scheduled_input'):
            agent._scheduled_input = None
        clear_ulw_state(agent)
        return

    server = _server_state(agent)
    if agent.current_session.get('mode') != 'ulw':
        if server.get('mode') == 'ulw':
            clear_ulw_state(agent, agent.current_session.get('mode', DEFAULT_MODE))
        return

    lease = _validated_lease(server.get(ULW_STATE_KEY))
    if server.get('mode') != 'ulw' or lease is None:
        clear_ulw_state(agent)
        return

    if lease['turns_used'] < lease['turns']:
        _schedule_continuation(agent)
        return

    if getattr(agent, '_session_id_authenticated', False):
        # Hosted bound sessions do not have a separately signed checkpoint
        # control frame. Waiting on generic io.receive() would either hang or
        # let an unrelated approval/ask-user/runtime frame extend the lease.
        # End safely; a later fully signed INPUT can explicitly start a new
        # bounded ULW lease.
        _exit_ulw_mode(agent)
        return

    if not agent.io:
        _exit_ulw_mode(agent)
        return

    agent.io.send({
        'type': 'ulw_turns_reached',
        'turns_used': lease['turns_used'],
        'max_turns': lease['turns'],
    })
    response = agent.io.receive()
    if not isinstance(response, dict):
        _exit_ulw_mode(agent)
        return
    action = response.get('action')
    if action == 'continue' and _extend_lease(agent, lease, response.get('turns', ULW_DEFAULT_TURNS)):
        _log(agent, f"[cyan]ULW extended: +{response.get('turns', ULW_DEFAULT_TURNS)} turns[/cyan]")
        _schedule_continuation(agent)
    elif action == 'switch_mode':
        _exit_ulw_mode(agent, response.get('mode', DEFAULT_MODE))
    else:
        _exit_ulw_mode(agent)


@before_iteration
def poll_prompt_update(agent: 'Agent') -> None:
    """Apply authenticated prompt updates to the server-owned ULW lease."""
    if not agent.io or _server_state(agent).get('mode') != 'ulw':
        return
    lease = _validated_lease(_server_state(agent).get(ULW_STATE_KEY))
    if lease is None:
        clear_ulw_state(agent)
        return

    changed = False
    for msg in agent.io.receive_all('prompt_update'):
        if not isinstance(msg, dict):
            continue
        prompt = msg.get('prompt', '')
        if isinstance(prompt, str) and len(prompt) <= ULW_MAX_PROMPT_CHARS:
            lease['prompt'] = prompt
            changed = True
    if changed:
        _set_authoritative_ulw(agent, lease)
        _checkpoint_server_state(agent)


@before_llm
def inject_ulw_prompt(agent: 'Agent') -> None:
    """Inject the trusted saved prompt into the system message."""
    if _server_state(agent).get('mode') != 'ulw':
        return
    lease = _validated_lease(_server_state(agent).get(ULW_STATE_KEY))
    prompt = lease.get('prompt') if lease else None
    if not prompt:
        return

    messages = agent.current_session['messages']
    if messages and messages[0]['role'] == 'system':
        base = messages[0]['content'].split('\n\n[Prompt]')[0]
        messages[0]['content'] = f"{base}\n\n[Prompt]\n{prompt}"


ulw = [
    enable_ulw_plugin,
    restore_ulw_state,
    consume_ulw_turn,
    reconcile_ulw_mode,
    reconcile_ulw_mode_before_llm,
    ulw_keep_working,
    poll_prompt_update,
    inject_ulw_prompt,
]

__all__ = [
    'ulw',
    'handle_ulw_mode_change',
    'clear_ulw_state',
    'enable_ulw_plugin',
    'is_ulw_active',
    'restore_ulw_state',
    'consume_ulw_turn',
    'reconcile_ulw_mode_before_llm',
    'ULW_DEFAULT_TURNS',
    'ULW_MAX_TURNS',
]
