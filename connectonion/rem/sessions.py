"""One page per conversation the owner typed in; no model."""

import hashlib
import json
import re
import time
from collections import Counter
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, service, source
from .files import (SECRET_SHAPES, WRITE_WAIT_SECONDS, Notebook, RemError,
                    maintenance_lock, read_json, state_path, write_json)
from .scan import project_exclusion
from .project_material import REDACTED, page_folders, page_for, retain_cited_sessions
from .page_review import _plain, _quoted_in

AGENTS = {"codex": "Codex", "claude-code": "Claude Code"}
PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+\b")
COMMIT = re.compile(r"^\[([^\]\n]+?) (?:\(root-commit\) )?([0-9a-fA-F]{7,})\] (.+)$", re.M)
NOTABLE = re.compile(r"^(?:git (?:commit|push|merge|rebase)|gh (?:pr|release|workflow run)|"
                     r"npm publish|twine upload|uv publish|docker|wrangler|vercel|gcloud|ssh|"
                     r"\./deploy[^\s]*|[^\s]*deploy[^\s]*\.sh|co (?:deploy|rem))(?:\s|$)")
SHELL_TOOLS = {"exec", "exec_command", "shell", "shell_command", "run_shell_command", "Bash"}


def _tool_calls(row: dict, kind: str) -> list[str]:
    if kind == "codex":
        payload = row.get("payload") or {}
        if row.get("type") != "response_item":
            return []
        text = {"function_call": payload.get("arguments"),
                "custom_tool_call": payload.get("input")}.get(payload.get("type"))
        return [text] if isinstance(text, str) else []
    if row.get("type") != "assistant" or row.get("isSidechain"):
        return []
    return [json.dumps(block["input"]) for block in (row.get("message") or {}).get("content", [])
            if isinstance(block, dict) and block.get("type") == "tool_use" and "input" in block]


def _touched(text: str, cwd: str) -> Counter:
    # Tool bodies can contain whole files; project evidence only needs their head.
    text = text[:20_000]
    workdir = re.search(r'"workdir"\s*:\s*"([^"\n]+)"', text)
    here = Path(workdir[1] if workdir else cwd)
    paths = Counter(re.findall(r"(?<![\w./:~$-])/(?:[a-zA-Z0-9._@+-]+/)*[a-zA-Z0-9._@+-]+", text))
    for target in re.findall(r"\bcd\s+([^\s;&|)'\"]+)", text):
        if not target.startswith(("~", "-", "$", "/")) and here.is_absolute():
            paths[str((here / target).resolve())] += 1
    return paths


def _project(session: dict, folders: dict) -> str | None:
    cwd = session["cwd"]
    project = page_for(cwd, folders) if cwd else None
    if project:
        return project
    counts = Counter()
    for path, count in session["touched"].items():
        project = page_for(path, folders)
        if project:
            counts[project] += count
    return min(counts, key=lambda page: (-counts[page], page), default=None)


def _redact(text: str) -> str:
    return SECRET_SHAPES.sub(REDACTED, text)


def _tool_text(value, limit: int = 20_000) -> str:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        parts = []
        for part in value:
            text = _tool_text(part, limit)
            parts.append(text)
            limit -= len(text) + 1
            if limit <= 0:
                break
        return "\n".join(parts)
    if isinstance(value, dict):
        return _tool_text(list(value.values()), limit)
    return ""


def _artifact_events(row: dict, kind: str):
    if kind == "codex":
        payload = row.get("payload") or {}
        if row.get("type") != "response_item":
            return
        shape = payload.get("type")
        if shape in ("function_call", "custom_tool_call"):
            value = payload.get("arguments" if shape == "function_call" else "input", "")
            # Function arguments are JSON; freeform patches are already text.
            if isinstance(value, str) and value.lstrip().startswith("{"):
                value = json.loads(value)
            yield "call", payload.get("name", ""), value
        elif shape in ("function_call_output", "custom_tool_call_output"):
            value = payload.get("output", "")
            if isinstance(value, str) and value.lstrip().startswith("{"):
                value = json.loads(value)
            yield "output", "", value
        return
    if row.get("isSidechain") or row.get("type") not in ("assistant", "user"):
        return
    content = (row.get("message") or {}).get("content", [])
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        if row["type"] == "assistant" and block.get("type") == "tool_use":
            yield "call", block.get("name", ""), block.get("input", {})
        elif row["type"] == "user" and block.get("type") == "tool_result":
            yield "output", "", block.get("content", "")


