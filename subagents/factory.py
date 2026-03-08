"""
Sub-agent factory - Creates Agent instances from definitions.

This module provides the factory function to create Agent instances from
sub-agent definitions loaded by the loader module.

Architecture:
- Resolves tool names to actual tool functions
- Creates Agent with specialized config
- NO plugins for sub-agents (keep them simple)
- Fresh instance per call (stateless design)
"""

from typing import Optional, List
from .loader import get_subagent_definition


def _resolve_tools(tool_names: List[str]) -> List:
    """
    Resolve tool group names to actual tool instances.

    Supported tool groups:
    - file_read: Read-only file operations (glob, grep, read_file)
    - file_write: Full file operations (glob, grep, read_file, edit, write, multi_edit)
    - browser: Browser automation (navigate, click, type, screenshot)
    - web: HTTP requests (fetch)
    - shell: Bash commands (bash)
    - email: Email operations (send, get, mark_read, mark_unread)

    Args:
        tool_names: List of tool group names (e.g., ["file_read", "web"])

    Returns:
        List of tool instances/functions
    """
    # Import here to avoid circular dependency
    from connectonion.useful_tools.file_tools import FileTools
    from connectonion import bash, WebFetch

    TOOL_GROUPS = {
        "file_read": FileTools(permission="read"),
        "file_write": FileTools(permission="write"),
        "web": WebFetch,
        "shell": bash,
    }

    # Optional tools (only import if needed)
    # "browser": BrowserAutomation(),  # Import only if browser tools available
    # "email": Gmail(),                # Import only if email tools available

    tools = []
    for name in tool_names:
        if name in TOOL_GROUPS:
            tools.append(TOOL_GROUPS[name])
        else:
            # Unknown tool group - log warning
            import sys
            print(f"Warning: Unknown tool group '{name}', skipping", file=sys.stderr)

    return tools


def create_subagent(agent_type: str):
    """
    Create a sub-agent from definition file.

    Args:
        agent_type: Name of sub-agent (e.g., "explore", "plan")

    Returns:
        Configured Agent instance or None if not found

    Example:
        subagent = create_subagent("explore")
        result = subagent.input("Find all API endpoints")
    """
    from connectonion import Agent

    definition = get_subagent_definition(agent_type)

    if not definition:
        return None

    # Resolve tool group names to actual tools
    tools = _resolve_tools(definition.tools)

    return Agent(
        name=f"subagent-{definition.name}",
        tools=tools,
        plugins=[],  # NO plugins for sub-agents
        system_prompt=definition.system_prompt,
        model=definition.model,
        max_iterations=definition.max_iterations,
    )
