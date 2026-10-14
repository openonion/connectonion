"""Sessions from coding agents besides Codex and Claude Code (#2501): Gemini CLI, opencode, Factory's
droid and Cursor. Each is read where the agent itself keeps it, into the turns `sessions` works on:
{role: user|assistant, text, timestamp}. What was said, never tool calls or their output.

Where each one keeps a session, as found on a real machine (2026-10-14):
  gemini    ~/.gemini/tmp/<sha256(project) or a name>/chats/session-*.json(l); "projectHash" is the
            sha256 of the project's folder, messages are {timestamp, type: user|gemini|info, content}
  opencode  ~/.local/share/opencode/storage/session/<project>/<ses_id>.json holds "directory"; its
            messages are message/<ses_id>/*.json {role, time.created}, their text part/<msg_id>/*.json
  droid     ~/.factory/sessions/<folder with / as ->/<id>.jsonl; rows {type: message, timestamp,
            message: {role, content}} as Claude Code writes them, the first {type: session_start, cwd}
  cursor    Cursor's own database (globalStorage/state.vscdb): composerData:<id> lists its bubbles,
            bubbleId:<id>:<bubble> {type: 1 user | 2 assistant, text}; a workspace's own state.vscdb
            names the conversations held for its folder. Copied out to ~/.co/handoff/imported/cursor/.
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote

AGENTS = ("gemini", "opencode", "droid", "cursor")
NAMES = {"gemini": "Gemini CLI", "opencode": "opencode", "droid": "droid", "cursor": "Cursor"}
INJECTED = re.compile(r"^\s*<(?:system-reminder|session_context)>")


def candidates(agent: str, cwd: Path) -> list[Path]:
    """The sessions `agent` holds for `cwd`, newest first by when they were last written."""
    found = {"gemini": _gemini_sessions, "opencode": _opencode_sessions, "droid": _droid_sessions,
             "cursor": _cursor_sessions}[agent](Path(cwd).resolve())
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def turns(agent: str, path: Path) -> list[dict]:
    rows = {"gemini": _gemini_turns, "opencode": _opencode_turns, "droid": _droid_turns,
            "cursor": _imported_turns}[agent](Path(path))
    return [t for t in (_turn(role, text, when) for role, text, when in rows) if t]


def folder(agent: str, path: Path) -> Path | None:
    """The folder the session worked in, for where its code is."""
    path = Path(path)
    if agent == "gemini":
        root = path.parent.parent / ".project_root"
        return Path(root.read_text(encoding="utf-8").strip()) if root.exists() else None
    if agent == "opencode":
        return Path(json.loads(path.read_text(encoding="utf-8"))["directory"])
    if agent == "droid":
        with path.open(encoding="utf-8") as f:
            first = json.loads(f.readline() or "{}")
        return Path(first["cwd"]) if first.get("cwd") else None
    with path.open(encoding="utf-8") as f:
        first = json.loads(f.readline() or "{}")
    return Path(first["folder"]) if first.get("folder") else None


def kind_of(path: Path) -> str | None:
    """Which of AGENTS wrote the session at `path`, by where it is kept."""
    path = Path(path).resolve()
    homes = {"gemini": _gemini_home() / "tmp", "opencode": _opencode_home() / "session",
             "droid": _droid_home() / "sessions", "cursor": imported_home() / "cursor"}
    return next((agent for agent, home in homes.items() if home.resolve() in path.parents), None)


def _turn(role: str, text: str, when: str) -> dict | None:
    from .sessions import _spoken
    text = "\n".join(part for part in text.split("\n\n") if not INJECTED.match(part)) if role == "user" else text
    return _spoken(role, text, when)


def _iso(ms) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---- Gemini CLI ----

def _gemini_home() -> Path:
    return Path(os.environ.get("GEMINI_CLI_HOME") or Path.home()) / ".gemini"


def _gemini_sessions(cwd: Path) -> list[Path]:
    wanted = hashlib.sha256(str(cwd).encode()).hexdigest()
    return [p for p in (_gemini_home() / "tmp").glob("*/chats/session-*.json*") if _gemini_meta(p).get("projectHash") == wanted]


def _gemini_meta(path: Path) -> dict:
    """A .json session is one object; a .jsonl one starts with its header."""
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    with path.open(encoding="utf-8") as f:
        return json.loads(f.readline() or "{}")


def _gemini_turns(path: Path) -> list[tuple]:
    if path.suffix == ".json":
        messages = json.loads(path.read_text(encoding="utf-8")).get("messages", [])
    else:   # .jsonl: a header, then rows that set the messages or add one
        messages = []
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            row = json.loads(line) if line.strip() else {}
            if isinstance(row.get("$set"), dict) and "messages" in row["$set"]:
                messages = row["$set"]["messages"]
            elif row.get("type"):
                messages.append(row)
    role = {"user": "user", "gemini": "assistant"}
    return [(role[m["type"]], _gemini_text(m.get("content")), m.get("timestamp", ""))
            for m in messages if m.get("type") in role]


def _gemini_text(content) -> str:
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


# ---- opencode ----

def _opencode_home() -> Path:
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return data / "opencode" / "storage"


def _opencode_sessions(cwd: Path) -> list[Path]:
    return [p for p in (_opencode_home() / "session").glob("*/ses_*.json")
            if json.loads(p.read_text(encoding="utf-8")).get("directory") == str(cwd)]


def _opencode_turns(path: Path) -> list[tuple]:
    home = _opencode_home()
    messages = [json.loads(p.read_text(encoding="utf-8")) for p in (home / "message" / path.stem).glob("msg_*.json")]
    rows = []
    for message in sorted(messages, key=lambda m: (m.get("time") or {}).get("created", 0)):
        parts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((home / "part" / message["id"]).glob("prt_*.json"))]
        text = "\n".join(p.get("text", "") for p in parts if p.get("type") == "text" and not p.get("synthetic"))
        rows.append((message.get("role"), text, _iso((message.get("time") or {}).get("created", 0))))
    return [r for r in rows if r[0] in ("user", "assistant")]


# ---- droid (Factory) ----

def _droid_home() -> Path:
    return Path.home() / ".factory"


def _droid_sessions(cwd: Path) -> list[Path]:
    return list((_droid_home() / "sessions" / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))).glob("*.jsonl"))


def _droid_turns(path: Path) -> list[tuple]:
    from .sessions import _text
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line) if line.strip() else {}
        message = row.get("message") or {}
        if row.get("type") == "message" and message.get("role") in ("user", "assistant"):
            content = message.get("content")
            if isinstance(content, list):   # droid puts its reminders in their own text parts
                content = [p for p in content if not (isinstance(p, dict) and INJECTED.match(p.get("text", "")))]
            rows.append((message["role"], _text(content), row.get("timestamp", "")))
    return rows


# ---- Cursor ----

def _cursor_storage() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Cursor" / "User"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "Cursor" / "User"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "Cursor" / "User"


def imported_home() -> Path:
    from ..environment import global_config_dir
    return global_config_dir() / "handoff" / "imported"


def _db(path: Path) -> sqlite3.Connection:
    """Read Cursor's database where it is, without writing to it or waiting on Cursor."""
    return sqlite3.connect(f"file:{quote(str(path))}?immutable=1", uri=True)


