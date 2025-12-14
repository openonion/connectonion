"""
Purpose: Orchestrate AI agent execution with LLM calls, tool execution, and automatic logging
LLM-Note:
  Dependencies: imports from [llm.py, tool_factory.py, prompts.py, decorators.py, logger.py, tool_executor.py, tool_registry.py] | imported by [__init__.py, debug_agent/__init__.py] | tested by [tests/test_agent.py, tests/test_agent_prompts.py, tests/test_agent_workflows.py]
  Data flow: receives user prompt: str from Agent.input() → creates/extends current_session with messages → calls llm.complete() with tool schemas → receives LLMResponse with tool_calls → executes tools via tool_executor.execute_and_record_tools() → appends tool results to messages → repeats loop until no tool_calls or max_iterations → logger logs to .co/logs/{name}.log and .co/sessions/{name}_{timestamp}.yaml → returns final response: str
  State/Effects: modifies self.current_session['messages', 'trace', 'turn', 'iteration'] | writes to .co/logs/{name}.log and .co/sessions/ via logger.py
  Integration: exposes Agent(name, tools, system_prompt, model, log, quiet), .input(prompt), .execute_tool(name, args), .add_tool(func), .remove_tool(name), .list_tools(), .reset_conversation() | tools stored in ToolRegistry with attribute access (agent.tools.tool_name) and instance storage (agent.tools.gmail) | tool execution delegates to tool_executor module | log defaults to .co/logs/ (None), can be True (current dir), False (disabled), or custom path | quiet=True suppresses console but keeps session logging | trust enforcement moved to host() for network access control
  Performance: max_iterations=10 default (configurable per-input) | session state persists across turns for multi-turn conversations | ToolRegistry provides O(1) tool lookup via .get() or attribute access
  Errors: LLM errors bubble up | tool execution errors captured in trace and returned to LLM for retry
"""

import os
import sys
import time
from typing import List, Optional, Dict, Any, Callable, Union
from pathlib import Path
from .llm import LLM, create_llm, TokenUsage
from .usage import get_context_limit
from .tool_factory import create_tool_from_function, extract_methods_from_instance, is_class_instance
from .tool_registry import ToolRegistry
from .prompts import load_system_prompt
from .decorators import (
    _is_replay_enabled  # Only need this for replay check
)
from .logger import Logger
from .tool_executor import execute_and_record_tools, execute_single_tool
from .events import EventHandler


