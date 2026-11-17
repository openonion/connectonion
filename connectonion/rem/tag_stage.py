"""`co rem tag`: tag pages from one vocabulary, many pages a turn, reading pages and never sources.

A page waits when its text without the Tags line hashes differently from when it
was last tagged (`.state/tag-pages.json`), so a page that investigation or deepen
rewrote waits again with no wiring of its own. The model returns JSON; code
reviews every tag against the page and writes only the Tags line.
docs/cli/rem-tags.md is the contract; useful_skills/rem-tag/SKILL.md the prompt.
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

BATCH = 20
EXCERPT = 5000
PER_PAGE = 8
NEW_PER_TURN = 8
MARKS = "tag-pages.json"
SHOWN_VOCABULARY = 300


def digest(text: str) -> str:
    return hashlib.sha256(re.sub(r"\n{2,}", "\n\n", tags.without_tags(text)).strip().encode("utf-8")).hexdigest()


def candidates(root: Path) -> list[str]:
    """Written pages waiting to be tagged: never tagged first, then those changed since."""
    from .census import written
    book, marks = Notebook(root), read_json(state_path(root, MARKS), {})
    waiting = []
    for category in tags.TAGGED_KINDS:
        for record in book.list(category):
            text = book.read(record)
            # A stub the map made has nothing to tag yet; once written it waits.
            if (re.search(r"(?m)^## Facts[ \t]*$", text) and written(text)
                    and marks.get(record) != digest(text)):
                waiting.append((record in marks, record))
    return [record for _, record in sorted(waiting)]


def _excerpt(text: str) -> str:
    """The page as the model reads it: no Sources, no stamp, no old Tags line."""
    body = re.split(r"(?m)^## Sources[ \t]*$", tags.without_tags(text))[0]
    body = re.sub(r"(?m)^Investigation:[^\n]*$", "", body).strip()
    return body[:EXCERPT] + ("\n…" if len(body) > EXCERPT else "") + "\n"


def _skill() -> str:
    from .runner import useful_skills_dir
    text = (useful_skills_dir() / "rem-tag" / "SKILL.md").read_text(encoding="utf-8")
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)


def prepare(root: Path, records: list[str], *, directory: Path, native: bool = False) -> dict:
    book = Notebook(root)
    before = {record: book.read(record) for record in records}
    ids = {f"p{i}": record for i, record in enumerate(records, 1)}
    (directory / "pages").mkdir(parents=True, exist_ok=True)
    for page_id, record in ids.items():
        (directory / "pages" / f"{page_id}.md").write_text(_excerpt(before[record]), encoding="utf-8")
    known = tags.vocabulary(root)
    shown = sorted(known.items(), key=lambda item: (-item[1]["count"], item[0]))[:SHOWN_VOCABULARY]
    write_json(directory / "vocabulary.json", [{"tag": slug, **entry} for slug, entry in shown], readable=True)
    output = directory / "candidate.json"
    task = (f"<co_rem_task> Tag {len(ids)} pages: {', '.join(f'pages/{page_id}.md' for page_id in ids)}. "
            f"The vocabulary is {directory / 'vocabulary.json'}. Write the JSON object to {output}. </co_rem_task>")
    if native:
        prompt = "/rem-tag " + task
    else:
        (directory / "rem-tag.md").write_text(_skill(), encoding="utf-8")
        prompt = f"Read {directory / 'rem-tag.md'}: it is the skill for this task, and follow it.\n" + task
    return {"records": records, "ids": ids, "before": before, "candidate": str(output), "prompt": prompt}


def _plain(text: str) -> str:
    """Case, whitespace and Markdown link targets do not count when a span is looked for."""
    return " ".join(re.sub(r"\]\([^)]*\)", "]", text).split()).casefold()


def _citation(page: str, evidence: str) -> str:
    cited = tags.CITE.findall(evidence)
    if cited:
        return cited[0]
    line = next((line for line in page.splitlines() if _plain(evidence) in _plain(line)), "")
    found = tags.CITE.findall(line)
    return found[0] if found else ""


def _names(slug: str, entry: dict) -> list[str]:
    return [tags.normalise(name) for name in (slug, entry.get("label", ""), *entry.get("aliases", [])) if name]


def _named(evidence: str, slug: str, entry: dict) -> bool:
    plain = tags.normalise(re.sub(r"\]\([^)]*\)", "]", evidence))
    return any(name and all(part in plain for part in name.split("-")) for name in _names(slug, entry))


def _person_names(root: Path) -> set[str]:
    book = Notebook(root)
    names = {Path(record).stem for record in book.list("people")}
    names.update(tags.normalise(book.read(record).partition("\n")[0].lstrip("# ")) for record in book.list("people"))
    return names


def _new_entries(root: Path, proposals, known: dict) -> tuple[dict, dict]:
    """(accepted new tags, {slug: why refused}); a proposal naming an existing tag is that tag."""
    accepted, refused, people = {}, {}, _person_names(root)
    for row in proposals if isinstance(proposals, list) else []:
        if not isinstance(row, dict):
            continue
        slug = tags.normalise(row.get("tag", ""))
        if not slug or tags.resolve(known, slug) or slug in accepted:
            continue
        label, kind = str(row.get("label") or "").strip(), row.get("kind")
        if (not tags.SLUG.fullmatch(slug) or kind not in tags.TAG_KINDS or not label or slug in tags.CATCH_ALL
                or slug in people or tags.normalise(label) in people):
            refused[slug] = "bad new tag"
        elif len(accepted) >= NEW_PER_TURN:
            refused[slug] = "bad new tag: past the turn's cap of new tags"
        else:
            aliases = [tags.normalise(a) for a in row.get("aliases", []) if isinstance(a, str) and tags.normalise(a)]
            accepted[slug] = {"label": label[:60], "kind": kind, "aliases": aliases[:5]}
    return accepted, refused


def _review(page: str, rows, known: dict, new: dict, refused_new: dict) -> tuple[list[dict], list[dict]]:
    """(accepted {tag, citation} rows, refused {tag, reason} rows) for one page."""
    accepted, refused, both = [], [], {**known, **new}
    body = _plain(re.split(r"(?m)^## Sources[ \t]*$", tags.without_tags(page))[0])
    for row in rows if isinstance(rows, list) else []:
        given = tags.normalise(row.get("tag", "")) if isinstance(row, dict) else ""
        evidence = str(row.get("evidence") or "") if isinstance(row, dict) else ""
        slug = tags.resolve(both, given) if given else None
        reason = (refused_new.get(given) or ("not in vocabulary" if slug is None else
                  "no evidence" if not evidence.strip() or _plain(evidence) not in body else
                  "not named" if both[slug]["kind"] in tags.NAMED_KINDS and not _named(evidence, slug, both[slug]) else
                  "too many" if len(accepted) >= PER_PAGE else ""))
        if slug in [found["tag"] for found in accepted]:
            continue
        if reason:
            refused.append({"tag": given or "?", "reason": reason})
        else:
            accepted.append({"tag": slug, "citation": _citation(page, evidence)})
    return accepted, refused


def _facts(page: str) -> str:
    found = re.search(r"(?ms)^## Facts[ \t]*\n(.*?)(?=^#{1,2} |\Z)", tags.without_tags(page))
    return found[1] if found else ""


def _team_named(facts: str, slug: str) -> bool:
    """`9900-f13-cake` is named when the Facts hold its course number and each other part as a word."""
    words = tags.normalise(re.sub(r"\]\([^)]*\)", "]", facts)).split("-")
    course, *parts = slug.split("-")
    return bool(parts) and any(course in word for word in words) and all(part in words for part in parts)


def _line_citation(facts: str, needle) -> str:
    line = next((line for line in facts.splitlines() if needle(line)), "")
    found = tags.CITE.findall(line)
    return found[0] if found else ""


def _implied(record: str, page: str, known: dict, accepted: list[dict]) -> list[dict]:
    """Tags the page carries by rule, added by code whatever the reply said (docs/cli/rem-tags.md):
    an organisation page its own tag, a page its Facts' organisations, a known course or team named
    in its Facts (`COMP9900` names `9900`), and the course of every team tag."""
    facts, have = _facts(page), {row["tag"] for row in accepted}
    rows = []

    def add(slug, citation, reason):
        if slug in known and slug not in have:
            have.add(slug)
            rows.append({"tag": slug, "citation": citation, "reason": reason})
    if record.startswith("orgs/"):
        add(tags.resolve(known, Path(record).stem), "", "the organisation's own tag")
    for stem in tags.org_links(page):
        add(tags.resolve(known, stem), _line_citation(facts, lambda line, stem=stem: f"orgs/{stem}" in line.lower()),
            "an organisation in its Facts")
    for slug, entry in known.items():
        if entry["kind"] == "team" and _team_named(facts, slug):
            add(slug, _line_citation(facts, lambda line, slug=slug: _team_named(line, slug)), "a team named in its Facts")
    words = tags.normalise(re.sub(r"\]\([^)]*\)", "]", facts)).split("-")
    for slug, entry in known.items():
        if entry["kind"] == "course" and any(re.fullmatch(rf"[a-z]*{re.escape(slug)}", word) for word in words):
            add(slug, _line_citation(facts, lambda line, slug=slug: slug in line), "a course named in its Facts")
    for slug in list(have):
        course = slug.split("-")[0]
        if known.get(slug, {}).get("kind") == "team" and known.get(course, {}).get("kind") == "course":
            add(course, "", "the course of its team")
    return rows


def check(root: Path, task: dict, output: dict) -> dict:
    """The reviewed plan: each page's accepted tags, the new vocabulary entries used, and every refusal."""
    reply = re.sub(r"\A```(?:json)?\s*\n?(.*?)\n?```\Z", r"\1", str(output.get("result") or "").strip(), flags=re.S)
    value = json.loads(reply)
    pages = value.get("pages") if isinstance(value, dict) else None
    if (not isinstance(pages, list) or any(not isinstance(row, dict) for row in pages)
            or sorted(str(row.get("id")) for row in pages) != sorted(task["ids"])):
        raise RemError("The tag reply must return every page id exactly once: " + ", ".join(task["ids"]))
    known = tags.vocabulary(root)
    new, refused_new = _new_entries(root, value.get("new_tags"), known)
    plan = {"pages": {}, "new": {}, "refused": [], "added": [], "usage": output.get("usage") or {}}
    for row in pages:
        record = task["ids"][row["id"]]
        accepted, refused = _review(task["before"][record], row.get("tags"), known, new, refused_new)
        implied = _implied(record, task["before"][record], {**known, **new}, accepted)
        plan["added"] += [{"record": record, **item} for item in implied]
        accepted += [{"tag": item["tag"], "citation": item["citation"]} for item in implied]
        plan["pages"][record] = {"before": task["before"][record], "rows": accepted}
        plan["refused"] += [{"record": record, **item} for item in refused]
        plan["new"].update({row["tag"]: new[row["tag"]] for row in accepted if row["tag"] in new})
    return plan


