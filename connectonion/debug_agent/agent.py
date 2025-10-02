"""Debug agent for enhanced exception analysis with runtime inspection.

A specialized agent that uses a RuntimeInspector instance to execute code,
inspect objects, test fixes, and validate assumptions using real runtime data.
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