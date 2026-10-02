"""What is in the notebook, counted once for every screen (#2008).

The reader said "174 with findings" when three pages had been written -- a
mapped skill page shows its description, a mapped project page its paths, and
the page's own JavaScript took both for findings. People were 76 on one screen
and 82 on another, skills 159 and 152, because each screen chose for itself
which pages to leave out. `co rem status` and the reader now both ask here:

- counted: people, projects, organisations and skill catalog pages; not the
  pages held for review, not services still on a people page, not the skills
  index, and one page per skill title;
- written: the page's status line no longer says "not investigated yet" (a
  merge keeps the investigated page's status, so a merged page is written
  exactly when what it kept was);
- last activity: the page's own dates (last contact, last session, last
  investigation), never the file's mtime, which is when the last map rewrote it.
"""

from __future__ import annotations

import re
from pathlib import Path

from .files import Notebook, read_json, state_path

CATEGORIES = ("people", "projects", "orgs", "skills")
DAY = r"(\d{4}-\d{2}-\d{2})"
# Dates that say when something happened, as each kind of page writes them.
ACTIVITY = re.compile(
    rf"\bLast contact:\s*{DAY}"                       # an investigated person's lead
    rf"|\blast:\s*{DAY}"                              # a mapped person's History
    rf"|^- Last seen:\s*{DAY}"                        # a project's last session
    rf"|\blast on\s*{DAY}", re.I | re.M)               # a skill's last invocation
# When the notebook last worked on the page: the date to show only when the page names no activity.
WORKED = re.compile(rf"^Investigation:.*?\b(?:investigated|written|updated|quick sample)\s+{DAY}", re.M)


def written(page: str) -> bool:
    """Someone or a model wrote it: not map output alone."""
    from .merge import mapped_only
    return not mapped_only(page)


def last_activity(page: str) -> str:
    """The latest date the page itself gives for activity, else its last investigation, or ''."""
    days = [day for match in ACTIVITY.finditer(page) for day in match.groups() if day]
    return max(days, default="") or max(WORKED.findall(page), default="")


def _counted(record: str) -> bool:
    category = record.split("/")[0]
    if category == "skills":
        return record.startswith("skills/catalog/") and record != "skills/catalog/index.md"
    return category in CATEGORIES


def pages(root: Path) -> dict:
    """{record: {category, written, last, held, service, duplicate}} for every counted page."""
    from .map import needs_review, service_page
    notebook = Notebook(root)
    state = read_json(state_path(root, "map.json"), {})
    # Rows with an address: the owner's row names only the record.
    rows = {row.get("record"): row for row in state.get("people", []) if row.get("record") and row.get("address")}
    automated = {row["address"].casefold() for row in state.get("automated_correspondents", [])
                 if row.get("address")}
    owner = (state.get("owner") or {}).get("record")
    people = {person["path"]: person for person in notebook.people()}
    held, titles, found = needs_review(root), set(), {}
    for record in notebook.list():
        if not _counted(record):
            continue
        text = notebook.read(record)
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), record)
        category = record.split("/")[0]
        person = people.get(record)
        duplicate = category == "skills" and title.casefold() in titles
        if category == "skills":
            titles.add(title.casefold())
        found[record] = {
            "category": category, "written": written(text), "last": last_activity(text),
            "held": record in held, "duplicate": duplicate,
            "service": bool(person) and record != owner and not written(text)
            and service_page(title, person["emails"], rows.get(record), automated)}
    return found


def listed(entry: dict) -> bool:
    return not (entry["held"] or entry["service"] or entry["duplicate"])


def counts(root: Path, found: dict | None = None) -> dict:
    """Pages per category: mapped (every listed page) and written."""
    found = pages(root) if found is None else found
    result = {category: {"mapped": 0, "written": 0} for category in CATEGORIES}
    for entry in found.values():
        if listed(entry):
            result[entry["category"]]["mapped"] += 1
            result[entry["category"]]["written"] += entry["written"]
    return result
