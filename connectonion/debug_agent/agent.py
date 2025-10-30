"""
Purpose: Factory function to create debug agents with runtime inspection capabilities for AI-powered exception analysis
LLM-Note:
  Dependencies: imports from [pathlib, ../agent.py, runtime_inspector.py] | imported by [__init__.py, auto_debug_exception.py] | tested by [tests/test_debug_agent.py]
  Data flow: auto_debug_exception() calls create_debug_agent(frame, traceback, model) → creates RuntimeInspector(frame, traceback) → loads system prompt from prompts/debug_assistant.md → creates Agent with inspector as tool → returns Agent configured for debugging
  State/Effects: reads debug_assistant.md file | creates Agent and RuntimeInspector instances | no writes or global state | inspector has frozen exception frame context
  Integration: exposes create_debug_agent(frame, exception_traceback, model) function | agent gets RuntimeInspector methods as tools via automatic method extraction | used by auto_debug_exception() to analyze crashes
  Performance: one-time setup per exception | loads prompt from file once | inspector methods have minimal overhead
  Errors: FileNotFoundError if prompt file missing | Agent creation errors propagate | model defaults to "o4-mini" for speed | max_iterations=5 for experimentation loops
"""

from pathlib import Path
from ..agent import Agent
from .runtime_inspector import RuntimeInspector


def create_debug_agent(frame=None, exception_traceback=None, model: str = "o4-mini") -> Agent:
    """Create a debug agent with runtime inspection capabilities.

    The agent uses a RuntimeInspector instance as a tool, which provides
    access to the actual runtime state when an exception occurs.

    Args:
        frame: The exception frame (from traceback.tb_frame)
        exception_traceback: The traceback object
        model: LLM model to use (default: o4-mini for speed)

    Returns:
        Configured Agent with RuntimeInspector as a tool
    """
    # Create the inspector with the runtime context
    inspector = RuntimeInspector(frame=frame, exception_traceback=exception_traceback)

    # Load prompt from file
    prompt_file = Path(__file__).parent / "prompts" / "debug_assistant.md"

    # Pass the inspector instance as a tool
    # ConnectOnion will automatically discover all its public methods!
    return Agent(
        name="debug_agent",
        model=model,
        system_prompt=prompt_file,
        tools=[inspector],  # Just pass the class instance!
        max_iterations=5  # More iterations for experimentation
    )