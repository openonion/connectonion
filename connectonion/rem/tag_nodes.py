"""Tag pages (#3140): every tag links to a page; a tag no page is named for gets a tag page, by investigate.

The knowledge graph has one kind of point, the page (docs/cli/rem-naming.md). A tag
names a person, organisation or project page when one is named for it (by title,
alias or file name): then the tag is a link to that page and nothing is written.
A tag no page is named for (a role, a theme) and shared by two or more pages gets
a tag page (标签页), `knowledge/<tag>.md`: `co rem investigate tag "AI Agent"` (or
`co rem investigate tags` for every tag page that is due) has the cheap model read
the pages carrying it and write the page when missing, append when it exists.

A tag is a knowledge page. Every page carrying `kiln-pilot` is read (its head and
the lines that name the tag), and the model writes `knowledge/kiln-pilot.md`:
what it is, how its pages connect, and a timeline. Every line is cited by a
notebook-wide number whose definition is the member page's own source, so a node
line traces to mail or a session, never just to another page. Code owns the
title's Tags line, the member list and the Sources; the model owns the prose.
A node is rewritten only when its members changed (`.state/tag-nodes.json`),
and a cited line the node had is kept (#3105's append rule).
"""

import hashlib
import json
import re
import tempfile
import time
import uuid
from pathlib import Path

from . import tags
from .files import Notebook, RemError, maintenance_lock, read_json, state_path, write_json

MIN_MEMBERS = 2          # default for limits.topic_min_pages: a tag on one page stays a plain link


def min_pages(root: Path) -> int:
    """How many pages must share an unresolved tag before it gets a tag page (limits.topic_min_pages)."""
    from .config import read_config
    return int(read_config(root)["limits"].get("topic_min_pages", MIN_MEMBERS))
MAX_MEMBERS = 40         # the most-cited members are read; the rest are listed
HEAD = 1200              # characters of each member page's head
TAG_LINES = 6            # plus up to this many of its lines naming the tag
LEDGER = "tag-nodes.json"
TURN_BASE = 70_000
SOURCE_DEF = re.compile(r"(?m)^- \[(W?\d+)\][ \t]+(.+)$")
# A privacy mark as the reader reads one (reader_model.PRIVATE): a tag page's title never carries it (#3385).
PRIVATE = re.compile(r"[\[［](?:sensitive|personal)[\]］]", re.I)


def _title(text: str, record: str) -> str:
    first = text.partition("\n")[0]
    return first[2:].strip() if first.startswith("# ") else Path(record).stem


PAGE_KINDS = ("orgs", "projects", "people")   # the order a name shared by two kinds resolves in


def _names_of(text: str, record: str) -> set[str]:
    stem = Path(record).stem
    names = {_title(text, record), stem, re.sub(r"-[0-9a-f]{10}$", "", stem)}
    for line in re.findall(r"(?m)^- Also known as:[ \t]*(.+)$", text):
        names.update(part for part in re.split(r"[,;，；]", re.sub(r"\[(W?\d+)\]", "", line)))
    return {tags.normalise(name) for name in names if tags.normalise(name)}


def pages_for_tags(root: Path) -> dict[str, str]:
    """{tag: the person, organisation or project page named for it}, by title, alias or file name."""
    return tags.once(root, "pages_for_tags", lambda: _pages_for_tags(root))


def _pages_for_tags(root: Path) -> dict[str, str]:
    book, index = Notebook(root), {}
    for category in PAGE_KINDS:
        for record in book.list(category):
            for name in _names_of(book.read(record), record):
                index.setdefault(name, record)
    found = {}
    for slug, entry in tags.vocabulary(root).items():
        for name in (slug, entry.get("label", ""), *entry.get("aliases", [])):
            record = index.get(tags.normalise(name)) if name else None
            if record:
                found[slug] = record
                break
    return found


