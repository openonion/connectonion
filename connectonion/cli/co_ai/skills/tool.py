"""Skill tool - allows agent to invoke skills."""

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
