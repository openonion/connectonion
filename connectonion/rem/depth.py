"""Each run goes one level deeper: one round on one page is enrich then muse.

Round N reads what round N-1 left through run logs: enrich's open leads and
muse's open questions. Value times thinness chooses pages. Deepening budgets
its own share of the Codex week, 30 points by default (the owner's #2533 decision).
"""

import re
import time
from datetime import datetime, timedelta, timezone
from math import log2

from . import muse, quota, runner, service
from .config import read_config
from .files import Notebook, RemError, read_json, state_path, write_json
from .page_review import _listed_sources, quotes as page_quotes

REST_DAYS = 30
DEPTH_PHASES = quota.DEPTH_PHASES


def page_metrics(text) -> dict:
    return {"chars": len(text), "quotes": len(page_quotes(text)), "sources": len(_listed_sources(text))}


def _stamp(value) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _gain(row) -> int:
    return sum(row[key][1] - row[key][0] for key in ("quotes", "sources")) + row["insights"]


def _resting(rounds, today) -> bool:
    """2026-10-20: four handoff rounds added 350–600 chars and only 0–2 quotes each."""
    if not rounds:
        return False
    last = rounds[-1]
    # A refused or failed round changed nothing because it was not let through, not because
    # the page has nothing left (2026-10-20: a refused project round would have rested a month).
    if last["enrich"] != "completed" or last["muse"] != "completed":
        return False
    unchanged = all(last[key][0] == last[key][1] for key in ("chars", "quotes", "sources")) and last["insights"] == 0
    plateau = len(rounds) >= 2 and all(_gain(row) <= 1 and abs(row["chars"][1] - row["chars"][0]) < 600
                                       for row in rounds[-2:])
    return today - _stamp(last["at"]) < timedelta(days=REST_DAYS) and (unchanged or plateau)


def _value_last(record, row, text, mapped_rows) -> tuple[int, str | None]:
    project = record.startswith("projects/")
    if record.startswith("orgs/") and row is not None:
        people = [mapped_rows[person] for person in row["people"] if person in mapped_rows]
        last = max((person["last"] for person in people if person.get("last")), key=_stamp, default=None)
        return sum(person.get("mails") or 0 for person in people), last
    if row is not None:
        return row.get("sessions" if project else "mails") or 0, row.get("last")
    if not project:
        return 0, None
    paths = text.partition("## Paths\n")[2].split("\n## ", 1)[0]
    sessions = re.search(r"(?m)^- Sessions: (\d+)\b", paths)
    last = re.search(r"(?m)^- Last seen: (\d{4}-\d{2}-\d{2})\b", text)
    return int(sessions[1]) if sessions else 0, last[1] if last else None


def _mapped_rows(mapped) -> dict:
    return {row["record"]: row for kind in ("people", "projects", "orgs")
            for row in mapped.get(kind, []) if row.get("record")}


def _notification_org(record, mapped_rows) -> bool:
    """2026-10-20: the first org picked was an event domain with one one-way person."""
    row = mapped_rows.get(record)
    if not record.startswith("orgs/") or row is None:
        return False
    people = [mapped_rows.get(person, {}) for person in row["people"]]
    return all(person.get("automated_hint") or person.get("one_way") for person in people)


def _candidate(notebook, record, mapped_rows, rounds, today) -> dict:
    text = notebook.read(record)
    value, last = _value_last(record, mapped_rows.get(record), text, mapped_rows)
    metrics = page_metrics(text)
    recent = 2 if last and today - _stamp(last) <= timedelta(days=30) else 1
    thin = 1 / (1 + metrics["quotes"] / 3 + metrics["sources"] / 10)
    # 2026-10-20, fresh notebook copy, two-slot picker: 5 mails on an almost empty
    # page (priority 4.3) beat 30–55 mails; the round gained one quote, 2,669 ->
    # 2,660 chars. Square log-value so thinness does not outweigh useful activity.
    priority = log2(2 + value) ** 2 * recent * thin / (1 + len(rounds))
    return {"record": record, "priority": priority, "value": value, "recent": recent,
            "rounds": len(rounds), **metrics}


