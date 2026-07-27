"""
Purpose: YOLO/ULW autonomous agent mode with turn-based checkpoints
LLM-Note:
  Dependencies: imports from [core/events.py] | imported by [useful_plugins/__init__.py]
  Data flow: --yolo or mode_change to 'yolo'/'ulw' → skip approvals → on_complete continues until max turns
  State/Effects: sets mode, ulw_turns, ulw_turns_used, skip_tool_approval in session
  Integration: communicates with tool_approval via skip_tool_approval flag in session
  Errors: continuation failures propagate; a stop signal exits autonomous mode

YOLO mode is the public name for approval-free autonomous work. ULW remains a
backward-compatible plugin and wire-protocol name for existing clients.

When in YOLO/ULW mode:
1. All tool approvals are skipped (via skip_tool_approval flag)
2. Agent keeps working until max turns reached
3. At checkpoint, user can continue, switch mode, or stop

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import tool_approval, yolo

    agent = Agent("worker", plugins=[tool_approval, yolo(turns=25)])
"""

from typing import TYPE_CHECKING

from ..core.events import (
    after_user_input,
    before_iteration,
    before_llm,
    on_complete,
    on_stop_signal,
)

if TYPE_CHECKING:
    from ..core.agent import Agent


ULW_DEFAULT_TURNS = 100
YOLO_DEFAULT_TURNS = ULW_DEFAULT_TURNS
AUTONOMOUS_MODES = frozenset({"yolo", "ulw"})

ULW_CONTINUE_PROMPT = """Review what you've done so far. Consider:
- Are there edge cases not handled?
- Could the code be cleaner or simpler?
- Are there missing tests or documentation?
- Any obvious improvements?

Continue improving, or say "genuinely complete" if nothing meaningful left to do."""
YOLO_CONTINUE_PROMPT = ULW_CONTINUE_PROMPT


def _log(agent: 'Agent', message: str) -> None:
    """Log message via agent's logger if available."""
    if hasattr(agent, 'logger') and agent.logger:
        agent.logger.print(message)


def _validate_turns(turns: int | None) -> int:
    """Return a positive turn budget, using the default when omitted."""
    if turns is None:
        return YOLO_DEFAULT_TURNS
    if isinstance(turns, bool) or not isinstance(turns, int) or turns <= 0:
        raise ValueError("turns must be a positive integer")
    return turns


def _activate_autonomous_mode(
    agent: 'Agent',
    mode: str,
    turns: int | None,
    *,
    label: str | None = None,
) -> None:
    """Activate a named autonomous mode while retaining ULW state keys."""
    turn_budget = _validate_turns(turns)
    old_mode = agent.current_session.get('mode', 'safe')
    display_name = label or mode

    # Keep the ulw_* keys and events stable for existing SDK and oo-chat clients.
    agent.current_session['mode'] = mode
    agent.current_session['ulw_turns'] = turn_budget
    agent.current_session['ulw_turns_used'] = 0
    agent.current_session['skip_tool_approval'] = True

    if agent.io:
        agent.io.send({'type': 'mode_changed', 'mode': mode, 'triggered_by': 'user'})

    _log(agent, f"[cyan]Mode changed: {old_mode} → {display_name} ({turn_budget} turns)[/cyan]")


def handle_yolo_mode_change(agent: 'Agent', turns: int = None) -> None:
    """Activate public YOLO mode.

    CLI callers use this public name. Runtime state and frontend messages remain
    ``ulw`` so currently deployed SDK and oo-chat clients stay compatible.
    """
    _activate_autonomous_mode(agent, 'ulw', turns, label='yolo')


def handle_ulw_mode_change(agent: 'Agent', turns: int = None) -> None:
    """Handle the legacy ULW mode change.

    Called when frontend sends { type: 'mode_change', mode: 'ulw', turns: N }

    Sets up ULW state:
    - mode = 'ulw'
    - ulw_turns = max turns before checkpoint
    - ulw_turns_used = 0
    - skip_tool_approval = True (tells tool_approval to skip all checks)

    Args:
        agent: Agent instance
        turns: Max turns before checkpoint (default: 100)
    """
    # Older clients used zero as the "use the default" sentinel. Keep that
    # wire behavior while the public YOLO API and CLI reject non-positive input.
    if turns == 0 and not isinstance(turns, bool):
        turns = None
    _activate_autonomous_mode(agent, 'ulw', turns)


