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
3. customer default skill             (bundled, lowest priority)

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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Dict, Any, List
from copy import deepcopy

from ..core.events import after_user_input, on_complete, before_each_tool, on_agent_ready
from ..project import project_co_dir, project_root
from ..skill_requirements import (
    SkillManifestError,
    SkillRequirements,
    parse_skill_requirements,
)
from ..skills_catalog import (
    DEFAULT_LIBRARY_SKILLS,
    builtin_skills_dir,
    default_skill_path,
    useful_skills_dir,
)

if TYPE_CHECKING:
    from ..core.agent import Agent


@dataclass
class SkillInfo:
    name: str
    description: str
    location: str  # project | claude-project | user | claude-user | builtin
    path: Optional[Path] = None
    requirements: Optional[SkillRequirements] = None


# The only locations a hosted agent publishes to clients: the two that ship inside
# the project tree. user (~/.co/skills) and claude-user are the operator's personal
# toolboxes and builtin is framework noise — none may leak into the public directory.
# An allowlist, so an unknown future category stays private by default.
#
# Anything a client is expected to *invoke* must be drawn from this same set: a
# client validates skill names against the published profile and refuses the rest,
# so offering a skill outside it produces a button that can never run.
PUBLISHED_SKILL_LOCATIONS = ("project", "claude-project")

# The locations that survive a deploy. Both packaging paths carry the project tree
# and nothing outside it, so a skill in ~/.co/skills or ~/.claude/skills is simply
# absent on the server — those two are the operator's laptop, not the agent.
#
# builtin is here and NOT in PUBLISHED_SKILL_LOCATIONS: it ships inside the installed
# connectonion package, so a deployed agent has it, but it is framework noise nobody
# should see in a public directory. That divergence is why these are two constants
# and not one — travelling and being publishable are different questions.
TRAVELS_ON_DEPLOY = ("project", "claude-project", "builtin")


# =============================================================================
# SKILL DISCOVERY
# =============================================================================

def _get_skill_paths(skill_name: str) -> List[Path]:
    """Get potential paths for a skill in priority order.

    Priority:
    1. .co/skills/skill-name/SKILL.md (project-level)
    2. ~/.co/skills/skill-name/SKILL.md (user-level)
    3. customer-facing default skills (bundled with ConnectOnion)

    Args:
        skill_name: Skill name (e.g., "commit")

    Returns:
        List of Path objects in priority order
    """
    paths = []
    home = Path.home()

    # 1. Project-level ConnectOnion: .co/skills/skill-name/SKILL.md
    paths.append(project_co_dir() / 'skills' / skill_name / 'SKILL.md')

    # 2. Project-level Claude Code: .claude/skills/skill-name/SKILL.md
    paths.append(project_root() / '.claude' / 'skills' / skill_name / 'SKILL.md')

    # 3. User-level ConnectOnion: ~/.co/skills/skill-name/SKILL.md
    paths.append(home / '.co' / 'skills' / skill_name / 'SKILL.md')

    # 4. User-level Claude Code: ~/.claude/skills/skill-name/SKILL.md
    paths.append(home / '.claude' / 'skills' / skill_name / 'SKILL.md')

    # 5. Customer-facing defaults. Library-backed defaults resolve to their
    # canonical useful_skills body rather than a copied builtin.
    default = default_skill_path(skill_name)
    if default:
        paths.append(default)

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
            content = path.read_text(encoding="utf-8")
            frontmatter, instructions = _parse_skill_content(content)
            manifest_name = frontmatter.get('name') or skill_name
            requirements = parse_skill_requirements(frontmatter, str(manifest_name))
            return {
                'path': str(path),
                'frontmatter': frontmatter,
                'instructions': instructions,
                'requirements': requirements,
            }

    return None


# ---\n<yaml>\n---\n<instructions>.  Shared with the reader that diagnoses a
# SKILL.md, so "what doctor checks" cannot drift from "what loading accepts".
_FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)


