"""Incremental read-only importer for native Codex rollout JSONL messages."""

import copy
import hashlib
import json
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


def source_files(subscription: dict) -> list[Path]:
    root = Path(subscription["root"])
    if root.is_symlink():
        raise WikiError("Session source root cannot be a symlink")
    paths = sorted(root.rglob("rollout-*.jsonl"))
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
def _read_rollout(path: Path, old: dict):
    offset = old.get("offset", 0)
    if type(offset) is not int or offset < 0:
        raise WikiError("Invalid source progress; preserve it for diagnosis")
    with path.open("rb") as source:
        try:
            first = json.loads(source.readline(1_000_000))
        except (ValueError, UnicodeError) as error:
            raise WikiError("Invalid Codex session metadata") from error
        if first.get("type") != "session_meta" or not isinstance(first.get("payload"), dict):
            raise WikiError("Unrecognized Codex rollout format")
        source.seek(0)
        digest = _verify_prefix(source, offset, old.get("digest"))
        yield source, first["payload"], offset, digest


def _message(row: dict, since: datetime) -> dict | None:
    payload = row.get("payload", {})
    if row.get("type") != "response_item" or payload.get("type") != "message":
        return None
    if payload.get("role") not in ("user", "assistant"):
        return None
    if timestamp(row.get("timestamp")) < since:
        return None
    content = payload.get("content", [])
    text = "\n".join(part["text"] for part in content if isinstance(part, dict)
                     and part.get("type") in ("input_text", "output_text")
                     and isinstance(part.get("text"), str))
    if not text.strip():
        return None
    return {"role": payload["role"], "text": text, "timestamp": row["timestamp"]}


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
    root, since = Path(subscription["root"]), timestamp(subscription["since"])
    result, updated, used = [], copy.deepcopy(progress), 0
    # Newest session first. A first start faces a week of backlog and a daily attempt
    # cap; walking it oldest-first would leave the notebook describing last Monday
    # until the cap ran out. Progress is per file, so the order changes nothing else.
    for path in sorted(source_files(subscription), key=lambda p: p.stat().st_mtime_ns, reverse=True):
        name = path.relative_to(root).as_posix()
        old, stat = progress.get(name, {}), path.stat()
        if stat.st_size == old.get("offset") and stat.st_mtime_ns == old.get("mtime_ns"):
            continue
        # Messages are appended with their own time, so a file last written before the
        # lookback cannot hold one inside it. On first start this is most of the store.
        if datetime.fromtimestamp(stat.st_mtime, timezone.utc) < since:
            continue
        with _read_rollout(path, old) as (source, meta, offset, digest):
            if meta.get("originator") == "co_wiki" or meta.get("source") == "co_wiki":
                continue
            if subscription.get("project") and meta.get("cwd") != subscription["project"]:
                continue
            scanned = 0
            while scanned < SCAN_BYTES_PER_PASS:
                line = source.readline()
                if not line or not line.endswith(b"\n"):
                    break  # A running session may still be writing this last line.
                item = None
                # Nearly every byte of a large rollout is tool output. Only lines that can
                # be a user/assistant message are worth parsing; the rest are consumed as-is.
                if b"message" in line and b"role" in line:
                    try:
                        row = json.loads(line)
                        item = _message(row, since) if row.get("type") == "response_item" else None
                    except (ValueError, UnicodeError, AttributeError, TypeError) as error:
                        raise WikiError("Invalid complete source line; progress was not advanced") from error
                if item:
                    item.update({"source": f"codex:{meta.get('id', name)}:{offset}",
                                 "reference": path.as_uri(), "project": meta.get("cwd", "")})
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
