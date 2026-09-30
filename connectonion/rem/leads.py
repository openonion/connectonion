"""Which existing pages a maintenance batch most likely concerns, found without a model.

A real maintenance pass on a 1,187-page notebook spent six of its sixteen turns
running `rg` over every page to find where its material belonged, each turn
re-sending the whole context, and timed out at twenty minutes. The map already
knows what a script can know: a coding session names the directory it ran in,
which is on a project page's Paths; and a person is named in the material by a
title or alias the roster holds. Those are handed over as the place to start.
Judgement -- whether "Dora" here is that Dora -- stays with the model.
"""

import re
from pathlib import Path

from .files import Notebook, read_json, state_path
from .investigate import project_paths

MAX_LEADS = 15


def _under(path: str, roots: list[str]) -> bool:
    return any(path == root or path.startswith(root.rstrip("/") + "/") for root in roots)


def _named(name: str, text: str) -> int:
    """How often a title or alias appears as a word. Short Latin names must match
    case exactly ("One" the project, not "one" the word); Chinese names are
    usually two characters, so they get their own floor."""
    if "@" in name or len(name) < (3 if name.isascii() else 2):
        return 0
    flags = re.I if len(name) >= 4 or not name.isascii() else 0
    return len(re.findall(rf"(?<![\w@./-]){re.escape(name)}(?![\w@-])", text, flags))


def _not_leads(notebook: Notebook) -> set:
    """The owner's page and pages that may be the owner's: every session is the
    owner's own, so their name is in all of it and says nothing about where a
    batch belongs. Automated senders are not people."""
    state = read_json(state_path(notebook.root, "map.json"), {})
    skip = {(state.get("owner") or {}).get("record")}
    skip |= {row.get("record") for row in state.get("possible_own_addresses", [])}
    skip |= {row.get("record") for row in state.get("people", [])
             if row.get("classification") == "automated candidate"}
    return skip


def page_leads(notebook: Notebook, items: list[dict]) -> list[str]:
    text = "\n".join(str(item.get("text", "")) for item in items)
    skip = _not_leads(notebook)
    directories = {str(item["project"]) for item in items if item.get("project")}
    leads = []
    if directories:
        pages = {record: project_paths(notebook.read(record)) for record in notebook.list("projects")}
        for directory in directories:
            # The most specific project holding this folder, not every ancestor:
            # a page for the home directory holds every session there is.
            depth = {record: max(len(root) for root in roots if _under(directory, [root]))
                     for record, roots in pages.items() if roots and _under(directory, roots)}
            if depth:
                deepest = max(depth.values())
                leads += [(10_000, record) for record, size in depth.items() if size == deepest]
    for person in notebook.people():
        if person["path"] in skip:
            continue
        hits = sum(_named(name, text) for name in {person.get("title", ""), *person.get("aliases", [])})
        if hits:
            leads.append((hits, person["path"]))
    for record in notebook.list("projects"):
        title = next((line[2:].strip() for line in notebook.read(record).splitlines() if line.startswith("# ")), "")
        hits = _named(title, text)
        if hits and all(record != lead for _, lead in leads):
            leads.append((hits, record))
    leads.sort(key=lambda lead: (-lead[0], lead[1]))
    return [record for _, record in leads[:MAX_LEADS]]


def named_projects(notes: str) -> list[str]:
    """The project names an extraction wrote under `## Projects` (`- **Name** — …`)."""
    section = re.search(r"(?ms)^## Projects\s*$(.*?)(?=^## |\Z)", notes)
    return list(dict.fromkeys(m.strip() for m in re.findall(r"(?m)^\s*-\s+\*\*([^*]+)\*\*", section[1])))\
        if section else []


def note_leads(notebook: Notebook, notes: str) -> tuple[list[str], list[str]]:
    """Project pages the extraction names, and the names no page answers to.

    Page leads come from the raw material, by the folder a session ran in or a
    page's title in the text. Sessions typed in the workspace root match no
    folder, and "the Wiki/REM work" names no title: ten of eleven project notes
    in one sync reached no page and the run said nothing (#1985). The notes
    name the project; match that name to a page's title or its folders' names.
    """
    pages = {}
    for record in notebook.list("projects"):
        text = notebook.read(record)
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")
        keys = {title.casefold(), *(Path(p).name.casefold() for p in project_paths(text))}
        pages[record] = {k for k in keys if k}
    found, unrouted = [], []
    for name in named_projects(notes):
        matches = [record for record, keys in pages.items() if name.casefold() in keys]
        if matches:
            found += [m for m in matches if m not in found]
        else:
            unrouted.append(name)
    return found, unrouted


def nothing_new(notebook: Notebook, record: str, items: list[dict]) -> bool:
    """Whether the page has already read every message here that points at it.

    A page turn re-sends the page and the material, about 110k tokens, and two
    of three leads in a measured batch changed nothing (#1846). What points at a
    page is what made it a lead: a message typed in its folders, or one naming
    it. The page has read a message it cites, and a project page has read the
    messages `co rem projects write` wrote it from. One unread message, or none
    pointing at it, and the page gets its turn.
    """
    from .page_review import SOURCE_ID
    from .project_material import page_state, stored
    text = notebook.read(record)
    roots = project_paths(text) if record.startswith("projects/") else []
    person = next((p for p in notebook.people() if p["path"] == record), {})
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")
    names = {person.get("title", title), *person.get("aliases", [])}
    pointing = {source for item in items
                if (item.get("project") and _under(str(item["project"]), roots))
                or any(_named(name, str(item.get("text", ""))) for name in names)
                for source in item.get("sources") or [item.get("source")] if source}
    read = {source.rstrip(".,;") for source in SOURCE_ID.findall(text)}
    if roots:
        through = page_state(notebook.root, record).get("written_through") or ""
        read |= {m["source"] for m in stored(notebook.root, record) if m["timestamp"] <= through}
    return bool(pointing) and pointing <= read
