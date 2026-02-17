"""
LLM-Note: Skill tool for runtime skill invocation by agents.

This module provides the skill() tool that allows agents to dynamically load
skill instructions at runtime based on task recognition.

Key components:
- skill(): Tool function that loads and returns full SKILL.md content by name
- Auto-loading: Ensures SKILLS_REGISTRY is populated before lookup
- Error handling: Returns available skills list if requested skill not found
- Argument support: Optional args parameter appended to skill content

Architecture:
- Tool callable by LLM agents via tool_calls
- Lazy registry initialization (loads on first call if empty)
- Returns full SKILL.md markdown content for agent instruction
- Arguments appended as ## Arguments section if provided
- Integrates with loader.py's SKILLS_REGISTRY global state

Workflow:
    1. Agent recognizes task matches skill description from system prompt
    2. Agent calls skill(name="commit") via tool_calls
    3. Tool ensures SKILLS_REGISTRY loaded (calls load_skills() if empty)
    4. Tool retrieves SkillInfo from registry via get_skill()
    5. Tool loads full SKILL.md content via skill_info.load_content()
    6. Returns markdown content to agent for instruction following

Usage:
    # Agent sees <skill name="commit" description="Create commits"/> in prompt
    # Agent recognizes task matches description
    # Agent invokes:
    result = skill("commit")  # Returns full SKILL.md content
"""

from typing import Optional
from connectonion.cli.co_ai.skills.loader import get_skill, load_skills, SKILLS_REGISTRY


def skill(name: str, args: Optional[str] = None) -> str:
    """
    Invoke a skill by name.

    Skills are specialized instruction sets that guide you through specific tasks.
    When you recognize a task matches a skill's description, call this tool to
    load the full instructions.

    Args:
        name: The skill name (e.g., "commit", "review-pr")
        args: Optional arguments to pass to the skill

    Returns:
        The full skill instructions (SKILL.md content)

    Example:
        skill("commit")  # Load commit instructions
        skill("review-pr", args="123")  # Load PR review with PR number
    """
    # Ensure skills are loaded
    if not SKILLS_REGISTRY:
        load_skills()

    skill_info = get_skill(name)

    if not skill_info:
        available = list(SKILLS_REGISTRY.keys())
        if available:
            return f"Skill '{name}' not found. Available skills: {', '.join(available)}"
        else:
            return f"Skill '{name}' not found. No skills are currently loaded."

    # Load the full skill content
    content = skill_info.load_content()

    # If args provided, append them
    if args:
        content += f"\n\n---\n## Arguments\n{args}"

    return content
