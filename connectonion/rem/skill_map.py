"""Inventory installed skills and keep one catalog page per skill name, without a model.

A skill installed in `~/.claude/skills`, `~/.codex/skills` and `~/.agents/skills`
is one skill. On the owner's notebook (September 2026) the catalog held 420
pages for 163 names -- a page per copy, copies in temporary worktrees and
`site-packages` included -- and 409 pasted the whole SKILL.md (#1974). Now:

- one page per name, `skills/catalog/<name>.md`;
- copies compared by content hash and listed in the page's map-owned `Source`
  block, where a copy that drifted says so;
- a copy in a temporary or package location is never a page's `File`, and a
  name found only there has no page (the index lists it);
- the source is linked, not pasted; the frontmatter facts are kept short;
- `Usage history` opens with invocations counted from the user's sessions
  (`skill_usage`);
- pages an earlier map made per copy are merged into the name's page
  (`merge.merge_into`): written lines kept, the old page archived, its record an alias.
"""

import hashlib
from contextlib import nullcontext
import os
import re
from pathlib import Path

from .files import Notebook, maintenance_lock
from .page_review import prose

COPIES = ("<!-- rem-installed-copies -->", "<!-- /rem-installed-copies -->")
USAGE = ("<!-- rem-usage -->", "<!-- /rem-usage -->")
# Where a copy is made and unmade by something else: a checkout, an upgrade, a cache.
TRANSIENT = (("/.claude/worktrees/", "temporary worktree"), ("/.codex/worktrees/", "temporary worktree"),
             ("/.worktree/", "worktree"), ("/.worktrees/", "worktree"),
             ("/site-packages/", "installed package"), ("/dist-packages/", "installed package"),
             ("/plugins/cache/", "plugin cache"), ("/.cache/", "cache"), ("/Caches/", "cache"))
SHORT_DESCRIPTION = 280


def transient(path: str) -> str:
    """Why a copy's location is temporary or managed by something else, or ""."""
    return next((why for marker, why in TRANSIENT if marker in path), "")


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
                    raw = path.read_bytes()
                    content = raw.decode("utf-8")
                    meta = parse_skill_frontmatter(content)
                    inline = lambda value: " ".join(str(value or "").split())
                    name = inline(meta.get("name")) or (entry.name if entry.is_dir() else entry.stem)
                    tools = meta.get("allowed-tools") or meta.get("allowed_tools") or ""
                    found[canonical] = {"name": name, "description": inline(meta.get("description")),
                                        "path": canonical, "location": location,
                                        "sha256": hashlib.sha256(raw).hexdigest(),
                                        "allowed_tools": inline(", ".join(map(str, tools))
                                                                if isinstance(tools, list) else tools)}
                    if include_content:
                        found[canonical]["_content"] = content
                except (OSError, UnicodeError, ValueError) as error:
                    errors.append({"path": str(path), "error": type(error).__name__})
        except OSError as error:
            info["status"] = "unavailable"
            errors.append({"path": str(directory), "error": type(error).__name__})
    return {"skills": sorted(found.values(), key=lambda row: (row["name"].casefold(), row["path"])),
            "roots": coverage, "errors": errors}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", name.lower()).strip("-")[:60] or "skill"


def _title(page: str) -> str:
    return next((line[2:].strip() for line in page.splitlines() if line.startswith("# ")), "")


def _record(notebook: Notebook, name: str) -> str:
    """`skills/catalog/<slug>.md`, unless another name already holds that slug."""
    record = f"skills/catalog/{_slug(name)}.md"
    path = notebook.path(record)
    if path.is_file() and _title(notebook.read(record)).casefold() != name.casefold():
        record = f"skills/catalog/{_slug(name)}-{hashlib.sha256(name.encode()).hexdigest()[:8]}.md"
    return record


def _short(text: str) -> str:
    if len(text) <= SHORT_DESCRIPTION:
        return text
    return text[:SHORT_DESCRIPTION].rsplit(" ", 1)[0].rstrip(",;:") + " …"