def topic_slug(root: Path, target: str) -> str:
    """The tag `co rem investigate TARGET` means when TARGET is a topic: a tag name or alias no person,
    organisation or project page is named for, `topics/<slug>`, or the tag page's path. '' otherwise."""
    from .files import Notebook as _Notebook
    value = target.strip()
    if value.startswith("topics/"):
        value = value[len("topics/"):]
    if value.startswith("knowledge/") and value.endswith(".md"):
        value = Path(value).stem
    vocabulary, found = tags.vocabulary(root), members(root)
    slug = tags.resolve(vocabulary, value) or (tags.normalise(value) if tags.normalise(value) in found else None)
    if not slug or slug in pages_for_tags(root):
        return ""
    if target.startswith("knowledge/") and node_record(root, slug) != target:
        return ""
    return slug if slug in found or _Notebook(root).exists(node_record(root, slug)) else ""


def due(root: Path) -> list[str]:
    """Topics due for investigation: shared by enough pages, unwritten or with new or changed pages."""
    return candidates(root)


def node_record(root: Path, slug: str) -> str:
    """The tag's knowledge page: knowledge/<slug>.md, or a knowledge entry already named for the tag."""
    book, entry = Notebook(root), tags.vocabulary(root).get(slug, {})
    if f"knowledge/{slug}.md" in book.list("knowledge"):
        return f"knowledge/{slug}.md"
    names = {tags.normalise(name) for name in (slug, entry.get("label", ""), *entry.get("aliases", [])) if name}
    for record in book.list("knowledge"):
        if tags.normalise(_title(book.read(record), record)) in names:
            return record
    return f"knowledge/{slug}.md"


def members(root: Path) -> dict[str, list[str]]:
    """{tag: [records carrying it]}, a tag's own node excluded, in path order."""
    return tags.once(root, "members", lambda: _members(root))


def _members(root: Path) -> dict[str, list[str]]:
    book, found = Notebook(root), {}
    for record in book.list():
        for slug in tags.page_tags(book.read(record)):
            found.setdefault(slug, []).append(record)
    return {slug: sorted(r for r in records if r != f"knowledge/{slug}.md") for slug, records in found.items()}


def orphans(root: Path) -> list[str]:
    """Written pages of a tagged kind that carry no tag: nothing connects them to the graph yet."""
    from .census import written
    book = Notebook(root)
    return sorted(record for category in tags.TAGGED_KINDS for record in book.list(category)
                  if written(book.read(record)) and not tags.page_tags(book.read(record)))


def _digest(root: Path, records: list[str]) -> str:
    from .tag_stage import digest
    book = Notebook(root)
    return hashlib.sha256(json.dumps([[r, digest(book.read(r))] for r in records]).encode()).hexdigest()


def candidates(root: Path) -> list[str]:
    """Tags no page is named for, carried by two or more pages, whose tag page is missing or older
    than its members, the largest first."""
    ledger, found, named = read_json(state_path(root, LEDGER), {}), members(root), pages_for_tags(root)
    waiting = [(-len(records), slug) for slug, records in found.items()
               if slug not in named and len(records) >= min_pages(root) and ledger.get(slug) != _digest(root, records)]
    return [slug for _, slug in sorted(waiting)]


def _body(text: str) -> str:
    body = re.split(r"(?m)^## Sources[ \t]*$", tags.without_tags(text))[0]
    return re.sub(r"(?m)^Investigation:[^\n]*$", "", body).strip()


def _excerpt(text: str, names: set[str]) -> str:
    body = _body(text)
    head, rest = body[:HEAD], body[HEAD:]
    lines = [line for line in rest.splitlines() if line.strip() and any(name in tags.normalise(line) for name in names)]
    return head + ("\n…\n" + "\n".join(lines[:TAG_LINES]) if lines else ("\n…" if rest else ""))