def _parse_skill_content(content: str) -> tuple[Dict[str, Any], str]:
    """Parse SKILL.md content into frontmatter and instructions.

    Args:
        content: Raw SKILL.md content

    Returns:
        (frontmatter_dict, instructions_text)
    """
    match = _FRONTMATTER_RE.match(content)

    if not match:
        # No frontmatter
        return {}, content.strip()

    yaml_text = match.group(1)
    instructions = match.group(2).strip()

    return _read_frontmatter(yaml_text), instructions


# The only keys worth rescuing from a frontmatter YAML refuses to parse.
#
# Deliberately not `tools:`. test_one_reader_for_skill_frontmatter records why
# the strict reader won: "neither invents a reading of a file that has a syntax
# error in it", and `tools:` is fed to _grant_skill_permissions — guessing it
# from a file that does not parse would widen an agent's permissions on the
# strength of a line split. These two only decide whether the model is told the
# skill exists and what it is for.
_RECOVERABLE_KEYS = ('name', 'description')


def _read_frontmatter(yaml_text: str) -> Dict[str, Any]:
    """Frontmatter as YAML; if YAML refuses, rescue the name and description.

    This returned `{}` on a YAMLError, which was chosen on purpose — the strict
    reader replaced a line splitter, and `co doctor` was taught to name the file
    and line so that the skills which stop being read are reported loudly.

    What that left is still a silent failure at the only moment that matters.
    The description is what the model is given to decide whether a skill
    applies, so an empty frontmatter means the skill is listed with nothing
    about when to use it, and is never chosen. Nothing at load time says so; you
    have to think to run `co doctor`.

    And the shape is not rare. An unquoted colon inside a value is invalid YAML
    and is what people write:

        description: Orchestrate a workflow from a Markdown draft: prepare a
                     cover, draft the article...

    Eight skills installed on the machine this was found on were unreadable for
    that reason, every one authored by Claude Code, which loads them all.

    So YAML stays the authority — a valid file keeps its lists and nested
    values, and anything with consequences comes from YAML or not at all — and a
    file it rejects gives up only its `tools:`, not its identity. `co doctor`
    goes on reporting the file, because it should still be fixed.
    """
    import yaml

    try:
        return yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        pass

    recovered = {}
    for line in yaml_text.splitlines():
        if line.startswith((' ', '\t')) or ':' not in line:
            continue
        key, value = line.split(':', 1)
        if key.strip() in _RECOVERABLE_KEYS:
            recovered[key.strip()] = value.strip().strip('"').strip("'")
    return recovered


def _skill_search_paths(co_dir: Optional[Path] = None,
                        project_dir: Optional[Path] = None) -> List[tuple]:
    """Skill sources as ``(location, directory, optional allowlist)`` triples.

    One definition, so discovery and any diagnosis of it look in the same places —
    a second copy would eventually report on directories the loader no longer reads.
    """
    # The project, not the directory this was called from. #663 gave the
    # loader (`_get_skill_paths`) the walk-up and left this one on the bare cwd,
    # so from a subdirectory a project skill was still loadable by name and no
    # longer *listed* -- and a skill the model is never told about is a skill
    # that does not work. Measured with `co ai` in a project one level down: the
    # skill answered at the root and was invisible in `sub/`.
    base = project_dir or (co_dir.parent if co_dir else project_root())
    co_base = co_dir or (base / '.co')
    return [
        ('project', co_base / 'skills', None),
        ('claude-project', base / '.claude' / 'skills', None),
        ('user', Path.home() / '.co' / 'skills', None),
        ('claude-user', Path.home() / '.claude' / 'skills', None),
        ('builtin', builtin_skills_dir(), None),
        ('builtin', useful_skills_dir(), frozenset(DEFAULT_LIBRARY_SKILLS)),
    ]


