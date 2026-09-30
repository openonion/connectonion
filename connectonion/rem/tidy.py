"""Tidy a notebook an older version made, by today's rules (#1999, #2008).

Maps get better and the pages an older one made stay. The owner's upgraded
notebook kept services as people (Apple ID, notify@x.com, GitHub's unsub+
reply addresses), two of the owner's own addresses queued as people, three
pairs of pages for one skill, and old pages carrying `web: not searched` and
`investigation:coverage` citations. Every map and every sync calls `tidy`
first. It is idempotent and calls no model. Nothing is deleted: pages move to
`.state/archived/` (folded ones leave an alias, as `merge.merge_into` does),
and every action -- each removed line with its text -- is appended to
`.state/tidy.json`. A page someone investigated is never moved or folded.
"""

from __future__ import annotations

import re
from contextlib import nullcontext
from datetime import date
from pathlib import Path

from .files import Notebook, maintenance_lock, read_json, state_path, write_json

LOG = "tidy.json"
WEB_LINE = re.compile(r"^\s*- web: not searched\b.*$")
COVERAGE = re.compile(r"^\s*- \[(W?\d+)\] investigation:coverage\b.*$")
# The runner's own deterministic citation for a project's empty session window
# (runner._project_window_notice) backs a fact it states; only the model's kept.
RUNNER_COVERAGE = "source-collection record for this investigation"


def tidy(root: Path, *, lock_held: bool = False) -> dict:
    """Tidy under the notebook lock; returns {action: [pages]} for what changed."""
    root = Path(root)
    if not (root / ".state").is_dir():
        return {}
    with nullcontext() if lock_held else maintenance_lock(root):
        notebook, actions = Notebook(root), []
        state = read_json(state_path(root, "map.json"), {})
        actions += _services(notebook, state)
        actions += _own_addresses(notebook, state)
        actions += _skills(notebook)
        actions += _lines(notebook)
        if not actions:
            return {}
        log = read_json(state_path(root, LOG), [])
        write_json(state_path(root, LOG), log + [{"date": date.today().isoformat(), **action} for action in actions])
        summary = {}
        for action in actions:
            summary.setdefault(action["action"], []).append(action["page"])
        return {key: sorted(set(pages)) for key, pages in summary.items()}


def _archive(notebook: Notebook, record: str) -> str:
    target = notebook.root / ".state" / "archived" / record
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook.path(record).replace(target)
    return f".state/archived/{record}"


def _services(notebook: Notebook, state: dict) -> list[dict]:
    """People pages for services and automated senders, never investigated: archived."""
    from .census import written
    from .map import service_page
    rows = {row.get("record"): row for row in state.get("people", []) if row.get("record")}
    automated = {row["address"].casefold() for row in state.get("automated_correspondents", []) if row.get("address")}
    owner = (state.get("owner") or {}).get("record")
    moved = []
    for person in notebook.people():
        record = person["path"]
        if record == owner or written(notebook.read(record)):
            continue
        if service_page(person["title"], person["emails"], rows.get(record), automated):
            moved.append({"action": "archived service", "page": record, "archived": _archive(notebook, record)})
    return moved


def _own_addresses(notebook: Notebook, state: dict) -> list[dict]:
    """The owner's own addresses on pages of their own: folded into the owner's page.

    Own means confirmed (already one of the owner's addresses) or clearly own:
    never replied to, and carrying the owner's name or confirmed address
    (`map.looks_own`). Also narrows the saved "Possibly yours" list the same way.
    """
    from .census import written
    from .map import looks_own, owner_tokens
    owner = state.get("owner") or {}
    record = owner.get("record")
    if not record or not notebook.path(record).is_file():
        return []
    title = notebook.read(record).split("\n", 1)[0].lstrip("# ").strip()
    confirmed = {address.casefold() for address in owner.get("addresses") or []}
    tokens = owner_tokens(confirmed, "" if "@" in title or title == "Account owner" else title)
    rows = {row.get("record"): row for row in state.get("people", []) if row.get("record")}
    folded, added = [], []
    for person in notebook.people():
        page, emails = person["path"], {email.casefold() for email in person["emails"]}
        if page == record or not emails or written(notebook.read(page)):
            continue
        row = rows.get(page) or {}
        group = [{"address": email, "name": row.get("name", ""), "sent": row.get("sent", 0),
                  "received": row.get("received", 1)} for email in sorted(emails)]
        if emails <= confirmed or (tokens and len(group) == 1 and looks_own(group, tokens)):
            _fold_owner(notebook, record, page, sorted(emails))
            folded.append({"action": "folded into the owner's page", "page": page, "into": record,
                           "addresses": sorted(emails), "archived": f".state/archived/{page}"})
            added += sorted(emails - confirmed)
    asked = state.get("possible_own_addresses") or []
    kept = [row for row in asked if row.get("address", "").casefold() not in confirmed | set(added)
            and (not tokens or looks_own([{**rows.get(row.get("record"), {}), **row, "received": 0}], tokens))]
    if added or kept != asked:
        owner["addresses"] = sorted(confirmed | set(added))
        state.update(owner=owner, possible_own_addresses=kept)
        write_json(state_path(notebook.root, "map.json"), state)
    return folded


