"""
ConnectOnion Debugging Decorators

This module provides powerful debugging decorators for AI agent tools:
- @xray: See everything the Agent is thinking during tool execution
- @replay: Quickly retry tool execution with different parameters
- xray.trace(): Visualize complete tool execution flow with timing

The decorators use a hybrid design pattern where they serve dual purposes:
1. As decorators to enable functionality (@xray, @replay)
2. As global objects for accessing context (xray.agent, replay())
3. As debugging tools (xray.trace() shows execution history)

Key Features:
- Thread-safe context management for concurrent executions
- Zero overhead when decorators aren't used
- Smart truncation for large data structures
- Integration with agent History for persistence

This design prioritizes developer experience, making debugging as frictionless as possible.
"""

import functools
import inspect
from typing import Any, Callable, Dict, Optional
import threading
import builtins

# =============================================================================
# Thread-Local Context Management
# =============================================================================

# Thread-local storage ensures context isolation between concurrent executions
_context = threading.local()


def _get_debug_context() -> Dict[str, Any]:
    """
    Get the current debugging context from thread-local storage.
    
    Returns:
        Dict containing agent context, or empty dict if no context exists
    """
    return getattr(_context, 'data', {})


def _set_debug_context(data: Dict[str, Any]) -> None:
    """
    Set debugging context in thread-local storage.
    
    This is called by the Agent before tool execution to provide context.
    
    Args:
        data: Dictionary containing agent, user_prompt, messages, iteration, etc.
    """
    _context.data = data


def _clear_debug_context() -> None:
    """
    Clear debugging context from thread-local storage.
    
    Called after tool execution to prevent context leakage.
    """
    if hasattr(_context, 'data'):
        del _context.data


# =============================================================================
# XRay Context and Decorator
# =============================================================================

class XrayContext:
    """
    Container for Agent execution context accessible during debugging.
    
    This class holds all the debugging information about the current
    Agent execution, including the agent instance, user_prompt, messages,
    iteration count, and previously called tools.
    """
    
    def __init__(self):
        """Initialize with empty context."""
        self._context = {}
    
    def _update(self, context: Dict[str, Any]) -> None:
        """
        Update context with new data (internal use).
        
        Args:
            context: Dictionary containing agent execution context
        """
        self._context = context
    
    def _clear(self) -> None:
        """Clear context after execution (internal use)."""
        self._context = {}
    
    # -------------------------------------------------------------------------
    # Properties for accessing context data
    # -------------------------------------------------------------------------
    
    @property
    def agent(self):
        """
        The Agent instance that called this tool.
        
        Returns None if not in an active @xray decorated function.
        """
        if not self._context:
            return None
        return self._context.get('agent')
    
    @property
    def user_prompt(self):
        """
        The original user prompt string passed to agent.input().
        
        Returns None if not in an active @xray decorated function.
        """
        if not self._context:
            return None
        return self._context.get('user_prompt')
    
    @property
    def messages(self):
        """
        Complete conversation history (the prompt) as a list of message dicts.
        
        Each message has 'role' and 'content' keys. Returns empty list if
        not in an active @xray decorated function.
        """
        if not self._context:
            return []
        return self._context.get('messages', [])
    
    @property
    def iteration(self):
        """
        Current iteration number in the agent's execution loop.
        
        Agents may call tools multiple times; this tracks which iteration
        we're in. Returns None if not in an active @xray decorated function.
        """
        if not self._context:
            return None
        return self._context.get('iteration')
    
    @property
    def previous_tools(self):
        """
        List of tool names called in previous iterations.
        
        Useful for understanding the sequence of tool calls. Returns empty
        list if not in an active @xray decorated function.
        """
        if not self._context:
            return []
        return self._context.get('previous_tools', [])
    
    def get_context(self) -> Dict[str, Any]:
        """
        Get the complete context dictionary.
        
        Returns:
            Dictionary containing all context data (agent, user_prompt, messages, etc.)
        """
        return self._context.copy()
    
    def __repr__(self):
        """
        Provide helpful representation for debugging.
        
        Shows available context data and usage hints.
        """
        if not self._context:
            return ("<XrayContext (no active context)>\n"
                    "  Use @xray decorator on your function to enable context tracking")
        
        agent_name = self.agent.name if self.agent else 'None'
        prompt_preview = (self.user_prompt[:50] + '...') if self.user_prompt and len(self.user_prompt) > 50 else self.user_prompt
        
        lines = [
            f"<XrayContext active>",
            f"  agent: '{agent_name}'",
            f"  user_prompt: '{prompt_preview}'",
            f"  iteration: {self.iteration}",
            f"  messages: {len(self.messages)} items",
        ]
        
        if self.previous_tools:
            lines.append(f"  previous_tools: {self.previous_tools}")
        
        lines.append("  Access values with: xray.agent, xray.user_prompt, etc.")
        
        return '\n'.join(lines)


