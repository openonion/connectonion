"""
Purpose: Execute agent tools with xray context injection, timing, error handling, and trace recording
LLM-Note:
  Dependencies: imports from [time, json, typing, xray.py] | imported by [agent.py] | tested by [tests/unit/test_tool_executor.py]
  Data flow: receives Agent tool calls → injects xray → hosted agent-aware tools use a copied session/revocable IO; opted-in stateful tools also fork → commit completed calls → record result and clear xray
  State/Effects: mutates agent.current_session['messages'] by appending assistant message with tool_calls and tool result messages | mutates agent.current_session['trace'] by appending tool_call then tool_result entries | calls logger.log_tool_call() and logger.log_tool_result() for user feedback | injects/clears xray context via thread-local storage
  Integration: exposes execute_and_record_tools(tool_calls, tools, agent, logger), execute_single_tool(...) | uses logger.log_tool_call(name, args) for natural function-call style output: greet(name='Alice') | creates trace entries with type, tool_name, arguments, call_id, result, status, timing, iteration, timestamp
  Performance: times each tool execution in milliseconds | executes tools sequentially (not parallel) | trace entry added BEFORE auto-trace so xray.trace() sees it | agent injection uses cached _needs_agent flag (set by tool_factory) instead of inspect.signature() for zero overhead
  Errors: catches all tool execution exceptions | wraps errors in trace_entry with error, error_type fields | returns error message to LLM for retry | prints error to logger with red ✗
"""

import asyncio
import copy
import inspect
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from ..debug.xray import clear_xray_context, inject_xray_context, is_xray_enabled
from .interrupt import InterruptibleIO, UserInterrupt, run_interruptible

_async_loop: Optional[asyncio.AbstractEventLoop] = None
_async_loop_thread: Optional[threading.Thread] = None
_async_loop_lock = threading.Lock()

STRUCTURED_OUTPUT_MAX_DEPTH = 8
STRUCTURED_OUTPUT_MAX_BYTES = 64 * 1024


def _structured_tool_output(value: Any) -> tuple[bool, Any]:
    """Return a bounded detached JSON-native copy for transport."""
    budget = [STRUCTURED_OUTPUT_MAX_BYTES]
    try:
        detached = _copy_structured_output(value, 0, set(), budget)
    except (TypeError, ValueError, OverflowError, RecursionError, RuntimeError):
        return False, None
    return True, detached


def _copy_structured_output(
    value: Any,
    depth: int,
    active: set[int],
    budget: list[int],
) -> Any:
    value_type = type(value)
    if value is None or value_type in (bool, int, float, str):
        _spend_json_scalar(value, budget)
        return value
    if value_type is list:
        return _copy_structured_list(value, depth, active, budget)
    if value_type is dict:
        return _copy_structured_dict(value, depth, active, budget)
    raise TypeError("structured tool output must be JSON-native")


def _spend_json_scalar(value: Any, budget: list[int]) -> None:
    if type(value) is float and not math.isfinite(value):
        raise ValueError("non-finite floats are not interoperable JSON")
    if type(value) is str and len(value) > STRUCTURED_OUTPUT_MAX_BYTES:
        raise ValueError("structured tool output exceeds its byte limit")
    if type(value) is int and value.bit_length() > STRUCTURED_OUTPUT_MAX_BYTES * 4:
        raise ValueError("structured tool output exceeds its byte limit")
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    _spend(len(encoded.encode("utf-8")), budget)


def _spend(size: int, budget: list[int]) -> None:
    if size > budget[0]:
        raise ValueError("structured tool output exceeds its byte limit")
    budget[0] -= size


def _copy_structured_list(
    value: list,
    depth: int,
    active: set[int],
    budget: list[int],
) -> list:
    _enter_container(value, depth, active, budget)
    detached = []
    try:
        for index, item in enumerate(value):
            if index:
                _spend(1, budget)
            detached.append(_copy_structured_output(item, depth + 1, active, budget))
        _spend(1, budget)
        return detached
    finally:
        active.remove(id(value))


