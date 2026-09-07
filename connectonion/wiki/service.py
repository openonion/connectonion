"""Foreground maintenance core. Background lifecycle is a separate milestone."""

import hashlib
import json
import os
import re
import uuid
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


def status(root: Path) -> dict:
    config = read_config(root)
    saved_zone = config.get("schedule", {}).get("timezone", "")
    zone = ZoneInfo(saved_zone) if saved_zone else timezone.utc
    today = now().astimezone(zone).date()
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
    return {"state": "Not started — background worker not implemented in this milestone",
            "root": str(root), "configured": (root / "config.yaml").exists(),
            "date": str(today), "timezone": saved_zone or "Unknown (UTC reporting fallback only)",
            "schedule_times": config.get("schedule", {}).get("times", []), "next_run": None,
            "batches_today": len(recent), "runner_attempts_today": len(attempted),
            "usage_today": usage, "usage_coverage": coverage,
            "last_run": logs[0] if logs else None}


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


def run_sync(root: Path, *, source: str = "", dry_run: bool = False, runner=None) -> dict:
    """Internal foreground entry; caller must have recorded explicit source consent."""
    root = root.resolve()
    if dry_run:
        progress = read_json(state_path(root, "progress.json"), {})
        return {"dry_run": True, "sources": {
            name: pending_metadata(sub, progress.get(name, {}))
            for name, sub in _selected_sources(root, source).items()}}
    if not state_path(root, "consent.json").is_file():
        raise WikiError("Source access is not authorized; the start/consent workflow is not shipped yet")
    with maintenance_lock(root):
        config = validate(read_config(root))
        selected = _selected_sources(root, source)
        progress = read_json(state_path(root, "progress.json"), {})
        if not isinstance(progress, dict):
            raise WikiError("Invalid source progress; preserve it for diagnosis")
        return _sync_locked(root, selected, progress, config, runner)


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
              "runner_attempts": 0, "outcome": "no_change", "usage": None, "changed": []}
    path = state_path(root, f"runs/{record['id']}.json")
    if not items:
        write_json(state_path(root, "progress.json"), updated)
        write_json(path, record)
        return record
    if status(root)["runner_attempts_today"] >= limits["runner_calls_per_day"]:
        raise WikiError("Daily runner-attempt limit reached; source progress was not advanced")
    record.update(outcome="running", runner_attempts=1)
    write_json(path, record)  # Reserve the attempt before starting a native process.
    try:
        result = (runner or run_codex)(Notebook(root), items, config)
        record.update(outcome="completed", usage=result.get("usage"), changed=result.get("changed", []))
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
