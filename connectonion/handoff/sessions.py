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

Compaction. Both clients keep the full history on disk and add a marker when the
model's context was compacted:

- Claude Code writes a ``user`` row with ``isCompactSummary: true`` whose text is
  the plaintext summary ("This session is being continued from a previous
  conversation…"). It is read as a ``summary`` turn.
- Codex writes a ``compacted`` row. Its summary is a ``compaction`` item holding
  only ``encrypted_content`` (0 of 107 compactions on one Mac had plaintext), so it
  cannot be read. What Codex itself kept is ``replacement_history``: the user's own
  earlier messages. Those are read as ``earlier`` turns.

So a compacted session yields: what survived the last compaction, then the turns
after it. An uncompacted one yields its last EXCERPT_TURNS turns.
"""

import json
import os
import re
from pathlib import Path

from ..rem.source import INJECTED_BLOCK

MAX_TURN_CHARS = 2000
SUMMARY_CHARS = 12000
# Only the end of a session is the task being handed off. Forty turns covers a
# discussion that settled two options; the draft names the cut so it is visible.
EXCERPT_TURNS = 40


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
    """The turns a handoff needs, oldest first: {role, text, timestamp}.

    Roles: user, assistant, and for a compacted session `summary` (Claude Code's
    plaintext summary) or `earlier` (messages Codex retained). Tool calls, tool
    output and reasoning are left out.
    """
    parse = _codex_turn if agent == "codex" else _claude_turn
    turns = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            kept = _compaction(agent, row)
            if kept is not None:
                turns = kept          # everything before is what the compaction replaced
                continue
            turn = parse(row)
            if turn:
                turns.append(turn)
    return turns


def _compaction(agent: str, row: dict) -> list[dict] | None:
    if agent == "claude" and row.get("type") == "user" and row.get("isCompactSummary"):
        text = (row.get("message") or {}).get("content")
        text = text if isinstance(text, str) else "\n".join(
            p.get("text", "") for p in text or [] if isinstance(p, dict))
        return [{"role": "summary", "text": text.strip(), "timestamp": row.get("timestamp", "")}]
    if agent == "codex" and row.get("type") == "compacted":
        payload = row.get("payload") or {}
        kept = [{"role": "summary", "text": payload["message"], "timestamp": row.get("timestamp", "")}] \
            if payload.get("message") else []
        for item in payload.get("replacement_history") or []:
            turn = _codex_turn({"type": "response_item", "payload": item, "timestamp": row.get("timestamp", "")})
            if turn and turn["role"] == "user":
                kept.append(dict(turn, role="earlier"))
        return kept
    return None


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


def excerpt(turns: list[dict], limit: int = EXCERPT_TURNS) -> list[dict]:
    """What survived compaction (always kept), then the last `limit` turns after it."""
    head = [t for t in turns if t["role"] in ("summary", "earlier")]
    tail = [t for t in turns if t["role"] not in ("summary", "earlier")][-limit:]
    return [dict(t, text=_clip(t["text"], SUMMARY_CHARS if t["role"] == "summary" else MAX_TURN_CHARS))
            for t in head + tail]


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[cut by co handoff: {len(text) - limit} more characters]"


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
    if row.get("type") not in ("user", "assistant") or row.get("isMeta") or row.get("isSidechain"):
        return None
    content = (row.get("message") or {}).get("content")
    if isinstance(content, list):
        content = "\n".join(part.get("text", "") for part in content
                            if isinstance(part, dict) and part.get("type") == "text")
    if not isinstance(content, str):
        return None
    return _spoken(row["type"], content, row.get("timestamp", ""))


def _spoken(role: str, text: str, when: str) -> dict | None:
    if not text.strip():
        return None
    if role == "user" and INJECTED_BLOCK.match(text):
        return None
    return {"role": role, "text": text.strip(), "timestamp": when}
