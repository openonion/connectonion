"""
Purpose: Convert Jira's Atlassian Document Format (ADF) into readable text for co rem records (F13FCAKE-11).
LLM-Note:
  Dependencies: imports from [datetime, re] | imported by [useful_tools/adapter.py, tests/unit/test_jira_adf.py] | no network calls
  Data flow: issue.fields.description (ADF dict) → adf_to_text() → light Markdown text (headings, lists, code fences, quotes, tables)
  State/Effects: pure functions, no I/O
  Integration: adf_to_text() is the only public function; adapter._jira_record() puts its result in record["text"] and keeps the raw ADF under extensions.description_adf
  Errors: never raises — non-dict input gives "", unknown node types keep their child text, media becomes a metadata placeholder (nothing is downloaded)

ADF reference: https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/
"""

import datetime
import re

_LISTS = ("bulletList", "orderedList")
_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
# Largest timestamp (ms) that is still a real date; anything above is not a date and is dropped.
_MAX_TIMESTAMP_MS = (datetime.datetime(9999, 12, 31, tzinfo=datetime.timezone.utc) - _EPOCH) // datetime.timedelta(milliseconds=1)


# Public entry point: ADF document (or plain string) → readable text; never raises.
def adf_to_text(adf) -> str:
    """Readable text for an ADF document; a plain string is returned trimmed, anything else gives ""."""
    if isinstance(adf, str):
        return adf.strip()
    if not isinstance(adf, dict):
        return ""
    return _tidy(_node(adf, 0))


def _children(node) -> list:
    content = node.get("content") if isinstance(node, dict) else None
    return content if isinstance(content, list) else []


def _attrs(node) -> dict:
    attrs = node.get("attrs") if isinstance(node, dict) else None
    return attrs if isinstance(attrs, dict) else {}


def _inline(node) -> str:
    return "".join(_node(child, 0) for child in _children(node))


def _blocks(node, depth: int, separator: str = "\n\n") -> str:
    parts = [_node(child, depth) for child in _children(node)]
    return separator.join(part for part in parts if part.strip())


# Dispatch one node to its renderer; unknown types fall back to their children's text.
def _node(node, depth: int) -> str:
    if not isinstance(node, dict):
        return ""
    render = _RENDERERS.get(node.get("type"))
    if render is not None:
        return render(node, depth)
    if any(isinstance(child, dict) and child.get("type") == "text" for child in _children(node)):
        return _inline(node)
    return _blocks(node, depth, "\n")


# Text with its marks: code stays in backticks, a link keeps its target in brackets.
def _text(node, depth: int) -> str:
    text = str(node.get("text") or "")
    for mark in node.get("marks") if isinstance(node.get("marks"), list) else []:
        kind = mark.get("type") if isinstance(mark, dict) else None
        href = _attrs(mark).get("href")
        if kind == "code":
            text = f"`{text}`"
        elif kind == "link" and href and href != text:
            text = f"{text} ({href})"
    return text


def _heading(node, depth: int) -> str:
    level = _attrs(node).get("level")
    hashes = "#" * level if isinstance(level, int) and 1 <= level <= 6 else "#"
    return f"{hashes} {_inline(node)}"


# Bullet and numbered lists; nested lists indent two spaces per level.
def _list(node, depth: int) -> str:
    ordered = node.get("type") == "orderedList"
    start = _attrs(node).get("order") if isinstance(_attrs(node).get("order"), int) else 1
    lines = [_list_item(item, depth, f"{start + offset}." if ordered else "-")
             for offset, item in enumerate(_children(node))]
    return "\n".join(line for line in lines if line.strip())


def _list_item(item, depth: int, marker: str) -> str:
    indent = "  " * depth
    lines: list[str] = []
    for child in _children(item):
        if isinstance(child, dict) and child.get("type") in _LISTS:
            lines.append(_node(child, depth + 1))
            continue
        text = _node(child, depth).replace("\n", "\n" + indent + "  ")
        lines.append((f"{indent}{marker} " if not lines else indent + "  ") + text)
    return "\n".join(line for line in lines if line.strip())


def _code_block(node, depth: int) -> str:
    language = _attrs(node).get("language") or ""
    return f"```{language}\n{_inline(node)}\n```"


def _quote(node, depth: int) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in _blocks(node, depth).split("\n"))


# Tables become one line per row, cells separated by " | ".
def _table(node, depth: int) -> str:
    rows = [" | ".join(_blocks(cell, depth, " ").replace("\n", " ").strip() for cell in _children(row))
            for row in _children(node)]
    return "\n".join(row for row in rows if row.strip(" |"))


def _expand(node, depth: int) -> str:
    title = str(_attrs(node).get("title") or "")
    body = _blocks(node, depth)
    return f"{title}\n{body}" if title else body


def _task_item(node, depth: int) -> str:
    box = "[x]" if _attrs(node).get("state") == "DONE" else "[ ]"
    return f"{box} {_inline(node)}"


# Date nodes carry epoch milliseconds; out-of-range or non-numeric values become "" instead of raising.
def _date(node, depth: int) -> str:
    timestamp = str(_attrs(node).get("timestamp") or "")
    if not timestamp.isdigit() or int(timestamp) > _MAX_TIMESTAMP_MS:
        return ""
    return (_EPOCH + datetime.timedelta(milliseconds=int(timestamp))).date().isoformat()


# Media is never downloaded here: it becomes a placeholder naming the file when ADF gives one.
def _media(node, depth: int) -> str:
    alt = _attrs(node).get("alt")
    return f"[attachment: {alt}]" if alt else "[attachment]"


def _attr_text(name: str, wrap: str = "{}"):
    return lambda node, depth: wrap.format(_attrs(node).get(name)) if _attrs(node).get(name) else ""


_RENDERERS = {
    "doc": lambda node, depth: _blocks(node, depth),
    "paragraph": lambda node, depth: _inline(node),
    "text": _text,
    "hardBreak": lambda node, depth: "\n",
    "heading": _heading,
    "bulletList": _list,
    "orderedList": _list,
    "codeBlock": _code_block,
    "blockquote": _quote,
    "rule": lambda node, depth: "---",
    "table": _table,
    "panel": lambda node, depth: _blocks(node, depth),
    "expand": _expand,
    "nestedExpand": _expand,
    "taskList": lambda node, depth: _blocks(node, depth, "\n"),
    "taskItem": _task_item,
    "decisionList": lambda node, depth: _blocks(node, depth, "\n"),
    "decisionItem": lambda node, depth: f"Decision: {_inline(node)}",
    "mention": _attr_text("text"),
    "emoji": lambda node, depth: str(_attrs(node).get("text") or _attrs(node).get("shortName") or ""),
    "inlineCard": _attr_text("url"),
    "blockCard": _attr_text("url"),
    "embedCard": _attr_text("url"),
    "status": _attr_text("text", "[{}]"),
    "date": _date,
    "media": _media,
    "mediaInline": _media,
    "mediaSingle": lambda node, depth: _blocks(node, depth, "\n"),
    "mediaGroup": lambda node, depth: _blocks(node, depth, "\n"),
}


def _tidy(text: str) -> str:
    lines = [line.rstrip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
