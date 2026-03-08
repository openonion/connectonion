"""
Sub-agent task delegation system.

This module provides the task() function for delegating work to specialized sub-agents.
Sub-agents are defined in .md files with YAML frontmatter and auto-discovered on import.

Usage:
    from connectonion import task

    # Explore codebase
    task("Find all authentication files", "explore")

    # Design implementation plan
    task("Design a plan to add dark mode", "plan")

Available sub-agents are automatically discovered from .md files in this directory.
"""

from typing import Optional
from .loader import load_subagents, get_subagent_definition, list_subagents
from .factory import create_subagent


def task(prompt: str, agent_type: str = "explore") -> str:
    """
    Delegate a task to a specialized sub-agent.

    Sub-agents are lightweight, focused agents optimized for specific tasks.
    They have no memory of the parent agent's conversation.

    Args:
        prompt: Task description (must be self-contained with full context)
        agent_type: Type of sub-agent to use (default: "explore")

    Returns:
        Sub-agent's response as a string

    Available agent types:
        - explore: Fast codebase exploration (read-only, cheap model)
        - plan: Implementation planning (read-only, smart model)

    Examples:
        # Find files
        task("Find all API endpoints and their handlers", "explore")

        # Design plan
        task("Design a plan to add user authentication", "plan")

    Important:
        - Sub-agents have NO memory of parent conversation
        - Include ALL necessary context in the prompt
        - Sub-agents are stateless - fresh instance per call
    """
    # Ensure definitions are loaded
    if not list_subagents():
        load_subagents()

    # Validate agent type
    available = list_subagents()
    if agent_type not in available:
        available_str = ", ".join(available)
        return f"Error: Unknown agent type '{agent_type}'. Available: {available_str}"

    # Get definition for logging
    definition = get_subagent_definition(agent_type)
    if not definition:
        return f"Error: Failed to load definition for {agent_type}"

    # Create sub-agent
    subagent = create_subagent(agent_type)
    if subagent is None:
        return f"Error: Failed to create {agent_type} agent"

    # Log task start (optional, can be disabled)
    short_prompt = prompt[:60] + "..." if len(prompt) > 60 else prompt
    print(f"  ▶ Task ({agent_type}): {short_prompt}")
    print(f"    {definition.description}")

    # Execute task
    result = subagent.input(prompt)

    # Log completion
    print(f"  ◀ Task completed")

    return result


# Auto-load sub-agent definitions on import
load_subagents()


__all__ = [
    "task",
    "load_subagents",
    "list_subagents",
    "get_subagent_definition",
]