def candidates(root) -> list[dict]:
    mapped = read_json(state_path(root, "map.json"), {})
    history = read_json(state_path(root, "depth.json"), {})
    owner = mapped.get("owner")
    owner = owner.get("record") if isinstance(owner, dict) else owner
    mapped_rows = _mapped_rows(mapped)
    notebook, today, rows = Notebook(root), service.now(), []
    for record in notebook.list():
        row = mapped_rows.get(record, {})
        if (not record.startswith(("people/", "projects/", "orgs/")) or record == owner
                or row.get("classification") == "account owner" or row.get("automated_hint")
                or _notification_org(record, mapped_rows)):
            continue
        rounds = history.get(record, [])
        if _resting(rounds, today):
            continue
        rows.append(_candidate(notebook, record, mapped_rows, rounds, today))
    return sorted(rows, key=lambda row: (-row["priority"], row["record"]))


def spent(root, meter) -> float:
    return quota.depth_points(service.run_logs(root), meter)


def stop_reason(root, config) -> str:
    meter, limits = quota.read(config), config["limits"]
    floor = quota.floor_block(meter, limits)
    if floor:
        return floor
    used, budget = spent(root, meter), limits["depth_quota_points"]
    return f"deepening has used {used} of its {budget}-point weekly budget" if used >= budget else ""


def _stage(root, record, name) -> dict:
    return getattr(muse, name)(root, record)


def _run(root, record, name, stage) -> dict:
    # A failed enrich must leave a round record and still let muse think (#2533).
    try:
        result = stage(root, record, name)
        return {**result, "outcome": result.get("outcome", "completed")}
    except RemError as error:
        return {"outcome": "refused" if "rejected" in str(error) else f"failed: {str(error)[:200]}",
                "usage": getattr(error, "usage", None)}


def deepen(root, record, *, stage=None) -> dict:
    notebook = Notebook(root)
    text = notebook.read(record)
    before, quotes = page_metrics(text), page_quotes(text)
    enrich = _run(root, record, "enrich", stage or _stage)
    after_enrich = page_metrics(notebook.read(record))
    thought = _run(root, record, "muse", stage or _stage)
    text = notebook.read(record)
    after = page_metrics(text)
    history = read_json(state_path(root, "depth.json"), {})
    rounds = history.setdefault(record, [])
    row = {"round": len(rounds) + 1, "at": service.now().isoformat(),
           **{key: [before[key], after[key]] for key in before},
           "after_enrich": after_enrich,
           "insights": thought.get("insights", 0), "lost_quotes": len(quotes - page_quotes(text)),
           "enrich": enrich["outcome"], "muse": thought["outcome"],
           "points": sum(quota._token_points(result.get("usage"), read_config(root)["speed"]) for result in (enrich, thought))}
    rounds.append(row)
    write_json(state_path(root, "depth.json"), history)
    return {"record": record, **row}


def slot(root, *, records=None, pages=None, stage=None, say=None) -> dict:
    started = time.monotonic()
    config = read_config(root)
    limit = config["limits"]["depth_slot_minutes"]
    if records is None:
        choices = candidates(root)
        pages = config["limits"]["depth_pages_per_slot"] if pages is None else pages
    else:
        history = read_json(state_path(root, "depth.json"), {})
        mapped_rows = _mapped_rows(read_json(state_path(root, "map.json"), {}))
        notebook, today = Notebook(root), service.now()
        choices = [_candidate(notebook, record, mapped_rows, history.get(record, []), today) for record in records]
        pages = len(choices)
    problem, _ = runner.ready(config)
    if problem:
        return {"rounds": [], "picked": [], "stopped": problem, "left": len(choices)}
    rounds, picked, reason = [], [], ""
    for choice in choices[:pages]:
        if rounds:
            minutes = (time.monotonic() - started) / 60
            if minutes > limit:
                reason = f"the slot has run {int(minutes)} of its {limit} minutes"
                break
        reason = stop_reason(root, config)
        if reason:
            break
        record = choice["record"]
        if say:
            say(f"Deepening {record} (round {choice['rounds'] + 1})…")
        rounds.append(deepen(root, record, stage=stage))
        picked.append({key: choice[key] for key in ("record", "priority", "value", "recent", "quotes", "sources", "rounds")})
    return {"rounds": rounds, "picked": picked, "stopped": reason, "left": len(choices) - len(rounds)}
