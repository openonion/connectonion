"""Foreground maintenance core. Background lifecycle is a separate milestone."""

import hashlib
import json
import os
import re
import signal
import socket
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import prepare, read_config, validate
from .files import Notebook, RemError, maintenance_lock, read_json, state_path, write_json
from .mail import collect_mail
from .mail_archive import archive_state, resume_stalled
from .chat import CHAT_KINDS, chat_home, collect_chat
from .source import KINDS, collect, pending_metadata, timestamp

MAIL_KINDS = ("gmail", "outlook")


def mail_client(kind: str, *, attachments: bool = False):
    """The live client for a mail kind; tests replace this with a fake.

    `attachments=True` lets the client save files outside its own sandbox
    root: co rem downloads a subject's contracts and decks into the
    notebook's .state, which is operator territory, not an agent's.
    """
    if kind == "outlook":
        from ..useful_tools.outlook import Outlook
        return Outlook(allow_external_attachments=attachments)
    from ..useful_tools.gmail import Gmail
    return Gmail(allow_external_attachments=attachments)


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
MAX_LOOKBACK_DAYS = {"codex": 180, "claude-code": 180, "gmail": 730, "outlook": 730, "whatsapp": 730}
# Every kind a subscription can be consented for and read.
READABLE = (*KINDS, *MAIL_KINDS, *CHAT_KINDS)


def subscriptions(root: Path) -> dict:
    saved = read_json(state_path(root, "subscriptions.json"), {})
    if not isinstance(saved, dict):
        raise RemError("Invalid subscriptions file; preserve it for diagnosis")
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
        # Off until the user names a chat: a linked device sees every group the
        # number is in, and nothing is read from a chat nobody chose.
        "whatsapp": {"id": "whatsapp", "kind": "whatsapp", "root": str(chat_home("whatsapp")), "chats": [],
                     "since": since, "max_lookback_days": MAX_LOOKBACK_DAYS["whatsapp"],
                     "enabled": False, "consented": False,
                     "adapter": "available" if (chat_home("whatsapp") / "received.jsonl").is_file()
                     else "waiting for co whatsapp listen"},
    }
    defaults.update(saved)
    return defaults


def subscribe_read_mail(root: Path, kinds) -> list[str]:
    """Mailboxes init has just read are the ones the daily round should read.

    They were left switched off, so `start`'s summary listed the very mailboxes
    the map was built from as "unsubscribed" and the daily round never read
    mail at all (#1943). This is a choice, not consent: `consented` stays as it
    was, and nothing is read in the background until `start` is approved. A
    mailbox the user unsubscribed stays unsubscribed.
    """
    changed = []
    with maintenance_lock(root):
        sources = subscriptions(root)
        for kind in kinds:
            source = sources.get(kind)
            if not source or source.get("unsubscribed") or source.get("enabled"):
                continue
            source["enabled"] = True
            changed.append(kind)
        if changed:
            write_json(state_path(root, "subscriptions.json"), sources)
    return changed


def approve_sources(root: Path) -> None:
    """Internal consent handoff for tests/future start; never called by inspection."""
    with maintenance_lock(root):
        prepare(root)
        validate(read_config(root))
        sources = subscriptions(root)
        for source in sources.values():
            if source.get("kind") in READABLE and source.get("enabled"):
                source["consented"] = True
        write_json(state_path(root, "subscriptions.json"), sources)
        write_json(state_path(root, "consent.json"), {"authorized_at": now().isoformat(),
                                                      "summary": summary_fingerprint(root)})


def summary_fingerprint(root: Path) -> str:
    """What the user agreed to, as one value: every line the consent summary shows.

    Consent used to be a bare timestamp, so after `stop`, switching the runner
    from Codex to Claude Code, `start` reinstalled the job without showing the
    summary and ignored the `n` typed at it. Recording what was shown lets
    `start` ask again whenever the sources, runner, model, permissions or
    schedule are no longer what the user said yes to.
    """
    shown = json.dumps(consent_summary(root), sort_keys=True, default=str)
    return hashlib.sha256(shown.encode()).hexdigest()


def toggle_source(root: Path, name: str, enabled: bool, *, project: str = "", about: str = "",
                  since: str = "7d", chats=()) -> str:
    """Store a choice, not permission to read bodies or run the model.

    A scope -- one directory, or one subject -- is a subscription of its own with its
    own cursor, so it neither consumes the main source's material nor re-reads its own
    on every pass. Subject scopes exist because directory scopes cannot do this work on
    a real machine: 701 of 830 Codex sessions over six months, and 24 of 26 Claude Code
    ones, ran in the same workspace directory.
    """
    with maintenance_lock(root):
        sources = subscriptions(root)
        if project or about:
            if name not in KINDS:
                raise RemError(f"A scope narrows a coding source ({', '.join(KINDS)}), not {name}")
            days = window_days(since, name)
            if project:
                project = str(Path(project).expanduser().resolve())
                scope = "dir-" + hashlib.sha256(project.encode()).hexdigest()[:12]
            else:
                about = " ".join(about.split()).lower()
                scope = "about-" + re.sub(r"[^a-z0-9]+", "-", about).strip("-")[:40]
                if not scope.strip("about-"):
                    raise RemError("A subject scope needs a word to match, such as --about browser")
            base, name = name, f"{name}-{scope}"
            if name not in sources:
                sources[name] = {**sources[base], "id": name, "project": project or None,
                                 "about": about or None, "consented": False,
                                 "since": (now() - timedelta(days=days)).isoformat()}
        if name not in sources:
            raise RemError(f"No source called {name!r}; the sources are gmail, outlook, codex, claude-code and whatsapp, and `co rem sources` lists the ones saved here")
        if chats:
            if sources[name].get("kind") not in CHAT_KINDS:
                raise RemError(f"--chat names a chat in {', '.join(CHAT_KINDS)}, not in {name}")
            current = set(sources[name].get("chats") or [])
            chosen = current | set(chats) if enabled else current - set(chats)
            if chosen - current:
                # A new chat is material the user has not agreed to have read.
                # The next `start` shows the summary again before anything is.
                sources[name]["consented"] = False
            sources[name]["chats"] = sorted(chosen)
            enabled = bool(chosen)
        elif enabled and sources[name].get("kind") in CHAT_KINDS and not sources[name].get("chats"):
            raise RemError("Name the chats to read: --chat <id>, from `co whatsapp chats`")
        sources[name]["enabled"] = enabled
        # "Never subscribed" and "the user said stop" both read as enabled=False;
        # only the second forbids an explicit investigation from reading it.
        sources[name]["unsubscribed"] = not enabled
        write_json(state_path(root, "subscriptions.json"), sources)
    return name


