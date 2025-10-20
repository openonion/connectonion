"""
Interactive debugging orchestration for AI agents.
This module handles the debugging logic and delegates all UI
interactions to the DebuggerUI class.
"""

from typing import Any, Dict, Optional, List
from .debugger_ui import DebuggerUI, BreakpointContext, BreakpointAction


class InteractiveDebugger:
    """Orchestrates debugging sessions for AI agents.

    This class handles the debugging logic and intercepts tool execution,
    delegating all UI interactions to the DebuggerUI class.
    """

    def __init__(self, agent: Any, ui: Optional[DebuggerUI] = None):
        """Initialize debugger with an agent instance and optional UI.

        Args:
            agent: The Agent instance to debug
            ui: Optional DebuggerUI instance (creates default if None)
        """
        self.agent = agent
        self.ui = ui or DebuggerUI()
        self.original_execute_single_tool = None

    def start_debug_session(self, prompt: Optional[str] = None):
        """Start a debugging session for the agent.

        Args:
            prompt: Optional prompt to debug. If provided, runs single session.
                   If None, runs in interactive mode.

        Orchestrates the debug session by:
        1. Showing welcome message via UI
        2. Either using provided prompt or getting from user
        3. Executing tasks with debugging enabled
        4. Showing results via UI
        """
        # Show welcome
        self.ui.show_welcome(self.agent.name)

        # Determine mode based on prompt
        if prompt:
            # Single prompt mode - execute once and exit
            self._execute_debug_task(prompt)
        else:
            # Interactive mode - loop until user quits
            while True:
                # Get prompt from user
                user_prompt = self.ui.get_user_prompt()
                if user_prompt is None:
                    break  # User wants to quit

                self._execute_debug_task(user_prompt)

    def _execute_debug_task(self, prompt: str):
        """Execute a single task with debugging enabled.

        Args:
            prompt: The task prompt to execute
        """
        # Attach debugger to intercept tool execution
        self._attach_debugger_to_tool_execution()

        try:
            # Execute the prompt with debugging
            self.ui.show_executing(prompt)
            result = self.agent.input(prompt)
            self.ui.show_result(result)

        except KeyboardInterrupt:
            self.ui.show_interrupted()

        finally:
            # Detach debugger after task completes
            self._detach_debugger_from_tool_execution()

    def _attach_debugger_to_tool_execution(self):
        """Attach debugger to intercept tool execution and pause at breakpoints.

        This installs an interceptor that will:
        - Execute tools normally
        - Check if the tool has @xray or encountered an error
        - Pause execution and show UI if breakpoint conditions are met
        - Only affect this specific agent instance
        """
        from . import tool_executor
        from .xray import is_xray_enabled

        # Store original function for restoration later
        self.original_execute_single_tool = tool_executor.execute_single_tool

        # Create interceptor function
        def tool_execution_interceptor(tool_name, tool_args, tool_id, tool_map, agent, console):
            # Execute tool normally
            trace_entry = self.original_execute_single_tool(
                tool_name, tool_args, tool_id, tool_map, agent, console
            )

            # CRITICAL: Only debug OUR agent, not all agents in the process
            if agent is not self.agent:
                return trace_entry  # Skip debugging for other agents

            # Check if tool has @xray decorator or if there was an error
            tool = tool_map.get(tool_name)
            should_pause = False

            if tool and is_xray_enabled(tool):
                should_pause = True
            elif trace_entry.get('status') == 'error':
                should_pause = True  # Always pause on errors for debugging

            if should_pause:
                # Pause at breakpoint and show UI
                self._show_breakpoint_ui_and_wait_for_continue(tool_name, tool_args, trace_entry)

            return trace_entry

        # Install the interceptor
        tool_executor.execute_single_tool = tool_execution_interceptor

    def _detach_debugger_from_tool_execution(self):
        """Detach debugger and restore normal tool execution flow.

        This removes the interceptor and restores the original
        tool execution function.
        """
        if self.original_execute_single_tool:
            from . import tool_executor
            tool_executor.execute_single_tool = self.original_execute_single_tool

    def _show_breakpoint_ui_and_wait_for_continue(self, tool_name: str, tool_args: Dict, trace_entry: Dict):
        """Show breakpoint UI and wait for user to continue.

        This delegates all UI interaction to the DebuggerUI class and
        handles the logic of what to do based on user choices.

        Args:
            tool_name: Name of the tool that executed
            tool_args: Arguments passed to the tool
            trace_entry: Trace entry with execution result (can be modified)
        """
        # Get session context and agent info
        session = self.agent.current_session or {}

        # Gather previous tools from trace
        trace = session.get('trace', [])
        previous_tools = [
            entry['tool_name'] for entry in trace[-3:]
            if entry.get('type') == 'tool_execution' and entry.get('tool_name') != tool_name
        ]

        # Get preview of next LLM action
        next_actions = self._get_llm_next_action_preview(tool_name, trace_entry)

        # Get the actual tool function for source inspection
        tool = self.agent.tool_map.get(tool_name)
        tool_function = tool.run if tool and hasattr(tool, 'run') else None

        # Create context for UI with extended debugging info
        context = BreakpointContext(
            tool_name=tool_name,
            tool_args=tool_args,
            trace_entry=trace_entry,
            user_prompt=session.get('user_prompt', ''),
            iteration=session.get('iteration', 0),
            max_iterations=self.agent.max_iterations,
            previous_tools=previous_tools,
            next_actions=next_actions,
            tool_function=tool_function  # Pass the actual function
        )

        # Keep showing menu until user chooses to continue
        while True:
            action = self.ui.show_breakpoint(context)

            if action == BreakpointAction.CONTINUE:
                break  # Exit the breakpoint
            elif action == BreakpointAction.EDIT:
                # Let user edit values in Python REPL
                modifications = self.ui.edit_value(context, agent=self.agent)

                # Apply modifications
                if 'result' in modifications:
                    trace_entry['result'] = modifications['result']
                    # Re-generate preview with edited value
                    next_actions = self._get_llm_next_action_preview(tool_name, trace_entry)
                    context.next_actions = next_actions

                if 'tool_args' in modifications:
                    # Update tool_args in context (for display purposes)
                    context.tool_args.update(modifications['tool_args'])

                if 'iteration' in modifications:
                    # Update iteration in session
                    if self.agent.current_session:
                        self.agent.current_session['iteration'] = modifications['iteration']
                        context.iteration = modifications['iteration']

                if 'max_iterations' in modifications:
                    # Update max_iterations on agent
                    self.agent.max_iterations = modifications['max_iterations']
                    context.max_iterations = modifications['max_iterations']
            elif action == BreakpointAction.QUIT:
                # User wants to quit debugging
                raise KeyboardInterrupt("User quit debugging session")

    def _get_llm_next_action_preview(self, tool_name: str, trace_entry: Dict) -> Optional[List[Dict]]:
        """Get a preview of what the LLM plans to do next without executing.

        This simulates the next iteration by calling the LLM with the current
        tool result, but doesn't actually execute the planned tools.

        CRITICAL TIMING NOTE:
        =====================
        The debugger pauses DURING tool execution (inside execute_single_tool),
        which means the current tool's result hasn't been added to messages yet.

        Timeline:
        1. tool_executor.py:41 → Adds assistant message with tool_calls
        2. tool_executor.py:46-53 → Executes tool → **DEBUGGER PAUSES HERE**
        3. tool_executor.py:56-60 → Adds tool result message (NOT REACHED YET!)

        So agent.current_session['messages'] contains:
        - ✅ Assistant message with ALL tool_calls
        - ✅ Results from PREVIOUS tools (if parallel execution)
        - ❌ Result from CURRENT tool (not added yet - we're paused!)

        Therefore, we must manually append the current tool's result to get
        a complete message history for the LLM preview.

        Args:
            tool_name: Name of the tool that just executed
            trace_entry: The execution result

        Returns:
            List of planned tool calls (each with 'name' and 'args'),
            or None if no tools planned or error occurred
        """
        try:
            # Start with current messages (has assistant message + previous tool results)
            temp_messages = self.agent.current_session['messages'].copy()

            # Add the current tool's result to complete the message history
            # (See docstring above for why this is necessary - we're paused mid-execution)
            for msg in reversed(temp_messages):
                if msg.get('role') == 'assistant' and msg.get('tool_calls'):
                    # Find the tool_call_id matching our current tool
                    for tool_call in msg.get('tool_calls', []):
                        if tool_call.get('function', {}).get('name') == tool_name:
                            # Add missing tool result message for preview
                            temp_messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call['id'],
                                "content": str(trace_entry.get('result', ''))
                            })
                            break
                    break

            # Call LLM to get its next planned action
            # Use the agent's LLM and tools configuration
            tool_schemas = [tool.to_function_schema() for tool in self.agent.tools] if self.agent.tools else None

            # Make the LLM call
            response = self.agent.llm.complete(temp_messages, tools=tool_schemas)

            # Extract planned tool calls
            if response.tool_calls:
                next_actions = []
                for tool_call in response.tool_calls:
                    next_actions.append({
                        'name': tool_call.name,
                        'args': tool_call.arguments
                    })
                return next_actions
            else:
                # No more tools planned - task might be complete
                return []

        except Exception as e:
            # If preview fails, return None to indicate unavailable
            # This is non-critical, so we don't want to break the debugger
            # Show the actual error for debugging (remove this later)
            print(f"[dim]Preview error: {type(e).__name__}: {str(e)}[/dim]")
            return None