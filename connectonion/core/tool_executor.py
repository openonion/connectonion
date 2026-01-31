"""
Purpose: Execute agent tools with xray context injection, timing, error handling, and trace recording
LLM-Note:
  Dependencies: imports from [time, json, typing, xray.py] | imported by [agent.py] | tested by [tests/test_tool_executor.py]
  Data flow: receives from Agent → tool_calls: List[ToolCall], tools: ToolRegistry, agent: Agent, logger: Logger → for each tool: injects xray context via inject_xray_context() → executes tool_func(**tool_args) → records timing and result → appends to agent.current_session['trace'] → clears xray context → adds tool result to messages
  State/Effects: mutates agent.current_session['messages'] by appending assistant message with tool_calls and tool result messages | mutates agent.current_session['trace'] by appending tool_execution entries | calls logger.log_tool_call() and logger.log_tool_result() for user feedback | injects/clears xray context via thread-local storage
  Integration: exposes execute_and_record_tools(tool_calls, tools, agent, logger), execute_single_tool(...) | uses logger.log_tool_call(name, args) for natural function-call style output: greet(name='Alice') | creates trace entries with type, tool_name, arguments, call_id, result, status, timing, iteration, timestamp
  Performance: times each tool execution in milliseconds | executes tools sequentially (not parallel) | trace entry added BEFORE auto-trace so xray.trace() sees it
  Errors: catches all tool execution exceptions | wraps errors in trace_entry with error, error_type fields | returns error message to LLM for retry | prints error to logger with red ✗
"""

import time
import json
from typing import List, Dict, Any, Optional, Callable

from ..debug.xray import (
    inject_xray_context,
    clear_xray_context,
    is_xray_enabled
)


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
    for tool_call in tool_calls:
        # Execute the tool and get trace entry
        trace_entry = execute_single_tool(
            tool_name=tool_call.name,
            tool_args=tool_call.arguments,
            tool_id=tool_call.id,
            tools=tools,
            agent=agent,
            logger=logger
        )

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

    # Record tool_call event BEFORE execution (for real-time UI updates)
    agent._record_trace({
        "type": "tool_call",
        "tool_id": tool_id,  # LLM's tool call ID
        "name": tool_name,
        "args": tool_args,
    })

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

    try:
        # Set pending_tool for before_tool handlers to access
        agent.current_session['pending_tool'] = {
            'name': tool_name,
            'arguments': tool_args,
            'id': tool_id,
            'description': getattr(tool_func, 'description', '')
        }

        # Invoke before_each_tool events
        agent._invoke_events('before_each_tool')

        # Clear pending_tool after event (it's only valid during before_tool)
        agent.current_session.pop('pending_tool', None)

        # Execute the tool with timing (restart timer AFTER events for accurate tool timing)
        tool_start = time.time()

        # Inject agent for ask_user tool (YAGNI - only generalize when needed)
        if tool_name == 'ask_user':
            tool_args['agent'] = agent

        result = tool_func(**tool_args)
        tool_duration = (time.time() - tool_start) * 1000  # milliseconds

        trace_entry["timing_ms"] = tool_duration
        trace_entry["result"] = str(result)
        trace_entry["status"] = "success"

        agent._record_trace(trace_entry)
        logger.log_tool_result(str(result), tool_duration)

        # Auto-print Rich table if @xray enabled
        if xray_enabled:
            logger.print_xray_table(
                tool_name=tool_name,
                tool_args=tool_args,
                result=result,
                timing=tool_duration,
                agent=agent
            )

        # Note: after_tool event will fire in execute_and_record_tools after result message added

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

    finally:
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