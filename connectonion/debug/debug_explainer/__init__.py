"""
Purpose: Debug explainer module for AI-powered tool choice explanations
LLM-Note:
  Dependencies: imports from [explain_agent.py, explain_context.py] | imported by [debug/__init__.py, user code] | tested by [tests/debug/test_debug_explainer.py]
  Data flow: re-exports explain_tool_choice function and RuntimeContext dataclass
  State/Effects: no state
  Integration: exposes explain_tool_choice(agent, tool_name, tool_args) → str, RuntimeContext dataclass | used for post-hoc analysis of agent decisions
  Performance: trivial
  Errors: none
Debug explainer - AI-powered explanation of tool choices during debugging.

Provides runtime investigation capabilities to explain why an agent
chose to call a specific tool with specific arguments.
"""

from .explain_agent import explain_tool_choice
from .explain_context import RuntimeContext

__all__ = ["explain_tool_choice", "RuntimeContext"]
