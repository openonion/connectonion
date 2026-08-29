"""
Purpose: Discover SKILL.md files across agent tool directories and copy them into ~/.co/skills/.

LLM-Note:
  Dependencies: imports from [json, re, shutil, datetime, pathlib, rich] | imported by [cli/main.py via handle_skills_*()]
  Data flow:
    discover: walk SOURCES roots → parse frontmatter → write ~/.co/skills/index.json
    copy:     read index.json → resolve entry by name → copy SKILL.md (and sibling files if dir) → ~/.co/skills/<name>/
    list:     enumerate ~/.co/skills/*/SKILL.md → print table
    manifest: scan ~/.co/skills/*/SKILL.md → merge {name, description, publish}[] into ~/.co/agent.json
  State/Effects: writes ~/.co/skills/index.json | creates ~/.co/skills/<name>/ directories | updates ~/.co/agent.json skills metadata
  Integration: SOURCES table mirrors oo/lib/fanout.py write-side; single source of truth on the read side.
"""

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.table import Table

from ...project import project_co_dir

console = Console()

CO_HOME = Path.home() / ".co"
SKILLS_DIR = CO_HOME / "skills"
INDEX_FILE = SKILLS_DIR / "index.json"
AGENT_JSON = CO_HOME / "agent.json"

def project_skills_dir() -> Path:
    """`.co/skills` in the project, wherever `co` was run from.

    Resolved per call. As a module-level constant this was `Path.cwd() / '.co'`
    evaluated at *import* time, so it named the directory the process started in
    and nothing could change it afterwards. `--to-project` then mkdir'd it,
    which plants a `.co/` that shadows the project's own for every later lookup.
    """
    return project_co_dir() / "skills"


# Sources mirror oo/lib/fanout.py — same agents, read direction.
# Each entry: (source_id, root_path, layout)
# layout: "skill-dir" → root/<name>/SKILL.md, "flat-md" → root/<name>.md, "mdc" → root/<name>.mdc
def sources() -> list:
    return [
        ("co-project", project_skills_dir(), "skill-dir"),
        ("co-user",    Path.home() / ".co" / "skills", "skill-dir"),
        ("claude",     Path.home() / ".claude" / "skills", "skill-dir"),
        ("codex",      Path.home() / ".codex" / "skills", "skill-dir"),
        ("cursor",     Path.home() / ".cursor" / "rules", "mdc"),
        ("kiro",       Path.home() / ".kiro" / "steering", "flat-md"),
    ]

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def scan_source(source_id: str, root: Path, layout: str) -> list:
    if not root.exists():
        return []
    found = []
    if layout == "skill-dir":
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if skill_file.exists():
                found.append(_entry(source_id, child.name, skill_file))
    else:
        suffix = ".mdc" if layout == "mdc" else ".md"
        for child in sorted(root.iterdir()):
            if child.is_file() and child.suffix == suffix:
                found.append(_entry(source_id, child.stem, child))
    return found


