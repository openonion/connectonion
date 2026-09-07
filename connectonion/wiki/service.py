"""Foreground maintenance core. Background lifecycle is a separate milestone."""

import hashlib
import json
import os
import re
import signal
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import prepare, read_config, validate
from .files import Notebook, WikiError, maintenance_lock, read_json, state_path, write_json
from .source import collect, pending_metadata


def now() -> datetime:
    return datetime.now(timezone.utc)


def codex_sessions_root() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser().resolve() / "sessions"


def subscriptions(root: Path) -> dict:
    saved = read_json(state_path(root, "subscriptions.json"), {})
    if not isinstance(saved, dict):
        raise WikiError("Invalid subscriptions file; preserve it for diagnosis")
    defaults = {
        "codex": {"id": "codex", "kind": "codex", "root": str(codex_sessions_root()),
                  "project": None, "since": (now() - timedelta(days=7)).isoformat(),
                  "enabled": True, "consented": False, "adapter": "available"},
        "claude-code": {"id": "claude-code", "enabled": True, "consented": False, "adapter": "deferred"},
        "gmail": {"id": "gmail", "enabled": False, "consented": False, "adapter": "deferred"},
        "outlook": {"id": "outlook", "enabled": False, "consented": False, "adapter": "deferred"},
    }
    defaults.update(saved)
    return defaults


def approve_sources(root: Path) -> None:
    """Internal consent handoff for tests/future start; never called by inspection."""
    with maintenance_lock(root):
        prepare(root)
        validate(read_config(root))
        sources = subscriptions(root)
        for source in sources.values():
            if source.get("kind") == "codex" and source.get("enabled"):
                source["consented"] = True
        write_json(state_path(root, "subscriptions.json"), sources)
        write_json(state_path(root, "consent.json"), {"authorized_at": now().isoformat()})


def toggle_source(root: Path, name: str, enabled: bool, *, project: str = "", since: str = "7d") -> str:
    """Store a choice, not permission to read bodies or run the model."""
    with maintenance_lock(root):
        sources = subscriptions(root)
        if project:
            if name != "codex" or not re.fullmatch(r"[1-9]\d*d", since):
                raise WikiError("Custom scopes require codex and a lookback such as 7d")
            project = str(Path(project).expanduser().resolve())
            name = "codex-" + hashlib.sha256(project.encode()).hexdigest()[:12]
            if name not in sources:
                sources[name] = {**sources["codex"], "id": name, "project": project,
                                 "consented": False,
                                 "since": (now() - timedelta(days=int(since[:-1]))).isoformat()}
        if name not in sources:
            raise WikiError("Subscription not found; inspect subscriptions for exact names")
        sources[name]["enabled"] = enabled
        write_json(state_path(root, "subscriptions.json"), sources)
    return name


def run_logs(root: Path, run_id: str = "") -> list[dict]:
    if run_id:
        if not re.fullmatch(r"run_[0-9a-f]{32}", run_id):
            raise WikiError("Unknown run ID; use an ID from the logs listing")
        path = state_path(root, f"runs/{run_id}.json")
        if not path.is_file():
            raise WikiError("Run not found; inspect logs for a current run ID")
        paths = [path]
    else:
        directory = state_path(root, "runs")
        paths = [state_path(root, f"runs/{p.name}") for p in directory.glob("run_*.json")]
    records = [read_json(path, {}) for path in paths]
    if any(not isinstance(record, dict) or "started_at" not in record for record in records):
        raise WikiError("Invalid run log; preserve it for diagnosis")
    return sorted(records, key=lambda record: record["started_at"], reverse=True)


def worker_state(root: Path) -> dict:
    saved = read_json(state_path(root, "worker.json"), {})
    return saved if isinstance(saved, dict) else {}


def latest_slot(config: dict, moment: datetime) -> datetime | None:
    """The most recent saved time at or before `moment`, in the saved zone.

    Comparing the last served slot against this -- rather than asking "is it
    17:00 right now" -- is what makes a missed slot catch up, and catch up once:
    a night asleep is one batch, not three. Same rule as host/schedule.py.
    """
    schedule = config.get("schedule", {})
    times, zone_name = schedule.get("times", []), schedule.get("timezone", "")
    if not times or not zone_name:
        return None
    local = moment.astimezone(ZoneInfo(zone_name))
    candidates = []
    for value in times:
        hour, minute = (int(part) for part in value.split(":"))
        slot = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        candidates.append(slot if slot <= local else slot - timedelta(days=1))
    return max(candidates)