def _table(before: str, texts: dict[str, str]) -> tuple[dict, dict]:
    """One source table: the node's own Sources keep their numbers, members' sources follow, each id once.

    Returns ({number: definition}, {record: {local: number}})."""
    table, by_id, local = {}, {}, {}
    for number, definition in SOURCE_DEF.findall(before):
        table[number] = definition.strip()
        by_id.setdefault(definition.split()[0], number)
    following = max((int(n.lstrip("W")) for n in table), default=0)
    for record, text in texts.items():
        local[record] = {}
        for number, definition in SOURCE_DEF.findall(text.partition("\n## Sources\n")[2]):
            key = definition.split()[0]
            if key not in by_id:
                following += 1
                by_id[key] = str(following)
                table[str(following)] = f"{definition.strip()} — from `{record}`"
            local[record][number] = by_id[key]
    return table, local


def _skill() -> str:
    from .runner import useful_skills_dir
    text = (useful_skills_dir() / "rem-tag-node" / "SKILL.md").read_text(encoding="utf-8")
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)


def prepare(root: Path, slug: str, *, directory: Path, native: bool = False) -> dict:
    """The files the model reads for one tag, and the task the review checks against."""
    book, entry = Notebook(root), tags.vocabulary(root).get(slug, {"label": slug, "kind": "topic", "aliases": []})
    record, records = node_record(root, slug), members(root).get(slug, [])
    before = book.read(record) if record in book.list("knowledge") else ""
    texts = {r: book.read(r) for r in records}
    read = sorted(records, key=lambda r: -len(SOURCE_DEF.findall(texts[r])))[:MAX_MEMBERS]
    table, local = _table(before, {r: texts[r] for r in read})
    names = {tags.normalise(n) for n in (slug, entry.get("label", ""), *entry.get("aliases", [])) if n}
    directory.mkdir(parents=True, exist_ok=True)
    blocks = []
    for r in read:
        excerpt = re.sub(r"\[(W?\d+)\](?!\()", lambda m, r=r: f"[{local[r].get(m[1], '?')}]", _excerpt(texts[r], names))
        blocks.append(f"## {r} — {_title(texts[r], r)}\n\n{excerpt}\n")
    (directory / "members.md").write_text("\n".join(blocks), encoding="utf-8")
    (directory / "sources.md").write_text("\n".join(f"[{n}] {d}" for n, d in table.items()) + "\n", encoding="utf-8")
    before_file = directory / "node-before.md"
    before_file.write_text(before or "(no tag page yet)\n", encoding="utf-8")
    output = directory / "candidate.md"
    label = entry.get("label") or slug
    task = (f"<co_rem_task> Write the knowledge node for the tag \"{label}\" ({entry.get('kind', 'topic')}), carried by "
            f"{len(records)} pages. Members: {directory / 'members.md'}. Source numbers: {directory / 'sources.md'}. "
            f"The node as it stands: {before_file}. Write the page to {output}. </co_rem_task>")
    if native:
        prompt = "/rem-tag-node " + task
    else:
        (directory / "rem-tag-node.md").write_text(_skill(), encoding="utf-8")
        prompt = f"Read {directory / 'rem-tag-node.md'}: it is the skill for this task, and follow it.\n" + task
    return {"slug": slug, "label": label, "record": record, "records": records, "before": before,
            "before_file": str(before_file), "sources": table, "numbers": sorted(int(n.lstrip("W")) for n in table),
            "candidate": str(output), "prompt": prompt, "digest": _digest(root, records)}


def _sections(text: str) -> list[tuple[str, list[str]]]:
    parts, heading = [("", [])], ""
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line
            parts.append((heading, []))
        else:
            parts[-1][1].append(line)
    return parts


