"""
Purpose: Per-tool fan-out — materialize one canonical bundle into every detected coding agent (Claude, Codex, OpenClaw, Cursor, Kiro).
LLM-Note:
  Dependencies: imports from [re, shutil, pathlib] | imported by [cli/commands/sub_commands.py for subscription install] | tested by [tests/unit/test_fanout.py]
  Data flow: receives bundle: Path (layout `<root>/skills/<name>/SKILL.md`) + alias: str → walks bundle/skills/* → for each detected tool (~/.claude, ~/.codex, ~/.openclaw, ~/.cursor, ~/.kiro), materializes in that tool's expected shape → returns {tool: skill_count}. Cursor needs frontmatter rewritten to `.mdc` (alwaysApply: false). Kiro wants plain `.md` copies. Claude/Codex/OpenClaw get symlinks.
  State/Effects: creates symlinks under ~/.<tool>/ | mkdir -p for missing target dirs | rm + relink on idempotent re-runs (_replace clears existing dir/symlink/file before linking) | no network, no logs
  Integration: exposes detected_tools(), install_claude(), install_skill_dirs(bundle, alias, tool), install_cursor(), install_kiro(), install_all(bundle, alias) -> {tool: int}, uninstall_all(alias) | HOME module attribute is monkeypatched by tests to redirect away from real ~/
  Performance: O(skills × tools) filesystem ops | no I/O beyond symlink/copy/write | typical bundle (20 skills) installs in <50ms
  Errors: lets OSError bubble (permission denied, broken symlink targets); FRONTMATTER_RE.match returns None for cursor → skill silently skipped (intentional — non-frontmatter bodies aren't valid cursor rules)

Per-tool layout produced:
  install_claude(bundle, alias)              ~/.claude/plugins/<alias>/        (symlink to bundle)
  install_skill_dirs(bundle, alias, tool)    ~/.<tool>/skills/<alias>-<skill>/ (per-skill symlinks)
  install_cursor(bundle, alias)              ~/.cursor/rules/<alias>-<skill>.mdc (file, frontmatter rewritten)
  install_kiro(bundle, alias)                ~/.kiro/steering/<alias>-<skill>.md  (plain copy)
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

HOME = Path.home()
TOOLS = ("claude", "codex", "openclaw", "cursor", "kiro")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def detected_tools() -> list[str]:
    return [t for t in TOOLS if (HOME / f".{t}").is_dir()]


def _replace(dst: Path, src: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    dst.symlink_to(src)


def install_claude(bundle: Path, alias: str) -> int:
    _replace(HOME / ".claude" / "plugins" / alias, bundle)
    return 1


def install_skill_dirs(bundle: Path, alias: str, tool: str) -> int:
    n = 0
    for skill in sorted((bundle / "skills").iterdir()):
        if not skill.is_dir() or not (skill / "SKILL.md").exists():
            continue
        _replace(HOME / f".{tool}" / "skills" / f"{alias}-{skill.name}", skill)
        n += 1
    return n


def install_cursor(bundle: Path, alias: str) -> int:
    rules = HOME / ".cursor" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    n = 0
    for skill in sorted((bundle / "skills").iterdir()):
        md = skill / "SKILL.md"
        if not md.exists():
            continue
        m = FRONTMATTER_RE.match(md.read_text())
        if not m:
            continue
        fm, body = m.groups()
        desc = next(
            (l.split(":", 1)[1].strip() for l in fm.splitlines() if l.startswith("description:")),
            "",
        )
        (rules / f"{alias}-{skill.name}.mdc").write_text(
            f"---\ndescription: {desc}\nalwaysApply: false\n---\n{body}"
        )
        n += 1
    return n


def install_kiro(bundle: Path, alias: str) -> int:
    steering = HOME / ".kiro" / "steering"
    steering.mkdir(parents=True, exist_ok=True)
    n = 0
    for md in sorted((bundle / "skills").glob("*/SKILL.md")):
        shutil.copy(md, steering / f"{alias}-{md.parent.name}.md")
        n += 1
    return n


def install_all(bundle: Path, alias: str) -> dict[str, int]:
    """Install into every detected tool. Returns {tool: skill_count}."""
    handlers = {
        "claude":   lambda: install_claude(bundle, alias),
        "codex":    lambda: install_skill_dirs(bundle, alias, "codex"),
        "openclaw": lambda: install_skill_dirs(bundle, alias, "openclaw"),
        "cursor":   lambda: install_cursor(bundle, alias),
        "kiro":     lambda: install_kiro(bundle, alias),
    }
    return {tool: handlers[tool]() for tool in detected_tools()}


def uninstall_all(alias: str) -> None:
    """Remove every per-tool install for `alias`."""
    targets: list[Path] = [HOME / ".claude" / "plugins" / alias]
    for tool in ("codex", "openclaw"):
        skills_dir = HOME / f".{tool}" / "skills"
        if skills_dir.is_dir():
            targets += [p for p in skills_dir.iterdir() if p.name.startswith(f"{alias}-")]
    for base in (HOME / ".cursor" / "rules", HOME / ".kiro" / "steering"):
        if base.is_dir():
            targets += [p for p in base.iterdir() if p.name.startswith(f"{alias}-")]
    for t in targets:
        if t.is_symlink() or t.is_file():
            t.unlink()
        elif t.is_dir():
            shutil.rmtree(t)