WINDOW = re.compile(r"(\d+)\s*([dwmy])", re.IGNORECASE)
WINDOW_DAYS = {"d": 1, "w": 7, "m": 30, "y": 365}


def window_days(value: str, kind: str) -> int:
    """`3d`, `2w`, `6m`, `1y` as a number of days, within the cap for this kind."""
    match = WINDOW.fullmatch((value or "").strip())
    if not match:
        raise RemError("A window looks like 7d, 3w, 6m or 1y")
    days = int(match.group(1)) * WINDOW_DAYS[match.group(2).lower()]
    cap = MAX_LOOKBACK_DAYS.get(kind, DEFAULT_LOOKBACK_DAYS)
    if days > cap:
        raise RemError(f"How far back this source may be read is capped at {cap} days; ask for less")
    if days < 1:
        raise RemError("A window has to be at least one day")
    return days


def set_window(root: Path, name: str, value: str, *, narrow: bool = False, force: bool = False) -> dict:
    """How far back a source is read, as coverage rather than replacement.

    "At least three days of Claude Code" is what a person asks for, and it is not the
    same as "only three days": the window is widened when it has to be and a wider one
    is left alone. Narrowing is the destructive direction -- material between the old
    edge and the new one is dropped unread, and no cursor brings it back -- so it takes
    `--only` to mean it and `--force` to accept the loss.
    """
    with maintenance_lock(root):
        sources = subscriptions(root)
        if name not in sources:
            raise RemError(f"No source called {name!r}; the sources are gmail, outlook, codex, claude-code and whatsapp, and `co rem sources` lists the ones saved here")
        days = window_days(value, sources[name].get("kind", name))
        since = now() - timedelta(days=days)
        current = sources[name].get("since")
        covered = current and timestamp(current) <= since
        if covered and not narrow:
            return {"subscription": name, "since": current, "days": days, "changed": False,
                    "note": f"already reads back to {current[:10]}, further than {days} days"}
        if covered and narrow and not force:
            raise RemError(f"Narrowing from {current[:10]} to {days} days drops what lies between, unread "
                            f"and unrecoverable. Repeat with --force to accept that")
        sources[name] = {**sources[name], "since": since.isoformat()}
        write_json(state_path(root, "subscriptions.json"), sources)
    return {"subscription": name, "since": sources[name]["since"], "days": days, "changed": True}


def run_logs(root: Path, run_id: str = "") -> list[dict]:
    if run_id:
        if not re.fullmatch(r"run_[0-9a-f]{32}", run_id):
            raise RemError("Unknown run ID; use an ID from the logs listing")
        path = state_path(root, f"runs/{run_id}.json")
        if not path.is_file():
            raise RemError("Run not found; inspect logs for a current run ID")
        paths = [path]
    else:
        directory = state_path(root, "runs")
        paths = [state_path(root, f"runs/{p.name}") for p in directory.glob("run_*.json")]
    records = [read_json(path, {}) for path in paths]
    if any(not isinstance(record, dict) or "started_at" not in record for record in records):
        raise RemError("Invalid run log; preserve it for diagnosis")
    return sorted(records, key=lambda record: record["started_at"], reverse=True)


def running_marker() -> dict:
    """Which process a "running" record belongs to, so a later run can tell it died."""
    return {"pid": os.getpid(), "host": socket.gethostname()}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # another user's process: alive, not ours to judge
        return True
    return True


def seen_outcome(record: dict) -> str:
    """A run's outcome as it is now, without writing: "running" whose process on
    this machine is gone reads "interrupted" at once (#2008). A Ctrl-C'd run
    showed "running" in status until the next command that writes runs."""
    outcome = record.get("outcome", "unknown")
    if (outcome == "running" and record.get("pid") and record.get("host") == socket.gethostname()
            and not _alive(int(record["pid"]))):
        return "interrupted"
    return outcome


def abandon_stale_runs(root: Path) -> list[str]:
    """Mark "running" records whose run can no longer finish as abandoned, with why (#1974).

    A run killed outright (SIGKILL, a sleep that never woke the process, a
    closed laptop lid mid-turn) never closes its record, and the owner's
    notebook showed two runs "running" for days. On this machine a record
    names its process, so a dead one is certain; a record from before that, or
    from another machine, is abandoned once it is older than the runner
    timeout times its attempts, plus an hour for gathering. Called by the
    commands that write runs; status and logs stay read-only.
    """
    timeout = read_config(root)["limits"]["timeout_seconds"]
    host, moment, closed = socket.gethostname(), now(), []
    for path in state_path(root, "runs").glob("run_*.json"):
        record = read_json(path, {})
        if not isinstance(record, dict) or record.get("outcome") != "running":
            continue
        if record.get("pid") and record.get("host") == host:
            if _alive(int(record["pid"])):
                continue
            reason = f"its process ({record['pid']}) is no longer running; it was killed or the machine restarted"
        else:
            last = datetime.fromisoformat(record.get("stage_updated_at") or record["started_at"])
            limit = timedelta(seconds=timeout * (max(int(record.get("runner_attempts") or 0), 1) + 1) + 3600)
            if moment - last < limit:
                continue
            reason = (f"no progress for {int((moment - last).total_seconds() // 3600)} h, past its runner "
                      f"timeout ({timeout} s a call); it was killed or the machine slept through it")
        record.update(outcome="abandoned", reason=reason, finished_at=record.get("finished_at") or moment.isoformat())
        write_json(path, record)
        closed.append(record.get("id", path.stem))
    return closed


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
        return "Not started — run `co rem start` to authorize sources and begin", None
    worker = worker_state(root)
    if worker.get("enabled") and worker.get("scheduler") == "launchd":
        # worker.json travels with a copied notebook; the job it describes runs
        # the original's --root. A copy said "Running in background" and doctor
        # said "ok schedule" for a schedule that never ran it (#1964).
        from .schedule import Launchd
        launcher = Launchd()
        if not launcher.installed(root):
            return ("Not scheduled here — the saved schedule belongs to another notebook or was removed; "
                    "`co rem start` schedules this one"), None
        if sys.platform == "darwin":
            launched = launcher.describe(root)
            if not launched["loaded"]:
                return "Background needs attention — launchd job is not loaded; run `co rem start`", None
            if launched.get("last_exit_code") not in (None, "0", "(never exited)"):
                return ("Background needs attention — last launchd exit code "
                        f"{launched['last_exit_code']}; run `co rem doctor`"), None
    if worker.get("enabled"):
        slot = next_slot(config, zone)
        if worker.get("last_scheduled_warning") or worker.get("last_scheduled_outcome") == "failed":
            reason = (worker.get("last_scheduled_reason") if worker.get("last_scheduled_outcome") == "failed"
                      else worker.get("last_scheduled_warning"))
            return ("Background needs attention — " + (reason or "the last scheduled pass failed")
                    + "; run `co rem logs`"), slot
        return f"Running in background ({worker.get('scheduler', 'scheduler')}); next slot {slot or 'unknown'}", slot
    return "Stopped — background maintenance is off; `co rem sync` works by hand, `co rem start` resumes", None