def _command_artifacts(command: str, artifacts: dict) -> None:
    artifacts["commands"]["count"] += 1
    # Quoted commit subjects can contain separators; they are still one command.
    for line in re.findall(r'''(?:[^\n;&'"\\]|\\.|'[^']*'|"(?:[^"\\]|\\.)*")+''', command[:20_000]):
        line = line.strip()
        branch = re.match(r"git (?:checkout -b|switch -c|branch) +([^\s;&]+)", line)
        worktree = re.match(r"git worktree add\b.*? -b +([^\s;&]+)", line)
        name = branch or worktree
        if name and not name[1].startswith("-"):
            artifacts["branches"][_redact(name[1].strip("\"'"))] = None
        notable = artifacts["commands"]["notable"]
        if NOTABLE.match(line) and len(notable) < 12:
            notable[_redact(line)[:160]] = None


def _call_artifacts(name: str, value, session: dict) -> None:
    artifacts = session["artifacts"]
    data = value if isinstance(value, dict) else {}
    cwd = data.get("workdir") or data.get("cwd") or session["cwd"]
    patch = value if isinstance(value, str) else data.get("patch", data.get("cmd", data.get("command", "")))
    paths = re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", _tool_text(patch), re.M)
    if name.rsplit(".", 1)[-1] in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        paths += [data.get("file_path") or data.get("notebook_path") or ""]
    for path in filter(None, paths):
        resolved = Path(cwd) / path.strip()
        artifacts["files"][_redact(str(resolved.resolve() if resolved.is_absolute() else resolved))] = None
    command = data.get("cmd", data.get("command"))
    if isinstance(command, list):
        command = command[-1] if len(command) >= 3 and command[1] in ("-c", "-lc") else " ".join(command)
    tool = name.rsplit(".", 1)[-1]
    if isinstance(value, str) and tool in SHELL_TOOLS:
        command = value
    if isinstance(command, str) and (tool in SHELL_TOOLS or not name):
        _command_artifacts(command, artifacts)


def _collect_artifacts(row: dict, session: dict) -> None:
    artifacts = session["artifacts"]
    for event, name, value in _artifact_events(row, session["kind"]):
        if event == "call":
            _call_artifacts(name, value, session)
            continue
        text = _tool_text(value)
        for url in PR_URL.findall(text):
            artifacts["prs"][_redact(url)] = None
        for branch, sha, subject in COMMIT.findall(text):
            artifacts["commits"].setdefault(sha.lower(), {
                "sha": _redact(sha), "branch": _redact(branch), "subject": _redact(subject)})
            artifacts["branches"][_redact(branch)] = None


def _artifact_lists(artifacts: dict) -> dict:
    return {"prs": list(artifacts["prs"]), "commits": list(artifacts["commits"].values()),
            "branches": list(artifacts["branches"]), "files": list(artifacts["files"])[:30],
            "file_count": len(artifacts["files"]), "commands": {
                "count": artifacts["commands"]["count"], "notable": list(artifacts["commands"]["notable"])}}


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
                   "kind": kind, "messages": [], "reply": "", "touched": Counter(),
                   "artifacts": {"prs": {}, "commits": {}, "branches": {}, "files": {},
                                 "commands": {"count": 0, "notable": {}}}}
        reasons = set()
        offset = 0
        transcript.seek(0)  # Claude's first row can itself be the first typed message.
        for line in transcript:
            at, offset = offset, offset + len(line)
            if not line.endswith(b"\n") or not any(token in line for token in
                    (b'"message"', b'"function_call"', b'"custom_tool_call"',
                     b'"function_call_output"', b'"custom_tool_call_output"')):
                continue
            try:
                row = json.loads(line)
                item = parsers["message"](row, since, meta) if isinstance(row, dict) else None
                if isinstance(row, dict):
                    _collect_artifacts(row, session)
            except (ValueError, UnicodeError, AttributeError, TypeError, RemError):
                continue  # Clients can leave a torn row while appending.
            if not isinstance(row, dict):
                continue
            for text in _tool_calls(row, kind):
                session["touched"].update(_touched(text, session["cwd"]))
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
    session["artifacts"] = _artifact_lists(session["artifacts"])
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


def summary_path(root: Path, key: str) -> Path:
    return state_path(root, f"session-summaries/{hashlib.sha256(key.encode()).hexdigest()}.json")


def read_summary(root: Path, key: str) -> dict:
    saved = read_json(summary_path(root, key), {})
    return saved if saved.get("key") == key else {}


def _decision_lines(saved: dict, messages: list[dict], zone) -> list[str]:
    originals = [(source.timestamp(m["timestamp"]).astimezone(zone).strftime("%H:%M"), _plain(m["text"]))
                 for m in messages]
    return [f"- “{decision['quote']}” ({decision['time']})" for decision in saved.get("decisions", [])
            if decision.get("quote", "").strip() and any(
                clock == decision.get("time") and _quoted_in(decision["quote"], text)
                for clock, text in originals)]