def _copy_structured_dict(
    value: dict,
    depth: int,
    active: set[int],
    budget: list[int],
) -> dict:
    _enter_container(value, depth, active, budget)
    detached = {}
    try:
        for index, (key, item) in enumerate(value.items()):
            if type(key) is not str:
                raise TypeError("structured tool output keys must be strings")
            if index:
                _spend(1, budget)
            _spend_json_scalar(key, budget)
            _spend(1, budget)
            detached[key] = _copy_structured_output(item, depth + 1, active, budget)
        _spend(1, budget)
        return detached
    finally:
        active.remove(id(value))


def _enter_container(
    value: list | dict,
    depth: int,
    active: set[int],
    budget: list[int],
) -> None:
    if depth >= STRUCTURED_OUTPUT_MAX_DEPTH:
        raise ValueError("structured tool output exceeds its depth limit")
    identity = id(value)
    if identity in active:
        raise ValueError("structured tool output contains a cycle")
    active.add(identity)
    _spend(1, budget)


def _get_async_tool_loop():
    """Return the long-lived event loop used by asynchronous tools."""
    global _async_loop, _async_loop_thread

    with _async_loop_lock:
        if _async_loop is None or _async_loop.is_closed():
            ready = threading.Event()

            def run_loop():
                global _async_loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                _async_loop = loop
                ready.set()
                loop.run_forever()

            _async_loop_thread = threading.Thread(
                target=run_loop, name="connectonion-async-tools", daemon=True
            )
            _async_loop_thread.start()
            ready.wait()

    assert _async_loop is not None
    return _async_loop


def _run_async_tool(coro):
    """Run a coroutine on the shared asynchronous-tool event loop.

    Async tools share one loop so loop-bound resources (aiohttp sessions,
    playwright handles) stay usable across calls.

    Nested case: an async tool can drive another tool execution — a sub-agent
    tool calls agent.input(), which executes the sub-agent's own async tool.
    That second call arrives on the shared loop's own thread, and submitting
    back to a single-threaded loop that is blocked waiting on us would hang
    forever. Give the nested coroutine its own throwaway loop instead: it loses
    affinity with the outer loop's resources, but it completes.
    """
    loop = _get_async_tool_loop()

    if threading.current_thread() is _async_loop_thread:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="co-async-nested") as pool:
            return pool.submit(asyncio.run, coro).result()

    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def execute_and_record_tools(
    tool_calls: List,
    tools: Any,  # ToolRegistry
    agent: Any,
    logger: Any  # Logger instance
) -> None:
    """Execute requested tools and update conversation messages.

    Uses agent.current_session as single source of truth for messages and trace.

    Args:
        tool_calls: List of tool calls from LLM response
        tools: ToolRegistry containing tools
        agent: Agent instance with current_session containing messages and trace
        logger: Logger for output (always provided by Agent)
    """
    # Format and add assistant message with tool calls
    _add_assistant_message(agent.current_session['messages'], tool_calls)

    # before_tools fires ONCE before ALL tools in the batch execute
    agent._invoke_events('before_tools')

    # Execute each tool
    for i, tool_call in enumerate(tool_calls):
        # Execute the tool and get trace entry
        trace_entry = execute_single_tool(
            tool_name=tool_call.name,
            tool_args=tool_call.arguments,
            tool_id=tool_call.id,
            tools=tools,
            agent=agent,
            logger=logger
        )

        # stop_signal: swap result with clean message, mark remaining as rejected
        rejection = agent.current_session.get('stop_signal')
        if rejection:
            _add_tool_result_message(agent.current_session['messages'], tool_call.id, rejection)
            for remaining in tool_calls[i + 1:]:
                _add_tool_result_message(agent.current_session['messages'], remaining.id, "Rejected by user")
            break

        # Add result to conversation messages
        _add_tool_result_message(
            agent.current_session['messages'],
            tool_call.id,
            trace_entry["result"]
        )

        # Note: trace_entry already added to session in execute_single_tool
        # (before auto-trace, so it shows up in xray.trace() output)

        # Fire events AFTER tool result message is added (proper message ordering)
        # on_error fires first for errors/not_found
        if trace_entry["status"] in ("error", "not_found"):
            agent._invoke_events('on_error')

        # after_each_tool fires for EACH tool execution (success, error, not_found)
        # WARNING: Do NOT add messages here - it breaks Anthropic's message ordering
        agent._invoke_events('after_each_tool')

    # An interrupt exits through on_stop_signal. Do not run after_tools hooks:
    # built-in reflection can make another blocking LLM call, defeating Stop.
    if not agent.current_session.get('stop_signal'):
        # after_tools fires ONCE after ALL tools in the batch complete
        # This is the safe place to add messages (e.g., reflection) because all
        # tool_results have been added and message ordering is correct for all LLMs
        agent._invoke_events('after_tools')