def mailbox_state(kind: str, source: dict) -> tuple[str, str]:
    """(what is true of this mailbox for the daily round, the command that changes it or '').

    Notebooks made before init subscribed its mailboxes (#1946) had Gmail
    connected but switched off, and doctor said "connected" while the round
    read no mail at all (#1974). Connected, subscribed and approved are three
    facts, each with its own fix.
    """
    provider = "google" if kind == "gmail" else "microsoft"
    if not mail_available(kind):
        return "not connected", f"co auth {provider}"
    if source.get("unsubscribed"):
        return "removed by you; investigate and the daily round leave it alone", ""
    if not source.get("enabled"):
        return "connected, but not read by the daily round (not subscribed)", f"co rem sources add {kind}"
    if not source.get("consented"):
        return "subscribed, waiting for your approval", "co rem start"
    return "read by the daily round", ""


def status(root: Path, *, live_quota: bool = False) -> dict:
    """`live_quota` reads the Codex meter now (#1843). Only `co rem status` asks:
    the round and sync call this inside the lock, where a Codex process per
    call would only slow them."""
    config = read_config(root)
    saved_zone = config.get("schedule", {}).get("timezone", "")
    zone = notebook_zone(config)
    state, slot = _state_line(root, config, zone)
    logs = run_logs(root)
    today, recent = runs_today(logs, zone)
    attempted = [record for record in recent if record.get("runner_attempts", 0)]
    # Every run that called a model: an `investigate` records no runner
    # attempts, and its tokens were missing from the day's total (#2008).
    from .quota import INVESTIGATION_PHASES
    model_runs = [record for record in recent if record.get("runner_attempts", 0)
                  or record.get("phase") in INVESTIGATION_PHASES or record.get("usage")]
    usage = {}
    coverage = {}
    for key in ("input_tokens", "output_tokens", "cached_input_tokens"):
        values = [(record.get("usage") or {}).get(key) for record in model_runs]
        known = [value for value in values if type(value) is int and value >= 0]
        # One run without usage no longer turns the day into "unknown": the
        # known runs are summed and the rest counted (runs_without_usage).
        usage[key] = sum(known) if known else None
        coverage[key] = {"known_runs": len(known), "model_runs": len(model_runs)}
    usage["runs_without_usage"] = sum(type((record.get("usage") or {}).get("input_tokens")) is not int
                                      for record in model_runs)
    return {"state": state,
            "root": str(root), "configured": (root / "config.yaml").exists(),
            "date": str(today), "timezone": saved_zone or "Unknown (UTC reporting fallback only)",
            "schedule_times": config.get("schedule", {}).get("times", []), "next_run": slot,
            "worker": worker_state(root),
            # A run the cap refused is recorded so logs can show it (#1957); it read nothing.
            "batches_today": sum(record.get("outcome") != "refused" for record in recent),
            "runner_attempts_today": sum(record.get("runner_attempts", 0) for record in attempted),
            "usage_today": usage, "usage_coverage": coverage,
            "last_run": {**logs[0], "outcome": seen_outcome(logs[0])} if logs else None,
            "mailboxes": _mailbox_lines(root),
            # An unfinished init archive (#2035): investigations ask the servers until it is done.
            **({"mail_archive": archive} if (archive := archive_state(root, now=now())) else {}),
            **(_quota_status(config, logs) if live_quota else {})}


def notebook_zone(config: dict):
    """The notebook's own timezone (schedule.timezone), UTC until one is saved."""
    saved_zone = config.get("schedule", {}).get("timezone", "")
    return ZoneInfo(saved_zone) if saved_zone else timezone.utc


def runs_today(logs: list[dict], zone) -> tuple:
    """(today in the notebook's zone, the runs that started today): the day status and the daily cap count in."""
    today = now().astimezone(zone).date()
    return today, [record for record in logs
                   if datetime.fromisoformat(record["started_at"]).astimezone(zone).date() == today]


def _mailbox_lines(root: Path) -> dict:
    sources = subscriptions(root)
    lines = {}
    for kind in MAIL_KINDS:
        state, fix = mailbox_state(kind, sources.get(kind, {}))
        lines[kind] = f"{state}: {fix}" if fix else state
    return lines


CAP_LIMIT = "Daily runner-attempt limit reached"


