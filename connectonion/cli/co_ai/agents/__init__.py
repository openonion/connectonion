"""
LLM-Note: Sub-agent system for OO coding assistant.

This module provides access to specialized sub-agents that can be invoked
via the Task tool for specific purposes (exploration, planning, etc.).

Key components:
- SUBAGENTS: Dictionary of available sub-agent configurations
- get_subagent(type): Factory function to create sub-agent instances

Architecture:
- Registry pattern with agent configurations in registry.py
- Each sub-agent has specific tools, model, and max_iterations
- Currently supports: "explore" (codebase exploration), "plan" (implementation planning)
"""

from connectonion.cli.co_ai.agents.registry import SUBAGENTS, get_subagent

__all__ = ["SUBAGENTS", "get_subagent"]
