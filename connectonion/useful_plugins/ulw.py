"""
Purpose: ULW (Ultra Light Work) plugin - keep improving until truly good enough
LLM-Note:
  Dependencies: imports from [core/events.py] | imported by [useful_plugins/__init__.py]
  Data flow: on_complete fires → check if result says "genuinely complete" → if not and rounds < max, call agent.input() again
  State/Effects: tracks _ulw_rounds in current_session (private, underscore prefix)
  Integration: pure plugin, no core changes needed, composable with other plugins
  Errors: no explicit error handling, agent.input() failures propagate

ULW Mode - Ultra Light Work.

When in ULW mode:
1. Agent completes its initial task
2. Plugin intercepts and prompts agent to self-critique
3. Agent continues improving until it says "genuinely complete" or max_rounds reached

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import ulw

    agent = Agent("worker", plugins=[ulw])

    # With custom max rounds:
    from connectonion.useful_plugins.ulw import UltraWork
    agent = Agent("worker", plugins=[UltraWork(max_rounds=3)])
"""

from typing import TYPE_CHECKING

from ..core.events import on_complete

if TYPE_CHECKING:
    from ..core.agent import Agent


ULW_DEFAULT_MAX_ROUNDS = 5

ULW_CONTINUE_PROMPT = """Review what you've done so far. Consider:
- Are there edge cases not handled?
- Could the code be cleaner or simpler?
- Are there missing tests or documentation?
- Any obvious improvements?

Continue improving, or say "genuinely complete" if nothing meaningful left to do."""


def _make_ulw_handler(max_rounds: int):
    @on_complete
    def ulw_keep_working(agent: 'Agent') -> None:
        """If rounds remaining and not genuinely complete, start another improvement round."""
        rounds_used = agent.current_session.get('_ulw_rounds', 0)

        if rounds_used >= max_rounds:
            return

        result = agent.current_session.get('result', '') or ''
        if 'genuinely complete' in result.lower():
            return

        agent.current_session['_ulw_rounds'] = rounds_used + 1
        agent.input(ULW_CONTINUE_PROMPT)

    return ulw_keep_working


# Default plugin: max 5 improvement rounds
ulw = [_make_ulw_handler(ULW_DEFAULT_MAX_ROUNDS)]


def UltraWork(max_rounds: int = ULW_DEFAULT_MAX_ROUNDS) -> list:
    """Create a ULW plugin with custom max rounds.

    Args:
        max_rounds: Maximum improvement iterations before stopping (default: 5)

    Returns:
        Plugin list ready to pass to Agent(plugins=[...])

    Example:
        agent = Agent("worker", plugins=[UltraWork(max_rounds=3)])
    """
    return [_make_ulw_handler(max_rounds)]


__all__ = ['ulw', 'UltraWork', 'ULW_DEFAULT_MAX_ROUNDS', 'ULW_CONTINUE_PROMPT']
