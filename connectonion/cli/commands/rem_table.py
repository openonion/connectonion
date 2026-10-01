"""`co rem list people --table`: the people as a CRM table, read from co rem's index (#2064, #2067).

The columns are the facts you scan for -- company, role, email, phone, last
contact, mails, what is open -- read from `.state/rem.db` rather than parsed
out of 381 pages on every call. Plain text aligned by terminal cells, so a
Chinese name lines up with an English one; `--json` gives the rows.
"""

from rich.cells import cell_len
from rich.markup import escape

from ..style import count, heading

COLUMNS = (("Name", "name", 24), ("Company", "company", 20), ("Role", "role", 20), ("Email", "email", 30),
           ("Phone", "phone", 16), ("Last contact", "last_contact", 12), ("Mails", "mails", 5),
           ("Open", "open_threads", 4), ("Status", "status", 7))
NUMBERS = ("mails", "open_threads")


def _fit(text: str, width: int) -> str:
    """Cut to `width` terminal cells with an ellipsis, then pad to it."""
    if cell_len(text) > width:
        while cell_len(text) > width - 1:
            text = text[:-1]
        text += "…"
    return text + " " * (width - cell_len(text))


def _cells(row: dict) -> dict:
    emails = row.get("emails") or []
    return {**row, "email": emails[0] if emails else "", "status": "written" if row.get("written") else "mapped",
            **{key: str(row.get(key) or 0) for key in NUMBERS}}


def draw(rows: list[dict], order: str = "most recent contact first") -> str:
    """Header, one line per person, and how many: markup for rem_look.say."""
    cells = [_cells(row) for row in rows]
    widths = [max([cell_len(title)] + [min(cap, cell_len(str(c[key] or ""))) for c in cells])
              for title, key, cap in COLUMNS]
    def line(values):
        return "  ".join(_fit(str(value or ""), width) if key not in NUMBERS else str(value).rjust(width)
                         for (_, key, _), value, width in zip(COLUMNS, values, widths)).rstrip()
    lines = [heading(line([title for title, _, _ in COLUMNS]))]
    lines += [escape(line([c[key] for _, key, _ in COLUMNS])) for c in cells]
    lines += ["", f"{count(len(rows))} {'person' if len(rows) == 1 else 'people'}, {escape(order)}."]
    return "\n".join(lines)
