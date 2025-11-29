"""
Purpose: Event system for hooking into agent lifecycle
LLM-Note:
  Dependencies: None (standalone module) | imported by [agent.py, __init__.py] | tested by [tests/test_events.py]
  Data flow: Wrapper functions tag event handlers with _event_type attribute → Agent organizes handlers by type → Agent invokes handlers at specific lifecycle points passing agent instance
  State/Effects: Event handlers receive agent instance and can modify agent.current_session (messages, trace, etc.)
  Integration: exposes after_user_input(), before_llm(), after_llm(), before_tool(), after_tool(), on_error(), on_complete() | supports both decorator (@before_tool) and wrapper (before_tool(fn1, fn2)) syntax
  Performance: Minimal overhead - just function attribute checking and iteration over handler lists
  Errors: Event handler exceptions propagate and stop agent execution (fail fast)
"""

from typing import Callable, List, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import Agent

# Event handler type: function that takes Agent and returns None
EventHandler = Callable[['Agent'], None]


def after_user_input(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as after_user_input event handlers.

    Fires once per turn, after user input is added to session.
    Use for: adding context, timestamps, initializing turn state.

    Supports both decorator and wrapper syntax:
        # As decorator
        @after_user_input
        def add_timestamp(agent):
            ...

        # As wrapper (single or multiple)
        on_events=[after_user_input(handler1, handler2)]
    """
    for fn in funcs:
        fn._event_type = 'after_user_input'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)


def before_llm(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as before_llm event handlers.

    Fires before each LLM call (multiple times per turn).
    Use for: modifying messages for specific LLM calls.

    Supports both decorator and wrapper syntax:
        @before_llm
        def inject_context(agent):
            ...

        on_events=[before_llm(handler1, handler2)]
    """
    for fn in funcs:
        fn._event_type = 'before_llm'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)


def after_llm(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as after_llm event handlers.

    Fires after each LLM response (multiple times per turn).
    Use for: logging LLM calls, analyzing responses.

    Supports both decorator and wrapper syntax:
        @after_llm
        def log_llm(agent):
            trace = agent.current_session['trace'][-1]
            if trace['type'] == 'llm_call':
                print(f"LLM took {trace['duration_ms']:.0f}ms")

        on_events=[after_llm(log_llm)]
    """
    for fn in funcs:
        fn._event_type = 'after_llm'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)


def before_tool(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as before_tool event handlers.

    Fires before each tool execution.
    Use for: validating arguments, approval prompts, logging.

    Access pending tool via agent.current_session['pending_tool']:
        - name: Tool name (e.g., "bash")
        - arguments: Tool arguments dict
        - id: Tool call ID

    Raise an exception to cancel the tool execution.

    Supports both decorator and wrapper syntax:
        @before_tool
        def approve_dangerous(agent):
            ...

        # Multiple handlers
        on_events=[before_tool(check_shell, check_email)]
    """
    for fn in funcs:
        fn._event_type = 'before_tool'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)


def after_tool(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as after_tool event handlers.

    Fires after each tool execution (success, error, or not_found).
    Use for: adding reflection, logging performance.

    Supports both decorator and wrapper syntax:
        @after_tool
        def add_reflection(agent):
            trace = agent.current_session['trace'][-1]
            if trace['type'] == 'tool_execution' and trace['status'] == 'success':
                print(f"Tool completed: {trace['tool_name']}")

        on_events=[after_tool(handler1, handler2)]
    """
    for fn in funcs:
        fn._event_type = 'after_tool'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)


def on_error(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as on_error event handlers.

    Fires when tool execution fails.
    Use for: custom error handling, retries, fallback values.

    Supports both decorator and wrapper syntax:
        @on_error
        def handle_error(agent):
            trace = agent.current_session['trace'][-1]
            if trace.get('status') == 'error':
                print(f"Tool failed: {trace['error']}")

        on_events=[on_error(handler1, handler2)]
    """
    for fn in funcs:
        fn._event_type = 'on_error'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)


def on_complete(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as on_complete event handlers.

    Fires once per input() call, after final response is generated.
    Use for: metrics, logging, cleanup, final summary.

    Supports both decorator and wrapper syntax:
        @on_complete
        def log_done(agent):
            trace = agent.current_session['trace']
            tools_used = [t['tool_name'] for t in trace if t['type'] == 'tool_execution']
            print(f"Task done. Tools: {tools_used}")

        on_events=[on_complete(handler1, handler2)]
    """
    for fn in funcs:
        fn._event_type = 'on_complete'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)