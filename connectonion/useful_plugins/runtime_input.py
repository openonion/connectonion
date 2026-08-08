"""
Purpose: Apply mid-execution user input without losing final-iteration arrivals
LLM-Note:
  Dependencies: imports from [core/events (after_user_input, before_iteration, after_iteration)] | imported by [useful_plugins/__init__.py] | tested by [tests/unit/test_runtime_input.py]
  Data flow: ws_router pushes accepted runtime input to agent.io → @before_iteration drains ordinary arrivals; @after_iteration atomically drains-or-seals a final no-tool response → pending final input sets _continue_iteration so the LLM answers it → framed user message + trace → session_to_chat_items strips the frame prefix
  State/Effects: mutates agent.current_session['messages'] | emits user_input trace events
  Integration: exports runtime_input plugin (turn-open, iteration-start, final-boundary handlers) + RUNTIME_INPUT_FRAME_PREFIX constant | plugin opt-in via Agent(plugins=[runtime_input]) for hosted agents that should accept mid-execution user input
  Errors: silent no-op when agent.io is None or doesn't support pop_runtime_inputs
"""

from typing import TYPE_CHECKING

from ..core.events import after_iteration, after_user_input, before_iteration

if TYPE_CHECKING:
    from ..core.agent import Agent


RUNTIME_INPUT_FRAME_PREFIX = (
    "[The user sent this while you were working on the previous request. "
    "Treat it as additional context or a follow-up — do NOT abandon the "
    "original task unless they explicitly say to stop or replace it. "
    "Address both the original request and this new input in your response.]\n\n"
)


def _append_runtime_inputs(agent: "Agent", messages: list[dict]) -> bool:
    """Append a drained batch and report whether it contained usable input."""
    appended = False
    for msg in messages:
        prompt = msg.get('prompt')
        if not prompt:
            continue
        appended = True
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
    return appended


@after_user_input
def open_runtime_input_window(agent: "Agent") -> None:
    """Re-open acceptance when a reused IO starts another agent turn."""
    opener = getattr(agent.io, 'open_runtime_inputs', None) if agent.io else None
    if opener:
        opener()


@before_iteration
def apply_runtime_input(agent: "Agent") -> None:
    """Pull input queued before an iteration starts."""
    if not agent.io or not hasattr(agent.io, 'pop_runtime_inputs'):
        return
    _append_runtime_inputs(agent, agent.io.pop_runtime_inputs())


@after_iteration
def apply_runtime_input_before_completion(agent: "Agent") -> None:
    """Drain input that arrived during a final no-tool LLM call."""
    messages = agent.current_session.get('messages', [])
    if not messages or messages[-1].get('role') != 'assistant':
        return
    if messages[-1].get('tool_calls'):
        return
    if not agent.io or not hasattr(agent.io, 'pop_runtime_inputs'):
        return

    finish = getattr(agent.io, 'finish_runtime_inputs', None)
    pending = finish() if finish else agent.io.pop_runtime_inputs()
    if _append_runtime_inputs(agent, pending):
        agent.current_session['_continue_iteration'] = True


runtime_input = [
    open_runtime_input_window,
    apply_runtime_input,
    apply_runtime_input_before_completion,
]
