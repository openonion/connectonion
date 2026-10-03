"""
Purpose: Lay out one investigation's gathered material as files an agent searches, instead of chunks a model summarises
LLM-Note:
  Dependencies: imports from [hashlib, json, pathlib, .chat.CHAT_KINDS] | imported by [rem/investigate.py] | tested by [tests/unit/test_rem_evidence.py]
  Data flow: write_evidence(directory, items) → one file per mailbox-month (split past 40k chars), per attachment, per session or chat → index.md, one line per file → {"index", "files", "sources", "chars"}
  State/Effects: writes under the given directory only (0700); the caller deletes it after the run

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
from .source import timestamp

INDEX = "index.md"


# A file the agent reads in one go. One file per mail made Ody Zhou's 98k
# characters 373 files; the agent re-sends its whole context with every file
# it opens, and the turn cost 2.77M input tokens (#2080). A month of one
# mailbox is one file, split when it passes this.
FILE_CHARS = 40_000


def _order(item: dict) -> str:
    """Keep actual instant order when local offsets change across daylight saving."""
    stamp = str(item.get("timestamp", ""))
    return timestamp(stamp).isoformat() if re.search(r"T.*(?:Z|[+-]\d{2}:\d{2})$", stamp) else stamp


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
    return source.rsplit(":", 1)[0]   # a session: codex:<session>:<offset>


def _file_name(group: str, first: str) -> str:
    kind = group.split(":")[0] or "other"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", group.split(":", 1)[-1])[:40].strip("-") or "item"
    short = hashlib.sha256(group.encode()).hexdigest()[:8]
    return f"{kind}/{first[:10] or 'undated'}_{slug}_{short}.md"


def _entry(item: dict) -> str:
    who = item.get("speaker") or item.get("role") or ""
    head = f"### {item.get('source', '')} · {item.get('timestamp', '')} · {who}"
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
    groups: dict[str, list[dict]] = {}
    for item in sorted(items, key=_order):
        groups.setdefault(_group(item), []).append(item)
    groups = {name: part for group, entries in groups.items() for name, part in _split(group, entries)}
    lines, sources, total = [], [], 0
    for group, entries in sorted(groups.items(), key=lambda pair: _order(pair[1][0])):
        name = _file_name(group, str(entries[0].get("timestamp", "")))
        text = "\n".join(_entry(item) for item in entries)
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(text, encoding="utf-8")
        total += len(text)
        sources += [str(item.get("source", "")) for item in entries if item.get("source")]
        first, last = str(entries[0].get("timestamp", ""))[:10], str(entries[-1].get("timestamp", ""))[:10]
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
        "each entry starts with `### <source id> · <time> · <speaker>`; cite that source id.\n\n"
        + "\n".join(lines) + "\n", encoding="utf-8")
    return {"index": index, "files": len(groups), "sources": sources, "chars": total}
