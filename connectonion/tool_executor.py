"""
Purpose: Execute agent tools with xray context injection, timing, error handling, and trace recording
LLM-Note:
  Dependencies: imports from [time, json, typing, console.py, xray.py] | imported by [agent.py] | tested by [tests/test_tool_executor.py]
  Data flow: receives from Agent → tool_calls: List[ToolCall], tool_map: Dict[str, Callable], agent: Agent, console: Console → for each tool: injects xray context via inject_xray_context() → executes tool_func(**tool_args) → records timing and result → appends to agent.current_session['trace'] → clears xray context → adds tool result to messages
  State/Effects: mutates agent.current_session['messages'] by appending assistant message with tool_calls and tool result messages | mutates agent.current_session['trace'] by appending tool_execution entries | calls console.print() for user feedback | calls console.print_xray_table() if @xray enabled | injects/clears xray context via thread-local storage
  Integration: exposes execute_and_record_tools(tool_calls, tool_map, agent, console), execute_single_tool(...) | checks is_xray_enabled() on tool functions | creates trace entries with type, tool_name, arguments, call_id, result, status, timing, iteration, timestamp | status values: success, error, not_found
  Performance: times each tool execution in milliseconds | executes tools sequentially (not parallel) | trace entry added BEFORE auto-trace so xray.trace() sees it
  Errors: catches all tool execution exceptions | wraps errors in trace_entry with error, error_type fields | returns error message to LLM for retry | prints error to console with red ✗
"""

import time
import json
from typing import List, Dict, Any, Optional, Callable

from .console import Console
from .xray import (
    inject_xray_context,
    clear_xray_context,
    is_xray_enabled
)


def execute_and_record_tools(
    tool_calls: List,
    tool_map: Dict[str, Callable],
    agent: Any,
    console: Console
) -> None:
    """Execute requested tools and update conversation messages.

    Uses agent.current_session as single source of truth for messages and trace.

    Args:
        tool_calls: List of tool calls from LLM response
        tool_map: Dictionary mapping tool names to callable functions
        agent: Agent instance with current_session containing messages and trace
        console: Console for output (always provided by Agent)
    """
    # Format and add assistant message with tool calls
    _add_assistant_message(agent.current_session['messages'], tool_calls)

    # Execute each tool
    for tool_call in tool_calls:
        # Execute the tool and get trace entry
        trace_entry = execute_single_tool(
            tool_name=tool_call.name,
            tool_args=tool_call.arguments,
            tool_id=tool_call.id,
            tool_map=tool_map,
            agent=agent,
            console=console
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
        # on_error fires first for errors/not_found, then after_tool always fires
        if trace_entry["status"] in ("error", "not_found"):
            agent._invoke_events('on_error')

        # after_tool fires for ALL tool executions (success, error, not_found)
        agent._invoke_events('after_tool')


def execute_single_tool(
    tool_name: str,
    tool_args: Dict,
    tool_id: str,
    tool_map: Dict[str, Callable],
    agent: Any,
    console: Console
) -> Dict[str, Any]:
    """Execute a single tool and return trace entry.

    Uses agent.current_session as single source of truth.
    Checks for __xray_enabled__ attribute to auto-print Rich tables.

    Args:
        tool_name: Name of the tool to execute
        tool_args: Arguments to pass to the tool
        tool_id: ID of the tool call
        tool_map: Dictionary mapping tool names to callable functions
        agent: Agent instance with current_session
        console: Console for output (always provided by Agent)

    Returns:
        Dict trace entry with: type, tool_name, arguments, call_id, result, status, timing, iteration, timestamp
    """
    # Console output
    args_str = str(tool_args)[:50] + "..." if len(str(tool_args)) > 50 else str(tool_args)
    console.print(f"[blue]→[/blue] Tool: {tool_name}({args_str})")

    # Create single trace entry
    trace_entry = {
        "type": "tool_execution",
        "tool_name": tool_name,
        "arguments": tool_args,
        "call_id": tool_id,
        "timing": 0,
        "status": "pending",
        "result": None,
        "iteration": agent.current_session['iteration'],
        "timestamp": time.time()
    }

    # Check if tool exists
    if tool_name not in tool_map:
        error_msg = f"Tool '{tool_name}' not found"

        # Update trace entry
        trace_entry["result"] = error_msg
        trace_entry["status"] = "not_found"
        trace_entry["error"] = error_msg

        # Add trace entry to session (so on_error handlers can see it)
        agent.current_session['trace'].append(trace_entry)

        # Console output
        console.print(f"[red]✗[/red] {error_msg}")

        # Note: on_error event will fire in execute_and_record_tools after result message added

        return trace_entry

    # Get the tool function
    tool_func = tool_map[tool_name]

    # Check if tool has @xray decorator
    xray_enabled = is_xray_enabled(tool_func)

    # Prepare context data for xray
    previous_tools = [
        entry.get("tool_name") for entry in agent.current_session['trace']
        if entry.get("type") == "tool_execution"
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

    try:
        # Invoke before_tool events
        agent._invoke_events('before_tool')

        # Execute the tool with timing (restart timer AFTER events for accurate tool timing)
        tool_start = time.time()
        result = tool_func(**tool_args)
        tool_duration = (time.time() - tool_start) * 1000  # milliseconds

        # Update trace entry
        trace_entry["timing"] = tool_duration
        trace_entry["result"] = str(result)
        trace_entry["status"] = "success"

        # Add trace entry to session BEFORE auto-trace
        # (so it shows up in xray.trace() output)
        agent.current_session['trace'].append(trace_entry)

        # Console output
        result_str = str(result)[:50] + "..." if len(str(result)) > 50 else str(result)
        # Show more precision for fast operations (<0.1s), less for slow ones
        time_str = f"{tool_duration/1000:.4f}s" if tool_duration < 100 else f"{tool_duration/1000:.1f}s"
        console.print(f"[green]←[/green] Result ({time_str}): {result_str}")

        # Auto-print Rich table if @xray enabled
        if xray_enabled:
            console.print_xray_table(
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

        # Update trace entry
        trace_entry["timing"] = tool_duration
        trace_entry["status"] = "error"
        trace_entry["error"] = str(e)
        trace_entry["error_type"] = type(e).__name__

        error_msg = f"Error executing tool: {str(e)}"
        trace_entry["result"] = error_msg

        # Add error trace entry to session (so on_error handlers can see it)
        agent.current_session['trace'].append(trace_entry)

        # Console output
        time_str = f"{tool_duration/1000:.4f}s" if tool_duration < 100 else f"{tool_duration/1000:.1f}s"
        console.print(f"[red]✗[/red] Error ({time_str}): {str(e)}")

        # Note: on_error event will fire in execute_and_record_tools after result message added

    finally:
        # Clear xray context after tool execution
        clear_xray_context()

    return trace_entry


def _add_assistant_message(messages: List[Dict], tool_calls: List) -> None:
    """Format and add assistant message with tool calls.

    Args:
        messages: Conversation messages list (will be mutated)
        tool_calls: Tool calls from LLM response
    """
    assistant_tool_calls = []
    for tool_call in tool_calls:
        assistant_tool_calls.append({
            "id": tool_call.id,
            "type": "function",
            "function": {
                "name": tool_call.name,
                "arguments": json.dumps(tool_call.arguments)
            }
        })

    messages.append({
        "role": "assistant",
        "content": None,
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