def _keep_lines(before: str, after: str) -> str:
    """Every cited line the node had, put back under its heading when the rewrite dropped it (#3105)."""
    def key(line):
        return " ".join(re.sub(r"\[(W?\d+)\]", "", line).split()).casefold()
    kept = {key(line) for line in after.splitlines()}
    lost = [(heading, line) for heading, lines in _sections(_prose(before)) for line in lines
            if re.search(r"\[(W?\d+)\](?!\()", line) and key(line) not in kept]
    if not lost:
        return after
    out = after.rstrip("\n").split("\n")
    for heading, line in lost:
        at = next((i for i, row in enumerate(out) if heading and row == heading), None)
        if at is None:
            out.append(line)
            continue
        end = next((i for i in range(at + 1, len(out)) if out[i].startswith("## ")), len(out))
        while end > at + 1 and not out[end - 1].strip():
            end -= 1
        out.insert(end, line)
    return "\n".join(out) + "\n"


def _prose(text: str) -> str:
    """The page without what code owns: the Tags line, the member list, the stamp and the Sources."""
    text = re.sub(r"(?m)^Investigation:[^\n]*\n?", "", tags.without_tags(text))
    return re.split(r"(?m)^## (?:Pages|Sources)[ \t]*$", text)[0].rstrip() + "\n"


def check(root: Path, task: dict, output: dict) -> str:
    """The reviewed node page, or RemError saying why it is refused."""
    path = Path(task["candidate"])
    raw = path.read_text(encoding="utf-8") if path.is_file() else str(output.get("result") or "")
    prose = _prose(raw.strip() + "\n")
    if not re.match(r"# \S", prose) or len(re.findall(r"(?m)^# ", prose)) != 1:
        raise RemError("The tag page needs exactly one title line, first")
    if PRIVATE.search(prose.partition("\n")[0]):
        raise RemError("A tag page's title never carries [personal] or [sensitive]: the reader would show it as "
                       "\"Personal\", like every other marked page. Put the mark on the passage that is private")
    cited = re.findall(r"\[(W?\d+)\](?!\()", prose)
    if not cited:
        raise RemError("The tag page has no cited line; every line cites a source number from sources.md")
    unknown = sorted({n for n in cited if n not in task["sources"]}, key=lambda n: int(n.lstrip("W")))
    if unknown:
        raise RemError("The tag page cites " + ", ".join(f"[{n}]" for n in unknown) + ", not in sources.md")
    return _keep_lines(task["before"], prose) if task["before"] else prose


def _page(root: Path, task: dict, prose: str) -> str:
    book = Notebook(root)
    page = tags.with_tags(prose, [{"tag": task["slug"], "citation": ""}])
    links = [f"- [{_title(book.read(r), r)}](../{r})" for r in task["records"]]
    from .service import now
    stamp = f"Investigation: investigated {now().date().isoformat()} (tag page, from {len(task['records'])} pages)"
    used = sorted({n for n in re.findall(r"\[(W?\d+)\](?!\()", prose)}, key=lambda n: int(n.lstrip("W")))
    sources = [f"- [{n}] {task['sources'][n]}" for n in used if n in task["sources"]]
    return (page.rstrip("\n") + "\n\n## Pages\n" + "\n".join(links) + "\n\n" + stamp + "\n\n## Sources\n"
            + "\n".join(sources) + "\n")


def commit(root: Path, task: dict, prose: str) -> list[str]:
    """Write the node and mark its members read; the caller may hold the maintenance lock."""
    from .page_review import PAGE_REFUSED
    book, ledger = Notebook(root), read_json(state_path(root, LEDGER), {})
    if task["before"] and book.read(task["record"]) != task["before"]:
        return []  # changed since it was read: it waits for the next turn
    page = _page(root, task, prose)
    if len(page) > PAGE_REFUSED:
        raise RemError(f"The tag page is {len(page):,} characters, over the {PAGE_REFUSED:,} limit; keep it shorter")
    from . import page_versions
    changed = [task["record"]] if book.write(task["record"], page) is not False else []
    page_versions.keep_previous(root, task["record"], task["before"], page)  # Undo, as for any investigated page
    ledger[task["slug"]] = task["digest"]
    write_json(state_path(root, LEDGER), ledger)
    return changed