class XrayDecorator:
    """
    Hybrid object that acts as both a decorator and context accessor.
    
    This class implements the dual-purpose design:
    1. When called with a function, acts as @xray decorator
    2. When accessing attributes, provides context data
    3. When called without args, returns full context dict
    
    This design prioritizes developer experience - after importing xray,
    it "just works" for both decoration and context access.
    """
    
    def __init__(self, context: XrayContext):
        """
        Initialize with a context container.
        
        Args:
            context: XrayContext instance to hold execution data
        """
        self._context = context
        # Make this available globally as 'xray' for easy access
        builtins.xray = self
    
    def __call__(self, func: Optional[Callable] = None) -> Any:
        """
        Act as decorator when given a function, or return context when called empty.
        
        Args:
            func: Function to decorate (optional)
            
        Returns:
            Decorated function if func provided, context dict otherwise
            
        Examples:
            As decorator:
                @xray
                def my_tool(param: str) -> str:
                    # Can now access xray.agent, xray.user_prompt, etc.
                    return result
                    
            As function:
                context = xray()  # Get full context dictionary
        """
        # If called without arguments, return the context dict
        if func is None:
            return self.get_context()
        
        # Otherwise, act as a decorator
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get context set by Agent before tool execution
            context = _get_debug_context()
            
            # Update our context object with current execution data
            if context:
                self._context._update(context)
            
            try:
                # Execute the original function
                return func(*args, **kwargs)
            finally:
                # Clean up context to prevent leakage
                self._context._clear()
        
        # Mark function as xray-enabled so Agent knows to inject context
        wrapper.__xray_enabled__ = True
        return wrapper
    
    # -------------------------------------------------------------------------
    # Proxy attribute access to underlying context
    # -------------------------------------------------------------------------
    
    def __getattr__(self, name):
        """Forward any attribute access to the context object."""
        return getattr(self._context, name)
    
    # Explicitly define common properties for better IDE support
    
    @property
    def agent(self):
        """The Agent instance that called this tool."""
        return self._context.agent
    
    @property
    def user_prompt(self):
        """The original user prompt string from agent.input()."""
        return self._context.user_prompt
    
    @property
    def messages(self):
        """Complete conversation history (the prompt)."""
        return self._context.messages
    
    @property
    def iteration(self):
        """Current iteration number in the agent loop."""
        return self._context.iteration
    
    @property
    def previous_tools(self):
        """List of tools called in previous iterations."""
        return self._context.previous_tools
    
    def get_context(self):
        """Get the complete context dictionary."""
        return self._context.get_context()
    
    def __repr__(self):
        """Delegate representation to context for consistency."""
        return repr(self._context)
    
    def trace(self):
        """
        Display a visual trace of tool execution flow.
        
        Shows the complete sequence of tool calls with inputs, outputs,
        and execution timing in a clear, scannable format designed for
        terminal readability.
        
        Usage:
            # Within an @xray decorated tool:
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
        # Get agent from current context - trace() only works inside @xray decorated functions
        if not self._context.agent:
            print("xray.trace() can only be used inside @xray decorated functions.")
            print("Add @xray decorator to your tool function to enable tracing.")
            return
            
        target_agent = self._context.agent
            
        # Try to get from current execution context first (if called within a tool)
        execution_history = self._context._context.get('execution_history', [])
        user_prompt = self._context.user_prompt
        
        # If not in active context, get from agent's persisted history
        if not execution_history and target_agent.history.records:
            # Get the most recent prompt execution
            last_record = target_agent.history.records[-1]
            user_prompt = last_record.user_prompt
            
            # Convert tool_calls from history format to execution_history format
            # This allows trace() to work even after the agent has finished
            execution_history = []
            for tc in last_record.tool_calls:
                exec_entry = {
                    'tool_name': tc.get('name', 'unknown'),
                    'parameters': tc.get('arguments', {}),
                    'status': tc.get('status', 'success'),
                    'timing': tc.get('timing', 0),  # Timing added by agent during execution
                    'result': tc.get('result'),
                    'error': tc.get('error') if tc.get('status') == 'error' else None
                }
                execution_history.append(exec_entry)
        
        if not execution_history:
            print("No tool execution history available.")
            print("Make sure you're using @xray decorator and the agent has run.")
            return
        
        # Display the prompt that was executed
        if user_prompt:
            print(f'User Prompt: "{user_prompt}"')
            print()
        
        # Display each tool execution with visual formatting
        for i, entry in enumerate(execution_history, 1):
            # Format timing with appropriate precision
            timing = entry.get('timing', 0)
            if timing >= 1000:
                timing_str = f"{timing/1000:.1f}s"  # Show seconds for long operations
            elif timing >= 1:
                timing_str = f"{timing:.0f}ms"      # Whole milliseconds
            else:
                timing_str = f"{timing:.2f}ms"      # Sub-millisecond precision
            
            # Format function call
            func_name = entry.get('tool_name', 'unknown')
            params = entry.get('parameters', {})
            
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
        iterations = self._context.iteration or 1
        
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
xray_context = XrayContext()
xray = XrayDecorator(xray_context)


# =============================================================================
# Replay Function and Decorator
# =============================================================================

class ReplayFunction:
    """
    Container for replay functionality.
    
    Holds the current function and its arguments to enable re-execution
    with modified parameters during debugging.
    """
    
    def __init__(self):
        """Initialize with no active function."""
        self._func = None
        self._args = None
        self._kwargs = None
        self._original_func = None
    
    def _setup(self, func: Callable, args: tuple, kwargs: dict) -> None:
        """
        Set up replay context (internal use).
        
        Args:
            func: The function to replay
            args: Original positional arguments
            kwargs: Original keyword arguments
        """
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._original_func = func
    
    def _clear(self) -> None:
        """Clear replay context after execution (internal use)."""
        self._func = None
        self._args = None
        self._kwargs = None
        self._original_func = None
    
    def __call__(self, **new_kwargs) -> Any:
        """
        Replay the function with modified parameters.
        
        Args:
            **new_kwargs: Keyword arguments to override
            
        Returns:
            Result of re-executing the function
            
        Example:
            # In debugger at breakpoint:
            >>> replay(threshold=0.8)  # Re-run with new threshold
            🔄 Replaying my_function()
               Modified parameters: {'threshold': 0.8}
            ✅ Result: 0.95
        """
        if self._func is None:
            print("❌ No function to replay. Make sure you're in a breakpoint "
                  "inside a @replay decorated function.")
            return None
        
        # Merge original kwargs with new ones (new ones override)
        merged_kwargs = self._kwargs.copy() if self._kwargs else {}
        merged_kwargs.update(new_kwargs)
        
        print(f"🔄 Replaying {self._original_func.__name__}()")
        if new_kwargs:
            print(f"   Modified parameters: {new_kwargs}")
        
        try:
            result = self._func(*self._args, **merged_kwargs)
            print(f"✅ Result: {result}")
            return result
        except Exception as e:
            print(f"❌ Error during replay: {e}")
            raise
    
    def __repr__(self):
        """Show current replay state."""
        if self._original_func:
            return f"<replay function for {self._original_func.__name__}>"
        return "<replay function (not active)>"


class ReplayDecorator:
    """
    Hybrid object that acts as both a decorator and replay function.
    
    Similar dual-purpose design as XrayDecorator:
    1. When decorating a function, enables replay functionality
    2. When called with kwargs, replays the current function
    """
    
    def __init__(self, replay_func: ReplayFunction):
        """
        Initialize with a replay function container.
        
        Args:
            replay_func: ReplayFunction instance to manage replay state
        """
        self._replay_func = replay_func
        # Make this available globally as 'replay' for easy access
        builtins.replay = self
    
    def __call__(self, *args, **kwargs) -> Any:
        """
        Act as decorator or replay function based on arguments.
        
        If called with a single callable argument and no kwargs, acts as decorator.
        Otherwise, forwards the call to replay the current function.
        
        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Decorated function or replay result
        """
        # Check if being used as decorator
        if len(args) == 1 and len(kwargs) == 0 and callable(args[0]):
            func = args[0]
            
            @functools.wraps(func)
            def wrapper(*inner_args, **inner_kwargs):
                # Set up replay context with current execution
                self._replay_func._setup(func, inner_args, inner_kwargs)
                
                try:
                    # Execute the original function
                    return func(*inner_args, **inner_kwargs)
                finally:
                    # Clean up replay context
                    self._replay_func._clear()
            
            # Mark function as replay-enabled
            wrapper.__replay_enabled__ = True
            return wrapper
        
        # Otherwise, act as the replay function
        else:
            return self._replay_func(*args, **kwargs)
    
    def __repr__(self):
        """Delegate representation to replay function."""
        return repr(self._replay_func)


# Create the global replay instance
replay_function = ReplayFunction()
replay = ReplayDecorator(replay_function)


# =============================================================================
# Combined Decorator
# =============================================================================

def xray_replay(func: Callable) -> Callable:
    """
    Convenience decorator that combines @xray and @replay.
    
    Equivalent to:
        @xray
        @replay
        def my_tool(...):
            ...
            
    Args:
        func: Function to decorate
        
    Returns:
        Function with both xray and replay capabilities
    """
    return xray(replay(func))


# =============================================================================
# Internal Helper Functions for Agent Integration
# =============================================================================

def _inject_context_for_tool(agent, user_prompt: str, messages: list, 
                           iteration: int, previous_tools: list, 
                           execution_history: list = None) -> None:
    """
    Inject debugging context before tool execution.
    
    This is called internally by the Agent when executing an @xray decorated tool.
    
    Args:
        agent: The Agent instance
        user_prompt: Original user prompt string from agent.input()
        messages: Conversation history
        iteration: Current iteration number
        previous_tools: List of previously called tool names
        execution_history: List of all tool executions with timing
    """
    context = {
        'agent': agent,
        'user_prompt': user_prompt,
        'messages': messages,
        'iteration': iteration,
        'previous_tools': previous_tools
    }
    
    if execution_history is not None:
        context['execution_history'] = execution_history
        
    _set_debug_context(context)


def _clear_context_after_tool() -> None:
    """
    Clear debugging context after tool execution.
    
    This is called internally by the Agent to prevent context leakage.
    """
    _clear_debug_context()


def _is_xray_enabled(func: Callable) -> bool:
    """
    Check if a function has the @xray decorator.
    
    Args:
        func: Function to check
        
    Returns:
        True if function is decorated with @xray
    """
    return getattr(func, '__xray_enabled__', False)


def _is_replay_enabled(func: Callable) -> bool:
    """
    Check if a function has the @replay decorator.
    
    Args:
        func: Function to check
        
    Returns:
        True if function is decorated with @replay
    """
    return getattr(func, '__replay_enabled__', False)