def _entry(source_id: str, fallback_name: str, path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter(text)
    name = fm.get("name") or fallback_name
    desc = fm.get("description") or ""
    if ":" in name:
        # plugin-namespaced — skip in caller, but tag for visibility
        pass
    return {
        "name": name,
        "description": desc,
        "source": source_id,
        "path": str(path),
    }


def handle_skills_discover(save: bool = True, json_out: bool = False, include_namespaced: bool = False):
    """Scan known agent skill roots and print/save an index."""
    all_skills: list = []
    for source_id, root, layout in sources():
        all_skills.extend(scan_source(source_id, root, layout))

    if not include_namespaced:
        all_skills = [s for s in all_skills if ":" not in s["name"]]

    # De-dupe by (name, source) keeping first occurrence
    seen = set()
    deduped = []
    for s in all_skills:
        key = (s["name"], s["source"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [src for src, _, _ in sources()],
        "skills": deduped,
    }

    if save:
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")

    if json_out:
        console.print_json(data=index)
        return

    table = Table(title=f"Discovered skills ({len(deduped)})")
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Description", style="dim", overflow="fold")
    for s in deduped:
        desc = s["description"]
        if len(desc) > 80:
            desc = desc[:77] + "..."
        table.add_row(s["name"], s["source"], desc)
    console.print(table)
    if save:
        console.print(f"[dim]Index written to {INDEX_FILE}[/dim]")


def _load_index() -> Optional[dict]:
    if not INDEX_FILE.exists():
        return None
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


def source_priority() -> dict:
    """Priority by source, in the order `sources()` lists them.

    A function, not a constant: as a constant it ran `sources()` at import
    time, which resolves the project directory — the very thing this module
    stopped doing at import time.
    """
    return {src: i for i, (src, _, _) in enumerate(sources())}


# What a skill must not carry with it. VERSIONING.md put it plainly when the
# command was introduced -- "skills carry their own files but never their
# secrets" -- and nothing implemented it: the copy took the directory whole,
# .env, credentials.json, keys/ and all.
#
# It matters most where the command points. `--to-project` puts the skill where
# `co deploy` will find it, and a deploy rsyncs the project tree to a server, so
# a credential a skill kept beside itself on a laptop lands on the box.
#
# Matched on the name, not the contents: guessing at contents gets both false
# positives and false negatives, and a name like `.env` or `id_rsa` is what
# people actually use. `.env.example` is deliberately not caught -- it is the
# file you commit.
SECRET_NAMES = {".env", ".netrc", ".npmrc", ".pypirc", "keys.env",
                "credentials.json", "service-account.json", "service_account.json",
                "token.json", "auth.json", "secrets.json", "secrets.yaml", "secrets.yml",
                ".git-credentials"}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")

# Whole directories that exist to hold credentials. Listed as directories on
# purpose: the first pass named `id_rsa` and `id_ed25519` and `.ssh/id_ecdsa`
# walked straight past, because guessing every key filename is the wrong shape
# of rule. Nothing inside one of these travels.
SECRET_DIRS = {".ssh", ".aws", ".gnupg", ".kube", ".docker", ".azure"}


def _is_secret(path: Path) -> bool:
    name = path.name
    if name in SECRET_DIRS:
        return True
    if name in SECRET_NAMES or name.endswith(SECRET_SUFFIXES):
        return True
    # An SSH private key is `id_<type>`; its `.pub` half is not a secret, and
    # nor is anything else that merely starts with those two letters.
    if name.startswith("id_") and not name.endswith(".pub"):
        return True
    # `.env.local`, `.env.production` -- but not `.env.example`
    return name.startswith(".env.") and not name.endswith((".example", ".sample", ".template"))


def _copy_entry(entry: dict, force: bool, skills_dir: Optional[Path] = None) -> bool:
    """Copy a single index entry into <skills_dir>/<name>/. Returns True if copied."""
    name = entry["name"]
    src_path = Path(entry["path"])
    from ...skill_preflight import format_preflight_report, preflight_skills
    from ...skill_requirements import parse_skill_requirements
    from ...useful_plugins.skills import _parse_skill_content

    frontmatter, _ = _parse_skill_content(src_path.read_text(encoding="utf-8"))
    manifest_name = str(frontmatter.get("name") or name)
    requirements = parse_skill_requirements(frontmatter, manifest_name)
    dest_dir = (skills_dir or SKILLS_DIR) / name
    dest_file = dest_dir / "SKILL.md"

    if src_path.resolve() == dest_file.resolve():
        console.print(f"[dim]Skipped {name} (already at destination from {entry['source']})[/dim]")
        return False

    if dest_file.exists() and not force:
        console.print(f"[yellow]Skipped: {name} (exists, use --force)[/yellow]")
        return False

    dest_dir.mkdir(parents=True, exist_ok=True)
    left_behind = []
    if src_path.name == "SKILL.md" and src_path.parent.is_dir():
        def skip_secrets(directory, names):
            # copytree's ignore hook, so a credential nested in a subdirectory is
            # left behind too -- keys/id_rsa was the one that made this obvious.
            dropped = [n for n in names if _is_secret(Path(directory) / n)]
            left_behind.extend(str(Path(directory).joinpath(n)) for n in dropped)
            return set(dropped)

        for item in src_path.parent.iterdir():
            target = dest_dir / item.name
            if _is_secret(item):
                left_behind.append(str(item))
                continue
            if item.is_dir():
                if target.exists() and force:
                    shutil.rmtree(target)
                shutil.copytree(item, target, ignore=skip_secrets)
            else:
                shutil.copy2(item, target)
    else:
        shutil.copy2(src_path, dest_file)

    # A directory whose whole contents were secrets arrives empty, which reads as
    # "the keys came along". Remove it rather than leave that impression.
    for directory in sorted((d for d in dest_dir.rglob("*") if d.is_dir()),
                            key=lambda d: len(d.parts), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()

    # Said out loud: a skill that really did keep something here would otherwise
    # lose it without a word, and finding that out later is worse.
    for path in left_behind:
        console.print(f"[yellow]  skipped {Path(path).name} (a secret stays where it is)[/yellow]")

    console.print(f"[green]✓ Copied {name} ({entry['source']}) → {dest_dir}[/green]")
    report = format_preflight_report(preflight_skills([(manifest_name, requirements)]))
    if report:
        console.print(report)
    return True


def handle_skills_copy(
    names: List[str],
    source: Optional[str] = None,
    force: bool = False,
    all_: bool = False,
    to_project: bool = False,
):
    """Copy one or more discovered skills into a skills directory.

    Which directory is the whole question. ~/.co/skills is the operator's
    library and does not travel — `co skills list` marks it `Deploys ✗`. Only
    the project's .co/skills reaches a server, which is what every deploy tells
    you ("move one into .co/skills/ to ship it") and what no command did.
    """
    index = _load_index()
    if not index:
        console.print("[yellow]No index found. Run `co skills discover` first.[/yellow]")
        return

    skills_dir = project_skills_dir() if to_project else SKILLS_DIR
    skills_dir.mkdir(parents=True, exist_ok=True)

    by_name: dict = {}
    for s in index["skills"]:
        by_name.setdefault(s["name"], []).append(s)

    if all_:
        candidates = [s for s in index["skills"] if not source or s["source"] == source]
        # Dedupe by name using source priority order (co-project > co-user > claude > ...)
        priority = source_priority()
        chosen: dict = {}
        for s in candidates:
            existing = chosen.get(s["name"])
            if existing is None or priority[s["source"]] < priority[existing["source"]]:
                chosen[s["name"]] = s

        copied = skipped = 0
        for entry in chosen.values():
            if _copy_entry(entry, force, skills_dir):
                copied += 1
            else:
                skipped += 1
        console.print(f"\n[bold]Copied {copied} skill(s)[/bold]"
                      + (f", skipped {skipped}" if skipped else "")
                      + f" → {skills_dir}")
        return

    if not names:
        console.print("[yellow]No skill names given. Use `co skills copy <name>` or `--all`.[/yellow]")
        return

    for name in names:
        matches = by_name.get(name, [])
        if source:
            matches = [m for m in matches if m["source"] == source]
        if not matches:
            console.print(f"[red]Not found: {name}[/red]")
            continue
        if len(matches) > 1 and not source:
            sources = ", ".join(m["source"] for m in matches)
            console.print(f"[yellow]{name} exists in: {sources}. Use --source to pick one.[/yellow]")
            continue
        _copy_entry(matches[0], force, skills_dir)


def handle_skills_manifest(
    path: Optional[str] = None,
    out: Optional[str] = None,
    stdout: bool = False,
):
    """Build skill metadata from a skills directory.

    Default: scans ~/.co/skills/ and merges into ~/.co/agent.json.
    --path overrides what to scan. --out overrides where to write.
    --out agent.json merges into its skills[] key (and strips signature).
    --stdout prints JSON instead of writing.
    """
    skills_root = Path(path) if path else SKILLS_DIR
    if not skills_root.exists() or not skills_root.is_dir():
        console.print(f"[red]Not a directory: {skills_root}[/red]")
        raise SystemExit(1)

    manifest = []
    for child in sorted(skills_root.iterdir()):
        if not child.is_dir():
            continue
        skill_file = child / "SKILL.md"
        if not skill_file.exists():
            continue
        fm = parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="replace"))
        name = fm.get("name") or child.name
        desc = fm.get("description") or ""
        if not desc:
            console.print(f"[yellow]Warning: {name} has no description[/yellow]")
        manifest.append({"name": name, "description": desc, "publish": False})

    if stdout:
        console.print_json(data=manifest)
        return

    out_path = Path(out) if out else AGENT_JSON
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.name == "agent.json":
        if not out_path.exists():
            console.print(f"[red]Not found: {out_path}. Run `co setup` first or pass --out to write standalone JSON.[/red]")
            raise SystemExit(1)
        profile = json.loads(out_path.read_text(encoding="utf-8"))
        existing_by_name = {
            s.get("name"): s
            for s in profile.get("skills", [])
            if isinstance(s, dict) and s.get("name")
        }
        for skill in manifest:
            existing = existing_by_name.get(skill["name"])
            if existing and "publish" in existing:
                skill["publish"] = bool(existing["publish"])
        profile["skills"] = manifest
        profile.pop("signature", None)
        profile.pop("signer", None)
        out_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        console.print(f"[green]✓ Merged {len(manifest)} skill(s) into {out_path}[/green]")
        console.print("[dim]Note: removed prior signature — re-sign before publishing.[/dim]")
    else:
        out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        console.print(f"[green]✓ Wrote {len(manifest)} skill(s) → {out_path}[/green]")


def handle_skills_list():
    """List every skill the agent can see, and say which of them travel.

    Used to list only ~/.co/skills/, which is the one tier that does NOT survive a
    deploy — so the command showing you your skills was showing you exactly the ones
    the deployed agent would not have.
    """
    from ...useful_plugins.skills import (
        TRAVELS_ON_DEPLOY,
        _discover_all_skills,
        find_skill_problems,
    )

    skills = _discover_all_skills()
    problems = find_skill_problems()

    if not skills:
        console.print("[dim]No skills found.[/dim]")
    else:
        table = Table(title=f"Skills ({len(skills)})")
        table.add_column("Name", style="cyan")
        table.add_column("Where", style="magenta")
        table.add_column("Deploys", justify="center")
        table.add_column("Description", style="dim", overflow="fold")
        for skill in skills:
            travels = skill.location in TRAVELS_ON_DEPLOY
            desc = skill.description or ""
            if len(desc) > 80:
                desc = desc[:77] + "..."
            table.add_row(
                skill.name,
                skill.location,
                "[green]✓[/green]" if travels else "[yellow]✗[/yellow]",
                desc,
            )
        console.print(table)

        staying = [s for s in skills if s.location not in TRAVELS_ON_DEPLOY]
        if staying:
            console.print(
                f"\n[yellow]{len(staying)} skill(s) stay on this machine.[/yellow] "
                "[dim]Move one into .co/skills/ to make it travel.[/dim]"
            )

    if problems:
        console.print(f"\n[red]{len(problems)} broken link(s):[/red]")
        for location, name, reason in problems:
            console.print(f"  [dim]{location}[/dim]  {name} — {reason}")


# Write direction: publish the skills bundled with ConnectOnion into the
# agent tools that read them. SOURCES above is the read side; these are the
# two targets that use the same <name>/SKILL.md layout.
LINK_TARGETS = [
    ("claude", Path.home() / ".claude" / "skills"),
    ("codex", Path.home() / ".codex" / "skills"),
]

BUNDLED_SKILLS = Path(__file__).parent.parent.parent / "useful_skills"


def _link_one(source: Path, target: Path, force: bool) -> str:
    """Point target at source. Returns a one-word status for the report."""
    if target.is_symlink():
        if target.resolve() == source.resolve() and not force:
            return "already linked"
        target.unlink()
    elif target.exists():
        if not force:
            # A real directory here is the user's own skill of the same name.
            # Silently replacing it would delete work we did not create.
            return "exists, not ours — skipped"
        shutil.rmtree(target)

    target.parent.mkdir(parents=True, exist_ok=True)

    # Windows only allows symlinks under Developer Mode or elevation, so fall
    # back to a copy there rather than failing. The cost is that a copy goes
    # stale on upgrade and has to be re-linked.
    if os.name == "nt":
        shutil.copytree(source, target)
        return "copied"

    target.symlink_to(source, target_is_directory=True)
    return "linked"


def handle_skills_link(force: bool = False):
    """Link the bundled ConnectOnion skills into ~/.claude/skills and ~/.codex/skills."""
    skills = sorted(d for d in BUNDLED_SKILLS.iterdir() if d.is_dir() and (d / "SKILL.md").exists())
    if not skills:
        console.print("[dim]No bundled skills found.[/dim]")
        return

    table = Table(title=f"Linking {len(skills)} bundled skill(s)")
    table.add_column("Skill", style="cyan")
    for name, _ in LINK_TARGETS:
        table.add_column(name)

    for skill in skills:
        row = [skill.name]
        for _, root in LINK_TARGETS:
            row.append(_link_one(skill, root / skill.name, force))
        table.add_row(*row)

    console.print()
    console.print(table)
    console.print(
        "\n[dim]Skipped entries are directories you own — pass [/dim]"
        "[bold]--force[/bold][dim] to replace them.[/dim]\n"
    )
