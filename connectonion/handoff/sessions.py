"""Read the coding-agent conversation a handoff is drafted from.

Two on-disk formats, both checked on a real Mac (codex-cli 0.162.1, Claude Code 2.1):

- Codex: ``$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<time>-<thread id>.jsonl``.
  Row 1 is ``session_meta`` with ``payload.cwd``; a turn is a ``response_item``
  whose payload is ``{"type": "message", "role": "user"|"assistant", "content": [...]}``.
  Inside Codex the shell has ``CODEX_THREAD_ID``.
- Claude Code: ``~/.claude/projects/<cwd with every non-alphanumeric as ->/<session>.jsonl``.
  A turn is a row with ``type`` user/assistant and a ``message``; ``isMeta`` and
  ``isSidechain`` rows are the client talking to itself. Inside Claude Code the
  shell has ``CLAUDE_CODE_SESSION_ID``.

Both clients write far more into the user slot than anyone typed (AGENTS.md,
environment context, skill bodies); `INJECTED_BLOCK` from co rem's importer is the
measured filter for that, reused rather than re-learned.

What a handoff keeps, the way a compaction does: every message the person typed,
word for word, and what the AI said, to be summarised. Tool calls, tool output
and reasoning are never read.

Compaction. Both clients keep the full history on disk and only add a marker when
the model's context was compacted, so the whole conversation is read from the
start and the markers are skipped:

- Claude Code writes a ``user`` row with ``isCompactSummary: true`` (the client's
  summary, not the person's words).
- Codex writes a ``compacted`` row whose ``replacement_history`` repeats user
  messages already earlier in the rollout; its summary is encrypted anyway.

A message the person typed while Claude Code was mid-turn is not a ``user`` row: it
is an ``attachment`` row of type ``queued_command`` with ``origin.kind: human``.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from ..rem.source import INJECTED_BLOCK

# Written by the client into the user slot, not typed by the person.
CLIENT_NOTICE = re.compile(r"^\[Request interrupted by user")


class SessionNotFound(Exception):
    """No session for this directory; the message says what was looked for."""


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def claude_slug(cwd: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def find_session(cwd: Path, agent: str = None) -> tuple[str, Path]:
    """The current session for `cwd`: (agent, path). `agent` is codex, claude or None for either."""
    cwd = Path(cwd).resolve()
    found = []
    if agent in (None, "codex"):
        found += [("codex", p) for p in _codex_candidates(cwd)]
    if agent in (None, "claude"):
        found += [("claude", p) for p in _claude_candidates(cwd)]
    if not found:
        where = {"codex": f"{codex_home() / 'sessions'} (cwd {cwd})",
                 "claude": str(Path.home() / ".claude" / "projects" / claude_slug(cwd))}
        looked = "; ".join(where[a] for a in (["codex", "claude"] if agent is None else [agent]))
        raise SessionNotFound(f"No coding-agent session found for {cwd}. Looked in: {looked}")
    # The live session is the one being written to right now.
    return max(found, key=lambda item: item[1].stat().st_mtime)


def _codex_candidates(cwd: Path) -> list[Path]:
    root = codex_home() / "sessions"
    thread = os.environ.get("CODEX_THREAD_ID")
    if thread:
        named = sorted(root.glob(f"*/*/*/rollout-*-{thread}.jsonl"))
        if named:
            return named[-1:]
    rollouts = sorted(root.glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p for p in rollouts[:200] if _codex_cwd(p) == cwd][:1]


def _codex_cwd(path: Path) -> Path | None:
    with path.open(encoding="utf-8") as f:
        first = json.loads(f.readline() or "{}")
    payload = first.get("payload") or {}
    # co's own Codex runs (co rem, opened handoffs) are not a person's discussion.
    if first.get("type") != "session_meta" or payload.get("originator") in ("connectonion", "co_rem"):
        return None
    return Path(payload.get("cwd", "")).resolve() if payload.get("cwd") else None


def _claude_candidates(cwd: Path) -> list[Path]:
    folder = Path.home() / ".claude" / "projects" / claude_slug(cwd)
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session and (folder / f"{session}.jsonl").exists():
        return [folder / f"{session}.jsonl"]
    files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:1]


def read_turns(agent: str, path: Path) -> list[dict]:
    """The whole conversation, oldest first: {role: user|assistant, text, timestamp}."""
    parse = _codex_turn if agent == "codex" else _claude_turn
    turns = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                turn = parse(json.loads(line))
                if turn:
                    turns.append(turn)
    return turns


def exchanges(turns: list[dict]) -> list[dict]:
    """Each user message with the AI text that followed it: {at, user, ai}."""
    found = []
    for turn in turns:
        if turn["role"] == "user":
            found.append({"at": turn["timestamp"], "user": turn["text"], "ai": ""})
        elif found:
            found[-1]["ai"] = (found[-1]["ai"] + "\n\n" + turn["text"]).strip()
    return found


def find_by_id(ref: str) -> tuple[str, Path]:
    """A session named by path, Codex thread id or Claude Code session id."""
    path = Path(ref).expanduser()
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            first = json.loads(f.readline() or "{}")
        return ("codex" if first.get("type") == "session_meta" else "claude"), path.resolve()
    named = sorted((codex_home() / "sessions").glob(f"*/*/*/rollout-*-{ref}.jsonl"))
    if named:
        return "codex", named[-1]
    named = sorted((Path.home() / ".claude" / "projects").glob(f"*/{ref}.jsonl"))
    if named:
        return "claude", named[-1]
    raise SessionNotFound(f"No session file or id '{ref}' under {codex_home() / 'sessions'} "
                          f"or {Path.home() / '.claude' / 'projects'}")


def _codex_turn(row: dict) -> dict | None:
    payload = row.get("payload") or {}
    if row.get("type") != "response_item" or payload.get("type") != "message":
        return None
    if payload.get("role") not in ("user", "assistant"):
        return None
    text = "\n".join(part.get("text", "") for part in payload.get("content") or []
                     if isinstance(part, dict) and part.get("type") in ("input_text", "output_text"))
    return _spoken(payload["role"], text, row.get("timestamp", ""))


def _claude_turn(row: dict) -> dict | None:
    attachment = row.get("attachment") or {}
    if attachment.get("type") == "queued_command" and (attachment.get("origin") or {}).get("kind") == "human":
        return _spoken("user", _text(attachment.get("prompt")), row.get("timestamp", ""))
    if row.get("type") not in ("user", "assistant") or row.get("isMeta") or row.get("isSidechain") \
            or row.get("isCompactSummary"):
        return None
    return _spoken(row["type"], _text((row.get("message") or {}).get("content")), row.get("timestamp", ""))


def _text(content) -> str:
    """A Claude Code message body: a string, or a list whose text parts are what was said."""
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content
                         if isinstance(part, dict) and part.get("type") == "text")
    return content if isinstance(content, str) else ""


def _spoken(role: str, text: str, when: str) -> dict | None:
    if not text.strip():
        return None
    if role == "user" and (INJECTED_BLOCK.match(text) or CLIENT_NOTICE.match(text)):
        return None
    return {"role": role, "text": text.strip(), "timestamp": when}


def code_at(folder: Path) -> dict | None:
    """Where the code is, so the recipient's agent can check out the same thing; None outside a repository."""
    if not shutil.which("git"):
        return None
    git = lambda *args: subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True)
    head = git("rev-parse", "HEAD")
    if head.returncode:                  # not a repository, or one without a commit yet
        return None
    remote = git("remote", "get-url", "origin").stdout.strip()
    return {"repository": re.sub(r"//[^/@]+@", "//", remote) or None,   # never a user:token@ in a URL
            "branch": git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
            "commit": head.stdout.strip(),
            "pushed": bool(git("branch", "-r", "--contains", "HEAD").stdout.strip()),
            "uncommitted": len(git("status", "--porcelain").stdout.splitlines())}
