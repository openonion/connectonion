"""
Purpose: Full access (YOLO) plugin - bounded autonomous permission profile with turn checkpoints
LLM-Note:
  Dependencies: imports from [core/events.py] | imported by [useful_plugins/__init__.py]
  Data flow: permission profile ':danger-full-access' → set skip_tool_approval=True → on_complete fires → continue until max turns
  State/Effects: sets mode, full_access_turns, full_access_turns_used, skip_tool_approval in session
  Integration: communicates with tool_approval via skip_tool_approval flag in session
  Errors: no explicit error handling, agent.input() failures propagate

Full access permission profile (YOLO CLI shorthand).

When the Full access profile is active:
1. All tool approvals are skipped (via skip_tool_approval flag)
2. Agent keeps working until max turns reached
3. At checkpoint, user can continue, switch profiles, or stop

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import tool_approval, full_access

    agent = Agent("worker", plugins=[tool_approval, full_access])
"""

from typing import TYPE_CHECKING

from ..core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
    legacy_permission_profile_id,
)
from ..core.events import after_user_input, before_iteration, before_llm, on_complete

if TYPE_CHECKING:
    from ..core.agent import Agent


FULL_ACCESS_DEFAULT_TURNS = 100
YOLO_DEFAULT_TURNS = FULL_ACCESS_DEFAULT_TURNS

FULL_ACCESS_CONTINUE_PROMPT = """Review what you've done so far. Consider:
- Are there edge cases not handled?
- Could the code be cleaner or simpler?
- Are there missing tests or documentation?
- Any obvious improvements?

Continue improving, or say "genuinely complete" if nothing meaningful left to do."""
YOLO_CONTINUE_PROMPT = FULL_ACCESS_CONTINUE_PROMPT


def _log(agent: 'Agent', message: str) -> None:
    """Log message via agent's logger if available."""
    if hasattr(agent, 'logger') and agent.logger:
        agent.logger.print(message)


def _positive_turn_count(value: object, *, default: int | None = None) -> int:
    """Return a bounded counter input without bool or numeric coercion."""
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("Full access turns must be a positive integer")
    return value


def handle_full_access_permission_profile_change(
    agent: 'Agent', turns: int = None
) -> None:
    """Handle a permission-profile change to Full access.

    Called for the canonical ``:danger-full-access`` permission profile.

    Sets up Full access state:
    - mode = ':danger-full-access'
    - full_access_turns = max turns before checkpoint
    - full_access_turns_used = 0
    - skip_tool_approval = True (tells tool_approval to skip all checks)

    Args:
        agent: Agent instance
        turns: Max turns before checkpoint (default: 100)
    """
    turns = _positive_turn_count(turns, default=FULL_ACCESS_DEFAULT_TURNS)

    # Preserve the documented pre-input activation path. The session does not
    # exist until Agent.input(), so defer activation to after_user_input.
    if agent.current_session is None:
        agent._yolo_turns = turns
        return

    try:
        old_mode = legacy_permission_profile_id(
            agent.current_session.get('mode', READ_ONLY_PERMISSION_PROFILE)
        )
    except ValueError:
        old_mode = READ_ONLY_PERMISSION_PROFILE

    # Set Full access state
    agent.current_session['mode'] = DANGER_FULL_ACCESS_PERMISSION_PROFILE
    agent.current_session['full_access_turns'] = turns
    agent.current_session['full_access_turns_used'] = 0
    agent.current_session['skip_tool_approval'] = True

    # Notify frontend
    if agent.io:
        agent.io.send({
            'type': 'mode_changed',
            'mode': DANGER_FULL_ACCESS_PERMISSION_PROFILE,
            'triggered_by': 'user',
        })

    _log(agent, f"[cyan]Permission profile changed: {old_mode} → :danger-full-access ({agent.current_session['full_access_turns']} turns)[/cyan]")