def _copies_block(copies: list[dict], gone: list[str]) -> str:
    """The Source section's map-owned lines: the file, and every other copy."""
    if not copies:
        return "\n".join([COPIES[0], *[f"- No longer found: {path}" for path in gone],
                          "- Status: no installed copy found at the last map", COPIES[1]])
    primary = copies[0]
    same = sum(1 for row in copies if row["sha256"] == primary["sha256"])
    lines = [COPIES[0], f"- File: {primary['path']}", f"- Discovery: {primary['location']}"]
    if primary["allowed_tools"]:
        lines.append(f"- Allowed tools: {primary['allowed_tools']}")
    count = f"{len(copies)} installed cop{'ies' if len(copies) > 1 else 'y'}"
    if 1 < len(copies) and same < len(copies):
        count += f", {len(copies) - same} with different content"
    lines.append(f"- Content: sha256 {primary['sha256'][:12]}; {count}")
    for row in copies[1:]:
        where = transient(row["path"])
        state = "identical" if row["sha256"] == primary["sha256"] else f"differs: sha256 {row['sha256'][:12]}"
        lines.append(f"- Also installed at: {row['path']} ({(where + '; ') if where else ''}{state})")
    lines += [f"- No longer found: {path}" for path in gone]
    lines += ["- Status: mapped from metadata; behavior not verified", COPIES[1]]
    return "\n".join(lines)


def _replace_block(section: str, markers: tuple[str, str], block: str) -> str:
    pattern = re.compile(re.escape(markers[0]) + r"\n.*?" + re.escape(markers[1]), re.S)
    if pattern.search(section):
        return pattern.sub(lambda _: block, section, count=1)
    return block + ("\n" + section if section.strip() else "")


def _with_section(page: str, heading: str, update) -> str:
    """`page` with one section's body passed through `update`; added before Sources if missing."""
    from .merge import render, sections
    head, parts, status = sections(page)
    names = [name for name, _ in parts]
    if heading in names:
        i = names.index(heading)
        parts[i] = (heading, update(parts[i][1]))
    else:
        at = names.index("Sources") if "Sources" in names else len(parts)
        parts.insert(at, (heading, update("")))
    return render(head, parts, status)


def _shape(page: str, copies: list[dict], gone: list[str], usage: str, description: str) -> str:
    """A catalog page in its current shape, whatever an earlier map left: no pasted
    source, the copies block in Source, the usage line opening Usage history."""
    from .merge import strip_generated
    page = strip_generated(page)
    installed = description and description not in prose(page)

    def source(body):
        kept = [line for line in body.splitlines()
                if line.strip() and not re.match(r"^- (?:File|Discovery|Status): ", line.strip())]
        block = _copies_block(copies, gone)
        if installed:  # the page says something else now; the installed words stay visible
            block = block.replace(COPIES[1], f"- Installed description: {_short(description)}\n{COPIES[1]}")
        return "\n".join([block, *kept])

    def history(body):
        kept = [line for line in body.splitlines() if line.strip() and "not investigated yet" not in line]
        return "\n".join([USAGE[0], usage, USAGE[1], *kept])

    def sources(body):  # the metadata citation names the page's File, not a merged copy's
        if not copies:
            return body
        return re.sub(r"^- Skill metadata: .*$", f"- Skill metadata: {copies[0]['path']}", body, count=1, flags=re.M)

    page = _with_section(page, "Source", source)
    page = _with_section(page, "Sources", sources)
    return _with_section(page, "Usage history", history)


def _existing(notebook: Notebook) -> dict:
    """Catalog pages by skill name, as earlier maps made them."""
    pages = {}
    for record in notebook.list("skills"):
        if record.startswith("skills/catalog/") and record != "skills/catalog/index.md":
            pages.setdefault(_title(notebook.read(record)).casefold(), []).append(record)
    return pages


def _listed_files(page: str) -> list[str]:
    return re.findall(r"^- (?:File|Also installed at|No longer found): (/.+?)(?: \(.*\))?$", page, re.M)


