"""
Purpose: Event system for hooking into agent lifecycle
LLM-Note:
  Dependencies: None (standalone module) | imported by [agent.py, __init__.py] | tested by [tests/test_events.py]
  Data flow: Wrapper functions tag event handlers with _event_type attribute → Agent organizes handlers by type → Agent invokes handlers at specific lifecycle points passing agent instance
  State/Effects: Event handlers receive agent instance and can modify agent.current_session (messages, trace, etc.)
  Integration: exposes on_agent_ready(), after_user_input(), before_iteration(), after_iteration(), before_llm(), after_llm(), before_each_tool(), before_tools(), after_each_tool(), after_tools(), on_error(), on_complete(), on_stop_signal(), on_tool_not_found()
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


def before_iteration(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as before_iteration event handlers.

    Fires at the start of each iteration (LLM decision cycle).
    Use for: polling IO for mode changes, initializing iteration state.

    Supports both decorator and wrapper syntax:
        @before_iteration
        def poll_io(agent):
            if agent.io:
                msg = agent.io.poll()
                if msg:
                    handle_message(agent, msg)

        on_events=[before_iteration(handler1, handler2)]
    """
    for fn in funcs:
        fn._event_type = 'before_iteration'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)


def after_iteration(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as after_iteration event handlers.

    Fires at the end of each iteration (after LLM + tools complete).
    Use for: metrics, checkpoints, cleanup after each cycle.

    Supports both decorator and wrapper syntax:
        @after_iteration
        def log_iteration(agent):
            iteration = agent.current_session.get('iteration', 0)
            print(f"Iteration {iteration} complete")

        on_events=[after_iteration(handler1, handler2)]
    """
    for fn in funcs:
        fn._event_type = 'after_iteration'  # type: ignore
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


def before_each_tool(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as before_each_tool event handlers.

    Fires before EACH individual tool execution.
    Use for: validating arguments, approval prompts, logging.

    Access pending tool via agent.current_session['pending_tool']:
        - name: Tool name (e.g., "bash")
        - arguments: Tool arguments dict
        - id: Tool call ID

    Raise an exception to cancel the tool execution.

    Supports both decorator and wrapper syntax:
        @before_each_tool
        def approve_dangerous(agent):
            ...

        # Multiple handlers
        on_events=[before_each_tool(check_shell, check_email)]
    """
    for fn in funcs:
        fn._event_type = 'before_each_tool'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)


def before_tools(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as before_tools event handlers.

    Fires ONCE before ALL tools in a batch execute.

    What is a "tools batch"?
    When the LLM responds, it can request multiple tools at once. For example:
        LLM Response: tool_calls = [search("python"), read_file("docs.md"), calculate(2+2)]

    This group of tools from ONE LLM response is called a "tools batch".
    - before_tools fires ONCE before the batch starts
    - after_tools fires ONCE after ALL tools in the batch complete

    Use for: batch validation, user approval before execution, setup.

    Supports both decorator and wrapper syntax:
        @before_tools
        def log_batch_start(agent):
            ...

        on_events=[before_tools(handler)]
    """
    for fn in funcs:
        fn._event_type = 'before_tools'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)


def after_each_tool(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as after_each_tool event handlers.

    Fires after EACH individual tool execution (success, error, or not_found).
    Use for: logging individual tool performance, debugging.

    ⚠️  WARNING: Do NOT add messages to agent.current_session['messages'] here!
    When LLM returns multiple tool_calls, this fires after EACH tool, which would
    interleave messages between tool results. This breaks Anthropic Claude's API
    which requires all tool_results to immediately follow the tool_use message.

    If you need to add messages after tools complete, use `after_tools` instead.

    Supports both decorator and wrapper syntax:
        @after_each_tool
        def log_tool(agent):
            trace = agent.current_session['trace'][-1]
            if trace['type'] == 'tool_execution':
                print(f"Tool: {trace['tool_name']} in {trace['timing']:.0f}ms")

        on_events=[after_each_tool(handler1, handler2)]
    """
    for fn in funcs:
        fn._event_type = 'after_each_tool'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)


