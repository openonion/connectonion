"""Which pages to investigate next, in what order (#1656).

A category run spends minutes, sometimes forty, per page, so the order is the
product: pages still marked Unknown, the ones with the most mail or sessions
first, because those are the relationships and projects the owner lives in.
The map already counted them; nothing here reads a source.

Left out on purpose:
- the owner's own page -- it has its own reading (`investigate me`), and the
  person path excludes the owner's addresses, so it would read no mail at all;
- addresses the map thinks may be the owner's -- investigated as a person, the
  owner's second Gmail (106 sent, 0 received) would top the list and pull the
  owner's own mail into a page about nobody;
- automated candidates, which are not people;
- a page investigated in the last week, so a daily category run does not
  spend the budget re-reading what it just read.
"""

import re
from datetime import date, datetime, timezone

from .files import Notebook, read_json, state_path

CATEGORIES = {"people": "people/", "projects": "projects/", "orgs": "orgs/", "skills": "skills/catalog/"}
RECENT_DAYS = 7


def last_investigated(status_line: str) -> date | None:
    days = [d for d in re.findall(r"(?<!not )investigated (\d{4}-\d{2}-\d{2})", status_line)]
    return max(date.fromisoformat(d) for d in days) if days else None


def order(root, category: str, today: date | None = None) -> list[dict]:
    if category not in CATEGORIES:
        raise ValueError(category)
    today = today or datetime.now(timezone.utc).date()
    prefix = CATEGORIES[category]
    state = read_json(state_path(root, "map.json"), {})
    weight = {row.get("record"): row.get("mails") or 0 for row in state.get("people", [])}
    weight.update({row.get("record"): row.get("sessions") or 0 for row in state.get("projects", [])})
    weight.update({row.get("record"): len(row.get("people") or []) for row in state.get("orgs", [])})
    excluded = {(state.get("owner") or {}).get("record")}
    excluded |= {row.get("record") for row in state.get("possible_own_addresses", [])}
    excluded |= {row.get("record") for row in state.get("people", [])
                 if row.get("classification") == "automated candidate"}
    rows = []
    for entry in Notebook(root).unfinished(prefix.split("/")[0]):
        path = entry["path"]
        if not path.startswith(prefix) or path in excluded or path.endswith("/index.md"):
            continue
        last = last_investigated(entry["status"])
        rows.append({"path": path, "weight": weight.get(path, 0), "unknown": entry["unknown"],
                     "last_investigated": last.isoformat() if last else None,
                     "recent": bool(last and (today - last).days < RECENT_DAYS)})
    rows.sort(key=lambda row: (row["recent"], -row["weight"], -row["unknown"], row["path"]))
    return rows