class Agent:
    """Agent that can use tools to complete tasks."""
    
    def __init__(
        self,
        name: str,
        llm: Optional[LLM] = None,
        tools: Optional[Union[List[Callable], Callable, Any]] = None,
        system_prompt: Union[str, Path, None] = None,
        api_key: Optional[str] = None,
        model: str = "co/gemini-2.5-pro",
        max_iterations: int = 10,
        log: Optional[Union[bool, str, Path]] = None,
        quiet: bool = False,
        plugins: Optional[List[List[EventHandler]]] = None,
        on_events: Optional[List[EventHandler]] = None
    ):
        self.name = name
        self.system_prompt = load_system_prompt(system_prompt)
        self.max_iterations = max_iterations

        # Current session context (runtime only)
        self.current_session = None

        # Token usage tracking
        self.total_cost: float = 0.0  # Cumulative cost in USD
        self.last_usage: Optional[TokenUsage] = None  # From most recent LLM call

        # Initialize logger (unified: terminal + file + YAML sessions)
        # Environment variable override (highest priority)
        effective_log = log
        if os.getenv('CONNECTONION_LOG'):
            effective_log = Path(os.getenv('CONNECTONION_LOG'))

        self.logger = Logger(agent_name=name, quiet=quiet, log=effective_log)

        # Initialize event registry
        # Note: before_each_tool/after_each_tool fire for EACH tool
        # before_tools/after_tools fire ONCE per batch (safe for adding messages)
        self.events = {
            'after_user_input': [],
            'before_llm': [],
            'after_llm': [],
            'before_each_tool': [],    # Fires before EACH tool
            'before_tools': [],        # Fires ONCE before ALL tools in a batch
            'after_each_tool': [],     # Fires after EACH tool (don't add messages here!)
            'after_tools': [],         # Fires ONCE after ALL tools (safe for messages)
            'on_error': [],
            'on_complete': []
        }

        # Register plugin events (flatten list of lists)
        if plugins:
            for event_list in plugins:
                for event_func in event_list:
                    self._register_event(event_func)

        # Register custom event handlers (supports both single functions and lists)
        if on_events:
            for item in on_events:
                if isinstance(item, list):
                    # Multiple handlers: before_tool(fn1, fn2) returns [fn1, fn2]
                    for fn in item:
                        self._register_event(fn)
                else:
                    # Single handler: @before_tool or before_tool(fn)
                    self._register_event(item)

        # Process tools: convert raw functions and class instances to tool schemas automatically
        self.tools = ToolRegistry()

        if tools is not None:
            tools_list = tools if isinstance(tools, list) else [tools]

            for tool in tools_list:
                if is_class_instance(tool):
                    # Store instance (agent.tools.gmail.my_id)
                    class_name = tool.__class__.__name__.lower()
                    self.tools.add_instance(class_name, tool)

                    # Extract methods as tools (agent.tools.send())
                    for method_tool in extract_methods_from_instance(tool):
                        self.tools.add(method_tool)
                elif callable(tool):
                    if not hasattr(tool, 'to_function_schema'):
                        processed = create_tool_from_function(tool)
                    else:
                        processed = tool
                    self.tools.add(processed)

        # Initialize LLM
        if llm:
            self.llm = llm
        else:
            # Use factory function to create appropriate LLM based on model
            # Each LLM provider checks its own env var if api_key is None:
            # - OpenAI models check OPENAI_API_KEY
            # - Anthropic models check ANTHROPIC_API_KEY
            # - Google models check GOOGLE_API_KEY
            # - co/ models check OPENONION_API_KEY
            self.llm = create_llm(model=model, api_key=api_key)

        # Print banner (if console enabled)
        if self.logger.console:
            # Determine log_dir if logging is enabled
            log_dir = ".co/" if self.logger.enable_sessions else None
            self.logger.console.print_banner(
                agent_name=self.name,
                model=self.llm.model,
                tools=len(self.tools),
                log_dir=log_dir,
                llm=self.llm
            )

    def _invoke_events(self, event_type: str):
        """Invoke all event handlers for given type. Exceptions propagate (fail fast)."""
        for handler in self.events.get(event_type, []):
            handler(self)

    def _register_event(self, event_func: EventHandler):
        """
        Register a single event handler to appropriate event type.

        Args:
            event_func: Event handler wrapped with after_llm(), after_tool(), etc.

        Raises:
            TypeError: If event handler is not callable
            ValueError: If event handler missing _event_type or invalid event type
        """
        # First check if it's callable (type validation)
        if not callable(event_func):
            raise TypeError(f"Event must be callable, got {type(event_func).__name__}")

        # Then check if it has _event_type attribute (wrapper validation)
        event_type = getattr(event_func, '_event_type', None)
        if not event_type:
            func_name = getattr(event_func, '__name__', str(event_func))
            raise ValueError(
                f"Event handler '{func_name}' missing _event_type. "
                f"Did you forget to wrap it? Use after_llm({func_name}), etc."
            )

        # Finally check if it's a valid event type (value validation)
        if event_type not in self.events:
            raise ValueError(f"Invalid event type: {event_type}")

        self.events[event_type].append(event_func)

    def input(self, prompt: str, max_iterations: Optional[int] = None,
              session: Optional[Dict] = None) -> str:
        """Provide input to the agent and get response.

        Args:
            prompt: The input prompt or data to process
            max_iterations: Override agent's max_iterations for this request
            session: Optional session to continue a conversation. Pass the session
                    from a previous response to maintain context. Contains:
                    - session_id: Conversation identifier
                    - messages: Conversation history
                    - trace: Execution trace for debugging
                    - turn: Turn counter

        Returns:
            The agent's response after processing the input
        """
        start_time = time.time()
        if self.logger.console:
            self.logger.console.print_task(prompt)

        # Session restoration: if session passed, restore it (stateless API continuation)
        if session is not None:
            self.current_session = {
                'session_id': session.get('session_id'),
                'messages': list(session.get('messages', [])),
                'trace': list(session.get('trace', [])),
                'turn': session.get('turn', 0)
            }
            # Start YAML session logging with session_id for thread safety
            self.logger.start_session(self.system_prompt, session_id=session.get('session_id'))
        elif self.current_session is None:
            # Initialize new session
            self.current_session = {
                'messages': [{"role": "system", "content": self.system_prompt}],
                'trace': [],
                'turn': 0  # Track conversation turns
            }
            # Start YAML session logging
            self.logger.start_session(self.system_prompt)

        # Add user message to conversation
        self.current_session['messages'].append({
            "role": "user",
            "content": prompt
        })

        # Track this turn
        self.current_session['turn'] += 1
        self.current_session['user_prompt'] = prompt  # Store user prompt for xray/debugging
        turn_start = time.time()

        # Add trace entry for this input
        self.current_session['trace'].append({
            'type': 'user_input',
            'turn': self.current_session['turn'],
            'prompt': prompt,  # Keep 'prompt' in trace for backward compatibility
            'timestamp': turn_start
        })

        # Invoke after_user_input events
        self._invoke_events('after_user_input')

        # Process
        self.current_session['iteration'] = 0  # Reset iteration for this turn
        result = self._run_iteration_loop(
            max_iterations or self.max_iterations
        )

        # Calculate duration
        duration = time.time() - turn_start

        self.current_session['result'] = result

        # Print completion summary
        if self.logger.console:
            session_path = f".co/sessions/{self.name}.yaml" if self.logger.enable_sessions else None
            self.logger.console.print_completion(duration, self.current_session, session_path)

        self._invoke_events('on_complete')

        # Log turn to YAML session (after on_complete so handlers can modify state)
        self.logger.log_turn(prompt, result, duration * 1000, self.current_session, self.llm.model)

        return result

    def reset_conversation(self):
        """Reset the conversation session. Start fresh."""
        self.current_session = None

    def execute_tool(self, tool_name: str, arguments: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute a single tool by name. Useful for testing and debugging.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments (default: {})

        Returns:
            Dict with: result, status, timing, name, arguments
        """
        arguments = arguments or {}

        # Create temporary session if needed
        if self.current_session is None:
            self.current_session = {
                'messages': [{"role": "system", "content": self.system_prompt}],
                'trace': [],
                'turn': 0,
                'iteration': 1,
                'user_prompt': 'Manual tool execution'
            }

        # Execute using the tool_executor
        trace_entry = execute_single_tool(
            tool_name=tool_name,
            tool_args=arguments,
            tool_id=f"manual_{tool_name}_{time.time()}",
            tools=self.tools,
            agent=self,
            logger=self.logger
        )

        # Note: trace_entry already added to session in execute_single_tool

        # Fire events (same as execute_and_record_tools)
        # on_error fires first for errors/not_found
        if trace_entry["status"] in ("error", "not_found"):
            self._invoke_events('on_error')

        # after_each_tool fires for this tool execution
        self._invoke_events('after_each_tool')

        # after_tools fires after all tools in batch (for single execution, fires once)
        self._invoke_events('after_tools')

        # Return simplified result (omit internal fields)
        return {
            "name": trace_entry["tool_name"],
            "arguments": trace_entry["arguments"],
            "result": trace_entry["result"],
            "status": trace_entry["status"],
            "timing": trace_entry["timing"]
        }

    def _create_initial_messages(self, prompt: str) -> List[Dict[str, Any]]:
        """Create initial conversation messages."""
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt}
        ]

    def _run_iteration_loop(self, max_iterations: int) -> str:
        """Run the main LLM/tool iteration loop until complete or max iterations."""
        while self.current_session['iteration'] < max_iterations:
            self.current_session['iteration'] += 1

            # Get LLM response
            response = self._get_llm_decision()

            # If no tool calls, we're done
            if not response.tool_calls:
                return response.content if response.content else "Task completed."

            # Process tool calls
            self._execute_and_record_tools(response.tool_calls)

            # After executing tools, continue the loop to let LLM decide next action
            # The LLM will see the tool results and decide if task is complete

        # Hit max iterations
        return f"Task incomplete: Maximum iterations ({max_iterations}) reached."

    def _get_llm_decision(self):
        """Get the next action/decision from the LLM."""
        # Get tool schemas
        tool_schemas = [tool.to_function_schema() for tool in self.tools] if self.tools else None

        # Show request info
        if self.logger.console:
            self.logger.console.print_llm_request(self.llm.model, self.current_session, self.max_iterations)

        # Invoke before_llm events
        self._invoke_events('before_llm')

        start = time.time()
        response = self.llm.complete(self.current_session['messages'], tools=tool_schemas)
        duration = (time.time() - start) * 1000  # milliseconds

        # Track token usage
        if response.usage:
            self.last_usage = response.usage
            self.total_cost += response.usage.cost

        # Add to trace
        self.current_session['trace'].append({
            'type': 'llm_call',
            'model': self.llm.model,
            'timestamp': start,
            'duration_ms': duration,
            'tool_calls_count': len(response.tool_calls) if response.tool_calls else 0,
            'iteration': self.current_session['iteration'],
            'usage': response.usage,
        })

        # Invoke after_llm events (after trace entry is added)
        self._invoke_events('after_llm')

        self.logger.log_llm_response(self.llm.model, duration, len(response.tool_calls), response.usage)

        return response

    def _execute_and_record_tools(self, tool_calls):
        """Execute requested tools and update conversation messages."""
        execute_and_record_tools(
            tool_calls=tool_calls,
            tools=self.tools,
            agent=self,
            logger=self.logger
        )

    def add_tool(self, tool: Callable):
        """Add a new tool to the agent."""
        if not hasattr(tool, 'to_function_schema'):
            processed_tool = create_tool_from_function(tool)
        else:
            processed_tool = tool
        self.tools.add(processed_tool)

    def remove_tool(self, tool_name: str) -> bool:
        """Remove a tool by name."""
        return self.tools.remove(tool_name)

    def list_tools(self) -> List[str]:
        """List all available tool names."""
        return self.tools.names()

    @property
    def context_percent(self) -> float:
        """Get current context window usage as percentage (0-100).

        Returns the percentage of context window used based on input_tokens
        from the last LLM call. Returns 0 if no LLM calls have been made yet.
        """
        if not self.last_usage:
            return 0.0
        limit = get_context_limit(self.llm.model)
        return (self.last_usage.input_tokens / limit) * 100

    def auto_debug(self, prompt: Optional[str] = None):
        """Start a debugging session for the agent.

        Args:
            prompt: Optional prompt to debug. If provided, runs single debug session.
                   If None, starts interactive debug mode.

        This MVP version provides:
        - Breakpoints at @xray decorated tools
        - Display of tool execution context
        - Interactive menu to continue or edit values

        Examples:
            # Interactive mode
            agent = Agent("my_agent", tools=[search, analyze])
            agent.auto_debug()

            # Single prompt mode
            agent.auto_debug("Find information about Python")
        """
        from .interactive_debugger import InteractiveDebugger
        debugger = InteractiveDebugger(self)
        debugger.start_debug_session(prompt)

