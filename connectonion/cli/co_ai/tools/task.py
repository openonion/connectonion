"""Task tool for delegating to sub-agents."""

from typing import Literal

from rich.console import Console
from rich.text import Text

from connectonion.cli.co_ai.agents.registry import get_subagent, SUBAGENTS

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
    if agent_type not in SUBAGENTS:
        available = ", ".join(SUBAGENTS.keys())
        return f"Error: Unknown agent type '{agent_type}'. Available: {available}"

    subagent = get_subagent(agent_type)
    if subagent is None:
        return f"Error: Failed to create {agent_type} agent"

    # Show task start
    short_prompt = prompt[:50] + "..." if len(prompt) > 50 else prompt
    text = Text()
    text.append("  ▶ ", style="blue")
    text.append(f"Task ({agent_type})", style="bold blue")
    text.append(f" {short_prompt}", style="dim")
    console.print(text)

    result = subagent.input(prompt)

    # Show task complete
    console.print(Text("  ◀ Task completed", style="blue"))

    return result
