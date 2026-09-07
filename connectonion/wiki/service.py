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
from .mail import collect_mail
from .source import KINDS, collect, pending_metadata

MAIL_KINDS = ("gmail", "outlook")


def mail_client(kind: str):
    """The live client for a mail kind; tests replace this with a fake."""
    if kind == "outlook":
        from ..useful_tools.outlook import Outlook
        return Outlook()
    from ..useful_tools.gmail import Gmail
    return Gmail()


def mail_available(kind: str) -> bool:
    """Whether existing co authentication can read this mailbox; never starts a login."""
    if kind == "outlook":
        scopes = os.getenv("MICROSOFT_SCOPES", "")
        return any(scope.startswith("Mail.") for scope in scopes.replace(",", " ").split())
    try:
        from ..useful_tools.google_scopes import granted_scopes
        return bool(granted_scopes() & {"gmail.readonly", "gmail.modify", "https://mail.google.com/"})
    except Exception:  # noqa: BLE001 - absent or unreadable credentials mean "not available", not a crash
        return False


def now() -> datetime:
    return datetime.now(timezone.utc)


def codex_sessions_root() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser().resolve() / "sessions"


def claude_projects_root() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))).expanduser().resolve() / "projects"


# How far back a first start reads, and the most a custom scope may ask for.
# Two months is enough history for the notebook to have a shape on day one;
# coding sessions older than half a year describe work that has moved on, while
# mail keeps its value for years (people, commitments, what was agreed).
DEFAULT_LOOKBACK_DAYS = 60
MAX_LOOKBACK_DAYS = {"codex": 180, "claude-code": 180, "gmail": 730, "outlook": 730}


