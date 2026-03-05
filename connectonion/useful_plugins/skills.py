"""
Purpose: Skills plugin - Pre-packaged workflows with scoped permissions
LLM-Note:
  Dependencies: imports from [core/events.py, core/llm_do.py] | imported by [useful_plugins/__init__.py] | tested by [tests/unit/test_skills.py]
  Data flow: @after_user_input intercepts /command → loads SKILL.md → sets permission_scope → @on_complete clears scope
  State/Effects: stores permission_scope in session (turn-specific) | replaces user message with skill instructions
  Integration: works with tool_approval plugin for permission matching | uses yaml frontmatter parsing
  Errors: raises FileNotFoundError if skill not found

Skills Plugin - Invoke pre-packaged workflows with scoped permissions.

Skills are markdown files with YAML frontmatter that define:
1. Tool permissions (auto-approved during skill execution)
2. Instructions for the agent to follow

Invocation:
- /command: Instant invocation (no LLM overhead)
- skill() tool: LLM can choose to invoke

Permission Scope:
- Set when skill invoked (tied to turn number)
- Auto-clears when turn ends (security)
- Only affects current turn (no permission escalation)

Discovery:
Skills are discovered from three locations (priority order):
1. .co/skills/skill-name/SKILL.md    (project-level, highest priority)
2. ~/.co/skills/skill-name/SKILL.md  (user-level)
3. builtin/skill-name/SKILL.md       (built-in, lowest priority)

SKILL.md Format:
```yaml
---
name: commit
description: Create git commits
tools:
  - Bash(git status)
  - Bash(git diff *)
  - read_file
---

Create a git commit with a good message.

1. Check status: `git status`
2. Review changes: `git diff --staged`
3. Commit with good message
```

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import skills, tool_approval

    agent = Agent("assistant", tools=[bash, read_file], plugins=[skills, tool_approval])

    # User types: /commit
    # → Skills plugin loads commit skill
    # → Sets permission_scope with allowed git commands
    # → Agent executes with auto-approved tools
    # → Permission scope cleared after turn

Permission Patterns:
- Bash(git status) - Exact match only
- Bash(git diff *) - Wildcard: git diff --staged, git diff HEAD
- Bash(git *) - All git commands
- read_file - Tool name only (any args)
"""

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict, Any, List
from copy import deepcopy

from ..core.events import after_user_input, on_complete, before_each_tool

if TYPE_CHECKING:
    from ..core.agent import Agent


# =============================================================================
# SKILL DISCOVERY
# =============================================================================

def _get_skill_paths(skill_name: str) -> List[Path]:
    """Get potential paths for a skill in priority order.

    Priority:
    1. .co/skills/skill-name/SKILL.md (project-level)
    2. ~/.co/skills/skill-name/SKILL.md (user-level)
    3. builtin skills (bundled with ConnectOnion)

    Args:
        skill_name: Skill name (e.g., "commit")

    Returns:
        List of Path objects in priority order
    """
    paths = []

    # 1. Project-level: .co/skills/skill-name/SKILL.md
    project_path = Path.cwd() / '.co' / 'skills' / skill_name / 'SKILL.md'
    paths.append(project_path)

    # 2. User-level: ~/.co/skills/skill-name/SKILL.md
    home = Path.home()
    user_path = home / '.co' / 'skills' / skill_name / 'SKILL.md'
    paths.append(user_path)

    # 3. Built-in: connectonion/cli/co_ai/skills/builtin/skill-name/SKILL.md
    # Find the builtin skills directory relative to this file
    builtin_base = Path(__file__).parent.parent / 'cli' / 'co_ai' / 'skills' / 'builtin'
    builtin_path = builtin_base / skill_name / 'SKILL.md'
    paths.append(builtin_path)

    return paths


def _load_skill(skill_name: str) -> Optional[Dict[str, Any]]:
    """Load skill from filesystem.

    Args:
        skill_name: Skill name (e.g., "commit")

    Returns:
        Dict with 'path', 'frontmatter', 'instructions' or None if not found
    """
    for path in _get_skill_paths(skill_name):
        if path.exists():
            content = path.read_text()
            frontmatter, instructions = _parse_skill_content(content)
            return {
                'path': str(path),
                'frontmatter': frontmatter,
                'instructions': instructions
            }

    return None


