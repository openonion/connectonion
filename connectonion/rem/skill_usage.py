"""How often, and when last, the user invoked each skill: a script over the
session transcripts, no model (#1974).

What counts as an invocation, per harness, once per turn:

- Claude Code: a `Skill` tool call (`{"name": "Skill", "input": {"skill": …}}`)
  and a `/name` command (`<command-name>/name</command-name>` in the user's row).
  A resumed session repeats earlier rows with the same `uuid`; each counts once.
- Codex: `$name` in a message the user typed (the reading `sync` uses, #1978),
  and a tool call whose arguments name `…/skills/<name>/SKILL.md` -- how Codex
  loads a skill, in a subagent's thread too. Codex lists every
  available skill's path in its own context, so only tool-call arguments count,
  never message text that merely mentions a path.

co rem's own model runs are not the user's and are skipped. The counts say a
skill was started, never that the task it was started for succeeded.

Each session file's events are cached in `.state/skill-usage.json` by size and
modification time, so a rerun reads only files that changed. Only names and
times are kept there, never message text.
"""

from __future__ import annotations

import json
import re
from itertools import chain
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import RemError, read_json, state_path, write_json
from .source import KINDS, source_files

CACHE = "skill-usage.json"
# 3: Recount messages whose optional Codex id was omitted; older caches missed them.
VERSION = 3
EVER = datetime(1970, 1, 1, tzinfo=timezone.utc)
COMMAND = re.compile(r"<command-name>/([^<\s]+)</command-name>")
MENTION = re.compile(r"(?<![\w$])\$([A-Za-z][\w.:-]*)")
LOADED = re.compile(r"/skills/([A-Za-z0-9][\w.:-]*)/SKILL\.md")
LABELS = {"claude-code": "Claude Code", "codex": "Codex"}


def _claude_events(path: Path) -> list[list]:
    events, seen = [], set()
    with path.open("rb") as handle:
        for line in handle:
            if b'"Skill"' not in line and b"<command-name>" not in line:
                continue
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            message = row.get("message") if isinstance(row, dict) else None
            if not isinstance(message, dict) or (row.get("uuid") and row["uuid"] in seen):
                continue
            seen.add(row.get("uuid"))
            when, content = str(row.get("timestamp") or ""), message.get("content")
            names = []
            if row.get("type") == "assistant" and isinstance(content, list):
                names = [part["input"]["skill"] for part in content
                         if isinstance(part, dict) and part.get("type") == "tool_use" and part.get("name") == "Skill"
                         and isinstance(part.get("input"), dict) and isinstance(part["input"].get("skill"), str)]
            elif row.get("type") == "user":
                text = content if isinstance(content, str) else " ".join(
                    part.get("text", "") for part in content or [] if isinstance(part, dict)
                    and isinstance(part.get("text"), str)) if isinstance(content, list) else ""
                names = COMMAND.findall(text)
            events += [[name, when, "claude-code", str(row.get("cwd") or "")] for name in names]
    return events


def _codex_events(path: Path) -> list[list]:
    events, seen, turn, cwd = [], set(), 0, ""
    with path.open("rb") as handle:
        first = handle.readline(1_000_000)
        try:
            meta = KINDS["codex"]["meta"](json.loads(first))
        except (ValueError, UnicodeError, RemError, AttributeError):
            return []
        if meta.get("skip"):
            return []  # co rem's own run
        cwd = meta.get("cwd") or ""
        for line in handle:
            head = line[:200]
            if b'"turn_context"' in head:
                turn += 1
                continue
            if b'"response_item"' not in head or (b"SKILL.md" not in line and b"$" not in line):
                continue
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            kind, when = payload.get("type"), str(row.get("timestamp") or "")
            if kind in ("function_call", "custom_tool_call", "local_shell_call"):
                value = payload.get("arguments") or payload.get("input") or payload.get("action")
                names = LOADED.findall(value if isinstance(value, str) else json.dumps(value))
            elif kind == "message" and payload.get("role") == "user":
                # `sync`'s own reading of a typed message (#1978): a `$name` in what a
                # subagent was handed, in an imported Claude Code history or in a block
                # the client injected was not the user starting a skill.
                try:
                    item = KINDS["codex"]["message"](row, EVER, meta)
                except (RemError, AttributeError, TypeError):
                    continue
                names = MENTION.findall(item["text"]) if isinstance(item, dict) else []
            else:
                continue
            for name in names:
                if (turn, name) not in seen:
                    seen.add((turn, name))
                    events.append([name, when, "codex", cwd])
    return events


READERS = {"claude-code": _claude_events, "codex": _codex_events}