def _discover_all_skills(co_dir: Optional[Path] = None, project_dir: Optional[Path] = None) -> List['SkillInfo']:
    """Discover all available skills from ConnectOnion and Claude Code directories.

    Args:
        co_dir: Path to .co directory (defaults to cwd/.co)
        project_dir: Project root (defaults to co_dir.parent or cwd)

    Returns:
        List of SkillInfo with 'name', 'description', 'location'
    """
    seen = set()
    result = []

    for location, skills_dir, allowed_names in _skill_search_paths(co_dir, project_dir):
        if not skills_dir.exists():
            continue

        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            if allowed_names is not None and skill_dir.name not in allowed_names:
                continue

            skill_file = skill_dir / 'SKILL.md'
            if not skill_file.exists():
                continue

            name = skill_dir.name
            if name in seen:
                continue

            # Named and skipped rather than allowed to escape. This runs during
            # agent construction, so one file saved as Windows-1252 — or a
            # compiled asset copied in by accident — would otherwise stop the
            # agent from being created at all, saying nothing about which of the
            # user's skills did it.
            try:
                content = skill_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"Skipping unreadable skill {skill_file}: {type(exc).__name__}: {exc}")
                continue

            seen.add(name)

            frontmatter, _ = _parse_skill_content(content)
            description = frontmatter.get('description', 'No description')
            try:
                requirements = parse_skill_requirements(frontmatter, name)
            except SkillManifestError:
                requirements = None  # find_skill_problems reports the exact field

            result.append(SkillInfo(
                name=name, description=description, location=location,
                path=skill_file, requirements=requirements,
            ))

    return result


def find_skill_problems(co_dir: Optional[Path] = None,
                        project_dir: Optional[Path] = None) -> List[tuple]:
    """Entries that look like skills but can never load. Returns (location, name, reason).

    Discovery is deliberately forgiving — it skips anything without a readable
    SKILL.md and says nothing. That is right for loading and wrong for diagnosing:
    most of our own skills are symlinks into a separate repo, so a dangling link
    looks exactly like "no skill here" and the agent quietly behaves differently.

    Reported, not raised: a broken link is a thing to tell the operator about, not
    a reason to refuse to run.
    """
    problems = []

    for location, skills_dir, allowed_names in _skill_search_paths(co_dir, project_dir):
        if not skills_dir.exists():
            continue

        for entry in skills_dir.iterdir():
            if entry.name.startswith('.'):
                continue
            if allowed_names is not None and entry.name not in allowed_names:
                continue

            if entry.is_symlink():
                # exists() follows the link, so False here means the target is gone.
                if not entry.exists():
                    problems.append((location, entry.name, 'broken symlink'))
                    continue

                resolved = entry.resolve()
                if resolved == skills_dir.resolve() or resolved in skills_dir.resolve().parents:
                    problems.append((location, entry.name, 'symlink points at its own ancestor'))
                    continue

                if entry.is_dir() and not (entry / 'SKILL.md').exists():
                    problems.append((location, entry.name, 'linked directory has no SKILL.md'))
                    continue

            # A plain directory without a SKILL.md is not a broken skill — people
            # keep notes, scratch dirs and shared assets in here, and nothing there
            # claims otherwise. A SKILL.md is the claim, and like a symlink it can
            # be false: loading swallows a YAML error and carries on with an empty
            # frontmatter, so the skill reaches the model with no description and
            # no `tools:` patterns, looking like it works.
            if entry.is_dir() and (entry / 'SKILL.md').exists():
                reason = _why_the_skill_cannot_be_read(entry / 'SKILL.md')
                if reason:
                    problems.append((location, entry.name, reason))

    return problems


