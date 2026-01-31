"""
Purpose: Core agent execution engine - minimal components for running an agent
LLM-Note:
  Dependencies: imports from [agent.py, llm.py, events.py, tool_factory.py, tool_registry.py, tool_executor.py, usage.py] | imported by [connectonion/__init__.py, network/, debug/, useful_tools/] | tested indirectly via component tests
  Data flow: bundles all core components → exports via __all__ → imported as `from connectonion.core import Agent, LLM, ...`
  State/Effects: none (pure re-export module)
  Integration: exposes core API: Agent (orchestrator), LLM (multi-provider abstraction), event decorators (lifecycle hooks), tool utilities (factory, registry, executor), usage tracking (TokenUsage, calculate_cost, get_context_limit)
  Performance: no overhead (just imports)
  Errors: import errors bubble from submodules
Core agent execution engine.

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