def execute_single_tool(
    tool_name: str,
    tool_args: Dict,
    tool_id: str,
    tools: Any,  # ToolRegistry
    agent: Any,
    logger: Any  # Logger instance
) -> Dict[str, Any]:
    """Execute a single tool and return trace entry.

    Uses agent.current_session as single source of truth.
    Checks for __xray_enabled__ attribute to auto-print Rich tables.
    If tool has _needs_agent flag (set by tool_factory), injects agent into args
    so tools can access agent.io for frontend communication.

    Args:
        tool_name: Name of the tool to execute
        tool_args: Arguments to pass to the tool
        tool_id: ID of the tool call
        tools: ToolRegistry containing tools
        agent: Agent instance with current_session
        logger: Logger for output (always provided by Agent)

    Returns:
        Dict trace entry with: type, tool_name, arguments, call_id, result, status, timing, iteration, timestamp
    """
    # Log tool call before execution
    logger.log_tool_call(tool_name, tool_args)

    trace_entry = {
        "type": "tool_result",
        "tool_id": tool_id,  # LLM's tool call ID for client-side matching
        "name": tool_name,
        "args": tool_args,
        "status": "pending",
        "result": None,
        "timing_ms": 0,
    }

    # Every result must have a preceding start with the same stable ID.  This
    # is required by streaming clients and also avoids a completion that cannot be
    # correlated by ConnectOnion clients when the requested tool is unknown.
    agent._record_trace({
        "type": "tool_call",
        "tool_id": tool_id,
        "name": tool_name,
        "args": tool_args,
    })

    # Check if tool exists
    tool_func = tools.get(tool_name)
    if tool_func is None:
        error_msg = f"Tool '{tool_name}' not found"

        trace_entry["result"] = error_msg
        trace_entry["status"] = "not_found"
        trace_entry["error"] = error_msg

        agent._record_trace(trace_entry)
        logger.print(f"[red]✗[/red] {error_msg}")

        return trace_entry

    # Check if tool has @xray decorator
    xray_enabled = is_xray_enabled(tool_func)

    previous_tools = [
        entry.get("name") for entry in agent.current_session['trace']
        if entry.get("type") == "tool_result"
    ]

    # Inject xray context before tool execution
    inject_xray_context(
        agent=agent,
        user_prompt=agent.current_session.get('user_prompt', ''),
        messages=agent.current_session['messages'].copy(),
        iteration=agent.current_session['iteration'],
        previous_tools=previous_tools
    )

    # Initialize timing (for error case if before_tool fails)
    tool_start = time.time()
    tool_io = None
    original_session = None
    tool_session = None
    original_tools = None
    tool_tools = None
    invoke_func = tool_func
    tool_agent = agent
    original_instance = None
    tool_instance = None

    def interrupted_tool_result():
        interruption = "Interrupted by user"
        agent.current_session['stop_signal'] = interruption
        trace_entry.update({
            "timing_ms": (time.time() - tool_start) * 1000,
            "result": interruption,
            "status": "interrupted",
        })
        agent._record_trace(trace_entry)
        logger.log_tool_result(interruption, trace_entry["timing_ms"])
        return trace_entry

    try:
        # Set pending_tool for before_tool handlers to access
        agent.current_session['pending_tool'] = {
            'name': tool_name,
            'arguments': tool_args,
            'id': tool_id,
            'description': getattr(tool_func, 'description', '')
        }

        # Invoke before_each_tool events. A rejection or interrupt is control
        # flow, but pending_tool is transient in every outcome.
        try:
            agent._invoke_events('before_each_tool')
        finally:
            agent.current_session.pop('pending_tool', None)

        # Execute the tool with timing (restart timer AFTER events for accurate tool timing)
        tool_start = time.time()

        # Inject agent for tools that declare 'agent' in their signature.
        # _needs_agent is cached by tool_factory at registration time.
        # This lets tools access agent.io for frontend communication (ask_user, DiffWriter, etc.)
        # A separate dict for the call, not a mutation of the caller's.
        #
        # This used to be `tool_args['agent'] = agent`, and the trace entry holds
        # `tool_args` by reference — so between recording the trace and the
        # `finally` that popped the field, an entry containing a live Agent was
        # reachable. In host mode the forwarder thread is draining and encoding
        # those entries concurrently, so the mitigation was a race. #382.
        #
        # `agent` is plumbing, not something the model asked for, and it does not
        # belong in the record of what was called.
        call_args = tool_args
        poll_io = agent.io
        if getattr(tool_func, '_needs_agent', False):
            tool_agent = agent
            if agent.io and all(
                hasattr(type(agent.io), method)
                for method in ('receive_interruptibly', 'receive_all_interruptibly', 'take_interrupt')
            ):
                # Bind the worker to this turn's session and a revocable IO
                # lease. Session and registry-membership mutations are committed
                # only when the invocation finishes. Stateful instances remain
                # shared unless they explicitly implement the private fork/commit
                # protocol below; arbitrary Python still requires cooperative
                # cancellation for its own external side effects.
                tool_io = InterruptibleIO(agent.io)
                tool_agent = copy.copy(agent)
                original_session = agent.current_session
                tool_session = copy.deepcopy(original_session)
                tool_agent.current_session = tool_session
                tool_agent.io = tool_io
                tool_agent.events = {
                    event: list(handlers) for event, handlers in agent.events.items()
                }
                original_tools = agent.tools
                tool_tools = copy.copy(original_tools)
                tool_tools._tools = dict(original_tools._tools)
                tool_tools._instances = dict(original_tools._instances)
                tool_agent.tools = tool_tools
                bound_instance = getattr(tool_func, '_bound_instance', None)
                instance_type = type(bound_instance)
                fork_instance = getattr(instance_type, '_fork_for_tool', None)
                commit_instance = getattr(
                    instance_type, '_commit_from_tool', None
                )
                if callable(fork_instance) and callable(commit_instance):
                    original_instance = bound_instance
                    tool_instance = fork_instance(original_instance)
                    invoke_func = getattr(tool_instance, tool_name)
                    for name, instance in tool_tools._instances.items():
                        if instance is original_instance:
                            tool_tools._instances[name] = tool_instance
            elif agent.io:
                # Legacy custom IO cannot cancel a blocked receive safely.
                # Preserve graceful boundary stopping instead of abandoning a
                # worker that could steal a future response.
                poll_io = None
            call_args = {**tool_args, 'agent': tool_agent}

        def invoke_tool():
            if inspect.iscoroutinefunction(invoke_func):
                return _run_async_tool(invoke_func(**call_args))
            return invoke_func(**call_args)

        def capture_tool_outcome():
            try:
                return True, invoke_tool()
            except BaseException as error:
                return False, error

        tool_agent.current_session['_active_tool_call_id'] = tool_id
        outcome, interrupted = run_interruptible(
            capture_tool_outcome,
            poll_io,
            on_interrupt=tool_io.cancel if tool_io else None,
        )
        tool_duration = (time.time() - tool_start) * 1000  # milliseconds

        if interrupted:
            return interrupted_tool_result()

        succeeded, result = outcome
        if not succeeded and isinstance(result, UserInterrupt):
            raise result

        # An opted-in stateful fork is transactional: neither its detached
        # instance nor copied session may commit when the method fails.
        if not succeeded and original_instance is not None:
            raise result

        if original_instance is not None:
            type(original_instance)._commit_from_tool(
                original_instance, tool_instance
            )
            for name, instance in tool_tools._instances.items():
                if instance is tool_instance:
                    tool_tools._instances[name] = original_instance

        tool_agent.current_session.pop('_active_tool_call_id', None)
        if tool_session is not None:
            original_session.clear()
            original_session.update(tool_session)
            original_tools._tools.clear()
            original_tools._tools.update(tool_tools._tools)
            original_tools._instances.clear()
            original_tools._instances.update(tool_tools._instances)
        if tool_io is not None and not tool_io.commit():
            raise UserInterrupt()

        if not succeeded:
            raise result

        trace_entry["timing_ms"] = tool_duration
        trace_entry["result"] = str(result)
        trace_entry["status"] = "success"

    except UserInterrupt:
        return interrupted_tool_result()

    except Exception as e:
        # Calculate timing from initial start (includes before_tool if it succeeded)
        tool_duration = (time.time() - tool_start) * 1000

        trace_entry["timing_ms"] = tool_duration
        trace_entry["status"] = "error"
        trace_entry["error"] = str(e)
        trace_entry["error_type"] = type(e).__name__

        # Always include schema info so LLM knows how to fix the call
        schema = getattr(tool_func, 'get_parameters_schema', lambda: {})()
        required = schema.get('required', [])
        properties = list(schema.get('properties', {}).keys())

        error_msg = f"Error: {str(e)}"
        error_msg += f"\n\nTool '{tool_name}' schema: required={required}, all_params={properties}, you_provided={list(tool_args.keys())}"
        trace_entry["result"] = error_msg

        agent._record_trace(trace_entry)

        time_str = f"{tool_duration/1000:.4f}s" if tool_duration < 100 else f"{tool_duration/1000:.1f}s"
        logger.print(f"[red]✗[/red] Error ({time_str}): {str(e)}")

        # Note: on_error event will fire in execute_and_record_tools after result message added

    else:
        wire_extras = None
        if agent.io:
            try:
                structured, raw_output = _structured_tool_output(result)
            except Exception:
                structured, raw_output = False, None
            if structured:
                try:
                    matches_canonical = str(raw_output) == trace_entry["result"]
                except Exception:
                    matches_canonical = False
                if matches_canonical:
                    wire_extras = {"raw_output": raw_output}
            agent._record_trace(trace_entry, wire_extras=wire_extras)
        else:
            agent._record_trace(trace_entry)
        logger.log_tool_result(trace_entry["result"], tool_duration)

        if xray_enabled:
            logger.print_xray_table(
                tool_name=tool_name,
                tool_args=tool_args,
                result=result,
                timing=tool_duration,
                agent=agent
            )

        # after_tool fires later, after the LLM tool message is added.

    finally:
        if getattr(agent, 'current_session', None):
            agent.current_session.pop('_active_tool_call_id', None)
        if tool_session is not None:
            tool_session.pop('_active_tool_call_id', None)
        if tool_io:
            tool_io.cancel()
        # No `tool_args.pop('agent')` here any more: nothing was ever put in.
        # Clear xray context after tool execution
        clear_xray_context()

    return trace_entry


