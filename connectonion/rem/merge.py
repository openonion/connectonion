"""Fold one page into another without losing what either said (#1974).

The map used to make a page per installed skill copy and a page per worktree,
so one skill was three pages and one repository two. When the map now finds
several pages for one thing, it keeps the one with the most written content and
folds the others into it:

- every written line of the other page goes into the same section of the kept
  one, its citations renumbered after the kept page's own;
- the other page moves to `.state/archived/` -- moved, never deleted, the same
  place `map._archive_stale` puts pages an earlier map made;
- its record becomes an alias in `.state/aliases.json`, links to it in other
  pages are rewritten, and `Notebook.path` answers the old name with the kept
  page, so a command or link given the old name still opens something.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .files import Notebook, read_json, state_path, write_json
from .page_review import prose

ALIASES = "aliases.json"
PLACEHOLDER = re.compile(r"^(?:- )?Unknown\b")
CITE = re.compile(r"\[(W?)(\d+)\](?!\()")
# Blocks the map writes and rewrites itself: never merged as content.
# `wiki-` is the same block from before co wiki became co rem (#1932).
GENERATED = re.compile(r"<!-- ((?:rem|wiki)-[a-z-]+) -->\n.*?<!-- /\1 -->\n?", re.S)
# Blocks a later pass manages as a whole: carried over when the kept page has none.
CARRIED = re.compile(r"<!-- rem-skill-runs:start -->.*?<!-- rem-skill-runs:end -->", re.S)
# Lines the map writes on every page it makes; a copy of them says nothing new.
MAP_LINES = re.compile(r"^- (?:File|Discovery|Status|Sessions|First seen|Last seen|Worktrees|Skill metadata): ")


def aliases(root: Path) -> dict:
    """Old record -> the record it was merged into."""
    return read_json(state_path(root, ALIASES), {})


def resolve(root: Path, record: str) -> str:
    """The page an old record now lives in, following merges of merges."""
    table, seen = aliases(root), set()
    while record in table and record not in seen:
        seen.add(record)
        record = table[record]["into"]
    return record


def mapped_only(page: str) -> bool:
    """Nothing but map output: the status line still says nobody investigated or wrote it."""
    status = next((line for line in page.splitlines() if line.startswith("Investigation:")), "")
    return "not investigated yet" in status


def weight(page: str) -> tuple:
    """How much a page holds that a person or a model wrote: an investigated page
    always outweighs a mapped one, then more written lines outweigh fewer."""
    written = sum(1 for heading, body in sections(page)[1] if heading not in ("Paths", "Source", "Sources")
                  for line in body.splitlines() if _meaningful(line))
    return (not mapped_only(page), written)


def sections(page: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    """(text before the first section, [(heading, body)], status lines). Headings
    inside fenced examples are text, and the runner's status line is kept apart."""
    status = re.findall(r"^Investigation:.*$", page, re.M)
    text = re.sub(r"^Investigation:.*\n?", "", page, flags=re.M)
    matches = list(re.finditer(r"^## (.+)$", prose(text), re.M))
    head = text[:matches[0].start()] if matches else text
    parts = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts.append((match[1].strip(), text[match.end():end].strip("\n")))
    return head, parts, status


def render(head: str, parts: list[tuple[str, str]], status: list[str]) -> str:
    blocks = [head.rstrip()] + [f"## {heading}\n{body}".rstrip() for heading, body in parts]
    return "\n\n".join(block for block in blocks if block) + "\n" + ("\n" + "\n".join(status) + "\n" if status else "")


def strip_generated(page: str) -> str:
    """The page without the blocks the map writes itself. Markers are found in
    the visible text only: a pasted SKILL.md may quote them inside its fence."""
    visible = prose(page) + page[len(prose(page)):]
    for match in reversed(list(GENERATED.finditer(visible))):
        page = page[:match.start()] + page[match.end():]
    return page


