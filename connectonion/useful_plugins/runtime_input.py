"""
Purpose: Apply mid-execution user input from io to message history at iteration boundaries
LLM-Note:
  Dependencies: imports from [core/events (before_iteration)] | imported by [useful_plugins/__init__.py] | tested by [tests/unit/test_runtime_input.py]
  Data flow: ws_router pushes runtime input to agent.io._runtime_inputs via push_runtime_input() → @before_iteration handler pulls them at iteration start → wrapped in RUNTIME_INPUT_FRAME_PREFIX (additive framing for LLM) → appended to messages as user role → user_input trace emitted with runtime_input: true → session_to_chat_items strips prefix when rendering user bubble
  State/Effects: mutates agent.current_session['messages'] | emits user_input trace events
  Integration: exports runtime_input plugin (single before_iteration handler) + RUNTIME_INPUT_FRAME_PREFIX constant | plugin opt-in via Agent(plugins=[runtime_input]) for hosted agents that should accept mid-execution user input
  Errors: silent no-op when agent.io is None or doesn't support pop_runtime_inputs
"""

from typing import TYPE_CHECKING

from ..core.events import before_iteration

if TYPE_CHECKING:
    from ..core.agent import Agent


RUNTIME_INPUT_FRAME_PREFIX = (
    "[The user sent this while you were working on the previous request. "
    "Treat it as additional context or a follow-up — do NOT abandon the "
    "original task unless they explicitly say to stop or replace it. "
    "Address both the original request and this new input in your response.]\n\n"
)


@before_iteration
def apply_runtime_input(agent: "Agent") -> None:
    """Pull mid-execution user messages from io and append to message history."""
    if not agent.io or not hasattr(agent.io, 'pop_runtime_inputs'):
        return
    for msg in agent.io.pop_runtime_inputs():
        prompt = msg.get('prompt')
        if not prompt:
            continue
        framed = RUNTIME_INPUT_FRAME_PREFIX + prompt
        agent.current_session['messages'].append({"role": "user", "content": framed})
        agent._record_trace({
            'type': 'user_input',
            'id': msg.get('id'),
            'content': prompt,
            'turn': agent.current_session.get('turn', 0),
            'iteration': agent.current_session['iteration'],
            'runtime_input': True,
        })


runtime_input = [apply_runtime_input]
