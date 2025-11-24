"""
Purpose: Orchestrate AI agent execution with LLM calls, tool execution, and automatic logging
LLM-Note:
  Dependencies: imports from [llm.py, tool_factory.py, prompts.py, decorators.py, console.py, tool_executor.py, trust.py] | imported by [__init__.py, trust.py, debug_agent/__init__.py] | tested by [tests/test_agent.py, tests/test_agent_prompts.py, tests/test_agent_workflows.py]
  Data flow: receives user prompt: str from Agent.input() → creates/extends current_session with messages → calls llm.complete() with tool schemas → receives LLMResponse with tool_calls → executes tools via tool_executor.execute_and_record_tools() → appends tool results to messages → repeats loop until no tool_calls or max_iterations → console logs to .co/logs/{name}.log → returns final response: str
  State/Effects: modifies self.current_session['messages', 'trace', 'turn', 'iteration'] | writes to .co/logs/{name}.log via console.py (default) or custom log path | initializes trust agent if trust parameter provided
  Integration: exposes Agent(name, tools, system_prompt, model, trust, log), .input(prompt), .execute_tool(name, args), .add_tool(func), .remove_tool(name), .list_tools(), .reset_conversation() | tools auto-converted via tool_factory.create_tool_from_function() | tool execution delegates to tool_executor module | trust system via trust.create_trust_agent() | log defaults to .co/logs/ (None), can be True (current dir), False (disabled), or custom path
  Performance: max_iterations=10 default (configurable per-input) | session state persists across turns for multi-turn conversations | tool_map provides O(1) tool lookup by name
  Errors: LLM errors bubble up | tool execution errors captured in trace and returned to LLM for retry | trust agent creation can fail if invalid trust parameter
"""

import os
import sys
import time
from typing import List, Optional, Dict, Any, Callable, Union
from pathlib import Path
from .llm import LLM, create_llm
from .tool_factory import create_tool_from_function, extract_methods_from_instance, is_class_instance
from .prompts import load_system_prompt
from .decorators import (
    _is_replay_enabled  # Only need this for replay check
)
from .console import Console
from .tool_executor import execute_and_record_tools, execute_single_tool
from .events import EventHandler