def map_skills(notebook: Notebook, directories: list[Path] | None = None, *, lock_held: bool = False,
               subscriptions: dict | None = None, days: int = 180) -> dict:
    """One page per skill name; merge per-copy pages; refresh the map-owned lines and the index."""
    from .config import prepare
    from .merge import mapped_only, merge_into, weight
    from .skill_usage import usage, usage_line

    inventory = scan_skills(directories)
    by_name = {}
    for row in inventory["skills"]:
        by_name.setdefault(row["name"].casefold(), []).append(row)
    created, preserved, merged, archived, only_transient = [], [], [], [], []
    with nullcontext() if lock_held else maintenance_lock(notebook.root):
        prepare(notebook.root)
        if subscriptions is None:
            from .service import subscriptions as saved
            subscriptions = saved(notebook.root)
        counted = usage(subscriptions, [rows[0]["name"] for rows in by_name.values()], root=notebook.root, days=days)
        existing = _existing(notebook)
        links = []
        for key in sorted(set(by_name) | set(existing)):
            rows = by_name.get(key, [])
            # The page's File: a copy somewhere real, the content most copies share, then by path.
            shared = {row["sha256"]: sum(r["sha256"] == row["sha256"] for r in rows) for row in rows}
            rows = sorted(rows, key=lambda row: (bool(transient(row["path"])), -shared[row["sha256"]], row["path"]))
            pages = existing.get(key, [])
            if rows and transient(rows[0]["path"]):
                only_transient += [{"name": row["name"], "path": row["path"], "why": transient(row["path"])}
                                   for row in rows]
                rows = []
            if not rows:
                # No real copy installed: pages that hold only map output and name
                # only temporary copies go to the archive; anything written stays.
                stale = [page for page in pages if mapped_only(notebook.read(page))
                         and all(transient(path) or not Path(path).exists()
                                 for path in _listed_files(notebook.read(page)) or ["/tmp/"])]
                for page in stale:
                    target = notebook.root / ".state" / "archived" / page
                    target.parent.mkdir(parents=True, exist_ok=True)
                    notebook.path(page).replace(target)
                    archived.append(page)
                pages = [page for page in pages if page not in stale]
                if not pages:
                    continue
            name = rows[0]["name"] if rows else _title(notebook.read(pages[0]))
            record = _record(notebook, name)
            if not notebook.path(record).is_file():
                base = max(pages, key=lambda page: (weight(notebook.read(page)), page), default=None)
                if base:  # the page with the most written content becomes the name's page
                    notebook.write(record, notebook.read(base))
                    target = notebook.root / ".state" / "archived" / base
                    target.parent.mkdir(parents=True, exist_ok=True)
                    notebook.path(base).replace(target)
                    pages = [page for page in pages if page != base]
                    _alias(notebook, base, record)
                    merged.append({"from": base, "into": record})
            made = notebook.stub_skill(record, name, rows[0]["path"] if rows else "",
                                       _short(rows[0]["description"]) if rows else "",
                                       rows[0]["location"] if rows else "")
            for page in pages:
                if page != record:
                    merged.append(merge_into(notebook, record, page, "same skill name"))
            installed = {row["path"] for row in rows}
            gone = sorted({path for path in _listed_files(notebook.read(record))
                           if path not in installed and not Path(path).exists()})
            line = usage_line(counted["counts"].get(name), counted)
            page = notebook.read(record)
            shaped = _shape(page, rows, gone, line, rows[0]["description"] if rows else "")
            if shaped != page:
                notebook.write(record, shaped)
            (created if made else preserved).append(record)
            label = name.replace("[", "\\[").replace("]", "\\]")
            use = counted["counts"].get(name) or {}
            links.append(f"- [{label}](./{Path(record).name}) — {len(rows)} cop{'ies' if len(rows) != 1 else 'y'}"
                         + (f"; used {use['count']}×, last {use['last']}" if use.get("count") else ""))
        index = ["# Skills map", "", "Generated inventory, one page per skill name; edit individual pages to add knowledge.",
                 "Metadata describes installed files, not verified capability. Use counts are invocations in your "
                 "coding sessions, not completed runs.", "", *links]
        if only_transient:
            index += ["", "## Only in temporary or package locations", "No page: these copies come and go with a "
                      "checkout, an upgrade or a cache."]
            index += [f"- {row['name']} — {row['path']} ({row['why']})" for row in only_transient]
        index += ["", "## Coverage", "Shallow scan of the roots below; plugin caches and remote catalogs are not recursively searched."]
        index += [f"- {r['path']} — {r['status']}" + (" (co ai default allowlist)" if "allowlist" in r else "")
                  for r in inventory["roots"]]
        index += ["", "## Unreadable entries"]
        index += [f"- {r['path']} — {r['error']}" for r in inventory["errors"]] or ["- None"]
        index += ["", "Pages merged into another keep their old names as aliases (.state/aliases.json); "
                  "pages are moved to .state/archived/, never deleted."]
        notebook.write("skills/catalog/index.md", "\n".join(index) + "\n")
    return {**inventory, "created": created, "preserved": preserved, "merged": merged, "archived": archived,
            "only_transient": only_transient, "usage": {"files": counted["files"], "days": counted["days"],
                                                         "sources": counted["sources"]},
            "index": "skills/catalog/index.md"}


def _alias(notebook: Notebook, old: str, new: str) -> None:
    """The base page moved to its name's record: the old record is an alias; nothing to merge."""
    from .files import read_json, state_path, write_json
    from .merge import ALIASES, _relink
    from datetime import date
    table = read_json(state_path(notebook.root, ALIASES), {})
    for entry in table.values():
        if entry["into"] == old:
            entry["into"] = new
    table[old] = {"into": new, "reason": "one page per skill name", "date": date.today().isoformat(),
                  "archived": f".state/archived/{old}"}
    write_json(state_path(notebook.root, ALIASES), table)
    _relink(notebook, old, new)