def daily_cap(root: Path) -> dict:
    """The day's runner attempts: used, left, and when the count starts again.

    The day is the notebook's own (schedule.timezone), the same day `status`
    counts in, so the reset named here is the one the cap will actually honour.
    """
    config, state = read_config(root), status(root)
    zone = notebook_zone(config)
    midnight = datetime.fromisoformat(state["date"]).replace(tzinfo=zone) + timedelta(days=1)
    limit, used = config["limits"]["runner_calls_per_day"], state["runner_attempts_today"]
    resets = midnight.isoformat(timespec="minutes")
    return {"used": used, "limit": limit, "remaining": max(0, limit - used), "resets_at": resets,
            "note": (f"{max(0, limit - used)} of {limit} runner attempts left today; the count resets "
                     f"{resets}. limits.runner_calls_per_day sets it")}


def _quota_status(config: dict, logs: list[dict]) -> dict:
    from . import quota
    meter = quota.read(config)
    spent = quota.points_spent(logs, meter)
    limits = config["limits"]
    if "unknown" in meter:
        week = f"unknown ({meter['unknown']}); the daily call cap is the only bound"
    else:
        zone = ZoneInfo(config["schedule"]["timezone"]) if config["schedule"]["timezone"] else timezone.utc
        resets = datetime.fromtimestamp(meter["resets_at"], zone).strftime("%a %d %b %H:%M")
        week = f"{meter['used_percent']}% used on {meter['plan']}; resets {resets}"
    # Sentences first for people; the same numbers stay structured for --json.
    return {"codex_week": week,
            "investigation_this_week": (f"{spent} of {limits['investigation_quota_points']} points; "
                                        f"nothing starts once the week is at {limits['quota_floor_percent']}%"),
            "quota": meter, "investigation_quota": {
        "spent_points": spent, "budget_points": limits["investigation_quota_points"],
        "floor_percent": limits["quota_floor_percent"]}}


# Whose account the model is called through, per runner. The line said "your
# own Codex login" whatever the runner was, so a user approving Claude Code
# was told their mail would go somewhere it would not.
MODEL_ROUTE = {
    "codex": "through your own Codex login (no API key, no OpenOnion server)",
    "claude-code": "through your own Claude Code login (no API key, no OpenOnion server)",
    "coai": "through ConnectOnion's own agent loop: a co/ model goes through OpenOnion's "
            "server on your OpenOnion account, any other model through your own provider key",
}


def offered_mailboxes(root: Path) -> list[str]:
    """Connected mailboxes the round does not read and the owner never removed: `start` offers them (#1974)."""
    sources = subscriptions(root)
    return [kind for kind in MAIL_KINDS if mail_available(kind)
            and not sources.get(kind, {}).get("enabled") and not sources.get(kind, {}).get("unsubscribed")]


def consent_summary(root: Path) -> dict:
    """Everything `start` must show before a single source body is read."""
    from .runner import CONFINEMENT
    config = read_config(root)
    sources = {}
    offered = offered_mailboxes(root)
    for name, source in subscriptions(root).items():
        if source.get("adapter") == "deferred":
            state = "not implemented yet"
        elif name in offered:
            state = ("connected; read from now on if you approve (automated senders skipped). "
                     f"Keep it out with co rem sources remove {name}")
        elif not source.get("enabled"):
            state = "unsubscribed"
        elif source.get("kind") in KINDS:
            state = "will be read" if Path(source["root"]).is_dir() else "directory missing"
        elif source.get("kind") in MAIL_KINDS:
            state = "will be read (automated senders skipped)" if source.get("adapter") == "available" else source["adapter"]
        elif source.get("kind") in CHAT_KINDS:
            chats = source.get("chats") or []
            state = (f"will read {len(chats)} chat(s), both sides, the agent's own replies left out"
                     if source.get("adapter") == "available" else source["adapter"])
        else:
            state = "waiting"
        sources[name] = {"state": state, "root": source.get("root"), "project": source.get("project"),
                         "since": source.get("since")}
        if source.get("kind") in CHAT_KINDS:
            sources[name]["chats"] = source.get("chats") or []
    return {"root": str(root), "sources": sources, "runner": config["runner"], "model": config["model"],
            "model_receives": "the new session messages plus the notebook pages it reads, "
                              + MODEL_ROUTE[config["runner"]],
            "model_permissions": CONFINEMENT[config["runner"]],
            "schedule": config["schedule"], "limits": config["limits"],
            # RunAtLoad is off (schedule.py): a login runs nothing; a slot missed
            # while asleep runs once at the next five-minute tick.
            "background": "a launchd job under your user at the times above (a time missed while "
                          "asleep runs once on wake); co rem stop removes it"}


def start(root: Path, *, confirm, scheduler, runner=None, run_first_batch: bool = True) -> dict:
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
    # A source subscribed after the first start -- a mailbox, a WhatsApp chat --
    # has not been agreed to. Asking only the first time meant it could never be
    # read; asking again whenever one is waiting means it is read only once shown.
    waiting = [name for name, source in subscriptions(root).items()
               if source.get("enabled") and not source.get("consented") and source.get("kind") in READABLE]
    # A connected mailbox init did not subscribe (notebooks before #1946) is
    # offered, never switched on unasked: it is read only if this is approved.
    offered = offered_mailboxes(root)
    waiting += offered
    # The same holds for everything else the summary shows. A consent recorded
    # before the summary was, has no fingerprint and is asked for once more.
    agreed = read_json(state_path(root, "consent.json"), {}) if not first else {}
    changed = not first and (not isinstance(agreed, dict)
                             or agreed.get("summary") != summary_fingerprint(root))
    if first or waiting or changed:
        if not confirm(consent_summary(root)):
            return {"started": False, "consented": False, "first_batch": None}
        subscribe_read_mail(root, offered)
        approve_sources(root)
    # The first batch runs before the clock is installed: loading a launchd job
    # fires its run-at-load batch immediately, and two batches would race for the
    # notebook lock, with the one the user is watching likely to lose.
    first_batch = run_sync(root, runner=runner) if first and run_first_batch else None
    try:
        installed = scheduler.install(root, read_config(root))
    except RemError:
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
            raise RemError("Requested subscription is missing or disabled")
        sources = {selector: sources[selector]}
        if sources[selector].get("adapter") == "deferred":
            raise RemError("This source adapter is deferred to a later milestone")
    return {name: source for name, source in sources.items()
            if source.get("enabled") and source.get("kind") in READABLE}