def _followup_lines(saved: dict, notebook: Notebook) -> list[str]:
    followups = saved.get("followups", [])
    if not followups:
        return []
    targets = []
    for category in ("people", "projects"):
        for record in notebook.list(category):
            title = notebook.read(record).splitlines()[0].removeprefix("# ")
            if pattern := _name_pattern(title):
                targets.append((title, record, pattern))
    targets.sort(key=lambda target: -len(target[0]))
    pattern = "|".join(f"(?P<n{i}>{target[2]})" for i, target in enumerate(targets))
    def link(match):
        record = targets[int(match.lastgroup[1:])][1]
        return f"[{match[0]}](../{record})"
    return ["- " + (re.sub(pattern, link, text) if pattern else text) for text in followups]


def _artifact_lines(artifacts: dict) -> list[str]:
    lines = []
    if artifacts["prs"]:
        lines.append("- Pull requests: " + ", ".join(artifacts["prs"]))
    for commit in artifacts["commits"][:20]:
        lines.append(f"- Commits: `{commit['sha']}` {commit['subject']} ({commit['branch']})")
    if len(artifacts["commits"]) > 20:
        lines.append(f"- … and {len(artifacts['commits']) - 20} more commits")
    if artifacts["branches"]:
        lines.append("- Branches: " + ", ".join(artifacts["branches"]))
    if artifacts["file_count"]:
        lines.append(f"- Files changed ({artifacts['file_count']}): " + ", ".join(artifacts["files"]))
    commands = artifacts["commands"]
    if commands["count"]:
        notable = "; notable: " + "; ".join(f"`{line}`" for line in commands["notable"]) if commands["notable"] else ""
        lines.append(f"- Commands: {commands['count']} run{notable}")
    return lines


def _structure_lines(session: dict, notebook: Notebook, folders: dict, zone, day: str) -> list[str]:
    messages = session["messages"]
    cwd = session["cwd"]
    project = _project(session, folders)
    title = notebook.read(project).splitlines()[0].removeprefix("# ") if project else ""
    linked = f"[{title}](../{project})" if project else cwd
    saved = read_summary(notebook.root, f"{session['kind']}:{session['id']}")
    started = _title(session)
    heading = saved.get("title") or started
    lines = [f"# {heading}", ""]
    if saved:
        lines += ["## Summary", saved.get("summary", ""), ""]
    lines += ["## Facts", f"- Date: {day}",
             f"- Agent: {AGENTS[session['kind']]}", f"- Project: {linked}", f"- Folder: {cwd}",
             f"- Session: {session['id']}", f"- Turns: {len(messages)}"]
    if saved:
        lines += [f"- Outcome: {saved.get('outcome', 'unknown')}", f"- Tags: {', '.join(saved.get('tags', []))}"]
        if saved.get("title"):
            lines.append(f"- Started with: {started}")
        for heading, content in (("Decisions", _decision_lines(saved, messages, zone)),
                                 ("Follow-ups", _followup_lines(saved, notebook))):
            if content:
                lines += ["", f"## {heading}", *content]
    artifacts = _artifact_lines(session["artifacts"])
    if artifacts:
        lines += ["", "## Artifacts", *artifacts]
    return lines


def _page(session: dict, notebook: Notebook, folders: dict, zone) -> tuple[str, str]:
    messages = session["messages"]
    day = source.timestamp(messages[0]["timestamp"]).astimezone(zone).date().isoformat()
    lines = [*_structure_lines(session, notebook, folders, zone, day), "", "## What you typed"]
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


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {heading}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match[1] if match else ""


def _excerpt(text: str) -> str:
    return " ".join(re.sub(r"^> ?", "", text, flags=re.M).split())[:300]