def _parse_skill_content(content: str) -> tuple[Dict[str, Any], str]:
    """Parse SKILL.md content into frontmatter and instructions.

    Args:
        content: Raw SKILL.md content

    Returns:
        (frontmatter_dict, instructions_text)
    """
    # Match YAML frontmatter: ---\n...\n---
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)

    if not match:
        # No frontmatter
        return {}, content.strip()

    yaml_text = match.group(1)
    instructions = match.group(2).strip()

    # Parse YAML frontmatter
    import yaml
    try:
        frontmatter = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return frontmatter, instructions


def _discover_all_skills() -> List[Dict[str, str]]:
    """Discover all available skills for system prompt.

    Returns:
        List of dicts with 'name', 'description', 'location'
    """
    skills = []
    seen_names = set()

    # Check all three locations for each potential skill
    # Priority: project > user > builtin
    for location, base_path in [
        ('project', Path.cwd() / '.co' / 'skills'),
        ('user', Path.home() / '.co' / 'skills'),
        ('builtin', Path(__file__).parent.parent / 'cli' / 'co_ai' / 'skills' / 'builtin')
    ]:
        if not base_path.exists():
            continue

        # Find all SKILL.md files
        for skill_dir in base_path.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / 'SKILL.md'
            if not skill_file.exists():
                continue

            skill_name = skill_dir.name

            # Skip if already seen (higher priority wins)
            if skill_name in seen_names:
                continue

            seen_names.add(skill_name)

            # Parse frontmatter for description
            content = skill_file.read_text()
            frontmatter, _ = _parse_skill_content(content)
            description = frontmatter.get('description', 'No description')

            skills.append({
                'name': skill_name,
                'description': description,
                'location': location
            })

    return skills


# =============================================================================
# UNIFIED PERMISSIONS WITH SNAPSHOT/RESTORE
# =============================================================================

def _grant_skill_permissions(agent: 'Agent', skill_name: str, patterns: List[str]) -> None:
    """Grant skill permissions using unified permission structure.

    Takes snapshot of current permissions before granting to preserve user approvals.
    Stores patterns directly in permissions dict - pattern matching happens at check time.

    Args:
        agent: Agent instance
        skill_name: Skill name for reason
        patterns: List of tool patterns (e.g., ["Bash(git *)", "read_file"])
    """
    # Take snapshot of current permissions to restore later
    current_perms = agent.current_session.get('permissions', {})
    agent.current_session['_permission_snapshot'] = deepcopy(current_perms)

    # Initialize permissions dict if needed
    if 'permissions' not in agent.current_session:
        agent.current_session['permissions'] = {}

    # Grant permissions for each pattern
    turn = agent.current_session.get('turn', 0)
    for pattern in patterns:
        # Store pattern itself as key in permissions dict
        agent.current_session['permissions'][pattern] = {
            'allowed': True,
            'source': 'skill',
            'reason': f'{skill_name} skill (turn {turn})',
            'expires': {'type': 'turn_end'}
        }


def _restore_permissions(agent: 'Agent') -> None:
    """Restore permissions snapshot after skill completes.

    This ensures user approvals are preserved and skill permissions are cleared.
    """
    if '_permission_snapshot' in agent.current_session:
        agent.current_session['permissions'] = agent.current_session.pop('_permission_snapshot')


def matches_permission_pattern(tool_name: str, tool_args: dict, patterns: List[str]) -> bool:
    """Check if tool call matches any allowed pattern.

    Pattern types:
    - "read_file" - Tool name only (matches any args)
    - "Bash(git status)" - Exact command match
    - "Bash(git diff *)" - Command with wildcard
    - "Bash(git *)" - All commands starting with "git"

    Args:
        tool_name: Tool name (e.g., "bash")
        tool_args: Tool arguments dict
        patterns: List of allowed patterns

    Returns:
        True if tool matches any pattern
    """
    for pattern in patterns:
        # Pattern: "tool_name" - matches tool name only
        if pattern == tool_name:
            return True

        # Pattern: "Bash(command pattern)" - matches bash commands
        if pattern.startswith('Bash(') and pattern.endswith(')'):
            if tool_name.lower() != 'bash':
                continue

            cmd_pattern = pattern[5:-1]  # Extract "git status" from "Bash(git status)"
            actual_cmd = tool_args.get('command', '')

            # Exact match: "git status" == "git status"
            if cmd_pattern == actual_cmd:
                return True

            # Wildcard match: "git diff *" matches "git diff --staged"
            if cmd_pattern.endswith(' *'):
                prefix = cmd_pattern[:-2]  # Remove " *"
                if actual_cmd.startswith(prefix):
                    return True

            # Wildcard match: "git *" matches "git status"
            if cmd_pattern == actual_cmd.split()[0] + ' *':
                return True

    return False


