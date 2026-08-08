"""
LLM-Note: Skills loader with multi-source discovery and YAML frontmatter parsing.

This module discovers and loads skill files from multiple search paths, parsing
YAML frontmatter to extract metadata and populating the global registry.

Key components:
- SkillInfo: Dataclass holding skill metadata (name, description, path)
- SKILLS_REGISTRY: Global dict mapping skill names to SkillInfo instances
- discover_skills(): Multi-path discovery (.co/skills, ~/.co/skills, builtin/)
- parse_skill_frontmatter(): Extracts YAML metadata from SKILL.md files
- load_skills(): Populates SKILLS_REGISTRY from discovered skills
- get_skill(): Retrieves skill by name from registry
- get_skills_for_prompt(): Formats skills as XML for system prompt injection

Architecture:
- Three search paths (priority: project > user > builtin)
- Supports SKILL.md in subdirs (skill-name/SKILL.md) or standalone .md files
- YAML frontmatter format: name, description fields
- Fallback: Uses directory/file name if no frontmatter name
- Fallback: Extracts first paragraph as description if missing
- Global registry mutated (not reassigned) to preserve references

Search tiers:
    1. .co/skills/skill-name/SKILL.md (project-level, highest priority)
    2. ~/.co/skills/skill-name/SKILL.md (user-level)
    3. customer defaults (native builtin plus an explicit useful_skills allowlist)

Usage:
    skills = load_skills()
    skill_info = get_skill("commit")
    content = skill_info.load_content()
    xml = get_skills_for_prompt()  # For system prompt
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional, List
from dataclasses import dataclass
from ....project import project_co_dir
from ....skills_catalog import default_skill_files


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


def parse_skill_frontmatter(content: str) -> Dict[str, Any]:
    """Parse YAML frontmatter from SKILL.md content.

    Defers to the parser the skills plugin uses, because SKILL.md is one format
    and two readers of it disagreed. This one used to split each line on the
    first colon, which accepted frontmatter YAML rejects (an unquoted colon in a
    description) and mangled what YAML handles (`tools: [a, b]` came back as the
    string "[a, b]"). Whether a skill worked depended on which entry point
    loaded it.

    A file whose frontmatter does not parse now reads as empty here too, and the
    fallbacks below take over — `co doctor` names the file and the line (#629),
    which is what makes converging on the stricter reader safe.
    """
    from ....useful_plugins.skills import _parse_skill_content

    frontmatter, _ = _parse_skill_content(content)
    return frontmatter


def discover_skills(base_path: Optional[Path] = None) -> List[SkillInfo]:
    """
    Discover all skills in .co/skills/ directory.

    Skills can be:
    - .co/skills/skill-name/SKILL.md (directory with SKILL.md)
    - .co/skills/skill-name.md (single file)
    - ~/.co/skills/ (user-level skills)
    - Customer-facing default skills shipped with ConnectOnion

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
        search_paths.append(project_co_dir() / "skills")

    # User-level skills
    home_skills = Path.home() / ".co" / "skills"
    if home_skills.exists():
        search_paths.append(home_skills)

    # search_paths is in priority order, so the FIRST match for a name wins and
    # later tiers are skipped. Dropping the duplicate here, rather than letting a
    # later one overwrite it, is what makes the documented precedence real: the
    # registry is built with `{s.name: s for s in skills}`, and last-write-wins
    # hands every contested name to builtin, which is appended last.
    seen = set()

    for skills_dir in search_paths:
        if not skills_dir.exists():
            continue

        # Find SKILL.md in subdirectories
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skill_info = _read_skill_or_skip(skill_file)
                    if skill_info and skill_info.name not in seen:
                        seen.add(skill_info.name)
                        skills.append(skill_info)

            # Also support single .md files
            elif skill_dir.suffix == ".md" and skill_dir.stem != "SKILL":
                skill_info = _read_skill_or_skip(skill_dir)
                if skill_info and skill_info.name not in seen:
                    seen.add(skill_info.name)
                    skills.append(skill_info)

    # Defaults are lowest priority. Some live in useful_skills so the installed
    # library and ``co ai`` share one body instead of drifting copies.
    for skill_file in default_skill_files():
        skill_info = _read_skill_or_skip(skill_file)
        if skill_info and skill_info.name not in seen:
            seen.add(skill_info.name)
            skills.append(skill_info)

    return skills


def _read_skill_or_skip(path: Path) -> Optional[SkillInfo]:
    """Parse one skill, or report it and move on.

    This loop runs inside create_agent(), before the CLI is usable, so an
    exception escaping here is not "that skill failed to load" — it is "co ai
    does not start", with nothing said about which of the user's skills caused
    it. One file saved as Windows-1252, or a compiled asset copied in by
    accident, is enough.

    The failure is named rather than swallowed: skipping silently trades a crash
    for a mystery, where the agent behaves differently and nothing points at the
    cause.
    """
    try:
        return _parse_skill_file(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"Skipping unreadable skill {path}: {type(exc).__name__}: {exc}")
        return None


def _parse_skill_file(path: Path) -> Optional[SkillInfo]:
    """Parse a SKILL.md file and extract metadata."""
    content = path.read_text(encoding="utf-8")
    frontmatter = parse_skill_frontmatter(content)

    # YAML types its values, and these two are labels for humans: the registry is
    # keyed by name and the description goes into a prompt. `name: no` is a bool
    # in YAML — `no`, `on`, `yes` and `off` all are — and a skill keyed by False
    # cannot be looked up by any name a user can type. Structured values like
    # `tools:` keep their real type; that is what the YAML reader is for.
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    if name is not None and not isinstance(name, str):
        name = str(name)
    if description is not None and not isinstance(description, str):
        description = str(description)

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
