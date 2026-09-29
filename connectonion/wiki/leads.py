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
from .scan import home_or_above

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
        # A page for the home directory (an older map made one) holds every
        # folder, so it would be the lead for every session nothing else covers.
        pages = {record: roots for record, roots in pages.items()
                 if not (roots and all(home_or_above(root) for root in roots))}
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
        roots = project_paths(notebook.read(record))
        if roots and all(home_or_above(root) for root in roots):
            continue  # its title is the user's name, which is in every path
        title = next((line[2:].strip() for line in notebook.read(record).splitlines() if line.startswith("# ")), "")
        hits = _named(title, text)
        if hits and all(record != lead for _, lead in leads):
            leads.append((hits, record))
    leads.sort(key=lambda lead: (-lead[0], lead[1]))
    return [record for _, record in leads[:MAX_LEADS]]