def _fold_owner(notebook: Notebook, owner: str, page: str, emails: list[str]) -> None:
    """The addresses join the owner's contact lines; the page, map output only, is archived
    with an alias. Its correspondent lines ("classification unassessed", a
    mail count as someone else) would say the wrong thing on the owner's page."""
    from .skill_map import _alias
    text = notebook.read(owner)
    for label in ("Email", "Handles", "Also known as"):
        def extend(match):
            known = [part.strip() for part in match[2].split(",") if part.strip() and part.strip() != "Unknown"]
            return match[1] + ", ".join(dict.fromkeys([*known, *emails]))
        text = re.sub(rf"^(- {label}: )(.*)$", extend, text, count=1, flags=re.M)
    notebook.write(owner, text)
    _archive(notebook, page)
    _alias(notebook, page, owner, "the owner's own address")


def _skills(notebook: Notebook) -> list[dict]:
    """Two catalog pages for one skill: the page named by its folder folds into the named one.

    Read from the pages, not from a scan, so it needs no working directory: a
    page titled `changxing-nonfiction-refine` joins `nonfiction-refine` when
    the two describe the skill the same way or list files with the same bytes
    (`skill_map._join_renamed` keeps a fresh map from making the pair).
    """
    from .census import written
    from .merge import merge_into
    from .skill_map import _title
    pages = {record: notebook.read(record) for record in notebook.list("skills")
             if record.startswith("skills/catalog/") and record != "skills/catalog/index.md"}
    titles = {_title(text).casefold(): record for record, text in pages.items()}
    folded = []
    for record, text in pages.items():
        title = _title(text).casefold()
        target = next((titles[name] for name in titles if name != title and title.endswith("-" + name)), None)
        if not target or written(text) or not _same_skill(text, pages[target]):
            continue
        merge_into(notebook, target, record, "same skill, named by its folder")
        folded.append({"action": "folded duplicate skill", "page": record, "into": target,
                       "archived": f".state/archived/{record}"})
    return folded


def _described(text: str) -> str:
    match = re.search(r"^## What it does\n(.+)$", text, re.M)
    value = match.group(1).strip() if match else ""
    return "" if value.startswith("Unknown") else value


def _same_skill(one: str, other: str) -> bool:
    from .skill_map import _listed_files

    def contents(text):
        return {Path(path).read_bytes() for path in _listed_files(text) if Path(path).is_file()}
    return bool(_described(one) and _described(one) == _described(other)) or bool(contents(one) & contents(other))


def _lines(notebook: Notebook) -> list[dict]:
    """Old `web: not searched` lines and model-written coverage citations, removed line by line."""
    removed = []
    for record in notebook.list():
        text = notebook.read(record)
        if "web: not searched" not in text and "investigation:coverage" not in text:
            continue
        keys = [match[1] for match in map(COVERAGE.match, text.split("\n"))
                if match and RUNNER_COVERAGE not in match[0]]
        kept, gone = [], []
        for line in text.split("\n"):
            match = COVERAGE.match(line)
            if WEB_LINE.match(line) or (match and match[1] in keys):
                gone.append(line)
                continue
            for key in keys:
                line = re.sub(rf" ?\[{key}\](?!\()", "", line)
            kept.append(line)
        if gone:
            notebook.write(record, "\n".join(kept))
            removed += [{"action": "removed line", "page": record, "line": line} for line in gone]
    return removed
