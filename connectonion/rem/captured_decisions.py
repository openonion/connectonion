"""The captured choices the nightly abstraction reads, with their original citations."""

import hashlib
import json
import re

from .files import _readable_json, read_json, state_path, write_json
from .page_review import _quote_bindings

# Twenty lets an older notebook catch up while keeping one night's review bounded.
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
    # Normally sections fit whole. Exceptionally large ones progress across nights.
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


def material(notebook, config=None):
    from .config import read_config
    budget = (config or read_config(notebook.root))["limits"]["input_chars_per_batch"]
    offered = read_json(state_path(notebook.root, "abstract-offered.json"), {})
    sections = sorted(_sections(notebook), key=lambda row: (notebook.path(row[0]).stat().st_mtime, row[0]))
    items = []
    for record, heading, body, sources in sections:
        captured = _captured(heading, body, sources)
        digest = hashlib.sha256(captured.encode()).hexdigest()
        saved = offered.get(record, {})
        offset = saved.get("offset", 0) if saved.get("sha256") == digest else 0
        if offset >= len(body):
            continue
        text, end = _piece(heading, body, sources, offset, budget)
        while text:
            item = {"role": "captured-decisions", "record": record, "source": f"notebook:{record}",
                    "section_sha256": digest, "section_end": end,
                    "sources": sorted({source for _, binding in _quote_bindings(text)
                                       if binding for source in binding}), "text": text}
            excess = len(json.dumps(_readable_json([*items, item]), ensure_ascii=False, indent=2)) + 1 - budget
            if excess <= 0:
                break
            if items:
                return items  # Start the next section whole tomorrow, in oldest-first order.
            text, end = _piece(heading, body, sources, offset, len(text) - excess)
        if not text:
            break
        items.append(item)
    return items


def remember_offered(root, items):
    """Called only after the native run's terminal outcome has been persisted."""
    path = state_path(root, "abstract-offered.json")
    offered = read_json(path, {})
    for item in items:
        if item.get("section_sha256"):
            offered[item["record"]] = {"sha256": item["section_sha256"], "offset": item["section_end"]}
    write_json(path, offered)


def quote_errors(text, items):
    """A lifted choice must keep a captured quote bound to the same original."""
    captured = [pair for item in items if item.get("role") == "captured-decisions"
                for pair in _quote_bindings(item["text"]) if pair[1]]
    if any(binding and (words, binding) in captured for words, binding in _quote_bindings(text)):
        return []
    return ["Decision must quote the owner's words with the original source citation from captured Decisions or Key decisions"]