def subscriptions(root: Path) -> dict:
    saved = read_json(state_path(root, "subscriptions.json"), {})
    if not isinstance(saved, dict):
        raise WikiError("Invalid subscriptions file; preserve it for diagnosis")
    since = (now() - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()
    defaults = {
        "codex": {"id": "codex", "kind": "codex", "root": str(codex_sessions_root()),
                  "project": None, "since": since, "max_lookback_days": MAX_LOOKBACK_DAYS["codex"],
                  "enabled": True, "consented": False, "adapter": "available"},
        "claude-code": {"id": "claude-code", "kind": "claude-code", "root": str(claude_projects_root()),
                        "project": None, "since": since, "max_lookback_days": MAX_LOOKBACK_DAYS["claude-code"],
                        "enabled": True, "consented": False, "adapter": "available"},
        "gmail": {"id": "gmail", "kind": "gmail", "since": since, "max_lookback_days": MAX_LOOKBACK_DAYS["gmail"],
                  "exclude_automated": True, "enabled": False, "consented": False,
                  "adapter": "available" if mail_available("gmail") else "waiting for co auth google"},
        "outlook": {"id": "outlook", "kind": "outlook", "since": since, "max_lookback_days": MAX_LOOKBACK_DAYS["outlook"],
                    "exclude_automated": True, "enabled": False, "consented": False,
                    "adapter": "available" if mail_available("outlook") else "waiting for co auth microsoft"},
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
            if (source.get("kind") in KINDS or source.get("kind") in MAIL_KINDS) and source.get("enabled"):
                source["consented"] = True
        write_json(state_path(root, "subscriptions.json"), sources)
        write_json(state_path(root, "consent.json"), {"authorized_at": now().isoformat()})


def toggle_source(root: Path, name: str, enabled: bool, *, project: str = "", since: str = "7d") -> str:
    """Store a choice, not permission to read bodies or run the model."""
    with maintenance_lock(root):
        sources = subscriptions(root)
        if project:
            if name != "codex" or not re.fullmatch(r"[1-9]\d*d", since):
                raise WikiError("Custom scopes require codex and a lookback such as 60d")
            days, cap = int(since[:-1]), MAX_LOOKBACK_DAYS["codex"]
            if days > cap:
                raise WikiError(f"Lookback for codex sessions is capped at {cap} days; use --since {cap}d or less")
            project = str(Path(project).expanduser().resolve())
            name = "codex-" + hashlib.sha256(project.encode()).hexdigest()[:12]
            if name not in sources:
                sources[name] = {**sources["codex"], "id": name, "project": project,
                                 "consented": False,
                                 "since": (now() - timedelta(days=days)).isoformat()}
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
        elif source.get("kind") in KINDS:
            state = "will be read" if Path(source["root"]).is_dir() else "directory missing"
        elif source.get("kind") in MAIL_KINDS:
            state = "will be read (automated senders skipped)" if source.get("adapter") == "available" else source["adapter"]
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
            if source.get("enabled") and (source.get("kind") in KINDS or source.get("kind") in MAIL_KINDS)}


def run_sync(root: Path, *, source: str = "", dry_run: bool = False, scheduled: bool = False,
             all_pending: bool = False, runner=None, extractor=None, _uncapped: bool = False) -> dict | None:
    """One bounded batch; caller must have recorded explicit source consent.

    `scheduled` is what the background tick passes: run only if a saved time has
    come due since the last scheduled batch, otherwise return None at once, with
    no lock taken and nothing read. Stopped notebooks tick to nothing.

    `all_pending` is the backfill: batch after batch, oldest material first,
    until nothing is pending. It is user-initiated and explicit, so the daily
    attempt cap -- a guard against unattended runaway -- does not apply; a
    failed batch stops it, as does a refusal to start.
    """
    root = root.resolve()
    if all_pending:
        records = []
        while True:
            record = run_sync(root, source=source, runner=runner, extractor=extractor, _uncapped=True)
            if record["outcome"] == "no_change":
                break
            records.append(record)
            if record["outcome"] != "completed":
                break
        outcome = "caught_up" if not records or records[-1]["outcome"] == "completed" else records[-1]["outcome"]
        return {"outcome": outcome, "batches": len(records), "items": sum(r["items"] for r in records),
                "changed": sorted({path for r in records for path in r.get("changed", [])}),
                "usage": {key: sum((r.get("usage") or {}).get(key, 0) for r in records)
                          for key in ("input_tokens", "output_tokens", "cached_input_tokens")},
                "runs": [r["id"] for r in records]}
    if scheduled:
        worker = worker_state(root)
        if not worker.get("enabled"):
            return None
        slot = latest_slot(read_config(root), now())
        served = worker.get("last_scheduled_slot")
        if slot is None or (served and datetime.fromisoformat(served) >= slot):
            return None
        record = run_sync(root, source=source, runner=runner, extractor=extractor)
        # Any recorded outcome serves the slot; a refusal to start (busy) raised
        # above this line and leaves it owed for the next tick.
        write_json(state_path(root, "worker.json"), {**worker_state(root), "last_scheduled_slot": slot.isoformat()})
        return record
    if dry_run:
        progress = read_json(state_path(root, "progress.json"), {})
        return {"dry_run": True, "sources": {
            name: (pending_metadata(sub, progress.get(name, {})) if sub.get("kind") in KINDS
                   else {"candidate_files": None, "message_count": None, "body_reads": False,
                         "source_available": mail_available(sub["kind"]),
                         "cursor": progress.get(name, {}).get("cursor") or sub.get("since")})
            for name, sub in _selected_sources(root, source).items()}}
    if not state_path(root, "consent.json").is_file():
        raise WikiError("Source access is not authorized yet; run `co wiki start` to review and confirm it")
    with maintenance_lock(root), _terminate_as_interrupt():
        config = validate(read_config(root))
        selected = _selected_sources(root, source)
        progress = read_json(state_path(root, "progress.json"), {})
        if not isinstance(progress, dict):
            raise WikiError("Invalid source progress; preserve it for diagnosis")
        return _sync_locked(root, selected, progress, config, runner, extractor, uncapped=_uncapped)


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


def _sync_locked(root, selected, progress, config, runner, extractor=None, *, uncapped=False):
    from .extract import NOTHING, extraction_instructions, extraction_item, run_extract
    from .runner import maintenance_instructions, run_codex, tool_specs

    items, updated, seen, counts = [], dict(progress), set(), {}
    limits = config["limits"]
    # A batch is gathered against the extraction budget: large, because the
    # tool-less extraction pass reads it once. A batch that fits items_per_batch
    # is small enough for the maintainer to read directly and skips extraction.
    maintain_room = limits["input_chars_per_batch"] - len(maintenance_instructions()) - len(json.dumps(tool_specs())) - 1000
    if maintain_room <= 0:
        raise WikiError("Configured input limit is too small for the maintenance Skill")
    remaining = max(limits["extract_chars_per_batch"] - len(extraction_instructions()) - 1000, maintain_room * 2 // 3)
    max_items = limits["extract_items_per_batch"]
    for name, subscription in selected.items():
        if len(items) >= max_items or remaining <= 0:
            break
        if subscription.get("kind") in MAIL_KINDS:
            batch = collect_mail(subscription, progress.get(name, {}), max_items - len(items),
                                 remaining, mail_client(subscription["kind"]))
        else:
            batch = collect(subscription, progress.get(name, {}), max_items - len(items), remaining)
        for item in batch.items:
            if item["source"] not in seen:
                items.append(item)
                seen.add(item["source"])
                counts[name] = counts.get(name, 0) + 1
                remaining -= len(json.dumps(item, ensure_ascii=False))
        updated[name] = batch.progress
    record = {"id": "run_" + uuid.uuid4().hex, "started_at": now().isoformat(),
              "model": config["model"], "sources": list(selected), "items": len(items),
              "runner_attempts": 0, "outcome": "no_change", "usage": None, "changed": [], "refused": 0,
              "extracted": len(items) > limits["items_per_batch"],
              # Where the tokens went, kept raw so the cost of a stage, a source or a
              # model can be computed later from the records rather than remembered.
              "usage_by_stage": {}, "items_by_source": counts,
              "chars_in": sum(len(json.dumps(item, ensure_ascii=False)) for item in items), "seconds": None}
    path = state_path(root, f"runs/{record['id']}.json")
    if not items:
        write_json(state_path(root, "progress.json"), updated)
        write_json(path, record)
        return record
    if not uncapped and status(root)["runner_attempts_today"] >= limits["runner_calls_per_day"]:
        raise WikiError("Daily runner-attempt limit reached; source progress was not advanced")
    runner = runner or run_codex
    # A runner may carry a preflight (the native one checks login, binary and
    # version). It raises before an attempt is reserved: a configuration error is
    # not a failed batch and must not spend one of the day's attempts.
    getattr(runner, "preflight", lambda: None)()
    record.update(outcome="running", runner_attempts=2 if record["extracted"] else 1)
    write_json(path, record)  # Reserve the attempts before starting a native process.
    try:
        usage = {}
        if record["extracted"]:
            digest = (extractor or run_extract)(items, config)
            usage = dict(digest.get("usage") or {})
            record["usage_by_stage"]["extract"] = digest.get("usage")
            notes = digest["notes"].strip()
            items = [] if notes == NOTHING else [extraction_item(notes, items)]
        if items:
            result = runner(Notebook(root), items, config)
            record["usage_by_stage"]["maintain"] = result.get("usage")
            for key, value in (result.get("usage") or {}).items():
                usage[key] = usage.get(key, 0) + value
        else:
            result = {"changed": [], "report": NOTHING}
        record.update(outcome="completed", usage=usage or None, changed=result.get("changed", []),
                      refused=result.get("refused", 0), refusals=result.get("refusals", []),
                      report=result.get("report", ""))
        write_json(state_path(root, "progress.json"), updated)
    except BaseException as error:
        record.update(outcome="interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "failed",
                      usage=getattr(error, "usage", None), changed=getattr(error, "changed", []),
                      error=str(error) if isinstance(error, WikiError) else "Runner failed; source progress preserved")
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        record["finished_at"] = now().isoformat()
        record["seconds"] = round((datetime.fromisoformat(record["finished_at"])
                                   - datetime.fromisoformat(record["started_at"])).total_seconds(), 1)
        write_json(path, record)
    return record


def usage_report(root: Path, days: int | None = None) -> dict:
    """Where the tokens went, computed from the raw run records.

    Totals, then by stage (extract / maintain), by model, and by source -- a
    run's tokens are attributed to its sources in proportion to the items each
    contributed, which is the honest split when one batch mixes sources. The
    derived rates (tokens per item, per 1k input characters) are what say which
    part is expensive and whether a change made it cheaper.
    """
    root = root.resolve()
    since = now() - timedelta(days=days) if days else None
    runs = [r for r in run_logs(root) if r.get("usage")
            and (since is None or datetime.fromisoformat(r["started_at"]) >= since)]
    keys = ("input_tokens", "output_tokens", "cached_input_tokens")

    def add(target, usage, factor=1.0):
        for key in keys:
            if isinstance((usage or {}).get(key), (int, float)):
                target[key] = round(target.get(key, 0) + usage[key] * factor)

    total, by_stage, by_model, by_source = {}, {}, {}, {}
    chars_by_model, items_by_source = {}, {}
    for run in runs:
        add(total, run["usage"])
        for stage, usage in (run.get("usage_by_stage") or {}).items():
            add(by_stage.setdefault(stage, {}), usage)
        model = run.get("model", "?")
        add(by_model.setdefault(model, {}), run["usage"])
        chars_by_model[model] = chars_by_model.get(model, 0) + (run.get("chars_in") or 0)
        shares = run.get("items_by_source") or {}
        total_items = sum(shares.values()) or 1
        for source, count in shares.items():
            add(by_source.setdefault(source, {}), run["usage"], count / total_items)
            items_by_source[source] = items_by_source.get(source, 0) + count
    for source, table in by_source.items():
        table["items"] = items_by_source[source]
        table["input_tokens_per_item"] = round(table.get("input_tokens", 0) / max(items_by_source[source], 1), 1)
    for model, table in by_model.items():
        table["chars_in"] = chars_by_model[model]
        table["input_tokens_per_1k_chars"] = round(table.get("input_tokens", 0) / max(chars_by_model[model] / 1000, 0.001), 1)
    return {"runs": len(runs), "days": days, "total": total, "by_stage": by_stage,
            "by_model": by_model, "by_source": by_source}