# Handle trust parameter - convert to trust agent
from .trust import create_trust_agent, get_default_trust_level
class Agent:
    """Agent that can use tools to complete tasks."""
    
    def __init__(
        self,
        name: str,
        llm: Optional[LLM] = None,
        tools: Optional[Union[List[Callable], Callable, Any]] = None,
        system_prompt: Union[str, Path, None] = None,
        api_key: Optional[str] = None,
        model: str = "co/o4-mini",
        max_iterations: int = 10,
        trust: Optional[Union[str, Path, 'Agent']] = None,
        log: Optional[Union[bool, str, Path]] = None,
        plugins: Optional[List[List[EventHandler]]] = None,
        on_events: Optional[List[EventHandler]] = None
    ):
        self.name = name
        self.system_prompt = load_system_prompt(system_prompt)
        self.max_iterations = max_iterations

        # Current session context (runtime only)
        self.current_session = None

        # Setup file logging (default to .co/logs/)
        log_file = None
        if log is None:
            # NEW: Default to .co/logs/ for automatic audit trail
            log_file = Path.cwd() / '.co' / 'logs' / f'{name}.log'
        elif log is True:
            # Explicit True: {name}.log in current directory
            log_file = Path(f"{name}.log")
        elif log is False:
            # Explicit opt-out: no logging
            log_file = None
        elif log:
            # Custom log file path
            log_file = Path(log)

        # Environment variable override (highest priority)
        if os.getenv('CONNECTONION_LOG'):
            log_file = Path(os.getenv('CONNECTONION_LOG'))

        # Initialize console (always shows output, optional file logging)
        self.console = Console(log_file=log_file)
        

        
        # If trust is None, check for environment default
        if trust is None:
            trust = get_default_trust_level()
        
        # Only create trust agent if we're not already a trust agent
        # (to prevent infinite recursion when creating trust agents)
        if name and name.startswith('trust_agent_'):
            self.trust = None  # Trust agents don't need their own trust agents
        else:
            # Store the trust agent directly (or None)
            self.trust = create_trust_agent(trust, api_key=api_key, model=model)

        # Initialize event registry
        self.events = {
            'after_user_input': [],
            'before_llm': [],
            'after_llm': [],
            'before_tool': [],
            'after_tool': [],
            'on_error': []
        }

        # Register plugin events (flatten list of lists)
        if plugins:
            for event_list in plugins:
                for event_func in event_list:
                    self._register_event(event_func)

        # Register custom event handlers
        if on_events:
            for event_func in on_events:
                self._register_event(event_func)

        # Process tools: convert raw functions and class instances to tool schemas automatically
        processed_tools = []
        if tools is not None:
            # Normalize tools to a list
            if isinstance(tools, list):
                tools_list = tools
            else:
                tools_list = [tools]
            
            # Process each tool
            for tool in tools_list:
                if is_class_instance(tool):
                    # Extract methods from class instance
                    methods = extract_methods_from_instance(tool)
                    processed_tools.extend(methods)
                elif callable(tool):
                    # Handle function or method
                    if not hasattr(tool, 'to_function_schema'):
                        processed_tools.append(create_tool_from_function(tool))
                    else:
                        processed_tools.append(tool)  # Already a valid tool
                else:
                    # Skip non-callable, non-instance objects
                    continue
        
        self.tools = processed_tools

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
        
        # Create tool mapping for quick lookup
        self.tool_map = {tool.name: tool for tool in self.tools}

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

    def input(self, prompt: str, max_iterations: Optional[int] = None) -> str:
        """Provide input to the agent and get response.

        Args:
            prompt: The input prompt or data to process
            max_iterations: Override agent's max_iterations for this request

        Returns:
            The agent's response after processing the input
        """
        start_time = time.time()
        self.console.print(f"[bold]INPUT:[/bold] {prompt[:100]}...")

        # Initialize session on first input, or continue existing conversation
        if self.current_session is None:
            self.current_session = {
                'messages': [{"role": "system", "content": self.system_prompt}],
                'trace': [],
                'turn': 0  # Track conversation turns
            }

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

        # Calculate duration (console already logged everything)
        duration = time.time() - turn_start

        self.console.print(f"[green]✓ Complete[/green] ({duration:.1f}s)")
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
            tool_map=self.tool_map,
            agent=self,
            console=self.console
        )

        # Note: trace_entry already added to session in execute_single_tool

        # Fire events (same as execute_and_record_tools)
        # on_error fires first for errors/not_found, then after_tool always fires
        if trace_entry["status"] in ("error", "not_found"):
            self._invoke_events('on_error')

        # after_tool fires for ALL tool executions (success, error, not_found)
        self._invoke_events('after_tool')

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
            iteration = self.current_session['iteration']

            self.console.print(f"[dim]Iteration {iteration}/{max_iterations}[/dim]")

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
        msg_count = len(self.current_session['messages'])
        tool_count = len(self.tools) if self.tools else 0
        self.console.print(f"[yellow]→[/yellow] LLM Request ({self.llm.model}) • {msg_count} msgs • {tool_count} tools")

        # Invoke before_llm events
        self._invoke_events('before_llm')

        start = time.time()
        response = self.llm.complete(self.current_session['messages'], tools=tool_schemas)
        duration = (time.time() - start) * 1000  # milliseconds

        # Add to trace
        self.current_session['trace'].append({
            'type': 'llm_call',
            'model': self.llm.model,
            'timestamp': start,
            'duration_ms': duration,
            'tool_calls_count': len(response.tool_calls) if response.tool_calls else 0,
            'iteration': self.current_session['iteration']
        })

        # Invoke after_llm events (after trace entry is added)
        self._invoke_events('after_llm')

        if response.tool_calls:
            self.console.print(f"[green]←[/green] LLM Response ({duration/1000:.1f}s): {len(response.tool_calls)} tool calls")
        else:
            self.console.print(f"[green]←[/green] LLM Response ({duration/1000:.1f}s)")

        return response

    def _execute_and_record_tools(self, tool_calls):
        """Execute requested tools and update conversation messages."""
        # Delegate to tool_executor module
        execute_and_record_tools(
            tool_calls=tool_calls,
            tool_map=self.tool_map,
            agent=self,  # Agent has current_session with messages and trace
            console=self.console
        )

    def add_tool(self, tool: Callable):
        """Add a new tool to the agent."""
        # Process the tool before adding it
        if not hasattr(tool, 'to_function_schema'):
            processed_tool = create_tool_from_function(tool)
        else:
            processed_tool = tool
            
        self.tools.append(processed_tool)
        self.tool_map[processed_tool.name] = processed_tool
    
    def remove_tool(self, tool_name: str) -> bool:
        """Remove a tool by name."""
        if tool_name in self.tool_map:
            tool = self.tool_map[tool_name]
            self.tools.remove(tool)
            del self.tool_map[tool_name]
            return True
        return False
    
    def list_tools(self) -> List[str]:
        """List all available tool names."""
        return [tool.name for tool in self.tools]

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

    def serve(self, relay_url: str = "wss://oo.openonion.ai/ws/announce"):
        """
        Start serving this agent on the relay network.

        This makes the agent discoverable and connectable by other agents.
        The agent will:
        1. Load/generate Ed25519 keys for identity
        2. Connect to relay server
        3. Send ANNOUNCE message with agent summary
        4. Wait for incoming TASK messages
        5. Process tasks and send responses

        Args:
            relay_url: WebSocket URL for relay (default: production relay)

        Example:
            >>> agent = Agent("translator", tools=[translate])
            >>> agent.serve()  # Runs forever, processing tasks
            ✓ Announced to relay: 0x3d4017c3...
            Debug: https://oo.openonion.ai/agent/0x3d4017c3e843895a...
            ♥ Sent heartbeat
            → Received task: abc12345...
            ✓ Sent response: abc12345...

        Note:
            This is a blocking call. The agent will run until interrupted (Ctrl+C).
        """
        import asyncio
        from . import address, announce, relay

        # Load or generate keys
        co_dir = Path.cwd() / '.co'
        addr_data = address.load(co_dir)

        if addr_data is None:
            self.console.print("[yellow]No keys found, generating new identity...[/yellow]")
            addr_data = address.generate()
            address.save(addr_data, co_dir)
            self.console.print(f"[green]✓ Keys saved to {co_dir / 'keys'}[/green]")

        # Create ANNOUNCE message
        # Use system_prompt as summary (first 1000 chars)
        summary = self.system_prompt[:1000] if self.system_prompt else f"{self.name} agent"
        announce_msg = announce.create_announce_message(
            addr_data,
            summary,
            endpoints=[]  # MVP: No direct endpoints yet
        )

        self.console.print(f"\n[bold]Starting agent: {self.name}[/bold]")
        self.console.print(f"Address: {addr_data['address']}")
        self.console.print(f"Debug: https://oo.openonion.ai/agent/{addr_data['address']}\n")

        # Define async task handler
        async def task_handler(prompt: str) -> str:
            """Handle incoming task by running through agent.input()"""
            return self.input(prompt)

        # Run serve loop
        async def run():
            ws = await relay.connect(relay_url)
            await relay.serve_loop(ws, announce_msg, task_handler)

        # Run the async loop
        asyncio.run(run())