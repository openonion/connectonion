"""
Purpose: An agent's own recurring work — read the schedule, decide what is due, run it, remember that it ran
LLM-Note:
  Dependencies: imports from [asyncio, dataclasses, datetime, json, os, pathlib, re, sys, uuid, yaml, zoneinfo, host.http_router] | imported by [network/host/server.py via create_schedule_lifespan()] | tested by [tests/unit/test_schedule.py]
  Data flow: load_entries(.co/schedule.yaml) → tick() every 60s → is_due(entry, last_run, now) → input_handler() in a worker thread → record_run() into .co/schedule-state.json
  State/Effects: reads .co/schedule.yaml (authored, deployed) | reads and writes .co/schedule-state.json (the server's own, never deployed over) | holds an OS lock while writing state | runs agent turns through the same path as POST /input, so every run lands in .co/session_results.jsonl
  Integration: exposes load_entries(), is_due(), load_state(), record_run(), last_run(), create_schedule_lifespan() | the lifespan pair composes with the relay's in host()
  Performance: one tick a minute, a dict comparison per entry | the run itself is a full agent turn, off the event loop in a thread
  Errors: a malformed schedule yields the entries that parse and never raises | unreadable state reads as empty | a failed run is recorded as failed and the tick continues

The clock lives in this process rather than in systemd, because `co` runs on
macOS, Windows and Linux and the OS scheduler does not — three implementations
of which two rot. The agent is already a long-lived process everywhere, so this
is one implementation. The argument in full is #521.
"""

import asyncio
import json
import os
import threading
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml

SCHEDULE_FILE = "schedule.yaml"
STATE_FILE = "schedule-state.json"

# The relay already wakes once a minute to heartbeat, so a minute is what the
# process costs anyway. It is also the resolution this is for: "every 15
# minutes", "weekday mornings". Nothing here wants a second hand.
TICK_SECONDS = 60

_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
_DURATION = re.compile(r"^(\d+)([smhd])$")
_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}



# Entry names with a run in flight right now.
#
# Module level rather than a closure so the Home page can read it: while a run
# is in flight, record_run has not landed and the Scheduled row shows the
# *previous* completion — which for an entry that takes longer than its
# interval reads as overdue (#539). The page needs to know the difference
# between "late" and "working".
_RUNNING: set = set()


def running_entries() -> set:
    """The live set of entry names currently executing."""
    return _RUNNING


@dataclass
class Entry:
    """One line of the schedule: what to run, and how often or when."""
    name: str
    run: str
    interval: Optional[timedelta] = None
    at: Optional[str] = None
    tz: Optional[str] = None


def _parse_duration(text) -> Optional[timedelta]:
    m = _DURATION.match(str(text).strip())
    if not m:
        return None
    return timedelta(**{_UNITS[m.group(2)]: int(m.group(1))})


def load_entries(co_dir, report=False):
    """The schedule as authored, minus anything that cannot mean something.

    One bad line must not take the others with it, and must not stop the agent
    booting: this file is hand-written and deployed, so a typo reaches
    production. But dropping it *silently* leaves absence as the only signal,
    and absence is what a correct schedule looks like most of the time — so the
    reasons are collected and the caller can say them out loud (#531).

    Pass ``report=True`` for ``(entries, problems)``.
    """
    path = Path(co_dir) / SCHEDULE_FILE
    problems = []

    def done(entries):
        return (entries, problems) if report else entries

    if not path.is_file():
        return done([])

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        problems.append(f"{SCHEDULE_FILE} does not parse: {exc}")
        return done([])
    if not isinstance(raw, list):
        problems.append(f"{SCHEDULE_FILE} should be a list of entries")
        return done([])

    entries, seen = [], set()
    for i, item in enumerate(raw, 1):
        where = f"entry {i}"
        if not isinstance(item, dict):
            problems.append(f"{where}: not a mapping")
            continue
        run = item.get("run")
        if not isinstance(run, str) or not run.strip():
            problems.append(f"{where}: no run")
            continue

        interval = at = None
        if item.get("every") is not None:
            interval = _parse_duration(item["every"])
            if interval is None:
                problems.append(f"{where}: {item['every']!r} is not a duration like 15m or 2h")
                continue
            if interval <= timedelta(0):
                # `every: 0m` is always due, so it ran a full agent turn on every
                # tick, forever, and looked like a working schedule while doing it.
                problems.append(f"{where}: every {item['every']!r} must be greater than zero")
                continue
        elif item.get("at"):
            at = str(item["at"]).strip()
        else:
            problems.append(f"{where}: needs every or at")
            continue

        name = str(item.get("name") or run).strip()
        entry = Entry(name=name, run=run.strip(), interval=interval, at=at,
                      tz=str(item["tz"]).strip() if item.get("tz") else None)

        if at is not None and _parse_at(entry) is None:
            problems.append(f"{where}: {at!r} is not a time like '09:00' or 'Mon 09:00'")
            continue
        if entry.tz and _zone_or_none(entry.tz) is None:
            # Kept, because refusing to run is worse than running in UTC — but
            # eight hours off is not a thing to discover from a missed report.
            problems.append(f"{where}: unknown timezone {entry.tz!r}, using UTC")
        if name in seen:
            # State is keyed by name: two entries sharing one overwrite each
            # other's last_run and each ends up running half as often as written.
            problems.append(f"{where}: duplicate name {name!r}")
            continue
        seen.add(name)
        entries.append(entry)

    return done(entries)