def estimate(root: Path, slug: str) -> int:
    """Input tokens one node turn reads, about four characters a token, with no model."""
    with tempfile.TemporaryDirectory() as temporary:
        task = prepare(root, slug, directory=Path(temporary))
        read = sum(len((Path(temporary) / name).read_text()) for name in ("members.md", "sources.md", "node-before.md"))
    # A Codex turn reads about 70,000 tokens of its own before the task's files (measured 2026-11-19: three
    # tag pages on Luna read 79–81k each).
    return TURN_BASE + (read + len(task["prompt"]) + 6000) // 4


def dry_run(root: Path) -> dict:
    found, waiting, named = members(root), candidates(root), pages_for_tags(root)
    used, least = [slug for slug in found if slug in named], min_pages(root)
    return {"tags": len(found), "members": {slug: len(records) for slug, records in found.items()},
            "tags_linked_to_pages": len(used),
            "tag_pages_possible": sum(1 for slug, records in found.items() if slug not in named and len(records) >= least),
            "single_page_tags": sum(1 for slug, records in found.items() if slug not in named and len(records) < least),
            "waiting": len(waiting), "orphans": len(orphans(root)),
            "estimated_input_tokens": sum(estimate(root, slug) for slug in waiting)}


def write_nodes(root: Path, *, limit: int = 50, only: str = "", run=None, ready=None, say=None) -> dict:
    """Write up to `limit` waiting tag pages (or only one tag's), one cheap-model turn each."""
    from . import config as rem_config, runner, service
    from .inquiry import stage_config
    settings = stage_config(root, rem_config.read_config(root), "tag-node")
    problem, fix = (ready or runner.ready)(settings)
    if problem:
        raise RemError(f"{problem}; run `{fix}` and try again")
    named = pages_for_tags(root)
    slugs = [tags.normalise(only)] if only else candidates(root)[:limit]
    # A tag a page is named for is a link to that page: there is nothing to write (#3140).
    linked = {slug: named[slug] for slug in slugs if slug in named}
    slugs = [slug for slug in slugs if slug not in linked]
    record = {"id": "run_" + uuid.uuid4().hex, "phase": "investigate", "stage": "tag-page", "started_at": service.now().isoformat(),
              "outcome": "running", "items": len(slugs), "written": [], "linked": linked, "failed": 0, "errors": [],
              "usage": {}, "model": settings["model"], **({"record": node_record(root, slugs[0])} if len(slugs) == 1 else {})}
    started, path = time.monotonic(), state_path(root, f"runs/{record['id']}.json")
    tasks_dir = state_path(root, "tasks")
    tasks_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for slug in slugs:
        try:
            with tempfile.TemporaryDirectory(prefix="node-", dir=tasks_dir) as temporary:
                task = prepare(root, slug, directory=Path(temporary))
                envelope = (run or runner.run_task)(Path(temporary), task["prompt"], settings, "tag-node")
                prose = check(root, task, envelope)
                with maintenance_lock(root, wait=60):
                    record["written"] += commit(root, task, prose)
            record["usage"] = _add(record["usage"], envelope.get("usage"))
        except (runner.RunFailed, RemError, OSError) as error:
            record["failed"] += 1
            record["errors"].append(f"{slug}: {str(error)[:300]}")
        if say:
            say(f"[{slugs.index(slug) + 1}/{len(slugs)}] {slug}: "
                + ("written" if f"knowledge/{slug}.md" in record["written"] or not record["errors"]
                   or not record["errors"][-1].startswith(slug + ":") else record["errors"][-1]))
        write_json(path, record)
    record.update(outcome="failed" if record["failed"] and not record["written"] else
                  "partial" if record["failed"] else "completed",
                  finished_at=service.now().isoformat(), seconds=round(time.monotonic() - started, 3))
    write_json(path, record)
    return {**record, "waiting": len(candidates(root))}


