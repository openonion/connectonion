"""A date window and a machine-readable listing, shared by the mail CLIs.

`-n <count>` is the only way to say "how much mail" and it is the wrong unit
for every sweep: a census, a backfill, a weekly digest all want "between these
two dates". Asking for a count and discarding the surplus fetched 1851 messages
to read a 150-day window on a real mailbox.

Both providers already answer the right question -- `Outlook.list_between` and
`Gmail.list_between` were written for the Wiki sources -- so this only wires
that up and prints it in a shape a caller can parse.
"""

import json
import re
from datetime import datetime, timedelta, timezone

from rich.console import Console

console = Console()

WINDOW = re.compile(r"(\d+)\s*([dwmy])", re.IGNORECASE)
WINDOW_DAYS = {"d": 1, "w": 7, "m": 30, "y": 365}
# What the providers return and a caller can rely on. Anything else a provider
# happens to include rides along; these are the ones that are always there.
LISTING_FIELDS = ("id", "from", "from_name", "to", "date", "subject", "unread")


def parse_since(value: str) -> datetime:
    """`30d`, `2w`, `6m`, `1y`, or an ISO date. Returns an aware UTC datetime."""
    text = (value or "").strip()
    match = WINDOW.fullmatch(text)
    if match:
        days = int(match.group(1)) * WINDOW_DAYS[match.group(2).lower()]
        if days < 1:
            raise ValueError("A window has to be at least one day")
        return datetime.now(timezone.utc) - timedelta(days=days)
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"Cannot read {value!r} as a date. Use 30d, 2w, 6m, 1y, or 2026-06-01."
        ) from None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def parse_until(value: str | None) -> datetime:
    return parse_since(value) if value else datetime.now(timezone.utc)


def window_listing(client, since: str, until: str | None, last: int) -> list:
    """Every message in the window, oldest first, capped at `last`."""
    start, end = parse_since(since), parse_until(until)
    if start >= end:
        raise ValueError("--since has to be earlier than --until")
    rows = []
    # A week at a time: the providers cap one response, and a busy month would
    # silently come back truncated if it were asked for in a single call.
    # A sliver is not a window: `--since 21d` puts `end` a few hundred
    # microseconds past the third boundary, and asking a provider for that
    # is a round trip that can only come back empty.
    cursor = start
    while (end - cursor).total_seconds() >= 1 and len(rows) < last:
        stop = min(cursor + timedelta(days=7), end)
        rows += client.list_between(cursor.isoformat(), stop.isoformat(),
                                    min(200, last - len(rows))) or []
        cursor = stop
    rows.sort(key=lambda row: str(row.get("date", "")))
    return rows[:last]


def print_json_listing(emails: list) -> None:
    """One array, the provider's own values, nothing reformatted for a screen."""
    console.print_json(json.dumps(
        [{field: email.get(field) for field in LISTING_FIELDS if field in email}
         for email in emails], ensure_ascii=False))