def _exit_autonomous_mode(
    agent: 'Agent',
    new_mode: str = 'safe',
    *,
    triggered_by: str | None = None,
) -> None:
    """Exit YOLO/ULW mode and switch to another mode.

    Cleans up ULW state and clears skip_tool_approval flag.
    """
    old_mode = agent.current_session.get('mode', 'yolo')
    agent.current_session.pop('skip_tool_approval', None)
    agent.current_session.pop('ulw_turns', None)
    agent.current_session.pop('ulw_turns_used', None)
    agent.current_session['mode'] = new_mode

    if agent.io:
        agent.io.send({
            'type': 'mode_changed',
            'mode': new_mode,
            'triggered_by': triggered_by or f'{old_mode}_checkpoint',
        })

    _log(agent, f"[cyan]Exited {old_mode} mode → {new_mode}[/cyan]")


@on_complete
def ulw_keep_working(agent: 'Agent') -> None:
    """If YOLO/ULW mode and turns remain, start another turn."""
    mode = agent.current_session.get('mode')
    if mode not in AUTONOMOUS_MODES:
        return

    # Track turns
    turns_used = agent.current_session.get('ulw_turns_used', 0) + 1
    agent.current_session['ulw_turns_used'] = turns_used
    max_turns = agent.current_session.get('ulw_turns', ULW_DEFAULT_TURNS)

    if turns_used >= max_turns:
        # Max turns reached - pause for user (if IO available)
        if agent.io:
            agent.io.send({
                'type': 'ulw_turns_reached',
                'turns_used': turns_used,
                'max_turns': max_turns
            })
            response = agent.io.receive()

            action = response.get('action')
            if action == 'continue':
                # Extend turns and continue
                extend = _validate_turns(response.get('turns'))
                agent.current_session['ulw_turns'] += extend
                _log(agent, f"[cyan]{mode.upper()} extended: +{extend} turns[/cyan]")
                # Fall through to continue working
            elif action == 'switch_mode':
                # Switch to another mode
                new_mode = response.get('mode', 'safe')
                _exit_autonomous_mode(agent, new_mode)
                return  # Stop working
            else:
                # Unknown action or stop - exit to safe mode
                _exit_autonomous_mode(agent, 'safe')
                return
        else:
            # No IO, truly complete
            return

    # Continue working without recursively entering Agent.input().
    agent._queue_input(ULW_CONTINUE_PROMPT)


@on_stop_signal
def stop_autonomous_mode(agent: 'Agent') -> None:
    """An interrupt or hard stop must not start another autonomous turn."""
    if agent.current_session.get('mode') in AUTONOMOUS_MODES:
        agent._pending_inputs.clear()
        _exit_autonomous_mode(agent, 'safe', triggered_by='stop_signal')


@before_iteration
def poll_prompt_update(agent: 'Agent') -> None:
    """Poll for prompt_update signals — frontend can update goal/direction mid-session."""
    if not agent.io:
        return
    for msg in agent.io.receive_all('prompt_update'):
        agent.current_session['ulw_prompt'] = msg.get('prompt', '')


@before_llm
def inject_ulw_prompt(agent: 'Agent') -> None:
    """Inject saved prompt into system message so agent remembers goal every turn."""
    prompt = agent.current_session.get('ulw_prompt')
    if not prompt:
        return
    messages = agent.current_session['messages']
    if messages and messages[0]['role'] == 'system':
        base = messages[0]['content'].split('\n\n[Prompt]')[0]
        messages[0]['content'] = f"{base}\n\n[Prompt]\n{prompt}"


# Export as plugin
ulw = [
    ulw_keep_working,
    stop_autonomous_mode,
    poll_prompt_update,
    inject_ulw_prompt,
]


def yolo(turns: int = YOLO_DEFAULT_TURNS):
    """Create an auto-activating YOLO plugin with a bounded turn budget.

    Unlike the legacy ``ulw`` bundle, this plugin activates itself on the first
    user input. That makes it suitable for ``co ai --yolo`` in both one-shot and
    hosted modes without requiring a frontend mode-change message.
    """
    turn_budget = _validate_turns(turns)

    @after_user_input
    def activate_yolo(agent: 'Agent') -> None:
        if agent.current_session.get('mode') not in AUTONOMOUS_MODES:
            handle_yolo_mode_change(agent, turn_budget)

    return [activate_yolo, *ulw]


__all__ = [
    'AUTONOMOUS_MODES',
    'ULW_CONTINUE_PROMPT',
    'ULW_DEFAULT_TURNS',
    'YOLO_CONTINUE_PROMPT',
    'YOLO_DEFAULT_TURNS',
    'handle_ulw_mode_change',
    'handle_yolo_mode_change',
    'stop_autonomous_mode',
    'ulw',
    'yolo',
]
