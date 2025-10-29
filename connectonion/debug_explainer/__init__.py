"""Debug explainer - AI-powered explanation of tool choices during debugging.

Provides runtime investigation capabilities to explain why an agent
chose to call a specific tool with specific arguments.
"""

from .explain_agent import explain_tool_choice
from .explain_context import RuntimeContext

__all__ = ["explain_tool_choice", "RuntimeContext"]