def usage(subscriptions: dict, names, *, root: Path | None = None, days: int = 180,
          now: datetime | None = None) -> dict:
    """Invocations of each name in `names` over the last `days` days of sessions.

    Returns {"counts": {name: {"count", "last", "by_tool": {tool: n}}}, "files",
    "days", "sources"}. A name invoked as `plugin:name` counts for `name` too.
    `root` is the notebook: its cache, and its own task folders to skip.
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    cache_path = state_path(root, CACHE) if root else None
    cache = read_json(cache_path, {}) if cache_path else {}
    files = cache.get("files", {}) if cache.get("version") == VERSION else {}
    wanted = {name.casefold(): name for name in names}
    counts = {name: {"count": 0, "last": "", "by_tool": {}} for name in names}
    fresh, read, sources = {}, 0, []
    for name, sub in subscriptions.items():
        kind = sub.get("kind")
        if kind not in READERS or sub.get("enabled") is False or not Path(sub.get("root") or "").is_dir():
            continue
        sources.append(LABELS[kind])
        for path in source_files(sub):
            stat = path.stat()
            if datetime.fromtimestamp(stat.st_mtime, timezone.utc) < since:
                continue
            key, stamp = str(path), [stat.st_size, stat.st_mtime_ns]
            entry = files.get(key)
            if not entry or entry.get("stamp") != stamp:
                entry = {"stamp": stamp, "events": READERS[kind](path)}
            fresh[key] = entry
            read += 1
            for invoked, when, tool, cwd in entry["events"]:
                skill = wanted.get(invoked.casefold()) or wanted.get(invoked.rsplit(":", 1)[-1].casefold())
                if not skill or (when and when[:19] < since.isoformat()[:19]):
                    continue
                if cwd and ("/.state/tasks/" in cwd + "/" or (root and _inside(cwd, root))):
                    continue  # co rem's own task folders
                row = counts[skill]
                row["count"] += 1
                row["last"] = max(row["last"], when[:10])
                row["by_tool"][tool] = row["by_tool"].get(tool, 0) + 1
    if cache_path:
        write_json(cache_path, {"version": VERSION, "files": fresh})
    return {"counts": counts, "files": read, "days": days, "sources": sources}


def _inside(cwd: str, root: Path) -> bool:
    try:
        return Path(cwd).resolve().is_relative_to(Path(root).resolve())
    except OSError:
        return False


def usage_line(row: dict | None, report: dict | None) -> str:
    """The first line of a skill page's Usage history."""
    if not report or not report.get("sources"):
        return "- Invocations not counted: no Claude Code or Codex session source is enabled (co rem sources)."
    window = f"in the last {report['days']} days ({report['files']} session files: {', '.join(report['sources'])})"
    if not row or not row["count"]:
        return f"- No invocation found in your coding sessions {window}."
    tools = ", ".join(f"{LABELS[tool]} {n}" for tool, n in sorted(row["by_tool"].items()))
    times = "once" if row["count"] == 1 else f"{row['count']} times"
    return (f"- Invoked {times} in your coding sessions {window}, last on {row['last']} ({tools}). "
            "Counted by co rem from Skill tool calls, /name commands, $name mentions and SKILL.md loads; "
            "an invocation is not a completed run.")


def session_samples(root: Path, name: str, limit: int = 3) -> dict:
    """Read recent invocation turns identified by the map; never scan unrelated sessions."""
    cached = read_json(state_path(root, CACHE), {})
    matches = []
    since = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()[:19]
    for file, entry in (cached.get("files", {}) if cached.get("version") == VERSION else {}).items():
        for invoked, when, kind, cwd in entry.get("events", []):
            if invoked.casefold().rsplit(":", 1)[-1] != name.casefold().rsplit(":", 1)[-1]:
                continue
            if when and when[:19] < since:
                continue
            if cwd and ("/.state/tasks/" in cwd + "/" or _inside(cwd, root)):
                continue
            matches.append((when, file, kind, cwd))
    selected = sorted(set(matches), reverse=True)[:limit]
    items, missing = [], []
    for when, file, kind, cwd in selected:
        path = Path(file)
        text = _invocation_turn(path, kind, when) if path.is_file() else ""
        if not text:
            missing.append({"file": file, "timestamp": when})
            continue
        items.append({"source": f"skill-session:{kind}:{path.stem}:{when}", "timestamp": when,
                      "project": cwd, "reference": path.as_uri(), "text": text})
    return {"items": items, "matched_invocations": len(set(matches)), "sample_limit": limit,
            "missing": missing, "cache_available": cached.get("version") == VERSION}


def _invocation_turn(path: Path, kind: str, when: str) -> str:
    """Raw request, invocation, tool results and replies until the next typed request."""
    from .files import SECRET_SHAPES
    selected, request, active = [], None, False
    with path.open() as handle:
        first = json.loads(handle.readline())
        meta = KINDS[kind]["meta"](first)
        for row in chain([first], (json.loads(line) for line in handle)):
            spoken = KINDS[kind]["message"](row, EVER, meta)
            if isinstance(spoken, dict) and spoken.get("role") == "user":
                if active:
                    break
                request = row
            if not active and row.get("timestamp") == when:
                active = True
                selected += [request] if request is not None and request is not row else []
            payload = row.get("payload") or row.get("message") or {}
            event = payload.get("type")
            if row.get('type') == 'assistant' and all(p.get('type') == 'thinking' for p in payload.get('content', [])):
                continue
            if active and ((row.get("type") in ("user", "assistant") and not row.get("isMeta")) or
                           (row.get("type") == "response_item" and event != "reasoning" and
                            (event != "message" or payload.get("role") == "assistant" or
                             isinstance(spoken, dict)))):
                selected.append(row)
            if active and row.get("type") == "event_msg" and event in ("task_complete", "turn_aborted"):
                selected.append(row)
                break
            if active and kind == 'claude-code' and payload.get('stop_reason') == 'end_turn':
                break
    return SECRET_SHAPES.sub("[REDACTED]", "\n".join(json.dumps(row, ensure_ascii=False) for row in selected))
