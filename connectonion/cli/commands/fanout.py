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


def _report_kept(dst: Path, *, removing: bool = False) -> None:
    """Say which path was left alone, so the skip is not silent.

    Says file or directory from the path, not from a fixed string: the message
    read "not deleting a real directory" about a hand-written .mdc file.
    """
    what = "directory" if dst.is_dir() and not dst.is_symlink() else "file"
    why = (f"not deleting a {what} we did not write"
           if removing else
           f"not overwriting your own {what} with a subscription; "
           f"move or rename it to sync this skill")
    print(f"  kept your own {dst} — {why}")


# What this module stamps into every file it generates, so a re-sync can tell its
# own output from a rule the user wrote by hand. Symlink paths need no marker —
# being a symlink we made is already the evidence — but cursor and kiro write
# real files, and "who wrote this" is not otherwise knowable.
OURS_MARKER = "connectonion:subscription"


def _may_write(dst: Path) -> bool:
    """Whether we may write `dst`: absent, or a file we generated before.

    install_cursor and install_kiro write files rather than symlink, so the
    _replace guard did not cover them: a hand-written
    ~/.cursor/rules/<alias>-<name>.mdc or ~/.kiro/steering/<alias>-<name>.md was
    overwritten with the publisher's content. Measured before this — both lost
    their contents on a sync.
    """
    if not dst.exists():
        return True
    try:
        return OURS_MARKER in dst.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _replace(dst: Path, src: Path) -> bool:
    """Point `dst` at `src`. False, without touching anything, if dst is not ours.

    This used to `shutil.rmtree(dst)` any real directory in the way. Replacing a
    symlink this module made is right — that is what a re-sync is — but a real
    directory is the user's, and it went with everything in it. Measured:

        ~/.codex/skills/mapper-candidate-mapping/
            SKILL.md   hand-written
            notes.md   hand-written
        co sub sync 0x…   ->  the path became a symlink, notes.md was gone

    The `{alias}-{name}` prefix makes that unlikely, not impossible: an alias is
    a string the publisher picked, so two publishers can pick the same one, and a
    subscriber may have named their own skills the same way.

    Losing a synced skill is recoverable by syncing again. Losing the notes
    underneath it is not, so the directory wins and the caller reports it.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        dst.unlink()          # ours, or stale — either way replaceable
    elif dst.exists():
        if dst.is_dir():
            return False      # somebody's real directory; not ours to delete
        dst.unlink()          # a plain file we wrote before
    dst.symlink_to(src)
    return True


def install_claude(bundle: Path, alias: str) -> int:
    """Link the bundle as one Claude plugin; report how many skills it carries.

    This returned a constant 1 — the number of plugins installed, under a
    heading that reads `installed N skill(s)`. Subscribing to an agent that
    announced a skill without publishing it printed:

        mirrored 0 skill(s) → ~/.co/subs/naturewill-mapping
        claude: installed 1 skill(s)          <- there were none

    The link is right and stays; every other tool in this module counts skills,
    so the number is what was out of step.
    """
    dst = HOME / ".claude" / "plugins" / alias
    if not _replace(dst, bundle):
        _report_kept(dst)
        return 0
    return _skill_count(bundle)


def _skills_in(bundle: Path):
    """The skill directories in a bundle — a dir holding a SKILL.md.

    One definition, so a count cannot disagree with what gets installed. That is
    how `claude: installed 1 skill(s)` came to be printed for a bundle with none.
    """
    root = bundle / "skills"
    if not root.is_dir():
        return []
    return [d for d in sorted(root.iterdir())
            if d.is_dir() and (d / "SKILL.md").exists()]


def _skill_count(bundle: Path) -> int:
    return len(_skills_in(bundle))


def install_skill_dirs(bundle: Path, alias: str, tool: str) -> int:
    n = 0
    for skill in _skills_in(bundle):
        dst = HOME / f".{tool}" / "skills" / f"{alias}-{skill.name}"
        if not _replace(dst, skill):
            _report_kept(dst)
            continue
        n += 1
    return n


def install_cursor(bundle: Path, alias: str) -> int:
    rules = HOME / ".cursor" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    n = 0
    # Same traversal as everywhere else; the extra filter below is cursor's own,
    # because a .mdc rule needs a description out of the frontmatter and a skill
    # without one has nothing to write. So this count is legitimately lower than
    # the others, which is why the filter stays here rather than moving into
    # _skills_in.
    for skill in _skills_in(bundle):
        md = skill / "SKILL.md"
        m = FRONTMATTER_RE.match(md.read_text(encoding="utf-8"))
        if not m:
            continue
        fm, body = m.groups()
        desc = next(
            (l.split(":", 1)[1].strip() for l in fm.splitlines() if l.startswith("description:")),
            "",
        )
        dst = rules / f"{alias}-{skill.name}.mdc"
        if not _may_write(dst):
            _report_kept(dst)
            continue
        # The marker goes in the body, not the frontmatter. Inside the header it
        # survives only because YAML treats `#` as a comment — our string in
        # someone else's block, working on a bet about how Cursor parses it.
        dst.write_text(
            f"---\ndescription: {desc}\nalwaysApply: false\n---\n"
            f"<!-- {OURS_MARKER} -->\n{body}",
            encoding="utf-8",
        )
        n += 1
    return n


def install_kiro(bundle: Path, alias: str) -> int:
    steering = HOME / ".kiro" / "steering"
    steering.mkdir(parents=True, exist_ok=True)
    n = 0
    for md in sorted((bundle / "skills").glob("*/SKILL.md")):
        dst = steering / f"{alias}-{md.parent.name}.md"
        if not _may_write(dst):
            _report_kept(dst)
            continue
        # Copy with the marker prepended as a comment, so a re-sync recognises
        # its own output; shutil.copy would leave nothing to recognise.
        dst.write_text(f"<!-- {OURS_MARKER} -->\n"
                       + md.read_text(encoding="utf-8"), encoding="utf-8")
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
    # Only what this module creates: symlinks (claude/codex/openclaw) and the
    # files it writes (cursor .mdc, kiro .md). A real directory matching the name
    # prefix is the user's — the install refuses to overwrite one, and removing a
    # subscription must not delete it either. Matching by prefix is a guess about
    # ownership; being a symlink we made is not.
    for t in targets:
        if t.is_symlink():
            t.unlink()            # a link we made
        elif t.is_file():
            # A file with our marker is ours; one without it is the user's, and
            # the name prefix alone is a guess about who wrote it.
            if _may_write(t):
                t.unlink()
            else:
                _report_kept(t, removing=True)
        elif t.is_dir():
            _report_kept(t, removing=True)
