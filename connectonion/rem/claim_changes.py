"""Record what a completed REM pass actually changed in cited, keyed facts."""

from __future__ import annotations

import re

from .store_build import _sections

FIELD = re.compile(r"^\s*[-*]\s*([^:\[\]`]{1,40}?)\s*[:：]\s*(.*)$")
CITE = re.compile(r"\[(W?\d{1,3})\]")
SOURCE_LINE = re.compile(r"^\s*[-*]\s*\[(W?\d{1,3})\]\s+[a-z][\w-]*:\S+", re.I | re.M)
UNKNOWN = re.compile(r"^(?:unknown|not found|none)\b", re.I)


def claims(text: str) -> dict[str, dict]:
    """Keyed Facts/Contact only; free prose cannot certify a semantic change."""
    sections = _sections(text)
    supported = set(SOURCE_LINE.findall(text))
    rows: dict[str, dict] = {}
    for name in ("Contact", "Facts"):
        for line in sections.get(name, []):
            match = FIELD.match(line)
            if not match:
                continue
            key = " ".join(match.group(1).casefold().split())
            cited = [number for number in CITE.findall(match.group(2)) if number in supported]
            value = CITE.sub("", match.group(2)).strip().strip("`*")
            if value and not UNKNOWN.match(value):
                rows[key] = {"value": value, "sources": cited}
    return rows


def material_changes(before: dict[str, str], after: dict[str, str], changed: list[str]) -> list[dict]:
    """A claim's old and new value, only when the new value cites a source."""
    found = []
    for path in changed:
        old = claims(before.get(path, ""))
        new = claims(after.get(path, ""))
        for key, current in new.items():
            previous = old.get(key)
            if not current["sources"]:
                continue
            if previous and _same(previous["value"], current["value"]):
                continue
            found.append({"record": path, "field": key, "before": previous["value"] if previous else "",
                          "after": current["value"], "sources": current["sources"],
                          "kind": "revised record" if previous else "newly recorded"})
    return found


def _same(a: str, b: str) -> bool:
    return re.sub(r"[^\w]+", "", a.casefold()) == re.sub(r"[^\w]+", "", b.casefold())
