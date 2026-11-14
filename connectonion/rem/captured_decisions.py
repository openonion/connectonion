"""The captured choices the nightly abstraction reads, with their original citations."""

import hashlib
import json
import re

from .files import _readable_json, read_json, state_path, write_json
from .page_review import QUOTE, _quote_bindings, _quoted_in

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
            sources = text.partition('\n## Sources\n')[2]
            if category == "sessions":
                body, sources = _session_bindings(body, sources, text)
            yield record, heading, body, sources


def _session_bindings(body, sources, text):
    """Recover legacy session citations only from owner turns retained on the page."""
    from .reader_model import SOURCE, session_detail
    if SOURCE.search(sources):
        return body, sources
    turns = session_detail(text, private=True)["session_messages"]
    numbers, lines = {}, []
    for line in body.splitlines(keepends=True):
        for quote in reversed(list(QUOTE.finditer(line))):
            stamp = re.search(r'\((\d{2}:\d{2})\)', line[quote.end():])
            matches = {turn["source"] for turn in turns if turn["role"] == "user" and turn.get("source")
                       and (not stamp or turn["time"].endswith(stamp[1]))
                       and _quoted_in(quote[1], turn["text"])}
            if len(matches) == 1:
                source = next(iter(matches))
                number = numbers.setdefault(source, len(numbers) + 1)
                line = line[:quote.end()] + f" [{number}]" + line[quote.end():]
        lines.append(line)
    definitions = "\n".join(f"- [{number}] {source}" for source, number in numbers.items())
    return ''.join(lines), sources + '\n' + definitions


def _owner_supported(root, words, binding):
    """Use the unchanged original-author check before spending a model turn."""
    from .decision_authorship import review
    ids = sorted(binding)
    text = f'“{words}” ' + ''.join(f'[{n}]' for n in range(1, len(ids) + 1))
    text += '\n\n## Sources\n' + '\n'.join(f'- [{n}] {source}' for n, source in enumerate(ids, 1))
    return not review(root, text)[1]


def _eligible_lines(body, sources, *, root=None):
    """Keep original character offsets while selecting quotes review can bind."""
    for match in re.finditer(r'.*(?:\n|$)', body):
        if any(binding and (root is None or _owner_supported(root, words, binding))
               for words, binding in _quote_bindings(match[0] + '\n\n## Sources\n' + sources)):
            yield match


def skipped_counts(notebook):
    """Count unsupported captures once across the notebook, outside the round loop."""
    counts = {"no_quote": 0, "no_source": 0, "not_owner": 0}
    for _, _, body, sources in _sections(notebook):
        eligible = {match.start() for match in _eligible_lines(body, sources)}
        supported = {match.start() for match in _eligible_lines(body, sources, root=notebook.root)}
        for match in re.finditer(r'.*(?:\n|$)', body):
            if match[0].strip() and match.start() not in eligible:
                counts["no_source" if QUOTE.search(match[0]) else "no_quote"] += 1
            elif match.start() in eligible and match.start() not in supported:
                counts["not_owner"] += 1
    return counts


def _captured(heading, body, sources):
    """Only definitions bound to quotes in this section belong in its packet."""
    from .reader_model import SOURCE
    full = f"## {heading}\n{body}\n\n## Sources\n{sources}"
    bound = {source for _, binding in _quote_bindings(full) if binding for source in binding}
    lines = [f"- [{match[1]}] {match[2].strip()}" for line in sources.splitlines()
             if (match := SOURCE.match(line)) and match[2].strip() in bound]
    return f"## {heading}\n{body}\n\n## Sources\n" + "\n".join(lines) + "\n"


def _piece(heading, lines, sources, offset, budget):
    lines = list(lines)
    # A packet ends at a whole eligible line; an oversized quote stays pending.
    while lines:
        end = offset + lines[-1].end()
        text = _captured(heading, ''.join(match[0] for match in lines), sources)
        if len(text) <= budget:
            return text, end
        lines.pop()
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
                lines = list(_eligible_lines(body[offset:start], sources, root=notebook.root))
                if lines:
                    yield record, heading, sources, digest, offset, lines
            offset = max(offset, end)


def pending_count(notebook, *, attempted=()):
    return sum(len(lines) for *_, lines in _pending(notebook, attempted))


def material(notebook, config=None, *, attempted=()):
    from .config import read_config
    budget = (config or read_config(notebook.root))["limits"]["input_chars_per_batch"]
    items = []
    lines_left = NIGHT_PAGE_LIMIT
    for record, heading, sources, digest, offset, lines in _pending(notebook, attempted):
        # Unsupported lines consume neither page capacity nor a model turn.
        lines = lines[:lines_left]
        text, end = _piece(heading, lines, sources, offset, budget)
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
            text, end = _piece(heading, lines, sources, offset, len(text) - excess)
        if not text:
            break
        items.append(item)
        lines_left -= sum(match.end() <= end - offset for match in lines)
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
