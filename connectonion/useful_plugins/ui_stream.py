"""
Purpose: Plugin for streaming agent completion summaries to WebSocket UI clients
LLM-Note:
  Dependencies: imports from [core/events.py on_complete, typing] | imported by [useful_plugins/__init__.py, user code] | tested by [tests/plugins/test_ui_stream.py]
  Data flow: fires on_complete event → extracts trace from current_session → counts tools_used and llm_calls → sends via agent.io.log('complete', tools_used, llm_calls, iterations) → WebSocket client receives completion event
  State/Effects: sends message via agent.io (if connected) | no persistent state | read-only access to session trace
  Integration: exposes ui_stream plugin (use via plugins=[ui_stream]) | only fires if agent.io exists (hosted mode) | complements direct events from agent.py/tool_executor.py | stream_complete handler decorated with @on_complete
  Performance: minimal overhead (just counting trace entries) | single io.log call
  Errors: returns early if no io connection | no exceptions raised
UI Stream Plugin - Stream agent completion summary to connected UI clients.

Events (user_input, thinking, tool_result, assistant) are now emitted directly
from their source (agent.py, tool_executor.py, plugins). This plugin only
handles the completion summary.

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import ui_stream

    agent = Agent("assistant", plugins=[ui_stream])
    host(agent)  # WebSocket clients receive real-time events
"""

from typing import TYPE_CHECKING
from ..core.events import on_complete

if TYPE_CHECKING:
    from ..core.agent import Agent


@on_complete
def stream_complete(agent: 'Agent') -> None:
    """Stream completion summary to connected UI."""
    if not agent.io:
        return

    trace = agent.current_session.get('trace', [])
    tools_used = [t.get('name', '') for t in trace if t.get('type') == 'tool_result']
    llm_calls = len([t for t in trace if t.get('type') == 'llm_call'])

    agent.io.log(
        'complete',
        tools_used=tools_used,
        llm_calls=llm_calls,
        iterations=agent.current_session.get('iteration', 0),
    )


ui_stream = [stream_complete]