def _cursor_sessions(cwd: Path) -> list[Path]:
    """Cursor's conversations for `cwd`, each copied out as turns so the rest reads them as files."""
    found = []
    for workspace in (_cursor_storage() / "workspaceStorage").glob("*/workspace.json"):
        uri = json.loads(workspace.read_text(encoding="utf-8")).get("folder", "")
        if not uri.startswith("file://") or Path(unquote(uri[len("file://"):])) != cwd:
            continue
        state = workspace.parent / "state.vscdb"
        row = _db(state).execute("SELECT value FROM ItemTable WHERE key = 'composer.composerData'").fetchone() \
            if state.exists() else None
        for composer in (json.loads(row[0]).get("allComposers", []) if row else []):
            found += [p for p in [_export(composer["composerId"], cwd)] if p]
    return found


def _export(composer_id: str, cwd: Path) -> Path | None:
    db = _db(_cursor_storage() / "globalStorage" / "state.vscdb")
    row = db.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (f"composerData:{composer_id}",)).fetchone()
    data = json.loads(row[0]) if row and row[0] else {}
    heads = data.get("fullConversationHeadersOnly") or []
    if not heads:
        return None
    started = data.get("createdAt") or 0
    lines = [json.dumps({"id": composer_id, "folder": str(cwd), "name": data.get("name", "")})]
    for head in heads:
        bubble = db.execute("SELECT value FROM cursorDiskKV WHERE key = ?",
                            (f"bubbleId:{composer_id}:{head['bubbleId']}",)).fetchone()
        bubble = json.loads(bubble[0]) if bubble and bubble[0] else {}
        when = bubble.get("createdAt") or (bubble.get("timingInfo") or {}).get("clientRpcSendTime") or started
        lines.append(json.dumps({"role": "user" if head.get("type") == 1 else "assistant",
                                 "text": bubble.get("text", ""), "timestamp": _iso(when) if str(when).isdigit() else when},
                                ensure_ascii=False))
    path = imported_home() / "cursor" / f"{composer_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    updated = int(data.get("lastUpdatedAt") or started) / 1000
    os.utime(path, (updated, updated))   # newest is the one Cursor last wrote, not the one copied last
    return path


def _imported_turns(path: Path) -> list[tuple]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[1:] if line.strip()]
    return [(r["role"], r["text"], r["timestamp"]) for r in rows]
