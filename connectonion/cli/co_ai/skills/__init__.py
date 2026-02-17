"""
LLM-Note: Skills system for OO coding assistant with auto-discovery and injection.

This module provides a skills system where markdown files teach the agent how to
perform specific tasks, with auto-detection based on description matching.

Key components:
- load_skills(): Discovers and loads all SKILL.md files from .co/skills/
- get_skill(): Retrieves a specific skill by name
- get_skills_for_prompt(): Finds skills matching user request for prompt injection
- skill: Tool that executes a named skill by injecting its instructions
- SKILLS_REGISTRY: Global dictionary of loaded skills {name: skill_data}

Architecture:
- Skills stored in .co/skills/{skill-name}/SKILL.md with YAML frontmatter
- YAML frontmatter contains: name (identifier), description (for auto-detection)
- Auto-discovery scans all subdirectories for SKILL.md files at startup
- Skills injected via <system-reminder> tags when description matches user request
- Tool integration allows explicit skill execution via skill(name="commit")

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

Usage:
    from connectonion.cli.co_ai.skills import load_skills, skill

    load_skills(".co/skills")
    agent = Agent("coder", tools=[skill])
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
