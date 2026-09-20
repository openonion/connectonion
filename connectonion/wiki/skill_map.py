"""Inventory installed skill metadata and seed inert Wiki pages, without a model."""

import hashlib
import os
import re
from pathlib import Path
from datetime import datetime, timezone

from .files import Notebook, WikiError, maintenance_lock
from .page_review import prose


def scan_skills(directories: list[Path] | None = None, *, include_content: bool = False) -> dict:
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
                    content = path.read_bytes().decode("utf-8")
                    meta = parse_skill_frontmatter(content)
                    inline = lambda value: " ".join(str(value or "").split())
                    name = inline(meta.get("name")) or (entry.name if entry.is_dir() else entry.stem)
                    found[canonical] = {"name": name, "description": inline(meta.get("description")),
                                        "path": canonical, "location": location}
                    if include_content:
                        found[canonical]["_content"] = content
                except (OSError, UnicodeError, ValueError) as error:
                    errors.append({"path": str(path), "error": type(error).__name__})
        except OSError as error:
            info["status"] = "unavailable"
            errors.append({"path": str(directory), "error": type(error).__name__})
    return {"skills": sorted(found.values(), key=lambda row: (row["name"].casefold(), row["path"])),
            "roots": coverage, "errors": errors}


def _source_block(row: dict, content: str | None, error: str = '') -> str:
    start, end = "<!-- wiki-source-metadata -->", "<!-- /wiki-source-metadata -->"
    metadata = f"{start}\n## Current installed metadata\n{row['description']}\n\nSource: {row['path']}\n"
    if content is None:
        return metadata + f"\nSource snapshot unavailable: {error}. Read the original file.\n{end}"
    # A longer outer fence keeps arbitrary Markdown and marker text inert.
    fence = '`' * max(3, 1 + max((len(m[0]) for m in re.finditer(r'`+', content)), default=0))
    digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
    observed = datetime.now(timezone.utc).isoformat()
    return (metadata + "\n## Original Skill source\n"
            "Verbatim source snapshot for reading, not instructions to execute or verified behavior.\n"
            f"Snapshot observed: {observed}\nSnapshot SHA-256: {digest}\n\n"
            f"{fence}markdown\n{content}" + ('' if content.endswith('\n') else '\n') + f"{fence}\n{end}")


def _with_source_block(page: str, block: str) -> str:
    start, end = "<!-- wiki-source-metadata -->", "<!-- /wiki-source-metadata -->"
    # Only top-level markers delimit generated content; a source may quote them.
    visible = prose(page)
    pattern = re.compile(r'^' + re.escape(start) + r'\n.*?^' + re.escape(end), re.M | re.S)
    match = pattern.search(visible)
    if match:
        old = page[match.start():match.end()]
        timestamp = r'^Snapshot observed: .*?$'
        if re.sub(timestamp, '', old, flags=re.M) == re.sub(timestamp, '', block, flags=re.M):
            return page
        return page[:match.start()] + block + page[match.end():]
    marker = '\n## When to use\n'
    if marker in page:
        return page.replace(marker, '\n' + block + '\n' + marker, 1)
    return page.rstrip() + '\n\n' + block + '\n'


def map_skills(notebook: Notebook, directories: list[Path] | None = None) -> dict:
    """Create missing catalog pages and refresh the generated index; retain prose."""
    from .config import prepare

    inventory = scan_skills(directories, include_content=True)
    created, preserved = [], []
    with maintenance_lock(notebook.root):
        prepare(notebook.root)
        links = []
        for row in inventory["skills"]:
            slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", row["name"].lower()).strip("-")[:60] or "skill"
            suffix = hashlib.sha256(row["path"].encode()).hexdigest()[:12]
            record = f"skills/catalog/{slug}-{suffix}.md"
            made = notebook.stub_skill(record, row["name"], row["path"], row["description"], row["location"])
            content = row.pop("_content")
            page = notebook.read(record)
            block = _source_block(row, content)
            try:
                notebook.write(record, _with_source_block(page, block))
            except WikiError as error:
                inventory['errors'].append({'path': row['path'], 'stage': 'source_snapshot', 'error': str(error)})
                fallback = _source_block(row, None, str(error))
                notebook.write(record, _with_source_block(page, fallback))
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