def handle_yolo_mode_change(agent: 'Agent', turns: int = None) -> None:
    """Recognizable CLI shorthand for the Full access profile handler."""
    handle_full_access_permission_profile_change(agent, turns)


def enable_full_access(agent: 'Agent', turns: int = None) -> None:
    """Configure the bounded Full access profile before the first input."""
    turns = _positive_turn_count(turns, default=FULL_ACCESS_DEFAULT_TURNS)

    agent._yolo_turns = turns
    agent._yolo_needs_activation = True
    if agent.current_session is not None:
        handle_full_access_permission_profile_change(agent, turns)
        agent._yolo_needs_activation = False


def enable_yolo(agent: 'Agent', turns: int = None) -> None:
    """Recognizable shorthand for :func:`enable_full_access`."""
    enable_full_access(agent, turns)


@after_user_input
def activate_configured_full_access(agent: 'Agent') -> None:
    """Enter the configured Full access profile before any LLM or tool call."""
    turns = getattr(agent, '_yolo_turns', None)
    needs_activation = getattr(agent, '_yolo_needs_activation', False)
    try:
        active_profile = legacy_permission_profile_id(
            agent.current_session.get('mode')
        )
    except ValueError:
        active_profile = READ_ONLY_PERMISSION_PROFILE
    if turns is None or (
        not needs_activation
        and active_profile == DANGER_FULL_ACCESS_PERMISSION_PROFILE
    ):
        return
    handle_full_access_permission_profile_change(agent, turns)
    agent._yolo_needs_activation = False


def _exit_full_access_profile(
    agent: 'Agent', new_profile: str = READ_ONLY_PERMISSION_PROFILE
) -> None:
    """Exit Full access and switch to another permission profile.

    Cleans up Full access state and clears skip_tool_approval flag.
    """
    agent.current_session.pop('skip_tool_approval', None)
    agent.current_session.pop('full_access_turns', None)
    agent.current_session.pop('full_access_turns_used', None)
    agent.current_session.pop('full_access_prompt', None)
    try:
        new_profile = legacy_permission_profile_id(new_profile)
    except ValueError:
        new_profile = READ_ONLY_PERMISSION_PROFILE
    if new_profile not in {
        READ_ONLY_PERMISSION_PROFILE,
        WORKSPACE_PERMISSION_PROFILE,
    }:
        new_profile = READ_ONLY_PERMISSION_PROFILE
    agent.current_session['mode'] = new_profile

    if agent.io:
        agent.io.send({'type': 'mode_changed', 'mode': new_profile, 'triggered_by': 'full_access_checkpoint'})

    _log(agent, f"[cyan]Exited Full access → {new_profile}[/cyan]")