def _why_the_skill_cannot_be_read(skill_md: Path) -> Optional[str]:
    """The reason a SKILL.md cannot be loaded, or None if it is fine.

    Only unambiguous breakage. A file with no frontmatter at all is a legitimate
    way to write a simple skill — the whole file is the instructions — and
    reporting a working skill is worse than the silence this fixes.
    """
    content = skill_md.read_text(errors='replace')

    if not content.strip():
        return 'SKILL.md is empty'

    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None

    import yaml
    yaml_text = match.group(1)
    try:
        yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        detail = str(e).split('\n')[0]
        mark = getattr(e, 'problem_mark', None)
        # The mark counts lines within the frontmatter, 0-based. Add one for the
        # opening `---` and one for counting from 1, so the number is the line an
        # editor puts the cursor on.
        where = f' at line {mark.line + 2}' if mark is not None else ''

        # Say what it costs, which is no longer "everything". _read_frontmatter
        # rescues name and description from a file YAML rejects, so these skills
        # work — reporting them as unreadable teaches people to stop reading the
        # doctor. What is genuinely lost is `tools:`, which is not rescued because
        # it grants permissions, so a file that declares one is the real problem:
        # the declaration does nothing and the author cannot tell.
        recovered = _read_frontmatter(yaml_text)
        # `tools:` only. `allowed-tools:` is another tool's key and _tool_patterns
        # never reads it, so it is ignored whether or not the YAML parses —
        # blaming the bad quoting for that would be a false claim, and most of
        # these files declare allowed-tools rather than tools.
        declares_tools = any(
            line.split(':', 1)[0].strip() == 'tools'
            for line in yaml_text.splitlines()
            if ':' in line and not line.startswith((' ', '\t'))
        )
        if declares_tools:
            return (f'SKILL.md frontmatter is not valid YAML{where}: {detail} '
                    f'— its tools: declaration is being ignored')
        if recovered.get('description'):
            return (f'SKILL.md frontmatter is not valid YAML{where}: {detail} '
                    f'— name and description were still read')
        return f'SKILL.md frontmatter is not valid YAML{where}: {detail}'

    frontmatter = _read_frontmatter(yaml_text)
    skill_name = frontmatter.get('name') or skill_md.parent.name
    try:
        parse_skill_requirements(frontmatter, str(skill_name))
    except SkillManifestError as exc:
        return str(exc)

    return None


def skills_that_will_not_travel(co_dir: Optional[Path] = None,
                                project_dir: Optional[Path] = None) -> List[SkillInfo]:
    """Discovered skills that exist only on this machine.

    A user-tier skill works perfectly for months and is simply absent the moment the
    agent runs anywhere else — deployed, in CI, on a teammate's checkout. Naming them
    before the deploy is the whole point: afterwards the agent just behaves differently
    for a reason nothing in the output explains.
    """
    return [s for s in _discover_all_skills(co_dir, project_dir)
            if s.location not in TRAVELS_ON_DEPLOY]


# =============================================================================
# UNIFIED PERMISSIONS WITH SNAPSHOT/RESTORE
# =============================================================================

def _tool_patterns(frontmatter: dict) -> list:
    """The `tools:` declaration as a list of patterns.

    YAML gives a string for `tools: read_file` and a list for `tools: [a, b]`.
    The caller does `for pattern in patterns`, so the scalar form walked the
    characters and registered `r`, `e`, `a`, `d`... as permission patterns.
    Nothing was granted that should not have been -- no single character matches
    a tool name -- but the author's declaration did nothing at all.
    """
    declared = frontmatter.get('tools')
    if declared is None:
        # No key at all, or `tools:` with nothing after it -- a null in YAML,
        # which the caller's `for pattern in patterns` used to trip over. That
        # runs when the skill is invoked, so it took the user's turn with it.
        return []
    if isinstance(declared, str):
        return [declared]
    return list(declared)


def _grant_skill_permissions(agent: 'Agent', skill_name: str, patterns: List[str]) -> None:
    """Grant skill permissions using unified permission structure with 'when' field.

    Takes snapshot of current permissions before granting to preserve user approvals.
    Keeps Bash(X) as the key (no collapse across multiple patterns) and adds 'when'
    for runtime fnmatch command matching and future extra-param extensibility.

    Args:
        agent: Agent instance
        skill_name: Skill name for reason
        patterns: List of tool patterns (e.g., ["Bash(git *)", "read_file"])
    """
    # Where this turn began — written once, by whichever skill runs first.
    #
    # A second skill in the same turn used to overwrite this with a state that
    # already contained the first one's grants, so restore returned to "after
    # skill A" and A's patterns were permanent for the rest of the session.
    # Skills reference other skills; two in a turn is ordinary.
    #
    # A stack would be the answer if restore ran per skill. It does not —
    # cleanup_scope is @on_complete and fires once, at the end of the turn — so
    # the only snapshot worth having is the first.
    # It also records which turn it describes. `on_complete` is not in a finally
    # block, so a turn that raises — a rejected approval does exactly that —
    # never restores and leaves its snapshot behind. Trusting that one would
    # send the next turn back two turns.
    turn_now = agent.current_session.get('turn', 0)
    snapshot = agent.current_session.get('_permission_snapshot')
    if snapshot is None or snapshot.get('turn') != turn_now:
        current_perms = agent.current_session.get('permissions', {})
        agent.current_session['_permission_snapshot'] = {
            'turn': turn_now, 'permissions': deepcopy(current_perms),
        }

    # Initialize permissions dict if needed
    if 'permissions' not in agent.current_session:
        agent.current_session['permissions'] = {}

    turn = agent.current_session.get('turn', 0)
    for pattern in patterns:
        if pattern.startswith('Bash(') and pattern.endswith(')'):
            # Keep Bash(X) as key — no collapse when multiple patterns present.
            # Add 'when' for runtime fnmatch check against full command.
            command_pattern = pattern[5:-1]
            permission = {
                'allowed': True,
                'source': 'skill',
                'reason': f'{skill_name} skill (turn {turn})',
                'when': {'command': command_pattern},
                'expires': {'type': 'turn_end'}
            }
            agent.current_session['permissions'][pattern] = permission
        else:
            permission = {
                'allowed': True,
                'source': 'skill',
                'reason': f'{skill_name} skill (turn {turn})',
                'expires': {'type': 'turn_end'}
            }
            agent.current_session['permissions'][pattern] = permission


