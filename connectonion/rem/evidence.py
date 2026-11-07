"""
Purpose: Lay out one investigation's gathered material as files an agent searches, instead of chunks a model summarises
LLM-Note:
  Dependencies: imports from [hashlib, json, pathlib, .chat.CHAT_KINDS] | imported by [rem/investigate.py] | tested by [tests/unit/test_rem_evidence.py]
  Data flow: write_evidence(directory, items) → searchable files, index.md and unchanged originals.json → {"index", "originals", "files", "sources", "chars"}
  State/Effects: writes under the given directory only (0700); the caller owns retention

Why files (#1850, owner 2026-09-24/30). The script has already gathered and
sorted the material; summarising all of it before writing a word cost the
owner's own page 40 calls, 16.2M input tokens and 75 minutes. So the material
is put where an agent looks for things, and the one investigate turn goes and
finds what each Unknown needs with rg, sed and ls. Summarising everything is
maintenance's job; investigation goes looking for answers.

Every entry's heading carries its source id, because that id is what the page
cites and what the validator accepts, so a search hit names one message even
though a month of mail shares a file (#2080: one file per mail meant one tool
call per mail). A session or a chat is one file, because a line of it means
little outside the conversation around it.
"""

import hashlib
import json
import re
from pathlib import Path

from .chat import CHAT_KINDS
from .files import RemError, read_json, safe_path, state_path, write_json

INDEX = "index.md"


# A file the agent reads in one go. One file per mail made Corin Marsh's 98k
# characters 373 files; the agent re-sends its whole context with every file
# it opens, and the turn cost 2.77M input tokens (#2080). A month of one
# mailbox is one file, split when it passes this.
FILE_CHARS = 40_000


def _group(item: dict) -> str:
    source = str(item.get("source", ""))
    kind = source.split(":")[0]
    if kind in CHAT_KINDS:
        return f"{kind}:{item.get('correspondent') or item.get('subject') or 'chat'}"
    if item.get("role") == "attachment" or source.startswith("project-source:"):
        return source   # one snapshot/document per file keeps its index entry discoverable
    if source.count(":") < 2:
        # Mail: a month per mailbox. Each entry keeps its `### <source id>`
        # heading, so a search hit still names the one message to cite.
        return f"{kind}:{str(item.get('timestamp', ''))[:7] or 'undated'}"
    return source.rsplit(":", 1)[0]   # the session, excluding its offset and optional text hash


def _file_name(group: str, first: str) -> str:
    kind = group.split(":")[0] or "other"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", group.split(":", 1)[-1])[:40].strip("-") or "item"
    short = hashlib.sha256(group.encode()).hexdigest()[:8]
    return f"{kind}/{first[:10] or 'undated'}_{slug}_{short}.md"


def _entry(item: dict) -> str:
    who = item.get("speaker") or item.get("role") or ""
    local = f" · local {item['local_time']}" if item.get("local_time") else ""
    head = f"### {item.get('source', '')} · {item.get('timestamp', '')}{local} · {who}"
    detail = [f"{label}: {item[key]}" for key, label in (("subject", "Subject"), ("correspondent", "With"),
                                                       ("thread", "Provider thread"),
                                                       ("project", "Project"), ("reference", "Reference"),
                                                       ("timestamp_scope", "Timestamp scope"),
                                                       ("origin", "Snapshot origin"),
                                                       ("captured_at", "Captured at"),
                                                       ("retained_at", "Retained at"),
                                                       ("body_format", "Body format"),
                                                       ("input_scope", "Input scope"),
                                                       ("comparison_scope", "Comparison scope"),
                                                       ("relationship_scope", "Relationship scope"))
              if item.get(key)]
    if item.get("participants"):
        detail.append("Participants: " + json.dumps(item["participants"], ensure_ascii=False))
    return "\n".join([head, *detail, "", str(item.get("text", "")), ""])


def _split(group: str, entries: list[dict]):
    """A group past FILE_CHARS in parts, whole entries each: `outlook:2026-09`, `outlook:2026-09 part 2`."""
    parts, size = [[]], 0
    for item in entries:
        length = len(_entry(item))
        if parts[-1] and size + length > FILE_CHARS:
            parts.append([])
            size = 0
        parts[-1].append(item)
        size += length
    for number, part in enumerate(parts, 1):
        yield (group if number == 1 else f"{group} part {number}"), part


