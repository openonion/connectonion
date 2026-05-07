"""
Purpose: Drain mid-execution user interjections from io and append to message history
LLM-Note:
  Dependencies: imports from [core/events (before_iteration)] | imported by [useful_plugins/__init__.py] | tested by [tests/unit/test_interjection.py]
  Data flow: ws_router pushes interjections to agent.io._interjections via push_interjection() → @before_iteration drain pulls them at iteration start → wrapped in INTERJECTION_FRAME_PREFIX (additive framing for LLM) → appended to messages as user role → user_input trace emitted with interjection: true → session_to_chat_items strips prefix when rendering user bubble
  State/Effects: mutates agent.current_session['messages'] | emits user_input trace events
  Integration: exports interjection plugin (single before_iteration handler) + INTERJECTION_FRAME_PREFIX constant | plugin opt-in via Agent(plugins=[interjection]) for hosted agents that should accept mid-execution user input
  Errors: silent no-op when agent.io is None or doesn't support pop_interjections
"""

from typing import TYPE_CHECKING

from ..core.events import before_iteration

if TYPE_CHECKING:
    from ..core.agent import Agent


INTERJECTION_FRAME_PREFIX = (
    "[The user sent this while you were working on the previous request. "
    "Treat it as additional context or a follow-up — do NOT abandon the "
    "original task unless they explicitly say to stop or replace it. "
    "Address both the original request and this new input in your response.]\n\n"
)


@before_iteration
def drain_interjections(agent: "Agent") -> None:
    """Pull mid-execution user messages from io and append to message history."""
    if not agent.io or not hasattr(agent.io, 'pop_interjections'):
        return
    for msg in agent.io.pop_interjections():
        prompt = msg.get('prompt')
        if not prompt:
            continue
        framed = INTERJECTION_FRAME_PREFIX + prompt
        agent.current_session['messages'].append({"role": "user", "content": framed})
        agent._record_trace({
            'type': 'user_input',
            'id': msg.get('id'),
            'content': prompt,
            'turn': agent.current_session.get('turn', 0),
            'iteration': agent.current_session['iteration'],
            'interjection': True,
        })


interjection = [drain_interjections]
