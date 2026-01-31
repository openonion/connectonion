"""Sub-agent registry and factory."""

from typing import Dict, Any, Optional
from connectonion import Agent

from connectonion.cli.co_ai.tools import glob, grep, read_file


# Sub-agent configurations
SUBAGENTS: Dict[str, Dict[str, Any]] = {
    "explore": {
        "description": "Fast agent for exploring codebases. Find files, search code, answer questions about structure.",
        "tools": [glob, grep, read_file],
        "model": "co/gemini-2.5-flash",  # Fast model for exploration
        "max_iterations": 15,
    },
    "plan": {
        "description": "Design implementation plans. Analyze architecture, identify files to change, plan steps.",
        "tools": [glob, grep, read_file],
        "model": "co/gemini-2.5-pro",  # Smarter model for planning
        "max_iterations": 10,
    },
}


def get_subagent(agent_type: str) -> Optional[Agent]:
    """
    Create a sub-agent instance by type.

    Args:
        agent_type: Type of sub-agent ("explore", "plan", etc.)

    Returns:
        Configured Agent instance or None if type not found
    """
    if agent_type not in SUBAGENTS:
        return None

    config = SUBAGENTS[agent_type]

    # Load prompt from co_ai/prompts/agents/
    from pathlib import Path
    prompt_path = Path(__file__).parent.parent / "prompts" / "agents" / f"{agent_type}.md"

    if prompt_path.exists():
        system_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = f"You are an {agent_type} agent. {config['description']}"

    return Agent(
        name=f"oo-{agent_type}",
        tools=config["tools"],
        plugins=[],
        system_prompt=system_prompt,
        model=config["model"],
        max_iterations=config["max_iterations"],
    )