def write_evidence(directory: Path, items: list[dict]) -> dict:
    """Write every item, oldest first within each file; return the index path and every citable id."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    originals = directory / "originals.json"
    write_json(originals, items)
    groups: dict[str, list[dict]] = {}
    for item in sorted(items, key=lambda i: str(i.get("timestamp", ""))):
        groups.setdefault(_group(item), []).append(item)
    groups = {name: part for group, entries in groups.items() for name, part in _split(group, entries)}
    lines, sources, total = [], [], 0
    for group, entries in sorted(groups.items(), key=lambda pair: str(pair[1][0].get("timestamp", ""))):
        name = _file_name(group, str(entries[0].get("timestamp", "")))
        text = "\n".join(_entry(item) for item in entries)
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(text, encoding="utf-8")
        total += len(text)
        sources += [str(item.get("source", "")) for item in entries if item.get("source")]
        first, last = [(item.get("local_time") or str(item.get("timestamp", "")))[:10]
                       for item in (entries[0], entries[-1])]
        who = next((str(i.get("speaker")) for i in entries if i.get("speaker")), "")
        subject = next((str(i.get("subject") or i.get("project")) for i in entries
                        if i.get("subject") or i.get("project")), "")
        span = first if first == last else f"{first}..{last}"
        lines.append(f"- {span} · {group} · {who[:60]} · {subject[:80]} · {len(entries)} entr"
                     f"{'y' if len(entries) == 1 else 'ies'} · {name} · {len(text):,} chars")
    index = directory / INDEX
    index.write_text(
        f"# Evidence index\n\n{len(items)} items in {len(groups)} files, {total:,} characters. "
        "One line per file: dates · group · who · subject · entries · file · size. Inside a file, "
        "each entry starts with `### <source id> · <timestamp> · local <local_time> · <speaker>` "
        "(local time when available); cite that source id.\n\n"
        + "\n".join(lines) + "\n", encoding="utf-8")
    return {"index": index, "originals": originals, "files": len(groups), "sources": sources, "chars": total}


def research_items(directory: Path) -> list[dict]:
    """Task-local captures of pages/searches and read-only CLI results; never fetch during validation."""
    from datetime import date

    web = safe_path(directory, "web")
    rows = read_json(safe_path(web, "sources.json"), [])
    if not isinstance(rows, list):
        raise RemError("web/sources.json must be a list of url/source, file and date entries")
    items = {}
    for row in rows:
        if not isinstance(row, dict) or any(not isinstance(row.get(k), str) for k in ("file", "date")):
            raise RemError("Each research capture needs file and date strings")
        source = row.get("url") or row.get("source")
        if not isinstance(source, str):
            raise RemError("Research captures need URL or native source IDs")
        _research_source(source)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"]):
            raise RemError("Research capture date must be YYYY-MM-DD")
        date.fromisoformat(row["date"])
        body = safe_path(web, row["file"]).read_text(encoding="utf-8")
        if not body.strip():
            raise RemError(f"Research capture has no saved text: {source}")
        item = items.setdefault(source, {"texts": [], "timestamp": row["date"]})
        if body not in item["texts"]:
            item["texts"].append(body)
        item["timestamp"] = max(item["timestamp"], row["date"])
    return [{"role": "research", "source": source, "text": "\n\n".join(item["texts"]),
             "timestamp": item["timestamp"]} for source, item in items.items()]


def _research_source(source: str) -> None:
    from urllib.parse import urlsplit

    url = urlsplit(source)
    if url.hostname and (url.hostname == "linkedin.com" or url.hostname.endswith(".linkedin.com")):
        raise RemError("LinkedIn pages must not be opened; cite a saved search result instead")
    native = re.fullmatch(r"(?:gmail|outlook|lark|github|codex|claude-code):\S+", source)
    attachment = re.fullmatch(r"(?:gmail|outlook):[0-9a-f]{12}:[^/\\\r\n]+", source)
    if not native and not attachment and (url.scheme not in ("http", "https") or not url.hostname):
        raise RemError("Research captures need an HTTP(S) URL or a native read-only source ID")


def retain_research(root: Path, text: str, items: list[dict]) -> None:
    """Keep cited captures outside disposable tasks so later reviews can still check their words."""
    from .reader_model import _source_ids

    cited = _source_ids([{"text": text}])
    for item in items:
        if item.get("role") != "research" or item["source"] not in cited:
            continue
        identity = hashlib.sha256(item["source"].encode()).hexdigest()
        digest = hashlib.sha256(item["text"].encode()).hexdigest()
        write_json(state_path(root, f"research/{identity}/{item['timestamp']}-{digest}.json"), item)


def research_contexts(root: Path, records: list[dict], *, private: bool = False) -> dict[str, dict]:
    """Resolve URL/native IDs to dated saved captures; no network or task-directory scans."""
    from .reader_model import PRIVATE, SOURCE, _source_ids

    if not state_path(root, "research").is_dir():
        return {}
    dates = {}
    for record in records:
        tail = record.get("text", "").partition("\n## Sources\n")[2]
        for match in SOURCE.finditer(tail):
            suffix = tail[match.end():].split("\n", 1)[0]
            if date := re.search(r"\b\d{4}-\d{2}-\d{2}\b", suffix):
                dates.setdefault(match[2], set()).add(date[0])
    contexts = {}
    for source in _source_ids(records):
        identity = hashlib.sha256(source.encode()).hexdigest()
        captures = [read_json(path, {}) for path in sorted(state_path(root, f"research/{identity}").glob("*.json"))]
        captures = [item for item in captures if item.get("source") == source
                    and (not dates.get(source) or item.get("timestamp") in dates[source])
                    and (private or not PRIVATE.search(item.get("text", "")))]
        if captures:
            contexts[source] = {"excerpt": "\n\n".join(dict.fromkeys(item["text"] for item in captures)),
                                "truncated": False}
            attachment = re.fullmatch(r"(?:gmail|outlook):[0-9a-f]{12}:([^/\\\r\n]+)", source)
            if attachment:
                contexts[source].update(source="attachment", filename=attachment[1], subject=attachment[1])
    return contexts


def additional_research(root: Path, directory: Path, items: list[dict]) -> list[dict]:
    """A CLI capture cannot replace authoritative supplied or archived mail/session text."""
    from .page_review import _source_item
    from .project_claim_review import original_items
    from .reader_model import cited_context

    captures = research_items(directory)
    if not captures:
        return []
    originals = original_items(items)
    native = [item for item in captures if not item["source"].startswith(("http://", "https://"))]
    records = [{"text": "\n## Sources\n" + "\n".join(
        f"- [{number}] {item['source']}" for number, item in enumerate(native, 1))}]
    retained = cited_context(root, records, private=True)
    additions = []
    for item in captures:
        original = _source_item(root, item["source"], originals)
        if original:
            additions.append(original)
        elif item not in native or item["source"] not in retained:
            additions.append(item)
    return additions