def after_tools(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as after_tools event handlers.

    Fires ONCE after ALL tools in a batch complete.

    What is a "tools batch"?
    When the LLM responds, it can request multiple tools at once. For example:
        LLM Response: tool_calls = [search("python"), read_file("docs.md"), calculate(2+2)]

    This group of tools from ONE LLM response is called a "tools batch".
    - before_tools fires ONCE before the batch starts
    - after_tools fires ONCE after ALL tools in the batch complete

    This is the SAFE place to add messages to agent.current_session['messages']
    after tool execution, because all tool_results have been added and message
    ordering is correct for all LLM providers (including Anthropic Claude).

    Message ordering when this event fires:
        - assistant (with tool_calls)
        - tool result 1
        - tool result 2
        - tool result N
        - [YOUR MESSAGE HERE - safe to add]

    Use for: reflection/reasoning injection, ReAct pattern, batch cleanup.

    Supports both decorator and wrapper syntax:
        @after_tools
        def add_reflection(agent):
            trace = agent.current_session['trace']
            recent = [t for t in trace if t['type'] == 'tool_execution'][-3:]
            agent.current_session['messages'].append({
                'role': 'assistant',
                'content': f"Completed {len(recent)} tools"
            })

        on_events=[after_tools(add_reflection)]
    """
    for fn in funcs:
        fn._event_type = 'after_tools'  # type: ignore
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


def on_agent_ready(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as on_agent_ready event handlers.

    Fires ONCE during agent initialization, when the agent is ready to use.
    At this point, all core components are initialized and available:
    - agent.name, agent.logger, agent.model
    - agent.events (all event handlers registered)
    - agent.tools (ToolRegistry with initial tools)
    - agent.llm (LLM instance created)
    - agent.system_prompt (can be modified)

    Use for: registering tools dynamically, modifying system_prompt, plugin setup.

    Supports both decorator and wrapper syntax:
        @on_agent_ready
        def register_task_tool(agent):
            agent.add_tool(task)
            agent.system_prompt += "\\n\\nAvailable subagents: explore, plan"

        on_events=[on_agent_ready(handler1, handler2)]
    """
    for fn in funcs:
        fn._event_type = 'on_agent_ready'  # type: ignore
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


def on_tool_not_found(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as on_tool_not_found event handlers.

    Fires when LLM requests a tool that doesn't exist.
    Handler can return a custom error message string to send to the LLM.

    Access the missing tool via agent.current_session['pending_tool']:
        - name: Tool name that was not found
        - arguments: Arguments passed to the tool
        - id: Tool call ID

    Supports both decorator and wrapper syntax:
        @on_tool_not_found
        def suggest_tool(agent) -> str:
            pending = agent.current_session['pending_tool']
            tool_name = pending['name']
            available = list(agent.tools._tools.keys())
            return f"Tool '{tool_name}' not found. Available: {available}"

        on_events=[on_tool_not_found(handler)]
    """
    for fn in funcs:
        fn._event_type = 'on_tool_not_found'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)


def on_stop_signal(*funcs: EventHandler) -> Union[EventHandler, List[EventHandler]]:
    """
    Mark function(s) as on_stop_signal event handlers.

    Fires when stop_signal is set in the session, before the iteration loop exits.
    Use for: cleanup of interrupted operations, saving checkpoints, rolling back
    partial changes, notifying user of interruption.

    Supports both decorator and wrapper syntax:
        @on_stop_signal
        def cleanup(agent):
            rollback_partial_changes()
            save_checkpoint(agent.current_session)
            print("⚠️  Operation interrupted - state saved")

        on_events=[on_stop_signal(handler1, handler2)]
    """
    for fn in funcs:
        fn._event_type = 'on_stop_signal'  # type: ignore
    return funcs[0] if len(funcs) == 1 else list(funcs)