"""`co rem list people --table`: the people as a CRM table, read from co rem's index (#2064, #2067).

The columns are the facts you scan for -- company, role, email, phone, last
contact, mails, what is open -- read from `.state/rem.db` rather than parsed
out of 381 pages on every call. Plain text aligned by terminal cells, so a
Chinese name lines up with an English one; `--json` gives the rows.

The UI audit of 2026-10-15 read it at 158 columns whatever the terminal, with
"[OpenOnion](../orgs…" for a company, a Luma relay as Ody's email and
"written" on every row. Cells are now the words a person reads, the widest
text columns give way until the table fits, a Status every row shares is not
a column, and a relay is never anyone's email (`map.RELAY`).
"""

import re
import shutil

from rich.cells import cell_len
from rich.markup import escape

from ..style import count, heading, muted

COLUMNS = (("Name", "name", 24), ("Company", "company", 20), ("Role", "role", 20), ("Email", "email", 30),
           ("Phone", "phone", 16), ("Last contact", "last_contact", 12), ("Mails", "mails", 5),
           ("Open", "open_threads", 4), ("Status", "status", 7))
NUMBERS = ("mails", "open_threads")
SHRINKS = ("name", "company", "role", "email", "phone")   # the text columns that give way to the terminal
NARROWEST = 8
LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
PRIVATE = re.compile(r"\[(?:sensitive|personal)\]", re.IGNORECASE)


def _fit(text: str, width: int) -> str:
    """Cut to `width` terminal cells with an ellipsis, then pad to it."""
    if cell_len(text) > width:
        while cell_len(text) > width - 1:
            text = text[:-1]
        text += "…"
    return text + " " * (width - cell_len(text))


def _email(emails: list) -> str:
    from ...rem.map import RELAY
    return next((address for address in emails if not RELAY.search(address)), "")


def _cells(row: dict) -> dict:
    words = {key: LINK.sub(r"\1", str(row.get(key) or "")) for key in ("name", "company", "role", "phone")}
    words = {key: "(private)" if PRIVATE.search(value) else value for key, value in words.items()}
    return {**row, **words, "email": _email(row.get("emails") or []),
            "status": "written" if row.get("written") else "mapped",
            **{key: str(row.get(key) or 0) for key in NUMBERS}}


def _columns(cells: list[dict]) -> list:
    """The columns worth a place: Status only when the rows differ in it."""
    return [column for column in COLUMNS
            if column[1] != "status" or len({c["status"] for c in cells}) > 1]


def _widths(columns: list, cells: list[dict], room: int) -> list[int]:
    """Each column's width, the widest text column narrowed a cell at a time until the line fits `room`."""
    widths = [max([cell_len(title)] + [min(cap, cell_len(c[key])) for c in cells]) for title, key, cap in columns]
    shrinkable = [i for i, (title, key, _) in enumerate(columns) if key in SHRINKS]
    while sum(widths) + 2 * (len(widths) - 1) > room:
        widest = max(shrinkable, key=lambda i: widths[i])
        if widths[widest] <= max(NARROWEST, cell_len(columns[widest][0])):
            break
        widths[widest] -= 1
    return widths


def draw(rows: list[dict], order: str = "most recent contact first") -> str:
    """Header, one line per person, and how many: markup for rem_look.say."""
    cells = [_cells(row) for row in rows]
    columns = _columns(cells)
    widths = _widths(columns, cells, shutil.get_terminal_size().columns)
    def line(values):
        return "  ".join(_fit(str(value or ""), width) if key not in NUMBERS else str(value).rjust(width)
                         for (_, key, _), value, width in zip(columns, values, widths)).rstrip()
    lines = [heading(line([title for title, _, _ in columns]))]
    lines += [escape(line([c[key] for _, key, _ in columns])) for c in cells]
    lines += ["", f"{count(len(rows))} {'person' if len(rows) == 1 else 'people'}, {escape(order)}."]
    return "\n".join(lines)


def names(notebook, records: list[str]) -> str:
    """`co rem list CATEGORY`: each page's title, its path muted beside it (the audit: bare paths read as files)."""
    titles = [next((line[2:].strip() for line in notebook.read(record).splitlines() if line.startswith("# ")),
                   record) for record in records]
    width = min(40, max((cell_len(title) for title in titles), default=0))
    return "\n".join(escape(_fit(title, width)) + "  " + muted(escape(record))
                     for title, record in zip(titles, records))
