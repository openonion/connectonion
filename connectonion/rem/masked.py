"""Masked pages keep their own number (#3385, art director on #3386).

A knowledge page whose title is marked [personal]/[sensitive] is masked: at the default "cover" level the reader
shows it as 「个人事项」. Several masked pages need to tell apart, so each carries `Masked: N` under its title:
numbered 1, 2, 3 … in the order each page was first masked, stored once in the page, never renumbered, and a
deleted page's number never reused (`.state/mask-numbers.json` keeps the highest number given).

The number is given where pages are written (Notebook.write), only when a masked page is written without one, so
opening or building the reader never writes it. The reader only reads it; a legacy page with none yet gets a
fallback the reader computes without writing.
"""

import re
from pathlib import Path

PRIVATE = re.compile(r"[\[［](?:sensitive|personal)[\]］]", re.I)
LINE = re.compile(r"(?m)^Masked:[ \t]*(\d+)[ \t]*$")
HIGH = "mask-numbers.json"


def masked(content: str) -> bool:
    """A page whose title carries a privacy mark."""
    return bool(PRIVATE.search(content.partition("\n")[0]))


def number(content: str) -> int | None:
    found = LINE.search(content)
    return int(found.group(1)) if found else None


def _highest(root: Path) -> int:
    from .files import read_json, state_path
    folder = root / "knowledge"
    stored = [number(path.read_text(encoding="utf-8", errors="replace")) for path in folder.glob("*.md")] if folder.is_dir() else []
    return max([read_json(state_path(root, HIGH), {}).get("high", 0), *(n for n in stored if n)], default=0)


def numbered(root: Path, record: str, content: str, previous: str | None) -> str:
    """The content to write: a masked knowledge page keeps its number, or gets the next one; others unchanged."""
    if not record.startswith("knowledge/") or not masked(content) or number(content):
        return content
    keep = number(previous or "")
    title, _, rest = content.partition("\n")
    given = keep or _highest(root) + 1
    if not keep:
        from .files import state_path, write_json
        write_json(state_path(root, HIGH), {"high": given})
    return f"{title}\nMasked: {given}\n{rest}"
