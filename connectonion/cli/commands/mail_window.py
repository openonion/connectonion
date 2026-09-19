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
errors = Console(stderr=True)

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
    """Messages in the window, oldest first, at most `last` of them.

    Walked **backwards**, from the recent edge towards `since`. The cap has to
    fall on one end or the other, and which end is not a detail: asked for the
    last 30 days of a busy mailbox, walking forwards filled up inside the first
    week and returned mail from a month ago while every message since was never
    fetched. `--since 1d` came back with yesterday and nothing from today.

    Whoever asks for a window wants what happened in it, and the recent end is
    what they mean by that. So the cap now drops the oldest, and
    `window_was_truncated` says out loud that it did — silently returning the
    wrong half is the failure this whole flag exists to avoid.
    """
    start, end = parse_since(since), parse_until(until)
    if start >= end:
        raise ValueError("--since has to be earlier than --until")
    rows = []
    # A week at a time: the providers cap one response, and a busy month would
    # silently come back truncated if it were asked for in a single call.
    # A sliver is not a window: `--since 21d` puts `start` a few hundred
    # microseconds before the third boundary, and asking a provider for that
    # is a round trip that can only come back empty.
    cursor = end
    while (cursor - start).total_seconds() >= 1 and len(rows) < last:
        step = max(cursor - timedelta(days=7), start)
        rows += _between(client, step, cursor, min(200, last - len(rows)))
        cursor = step
    rows.sort(key=lambda row: str(row.get("date", "")))
    # `cursor > start` means we stopped before reaching the far edge, which only
    # happens when the cap ran out: there is more mail in the window than was
    # asked for.
    window_was_truncated(len(rows) >= last and (cursor - start).total_seconds() >= 1, last)
    return rows[:last]


def _between(client, start, end, count: int) -> list:
    """One chunk, keeping the newest when the provider has to choose.

    Gmail's search is newest-first already; Outlook's listing takes an explicit
    flag and older callers of it do not pass one, so this asks only where asking
    is understood rather than making every provider grow a parameter.
    """
    try:
        return client.list_between(start.isoformat(), end.isoformat(), count,
                                   newest_first=True) or []
    except TypeError:
        return client.list_between(start.isoformat(), end.isoformat(), count) or []


def window_was_truncated(truncated: bool, last: int) -> None:
    """Say that a window came back incomplete, on stderr.

    stderr so that `--json` stays exactly one array on stdout and a caller
    parsing it is unaffected — but a person, and anything that reads stderr,
    finds out. A count that silently means "some of them" is the thing this
    module was written to stop.
    """
    if not truncated:
        return
    errors.print(
        f"[yellow]Showing the {last} most recent in this window; there are more. "
        f"Next: raise -n[/yellow]")


def print_json_listing(emails: list) -> None:
    """One array, the provider's own values, nothing reformatted for a screen."""
    console.print_json(json.dumps(
        [{field: email.get(field) for field in LISTING_FIELDS if field in email}
         for email in emails], ensure_ascii=False))
