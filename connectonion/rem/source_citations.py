"""Notebook-owned dispatch for opaque saved citation targets, never credentials.

Ownership is persisted before a task/page refers to a snapshot. These entries
are not approval or consumption checkpoints. Removal preserves entries while
the source hooks enforce the current selection whenever a target is read.
"""

import re
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

from .files import RemError, material_lock, read_json, state_path, write_json


_READ_SCOPE = ContextVar("rem_citation_read_scope", default=None)


@contextmanager
def read_scope(root: Path | None):
    """Cache ownership only within one operation, never selection or approval."""
    if root is None or _READ_SCOPE.get() is not None:
        yield
        return
    token = _READ_SCOPE.set({})
    try:
        yield
    finally:
        _READ_SCOPE.reset(token)


def read_operation(function):
    """For Reader/review functions with root first or as a keyword argument."""
    @wraps(function)
    def scoped(*args, **kwargs):
        root = kwargs.get("root")
        if root is None and args and isinstance(args[0], Path):
            root = args[0]
        with read_scope(root):
            return function(*args, **kwargs)
    return scoped


def routes(root: Path) -> dict:
    saved = read_json(state_path(root, "source-citations.json"), {})
    if not isinstance(saved, dict):
        raise RemError("Invalid source citation ownership; preserve it for diagnosis")
    for target, entry in saved.items():
        if (not isinstance(target, str) or not isinstance(entry, dict)
                or set(entry) != {"kind", "record", "subscription"}
                or any(not isinstance(value, str) or not value for value in entry.values())):
            raise RemError("Invalid source citation ownership; preserve it for diagnosis")
    return saved


def lookup(root: Path, target: str) -> dict | None:
    cache = _READ_SCOPE.get()
    if cache is None:
        return routes(root).get(target)
    key = str(root.resolve())
    if key not in cache:
        cache[key] = routes(root)
    return cache[key].get(target)


def remember(root: Path, entries: dict) -> None:
    """Caller already validated each reference through the approved adapter."""
    if not entries:
        return
    with material_lock(root):
        saved = routes(root)
        for target, entry in entries.items():
            if target in saved and saved[target] != entry:
                raise RemError("Conflicting owner for a saved citation; preserve the original mapping")
        updated = {**saved, **entries}
        if updated != saved:
            write_json(state_path(root, "source-citations.json"), updated)
        cache = _READ_SCOPE.get()
        if cache is not None:
            cache[str(root.resolve())] = updated


def canonical_sources(text: str, *, prefixes: set[str]) -> str:
    """Canonical Sources headings/entries, with no changes to target bytes.

    A normalizer does not grant ownership, repair hashes or resolve a target.
    Stop at the next Markdown section and leave fenced examples untouched.
    """
    if not prefixes:
        return text
    prefix = "(?:" + "|".join(re.escape(value) for value in sorted(prefixes)) + ")"
    entry = re.compile(r"^[ \t]*(?:[-*][ \t]*)?\[(W?\d+)\][ \t]+(`?)("
                       + prefix + r":[^\s`]+)\2([^\n]*)$")
    lines, result, inside, fence = text.split("\n"), [], False, ""
    for index, line in enumerate(lines):
        marker = re.match(r"^[ \t]*(`{3,}|~{3,})", line)
        if marker:
            if not fence:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = ""
            result.append(line)
            continue
        if fence:
            result.append(line)
            continue
        inline = re.match(r"^Sources?:[ \t]*(\[W?\d+\].*)$", line)
        match = entry.fullmatch(inline[1]) if inline else None
        if match:
            result.extend(["## Sources", f"- [{match[1]}] {match[3]}{match[4]}"])
            inside = True
            continue
        if re.fullmatch(r"(?:##[ \t]+)?Sources?:?[ \t]*", line):
            following = next((row for row in lines[index + 1:] if row.strip()), "")
            if line == "## Sources" or entry.fullmatch(following):
                result.append("## Sources")
                inside = True
                continue
        if re.match(r"^(?:#{1,6} |Investigation:)", line):
            inside = False
        match = entry.fullmatch(line) if inside else None
        result.append(f"- [{match[1]}] {match[3]}{match[4]}" if match else line)
    return "\n".join(result)
