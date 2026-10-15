"""One page per conversation the owner typed in; no model."""

import json
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, service, source
from .files import (SECRET_SHAPES, WRITE_WAIT_SECONDS, Notebook, RemError,
                    maintenance_lock, read_json, state_path, write_json)
from .scan import project_exclusion
from .project_material import REDACTED, page_folders, page_for, retain_cited_sessions

AGENTS = {"codex": "Codex", "claude-code": "Claude Code"}


def _redact(text: str) -> str:
    return SECRET_SHAPES.sub(REDACTED, text)


def _reply(row: dict, kind: str) -> str:
    if kind == "codex":
        message = row.get("payload") or {}
        if row.get("type") != "response_item" or message.get("type") != "message":
            return ""
        role, block = message.get("role"), "output_text"
    else:
        if row.get("isSidechain") or row.get("isMeta"):
            return ""
        message = row.get("message") or {}
        role, block = row.get("type"), "text"
    if role != "assistant" or not isinstance(message, dict):
        return ""
    return "\n".join(part["text"] for part in message.get("content", [])
                     if isinstance(part, dict) and part.get("type") == block
                     and isinstance(part.get("text"), str))


def _row_reason(row: dict, kind: str) -> str:
    user = row.get("type") == "user" if kind == "claude-code" else (
        row.get("payload") or {}).get("role") == "user"
    if not user:
        return ""
    if source.rem_task(row.get("cwd")):
        return "rem_task"
    if source.automated(row):
        return "program_prompt"
    if row.get("isSidechain"):
        return "sidechain"
    return "no_typed_message"


def _read_session(path: Path, kind: str, since: datetime) -> tuple[dict, str]:
    parsers = source.KINDS[kind]
    with path.open("rb") as transcript:
        first = transcript.readline(1_000_000)
        # A corrupt first line is a counted file, never a half-imported session.
        try:
            meta = parsers["meta"](json.loads(first))
        except (ValueError, UnicodeError, AttributeError, TypeError, RemError):
            return {}, "unreadable"
        if meta.get("skip"):
            return {}, "rem_task"
        if meta.get("subagent"):
            return {}, "exec_or_subagent"
        session = {"id": meta.get("id") or path.stem, "cwd": meta.get("cwd") or "",
                   "kind": kind, "messages": [], "reply": ""}
        reasons = set()
        offset = 0
        transcript.seek(0)  # Claude's first row can itself be the first typed message.
        for line in transcript:
            at, offset = offset, offset + len(line)
            if not line.endswith(b"\n") or b'"message"' not in line:
                continue
            try:
                row = json.loads(line)
                item = parsers["message"](row, since, meta) if isinstance(row, dict) else None
            except (ValueError, UnicodeError, AttributeError, TypeError, RemError):
                continue  # Clients can leave a torn row while appending.
            if not isinstance(row, dict):
                continue
            reasons.add(_row_reason(row, kind))
            reply = _reply(row, kind)
            if reply:
                session["reply"] = _redact(reply)
            if not isinstance(item, dict) or item.get("role") != "user":
                continue
            session["id"] = item.get("session") or session["id"]
            session["cwd"] = item.get("cwd") or session["cwd"]
            session["messages"].append({**item, "text": _redact(item["text"]),
                "source": f"{kind}:{session['id']}:{at}"})
    why = next((reason for reason in ("rem_task", "program_prompt", "sidechain") if reason in reasons),
               "no_typed_message")
    return session, "" if session["messages"] else why


def _title(session: dict) -> str:
    first = next(line for line in session["messages"][0]["text"].splitlines() if line.strip())
    title = " ".join(first.split())
    return title[:79] + "…" if len(title) > 80 else title


def _record(session: dict, day: str) -> str:
    words = re.findall(r"[a-z0-9]+", _title(session).lower(), re.ASCII)
    slug = "-".join(words[:6])[:40].rstrip("-") or "session"
    # The tail: a Codex id is a UUIDv7, whose head is the clock, and four probes
    # started in the same minute shared one page on a real machine (2026-10-16).
    short = re.sub(r"[^a-zA-Z0-9]", "", session["id"])[-8:]
    return f"sessions/{day}-{slug}-{short}.md"


def _quote(text: str) -> str:
    return "\n".join("> " + line for line in text.split("\n"))