def _add(total: dict, usage) -> dict:
    for key, value in (usage or {}).items():
        if isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value
    return total


def summary(report: dict) -> str:
    return (f"Investigated {len(report['written'])} of {report['items']} tag pages; {report['failed']} failed; "
            f"{report['waiting']} still waiting")


def states(root: Path, records: list[str]) -> dict[str, dict]:
    """What the Investigate button says on each tag page (page_runs.states' shape for topics)."""
    from .investigate import last_investigated
    book, waiting, found = Notebook(root), set(candidates(root)), members(root)
    result = {}
    for record in records:
        slug = topic_slug(root, record)
        if not slug or not book.exists(record):
            continue
        last = last_investigated(book.read(record))
        result[record] = {"last": last.isoformat() if last else None, "new_mails": 0, "new_sessions": 0,
                          "new_pages": len(found.get(slug, [])) if slug in waiting else 0, "leads": 0,
                          "label": "investigate" if not last else "update" if slug in waiting else "current",
                          "cost": {"quick": None, "full": None}}
    return result


# ---------- tag titles carry no privacy mark (#3385) ----------
# Before #3385 a model could put `[personal]` in a tag page's title. At the default "cover" level the reader shows
# such a title as the generic "Personal", so five marked tag pages (a language, a CLI, email, documents, sleep)
# became one repeated label and a link to one opened another. The page build repairs them, local only, with no model;
# the title's mark moves onto each prose passage, so nothing private turns public. It keeps no marker: it changes
# only a marked tag title, and review refuses new ones, so it is idempotent by construction, and a notebook with
# nothing to repair is never written (opening before start creates nothing).
STAMP = re.compile(r"(?m)^Investigation:[^\n]*\(tag page\b")
CODE_OWNED = re.compile(r"^(?:#|- Tags:|Investigation:|- \[[^\]]*\]\(\.\./|- \[W?\d+\] )")


def _marked_tag_pages(root: Path) -> list[str]:
    """Tag pages whose title carries a privacy mark: a knowledge page this stage wrote, or a tag's named node.
    Only each page's first line is read until one is marked, and a missing folder is never created."""
    folder = root / "knowledge"
    if not folder.is_dir():
        return []
    marked = []
    for path in sorted(folder.glob("*.md")):
        with path.open(encoding="utf-8", errors="replace") as handle:
            if PRIVATE.search(handle.readline()):
                marked.append(f"knowledge/{path.name}")
    if not marked:
        return []
    book, named = Notebook(root), {node_record(root, slug) for slug in tags.vocabulary(root)}
    return [r for r in marked if r in named or STAMP.search(book.read(r))]


def _unmarked(text: str) -> str:
    """The page with its title's mark moved onto each prose passage that carries none."""
    title, _, rest = text.partition("\n")
    mark = PRIVATE.search(title).group(0).replace("［", "[").replace("］", "]").lower()
    # An unmasked page needs no mask number (masked.py): its own name is its label again.
    rest = re.sub(r"(?m)^Masked:[ \t]*\d+[ \t]*\n", "", rest)
    prose, *owned = re.split(r"(?m)^(?=## (?:Pages|Sources)[ \t]*$)", rest, maxsplit=1)
    lines = [line if not line.strip() or CODE_OWNED.match(line) or PRIVATE.search(line) else line.rstrip() + " " + mark
             for line in prose.split("\n")]
    return " ".join(PRIVATE.sub("", title).split()) + "\n" + "\n".join(lines) + "".join(owned)


def repair_titles(root: Path) -> list[str]:
    """Take the privacy mark off every tag page's title (#3385). The pages it changed; nothing is written otherwise."""
    from . import page_versions
    book, changed = Notebook(root), []
    for record in _marked_tag_pages(root):
        before = book.read(record)
        after = _unmarked(before)
        if book.write(record, after) is not False:
            page_versions.keep_previous(root, record, before, after)
            changed.append(record)
    return changed
