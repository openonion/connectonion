"""Inventory installed skill metadata and seed inert Wiki pages, without a model."""

import hashlib
import os
import re
from pathlib import Path

from .files import Notebook, maintenance_lock


def scan_skills(directories: list[Path] | None = None) -> dict:
    """Read immediate skill entries; preserve distinct sources with the same name.

    Explicit directories replace defaults, so a caller can inventory another
    project's skills without depending on the runner's temporary working directory.
    No skill body is executed and no recursive traversal of home/plugin caches occurs.
    """
    from ..cli.co_ai.skills.loader import parse_skill_frontmatter
    from ..project import project_root
    from ..useful_plugins.skills import _skill_search_paths

    if directories is not None:
        roots = [("explicit", p, None) for p in directories]
    else:
        base = project_root()
        roots = list(_skill_search_paths(project_dir=base))
        roots += [("agent-project", base / ".agents/skills", None),
                  ("codex-project", base / ".codex/skills", None),
                  ("agent-user", Path.home() / ".agents/skills", None),
                  ("codex-user", Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills", None)]
    found, coverage, errors = {}, [], []
    for location, directory, allowed in roots:
        directory = Path(directory).expanduser().resolve()
        info = {"path": str(directory), "location": location, "status": "missing"}
        coverage.append(info)
        try:
            if not directory.is_dir():
                continue
            entries = sorted(directory.iterdir())
            info["status"] = "searched"
            if allowed is not None:
                info["allowlist"] = sorted(allowed)
            for entry in entries:
                if entry.name.startswith(".") or (allowed is not None and entry.name not in allowed):
                    continue
                path = entry / "SKILL.md" if entry.is_dir() else entry
                if path.suffix.lower() != ".md" or not path.is_file():
                    continue
                canonical = str(path.resolve())
                if canonical in found:
                    continue
                try:
                    if path.stat().st_size > 1_000_000:
                        raise ValueError("Skill metadata file exceeds 1 MB")
                    meta = parse_skill_frontmatter(path.read_text(encoding="utf-8"))
                    inline = lambda value: " ".join(str(value or "").split())
                    name = inline(meta.get("name")) or (entry.name if entry.is_dir() else entry.stem)
                    found[canonical] = {"name": name, "description": inline(meta.get("description")),
                                        "path": canonical, "location": location}
                except (OSError, UnicodeError, ValueError) as error:
                    errors.append({"path": str(path), "error": type(error).__name__})
        except OSError as error:
            info["status"] = "unavailable"
            errors.append({"path": str(directory), "error": type(error).__name__})
    return {"skills": sorted(found.values(), key=lambda row: (row["name"].casefold(), row["path"])),
            "roots": coverage, "errors": errors}


def map_skills(notebook: Notebook, directories: list[Path] | None = None) -> dict:
    """Create missing catalog pages and refresh the generated index; retain prose."""
    from .config import prepare

    inventory = scan_skills(directories)
    created, preserved = [], []
    with maintenance_lock(notebook.root):
        prepare(notebook.root)
        links = []
        for row in inventory["skills"]:
            slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", row["name"].lower()).strip("-")[:60] or "skill"
            suffix = hashlib.sha256(row["path"].encode()).hexdigest()[:12]
            record = f"skills/catalog/{slug}-{suffix}.md"
            made = notebook.stub_skill(record, row["name"], row["path"], row["description"], row["location"])
            if not made:
                page = notebook.read(record)
                start, end = "<!-- wiki-source-metadata -->", "<!-- /wiki-source-metadata -->"
                block = start + "\n## Current installed metadata\n" + row['description'] + "\n\nSource: " + row['path'] + "\n" + end
                pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
                updated = pattern.sub(lambda _: block, page) if start in page and end in page else page.rstrip() + "\n\n" + block + "\n"
                if updated != page:
                    notebook.write(record, updated)
            (created if made else preserved).append(record)
            label = row["name"].replace("[", "\\[").replace("]", "\\]")
            links.append(f"- [{label}](./{Path(record).name}) — {row['location']}")
        index = ["# Skills map", "", "Generated inventory; edit individual pages to add knowledge.",
                 "Metadata describes installed files, not verified capability or usage history.", "", *links,
                 "", "## Coverage", "Shallow scan of the roots below; plugin caches and remote catalogs are not recursively searched."]
        index += [f"- {r['path']} — {r['status']}" + (" (co ai default allowlist)" if "allowlist" in r else "")
                  for r in inventory["roots"]]
        index += ["", "## Unreadable entries"]
        index += [f"- {r['path']} — {r['error']}" for r in inventory["errors"]] or ["- None"]
        index += ["", "Existing pages are retained when a source moves or disappears; absence does not delete knowledge."]
        notebook.write("skills/catalog/index.md", "\n".join(index) + "\n")
    return {**inventory, "created": created, "preserved": preserved, "index": "skills/catalog/index.md"}
