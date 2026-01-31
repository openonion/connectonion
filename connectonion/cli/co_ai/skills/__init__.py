"""Skills system for OO agent.

Skills are markdown files that teach the agent how to do specific tasks.
They are auto-discovered based on description matching.

Directory structure:
    .co/skills/
    ├── commit/
    │   └── SKILL.md
    └── review-pr/
        └── SKILL.md

SKILL.md format:
    ---
    name: skill-name
    description: When to use this skill (for auto-detection)
    ---

    # Instructions
    ...
"""

from connectonion.cli.co_ai.skills.loader import (
    load_skills,
    get_skill,
    get_skills_for_prompt,
    SKILLS_REGISTRY,
)
from connectonion.cli.co_ai.skills.tool import skill

__all__ = [
    "load_skills",
    "get_skill",
    "get_skills_for_prompt",
    "skill",
    "SKILLS_REGISTRY",
]
