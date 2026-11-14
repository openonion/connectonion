"""The captured choices the nightly abstraction reads, with their original citations."""

import hashlib
import json
import re

from .files import _readable_json, read_json, state_path, write_json
from .page_review import _quote_bindings

# Twenty lets an older notebook catch up while keeping each slice's review bounded.
NIGHT_PAGE_LIMIT = 20


def _sections(notebook):
    for category, heading in (("sessions", "Decisions"), ("projects", "Key decisions")):
        for record in notebook.list(category):
            text = notebook.read(record)
            section = re.search(rf'(?ms)^## {heading}[ \t]*\n(.*?)(?=^## |^Investigation:|\Z)', text)
            if not section:
                continue
            body = section[1].strip()
            if not body or re.fullmatch(r'[-*\s]*(?:Unknown|None(?: yet)?|No decisions(?: yet)?)[.!]?', body, re.I):
                continue
            yield record, heading, body, text.partition('\n## Sources\n')[2]


def _captured(heading, body, sources):
    """Only definitions bound to quotes in this section belong in its packet."""
    from .reader_model import SOURCE
    full = f"## {heading}\n{body}\n\n## Sources\n{sources}"
    bound = {source for _, binding in _quote_bindings(full) if binding for source in binding}
    lines = [f"- [{match[1]}] {match[2].strip()}" for line in sources.splitlines()
             if (match := SOURCE.match(line)) and match[2].strip() in bound]
    return f"## {heading}\n{body}\n\n## Sources\n" + "\n".join(lines) + "\n"


def _piece(heading, body, sources, offset, budget):
    text = _captured(heading, body[offset:], sources)
    if len(text) <= budget:
        return text, len(body)
    # Normally sections fit whole. Exceptionally large ones progress across slices.
    end = min(len(body), offset + budget)
    while end > offset:
        text = _captured(heading, body[offset:end], sources)
        if len(text) <= budget:
            line = body.rfind('\n', offset, end)
            if line > offset:
                end = line + 1
                text = _captured(heading, body[offset:end], sources)
            return text, end
        end -= max(1, len(text) - budget)
    return "", offset


def slice_key(item):
    """Only offsets and the captured section hash identify an attempted slice."""
    return {key: item[key] for key in ("record", "section_sha256", "section_start", "section_end")}


def _pending(notebook, attempted=()):
    offered = read_json(state_path(notebook.root, "abstract-offered.json"), {})
    sections = sorted(_sections(notebook), key=lambda row: (notebook.path(row[0]).stat().st_mtime, row[0]))
    for record, heading, body, sources in sections:
        captured = _captured(heading, body, sources)
        digest = hashlib.sha256(captured.encode()).hexdigest()
        saved = offered.get(record, {})
        offset = saved.get("offset", 0) if saved.get("sha256") == digest else 0
        completed = saved.get("completed", []) if saved.get("sha256") == digest else []
        skipped = completed + [[item["section_start"], item["section_end"]] for item in attempted
                               if item["record"] == record and item["section_sha256"] == digest]
        for start, end in sorted(skipped) + [[len(body), len(body)]]:
            if start > offset:
                yield record, heading, body[:start], sources, digest, offset
            offset = max(offset, end)


def pending_count(notebook, *, attempted=()):
    return sum(bool(line.strip()) for _, _, body, _, _, offset in _pending(notebook, attempted)
               for line in body[offset:].splitlines())


def material(notebook, config=None, *, attempted=()):
    from .config import read_config
    budget = (config or read_config(notebook.root))["limits"]["input_chars_per_batch"]
    items = []
    lines_left = NIGHT_PAGE_LIMIT
    for record, heading, body, sources, digest, offset in _pending(notebook, attempted):
        # Cap nonempty decision lines at page capacity so every offered choice can become a page.
        ends = [match.end() for match in re.finditer(r'.*(?:\n|$)', body[offset:]) if match[0].strip()]
        bounded = body[:offset + ends[lines_left - 1]] if len(ends) > lines_left else body
        text, end = _piece(heading, bounded, sources, offset, budget)
        while text:
            item = {"role": "captured-decisions", "record": record, "source": f"notebook:{record}",
                    "section_sha256": digest, "section_start": offset, "section_end": end,
                    "sources": sorted({source for _, binding in _quote_bindings(text)
                                       if binding for source in binding}), "text": text}
            excess = len(json.dumps(_readable_json([*items, item]), ensure_ascii=False, indent=2)) + 1 - budget
            if excess <= 0:
                break
            if items:
                return items  # Start the next section whole next slice, in oldest-first order.
            text, end = _piece(heading, bounded, sources, offset, len(text) - excess)
        if not text:
            break
        items.append(item)
        lines_left -= sum(bool(line.strip()) for line in body[offset:end].splitlines())
        if lines_left <= 0:
            break
    return items


def _complete(saved, start, end):
    """Keep successes beyond a failed gap without losing the gap's later retry."""
    completed = []
    for left, right in sorted([*saved.get("completed", []), [start, end]]):
        if left <= saved["offset"]:
            saved["offset"] = max(saved["offset"], right)
        elif completed and left <= completed[-1][1]:
            completed[-1][1] = max(completed[-1][1], right)
        else:
            completed.append([left, right])
    saved["completed"] = completed
    failures = saved.get("failures", {})
    failures.pop(f"{start}:{end}", None)
    if not failures:
        saved.pop("failures", None)


def remember_offered(root, items, *, promoted=True, night=None, reason="No passing pages"):
    """Checkpoint success, or release a slice after three failed nights/manual runs."""
    path = state_path(root, "abstract-offered.json")
    offered = read_json(path, {})
    deferred = []
    for item in items:
        digest = item.get("section_sha256")
        if not digest:
            continue
        saved = offered.get(item["record"], {})
        if saved.get("sha256") != digest:
            saved = {"sha256": digest, "offset": 0}
        start, end = item.get("section_start", 0), item["section_end"]
        if saved["offset"] >= end or any(left <= start and right >= end for left, right in saved.get("completed", [])):
            continue
        if promoted:
            _complete(saved, start, end)
        else:
            failures = saved.setdefault("failures", {})
            nights = failures.setdefault(f"{start}:{end}", [])
            if night not in nights:
                nights.append(night)
            if len(nights) >= 3:
                saved.setdefault("given_up", []).append(dict(start=start, end=end, nights=nights, reason=reason))
                _complete(saved, start, end)
            else:
                deferred.append(slice_key(item))
        offered[item["record"]] = saved
    write_json(path, offered)
    return deferred


def quote_errors(text, items):
    """A lifted choice must keep a captured quote bound to the same original."""
    captured = [pair for item in items if item.get("role") == "captured-decisions"
                for pair in _quote_bindings(item["text"]) if pair[1]]
    if any(binding and (words, binding) in captured for words, binding in _quote_bindings(text)):
        return []
    return ["Decision must quote the owner's words exactly as captured in Decisions or Key decisions; "
            "put the quote in the body immediately followed by its [n] and define the original source ID under ## Sources"]
