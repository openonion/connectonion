"""
Purpose: Full access (YOLO) plugin - autonomous agent mode with turn-based checkpoints
LLM-Note:
  Dependencies: imports from [core/events.py] | imported by [useful_plugins/__init__.py]
  Data flow: mode_change to 'full_access' → set skip_tool_approval=True → on_complete fires → continue until max turns
  State/Effects: sets mode, full_access_turns, full_access_turns_used, skip_tool_approval in session
  Integration: communicates with tool_approval via skip_tool_approval flag in session
  Errors: no explicit error handling, agent.input() failures propagate

Full access mode (YOLO).

When in Full access mode:
1. All tool approvals are skipped (via skip_tool_approval flag)
2. Agent keeps working until max turns reached
3. At checkpoint, user can continue, switch mode, or stop

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import tool_approval, full_access

    agent = Agent("worker", plugins=[tool_approval, full_access])
"""

from typing import TYPE_CHECKING

from ..core.approval_modes import (
    AUTO_APPROVE_MODE,
    DEFAULT_MODE,
    FULL_ACCESS_MODE,
    legacy_approval_mode_id,
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


def handle_full_access_mode_change(agent: 'Agent', turns: int = None) -> None:
    """Handle mode change to Full access.

    Called when frontend sends { type: 'mode_change', mode: 'full_access', turns: N }

    Sets up Full access state:
    - mode = 'full_access'
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

    old_mode = agent.current_session.get('mode', DEFAULT_MODE)

    # Set Full access state
    agent.current_session['mode'] = FULL_ACCESS_MODE
    agent.current_session['full_access_turns'] = turns
    agent.current_session['full_access_turns_used'] = 0
    agent.current_session['skip_tool_approval'] = True

    # Notify frontend
    if agent.io:
        agent.io.send({'type': 'mode_changed', 'mode': FULL_ACCESS_MODE, 'triggered_by': 'user'})

    _log(agent, f"[cyan]Mode changed: {old_mode} → full_access ({agent.current_session['full_access_turns']} turns)[/cyan]")


def handle_yolo_mode_change(agent: 'Agent', turns: int = None) -> None:
    """Recognizable shorthand for :func:`handle_full_access_mode_change`."""
    handle_full_access_mode_change(agent, turns)


def enable_full_access(agent: 'Agent', turns: int = None) -> None:
    """Configure approval-free autonomous mode before the agent's first input."""
    turns = _positive_turn_count(turns, default=FULL_ACCESS_DEFAULT_TURNS)

    agent._yolo_turns = turns
    agent._yolo_needs_activation = True
    if agent.current_session is not None:
        handle_full_access_mode_change(agent, turns)
        agent._yolo_needs_activation = False


def enable_yolo(agent: 'Agent', turns: int = None) -> None:
    """Recognizable shorthand for :func:`enable_full_access`."""
    enable_full_access(agent, turns)


@after_user_input
def activate_configured_full_access(agent: 'Agent') -> None:
    """Enter configured Full access mode before the first LLM or tool call."""
    turns = getattr(agent, '_yolo_turns', None)
    needs_activation = getattr(agent, '_yolo_needs_activation', False)
    if turns is None or (
        not needs_activation and agent.current_session.get('mode') == FULL_ACCESS_MODE
    ):
        return
    handle_full_access_mode_change(agent, turns)
    agent._yolo_needs_activation = False


def _exit_full_access_mode(agent: 'Agent', new_mode: str = DEFAULT_MODE) -> None:
    """Exit Full access mode and switch to another mode.

    Cleans up Full access state and clears skip_tool_approval flag.
    """
    agent.current_session.pop('skip_tool_approval', None)
    agent.current_session.pop('full_access_turns', None)
    agent.current_session.pop('full_access_turns_used', None)
    agent.current_session.pop('full_access_prompt', None)
    agent.current_session['mode'] = new_mode

    if agent.io:
        agent.io.send({'type': 'mode_changed', 'mode': new_mode, 'triggered_by': 'full_access_checkpoint'})

    _log(agent, f"[cyan]Exited Full access mode → {new_mode}[/cyan]")


@on_complete
def full_access_keep_working(agent: 'Agent') -> None:
    """If Full access mode and turns remaining, start another turn."""
    mode = agent.current_session.get('mode')
    if mode != FULL_ACCESS_MODE:
        return

    # Validate restored/local state before it can keep approval bypass active.
    raw_used = agent.current_session.get('full_access_turns_used')
    try:
        max_turns = _positive_turn_count(
            agent.current_session.get('full_access_turns'),
        )
    except ValueError:
        _exit_full_access_mode(agent, DEFAULT_MODE)
        return
    if (
        isinstance(raw_used, bool)
        or not isinstance(raw_used, int)
        or raw_used < 0
        or raw_used >= max_turns
    ):
        _exit_full_access_mode(agent, DEFAULT_MODE)
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
            _exit_full_access_mode(agent, DEFAULT_MODE)
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
                    _exit_full_access_mode(agent, DEFAULT_MODE)
                    return
                agent.current_session['full_access_turns'] += extend
                _log(agent, f"[cyan]Full access extended: +{extend} turns[/cyan]")
                # Fall through to continue working
            elif action == 'switch_mode':
                # A checkpoint may leave Full access only for a bounded mode.
                # Re-selecting Full access here would bypass the transaction
                # that establishes its turn budget.
                try:
                    new_mode = legacy_approval_mode_id(
                        response.get('mode', DEFAULT_MODE)
                    )
                except ValueError:
                    new_mode = DEFAULT_MODE
                if new_mode not in {DEFAULT_MODE, AUTO_APPROVE_MODE}:
                    new_mode = DEFAULT_MODE
                _exit_full_access_mode(agent, new_mode)
                return  # Stop working
            else:
                # Unknown action or stop - exit to Default
                _exit_full_access_mode(agent, DEFAULT_MODE)
                return
        else:
            # No checkpoint receiver means there is no authority to extend the
            # grant. Remove bypass state before the next caller can resume it.
            _exit_full_access_mode(agent, DEFAULT_MODE)
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

# Export mode handlers for external use.
__all__ = [
    'yolo',
    'enable_full_access',
    'enable_yolo',
    'handle_yolo_mode_change',
    'YOLO_DEFAULT_TURNS',
    'YOLO_CONTINUE_PROMPT',
    'full_access',
    'activate_configured_full_access',
    'handle_full_access_mode_change',
    'FULL_ACCESS_DEFAULT_TURNS',
    'FULL_ACCESS_CONTINUE_PROMPT',
]
