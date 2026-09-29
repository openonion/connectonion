"""Which people to investigate next, and over which window: recent correspondents first (#1943 stage 3, #1723).

Investigating one person is `investigate.investigate`: its script gathers the
person's mail (the saved archive first, then the server for what is missing,
bodies and attachments) before any model starts, and since #1942 the one
investigate turn searches that material as files instead of digesting it
(#1850). What was missing is the order and the size of the work:

- **Order.** The busiest person first never fit a day's calls (#1723). The
  person the owner wrote to last is what is useful now, so people are ordered
  by their last mail, the last `recent_days` first.
- **Only what is new.** A page investigated before is not read again from the
  start: when mail with the person arrived after the page was last
  investigated, the window is the days since then, so the gather and the turn
  carry only the new mail. A page with nothing new waits.
- **What is new since the last run** is one metadata listing per mailbox
  (`correspondents_since`), not one server search per person.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import Notebook, WikiError, read_json, state_path, write_json
from .source import timestamp

# Correspondents of the last two weeks are investigated before anyone older (owner, 2026-09-30).
RECENT_DAYS = 14
# The window a page is read over when it has not been investigated from new mail.
FIRST_WINDOW_DAYS = 150
# Measured on the owner's machine, 2026-09-30 (docs/cli/wiki-people-pages.md):
# one full investigation of a 157-mail person, the #1850 baseline subject.
MEASURED = {"mails": 157, "input_tokens": 1_931_414, "minutes": 15}
# A mail still arriving at the last listing carries a time before it.
OVERLAP = timedelta(hours=1)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _map(root: Path) -> dict:
    return read_json(state_path(root, "map.json"), {})


def _excluded(state: dict) -> set:
    """The same people the investigate queue leaves out (queue.order)."""
    excluded = {(state.get("owner") or {}).get("record")}
    excluded |= {row.get("record") for row in state.get("possible_own_addresses", [])}
    excluded |= {row.get("record") for row in state.get("people", [])
                 if row.get("classification") == "automated candidate"}
    return excluded


def _stamp(value) -> datetime | None:
    value = str(value or "")
    if not value:
        return None
    try:
        return timestamp(value if "T" in value else value + "T00:00:00+00:00")
    except WikiError:
        return None


def _activity(root: Path) -> dict:
    return read_json(state_path(root, "people/activity.json"), {})


def last_activity(root: Path, record: str, *, state: dict | None = None, activity: dict | None = None) -> str:
    """The newest mail with this person the notebook knows of: the map's, or a later listing's."""
    state = _map(root) if state is None else state
    activity = _activity(root) if activity is None else activity
    row = next((r for r in state.get("people", []) if r.get("record") == record), {})
    stamps = [s for s in (_stamp(row.get("last")), _stamp(activity.get(record))) if s]
    return max(stamps).isoformat() if stamps else ""


def queue(root: Path, *, recent_days: int = RECENT_DAYS, now: datetime | None = None, since: str = "") -> list[dict]:
    """People to investigate: the last `recent_days` first, then older, newest first in each.

    `mode` is "update" when mail arrived after the page was last investigated
    (its window is the days since then) and "full" for an unfinished page not
    investigated in the last week. `since` keeps only people whose last mail
    is after it: what the daily round's later runs follow.
    """
    from .queue import last_investigated, order
    now = now or datetime.now(timezone.utc)
    today = now.date()
    cutoff = (now - timedelta(days=recent_days)).isoformat()
    state, activity = _map(root), _activity(root)
    done = read_json(state_path(root, "people/investigated.json"), {})
    excluded = _excluded(state)
    unfinished = {row["path"]: row for row in order(root, "people")}
    mails = {row.get("record"): row.get("mails") or 0 for row in state.get("people", [])}
    notebook = Notebook(root)
    rows = []
    for record in notebook.list("people"):
        if record in excluded or record.endswith("/index.md"):
            continue
        last = last_activity(root, record, state=state, activity=activity)
        status = next((line for line in notebook.read(record).splitlines() if line.startswith("Investigation:")), "")
        investigated = last_investigated(status)
        # The exact time this code last investigated the page, when it did: the
        # status line keeps only a date, and mail later that day is still new.
        at = _stamp(done.get(record)) or (datetime.combine(investigated, datetime.max.time(), timezone.utc)
                                          if investigated else None)
        if at and last and _stamp(last) > at:
            mode, window = "update", max(1, (today - at.date()).days + 1)
        elif record in unfinished and not unfinished[record]["recent"]:
            mode, window = "full", FIRST_WINDOW_DAYS
        else:
            continue
        if since and not last > since:
            continue
        rows.append({"record": record, "mode": mode, "days": window, "last_activity": last,
                     "recent": last >= cutoff, "mails": mails.get(record, 0),
                     "last_investigated": investigated.isoformat() if investigated else None})
    return sorted(rows, key=lambda r: (not r["recent"], -(_stamp(r["last_activity"]) or _EPOCH).timestamp(),
                                       r["record"]))


def estimate(rows: list[dict]) -> dict:
    """What investigating these people will cost, stated before anything is read or spent.

    One model call a person; the mail the map counted is what a full
    investigation reads (an update reads only its window). The measured figure
    is what one full investigation cost on the owner's machine.
    """
    return {"people": len(rows), "model_calls": len(rows), "recent": sum(1 for r in rows if r["recent"]),
            "updates": sum(1 for r in rows if r["mode"] == "update"),
            "mails_mapped": sum(r["mails"] for r in rows if r["mode"] == "full"), "measured": MEASURED}


def handles(root: Path, record: str) -> tuple[str, list[str]]:
    """The subject's title and every name and address the notebook has for them."""
    notebook = Notebook(root)
    text = notebook.read(record)
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), record)
    person = next((p for p in notebook.people() if p["path"] == record), {})
    row = next((r for r in _map(root).get("people", []) if r.get("record") == record), {})
    known = [*person.get("emails", []), *row.get("addresses", []), *person.get("aliases", [])]
    return title, list(dict.fromkeys([*known, title.split(" (")[0]]))


