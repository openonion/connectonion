"""Core Agent implementation for ConnectOnion."""

import time
from typing import List, Optional, Dict, Any, Callable, Union
from pathlib import Path
from .llm import LLM, OpenAILLM
from .history import History
from .tools import create_tool_from_function
from .prompts import load_system_prompt
from .decorators import (
    _inject_context_for_tool, 
    _clear_context_after_tool,
    _is_xray_enabled,
    _is_replay_enabled
)


class Agent:
    """Agent that can use tools to complete tasks."""
    
    def __init__(
        self,
        name: str,
        llm: Optional[LLM] = None,
        tools: Optional[List[Callable]] = None,
        system_prompt: Union[str, Path, None] = None,
        api_key: Optional[str] = None,
        model: str = "gpt-5-mini"
    ):
        self.name = name
        self.system_prompt = load_system_prompt(system_prompt)
        
        # Process tools: convert raw functions to tool schemas automatically
        processed_tools = []
        if tools:
            for tool in tools:
                if not hasattr(tool, 'to_function_schema'):
                    processed_tools.append(create_tool_from_function(tool))
                else:
                    processed_tools.append(tool)  # Already a valid tool
        self.tools = processed_tools

        self.history = History(name)
        
        # Initialize LLM
        if llm:
            self.llm = llm
        else:
            # Default to OpenAI if no LLM provided
            self.llm = OpenAILLM(api_key=api_key, model=model)
        
        # Create tool mapping for quick lookup
        self.tool_map = {tool.name: tool for tool in self.tools}
    
    def run(self, task: str) -> str:
        """Execute a task, potentially using tools."""
        start_time = time.time()
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task}
        ]
        
        # Get tool schemas for LLM
        tool_schemas = [tool.to_function_schema() for tool in self.tools] if self.tools else None
        
        # Track all tool calls for this task
        all_tool_calls = []  # Persisted in History for behavior tracking
        execution_history = []  # Used by xray.trace() with timing data
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Call LLM
            response = self.llm.complete(messages, tools=tool_schemas)
            
            # If no tool calls, we're done
            if not response.tool_calls:
                if response.content:
                    result = response.content
                else:
                    result = "Task completed."
                break
            
            # Add assistant message with ALL tool calls first
            assistant_tool_calls = []
            for tool_call in response.tool_calls:
                assistant_tool_calls.append({
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": str(tool_call.arguments)
                    }
                })
            
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": assistant_tool_calls
            })
            
            # Execute tool calls and add individual tool responses
            for tool_call in response.tool_calls:
                tool_name = tool_call.name
                tool_args = tool_call.arguments
                
                # Record tool call
                tool_record = {
                    "name": tool_name,
                    "arguments": tool_args,
                    "call_id": tool_call.id,
                    "timing": 0  # Will be updated after execution
                }
                
                # Execute tool
                if tool_name in self.tool_map:
                    try:
                        # Prepare context data for debugging decorators
                        previous_tools = [tc["name"] for tc in all_tool_calls]
                        
                        # Track execution for xray.trace() functionality
                        # This builds a parallel structure to tool_calls but with timing data
                        exec_entry = {
                            "tool_name": tool_name,
                            "parameters": tool_args,
                            "status": "pending"  # Will be updated after execution
                        }
                        execution_history.append(exec_entry)
                        
                        # Check if tool has @xray decorator and inject context
                        tool_func = self.tool_map[tool_name]
                        if _is_xray_enabled(tool_func):
                            _inject_context_for_tool(
                                agent=self,
                                task=task,
                                messages=messages.copy(),  # Provide copy to avoid modifications
                                iteration=iteration,
                                previous_tools=previous_tools,
                                execution_history=execution_history  # Pass execution history
                            )
                        
                        # Time the execution
                        tool_start = time.time()
                        # Execute the tool (call the function directly to preserve decorators)
                        tool_result = tool_func(**tool_args)
                        tool_duration = (time.time() - tool_start) * 1000  # Convert to milliseconds
                        
                        # Update execution entry with timing and result
                        # This data is used by xray.trace() to show execution flow
                        exec_entry["timing"] = tool_duration
                        exec_entry["result"] = tool_result
                        exec_entry["status"] = "success"
                        
                        # Clear context after execution
                        if _is_xray_enabled(tool_func):
                            _clear_context_after_tool()
                            
                        tool_record["result"] = str(tool_result)  # Ensure string for JSON serialization
                        tool_record["status"] = "success"
                        tool_record["timing"] = tool_duration  # Add timing for xray.trace() to use later
                        
                        messages.append({
                            "role": "tool",
                            "content": str(tool_result),  # Ensure result is string
                            "tool_call_id": tool_call.id
                        })
                        
                    except Exception as e:
                        # Update execution entry for error case
                        # Calculate timing if execution started
                        if 'tool_start' in locals():
                            tool_duration = (time.time() - tool_start) * 1000
                            exec_entry["timing"] = tool_duration
                        exec_entry["status"] = "error"
                        exec_entry["error"] = str(e)
                        
                        # Make sure to clear context even if there's an error
                        tool_func = self.tool_map[tool_name]
                        if _is_xray_enabled(tool_func):
                            _clear_context_after_tool()
                            
                        tool_result = f"Error executing tool: {str(e)}"
                        tool_record["result"] = tool_result
                        tool_record["status"] = "error"
                        if 'tool_duration' in locals():
                            tool_record["timing"] = tool_duration
                        
                        messages.append({
                            "role": "tool",
                            "content": str(tool_result),  # Ensure result is string
                            "tool_call_id": tool_call.id
                        })
                else:
                    tool_result = f"Tool '{tool_name}' not found"
                    tool_record["result"] = tool_result
                    tool_record["status"] = "not_found"
                    
                    messages.append({
                        "role": "tool",
                        "content": tool_result,
                        "tool_call_id": tool_call.id
                    })
                
                all_tool_calls.append(tool_record)
        
        # If we hit max iterations, set appropriate result
        if iteration >= max_iterations:
            result = "Task incomplete: Maximum iterations reached."
        
        # Record behavior
        duration = time.time() - start_time
        self.history.record(
            task=task,
            tool_calls=all_tool_calls,
            result=result,
            duration=duration
        )
        
        return result
    
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