def _restore_permissions(agent: 'Agent') -> None:
    """Restore permissions snapshot after skill completes.

    This ensures user approvals are preserved and skill permissions are cleared.
    """
    if '_permission_snapshot' not in agent.current_session:
        return

    restored = agent.current_session.pop('_permission_snapshot')['permissions']

    # An approval the operator gave *during* the skill is theirs, not the
    # skill's. It lives only in the live dict — the snapshot predates it — so a
    # wholesale replace threw it away: they answered a dialog with "trust this
    # for the session" and it silently did not stick.
    for key, permission in (agent.current_session.get('permissions') or {}).items():
        if permission.get('source') == 'user':
            restored[key] = permission

    agent.current_session['permissions'] = restored


# =============================================================================
# SKILL INVOCATION
# =============================================================================

@on_agent_ready
def setup_skills(agent: 'Agent') -> None:
    """Populate agent.skills on startup."""
    co_dir = getattr(agent, 'co_dir', None)
    agent.skills = _discover_all_skills(co_dir=co_dir)


def _close_out_a_turn_that_never_finished(agent: 'Agent') -> None:
    """Undo a skill's grants when the turn that made them died before restoring.

    `cleanup_scope` is @on_complete, and on_complete is a plain statement after
    the loop in Agent.input -- no finally. A turn that raises never reaches it,
    and the grant stays:

        turn 1, during        ['Bash(rm -rf *)', 'write']
          ... the turn raises
        turn 2, at the start  ['Bash(rm -rf *)', 'write']

    The permission record even carries expires={'type': 'turn_end'}; nothing was
    enforcing it. The ordinary way to get here is the operator answering "no" to
    an approval, which raises -- so a refusal left the skill's permissions alive
    for the rest of the session.

    A snapshot tagged with an earlier turn is exactly the evidence that its
    restore never ran, so this runs at the start of every turn rather than
    wrapping the turn in try/finally: on_complete keeps meaning "the turn
    finished", which the logger and the eval writer both read it as.
    """
    snapshot = agent.current_session.get('_permission_snapshot')
    if not snapshot:
        return
    if snapshot.get('turn') == agent.current_session.get('turn', 0):
        return          # this turn's own scope, still running
    _restore_permissions(agent)