def promote(root: Path, plan: dict) -> list[str]:
    """Write each page's Tags line and nothing else; the caller holds the maintenance lock."""
    book, marks, changed = Notebook(root), read_json(state_path(root, MARKS), {}), []
    if plan["new"]:
        tags.save(root, {**tags.entries(root), **plan["new"]})
    for record, entry in plan["pages"].items():
        current = book.read(record)
        if current != entry["before"]:
            continue   # changed since it was read: it waits for the next turn
        after = tags.with_tags(current, entry["rows"])
        if not tags.only_tags_changed(current, after):
            raise RemError(f"{record}: tagging would change more than its Tags line; nothing written")
        if after != current:
            book.write(record, after)
            changed.append(record)
        marks[record] = digest(after)
    write_json(state_path(root, MARKS), marks)
    return changed


def _turn(root: Path, records: list[str], settings: dict, run) -> dict:
    from . import runner
    tasks_dir = state_path(root, "tasks")
    tasks_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="tag-", dir=tasks_dir) as temporary:
        directory = Path(temporary)
        task = prepare(root, records, directory=directory)
        envelope = run(directory, task["prompt"], settings, "tag")
        candidate = Path(task["candidate"])
        result = candidate.read_text(encoding="utf-8") if candidate.is_file() else envelope.get("result", "")
        return check(root, task, {"result": result, "usage": envelope.get("usage")})