def next_slot(config: dict, zone) -> str | None:
    """The next configured time after now, in the saved zone; None without a timezone."""
    times = config.get("schedule", {}).get("times", [])
    if not times or zone is timezone.utc and not config.get("schedule", {}).get("timezone"):
        return None
    current = now().astimezone(zone)
    candidates = []
    for day in (0, 1):
        for value in times:
            hour, minute = (int(part) for part in value.split(":"))
            slot = (current + timedelta(days=day)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            if slot > current:
                candidates.append(slot)
    return min(candidates).isoformat(timespec="minutes") if candidates else None


def _state_line(root: Path, config: dict, zone) -> tuple[str, str | None]:
    if not state_path(root, "consent.json").is_file():
        return "Not started — run `co wiki start` to authorize sources and begin", None
    worker = worker_state(root)
    if worker.get("enabled"):
        slot = next_slot(config, zone)
        return f"Running in background ({worker.get('scheduler', 'scheduler')}); next slot {slot or 'unknown'}", slot
    return "Stopped — background maintenance is off; `co wiki sync` works by hand, `co wiki start` resumes", None


def status(root: Path) -> dict:
    config = read_config(root)
    saved_zone = config.get("schedule", {}).get("timezone", "")
    zone = ZoneInfo(saved_zone) if saved_zone else timezone.utc
    today = now().astimezone(zone).date()
    state, slot = _state_line(root, config, zone)
    logs = run_logs(root)
    recent = [record for record in logs
              if datetime.fromisoformat(record["started_at"]).astimezone(zone).date() == today]
    attempted = [record for record in recent if record.get("runner_attempts", 0)]
    usage = {}
    coverage = {}
    for key in ("input_tokens", "output_tokens", "cached_input_tokens"):
        values = [(record.get("usage") or {}).get(key) for record in attempted]
        known = [value for value in values if type(value) is int and value >= 0]
        usage[key] = sum(known) if known else None
        coverage[key] = {"known_attempts": len(known), "total_attempts": len(attempted)}
    return {"state": state,
            "root": str(root), "configured": (root / "config.yaml").exists(),
            "date": str(today), "timezone": saved_zone or "Unknown (UTC reporting fallback only)",
            "schedule_times": config.get("schedule", {}).get("times", []), "next_run": slot,
            "worker": worker_state(root),
            "batches_today": len(recent), "runner_attempts_today": len(attempted),
            "usage_today": usage, "usage_coverage": coverage,
            "last_run": logs[0] if logs else None}


def consent_summary(root: Path) -> dict:
    """Everything `start` must show before a single source body is read."""
    config = read_config(root)
    sources = {}
    for name, source in subscriptions(root).items():
        if source.get("adapter") == "deferred":
            state = "not implemented yet"
        elif not source.get("enabled"):
            state = "unsubscribed"
        elif source.get("kind") == "codex":
            state = "will be read" if Path(source["root"]).is_dir() else "directory missing"
        else:
            state = "waiting"
        sources[name] = {"state": state, "root": source.get("root"), "project": source.get("project"),
                         "since": source.get("since")}
    return {"root": str(root), "sources": sources, "runner": config["runner"], "model": config["model"],
            "model_receives": "the new session messages plus the notebook pages it reads, "
                              "through your own Codex login (no API key, no OpenOnion server)",
            "schedule": config["schedule"], "limits": config["limits"],
            "background": "a launchd job under your user at the times above, and one bounded batch at login"}


def start(root: Path, *, confirm, scheduler, runner=None) -> dict:
    """Prepare what is missing, confirm access once, install the clock, run the first batch.

    `confirm` receives the summary and returns True to proceed. Declining leaves
    every source body unread and installs nothing. A repeated start re-applies
    the schedule but does not ask again and does not repeat the initial batch.
    """
    root = root.resolve()
    with maintenance_lock(root):
        prepare(root)
        validate(read_config(root))
    first = not state_path(root, "consent.json").is_file()
    if first:
        if not confirm(consent_summary(root)):
            return {"started": False, "consented": False, "first_batch": None}
        approve_sources(root)
    # The first batch runs before the clock is installed: loading a launchd job
    # fires its run-at-load batch immediately, and two batches would race for the
    # notebook lock, with the one the user is watching likely to lose.
    first_batch = run_sync(root, runner=runner) if first else None
    try:
        installed = scheduler.install(root, read_config(root))
    except WikiError:
        # Consent stands -- the user gave it -- and manual sync works; only the clock is missing.
        write_json(state_path(root, "worker.json"), {"enabled": False, "scheduler": "none",
                                                     "installed_at": None, "stopped_at": None})
        raise
    # Nothing is owed at install: the slot that has already passed today belongs
    # to before the clock existed. The next saved time is the first one served.
    served = latest_slot(read_config(root), now())
    write_json(state_path(root, "worker.json"), {"enabled": True, **installed,
                                                 "installed_at": now().isoformat(), "stopped_at": None,
                                                 "last_scheduled_slot": served.isoformat() if served else None})
    return {"started": True, "consented": True, "first_batch": first_batch, **installed}


def stop(root: Path, *, scheduler) -> dict:
    """Turn the clock off and remember that; content, consent and manual sync stay.

    No notebook lock here: the batch the job itself started may be holding it,
    and stopping that batch is the point. Removing the job terminates it, and
    the worker file is a single atomic write.
    """
    root = root.resolve()
    scheduler.uninstall(root)
    state = {**worker_state(root), "enabled": False, "stopped_at": now().isoformat()}
    write_json(state_path(root, "worker.json"), state)
    return state


def _selected_sources(root: Path, selector: str) -> dict:
    sources = subscriptions(root)
    if selector:
        if selector not in sources or not sources[selector].get("enabled"):
            raise WikiError("Requested subscription is missing or disabled")
        sources = {selector: sources[selector]}
        if sources[selector].get("adapter") == "deferred":
            raise WikiError("This source adapter is deferred to a later milestone")
    return {name: source for name, source in sources.items()
            if source.get("enabled") and source.get("kind") == "codex"}


def run_sync(root: Path, *, source: str = "", dry_run: bool = False, scheduled: bool = False,
             runner=None) -> dict | None:
    """One bounded batch; caller must have recorded explicit source consent.

    `scheduled` is what the background tick passes: run only if a saved time has
    come due since the last scheduled batch, otherwise return None at once, with
    no lock taken and nothing read. Stopped notebooks tick to nothing.
    """
    root = root.resolve()
    if scheduled:
        worker = worker_state(root)
        if not worker.get("enabled"):
            return None
        slot = latest_slot(read_config(root), now())
        served = worker.get("last_scheduled_slot")
        if slot is None or (served and datetime.fromisoformat(served) >= slot):
            return None
        record = run_sync(root, source=source, runner=runner)
        # Any recorded outcome serves the slot; a refusal to start (busy) raised
        # above this line and leaves it owed for the next tick.
        write_json(state_path(root, "worker.json"), {**worker_state(root), "last_scheduled_slot": slot.isoformat()})
        return record
    if dry_run:
        progress = read_json(state_path(root, "progress.json"), {})
        return {"dry_run": True, "sources": {
            name: pending_metadata(sub, progress.get(name, {}))
            for name, sub in _selected_sources(root, source).items()}}
    if not state_path(root, "consent.json").is_file():
        raise WikiError("Source access is not authorized yet; run `co wiki start` to review and confirm it")
    with maintenance_lock(root), _terminate_as_interrupt():
        config = validate(read_config(root))
        selected = _selected_sources(root, source)
        progress = read_json(state_path(root, "progress.json"), {})
        if not isinstance(progress, dict):
            raise WikiError("Invalid source progress; preserve it for diagnosis")
        return _sync_locked(root, selected, progress, config, runner)


@contextmanager
def _terminate_as_interrupt():
    """`launchctl bootout` (and `co wiki stop`) end a running batch with SIGTERM.

    Left to the default action the process dies mid-write and the run record
    stays "running" forever. Raising KeyboardInterrupt instead routes SIGTERM
    through the same path as Ctrl-C: the record is closed as interrupted, the
    checkpoint is not advanced. Only the main thread may own signal handlers.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.getsignal(signal.SIGTERM)

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _sync_locked(root, selected, progress, config, runner):
    from .runner import maintenance_instructions, run_codex, tool_specs

    items, updated, seen = [], dict(progress), set()
    limits = config["limits"]
    remaining = limits["input_chars_per_batch"] - len(maintenance_instructions()) - len(json.dumps(tool_specs())) - 1000
    if remaining <= 0:
        raise WikiError("Configured input limit is too small for the maintenance Skill")
    remaining = remaining * 2 // 3  # Leave room for reading existing notebook context.
    for name, subscription in selected.items():
        if len(items) >= limits["items_per_batch"] or remaining <= 0:
            break
        batch = collect(subscription, progress.get(name, {}), limits["items_per_batch"] - len(items), remaining)
        for item in batch.items:
            if item["source"] not in seen:
                items.append(item)
                seen.add(item["source"])
                remaining -= len(json.dumps(item, ensure_ascii=False))
        updated[name] = batch.progress
    record = {"id": "run_" + uuid.uuid4().hex, "started_at": now().isoformat(),
              "model": config["model"], "sources": list(selected), "items": len(items),
              "runner_attempts": 0, "outcome": "no_change", "usage": None, "changed": [], "refused": 0}
    path = state_path(root, f"runs/{record['id']}.json")
    if not items:
        write_json(state_path(root, "progress.json"), updated)
        write_json(path, record)
        return record
    if status(root)["runner_attempts_today"] >= limits["runner_calls_per_day"]:
        raise WikiError("Daily runner-attempt limit reached; source progress was not advanced")
    runner = runner or run_codex
    # A runner may carry a preflight (the native one checks login, binary and
    # version). It raises before an attempt is reserved: a configuration error is
    # not a failed batch and must not spend one of the day's attempts.
    getattr(runner, "preflight", lambda: None)()
    record.update(outcome="running", runner_attempts=1)
    write_json(path, record)  # Reserve the attempt before starting a native process.
    try:
        result = runner(Notebook(root), items, config)
        record.update(outcome="completed", usage=result.get("usage"), changed=result.get("changed", []),
                      refused=result.get("refused", 0), refusals=result.get("refusals", []))
        write_json(state_path(root, "progress.json"), updated)
    except BaseException as error:
        record.update(outcome="interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "failed",
                      usage=getattr(error, "usage", None), changed=getattr(error, "changed", []),
                      error=str(error) if isinstance(error, WikiError) else "Runner failed; source progress preserved")
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        record["finished_at"] = now().isoformat()
        write_json(path, record)
    return record
