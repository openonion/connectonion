"""
LLM-Note: Task delegation tool for co_ai - Delegates tasks to specialized sub-agents (explore, plan)

Key components:
- task() function: Main entry point for delegating to sub-agents
- Agent types: "explore" (codebase exploration), "plan" (implementation planning)
- Uses SDK subagents plugin (connectonion.useful_plugins.subagents)

Architecture:
- Used by co_ai main agent to delegate complex tasks
- Wraps SDK's task() function with Rich console output
- SDK handles agent creation, discovery, and execution
"""

from typing import Literal

from rich.console import Console
from rich.text import Text

# Use SDK subagents plugin instead of registry
from connectonion.useful_plugins.subagents import task as sdk_task, _discover_all_agents

console = Console()


def task(
    prompt: str,
    agent_type: Literal["explore", "plan"] = "explore",
) -> str:
    """
    Delegate a task to a specialized sub-agent.

    Use this when you need to:
    - Explore the codebase (find files, search code, understand structure)
    - Plan an implementation (design approach, identify files to change)

    Args:
        prompt: The task description for the sub-agent
        agent_type: Type of sub-agent to use
            - "explore": Fast codebase exploration (find files, search code)
            - "plan": Design implementation plans

    Returns:
        Sub-agent's response

    Examples:
        task("Find all files that handle user authentication", agent_type="explore")
        task("Design a plan to add dark mode support", agent_type="plan")
        task("What is the project structure?", agent_type="explore")
    """
    # Show task start
    short_prompt = prompt[:50] + "..." if len(prompt) > 50 else prompt
    text = Text()
    text.append("  ▶ ", style="blue")
    text.append(f"Task ({agent_type})", style="bold blue")
    text.append(f" {short_prompt}", style="dim")
    console.print(text)

    # Use SDK task function (doesn't need agent parameter for standalone use)
    # We pass None as agent since we're calling it directly, not as an agent tool
    result = sdk_task(None, prompt, agent_type)

    # Show task complete
    console.print(Text("  ◀ Task completed", style="blue"))

    return result