def _add_assistant_message(messages: List[Dict], tool_calls: List) -> None:
    """Format and add assistant message with tool calls.

    Preserves extra_content (e.g., Gemini 3 thought_signature) which must be
    echoed back to the LLM for certain providers to work correctly.
    See: https://ai.google.dev/gemini-api/docs/thinking#openai-sdk

    Args:
        messages: Conversation messages list (will be mutated)
        tool_calls: Tool calls from LLM response
    """
    assistant_tool_calls = []
    for tool_call in tool_calls:
        tc_dict = {
            "id": tool_call.id,
            "type": "function",
            "function": {
                "name": tool_call.name,
                "arguments": json.dumps(tool_call.arguments)
            }
        }
        # Only include extra_content if present (Gemini rejects null values)
        if tool_call.extra_content:
            tc_dict["extra_content"] = tool_call.extra_content
        assistant_tool_calls.append(tc_dict)

    messages.append({
        "role": "assistant",
        "tool_calls": assistant_tool_calls
    })


def _add_tool_result_message(messages: List[Dict], tool_id: str, result: Any) -> None:
    """Add tool result message to conversation.

    Args:
        messages: Conversation messages list (will be mutated)
        tool_id: ID of the tool call
        result: Result from tool execution
    """
    messages.append({
        "role": "tool",
        "content": str(result),
        "tool_call_id": tool_id
    })