@after_user_input
def handle_skill_invocation(agent: 'Agent') -> None:
    """Detect /command and load skill with permission scope.

    Intercepts messages starting with / and loads corresponding skill.
    Sets permission_scope in session and replaces user message with skill instructions.
    """
    _close_out_a_turn_that_never_finished(agent)

    messages = agent.current_session.get('messages', [])
    if not messages:
        return

    last_msg = messages[-1]
    if last_msg.get('role') != 'user':
        return

    content = last_msg.get('content', '')
    if not content.startswith('/'):
        return

    # Extract skill name and arguments: "/commit arg1 arg2" → ("commit", "arg1 arg2")
    parts = content[1:].split(maxsplit=1) if len(content) > 1 else []
    skill_name = parts[0] if parts else ''
    skill_args = parts[1].strip() if len(parts) > 1 else ''
    if not skill_name:
        return

    # Load skill
    skill = _load_skill(skill_name)
    if not skill:
        # Skill not found - don't interfere
        return

    frontmatter = skill['frontmatter']
    instructions = skill['instructions']

    from ..skill_preflight import format_preflight_report, preflight_skills

    preflight = preflight_skills([(skill_name, skill.get('requirements'))])
    if preflight.missing_required:
        messages[-1]['content'] = format_preflight_report(preflight) + "\nSkill did not start."
        return

    # Grant skill permissions (with snapshot)
    patterns = _tool_patterns(frontmatter)
    _grant_skill_permissions(agent, skill_name, patterns)

    # Replace user message with skill instructions, preserving slash-command args.
    if skill_args:
        instructions = f"{instructions}\n\n---\n## Arguments\n{skill_args}"
    messages[-1]['content'] = instructions

    if agent.logger.console:
        description = frontmatter.get('description', '')
        agent.logger.console.print_skill_invocation(skill_name, description)


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
        co_dir = getattr(agent, 'co_dir', None)
        available = _discover_all_skills(co_dir=co_dir)
        skill_list = "\n".join(f"- {s.name}: {s.description}" for s in available)
        return f"Skill '{name}' not found. Available skills:\n{skill_list}"

    frontmatter = skill_data['frontmatter']
    instructions = skill_data['instructions']

    from ..skill_preflight import format_preflight_report, preflight_skills

    preflight = preflight_skills([(name, skill_data.get('requirements'))])
    if preflight.missing_required:
        return format_preflight_report(preflight) + "\nSkill did not start."

    # Grant skill permissions (with snapshot)
    patterns = _tool_patterns(frontmatter)
    _grant_skill_permissions(agent, name, patterns)

    return instructions


# =============================================================================
# SYSTEM PROMPT INJECTION
# =============================================================================

def _inject_skills_to_system_prompt(agent: 'Agent') -> None:
    """Inject available skills into system prompt.

    Adds a section listing all discoverable skills so the LLM knows what's available.
    """
    co_dir = getattr(agent, 'co_dir', None)
    skills_list = _discover_all_skills(co_dir=co_dir)
    if not skills_list:
        return

    # Project skills first: with dozens installed, the one that lives in this
    # repository is the one meant to win when several could apply, and order is
    # a signal the model reads.
    priority = {loc: i for i, loc in enumerate(
        ("project", "claude-project", "user", "claude-user", "builtin"))}
    skills_list = sorted(skills_list, key=lambda s: priority.get(s.location, 99))

    # An instruction, not a description of a capability. This used to end with
    # "you can call the skill() tool", and the agent did not — asked in a
    # skill's own trigger words it ran glob, then glob again, then `find`,
    # hunting for a file it could never see, because skills live under dot
    # directories.
    skills_text = "\n\n# Available Skills\n\n"
    skills_text += (
        "Pre-packaged workflows. When a request matches a skill's description, "
        "**your first action is `skill(name=...)`** to load its full "
        "instructions — before planning, and before touching any files.\n\n"
        "Do not use glob/grep/find to locate a skill. They live under dot "
        "directories and file search will not find them; the list below is the "
        "whole set.\n\n"
    )

    for skill in skills_list:
        skills_text += f"- `/{skill.name}` ({skill.location}): {skill.description}\n"

    skills_text += "\nA user can also type `/skill-name` directly.\n"

    # Find system message and append
    messages = agent.current_session.get('messages', [])
    for msg in messages:
        if msg.get('role') == 'system':
            msg['content'] = msg['content'] + skills_text
            break


# Export as plugin (list of event handlers)
# Usage: Agent("name", plugins=[skills, tool_approval])
skills = [setup_skills, handle_skill_invocation, cleanup_scope]

# Export helper functions for tool_approval integration
__all__ = [
    'skills',
    'skill',
    'SkillInfo',
    'matches_permission_pattern',
]
