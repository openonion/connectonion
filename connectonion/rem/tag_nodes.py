"""`co rem tag`'s second step (#3140): each tag's page, written by the cheap model from the pages carrying it.

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

MIN_MEMBERS = 2          # one page's tag is that page; a node starts at two
MAX_MEMBERS = 40         # the most-cited members are read; the rest are listed
HEAD = 1200              # characters of each member page's head
TAG_LINES = 6            # plus up to this many of its lines naming the tag
LEDGER = "tag-nodes.json"
SOURCE_DEF = re.compile(r"(?m)^- \[(W?\d+)\][ \t]+(.+)$")


def _title(text: str, record: str) -> str:
    first = text.partition("\n")[0]
    return first[2:].strip() if first.startswith("# ") else Path(record).stem


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
    """Tags of two or more pages whose node is missing or older than its members, the largest first."""
    ledger, found = read_json(state_path(root, LEDGER), {}), members(root)
    waiting = [(-len(records), slug) for slug, records in found.items()
               if len(records) >= MIN_MEMBERS and ledger.get(slug) != _digest(root, records)]
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
    """The page without what code owns: the Tags line, the member list and the Sources."""
    text = tags.without_tags(text)
    return re.split(r"(?m)^## (?:Pages|Sources)[ \t]*$", text)[0].rstrip() + "\n"


def check(root: Path, task: dict, output: dict) -> str:
    """The reviewed node page, or RemError saying why it is refused."""
    path = Path(task["candidate"])
    raw = path.read_text(encoding="utf-8") if path.is_file() else str(output.get("result") or "")
    prose = _prose(raw.strip() + "\n")
    if not re.match(r"# \S", prose) or len(re.findall(r"(?m)^# ", prose)) != 1:
        raise RemError("The tag page needs exactly one title line, first")
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
    used = sorted({n for n in re.findall(r"\[(W?\d+)\](?!\()", prose)}, key=lambda n: int(n.lstrip("W")))
    sources = [f"- [{n}] {task['sources'][n]}" for n in used if n in task["sources"]]
    return page.rstrip("\n") + "\n\n## Pages\n" + "\n".join(links) + "\n\n## Sources\n" + "\n".join(sources) + "\n"


def commit(root: Path, task: dict, prose: str) -> list[str]:
    """Write the node and mark its members read; the caller may hold the maintenance lock."""
    from .page_review import PAGE_REFUSED
    book, ledger = Notebook(root), read_json(state_path(root, LEDGER), {})
    if task["before"] and book.read(task["record"]) != task["before"]:
        return []  # changed since it was read: it waits for the next turn
    page = _page(root, task, prose)
    if len(page) > PAGE_REFUSED:
        raise RemError(f"The tag page is {len(page):,} characters, over the {PAGE_REFUSED:,} limit; keep it shorter")
    changed = [task["record"]] if book.write(task["record"], page) is not False else []
    ledger[task["slug"]] = task["digest"]
    write_json(state_path(root, LEDGER), ledger)
    return changed


def estimate(root: Path, slug: str) -> int:
    """Input tokens one node turn reads, about four characters a token, with no model."""
    with tempfile.TemporaryDirectory() as temporary:
        task = prepare(root, slug, directory=Path(temporary))
        read = sum(len((Path(temporary) / name).read_text()) for name in ("members.md", "sources.md", "node-before.md"))
    return (read + len(task["prompt"]) + 6000) // 4


def dry_run(root: Path) -> dict:
    found, waiting = members(root), candidates(root)
    return {"tags": len(found), "members": {slug: len(records) for slug, records in found.items()},
            "nodes_possible": sum(1 for records in found.values() if len(records) >= MIN_MEMBERS),
            "waiting": len(waiting), "orphans": len(orphans(root)),
            "estimated_input_tokens": sum(estimate(root, slug) for slug in waiting)}


def write_nodes(root: Path, *, limit: int = 50, only: str = "", run=None, ready=None, say=None) -> dict:
    """Write up to `limit` waiting nodes (or only one tag's), one cheap-model turn each."""
    from . import config as rem_config, runner, service
    from .inquiry import stage_config
    settings = stage_config(root, rem_config.read_config(root), "tag-node")
    problem, fix = (ready or runner.ready)(settings)
    if problem:
        raise RemError(f"{problem}; run `{fix}` and try again")
    slugs = [tags.normalise(only)] if only else candidates(root)[:limit]
    record = {"id": "run_" + uuid.uuid4().hex, "phase": "tag", "started_at": service.now().isoformat(),
              "outcome": "running", "items": len(slugs), "written": [], "failed": 0, "errors": [], "usage": {},
              "model": settings["model"]}
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
    return (f"Wrote {len(report['written'])} of {report['items']} tag pages; {report['failed']} failed; "
            f"{report['waiting']} still waiting")
