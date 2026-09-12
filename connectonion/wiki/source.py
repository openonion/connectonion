"""Incremental read-only importers for local session transcripts (Codex, Claude Code)."""

import copy
import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .files import WikiError, safe_path

# One real machine had 18 rollouts over 16 MB in a week (the largest 426 MB, almost
# all tool output). Files are never loaded whole: the consumed prefix is re-hashed
# in chunks, and at most this many bytes of the tail are walked per pass. What is
# left waits for the next pass, exactly like an unread batch.
SCAN_BYTES_PER_PASS = 64_000_000
TRUNCATION_NOTE = "\n[truncated by co wiki: {dropped} more characters in the source]"
# Both clients write far more into the `user` turn than the user ever types, and it
# does not look like the user: Codex's <recommended_plugins>, <environment_context>,
# the repository AGENTS.md, the approval reviewer quoting the agent's own transcript
# back at it, goal re-injection; Claude Code's slash-command echoes and skill bodies.
# Measured over one real week of this machine's sessions: 1,493 of 2,062 `role: user`
# messages were the harness talking to itself, and they carried 97.2% of the
# characters -- which is where the notebook's git SHAs, CI counts, PR numbers and
# dead screenshot paths came from. A message that opens with a tag or one of these
# preambles was not typed by anyone.
INJECTED_BLOCK = re.compile(
    r"\s*(?:<[a-z_-]+(?:\s[^<>]{0,400})?>"
    r"|#\s*AGENTS\.md\b"
    r"|The following is the Codex agent history"
    r"|>>> TRANSCRIPT START"
    r"|Caveat: The messages below"
    r"|This session is being continued from a previous conversation"
    r"|Base directory for this skill:)")
# Codex tags everything it injects into the user turn with this key; a message the
# person typed carries only `role` and `type`. Structure beats pattern-matching, so
# this is the first check, and INJECTED_BLOCK above is the belt to its braces.
CODEX_INJECTED_KEY = "internal_chat_message_metadata_passthrough"
# Nobody types more than this in one message. What exceeds it is a file, a log or a
# tool result relayed as input (134M characters of it in one machine's 60 days);
# the head is kept so the maintainer knows what was pasted, the bulk is not.
MAX_MESSAGE_CHARS = 4000
# In a coding session only the user's messages are read. They are the user's
# will -- what was decided, asked for, corrected; the assistant's replies are
# execution: code, test counts, confirmations of what the user just said. Reading
# only the user halves a session (13.8k user rows against 28.8k assistant rows in
# one machine's 60 days) and loses nothing a notebook is for. Mail is different:
# there the other party is a person, and stays.
CODING_SPEAKERS = ("user",)


@dataclass
class Batch:
    items: list[dict]
    progress: dict


def timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("missing timezone")
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as error:
        raise WikiError("Source contains an invalid timestamp") from error


# ---- Codex rollouts: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl ----

def _codex_meta(first: dict) -> dict:
    if first.get("type") != "session_meta" or not isinstance(first.get("payload"), dict):
        raise WikiError("Unrecognized Codex rollout format")
    payload = first["payload"]
    if payload.get("originator") == "co_wiki" or payload.get("source") == "co_wiki":
        return {"skip": True}
    return {"id": payload.get("id"), "cwd": payload.get("cwd", "")}


def _codex_message(row: dict, since: datetime) -> dict | None:
    payload = row.get("payload", {})
    if row.get("type") != "response_item" or payload.get("type") != "message":
        return None
    if payload.get("role") not in CODING_SPEAKERS or CODEX_INJECTED_KEY in payload:
        return None
    if timestamp(row.get("timestamp")) < since:
        return None
    content = payload.get("content", [])
    text = "\n".join(part["text"] for part in content if isinstance(part, dict)
                     and part.get("type") in ("input_text", "output_text")
                     and isinstance(part.get("text"), str))
    return _spoken(payload["role"], text, row["timestamp"])


# ---- Claude Code transcripts: ~/.claude/projects/<encoded cwd>/<session>.jsonl ----

