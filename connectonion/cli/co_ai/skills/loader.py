"""Skills loader - discovers and loads skills from .co/skills/ directory."""

import re
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass


@dataclass
class SkillInfo:
    """Metadata about a skill."""
    name: str
    description: str
    path: Path

    def load_content(self) -> str:
        """Load the full SKILL.md content."""
        return self.path.read_text(encoding="utf-8")


# Global registry of discovered skills
SKILLS_REGISTRY: Dict[str, SkillInfo] = {}


def parse_skill_frontmatter(content: str) -> Dict[str, str]:
    """Parse YAML frontmatter from SKILL.md content."""
    # Match --- ... --- at start of file
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return {}

    frontmatter = {}
    for line in match.group(1).split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            frontmatter[key.strip()] = value.strip()

    return frontmatter


def discover_skills(base_path: Optional[Path] = None) -> List[SkillInfo]:
    """
    Discover all skills in .co/skills/ directory.

    Skills can be:
    - .co/skills/skill-name/SKILL.md (directory with SKILL.md)
    - .co/skills/skill-name.md (single file)
    - ~/.co/skills/ (user-level skills)
    - Built-in skills from co_ai/skills/builtin/

    Returns:
        List of SkillInfo objects
    """
    skills = []

    # Search paths (in priority order)
    search_paths = []

    # Project-level skills (highest priority)
    if base_path:
        search_paths.append(base_path / ".co" / "skills")
    else:
        search_paths.append(Path.cwd() / ".co" / "skills")

    # User-level skills
    home_skills = Path.home() / ".co" / "skills"
    if home_skills.exists():
        search_paths.append(home_skills)

    # Built-in skills (lowest priority)
    builtin_skills = Path(__file__).parent / "builtin"
    if builtin_skills.exists():
        search_paths.append(builtin_skills)

    for skills_dir in search_paths:
        if not skills_dir.exists():
            continue

        # Find SKILL.md in subdirectories
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skill_info = _parse_skill_file(skill_file)
                    if skill_info:
                        skills.append(skill_info)

            # Also support single .md files
            elif skill_dir.suffix == ".md" and skill_dir.stem != "SKILL":
                skill_info = _parse_skill_file(skill_dir)
                if skill_info:
                    skills.append(skill_info)

    return skills


def _parse_skill_file(path: Path) -> Optional[SkillInfo]:
    """Parse a SKILL.md file and extract metadata."""
    content = path.read_text(encoding="utf-8")
    frontmatter = parse_skill_frontmatter(content)

    name = frontmatter.get("name")
    description = frontmatter.get("description")

    # If no name, use directory/file name
    if not name:
        if path.name == "SKILL.md":
            name = path.parent.name
        else:
            name = path.stem

    # If no description, try to extract from first paragraph
    if not description:
        # Remove frontmatter and find first paragraph
        content_without_frontmatter = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)
        lines = content_without_frontmatter.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                description = line[:200]  # First 200 chars
                break

    if not description:
        description = f"Skill: {name}"

    return SkillInfo(name=name, description=description, path=path)


def load_skills(base_path: Optional[Path] = None) -> Dict[str, SkillInfo]:
    """
    Load all skills and populate the registry.

    Returns:
        Dictionary of skill name -> SkillInfo
    """
    skills = discover_skills(base_path)

    # Mutate rather than reassign to keep references in sync
    SKILLS_REGISTRY.clear()
    SKILLS_REGISTRY.update({s.name: s for s in skills})

    return SKILLS_REGISTRY


def get_skill(name: str) -> Optional[SkillInfo]:
    """Get a skill by name from the registry."""
    return SKILLS_REGISTRY.get(name)


def get_skills_for_prompt() -> str:
    """
    Format skills for inclusion in system prompt.

    Returns XML-formatted available skills list.
    """
    if not SKILLS_REGISTRY:
        return ""

    lines = ["<available_skills>"]
    for name, info in SKILLS_REGISTRY.items():
        # Escape description for XML
        desc = info.description.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f'  <skill name="{name}" description="{desc}"/>')
    lines.append("</available_skills>")

    return "\n".join(lines)
