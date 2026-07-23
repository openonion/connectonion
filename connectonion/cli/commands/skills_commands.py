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
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.table import Table

console = Console()

CO_HOME = Path.home() / ".co"
SKILLS_DIR = CO_HOME / "skills"
INDEX_FILE = SKILLS_DIR / "index.json"
AGENT_JSON = CO_HOME / "agent.json"

# Sources mirror oo/lib/fanout.py — same agents, read direction.
# Each entry: (source_id, root_path, layout)
# layout: "skill-dir" → root/<name>/SKILL.md, "flat-md" → root/<name>.md, "mdc" → root/<name>.mdc
SOURCES = [
    ("co-project", Path.cwd() / ".co" / "skills", "skill-dir"),
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
    for source_id, root, layout in SOURCES:
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
        "sources": [src for src, _, _ in SOURCES],
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


SOURCE_PRIORITY = {src: i for i, (src, _, _) in enumerate(SOURCES)}


def _copy_entry(entry: dict, force: bool) -> bool:
    """Copy a single index entry into ~/.co/skills/<name>/. Returns True if copied."""
    name = entry["name"]
    src_path = Path(entry["path"])
    dest_dir = SKILLS_DIR / name
    dest_file = dest_dir / "SKILL.md"

    if src_path.resolve() == dest_file.resolve():
        console.print(f"[dim]Skipped {name} (already at destination from {entry['source']})[/dim]")
        return False

    if dest_file.exists() and not force:
        console.print(f"[yellow]Skipped: {name} (exists, use --force)[/yellow]")
        return False

    dest_dir.mkdir(parents=True, exist_ok=True)
    if src_path.name == "SKILL.md" and src_path.parent.is_dir():
        for item in src_path.parent.iterdir():
            target = dest_dir / item.name
            if item.is_dir():
                if target.exists() and force:
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
    else:
        shutil.copy2(src_path, dest_file)

    console.print(f"[green]✓ Copied {name} ({entry['source']}) → {dest_dir}[/green]")
    return True


def handle_skills_copy(
    names: List[str],
    source: Optional[str] = None,
    force: bool = False,
    all_: bool = False,
):
    """Copy one or more discovered skills into ~/.co/skills/<name>/."""
    index = _load_index()
    if not index:
        console.print("[yellow]No index found. Run `co skills discover` first.[/yellow]")
        return

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    by_name: dict = {}
    for s in index["skills"]:
        by_name.setdefault(s["name"], []).append(s)

    if all_:
        candidates = [s for s in index["skills"] if not source or s["source"] == source]
        # Dedupe by name using SOURCES priority order (co-project > co-user > claude > ...)
        chosen: dict = {}
        for s in candidates:
            existing = chosen.get(s["name"])
            if existing is None or SOURCE_PRIORITY[s["source"]] < SOURCE_PRIORITY[existing["source"]]:
                chosen[s["name"]] = s

        copied = skipped = 0
        for entry in chosen.values():
            if _copy_entry(entry, force):
                copied += 1
            else:
                skipped += 1
        console.print(f"\n[bold]Copied {copied} skill(s)[/bold]"
                      + (f", skipped {skipped}" if skipped else "")
                      + f" → {SKILLS_DIR}")
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
        _copy_entry(matches[0], force)


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
    """List skills currently materialized in ~/.co/skills/."""
    if not SKILLS_DIR.exists():
        console.print("[dim]~/.co/skills/ is empty.[/dim]")
        return
    rows = []
    for child in sorted(SKILLS_DIR.iterdir()):
        if not child.is_dir():
            continue
        skill_file = child / "SKILL.md"
        if not skill_file.exists():
            continue
        fm = parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="replace"))
        rows.append((fm.get("name") or child.name, fm.get("description") or ""))

    if not rows:
        console.print("[dim]No skills installed in ~/.co/skills/.[/dim]")
        return

    table = Table(title=f"~/.co/skills ({len(rows)})")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="dim", overflow="fold")
    for name, desc in rows:
        if len(desc) > 100:
            desc = desc[:97] + "..."
        table.add_row(name, desc)
    console.print(table)