def reader_fields(text: str) -> dict:
    facts = dict(re.findall(r"^- ([A-Za-z ]+): (.*)$", _section(text, "Facts"), re.M))
    project = re.fullmatch(r"\[[^\n]*\]\(\.\./([^\n]+)\)", facts.get("Project", ""))
    typed = _section(text, "What you typed")
    clock = re.search(r"^### (\d{2}:\d{2})$", typed, re.M)
    first = re.sub(r"^### [^\n]*\n", "", typed, count=1, flags=re.M)
    first = re.split(r"^### ", first, maxsplit=1, flags=re.M)[0]
    heading = re.search(r"^# (.+)$", text, re.M)
    artifacts = _section(text, "Artifacts")
    files = re.search(r"^- Files changed \((\d+)\):", artifacts, re.M)
    commits = re.search(r"^- … and (\d+) more commits$", artifacts, re.M)
    started = next((line.removeprefix("> ").strip() for line in first.splitlines()
                    if line.removeprefix("> ").strip()), "")
    started = " ".join(started.split())
    started = started[:79] + "…" if len(started) > 80 else started
    return {"session_project": project[1] if project else "", "session_date": facts.get("Date", ""),
            "session_time": clock[1] if clock else "", "session_agent": facts.get("Agent", ""),
            "session_turns": int(facts.get("Turns", "0")), "session_folder": facts.get("Folder", ""),
            "session_first": _excerpt(first), "session_reply": _excerpt(_section(text, "Final reply")),
            "session_title": heading[1] if heading else "", "session_summary": _section(text, "Summary").strip(),
            "session_tags": [tag.strip() for tag in facts.get("Tags", "").split(",") if tag.strip()],
            "session_outcome": facts.get("Outcome", ""), "session_started_with": facts.get("Started with", started),
            "session_artifacts": {"prs": len(set(PR_URL.findall("\n".join(re.findall(r"^- Pull requests: (.*)$", artifacts, re.M))))),
                                  "commits": len(re.findall(r"^- Commits:", artifacts, re.M)) + (int(commits[1]) if commits else 0),
                                  "files": int(files[1]) if files else 0}}


def _names(person: dict) -> list[str]:
    aliases = re.findall(r"^- Also known as: (.*)$", person["text"], re.M)
    names = [person["title"], *(name for alias in aliases for name in re.split(r"[,;]", alias))]
    names = [re.sub(r"\[(?:[A-Za-z]*\d+)\]", "", name).strip() for name in names]
    return [name for name in names if name and name.casefold() != "unknown"]


def _name_pattern(name: str) -> str:
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\uf900-\ufaff]", name):
        return re.escape(name) if len(name) >= 2 else ""
    if len(name) < 3:
        return ""
    pattern = re.escape(name)
    if len(name.split()) >= 2:
        pattern = f"(?i:{pattern})"
    elif len(re.findall(r"[^\W\d_]", name)) < 3:
        return ""
    # Latin edges only: "让Ody看看" names Ody, "melody" does not.
    return rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])"


def mentions(people: list[dict], sessions: list[dict]) -> dict[str, list[str]]:
    ordered = sorted(sessions, key=lambda row: row["path"])
    ordered.sort(key=lambda row: (row.get("session_date", ""), row.get("session_time", "")), reverse=True)
    typed = [(row["path"], _section(row["text"], "What you typed")) for row in ordered]
    found = {}
    for person in people:
        if person.get("needs_review"):
            continue
        patterns = [_name_pattern(name) for name in _names(person)]
        pattern = "|".join(filter(None, patterns))
        matches = [path for path, text in typed if pattern and re.search(pattern, text)]
        if matches:
            found[person["path"]] = matches
    return found


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
                                     "record": record, "session": key, "since": since.isoformat()}
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
        settings = {"days": days, "timezone": str(zone), "format": 3}
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


def rewrite_session(root: Path, key: str, *, lock_held: bool = False) -> str:
    with nullcontext() if lock_held else maintenance_lock(root, wait=WRITE_WAIT_SECONDS):
        progress = read_json(state_path(root, "sessions.json"), {"files": {}})
        matches = [(Path(path), entry) for path, entry in progress["files"].items()
                   if entry.get("session") == key and entry.get("record")]
        if not matches:
            raise RemError("Session has not been imported")
        path, entry = matches[-1]
        if path.is_symlink() or not path.is_file():
            raise RemError("Session transcript is missing or linked")
        # Preserve the import window: a summary must not pull older turns back in.
        since = source.timestamp(entry["since"]) if entry.get("since") else datetime.min.replace(tzinfo=timezone.utc)
        session, why = _read_session(path, key.split(":", 1)[0], since)
        if why or f"{session['kind']}:{session['id']}" != key:
            raise RemError("Session transcript no longer contains the imported conversation")
        notebook = Notebook(root)
        zone = ZoneInfo(progress.get("settings", {}).get("timezone") or "UTC")
        _, page = _page(session, notebook, page_folders(notebook), zone)
        notebook.write(entry["record"], page)
        retain_cited_sessions(root, session["messages"], {m["source"] for m in session["messages"]}, replace=True)
        return entry["record"]


def summary(report: dict) -> str:
    return (f"AI sessions: {report['imported']} imported, {report['updated']} updated, "
            f"{report['unchanged']} unchanged; {sum(report['skipped'].values())} skipped; {report['seconds']}s")
