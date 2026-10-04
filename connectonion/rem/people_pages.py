"""Which people to investigate next, and over which window: recent correspondents first (#1943 stage 3, #1723).

Investigating one person is `investigate.investigate`: its script gathers the
person's mail (the saved archive first, then the server for what is missing,
bodies and attachments) before any model starts, and since #1942 the one
investigate turn searches that material as files instead of digesting it
(#1850). What was missing is the order and the size of the work:

- **Order.** The busiest person first never fit a day's calls (#1723), and
  the last mail alone put vendors and one-mail strangers first (#1974). People
  the owner wrote to come first, then people who wrote more than once, then
  one-mail contacts; within each, the last `recent_days` first, then volume
  decayed by age (`rank`). This is the one people queue: the overview, `people
  --list` and the run read it.
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

from .files import Notebook, RemError, maintenance_lock, read_json, state_path, write_json
from .source import timestamp

# Correspondents of the last two weeks are investigated before anyone older (owner, 2026-09-30).
RECENT_DAYS = 14
# The window a page is read over when it has not been investigated from new mail.
FIRST_WINDOW_DAYS = 730  # two years: a real contact went back to July 2025, 38 mails; 150 days read 13 (2026-10-01)
# Measured on the owner's machine, 2026-09-30 (docs/cli/rem-people-pages.md):
# one full investigation of a 157-mail person, the #1850 baseline subject.
MEASURED = {"mails": 157, "input_tokens": 1_931_414, "minutes": 15,
            "date": "2026-09-30", "window_days": 150}
# A mail still arriving at the last listing carries a time before it.
OVERLAP = timedelta(hours=1)


def _map(root: Path) -> dict:
    return read_json(state_path(root, "map.json"), {})


def rank(row: dict, now: datetime) -> tuple:
    """Where a person stands in the queue; smaller first.

    Tier: the owner wrote to them (a correspondent), else they wrote more than
    once, else one mail. Within a tier the last `recent_days` first, then the
    map's mail count decayed by the weeks since the last mail, so 600 mails
    last week outrank one mail yesterday.
    """
    tier = 0 if row.get("sent") else 1 if row.get("mails", 0) > 1 else 2
    last = _stamp(row.get("last_activity"))
    weeks = max(0.0, (now - last).total_seconds() / 604_800) if last else 52.0
    return tier, not row["recent"], -(row.get("mails", 0) / (1 + weeks)), row["record"]


def _stamp(value) -> datetime | None:
    value = str(value or "")
    if not value:
        return None
    try:
        return timestamp(value if "T" in value else value + "T00:00:00+00:00")
    except RemError:
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
    from .queue import excluded_people, last_investigated, order
    now = now or datetime.now(timezone.utc)
    today = now.date()
    cutoff = (now - timedelta(days=recent_days)).isoformat()
    state, activity = _map(root), _activity(root)
    done = read_json(state_path(root, "people/investigated.json"), {})
    excluded = excluded_people(state)
    unfinished = {row["path"]: row for row in order(root, "people")}
    from .merge import resolve
    mapped = {resolve(root, row.get("record") or ""): row for row in state.get("people", [])}
    excluded = {resolve(root, record) for record in excluded if record}
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
        hollow = unfinished.get(record, {}).get("hollow")
        if hollow:
            # Stamped by a run that read nothing (#1974): read again in full.
            mode, window, investigated = "full", FIRST_WINDOW_DAYS, None
        elif at and last and _stamp(last) > at:
            mode, window = "update", max(1, (today - at.date()).days + 1)
        elif record in unfinished and not unfinished[record]["recent"]:
            mode, window = "full", FIRST_WINDOW_DAYS
        else:
            continue
        if since and not last > since:
            continue
        row = mapped.get(record, {})
        rows.append({"record": record, "mode": mode, "days": window, "last_activity": last,
                     "recent": last >= cutoff, "mails": row.get("mails") or 0,
                     "sent": row.get("sent") or 0, "received": row.get("received") or 0,
                     "last_investigated": investigated.isoformat() if investigated else None})
    return sorted(rows, key=lambda r: rank(r, now))


def estimate(rows: list[dict]) -> dict:
    """What investigating these people will cost, stated before anything is read or spent.

    One model call a person; the mail the map counted is what a full
    investigation reads (an update reads only its window). The measured figure
    is what one full investigation cost on the owner's machine.
    """
    return {"people": len(rows), "model_calls": len(rows), "recent": sum(1 for r in rows if r["recent"]),
            "updates": sum(1 for r in rows if r["mode"] == "update"),
            "mails_mapped": sum(r["mails"] for r in rows if r["mode"] == "full"), "measured": MEASURED,
            "window_days": next((row["days"] for row in rows if row["mode"] == "full"), FIRST_WINDOW_DAYS)}


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
    try:
        result = investigation.investigate(root, row["record"], title, names, days=row["days"], clients=clients,
                                           subscriptions=subscriptions, max_calls=max_calls, progress=progress,
                                           stage_progress=stage_progress)
    except investigation.NothingNew:
        # The window was read and held nothing: mail before `started` is not
        # new next run, or the same person is gathered again every run (#1984).
        mark_investigated(root, row["record"], started)
        raise
    mark_investigated(root, row["record"], started)
    return result


def mark_investigated(root: Path, record: str, when: datetime) -> None:
    """When the gather for this page started: mail after it is new for the next run."""
    folder = state_path(root, "people")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with maintenance_lock(root, wait=60):  # people finishing together each rewrite this file
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


def write_pages(rows: list[dict], *, write, gate=None, on_page=None, workers: int = 1) -> dict:
    """Investigate `rows` with bounded concurrency; gate before each submission.

    A refused or failed page does not stop the others; it stays in the queue.
    """
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    def one(row):
        try:
            write(row)
            return {"page": row["record"], "mode": row["mode"], "outcome": "accepted"}
        except RemError as error:
            return {"page": row["record"], "mode": row["mode"],
                    "outcome": "refused" if "rejected" in str(error) else "failed", "why": str(error)[:300]}

    done, stopped, pending, running = [], "", iter(rows), {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while True:
            while len(running) < workers and not stopped:
                row = next(pending, None)
                if row is None:
                    break
                stopped = gate() if gate else ""
                if not stopped:
                    running[pool.submit(one, row)] = row
            if not running:
                break
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                row = running.pop(future)
                outcome = future.result()
                done.append(outcome)
                if on_page:
                    on_page(len(done), len(rows), row, outcome)
    return {"pages": done, **({"stopped": stopped} if stopped else {})}