def _zone_or_none(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return None


def _zone(entry: Entry):
    if not entry.tz:
        return timezone.utc
    # An unknown zone name is a typo in a deployed file. UTC is wrong by hours;
    # refusing to run is wrong by everything. load_entries reports it.
    return _zone_or_none(entry.tz) or timezone.utc


def _parse_at(entry):
    """(weekday|None, hour, minute), or None when the string is not a time.

    Returns None rather than raising: the caller decides whether that means
    "drop this entry" (load) or "never fire" (evaluate).
    """
    parts = str(entry.at or "").split()
    if not parts or len(parts) > 2:
        return None
    day = None
    if len(parts) == 2:
        day = _WEEKDAYS.get(parts[0][:3].lower())
        if day is None:
            return None
    try:
        hour, minute = (int(x) for x in parts[-1].split(":"))
    except ValueError:
        return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return day, hour, minute


def _last_occurrence(entry, now):
    """The most recent moment this entry was supposed to fire, at or before now.

    Comparing against *that* rather than against "is it that weekday right now"
    is what makes a missed run catch up. An agent down through Monday used to
    skip its weekly summary for a whole week, silently, while interval entries
    caught up — the two forms of one feature disagreeing about the property
    #521 exists to preserve.
    """
    parsed = _parse_at(entry)
    if parsed is None:
        return None
    day, hour, minute = parsed

    local = now.astimezone(_zone(entry))
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if day is None:
        # Daily: today's time if it has passed, else yesterday's.
        if candidate > local:
            candidate -= timedelta(days=1)
        return candidate

    # Weekly: walk back to the most recent matching weekday at that time.
    behind = (local.weekday() - day) % 7
    candidate -= timedelta(days=behind)
    if candidate > local:
        candidate -= timedelta(days=7)
    return candidate


def _clock_due(entry, last_run, now):
    """Due when the most recent scheduled moment has not been served yet.

    Fires once for any number of missed occurrences: a month of downtime is one
    catch-up summary, not four.
    """
    occurrence = _last_occurrence(entry, now)
    if occurrence is None:
        return False

    if last_run is None:
        # A new entry has nothing to catch up: last Monday happened before it
        # existed. It fires when its own next occurrence arrives, which means
        # today, if today is the day and the time has passed.
        local = now.astimezone(_zone(entry))
        return occurrence.date() == local.date()

    return last_run.astimezone(_zone(entry)) < occurrence


def is_due(entry: Entry, last_run: Optional[datetime], now: datetime) -> bool:
    """Whether this entry should run now.

    A run missed while the process was down fires on the next tick — this is
    what `Persistent=true` gives a systemd timer, and it is the one thing
    in-process scheduling would otherwise lose. It fires *once*, not once per
    interval that elapsed: three days of downtime is one catch-up run, not
    seventy-two.
    """
    if entry.interval is not None:
        return last_run is None or (now - last_run) >= entry.interval
    if entry.at:
        return _clock_due(entry, last_run, now)
    return False


TICK_LOCK_FILE = "schedule.tick.lock"


def _tick_lock(co_dir: Path):
    """Take the tick for this minute, or return None because someone else has it.

    `create_app`'s docstring tells people to run `uvicorn myagent:app
    --workers 4`, so the lifespan — and this scheduler — runs once per forked
    process. The overlap guard above it is a module-level set, which is per
    process, and `last_run` is not written until the turn returns. So every
    worker saw the same due entry and started its own copy: four workers, four
    runs of a pipeline that was written expecting one.

    Elected per tick rather than for the life of the process. A worker that
    dies holding this costs one tick — the OS drops the flock — where a leader
    chosen at startup would leave the schedule stopped until someone noticed.

    Refusal is the answer here, not a retry: _lock() below waits and then
    proceeds anyway, which is right for a short write to the state file and
    exactly wrong for this, where proceeding is the duplicate run.
    """
    handle = open(co_dir / TICK_LOCK_FILE, "a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt
            # seek(0) so lock and unlock name the same byte. "a+" leaves the
            # position at the end, and this only works by accident while the
            # file stays empty. _lock() below already does this.
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except OSError:
        handle.close()
        return None


def _release_tick_lock(handle) -> None:
    if handle is None:
        return
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _lock(path: Path, attempts: int = 50, pause: float = 0.02):
    """Exclusive, released by the OS on death, and worth waiting a moment for.

    Retries rather than giving up at the first refusal. The lock used to be
    single-shot LOCK_NB, and every caller treated a refusal as permission to
    proceed — so under contention nobody held it and every writer did a
    read-modify-write on the same file. Measured: twelve threads, 240 writes,
    one whole entry silently missing from the result.

    Still bounded. A second of retries is generous for a write of a few hundred
    bytes, and blocking forever on a lock held by a process that died in a way
    the OS did not notice is worse than proceeding.

    Same shape as cli/browser_agent/transport.py — POSIX flock, Windows
    msvcrt. A scheduler that imports fcntl at module level is a scheduler that
    does not import on Windows.
    """
    import time as _time
    for attempt in range(attempts):
        handle = open(path, "a+", encoding="utf-8")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except OSError:
            handle.close()
            if attempt < attempts - 1:
                _time.sleep(pause)
    return None


def load_state(co_dir: Path) -> dict:
    """What has run, and how it went. Unreadable reads as empty.

    Losing this costs one duplicated run. Refusing to boot over it costs the
    agent, so a truncated write or a hand edit is not allowed to be fatal.
    """
    path = Path(co_dir) / STATE_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def record_run(co_dir: Path, name: str, *, when: datetime, status: str,
               session_id: Optional[str], reason: Optional[str] = None) -> None:
    """Remember one run, pointing at the session it produced.

    Only a pointer: .co/session_results.jsonl already holds the prompt, the
    transcript, the result and the duration. Copying any of that here would be
    a second source of truth that drifts.

    `reason` is the exception from a run that raised, and is the exception to
    that rule — a run that dies before producing a session leaves no session to
    point at, so this file is the only place its cause can live. Without it Home
    says `failed` and finding out that the account was out of credits costs an
    ssh session (#541).
    """
    co_dir = Path(co_dir)
    co_dir.mkdir(parents=True, exist_ok=True)
    path = co_dir / STATE_FILE

    handle = _lock(co_dir / f"{STATE_FILE}.lock")
    if handle is None:
        # Proceeding unlocked is the deliberate choice — blocking forever on a
        # lock held by a process the OS never noticed dying is worse. But this
        # write is a read-modify-write of the whole file, so it can drop another
        # writer's entry, and a lost last_run makes the scheduler run something
        # a second time. Say it, so that duplicate run is findable in the log
        # instead of being inferred weeks later.
        print(f"[schedule] writing {name} without the state lock — another "
              f"process is holding it; an entry may be lost")
    try:
        state = load_state(co_dir)
        # Rebuilt rather than updated, so a later success drops the reason a
        # previous failure left behind. A stale cause on a healthy entry is a
        # worse lie than no cause at all.
        state[name] = {
            "last_run": when.astimezone(timezone.utc).isoformat(),
            "status": status,
            "session_id": session_id,
        }
        if reason:
            state[name]["reason"] = reason
        # A name of its own. One shared `.tmp` meant concurrent writers wrote
        # over each other's file and then raced to rename it: the first
        # os.replace consumed it and the second raised FileNotFoundError, out
        # of the scheduler's own tick.
        tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)  # readers see the old file or the new one
        finally:
            # A crash between write and replace would otherwise leave one temp
            # file per incident, in the directory the agent reads on every boot.
            if tmp.exists():
                tmp.unlink(missing_ok=True)
    finally:
        if handle:
            handle.close()


def last_run(state: dict, name: str) -> Optional[datetime]:
    raw = (state.get(name) or {}).get("last_run")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def create_schedule_lifespan(co_dir: Path, create_agent, storage, result_ttl: int,
                             console=None):
    """Start and stop the tick alongside the ASGI app.

    Returns (on_startup, on_shutdown), the same pair shape the relay uses, so
    host() can compose them.
    """
    task: dict = {}
    in_flight = _RUNNING

    def _say(message: str) -> None:
        if console:
            console.print(f"[dim][schedule][/dim] {message}")

    def _run_entry(entry: Entry) -> tuple:
        """One turn, through the same path as POST /input.

        Reusing input_handler is what puts a scheduled run in
        .co/session_results.jsonl beside the interactive ones — same record,
        same fields, visible to anything that reads them. A separate execution
        path here would mean background work is the one kind nobody can inspect.
        """
        from .http_router import input_handler

        session_id = str(uuid.uuid4())
        out = input_handler(create_agent, storage, entry.run, result_ttl,
                            session={"session_id": session_id})
        return out.get("status", "done"), session_id

    async def tick_once(now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)
        entries = load_entries(co_dir)
        if not entries:
            return

        holder = _tick_lock(co_dir)
        if holder is None:
            # Another worker is running this tick. Not worth a line of output:
            # under --workers 4 it is the normal case three times over, every
            # minute, and it would bury what the running worker says.
            return
        try:
            await _run_due(entries, now)
        finally:
            _release_tick_lock(holder)

    async def _run_due(entries, now: datetime) -> None:
        state = load_state(co_dir)

        for entry in entries:
            if entry.name in in_flight:
                # record_run only happens after the turn returns, so last_run is
                # stale for the whole duration — an entry whose work outlives its
                # interval is "due" again while the first copy is still going, and
                # again after that. Two copies of a pipeline that downloads,
                # extracts and writes to one table race each other into the same
                # rows (#537).
                #
                # Said out loud rather than skipped quietly: an entry that
                # overruns every time is a misconfiguration — the schedule claims
                # fifteen minutes and the truth is twenty-five.
                _say(f"[yellow]{entry.name} still running, skipping this tick[/yellow]")
                continue
            if not is_due(entry, last_run(state, entry.name), now):
                continue
            _say(f"running {entry.name}")
            in_flight.add(entry.name)
            try:
                # A turn takes as long as it takes — four minutes is normal for
                # real work. In a thread, so the heartbeat keeps going and the
                # agent stays reachable while it runs.
                status, session_id = await asyncio.to_thread(_run_entry, entry)
            except Exception as exc:
                # One entry failing is not the scheduler failing. Record it and
                # keep the others on time.
                _say(f"[red]{entry.name} failed: {exc}[/red]")
                record_run(co_dir, entry.name, when=now, status="failed",
                           session_id=None, reason=str(exc))
                continue
            finally:
                # Released whatever happened. A flag that outlived a crash would
                # mean the entry never runs again, which is worse than the
                # overlap it prevents.
                in_flight.discard(entry.name)
            record_run(co_dir, entry.name, when=now, status=status, session_id=session_id)

    async def loop() -> None:
        while True:
            try:
                await tick_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _say(f"[red]tick failed: {exc}[/red]")
            await asyncio.sleep(TICK_SECONDS)

    async def on_startup() -> None:
        entries, problems = load_entries(co_dir, report=True)
        # Said once, at startup, where the operator is already looking. A
        # dropped entry is otherwise indistinguishable from one that is simply
        # not due yet — and that is what a working schedule looks like too.
        for problem in problems:
            _say(f"[yellow]{problem}[/yellow]")
        if not entries:
            return          # nothing scheduled: no task, no noise
        _say(f"{len(entries)} scheduled")
        task["handle"] = asyncio.create_task(loop())

    async def on_shutdown() -> None:
        handle = task.get("handle")
        if not handle:
            return
        handle.cancel()
        try:
            await handle
        except asyncio.CancelledError:
            pass

    on_startup.tick_once = tick_once      # the seam tests drive
    return on_startup, on_shutdown