def _claude_meta(first: dict) -> dict:
    # The first row is often a snapshot or mode record without a session id; the
    # id and cwd are repeated on every message row, so they are read from there.
    return {"id": first.get("sessionId"), "cwd": first.get("cwd", "")}


def _claude_message(row: dict, since: datetime) -> dict | None:
    role = row.get("type")
    # A sidechain row is a prompt the assistant wrote for its own subagent ("You are
    # one finder angle in a code review…"): the assistant's words in the user's slot.
    if role not in CODING_SPEAKERS or row.get("isMeta") or row.get("isSidechain"):
        return None
    message = row.get("message")
    if not isinstance(message, dict):
        return None
    if timestamp(row.get("timestamp")) < since:
        return None
    content = message.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        # Text blocks only: tool_use, tool_result, thinking and images are the
        # assistant's machinery, not what either of them said. A text block can
        # still be an injection (a skill body arrives this way), so each block is
        # checked on its own rather than after being joined into one string.
        text = "\n".join(part["text"] for part in content if isinstance(part, dict)
                         and part.get("type") == "text" and isinstance(part.get("text"), str)
                         and not INJECTED_BLOCK.match(part["text"]))
    else:
        return None
    item = _spoken(role, text, row["timestamp"])
    if item:
        item["cwd"] = row.get("cwd", "")
        item["session"] = row.get("sessionId")
    return item


def _spoken(role: str, text: str, when: str) -> dict | None:
    if not text.strip():
        return None
    if role == "user" and INJECTED_BLOCK.match(text):
        return None
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[:MAX_MESSAGE_CHARS] + TRUNCATION_NOTE.format(dropped=len(text) - MAX_MESSAGE_CHARS)
    return {"role": role, "text": text, "timestamp": when}


KINDS = {
    "codex": {"glob": "rollout-*.jsonl", "meta": _codex_meta, "message": _codex_message},
    "claude-code": {"glob": "*.jsonl", "meta": _claude_meta, "message": _claude_message},
}


def source_files(subscription: dict) -> list[Path]:
    root = Path(subscription["root"])
    if root.is_symlink():
        raise WikiError("Session source root cannot be a symlink")
    pattern = KINDS[subscription.get("kind", "codex")]["glob"]
    paths = sorted(root.rglob(pattern))
    return [safe_path(root, path.relative_to(root).as_posix()) for path in paths]


def pending_metadata(subscription: dict, progress: dict) -> dict:
    root = Path(subscription["root"])
    changed = 0
    for path in source_files(subscription):
        old = progress.get(path.relative_to(root).as_posix(), {})
        stat = path.stat()
        if (stat.st_size != old.get("offset") or stat.st_mtime_ns != old.get("mtime_ns")):
            changed += 1
    return {"candidate_files": changed, "message_count": None,
            "source_available": root.is_dir(), "body_reads": False}


def _verify_prefix(source, offset: int, expected) -> "hashlib._Hash":
    """Re-hash the consumed prefix without holding it; a rewrite must not pass as an append."""
    digest = hashlib.sha256()
    remaining = offset
    while remaining:
        chunk = source.read(min(1 << 20, remaining))
        if not chunk:
            raise WikiError("Previously processed source prefix changed; progress preserved for diagnosis")
        digest.update(chunk)
        remaining -= len(chunk)
    if offset and digest.hexdigest() != expected:
        raise WikiError("Previously processed source prefix changed; progress preserved for diagnosis")
    return digest


@contextmanager
def _read_rollout(path: Path, old: dict, kind: str):
    offset = old.get("offset", 0)
    if type(offset) is not int or offset < 0:
        raise WikiError("Invalid source progress; preserve it for diagnosis")
    with path.open("rb") as source:
        try:
            first = json.loads(source.readline(1_000_000))
        except (ValueError, UnicodeError) as error:
            raise WikiError("Invalid session metadata") from error
        if not isinstance(first, dict):
            raise WikiError("Unrecognized session transcript format")
        meta = KINDS[kind]["meta"](first)
        source.seek(0)
        digest = _verify_prefix(source, offset, old.get("digest"))
        yield source, meta, offset, digest


