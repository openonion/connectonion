"""
Purpose: Provide runtime debugging context and visual trace for AI agent tool execution
LLM-Note:
  Dependencies: imports from [inspect, builtins, typing] | imported by [tool_executor.py, __init__.py] | tested by [tests/test_xray_class.py, tests/test_xray_without_decorator.py, tests/test_xray_auto_trace.py]
  Data flow: receives from tool_executor → inject_xray_context(agent, user_prompt, messages, iteration, previous_tools) → stores in builtins.xray global → tool accesses xray.agent, xray.task, etc. → tool calls xray.trace() to display formatted execution history → clear_xray_context() after execution
  State/Effects: modifies builtins namespace by injecting global 'xray' object | stores thread-local context in XrayDecorator instance (_agent, _user_prompt, _messages, _iteration, _previous_tools) | clears context after tool execution | no file I/O or persistence
  Integration: exposes @xray decorator, xray global object with .agent, .task, .user_prompt, .messages, .iteration, .previous_tools properties, .trace() method | inject_xray_context(), clear_xray_context(), is_xray_enabled() helper functions | tool_executor checks __xray_enabled__ attribute to auto-print Rich tables
  Performance: lightweight context storage | trace() uses stack inspection to find agent instance | smart value formatting with truncation for strings (400 chars), lists, dicts, DataFrames, Images
  Errors: trace() handles missing agent gracefully with helpful messages | handles missing current_session | handles empty execution history

ConnectOnion XRay Debugging Tool

This module provides the @xray decorator and xray context for debugging AI agent tools.
See everything your agent is thinking during tool execution.

Usage:
    from connectonion.xray import xray

    @xray
    def my_tool(query: str):
        print(xray.agent.name)   # Access agent context
        print(xray.task)          # Access user prompt
        xray.trace()              # Display execution trace
        return result
"""

import inspect
import builtins
from typing import Any, Callable, Optional


