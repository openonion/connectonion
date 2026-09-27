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

from .files import Notebook
from .investigate import project_paths

MAX_LEADS = 15
# A name shorter than this is too likely to be part of another word ("Al" in
# "always"); a Chinese name is usually two characters, so it gets its own floor.


def _under(path: str, roots: list[str]) -> bool:
    return any(path == root or path.startswith(root.rstrip("/") + "/") for root in roots)


def page_leads(notebook: Notebook, items: list[dict]) -> list[str]:
    text = "\n".join(str(item.get("text", "")) for item in items)
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
        names = {person.get("title", ""), *person.get("aliases", [])}
        hits = sum(len(re.findall(rf"(?<![\w@.]){re.escape(name)}(?![\w@])", text, re.I))
                   for name in names if "@" not in name and len(name) >= (3 if name.isascii() else 2))
        if hits:
            leads.append((hits, person["path"]))
    leads.sort(key=lambda lead: (-lead[0], lead[1]))
    return [record for _, record in leads[:MAX_LEADS]]