# =============================================================================
# SKILL INVOCATION
# =============================================================================

@after_user_input
def handle_skill_invocation(agent: 'Agent') -> None:
    """Detect /command and load skill with permission scope.

    Intercepts messages starting with / and loads corresponding skill.
    Sets permission_scope in session and replaces user message with skill instructions.
    """
    messages = agent.current_session.get('messages', [])
    if not messages:
        return

    last_msg = messages[-1]
    if last_msg.get('role') != 'user':
        return

    content = last_msg.get('content', '')
    if not content.startswith('/'):
        return

    # Extract skill name: "/commit arg1 arg2" → "commit"
    skill_name = content[1:].split()[0] if len(content) > 1 else ''
    if not skill_name:
        return

    # Load skill
    skill = _load_skill(skill_name)
    if not skill:
        # Skill not found - don't interfere
        return

    frontmatter = skill['frontmatter']
    instructions = skill['instructions']

    # Grant skill permissions (with snapshot)
    patterns = frontmatter.get('tools', [])
    _grant_skill_permissions(agent, skill_name, patterns)

    # Replace user message with skill instructions
    messages[-1]['content'] = instructions

    # Log skill invocation
    if hasattr(agent, 'logger') and agent.logger:
        agent.logger.print(f"[cyan]🎯 Skill: {skill_name}[/cyan]")


@on_complete
def cleanup_scope(agent: 'Agent') -> None:
    """Restore permissions snapshot after turn completes."""
    _restore_permissions(agent)


# =============================================================================
# SKILL TOOL (LLM can invoke skills)
# =============================================================================

def skill(agent: 'Agent', name: str) -> str:
    """Invoke a skill by name.

    LLM can call this tool to invoke skills autonomously.
    Grants skill permissions and returns skill instructions.

    Args:
        agent: Agent instance
        name: Skill name (e.g., "commit")

    Returns:
        Skill instructions for the agent to follow
    """
    skill_data = _load_skill(name)
    if not skill_data:
        available = _discover_all_skills()
        skill_list = "\n".join(f"- {s['name']}: {s['description']}" for s in available)
        return f"Skill '{name}' not found. Available skills:\n{skill_list}"

    frontmatter = skill_data['frontmatter']
    instructions = skill_data['instructions']

    # Grant skill permissions (with snapshot)
    patterns = frontmatter.get('tools', [])
    _grant_skill_permissions(agent, name, patterns)

    return instructions


# =============================================================================
# SYSTEM PROMPT INJECTION
# =============================================================================

def _inject_skills_to_system_prompt(agent: 'Agent') -> None:
    """Inject available skills into system prompt.

    Adds a section listing all discoverable skills so the LLM knows what's available.
    """
    skills_list = _discover_all_skills()
    if not skills_list:
        return

    # Build skills section
    skills_text = "\n\n# Available Skills\n\n"
    skills_text += "Pre-packaged workflows you can invoke:\n\n"

    for skill in skills_list:
        skills_text += f"- `/{skill['name']}`: {skill['description']}\n"

    skills_text += "\nUser can type `/skill-name` or you can call the skill() tool.\n"

    # Find system message and append
    messages = agent.current_session.get('messages', [])
    for msg in messages:
        if msg.get('role') == 'system':
            msg['content'] = msg['content'] + skills_text
            break


# Export as plugin (list of event handlers)
# Usage: Agent("name", plugins=[skills, tool_approval])
skills = [handle_skill_invocation, cleanup_scope]

# Export helper functions for tool_approval integration
__all__ = [
    'skills',
    'skill',
    'matches_permission_pattern',
]
