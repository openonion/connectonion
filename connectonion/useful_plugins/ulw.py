"""
Purpose: ULW (Ultra Light Work) plugin - autonomous agent mode with turn-based checkpoints
LLM-Note:
  Dependencies: imports from [core/events.py] | imported by [useful_plugins/__init__.py]
  Data flow: mode_change to 'ulw' → set skip_tool_approval=True → on_complete fires → continue until max turns
  State/Effects: sets mode, ulw_turns, ulw_turns_used, skip_tool_approval in session
  Integration: communicates with tool_approval via skip_tool_approval flag in session
  Errors: no explicit error handling, agent.input() failures propagate

ULW Mode - Ultra Light Work.

When in ULW mode:
1. All tool approvals are skipped (via skip_tool_approval flag)
2. Agent keeps working until max turns reached
3. At checkpoint, user can continue, switch mode, or stop

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import tool_approval, ulw

    agent = Agent("worker", plugins=[tool_approval, ulw])
"""

from typing import TYPE_CHECKING

from ..core.events import on_complete, before_iteration, before_llm

if TYPE_CHECKING:
    from ..core.agent import Agent


ULW_DEFAULT_TURNS = 100

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


def handle_ulw_mode_change(agent: 'Agent', turns: int = None) -> None:
    """Handle mode change to ULW.

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
    old_mode = agent.current_session.get('mode', 'safe')

    # Set ULW state
    agent.current_session['mode'] = 'ulw'
    agent.current_session['ulw_turns'] = turns or ULW_DEFAULT_TURNS
    agent.current_session['ulw_turns_used'] = 0
    agent.current_session['skip_tool_approval'] = True

    # Notify frontend
    if agent.io:
        agent.io.send({'type': 'mode_changed', 'mode': 'ulw', 'triggered_by': 'user'})

    _log(agent, f"[cyan]Mode changed: {old_mode} → ulw ({agent.current_session['ulw_turns']} turns)[/cyan]")


def _exit_ulw_mode(agent: 'Agent', new_mode: str = 'safe') -> None:
    """Exit ULW mode and switch to another mode.

    Cleans up ULW state and clears skip_tool_approval flag.
    """
    agent.current_session.pop('skip_tool_approval', None)
    agent.current_session.pop('ulw_turns', None)
    agent.current_session.pop('ulw_turns_used', None)
    agent.current_session['mode'] = new_mode

    if agent.io:
        agent.io.send({'type': 'mode_changed', 'mode': new_mode, 'triggered_by': 'ulw_checkpoint'})

    _log(agent, f"[cyan]Exited ULW mode → {new_mode}[/cyan]")


@on_complete
def ulw_keep_working(agent: 'Agent') -> None:
    """If ULW mode and turns remaining, start another turn."""
    mode = agent.current_session.get('mode')
    if mode != 'ulw':
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
                extend = response.get('turns', ULW_DEFAULT_TURNS)
                agent.current_session['ulw_turns'] += extend
                _log(agent, f"[cyan]ULW extended: +{extend} turns[/cyan]")
                # Fall through to continue working
            elif action == 'switch_mode':
                # Switch to another mode
                new_mode = response.get('mode', 'safe')
                _exit_ulw_mode(agent, new_mode)
                return  # Stop working
            else:
                # Unknown action or stop - exit to safe mode
                _exit_ulw_mode(agent, 'safe')
                return
        else:
            # No IO, truly complete
            return

    # Continue working - start another turn
    agent.input(ULW_CONTINUE_PROMPT)


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
ulw = [ulw_keep_working, poll_prompt_update, inject_ulw_prompt]

# Export mode handler for external use
__all__ = ['ulw', 'handle_ulw_mode_change', 'ULW_DEFAULT_TURNS']
