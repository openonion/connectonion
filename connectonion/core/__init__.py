"""Core agent execution engine.

This module contains the minimal set of components needed to run an agent:
- Agent: Main orchestrator
- LLM: Multi-provider LLM abstraction
- Events: Event system for lifecycle hooks
- Tools: Tool execution, factory, and registry
- Usage: Token tracking and cost calculation
"""

from .agent import Agent
from .llm import LLM, create_llm, TokenUsage
from .events import (
    EventHandler,
    after_user_input,
    before_llm,
    after_llm,
    before_each_tool,
    before_tools,
    after_each_tool,
    after_tools,
    on_error,
    on_complete,
)
from .tool_factory import create_tool_from_function, extract_methods_from_instance, is_class_instance
from .tool_registry import ToolRegistry
from .tool_executor import execute_and_record_tools, execute_single_tool
from .usage import TokenUsage, calculate_cost, get_context_limit

__all__ = [
    "Agent",
    "LLM",
    "create_llm",
    "TokenUsage",
    "EventHandler",
    "after_user_input",
    "before_llm",
    "after_llm",
    "before_each_tool",
    "before_tools",
    "after_each_tool",
    "after_tools",
    "on_error",
    "on_complete",
    "create_tool_from_function",
    "extract_methods_from_instance",
    "is_class_instance",
    "ToolRegistry",
    "execute_and_record_tools",
    "execute_single_tool",
    "calculate_cost",
    "get_context_limit",
]