PAGES_PER_BATCH = 5


def _maintain_pages(root: Path, items: list[dict], config: dict, kind: str, leads: list[str],
                    say=None) -> dict:
    """Update each page the material concerns in its own turn, and keep going when one fails.

    One turn over the whole notebook edited eight pages at once, spent twenty
    minutes deciding and rewriting, and timed out with nothing saved -- twice,
    on the same real batch. A page per turn is small enough to finish, and a
    refusal costs that page, not the batch.
    """
    from .runner import RunFailed, run_stage
    notebook = Notebook(root)
    usage, changed, refusals, reviews, sizes, growth = {}, [], [], [], [], {}
    say = say or (lambda text: None)
    for record in leads:
        page_items = [{"role": "page", "record": record, "source": "investigation:page", "one_page": True,
                       "timestamp": now().isoformat(),
                       "text": f"The page as it stands, at {record}. Add what the material says about its "
                               f"subject; keep what is right:\n\n{notebook.read(record)}"}, *items]
        try:
            result = run_stage(notebook, page_items, config, kind=kind, stage="maintain", maintenance_lock_held=True)
            changed += result.get("changed", [])
            reviews += result.get("review_candidates", [])
            sizes += [result["instructions_chars"]] if result.get("instructions_chars") else []
            if result.get("page_chars"):
                growth[record] = result["page_chars"]
            part = result.get("usage")
        except RunFailed as error:
            refusals.append({"record": record, "errors": [str(error)[:400]]})
            part = getattr(error, "usage", None)
        # Each page's outcome as it finishes; it was only in the dump at the end (#2044).
        from .daily import outcome_line
        say(outcome_line({"page": record, "outcome": "refused", "why": refusals[-1]["errors"][0]}
                         if refusals and refusals[-1]["record"] == record else
                         {"page": record, "outcome": "accepted" if record in changed else "nothing_new"}))
        for key, value in (part or {}).items():
            usage[key] = usage.get(key, 0) + value
    return {"usage": usage or None, "changed": sorted(set(changed)), "refused": len(refusals),
            "refusals": refusals, "report": f"{len(leads)} pages worked one at a time",
            "review_candidates": reviews[:2],
            # The largest one-page turn: the 15k ceiling is per turn (#1959).
            "instructions_chars": max(sizes) if sizes else None,
            "page_chars": growth}