def _fit(item: dict, max_chars: int) -> dict:
    """A pasted log in one message must not block that session forever; keep its head."""
    if len(json.dumps(item, ensure_ascii=False)) <= max_chars:
        return item
    text, keep = item["text"], len(item["text"])
    while keep > 100:
        keep = keep * 3 // 4
        cut = {**item, "text": text[:keep] + TRUNCATION_NOTE.format(dropped=len(text) - keep)}
        if len(json.dumps(cut, ensure_ascii=False)) <= max_chars:
            return cut
    raise WikiError("Batch input limit is too small to hold one message; raise limits.input_chars_per_batch")


def collect(subscription: dict, progress: dict, max_items: int, max_chars: int) -> Batch:
    if not subscription.get("enabled") or not subscription.get("consented"):
        raise WikiError("Source is disabled or not yet authorized; run start to confirm access")
    kind = subscription.get("kind", "codex")
    if kind not in KINDS:
        raise WikiError(f"No importer for source kind {kind!r}")
    parse = KINDS[kind]["message"]
    root, since = Path(subscription["root"]), timestamp(subscription["since"])
    result, updated, used = [], copy.deepcopy(progress), 0
    # Oldest session first. The notebook should grow the way the user's understanding
    # did -- later sessions revising earlier pages -- and a backfill that starts at the
    # lookback and walks forward is also the only way to exercise, in a test, what a
    # year of maintenance does to the pages. Progress is per file; order changes
    # nothing else. (`sync --all` is what makes a long backfill finish in one go.)
    for path in sorted(source_files(subscription), key=lambda p: p.stat().st_mtime_ns):
        name = path.relative_to(root).as_posix()
        old, stat = progress.get(name, {}), path.stat()
        if stat.st_size == old.get("offset") and stat.st_mtime_ns == old.get("mtime_ns"):
            continue
        # Messages are appended with their own time, so a file last written before the
        # lookback cannot hold one inside it. On first start this is most of the store.
        if datetime.fromtimestamp(stat.st_mtime, timezone.utc) < since:
            continue
        with _read_rollout(path, old, kind) as (source, meta, offset, digest):
            if meta.get("skip"):
                continue
            if subscription.get("project") and kind == "codex" and meta.get("cwd") != subscription["project"]:
                continue
            scanned = 0
            while scanned < SCAN_BYTES_PER_PASS:
                line = source.readline()
                if not line or not line.endswith(b"\n"):
                    break  # A running session may still be writing this last line.
                item = None
                # Nearly every byte of a large transcript is tool output. Only lines that
                # can be a user/assistant message are worth parsing; the rest are consumed.
                if b"message" in line and b"role" in line:
                    try:
                        row = json.loads(line)
                        item = parse(row, since) if isinstance(row, dict) else None
                    except (ValueError, UnicodeError, AttributeError, TypeError) as error:
                        raise WikiError("Invalid complete source line; progress was not advanced") from error
                if item:
                    if subscription.get("project") and kind != "codex" and item.get("cwd") != subscription["project"]:
                        item = None
                if item:
                    session = item.pop("session", None) or meta.get("id") or name
                    project = item.pop("cwd", None) or meta.get("cwd", "")
                    item.update({"source": f"{kind}:{session}:{offset}", "reference": path.as_uri(),
                                 "project": project})
                    item = _fit(item, max_chars)
                    size = len(json.dumps(item, ensure_ascii=False))
                    if len(result) >= max_items or used + size > max_chars:
                        return Batch(result, updated)
                    result.append(item)
                    used += size
                offset += len(line)
                scanned += len(line)
                digest.update(line)
                updated[name] = {"offset": offset, "digest": digest.hexdigest(),
                                 "mtime_ns": stat.st_mtime_ns}
    return Batch(result, updated)
