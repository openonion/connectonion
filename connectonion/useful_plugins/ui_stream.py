"""
Purpose: Stream agent activity to UI via Connection API
LLM-Note:
  Dependencies: imports from [typing, core.events] | imported by [useful_plugins/__init__.py] | tested by [tests/unit/test_ui_stream.py]
  Data flow: Event handlers check agent.connection → if present, call connection.log() to stream events
  State/Effects: Streams events to WebSocket client | no file I/O | no blocking
  Integration: exposes ui_stream list of event handlers | used via Agent(plugins=[ui_stream]) | works with host() WebSocket
  Performance: O(1) event dispatch | no blocking | no LLM calls
  Errors: Silently skips if connection is None (local execution)

UI Stream Plugin - Stream agent activity to connected UI clients.

When agent.connection is set (by host() for WebSocket connections), this plugin
streams real-time events for:
- LLM responses (thinking, tool_calls)
- Tool execution (before/after each tool)
- Errors and completion

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import ui_stream

    agent = Agent("assistant", plugins=[ui_stream])
    host(agent)  # WebSocket clients receive real-time events
"""

from typing import TYPE_CHECKING
from ..core.events import (
    after_llm,
    before_each_tool,
    after_each_tool,
    on_error,
    on_complete,
)

if TYPE_CHECKING:
    from ..core.agent import Agent


@after_llm
def stream_llm_response(agent: 'Agent') -> None:
    """Stream LLM response to connected UI."""
    if not agent.connection:
        return

    trace = agent.current_session.get('trace', [])
    if not trace:
        return

    last = trace[-1]
    if last.get('type') != 'llm_call':
        return

    # Stream content if present
    content = last.get('content', '')
    if content:
        agent.connection.log('message', content=content)

    # Stream tool calls if present
    tool_calls = last.get('tool_calls', [])
    for tc in tool_calls:
        agent.connection.log(
            'tool_pending',
            name=tc.get('function', {}).get('name', ''),
            arguments=tc.get('function', {}).get('arguments', {}),
            id=tc.get('id', ''),
        )


@before_each_tool
def stream_tool_start(agent: 'Agent') -> None:
    """Stream tool execution start to connected UI."""
    if not agent.connection:
        return

    pending = agent.current_session.get('pending_tool')
    if not pending:
        return

    agent.connection.log(
        'tool_start',
        name=pending['name'],
        arguments=pending['arguments'],
        id=pending.get('id', ''),
    )


@after_each_tool
def stream_tool_result(agent: 'Agent') -> None:
    """Stream tool execution result to connected UI."""
    if not agent.connection:
        return

    trace = agent.current_session.get('trace', [])
    if not trace:
        return

    last = trace[-1]
    if last.get('type') != 'tool_execution':
        return

    status = last.get('status', 'unknown')
    result = last.get('result', '')

    # Truncate large results for UI
    if isinstance(result, str) and len(result) > 1000:
        result = result[:1000] + '...'

    agent.connection.log(
        'tool_result',
        name=last.get('tool_name', ''),
        status=status,
        result=result,
        timing_ms=last.get('timing', 0),
    )


@on_error
def stream_error(agent: 'Agent') -> None:
    """Stream error to connected UI."""
    if not agent.connection:
        return

    trace = agent.current_session.get('trace', [])
    if not trace:
        return

    last = trace[-1]
    if last.get('status') != 'error':
        return

    agent.connection.log(
        'error',
        tool_name=last.get('tool_name', ''),
        error=str(last.get('error', '')),
    )


@on_complete
def stream_complete(agent: 'Agent') -> None:
    """Stream completion to connected UI."""
    if not agent.connection:
        return

    trace = agent.current_session.get('trace', [])
    tools_used = [t.get('tool_name', '') for t in trace if t.get('type') == 'tool_execution']
    llm_calls = len([t for t in trace if t.get('type') == 'llm_call'])

    agent.connection.log(
        'complete',
        tools_used=tools_used,
        llm_calls=llm_calls,
        iterations=agent.current_session.get('iteration', 0),
    )


# Bundle as plugin
ui_stream = [
    stream_llm_response,
    stream_tool_start,
    stream_tool_result,
    stream_error,
    stream_complete,
]