def run_sync(root: Path, *, source: str = "", with_person: str = "", dry_run: bool = False,
             scheduled: bool = False, all_pending: bool = False, runner=None, extractor=None,
             on_batch=None, say=None) -> dict | None:
    """One bounded batch; caller must have recorded explicit source consent.

    `scheduled` is what the background tick passes: run only if a saved time has
    come due since the last scheduled batch, otherwise return None at once, with
    no lock taken and nothing read. Stopped notebooks tick to nothing.

    `all_pending` is the backfill: batch after batch, oldest material first,
    until nothing is pending or the day's runner attempts are spent. It once
    ignored the cap as "user-initiated", and on a real notebook ran 60 attempts
    against a cap of 30 in 37 silent minutes (#1957): typed by hand is not the
    same as watched. A failed batch stops it too. `on_batch(n, record)` is
    called as each batch finishes, so the caller can show progress and, on
    Ctrl-C, say what finished.
    """
    root = root.resolve()
    # Inspection must win over every execution mode, including recursive backfill.
    if dry_run:
        progress = read_json(state_path(root, "progress.json"), {})
        return {"dry_run": True, "sources": {
            name: (pending_metadata(sub, progress.get(name, {})) if sub.get("kind") in KINDS
                   else {"chats": sub.get("chats") or [], "body_reads": False,
                         "source_available": sub.get("adapter") == "available"}
                   if sub.get("kind") in CHAT_KINDS else {"candidate_files": None, "message_count": None, "body_reads": False,
                         "source_available": mail_available(sub["kind"]),
                         "cursor": progress.get(name, {}).get("cursor") or sub.get("since")})
            for name, sub in _selected_sources(root, source).items()},
            # `status` said 30/30 while the dry run said nothing of it (#1957).
            "daily_cap": daily_cap(root)}
    if all_pending:
        records, spent = [], ""
        while True:
            try:
                record = run_sync(root, source=source, with_person=with_person, runner=runner,
                                  extractor=extractor)
            except RemError as error:
                if CAP_LIMIT not in str(error):
                    raise
                spent = str(error)
                break
            if record["outcome"] == "no_change":
                break
            records.append(record)
            if on_batch:
                on_batch(len(records), record)
            if record["outcome"] != "completed":
                break
        outcome = ("budget_exhausted" if spent else "caught_up" if not records
                   or records[-1]["outcome"] == "completed" else records[-1]["outcome"])
        return {"outcome": outcome, **({"reason": spent} if spent else {}),
                "batches": len(records), "items": sum(r["items"] for r in records),
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
        try:
            record = run_sync(root, source=source, with_person=with_person, runner=runner, extractor=extractor,
                              say=say)
        except RemError as error:
            if CAP_LIMIT not in str(error):
                raise
            # The day's calls are spent: the slot is served, not owed. Leaving it
            # owed retried it on every five-minute tick until midnight and wrote
            # the same error into launchd.log each time (seen on a real notebook).
            record = {"outcome": "budget_exhausted", "reason": "the day's runner calls are spent"}
        # Any recorded outcome serves the slot; a refusal to start (busy) raised
        # above this line and leaves it owed for the next tick.
        write_json(state_path(root, "worker.json"), {
            **worker_state(root), "last_scheduled_slot": slot.isoformat(),
            "last_scheduled_outcome": record.get("outcome"),
            "last_scheduled_reason": record.get("reason") or record.get("error") or "",
            "last_scheduled_warning": record.get("warning") or "",
        })
        return record
    if not state_path(root, "consent.json").is_file():
        raise RemError("Source access is not authorized yet; run `co rem start` to review and confirm it")
    with maintenance_lock(root), _terminate_as_interrupt():
        config = validate(read_config(root))
        abandon_stale_runs(root)
        # An upgraded notebook is tidied by its first sync, before anything reads it (#1999).
        from .tidy import tidy
        tidied = tidy(root, lock_held=True)
        selected = _selected_sources(root, source)
        progress = read_json(state_path(root, "progress.json"), {})
        if not isinstance(progress, dict):
            raise RemError("Invalid source progress; preserve it for diagnosis")
        record = _sync_locked(root, selected, progress, config, runner, extractor,
                              with_person=with_person, include_local=not source, say=say)
        archive = _resume_archive(root, say) if isinstance(record, dict) else None
        record = {**record, "mail_archive": archive} if archive else record
        if isinstance(record, dict):
            # The index the table and thread views read (#2067): after everything this
            # sync wrote, still under the lock, and reported rather than fatal.
            from .store import refresh_safely
            record = {**record, "store": refresh_safely(root)}
        return {**record, "tidied": tidied} if tidied and isinstance(record, dict) else record


def _resume_archive(root: Path, say=None) -> dict | None:
    """A stalled init mail archive continues in the sync, for a bounded time (#2035).

    Only `init` ever resumed it, so on the 1.9.0a6 acceptance notebook every
    investigation for a day asked the mail servers instead. A mailbox the owner
    unsubscribed is not read; one that will not open is reported, not guessed.
    """
    state = archive_state(root, now=now())
    if not state or not state["stalled"]:
        return None
    sources, clients = subscriptions(root), {}
    for kind in MAIL_KINDS:
        if mail_available(kind) and not sources.get(kind, {}).get("unsubscribed"):
            try:
                clients[kind] = mail_client(kind)
            except Exception:  # resume_stalled names the mailbox it could not open
                clients[kind] = None
    return resume_stalled(root, clients, now=lambda: now(), say=say)


@contextmanager
def _terminate_as_interrupt():
    """`launchctl bootout` (and `co rem stop`) end a running batch with SIGTERM.

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


def _sync_locked(root, selected, progress, config, runner, extractor=None, *,
                 with_person="", include_local=True, say=None):
    from .extract import NOTHING, extraction_instructions, extraction_item, run_extract
    from .runner import maintenance_instructions, run_stage

    items, updated, seen, counts, unrecognised = [], dict(progress), set(), {}, {}
    source_skips = []
    kind = ""   # the one source this batch is drawn from; see the loop below
    limits = config["limits"]
    # A batch is gathered against the extraction budget: large, because the
    # extraction pass reads it once. A batch that fits items_per_batch
    # is small enough for the maintainer to read directly and skips extraction.
    # The widest source Skill, so the budget holds whichever source this batch is.
    widest_maintain = max(len(maintenance_instructions(k)) for k in ("", *READABLE))
    maintain_room = limits["input_chars_per_batch"] - widest_maintain - 1000
    if maintain_room <= 0:
        raise RemError("Configured input limit is too small for the maintenance Skill")
    # The largest source Skill, so the budget holds whichever source this batch turns out to be.
    widest = max(len(extraction_instructions(k)) for k in ("", *READABLE))
    remaining = max(limits["extract_chars_per_batch"] - widest - 1000, maintain_room * 2 // 3)
    max_items = limits["extract_items_per_batch"]
    from .reflections import context as reflection_context
    from .capture import pending as captured_pending
    processed = progress.get("rem_local_material", [])
    from .reviews import context as review_context
    local = reflection_context(root) + review_context(root) + captured_pending(root, list(set(processed) | set(progress.get("rem_seen_source_ids", []))), max_items, remaining)
    local = [item for item in local if item["source"] not in processed]
    if not with_person and include_local:
        for item in local:
            size = len(json.dumps(item, ensure_ascii=False))
            if len(items) >= max_items or size > remaining:
                break
            items.append(item)
            seen.add(item["source"])
            remaining -= size
        if items:
            counts["local_material"] = len(items)
            updated["rem_local_material"] = sorted(set(processed) | seen)
    for name, subscription in selected.items():
        if items:
            break
        if len(items) >= max_items or remaining <= 0:
            break
        if subscription.get("kind") in MAIL_KINDS:
            batch = collect_mail(subscription, progress.get(name, {}), max_items - len(items),
                                 remaining, mail_client(subscription["kind"]), only=with_person)
        elif with_person:
            continue  # a person is a mail concept; a coding session has no correspondent
        elif subscription.get("kind") in CHAT_KINDS:
            batch = collect_chat(subscription, progress.get(name, {}), max_items - len(items), remaining)
        else:
            batch = collect(subscription, progress.get(name, {}), max_items - len(items), remaining)
        source_skips.extend({"source": name, "file": path, "reason": "processed prefix changed"}
                            for path in batch.changed_files)
        if getattr(batch, "unreadable", False):
            unrecognised[name] = batch.unrecognised
        for item in batch.items:
            if item["source"] not in seen:
                items.append(item)
                seen.add(item["source"])
                counts[name] = counts.get(name, 0) + 1
                remaining -= len(json.dumps(item, ensure_ascii=False))
        updated[name] = batch.progress
        # One source per batch. Extraction is read through that source's own
        # Skill -- where its words hide, how its store is laid out, what it has
        # taught us -- and a batch mixing mail with coding sessions would have
        # to be read through both, or through neither. The next batch takes the
        # next source; nothing is skipped, only separated.
        if items:
            kind = subscription.get("kind", name)
            break
    if seen:
        updated["rem_seen_source_ids"] = sorted(set(progress.get("rem_seen_source_ids", [])) | seen)
    record = {"id": "run_" + uuid.uuid4().hex, "started_at": now().isoformat(),
              "model": config["model"], "sources": list(selected), "items": len(items),
              "runner_attempts": 0, "outcome": "no_change", "usage": None, "changed": [], "refused": 0,
              "extracted": len(items) > limits["items_per_batch"],
              # Where the tokens went, kept raw so the cost of a stage, a source or a
              # model can be computed later from the records rather than remembered.
              # Reading only what the user typed fails closed when a client changes its
              # transcript format, and closed is silent. A pass that passed over a pile
              # of user-slot messages it did not recognise says so, by source.
              "unrecognised": unrecognised,
              "source_skips": source_skips,
              "warning": "; ".join([*(f"{name}: {count} messages in an unfamiliar format were not read"
                                      for name, count in unrecognised.items()),
                                    *([f"{len(source_skips)} changed session file(s) skipped; checkpoints kept; "
                                       "other sessions continue; inspect co rem logs"] if source_skips else [])]),
              "usage_by_stage": {}, "items_by_source": counts,
              "chars_in": sum(len(json.dumps(item, ensure_ascii=False)) for item in items), "seconds": None}
    path = state_path(root, f"runs/{record['id']}.json")
    if not items:
        write_json(state_path(root, "progress.json"), updated)
        # Nothing new was read and no model ran, so there is no run to list
        # (#1846). Messages passed over in an unfamiliar format are still said.
        if record["warning"]:
            write_json(path, record)
        return record
    from .extract import finished_digest, forget_digest, remember_digest
    digested = finished_digest(root, items, kind) if record["extracted"] else None
    extract_calls = 1 if record["extracted"] and digested is None else 0
    # One call per page the material concerns (#1656): the script finds them,
    # the model updates one at a time. A fake runner in tests keeps the single
    # whole-notebook call. A page that has already read what points at it gets
    # no call at all (#1846).
    leads, current = [], []
    if runner is None or runner is run_stage:
        from .leads import nothing_new, page_leads
        found = page_leads(Notebook(root), items)
        current = [lead for lead in found if nothing_new(Notebook(root), lead, items)]
        leads = [lead for lead in found if lead not in current][:PAGES_PER_BATCH]
    if current:
        record["up_to_date"] = current
    if current and not leads:
        record.update(outcome="completed", report="Every page this material concerns has already read it")
        write_json(state_path(root, "progress.json"), updated)
        forget_digest(root)
        write_json(path, record)
        return record
    room = limits["runner_calls_per_day"] - status(root)["runner_attempts_today"] - extract_calls
    if room < 1:
        cap = daily_cap(root)
        reason = (f"{CAP_LIMIT} ({cap['used']} of {cap['limit']} used today; this batch needs "
                  f"{extract_calls + 1}); source progress was not advanced. The count resets "
                  f"{cap['resets_at']}; to allow more, raise limits.runner_calls_per_day with `co rem config`")
        # Recorded, so the logs the refusal points at show it (#1957). No
        # attempts are charged: nothing was read into a model.
        record.update(outcome="refused", reason=reason, finished_at=now().isoformat())
        write_json(path, record)
        raise RemError(reason)
    leads = leads[:room]
    attempts = extract_calls + (len(leads) or 1)
    runner = runner or run_stage
    # A runner may carry a preflight (the CLI adapter checks that co is installed). It raises before an attempt is reserved: a configuration error is
    # not a failed batch and must not spend one of the day's attempts.
    getattr(runner, "preflight", lambda: None)()
    from . import quota
    # What this run cost in points of the owner's Codex week (#1843), measured.
    record.update(outcome="running", runner_attempts=attempts, quota={"before": quota.read(config)},
                  **running_marker())
    write_json(path, record)  # Reserve the attempts before starting a COAI process.
    usage = {}
    stage = "extract" if record["extracted"] and digested is None else "maintain"
    # What the notebook held before the run: a failure after pages were written
    # still has to advance the cursor, or the same material is paid for daily.
    notebook = Notebook(root)
    before = {page: notebook.read(page) for page in notebook.list()}
    try:
        if digested is not None:
            record["extract_reused"] = True
            items = [] if digested == NOTHING else [extraction_item(digested, items)]
        elif record["extracted"]:
            digested_items = items
            digest = (extractor(items, config, kind) if extractor else
                      run_extract(items, config, kind, root=root))
            usage = dict(digest.get("usage") or {})
            record["usage_by_stage"]["extract"] = digest.get("usage")
            if digest.get("instructions_chars"):
                record.setdefault("instructions_chars", {})["extract"] = digest["instructions_chars"]
            notes = digest["notes"].strip()
            # The digest is the only thing the maintainer sees. Keeping it is how
            # a thin page gets traced to the pass that lost the fact.
            extracts = state_path(root, "extracts")
            extracts.mkdir(parents=True, exist_ok=True, mode=0o700)
            (extracts / f"{record['id']}.md").write_text(notes, encoding="utf-8")
            record["extract_notes"] = f".state/extracts/{record['id']}.md"
            remember_digest(root, digested_items, kind, f"extracts/{record['id']}.md")
            items = [] if notes == NOTHING else [extraction_item(notes, items)]
        if items and leads and record.get("extract_notes"):
            # The notes name projects the raw material could not point at (#1985).
            # Pages found that way join the batch while the day has attempts left;
            # names no page answers to are recorded, never dropped silently.
            from .leads import note_leads
            named, unrouted = note_leads(Notebook(root), items[0].get("text", ""))
            spare = max(0, room - len(leads))
            extra = [page for page in named if page not in leads and page not in current][:spare]
            if extra:
                leads += extra
                record["runner_attempts"] = record["runner_attempts"] + len(extra)
                record["routed_by_name"] = extra
                write_json(path, record)
            if unrouted:
                record["unrouted_projects"] = unrouted
        if items:
            stage = "maintain"
            if leads:
                result = _maintain_pages(root, items, config, kind, leads, say=say)
            else:
                options = {"maintenance_lock_held": True} if runner is run_stage else {}
                result = runner(Notebook(root), items, config, kind=kind, **options)
            record["usage_by_stage"]["maintain"] = result.get("usage")
            if result.get("instructions_chars"):
                record.setdefault("instructions_chars", {})["maintain"] = result["instructions_chars"]
            if result.get("page_chars"):
                record["page_chars"] = result["page_chars"]
            for key, value in (result.get("usage") or {}).items():
                usage[key] = usage.get(key, 0) + value
        else:
            result = {"changed": [], "report": NOTHING}
        from .reviews import ingest
        ingest(root, result.get("review_candidates", []))
        record.update(outcome="completed", usage=usage or None, changed=result.get("changed", []),
                      refused=result.get("refused", 0), refusals=result.get("refusals", []),
                      report=result.get("report", "") + (
                          f"; notes about {', '.join(record['unrouted_projects'])} matched no project page "
                          "(kept in the extract notes)" if record.get("unrouted_projects") else ""))
        # A refused page no longer holds back the batch, but the user's own
        # correction to that page is not marked done: it waits for the next pass.
        refused_pages = {row["record"] for row in result.get("refusals", [])}
        waiting = {item["source"] for item in local if item.get("record") in refused_pages}
        for key in ("rem_local_material", "rem_seen_source_ids"):
            if key in updated and waiting:
                updated[key] = sorted(set(updated[key]) - waiting)
        write_json(state_path(root, "progress.json"), updated)
        forget_digest(root)
    except BaseException as error:
        failed_usage = getattr(error, "usage", None)
        record["usage_by_stage"][stage] = failed_usage
        for key, value in (failed_usage or {}).items():
            usage[key] = usage.get(key, 0) + value
        record.update(outcome="interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "failed",
                      usage=usage or None, changed=getattr(error, "changed", []),
                      error=str(error) if isinstance(error, RemError) else "Runner failed; source progress preserved")
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise  # stopped mid-write: what is on disk may be half a batch, so it runs again
        # Pages on disk mean the maintainer finished with this material and the
        # failure came after (the runner promotes a batch's pages together, under
        # the lock). Holding the cursor back reran the batch on every schedule and
        # paid for it again.
        after = {page: notebook.read(page) for page in notebook.list()}
        written = sorted(page for page in before.keys() | after.keys() if before.get(page) != after.get(page))
        record.update(changed=written or record["changed"], progress_advanced=bool(written))
        if written:
            if not isinstance(error, RemError):
                record["error"] = "Runner failed after writing its pages; source progress advanced"
            write_json(state_path(root, "progress.json"), updated)
            forget_digest(root)
    finally:
        record["finished_at"] = now().isoformat()
        if record["outcome"] == "completed" and record.get("changed"):
            from .claim_changes import material_changes
            after = {page: notebook.read(page) for page in record["changed"] if notebook.path(page).is_file()}
            record["claim_changes"] = material_changes(before, after, record["changed"])
        record["quota"]["after"] = quota.read(config)
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
    chars_by_model, sized_by_model, items_by_source = {}, {}, {}
    for run in runs:
        add(total, run["usage"])
        # Every run's tokens land under a stage, so the stages add up to the
        # total: 2.35M investigation and project tokens had none (#2043). What
        # a run did not split by stage goes under the stage its kind implies.
        split = {}
        for stage, usage in (run.get("usage_by_stage") or {}).items():
            add(by_stage.setdefault(stage, {}), usage)
            add(split, usage)
        rest = {key: run["usage"][key] - split.get(key, 0) for key in keys
                if isinstance(run["usage"].get(key), (int, float)) and run["usage"][key] > split.get(key, 0)}
        if rest:
            add(by_stage.setdefault(PHASE_STAGES.get(run.get("phase"), "maintain"), {}), rest)
        # Records from before the model was stored are said to be that, not "?" (#1974).
        model = run.get("model") or "unrecorded"
        add(by_model.setdefault(model, {}), run["usage"])
        if run.get("chars_in") and run.get("items_by_source"):
            # Only sync batches, which put their recorded characters in the
            # prompt, count towards the rate: tokens from runs with no size, or
            # from an investigation whose material the model searched in files,
            # over the size of the others read 28,556.9 per 1k characters (#2043).
            chars_by_model[model] = chars_by_model.get(model, 0) + run["chars_in"]
            add(sized_by_model.setdefault(model, {}), run["usage"])
        shares = run.get("items_by_source") or {}
        total_items = sum(shares.values()) or 1
        for source, count in shares.items():
            add(by_source.setdefault(source, {}), run["usage"], count / total_items)
            items_by_source[source] = items_by_source.get(source, 0) + count
    for source, table in by_source.items():
        table["items"] = items_by_source[source]
        table["input_tokens_per_item"] = round(table.get("input_tokens", 0) / max(items_by_source[source], 1), 1)
    for model, table in by_model.items():
        table["chars_in"] = chars_by_model.get(model, 0)
        if chars_by_model.get(model):
            table["input_tokens_per_1k_chars"] = round(
                sized_by_model[model].get("input_tokens", 0) / (chars_by_model[model] / 1000), 1)
    # The fixed part of every turn: the composed Skill text, re-sent on each
    # tool round. #1851 set a 15k-character ceiling for a one-page turn; this
    # is where a regression shows up (older runs did not record it).
    sizes = {}
    for run in runs:
        for stage, chars in (run.get("instructions_chars") or {}).items():
            if isinstance(chars, int):
                sizes.setdefault(stage, []).append(chars)
    for stage, values in sizes.items():
        table = by_stage.setdefault(stage, {})
        table["instructions_chars_mean"] = round(sum(values) / len(values))
        table["instructions_chars_max"] = max(values)
        table["over_instructions_target"] = max(values) > INSTRUCTIONS_TARGET_CHARS
    # What the tokens bought (#1846): a page turn that changes nothing costs the same.
    changed = sum(len(run.get("changed") or []) for run in runs)
    per_100k = round(changed * 100_000 / total["input_tokens"], 2) if total.get("input_tokens") else None
    return {"runs": len(runs), "days": days, "total": total, "pages_changed": changed,
            "pages_changed_per_100k_input_tokens": per_100k, "by_stage": by_stage,
            "by_model": by_model, "by_source": by_source}


INSTRUCTIONS_TARGET_CHARS = 15_000

# The stage a run's unsplit tokens belong to, by the kind of run (#2043). A sync
# batch has no phase and splits extract / maintain itself; a daily update that
# predates its own split is mostly people, so investigate.
PHASE_STAGES = {"investigate": "investigate", "investigate me": "investigate",
                "daily-investigation": "investigate", "daily-update": "investigate",
                "projects write": "projects"}
