"""Incremental read-only importer for native Codex rollout JSONL messages."""

import copy
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .files import WikiError, safe_path

MAX_SOURCE_BYTES = 16_000_000


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


def _read_rollout(path: Path, old: dict) -> tuple[bytes, dict, int]:
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise WikiError("Session exceeds the 16 MB source limit; no progress advanced")
    with path.open("rb") as source:
        data = source.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise WikiError("Session exceeds the source size limit")
    offset = old.get("offset", 0)
    if (type(offset) is not int or offset < 0 or offset > len(data)
            or (offset and hashlib.sha256(data[:offset]).hexdigest() != old.get("digest"))):
        raise WikiError("Previously processed source prefix changed; progress preserved for diagnosis")
    try:
        first = json.loads(data.split(b"\n", 1)[0])
    except (ValueError, UnicodeError) as error:
        raise WikiError("Invalid Codex session metadata") from error
    if first.get("type") != "session_meta" or not isinstance(first.get("payload"), dict):
        raise WikiError("Unrecognized Codex rollout format")
    return data, first["payload"], offset


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


def collect(subscription: dict, progress: dict, max_items: int, max_chars: int) -> Batch:
    if not subscription.get("enabled") or not subscription.get("consented"):
        raise WikiError("Source is disabled or not yet authorized; run start to confirm access")
    root, since = Path(subscription["root"]), timestamp(subscription["since"])
    result, updated, used = [], copy.deepcopy(progress), 0
    for path in source_files(subscription):
        name = path.relative_to(root).as_posix()
        old, stat = progress.get(name, {}), path.stat()
        if stat.st_size == old.get("offset") and stat.st_mtime_ns == old.get("mtime_ns"):
            continue
        data, meta, offset = _read_rollout(path, old)
        if meta.get("originator") == "co_wiki" or meta.get("source") == "co_wiki":
            continue
        if subscription.get("project") and meta.get("cwd") != subscription["project"]:
            continue
        for line in data[offset:].splitlines(keepends=True):
            if not line.endswith(b"\n"):
                break  # A running session may still be writing this last line.
            try:
                row = json.loads(line)
                item = _message(row, since)
            except (ValueError, UnicodeError, AttributeError, TypeError) as error:
                raise WikiError("Invalid complete source line; progress was not advanced") from error
            if item:
                item.update({"source": f"codex:{meta.get('id', name)}:{offset}",
                             "reference": path.as_uri(), "project": meta.get("cwd", "")})
                size = len(json.dumps(item, ensure_ascii=False))
                if size > max_chars:
                    raise WikiError("A source message exceeds the batch input limit; no progress advanced")
                if len(result) >= max_items or used + size > max_chars:
                    return Batch(result, updated)
                result.append(item)
                used += size
            offset += len(line)
            updated[name] = {"offset": offset, "digest": hashlib.sha256(data[:offset]).hexdigest(),
                             "mtime_ns": stat.st_mtime_ns}
    return Batch(result, updated)
