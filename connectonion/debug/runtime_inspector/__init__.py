"""Runtime inspector for AI-powered crash debugging.

Provides RuntimeInspector class and factory function to create debug agents
that can experiment, test, and validate fixes using actual crashed program data.
"""

from .agent import create_debug_agent
from .runtime_inspector import RuntimeInspector

__all__ = [
    "create_debug_agent",
    "RuntimeInspector"
]