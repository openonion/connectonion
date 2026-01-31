"""
Purpose: Runtime inspector module for AI-powered crash debugging with experiment validation
LLM-Note:
  Dependencies: imports from [agent.py, runtime_inspector.py] | imported by [debug/__init__.py, user code] | tested by [tests/debug/test_runtime_inspector.py]
  Data flow: re-exports create_debug_agent factory and RuntimeInspector class
  State/Effects: no state
  Integration: exposes create_debug_agent() → Agent, RuntimeInspector class for capturing crash context and experimenting with fixes | used for interactive crash debugging
  Performance: trivial
  Errors: none
Runtime inspector for AI-powered crash debugging.

Provides RuntimeInspector class and factory function to create debug agents
that can experiment, test, and validate fixes using actual crashed program data.
"""

from .agent import create_debug_agent
from .runtime_inspector import RuntimeInspector

__all__ = [
    "create_debug_agent",
    "RuntimeInspector"
]