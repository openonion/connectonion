"""What one night did, measured, so schedules are compared on results and not guessed (D-104).

A night runs noon to noon in the notebook's zone, as the task count did. Its numbers come
from the receipts REM already keeps: turn receipts (.state/turns) and run records
(.state/runs). Idle minutes are counted inside 22:00-07:00, the hours every schedule
profile covers, so a dense night and a default one are measured on the same span.
Each finished night is appended once to .state/night-stats.jsonl.
"""

import json
from datetime import datetime, time, timedelta

from . import service
from .files import read_json, state_path

CORE = (time(22, 0), time(7, 0))
ACCEPTED, PARKED = ("completed",), ("parked",)
FAILED = ("failed", "refused", "timed-out", "discarded")


def _night_of(moment, zone):
    return (moment.astimezone(zone) - timedelta(hours=12)).date()


def _window(night, zone):
    start = datetime.combine(night, time(12, 0), zone)
    return start, start + timedelta(days=1)


def _turns(root):
    for path in sorted(state_path(root, "turns").glob("*.json")):
        turn = read_json(path, {})
        if turn.get("started_at") and turn.get("finished_at") and turn.get("result") != "skipped":
            yield datetime.fromisoformat(turn["started_at"]), datetime.fromisoformat(turn["finished_at"])


def _minutes(intervals, start, end):
    """Minutes inside [start, end) covered by any interval."""
    covered, cursor = 0.0, start
    for begin, finish in sorted(intervals):
        begin, finish = max(begin, cursor), min(finish, end)
        if finish > begin:
            covered += (finish - begin).total_seconds() / 60
            cursor = finish
    return round(covered)


def measure(root, night, zone) -> dict:
    """The numbers for one night (a date: the evening it starts)."""
    start, end = _window(night, zone)
    turns = [(begin, finish) for begin, finish in _turns(root) if start <= begin < end]
    runs = [run for run in service.run_logs(root)
            if start <= datetime.fromisoformat(run["started_at"]) < end]
    tasks = [run for run in runs if run.get("task_id")]
    core_start = datetime.combine(night, CORE[0], zone)
    core_end = datetime.combine(night + timedelta(days=1), CORE[1], zone)
    core = round((core_end - core_start).total_seconds() / 60)
    return {"night": night.isoformat(), "profile": _profile(root), "turns": len(turns),
            "tasks_accepted": sum(run.get("outcome") in ACCEPTED for run in tasks),
            "tasks_parked": sum(run.get("outcome") in PARKED for run in tasks),
            "tasks_failed": sum(run.get("outcome") in FAILED for run in tasks),
            "drafts": sum(run.get("phase") == "reply-draft" and run.get("outcome") in ACCEPTED for run in runs),
            "mail_read": sum(run.get("items", 0) for run in runs if run.get("phase") == "sync" and run.get("stage") == "maintain"),
            "minutes_busy": _minutes(turns, start, end),
            "minutes_idle": core - _minutes(turns, core_start, core_end)}


def _profile(root):
    from .config import read_config
    return read_config(root)["schedule"]["profile"]


def recent(root, nights=2) -> list[dict]:
    """Tonight so far and the nights before it, newest first, for status."""
    from .config import read_config
    zone = service.notebook_zone(read_config(root))
    tonight = _night_of(service.now(), zone)
    return [measure(root, tonight - timedelta(days=back), zone) for back in range(nights)]


def record(root) -> list[dict]:
    """Append every finished night since the last line (at most a week back); the lines written."""
    from .config import read_config
    zone = service.notebook_zone(read_config(root))
    path = state_path(root, "night-stats.jsonl")
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    last = json.loads(lines[-1])["night"] if lines else None
    tonight = _night_of(service.now(), zone)
    first = max(datetime.fromisoformat(last).date() + timedelta(days=1) if last else tonight - timedelta(days=1),
                tonight - timedelta(days=7))
    written = [measure(root, first + timedelta(days=day), zone) for day in range((tonight - first).days)]
    if written:
        with path.open("a", encoding="utf-8") as log:
            log.writelines(json.dumps(row) + "\n" for row in written)
    return written