class XrayDecorator:
    """
    Simple xray decorator that provides context access and auto-tracing.

    Usage:
        @xray                    # Auto-print trace after execution
        @xray(trace=False)       # No auto-trace
        @xray(rich=False)        # Simple text output

        def my_tool(query: str):
            print(xray.agent.name)   # Access agent context
            print(xray.task)          # Access user prompt
            xray.trace()              # Manual trace display
            return result
    """

    def __init__(self):
        """Initialize with empty context."""
        # Store context directly (no wrapper class needed)
        self._agent = None
        self._user_prompt = None
        self._messages = []
        self._iteration = None
        self._previous_tools = []

        # Make available globally as 'xray' for easy access
        builtins.xray = self

    def __call__(self, func: Optional[Callable] = None, *, trace: bool = True, rich: bool = True) -> Any:
        """
        Decorator that marks functions for auto-tracing.

        @xray                    # Auto-print trace after execution (Rich format)
        @xray(trace=False)       # No auto-trace
        @xray(rich=False)        # Simple text output

        The actual tracing logic is handled by tool_executor.py which checks
        the __xray_enabled__ and __xray_rich__ attributes.

        Args:
            func: Function to decorate (optional)
            trace: Enable automatic tracing (default: True)
            rich: Use Rich formatting for trace output (default: True)

        Returns:
            Decorated function (no wrapper) with __xray_enabled__ attribute
        """
        def decorator(f):
            # Mark the function with xray settings
            f.__xray_enabled__ = trace
            f.__xray_rich__ = rich
            return f

        # Handle different call patterns
        if func is None:
            # Called with parentheses: @xray() or @xray(trace=False)
            return decorator
        else:
            # Called without parentheses: @xray
            return decorator(func)

    # -------------------------------------------------------------------------
    # Properties for accessing context data
    # -------------------------------------------------------------------------

    @property
    def agent(self):
        """The Agent instance that called this tool."""
        return self._agent

    @property
    def task(self):
        """The original user prompt/task (alias for user_prompt)."""
        return self._user_prompt

    @property
    def user_prompt(self):
        """The original user prompt string from agent.input()."""
        return self._user_prompt

    @property
    def messages(self):
        """Complete conversation history (the prompt)."""
        return self._messages

    @property
    def iteration(self):
        """Current iteration number in the agent loop."""
        return self._iteration

    @property
    def previous_tools(self):
        """List of tools called in previous iterations."""
        return self._previous_tools

    def _update(self, agent, user_prompt, messages, iteration, previous_tools):
        """Internal: Update context (called by tool_executor before tool runs)."""
        self._agent = agent
        self._user_prompt = user_prompt
        self._messages = messages
        self._iteration = iteration
        self._previous_tools = previous_tools

    def _clear(self):
        """Internal: Clear context after tool execution."""
        self._agent = None
        self._user_prompt = None
        self._messages = []
        self._iteration = None
        self._previous_tools = []

    def __repr__(self):
        """Provide helpful representation for debugging."""
        if not self._agent:
            return "<xray (no active context)>"

        agent_name = self._agent.name if self._agent else 'None'
        prompt_preview = (self._user_prompt[:50] + '...') if self._user_prompt and len(self._user_prompt) > 50 else self._user_prompt

        lines = [
            f"<xray active>",
            f"  agent: '{agent_name}'",
            f"  task: '{prompt_preview}'",
            f"  iteration: {self._iteration}",
            f"  messages: {len(self._messages)} items",
        ]

        if self._previous_tools:
            lines.append(f"  previous_tools: {self._previous_tools}")

        return '\n'.join(lines)

    def trace(self):
        """
        Display a visual trace of tool execution flow.

        Uses stack inspection to find the agent instance, so it works
        from anywhere in the call stack (inside tools, breakpoints, etc.)

        Usage:
            # Within a tool or anywhere in the call stack:
            xray.trace()  # Shows current execution flow

            # In debugging session with breakpoint:
            >>> xray.trace()
            Task: "Analyze customer feedback and generate report"

            [1] • 89ms  analyze_document(text="Dear customer, Thank you for...")
                  IN  → text: <string: 15,234 chars> "Dear customer, Thank you for..."
                  OUT ← {sentiment: "positive", topics: ["refund", "satisfaction"]}

            [2] • 340ms process_image(image=<...>, enhance=true)
                  IN  → image: <Image: JPEG 1920x1080, 2.3MB>
                  IN  → enhance: true
                  OUT ← <Image: JPEG 1920x1080, 1.8MB, enhanced>

            Total: 429ms • 2 steps • 1 iterations

        Visual Format:
            - Step numbers in brackets: [1], [2], etc.
            - Timing shown after bullet (•) or ERROR/pending indicator
            - Function signature shows first 2 params inline, rest as "..."
            - IN → shows input parameters (one per line)
            - OUT ← shows return values
            - ERR ✗ shows errors
            - Smart truncation for long strings, images, DataFrames
        """
        # Use stack inspection to find agent instance
        target_agent = None
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals

            # Look for 'agent' in local variables
            if 'agent' in frame_locals:
                potential_agent = frame_locals['agent']
                # Check if it has current_session (duck typing for Agent)
                if hasattr(potential_agent, 'current_session'):
                    target_agent = potential_agent
                    break

            # Also check 'self' in case we're in an agent method
            if 'self' in frame_locals:
                potential_agent = frame_locals['self']
                if hasattr(potential_agent, 'current_session'):
                    target_agent = potential_agent
                    break

        if not target_agent:
            print("xray.trace() could not find agent in call stack.")
            print("Make sure you're calling this from within a tool or agent method.")
            return

        if not target_agent.current_session:
            print("No active session found on agent.")
            print("Make sure the agent has been run with .input() first.")
            return

        # Get trace data from agent session
        execution_history = [
            entry for entry in target_agent.current_session.get('trace', [])
            if entry.get('type') == 'tool_execution'
        ]
        user_prompt = target_agent.current_session.get('user_prompt', '')

        if not execution_history:
            print("No tool execution history available.")
            print("Make sure the agent has executed some tools first.")
            return

        # Display the prompt that was executed
        if user_prompt:
            print(f'User Prompt: "{user_prompt}"')
            print()

        # Display each tool execution with visual formatting
        for i, entry in enumerate(execution_history, 1):
            # Format timing with appropriate precision (timing is in milliseconds)
            timing = entry.get('timing', 0)
            if timing >= 1000:
                timing_str = f"{timing/1000:.1f}s"  # Show seconds for long operations
            elif timing >= 1:
                timing_str = f"{timing:.0f}ms"      # Whole milliseconds
            else:
                timing_str = f"{timing:.2f}ms"      # Sub-millisecond precision

            # Format function call
            func_name = entry.get('tool_name', 'unknown')
            # Check both 'arguments' (new format) and 'parameters' (old format)
            params = entry.get('arguments', entry.get('parameters', {}))

            # Build parameter preview for function signature
            # Shows first 2 params inline to keep the main line readable
            param_preview = []
            for k, v in list(params.items())[:2]:  # Show first 2 params in signature
                param_preview.append(f"{k}={self._format_value_preview(v)}")
            if len(params) > 2:
                param_preview.append("...")  # Indicate more params exist

            func_call = f"{func_name}({', '.join(param_preview)})"

            # Status indicators for visual clarity
            status = entry.get('status', 'success')
            if status == 'error':
                prefix = "ERROR"  # Clearly mark errors
            elif status == 'pending':
                timing_str = "..."  # Show operation in progress
                prefix = "..."
            else:
                prefix = "•"  # Success indicator

            # Print main execution line with aligned columns
            print(f"[{i}] {prefix} {timing_str:<6} {func_call}")

            # Print input parameters (one per line for readability)
            for param_name, param_value in params.items():
                formatted_value = self._format_value_full(param_value)
                print(f"      IN  → {param_name}: {formatted_value}")

            # Print result or error based on status
            if status == 'error':
                error = entry.get('error', 'Unknown error')
                print(f"      ERR ✗ {error}")
            elif status == 'pending':
                print(f"      ⋯ pending")
            else:
                result = entry.get('result')
                formatted_result = self._format_value_full(result)
                print(f"      OUT ← {formatted_result}")

            # Add spacing between entries for readability
            if i < len(execution_history):
                print()

        # Summary line with total execution statistics
        total_time = sum(e.get('timing', 0) for e in execution_history if e.get('timing'))
        iterations = target_agent.current_session.get('iteration', 1)

        # Format total time with same rules as individual timings
        if total_time >= 1000:
            total_str = f"{total_time/1000:.1f}s"
        elif total_time >= 1:
            total_str = f"{total_time:.0f}ms"
        else:
            total_str = f"{total_time:.2f}ms"

        print(f"\nTotal: {total_str} • {len(execution_history)} steps • {iterations} iterations")

    def _format_value_preview(self, value):
        """
        Format a value for compact display in function signature.

        Used in the main execution line to show parameter values inline
        without taking too much horizontal space.

        Args:
            value: Any parameter value to format

        Returns:
            Compact string representation (max ~50 chars)
        """
        if value is None:
            return "None"
        elif isinstance(value, str):
            if len(value) > 50:
                return f'"{value[:50]}..."'
            return repr(value)
        elif isinstance(value, (int, float, bool)):
            return str(value)
        elif isinstance(value, dict):
            return "{...}"  # Just indicate it's a dict
        elif isinstance(value, list):
            return "[...]"  # Just indicate it's a list
        else:
            return "..."    # Unknown type

    def _format_value_full(self, value):
        """
        Format a value for full display with smart truncation.

        Used in the detailed parameter/result lines. Provides more detail
        than preview format while still keeping output manageable.

        Truncation strategies:
        - Strings: Show first 400 chars (~4 sentences) with total length
        - Lists: Show item count if > 3 items
        - Dicts: Show first 3 keys if large
        - DataFrames: Show dimensions (rows × columns)
        - Images: Show format, dimensions, and estimated size

        Args:
            value: Any value to format for display

        Returns:
            Formatted string with smart truncation applied
        """
        if value is None:
            return "None"
        elif isinstance(value, str):
            # Show up to ~4 sentences worth of text (roughly 400 chars)
            if len(value) > 400:
                preview = value[:400].replace('\n', ' ')
                return f'<string: {len(value):,} chars> "{preview}..."'
            return repr(value)
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, bool):
            return str(value)
        elif isinstance(value, dict):
            # Show compact dict representation
            if len(str(value)) <= 80:
                return str(value)
            # Show keys for large dicts
            keys = list(value.keys())[:3]
            key_str = ", ".join(f"{k}: ..." for k in keys)
            if len(value) > 3:
                key_str += f", ... ({len(value)-3} more)"
            return f"{{{key_str}}}"
        elif isinstance(value, list):
            if len(value) == 0:
                return "[]"
            elif len(value) <= 3 and len(str(value)) <= 80:
                return str(value)
            else:
                return f"[{len(value)} items]"
        elif hasattr(value, '__class__'):
            # Handle custom objects
            class_name = value.__class__.__name__

            # Special handling for common ML/data objects
            if 'DataFrame' in class_name:
                # Try to get shape info
                if hasattr(value, 'shape'):
                    rows, cols = value.shape
                    return f"<DataFrame: {rows:,} rows × {cols} columns>"
                return f"<{class_name}>"
            elif 'Image' in class_name or 'PIL' in str(type(value)):
                # Handle image objects
                if hasattr(value, 'size'):
                    w, h = value.size
                    format_str = getattr(value, 'format', 'Unknown')
                    # Estimate size (rough)
                    size_mb = (w * h * 3) / (1024 * 1024)
                    return f"<Image: {format_str} {w}x{h}, {size_mb:.1f}MB>"
                return f"<{class_name}>"
            else:
                return f"<{class_name} object>"
        else:
            return str(type(value).__name__)


# Create the global xray instance
xray = XrayDecorator()


# =============================================================================
# Helper Functions for Tool Executor Integration
# =============================================================================

def inject_xray_context(agent, user_prompt: str, messages: list,
                        iteration: int, previous_tools: list) -> None:
    """
    Inject debugging context before tool execution.

    This is called internally by tool_executor before running a tool,
    making xray.agent, xray.task, etc. available inside the tool.

    Args:
        agent: The Agent instance
        user_prompt: Original user prompt string from agent.input()
        messages: Conversation history
        iteration: Current iteration number
        previous_tools: List of previously called tool names
    """
    xray._update(agent, user_prompt, messages, iteration, previous_tools)


def clear_xray_context() -> None:
    """
    Clear debugging context after tool execution.

    This is called internally by tool_executor to prevent context leakage.
    """
    xray._clear()


def is_xray_enabled(func: Callable) -> bool:
    """
    Check if a function has the @xray decorator.

    Args:
        func: Function to check

    Returns:
        True if function is decorated with @xray
    """
    return getattr(func, '__xray_enabled__', False)