def _meaningful(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not PLACEHOLDER.match(stripped) and stripped != "- (none yet)" \
        and not MAP_LINES.match(stripped)


def _bare(line: str) -> str:
    return CITE.sub("", line).strip()


def _renumber(text: str, offset: dict) -> str:
    return CITE.sub(lambda m: f"[{m[1]}{int(m[2]) + offset[m[1]]}]", text)


def merge_text(kept: str, other: str) -> str:
    """`kept` with every written line of `other` added to the same section."""
    return _merged(kept, other)[0]


def _merged(kept: str, other: str) -> tuple[str, int]:
    """(merged page, lines added outside Paths and Sources)."""
    kept, other = strip_generated(kept), strip_generated(other)
    carried = CARRIED.search(other)
    other = CARRIED.sub("", other)
    head, parts, status = sections(kept)
    _, theirs, _ = sections(other)
    offset = {"": 0, "W": 0}
    for _, body in parts:
        for match in CITE.finditer(body):
            offset[match[1]] = max(offset[match[1]], int(match[2]))
    index = {heading: i for i, (heading, _) in enumerate(parts)}
    used, added = set(), 0
    # Sources last: a definition is carried only for a citation a carried line uses.
    for heading, body in sorted(theirs, key=lambda part: part[0] == "Sources"):
        lines = [_renumber(line, offset) for line in body.splitlines() if _meaningful(line)]
        if heading == "Paths":
            lines = [line for line in lines if line.startswith("- /")]
        if heading == "Sources":
            defined = [(re.match(r"^\s*(?:- )?\[(W?\d+)\]", line), line) for line in lines]
            lines = [line for match, line in defined if not match or match[1] in used]
        if heading not in index:
            if lines:
                at = index.get("Sources", len(parts))
                parts.insert(at, (heading, "\n".join(lines)))
                index = {h: i for i, (h, _) in enumerate(parts)}
                used |= {m[1] + m[2] for line in lines for m in CITE.finditer(line)}
                added += len(lines) if heading not in ("Paths", "Sources") else 0
            continue
        current = parts[index[heading]][1]
        known = set(current.splitlines()) if heading == "Sources" else {_bare(line) for line in current.splitlines()}
        new = [line for line in lines if (line if heading == "Sources" else _bare(line)) not in known]
        if not new:
            continue
        used |= {m[1] + m[2] for line in new for m in CITE.finditer(line)}
        added += len(new) if heading not in ("Paths", "Sources") else 0
        mine = current.splitlines()
        if not any(_meaningful(line) or MAP_LINES.match(line.strip()) for line in mine):
            body = new  # the kept section said only Unknown
        elif heading == "Paths":  # folders first, then the map's counts
            last = max((i for i, line in enumerate(mine) if line.startswith("- /")), default=-1)
            body = mine[:last + 1] + new + mine[last + 1:]
        else:
            body = mine + new
        parts[index[heading]] = (heading, "\n".join(body))
    page = render(head, parts, status)
    if carried and "<!-- rem-skill-runs:start -->" not in page:
        at = page.find("\nInvestigation:")
        at = at if at >= 0 else len(page)
        page = page[:at].rstrip() + "\n\n" + carried[0] + "\n" + page[at:]
        added += 1
    return page, added


def _note(page: str, old: str) -> str:
    """The kept page's status line records the merge, without claiming an investigation."""
    stamp = f"merged {date.today().isoformat()} ({Path(old).stem})"
    lines = page.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("Investigation:"):
            if " · not investigated yet" in line:
                lines[i] = line.replace(" · not investigated yet", f" · {stamp} · not investigated yet")
            else:
                lines[i] = f"{line} · {stamp}"
            return "\n".join(lines) + "\n"
    return page


def merge_into(notebook: Notebook, kept: str, old: str, reason: str) -> dict:
    """Fold page `old` into page `kept`; returns what happened. Caller holds the lock."""
    root = notebook.root
    theirs, ours = notebook.read(old), notebook.read(kept)
    page, added = _merged(ours, theirs)
    if added:  # the status line says where written lines came from; a copy of map output is not news
        page = _note(page, old)
    if page != ours:
        notebook.write(kept, page)
    if old.startswith("projects/"):
        from .project_material import adopt
        adopt(root, old, kept)
    target = root / ".state" / "archived" / old
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook.path(old).replace(target)
    table = aliases(root)
    for entry in table.values():  # a page merged before into `old` now leads to `kept`
        if entry["into"] == old:
            entry["into"] = kept
    table[old] = {"into": kept, "reason": reason, "date": date.today().isoformat(),
                  "archived": f".state/archived/{old}"}
    write_json(state_path(root, ALIASES), table)
    relinked = _relink(notebook, old, kept)
    return {"from": old, "into": kept, "reason": reason, "lines_merged": added, "relinked": relinked}


def _relink(notebook: Notebook, old: str, new: str) -> list[str]:
    """Links naming the old record, in any page, now name the page it went into."""
    changed = []
    pattern = re.compile(r"(\]\((?:\.\./)*|\]\(\./)" + re.escape(old) + r"\)")
    same_dir = re.compile(r"\]\(\./" + re.escape(Path(old).name) + r"\)")
    for record in notebook.list():
        text = notebook.read(record)
        updated = pattern.sub(lambda m: m[1] + new + ")", text)
        if str(Path(record).parent) == str(Path(old).parent):
            if Path(new).parent == Path(old).parent:
                updated = same_dir.sub(f"](./{Path(new).name})", updated)
        if updated != text:
            notebook.write(record, updated)
            changed.append(record)
    return changed


IDENTITY_LINES = ("- email:", "- handles:", "- also known as:")


def _identity(page: str) -> tuple[str, set[str], set[str]]:
    """The page's title, the addresses on its identity lines, and the other names they give."""
    from .files import EMAIL, split_handles
    title = next((line[2:].strip() for line in page.splitlines() if line.startswith("# ")), "")
    lines = [line for line in page.splitlines()[:40] if line.casefold().startswith(IDENTITY_LINES)]
    addresses = {address.casefold() for line in lines for address in EMAIL.findall(line)}
    names = {re.sub(r"\s*\(.*", "", handle).strip().casefold() for line in lines
             if not line.casefold().startswith("- email:")
             for handle in split_handles(line.split(":", 1)[1]) if "@" not in handle}
    return title, addresses, names


def _distinctive(name: str) -> bool:
    """A full name or one not in Latin script: a first name alone ("David") is many people."""
    return len(name.split()) >= 2 or (len(name) >= 2 and not name.isascii())


def _why(a: tuple, b: tuple) -> str:
    """Why page `a` is probably the person on page `b`, or ''."""
    (title, addresses, names), (other, others, _) = a, b
    shared = sorted(addresses & others)
    if shared:
        return f"both list {', '.join(shared)}"
    if other.casefold() in names and _distinctive(other):
        return f"{title} is also known as {other}"
    local = {re.sub(r"[\d._-]+$", "", address.split("@")[0]): address for address in others}
    own = set(title.casefold().split())   # "David" on David Burt's page is his first name, not a handle
    handle = next((name for name in sorted(names) if len(name) >= 4 and name in local and name not in own), "")
    return f"{title} lists the handle {handle}, as in {local[handle]}" if handle else ""


def likely_pairs(notebook: Notebook) -> list[dict]:
    """People pages that are probably one person, with the evidence; never merged here (#2349).

    A real first run gave Ody two pages on one Gmail, Ziming Gong and 子明 one
    shared address, and Lee Larry the handle of liqingyong0507@gmail.com. Names
    alone are not evidence enough to merge, so the owner confirms each with
    `co rem merge KEPT OTHER`; the page with more written is the one to keep.
    """
    pages = {record: notebook.read(record) for record in notebook.list("people")}
    known = {record: _identity(page) for record, page in pages.items()}
    records = sorted(pages)
    pairs = []
    for index, a in enumerate(records):
        for b in records[index + 1:]:
            why = _why(known[a], known[b]) or _why(known[b], known[a])
            if why:
                kept, other = (a, b) if weight(pages[a]) >= weight(pages[b]) else (b, a)
                pairs.append({"kept": kept, "other": other, "why": why})
    return pairs
