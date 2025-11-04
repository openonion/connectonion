"""
Purpose: Event system for hooking into agent lifecycle
LLM-Note:
  Dependencies: None (standalone module) | imported by [agent.py, __init__.py] | tested by [tests/test_events.py]
  Data flow: Wrapper functions tag event handlers with _event_type attribute → Agent organizes handlers by type → Agent invokes handlers at specific lifecycle points passing agent instance
  State/Effects: Event handlers receive agent instance and can modify agent.current_session (messages, trace, etc.)
  Integration: exposes after_user_input(), before_llm(), after_llm(), before_tool(), after_tool(), on_error() wrapper functions | event handlers must accept (agent) parameter
  Performance: Minimal overhead - just function attribute checking and iteration over handler lists
  Errors: Event handler exceptions propagate and stop agent execution (fail fast)
"""

from typing import Callable, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import Agent

# Event handler type: function that takes Agent and returns None
EventHandler = Callable[['Agent'], None]


def after_user_input(func: EventHandler) -> EventHandler:
    """
    Wrapper for after_user_input events.

    Fires once per turn, after user input is added to session.
    Use for: adding context, timestamps, initializing turn state.

    Example:
        def add_timestamp(agent: Agent) -> None:
            from datetime import datetime
            agent.current_session['messages'].append({
                'role': 'system',
                'content': f'Time: {datetime.now()}'
            })

        agent = Agent("assistant", on_events=[after_user_input(add_timestamp)])
    """
    func._event_type = 'after_user_input'  # type: ignore
    return func


def before_llm(func: EventHandler) -> EventHandler:
    """
    Wrapper for before_llm events.

    Fires before each LLM call (multiple times per turn).
    Use for: modifying messages for specific LLM calls.

    Example:
        def inject_context(agent: Agent) -> None:
            # Modify messages before LLM sees them
            pass

        agent = Agent("assistant", on_events=[before_llm(inject_context)])
    """
    func._event_type = 'before_llm'  # type: ignore
    return func


def after_llm(func: EventHandler) -> EventHandler:
    """
    Wrapper for after_llm events.

    Fires after each LLM response (multiple times per turn).
    Use for: logging LLM calls, analyzing responses.

    Example:
        def log_llm(agent: Agent) -> None:
            trace = agent.current_session['trace'][-1]
            if trace['type'] == 'llm_call':
                print(f"LLM took {trace['duration_ms']:.0f}ms")

        agent = Agent("assistant", on_events=[after_llm(log_llm)])
    """
    func._event_type = 'after_llm'  # type: ignore
    return func


def before_tool(func: EventHandler) -> EventHandler:
    """
    Wrapper for before_tool events.

    Fires before each tool execution.
    Use for: validating arguments, logging.

    Example:
        def validate_tool_args(agent: Agent) -> None:
            trace = agent.current_session['trace'][-1]
            # Validate tool arguments
            pass

        agent = Agent("assistant", on_events=[before_tool(validate_tool_args)])
    """
    func._event_type = 'before_tool'  # type: ignore
    return func


def after_tool(func: EventHandler) -> EventHandler:
    """
    Wrapper for after_tool events.

    Fires after each successful tool execution.
    Use for: adding reflection, logging performance.

    Example:
        from connectonion import llm_do

        def add_reflection(agent: Agent) -> None:
            trace = agent.current_session['trace'][-1]
            if trace['type'] == 'tool_execution' and trace['status'] == 'success':
                reflection = llm_do(f"Reflect on: {trace['result'][:200]}")
                agent.current_session['messages'].append({
                    'role': 'assistant',
                    'content': f"💭 {reflection}"
                })

        agent = Agent("assistant", on_events=[after_tool(add_reflection)])
    """
    func._event_type = 'after_tool'  # type: ignore
    return func


def on_error(func: EventHandler) -> EventHandler:
    """
    Wrapper for on_error events.

    Fires when tool execution fails.
    Use for: custom error handling, retries, fallback values.

    Example:
        def handle_error(agent: Agent) -> None:
            trace = agent.current_session['trace'][-1]
            if trace.get('status') == 'error':
                print(f"⚠️ Tool failed: {trace['error']}")

        agent = Agent("assistant", on_events=[on_error(handle_error)])
    """
    func._event_type = 'on_error'  # type: ignore
    return func