def tag_pages(root: Path, *, limit: int = 200, run=None, say=None) -> dict:
    """Tag up to `limit` waiting pages, BATCH a turn; a refused or failed turn leaves its pages waiting."""
    from . import config as rem_config, runner, service
    from .inquiry import stage_config
    settings = stage_config(root, rem_config.read_config(root), "tag")
    problem, fix = runner.ready(settings)
    if problem:
        raise RemError(f"{problem}; run `{fix}` and tag again")
    rows, started = candidates(root)[:limit], time.monotonic()
    record = {"id": "run_" + uuid.uuid4().hex, "phase": "tag", "started_at": service.now().isoformat(),
              "outcome": "running", "runner_attempts": 0, "changed": [], "items": len(rows), "tagged": 0,
              "failed": 0, "refused": [], "errors": [], "usage": {}, "model": settings["model"]}
    path = state_path(root, f"runs/{record['id']}.json")
    for offset in range(0, len(rows), BATCH):
        chosen = rows[offset:offset + BATCH]
        record["runner_attempts"] += 1
        try:
            plan = _turn(root, chosen, settings, run or runner.run_task)
        except (runner.RunFailed, RemError, json.JSONDecodeError) as error:
            record["failed"] += len(chosen)
            record["errors"].append(str(error)[:300])
            record["usage"] = _add(record["usage"], getattr(error, "usage", None))
            if say:
                say(f"Failed {len(chosen)} pages: {str(error)[:200]}")
            continue
        with maintenance_lock(root, wait=60):
            record["changed"] += promote(root, plan)
        record["tagged"] += len(plan["pages"])
        record["refused"] += plan["refused"]
        record["usage"] = _add(record["usage"], plan["usage"])
        if say:
            say(f"Tagged {record['tagged']} of {len(rows)} pages; {len(plan['refused'])} tags refused in this turn")
        write_json(path, record)
    record.update(outcome="failed" if record["failed"] and not record["tagged"] else
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
    return (f"Tagged {report['tagged']} of {report['items']} pages ({len(report['changed'])} changed); "
            f"{len(report['refused'])} tags refused; {report['failed']} pages failed; {report['waiting']} still waiting")
