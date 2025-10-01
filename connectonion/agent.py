"""Core Agent implementation for ConnectOnion."""

import os
import sys
import time
from typing import List, Optional, Dict, Any, Callable, Union
from pathlib import Path
from dotenv import load_dotenv
from .llm import LLM, create_llm
from .history import History
from .tool_factory import create_tool_from_function, extract_methods_from_instance, is_class_instance
from .prompts import load_system_prompt
from .decorators import (
    _is_replay_enabled  # Only need this for replay check
)
from .console import Console
from .tool_executor import execute_and_record_tools, execute_single_tool

# Load environment variables from .env file
load_dotenv()

        # Handle trust parameter - convert to trust agent
from .trust import create_trust_agent, get_default_trust_level
class Agent:
    """Agent that can use tools to complete tasks."""
    
    def __init__(
        self,
        name: str,
        llm: Optional[LLM] = None,
        tools: Optional[Union[List[Callable], Callable, Any]] = None, system_prompt: Union[str, Path, None] = None,
        api_key: Optional[str] = None,
        model: str = "o4-mini",
        max_iterations: int = 10,
        trust: Optional[Union[str, Path, 'Agent']] = None,
        log: Optional[Union[bool, str, Path]] = None
    ):
        self.name = name
        self.system_prompt = load_system_prompt(system_prompt)
        self.max_iterations = max_iterations

        # Current session context (runtime only)
        self.current_session = None

        # Setup optional file logging
        log_file = None
        if log is True:
            # Default log file: {name}.log in current directory
            log_file = Path(f"{name}.log")
        elif log:
            # Custom log file path
            log_file = Path(log)
        elif os.getenv('CONNECTONION_LOG'):
            # Environment variable override
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

        self.history = History(name)
        
        # Initialize LLM
        if llm:
            self.llm = llm
        else:
            # Use factory function to create appropriate LLM based on model
            # For co/ models, the JWT token from 'co auth' is used automatically
            self.llm = create_llm(model=model, api_key=api_key)
        
        # Create tool mapping for quick lookup
        self.tool_map = {tool.name: tool for tool in self.tools}
    
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

        # Process
        self.current_session['iteration'] = 0  # Reset iteration for this turn
        result = self._run_iteration_loop(
            max_iterations or self.max_iterations
        )

        # Save this interaction to history (per turn, not per session)
        duration = time.time() - turn_start
        self._save_interaction_history(prompt, result, duration)

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

        # Hit max iterations
        return f"Task incomplete: Maximum iterations ({max_iterations}) reached."

    def _get_llm_decision(self):
        """Get the next action/decision from the LLM."""
        self.console.print(f"[yellow]→[/yellow] LLM Request ({self.llm.model})")

        # Get tool schemas
        tool_schemas = [tool.to_function_schema() for tool in self.tools] if self.tools else None

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

        if response.tool_calls:
            self.console.print(f"[green]←[/green] LLM Response ({duration:.0f}ms): {len(response.tool_calls)} tool calls")
        else:
            self.console.print(f"[green]←[/green] LLM Response ({duration:.0f}ms)")

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

    def _save_interaction_history(self, prompt: str, result: str, duration: float):
        """Save the interaction to history for behavior tracking."""
        # Extract tool calls from trace for backward compatibility
        tool_calls = [
            entry for entry in self.current_session['trace']
            if entry.get('type') == 'tool_execution'
        ]

        self.history.record(
            user_prompt=prompt,
            tool_calls=tool_calls,
            result=result,
            duration=duration
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