def investigate_person(root: Path, row: dict, *, clients: dict, subscriptions: dict, max_calls=None,
                       progress=None, stage_progress=None) -> dict:
    """One person through the investigation #1942 made: gathered by our code, searched by one turn."""
    from . import investigate as investigation
    title, names = handles(root, row["record"])
    started = datetime.now(timezone.utc)
    result = investigation.investigate(root, row["record"], title, names, days=row["days"], clients=clients,
                                       subscriptions=subscriptions, max_calls=max_calls, progress=progress,
                                       stage_progress=stage_progress)
    mark_investigated(root, row["record"], started)
    return result


def mark_investigated(root: Path, record: str, when: datetime) -> None:
    """When the gather for this page started: mail after it is new for the next run."""
    folder = state_path(root, "people")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    done = read_json(folder / "investigated.json", {})
    done[record] = when.isoformat()
    write_json(folder / "investigated.json", done)


def correspondents_since(root: Path, clients: dict, *, since: datetime, now: datetime | None = None) -> dict:
    """Which mapped people have mail since the last listing: one metadata listing per mailbox.

    Searching every person on the server each run is one query per person;
    listing the mailbox since the last run and matching addresses is one
    listing however many people there are. The newest date per person is kept
    in `.state/people/activity.json`, the cursor in `.state/people/refresh.json`;
    both are metadata, never a body. Returns {"records": [...], "listed": {kind: n}}.
    """
    from .mail import _address, _addresses, _list_all
    now = now or datetime.now(timezone.utc)
    state = _map(root)
    own = {a.casefold() for a in (state.get("owner") or {}).get("addresses", [])}
    by_address = {address.casefold(): row["record"] for row in state.get("people", [])
                  for address in row.get("addresses", []) if row.get("record") and address.casefold() not in own}
    folder = state_path(root, "people")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    cursor = read_json(folder / "refresh.json", {})
    activity = _activity(root)
    found, listed = set(), {}
    for kind, client in clients.items():
        start = (timestamp(cursor[kind]) - OVERLAP) if cursor.get(kind) else since
        rows = _list_all(client, start, now) if start < now else []
        listed[kind] = len(rows)
        for row in rows:
            when = _stamp(row.get("date"))
            involved = {_address(row.get("from", ""))} | set(_addresses(row.get("to"))) | set(_addresses(row.get("cc")))
            for address in involved:
                record = by_address.get(address)
                if record and when:
                    found.add(record)
                    old = _stamp(activity.get(record))
                    activity[record] = max(when, old).isoformat() if old else when.isoformat()
        cursor[kind] = now.isoformat()
    write_json(folder / "activity.json", activity)
    write_json(folder / "refresh.json", cursor)
    return {"records": sorted(found), "listed": listed}


def write_pages(rows: list[dict], *, write, gate=None, on_page=None) -> dict:
    """Investigate `rows` one after another; `gate()` says why not to start the next, or ''.

    A refused or failed page does not stop the others; it stays in the queue.
    """
    done, stopped = [], ""
    for number, row in enumerate(rows, 1):
        stopped = gate() if gate else ""
        if stopped:
            break
        if on_page:
            on_page(number, len(rows), row)
        try:
            write(row)
            done.append({"page": row["record"], "mode": row["mode"], "outcome": "accepted"})
        except WikiError as error:
            done.append({"page": row["record"], "mode": row["mode"],
                         "outcome": "refused" if "rejected" in str(error) else "failed", "why": str(error)[:300]})
    return {"pages": done, **({"stopped": stopped} if stopped else {})}