def _page(session: dict, notebook: Notebook, folders: dict, zone) -> tuple[str, str]:
    messages = session["messages"]
    day = source.timestamp(messages[0]["timestamp"]).astimezone(zone).date().isoformat()
    cwd = session["cwd"]
    project = page_for(cwd, folders) if cwd else None
    title = notebook.read(project).splitlines()[0].removeprefix("# ") if project else ""
    linked = f"[{title}](../{project})" if project else cwd
    lines = [f"# {_title(session)}", "", "## Facts", f"- Date: {day}",
             f"- Agent: {AGENTS[session['kind']]}", f"- Project: {linked}", f"- Folder: {cwd}",
             f"- Session: {session['id']}", f"- Turns: {len(messages)}", "", "## What you typed"]
    for message in messages:
        local = source.timestamp(message["timestamp"]).astimezone(zone)
        stamp = local.strftime("%H:%M" if local.date().isoformat() == day else "%Y-%m-%d %H:%M")
        lines += [f"### {stamp}", _quote(message["text"]), ""]
    reply = session["reply"]
    if reply:
        clipped = reply[:3000] + source.TRUNCATION_NOTE.format(dropped=len(reply) - 3000) if len(reply) > 3000 else reply
        lines += ["## Final reply", _quote(clipped), ""]
    lines += ["## Sources", *(f"- {message['source']}" for message in messages), ""]
    return day, _redact("\n".join(lines))


def _import_file(path, kind, since, notebook, folders, zone, progress, counts):
    stat = path.stat()
    if datetime.fromtimestamp(stat.st_mtime, timezone.utc) < since:
        return "outside_window"
    old = progress["files"].get(str(path), {})
    if ((old.get("size"), old.get("mtime_ns")) == (stat.st_size, stat.st_mtime_ns)
            and (not old.get("record") or notebook.path(old["record"]).is_file())):
        counts["unchanged"] += 1
        return ""
    session, why = _read_session(path, kind, since)
    cwd = session.get("cwd") or ""
    if not why and cwd and Path(cwd).resolve().is_relative_to(notebook.root):
        why = "notebook"
    # Probes and harness replays run in /tmp: 151 of 458 sessions on a real machine
    # (2026-10-16) were "Reply with exactly: pong" and the like, never the owner's work.
    if not why and cwd and project_exclusion(Path(cwd)) == "temporary execution directory":
        why = "temporary_directory"
    if why:
        progress["files"][str(path)] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                                         "record": "", "session": ""}
        return why
    key = f"{kind}:{session['id']}"
    day, page = _page(session, notebook, folders, zone)
    record = progress["sessions"].get(key) or _record(session, day)
    updated = notebook.path(record).is_file()
    notebook.write(record, page)
    retain_cited_sessions(notebook.root, session["messages"], {m["source"] for m in session["messages"]}, replace=True)
    progress["files"][str(path)] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                                     "record": record, "session": key}
    progress["sessions"][key] = record
    counts["updated" if updated else "imported"] += 1
    return ""


def import_sessions(root: Path, *, days: int = 180, now: datetime | None = None,
                    consented_only: bool = False) -> dict:
    if days < 1:
        raise RemError("Session import days must be positive")
    started = time.monotonic()
    since = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    notebook = Notebook(root)
    zone = ZoneInfo(config.read_config(root)["schedule"].get("timezone") or config.local_timezone() or "UTC")
    counts = {"imported": 0, "updated": 0, "unchanged": 0}
    skipped = Counter()
    with maintenance_lock(root, wait=WRITE_WAIT_SECONDS):
        progress = read_json(state_path(root, "sessions.json"), {"files": {}, "sessions": {}})
        settings = {"days": days, "timezone": str(zone)}
        if progress.get("settings") != settings:
            progress["files"] = {}
        progress["settings"] = settings
        folders = page_folders(notebook)
        for sub in service.subscriptions(root).values():
            kind = sub.get("kind")
            if kind not in source.KINDS or sub.get("enabled") is False or (consented_only and not sub.get("consented")):
                continue
            directory = Path(sub["root"])
            if directory.is_symlink() or not directory.is_dir():
                continue
            for path in sorted(directory.rglob(source.KINDS[kind]["glob"])):
                relative = path.relative_to(directory)
                if any((directory / parent).is_symlink() for parent in (relative, *relative.parents)) or not path.is_file():
                    continue
                why = _import_file(path, kind, since, notebook, folders, zone, progress, counts)
                if why:
                    skipped[why] += 1
        write_json(state_path(root, "sessions.json"), progress)
    return {**counts, "skipped": dict(skipped), "seconds": round(time.monotonic() - started, 3)}


def summary(report: dict) -> str:
    return (f"AI sessions: {report['imported']} imported, {report['updated']} updated, "
            f"{report['unchanged']} unchanged; {sum(report['skipped'].values())} skipped; {report['seconds']}s")
