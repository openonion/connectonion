"""Context loading for project awareness."""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from connectonion.cli.co_ai.skills.loader import load_skills, get_skills_for_prompt


def load_project_context(base_path: Optional[Path] = None) -> str:
    """
    Load project context from various sources.

    Reading priority:
    1. .co/OO.md   - OO-specific instructions (our brand)
    2. CLAUDE.md   - Compatibility with Claude Code
    3. README.md   - Project understanding
    4. Git status  - Current branch and changes
    5. Environment - Working directory, date

    Args:
        base_path: Base directory to look for context files (default: cwd)

    Returns:
        Assembled context string for system prompt
    """
    base = base_path or Path.cwd()
    parts = []

    # 1. Load .co/OO.md (our brand, primary)
    oo_md = base / ".co" / "OO.md"
    if oo_md.exists():
        content = oo_md.read_text(encoding="utf-8")
        parts.append(f"# Project Instructions (OO.md)\n\n{content}")

    # 2. Load CLAUDE.md (compatibility)
    claude_md = base / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8")
        if oo_md.exists():
            parts.append(f"# Additional Instructions (CLAUDE.md)\n\n{content}")
        else:
            parts.append(f"# Project Instructions (CLAUDE.md)\n\n{content}")

    # 3. Load README.md (project understanding)
    readme_md = base / "README.md"
    if readme_md.exists():
        content = readme_md.read_text(encoding="utf-8")
        # Truncate if too long (README can be verbose)
        if len(content) > 5000:
            content = content[:5000] + "\n\n... (truncated)"
        parts.append(f"# Project Overview (README.md)\n\n{content}")

    # 4. Load skills (descriptions only)
    load_skills(base)
    skills_prompt = get_skills_for_prompt()
    if skills_prompt:
        parts.append(f"# Available Skills\n\n{skills_prompt}")

    # 5. Git status
    git_info = _get_git_info(base)
    if git_info:
        parts.append(git_info)

    # 6. Environment info
    env_info = f"""# Environment

Working Directory: {base}
Date: {datetime.now().strftime("%Y-%m-%d")}
"""
    parts.append(env_info)

    return "\n\n---\n\n".join(parts)


def _get_git_info(base: Path) -> Optional[str]:
    """Get git status information."""
    git_dir = base / ".git"
    if not git_dir.exists():
        return None

    try:
        # Get current branch
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=base,
            timeout=5,
        )
        branch_name = branch.stdout.strip() if branch.returncode == 0 else "unknown"

        # Get status
        status = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            cwd=base,
            timeout=5,
        )
        status_output = status.stdout.strip() if status.returncode == 0 else ""

        # Get recent commits (last 3)
        log = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            capture_output=True,
            text=True,
            cwd=base,
            timeout=5,
        )
        log_output = log.stdout.strip() if log.returncode == 0 else ""

        result = f"# Git Status\n\nBranch: {branch_name}"

        if status_output:
            result += f"\n\nChanges:\n```\n{status_output}\n```"
        else:
            result += "\n\nNo uncommitted changes."

        if log_output:
            result += f"\n\nRecent commits:\n```\n{log_output}\n```"

        return result

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