@on_complete
def full_access_keep_working(agent: 'Agent') -> None:
    """If Full access is active and turns remain, start another turn."""
    try:
        mode = legacy_permission_profile_id(agent.current_session.get('mode'))
    except ValueError:
        return
    if mode != DANGER_FULL_ACCESS_PERMISSION_PROFILE:
        return
    agent.current_session['mode'] = mode

    # Validate restored/local state before it can keep approval bypass active.
    raw_used = agent.current_session.get('full_access_turns_used')
    try:
        max_turns = _positive_turn_count(
            agent.current_session.get('full_access_turns'),
        )
    except ValueError:
        _exit_full_access_profile(agent, READ_ONLY_PERMISSION_PROFILE)
        return
    if (
        isinstance(raw_used, bool)
        or not isinstance(raw_used, int)
        or raw_used < 0
        or raw_used >= max_turns
    ):
        _exit_full_access_profile(agent, READ_ONLY_PERMISSION_PROFILE)
        return

    # Track turns
    turns_used = raw_used + 1
    agent.current_session['full_access_turns_used'] = turns_used

    if turns_used >= max_turns:
        # A hosted grant is bounded by the launch-time authority captured by
        # Host. The local mailbox extension below is a standalone Agent
        # compatibility path; it must never increase remote authority.
        if getattr(agent, '_host_full_access_turns_ceiling', None) is not None:
            if agent.io:
                agent.io.send({
                    'type': 'full_access_checkpoint',
                    'turns_used': turns_used,
                    'max_turns': max_turns
                })
            _exit_full_access_profile(agent, READ_ONLY_PERMISSION_PROFILE)
            return

        # Max turns reached - pause for user (if IO available)
        if agent.io:
            agent.io.send({
                'type': 'full_access_checkpoint',
                'turns_used': turns_used,
                'max_turns': max_turns
            })
            response = agent.io.receive()

            action = response.get('action')
            if action == 'continue':
                # Extend turns and continue
                try:
                    extend = _positive_turn_count(
                        response.get('turns'),
                        default=FULL_ACCESS_DEFAULT_TURNS,
                    )
                except ValueError:
                    _exit_full_access_profile(agent, READ_ONLY_PERMISSION_PROFILE)
                    return
                agent.current_session['full_access_turns'] += extend
                _log(agent, f"[cyan]Full access extended: +{extend} turns[/cyan]")
                # Fall through to continue working
            elif action == 'switch_mode':
                # A checkpoint may leave Full access only for a bounded profile.
                # Re-selecting Full access here would bypass the transaction
                # that establishes its turn budget.
                try:
                    new_profile = legacy_permission_profile_id(
                        response.get('mode', READ_ONLY_PERMISSION_PROFILE)
                    )
                except ValueError:
                    new_profile = READ_ONLY_PERMISSION_PROFILE
                if new_profile not in {
                    READ_ONLY_PERMISSION_PROFILE,
                    WORKSPACE_PERMISSION_PROFILE,
                }:
                    new_profile = READ_ONLY_PERMISSION_PROFILE
                _exit_full_access_profile(agent, new_profile)
                return  # Stop working
            else:
                # Unknown action or stop - exit to Read only
                _exit_full_access_profile(agent, READ_ONLY_PERMISSION_PROFILE)
                return
        else:
            # No checkpoint receiver means there is no authority to extend the
            # grant. Remove bypass state before the next caller can resume it.
            _exit_full_access_profile(agent, READ_ONLY_PERMISSION_PROFILE)
            return

    # Continue working - start another turn
    agent.input(FULL_ACCESS_CONTINUE_PROMPT)


@before_iteration
def poll_prompt_update(agent: 'Agent') -> None:
    """Poll for prompt_update signals — frontend can update goal/direction mid-session."""
    if not agent.io:
        return
    for msg in agent.io.receive_all('prompt_update'):
        agent.current_session['full_access_prompt'] = msg.get('prompt', '')


@before_llm
def inject_full_access_prompt(agent: 'Agent') -> None:
    """Inject saved prompt into system message so agent remembers goal every turn."""
    prompt = agent.current_session.get('full_access_prompt')
    if not prompt:
        return
    messages = agent.current_session['messages']
    if messages and messages[0]['role'] == 'system':
        base = messages[0]['content'].split('\n\n[Prompt]')[0]
        messages[0]['content'] = f"{base}\n\n[Prompt]\n{prompt}"


# Full access is the canonical API. YOLO is the recognizable shorthand.
full_access = [
    activate_configured_full_access,
    full_access_keep_working,
    poll_prompt_update,
    inject_full_access_prompt,
]
yolo = full_access

# One source-compatibility window for callers of the previous function name.
handle_full_access_mode_change = handle_full_access_permission_profile_change

__all__ = [
    'yolo',
    'enable_full_access',
    'enable_yolo',
    'handle_yolo_mode_change',
    'YOLO_DEFAULT_TURNS',
    'YOLO_CONTINUE_PROMPT',
    'full_access',
    'activate_configured_full_access',
    'handle_full_access_permission_profile_change',
    'FULL_ACCESS_DEFAULT_TURNS',
    'FULL_ACCESS_CONTINUE_PROMPT',
]
