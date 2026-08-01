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


def load_entries(co_dir: Path) -> list:
    """The schedule as authored, minus anything that does not parse.

    One bad line must not take the others with it, and must not stop the agent
    booting: this file is hand-written and deployed, so a typo reaches
    production and the agent has to survive it. What does not parse is dropped;
    what does, runs.
    """
    path = Path(co_dir) / SCHEDULE_FILE
    if not path.is_file():
        return []

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []

    entries = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        run = item.get("run")
        if not isinstance(run, str) or not run.strip():
            continue

        interval = _parse_duration(item["every"]) if item.get("every") is not None else None
        at = item.get("at")
        if interval is None and not at:
            continue          # neither a valid interval nor a clock time

        entries.append(Entry(
            # State is keyed by name, and requiring one would be ceremony for the
            # single-entry case. The command is a serviceable identity.
            name=str(item.get("name") or run).strip(),
            run=run.strip(),
            interval=interval,
            at=str(at).strip() if at else None,
            tz=str(item["tz"]).strip() if item.get("tz") else None,
        ))
    return entries


def _zone(entry: Entry):
    if not entry.tz:
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(entry.tz)
    except Exception:
        # An unknown zone name is a typo in a deployed file. UTC is wrong by
        # hours; refusing to run is wrong by everything.
        return timezone.utc


def _clock_due(entry: Entry, last_run: Optional[datetime], now: datetime) -> bool:
    """`at: "09:00"` or `at: "Mon 09:00"` — due once per matching moment."""
    parts = entry.at.split()
    day = None
    if len(parts) == 2:
        day = _WEEKDAYS.get(parts[0][:3].lower())
        if day is None:
            return False
    try:
        hour, minute = (int(x) for x in parts[-1].split(":"))
    except ValueError:
        return False

    local = now.astimezone(_zone(entry))
    if day is not None and local.weekday() != day:
        return False
    if (local.hour, local.minute) < (hour, minute):
        return False

    if last_run is None:
        return True
    # Once per day. Compared in the entry's own zone, so a run at 09:00 Shanghai
    # does not re-fire because it is still yesterday in UTC.
    return last_run.astimezone(_zone(entry)).date() < local.date()


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


def _lock(path: Path):
    """Exclusive, non-blocking, released by the OS on death.

    Same shape as cli/browser_agent/transport.py — POSIX flock, Windows
    msvcrt. A scheduler that imports fcntl at module level is a scheduler that
    does not import on Windows.
    """
    handle = open(path, "a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


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
               session_id: Optional[str]) -> None:
    """Remember one run, pointing at the session it produced.

    Only a pointer: .co/session_results.jsonl already holds the prompt, the
    transcript, the result and the duration. Copying any of that here would be
    a second source of truth that drifts.
    """
    co_dir = Path(co_dir)
    co_dir.mkdir(parents=True, exist_ok=True)
    path = co_dir / STATE_FILE

    handle = _lock(co_dir / f"{STATE_FILE}.lock")
    try:
        state = load_state(co_dir)
        state[name] = {
            "last_run": when.astimezone(timezone.utc).isoformat(),
            "status": status,
            "session_id": session_id,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)      # readers see the old file or the new one
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
        state = load_state(co_dir)

        for entry in entries:
            if not is_due(entry, last_run(state, entry.name), now):
                continue
            _say(f"running {entry.name}")
            try:
                # A turn takes as long as it takes — four minutes is normal for
                # real work. In a thread, so the heartbeat keeps going and the
                # agent stays reachable while it runs.
                status, session_id = await asyncio.to_thread(_run_entry, entry)
            except Exception as exc:
                # One entry failing is not the scheduler failing. Record it and
                # keep the others on time.
                _say(f"[red]{entry.name} failed: {exc}[/red]")
                record_run(co_dir, entry.name, when=now, status="failed", session_id=None)
                continue
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
        entries = load_entries(co_dir)
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
