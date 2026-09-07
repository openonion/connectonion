"""Mail as a source: oldest first, one cursor, a body fetched only for the batch it joins.

A mailbox has no byte offsets, so progress is a timestamp cursor plus the ids
already consumed at that exact second (mail arrives in bursts). The adapter
needs two calls from a client -- an ascending, date-bounded listing and one
body -- and nothing else; `Outlook` and `Gmail` in useful_tools provide them.
The user's own mail speaks as `user`; everyone else's as `other`, with the
sender kept as `speaker`, so the maintainer can tell a request received from a
commitment made.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from .files import WikiError
from .source import TRUNCATION_NOTE, Batch, timestamp

# Reservation confirmations, CI notifications and newsletters are the bulk of a
# mailbox and almost never say anything the user would want remembered. Off by
# setting `exclude_automated: false` on the subscription.
AUTOMATED_SENDER = re.compile(r"(no-?reply|do-?not-?reply|notification|notifications|newsletter|mailer-daemon|"
                              r"postmaster|noreply|alerts?|digest|updates?|info|marketing|support|team|hello)@",
                              re.IGNORECASE)
LISTING_WINDOW = timedelta(days=7)   # one listing call covers this much of the timeline
LISTING_LIMIT = 200                  # per window; a busier week continues on the next pass
MAX_BODY_CHARS = 8_000               # a mail body beyond this is a pasted log or a marketing template
# Where the quoted thread below a reply begins. Those mails were already read on
# their own day; carrying them again turned a 17-mail batch into 370k tokens.
QUOTED_REPLY = re.compile(
    r"^(?:On .{0,120}? wrote:\s*$|-{3,}\s*Original Message\s*-{3,}|_{10,}\s*$|From: .{0,200}\nSent: |"
    r"在.{0,80}写道[：:]\s*$|> .*$)",
    re.MULTILINE)


def strip_quoted(body: str) -> str:
    """The reply itself, without the thread it quotes."""
    match = QUOTED_REPLY.search(body)
    return body[:match.start()] if match else body


def _address(value: str) -> str:
    match = re.search(r"<([^>]+)>", value or "")
    return (match.group(1) if match else (value or "")).strip().lower()


def _fit_text(text: str, room: int) -> str:
    if len(text) <= room:
        return text
    keep = max(room - len(TRUNCATION_NOTE) - 12, 200)
    return text[:keep] + TRUNCATION_NOTE.format(dropped=len(text) - keep)


def collect_mail(subscription: dict, progress: dict, max_items: int, max_chars: int, client, *, now=None) -> Batch:
    if not subscription.get("enabled") or not subscription.get("consented"):
        raise WikiError("Source is disabled or not yet authorized; run start to confirm access")
    kind = subscription["kind"]
    since = timestamp(subscription["since"])
    cursor = timestamp(progress["cursor"]) if progress.get("cursor") else since
    seen = set(progress.get("seen", []))
    mine = {a.lower() for a in client.my_addresses()}
    end = now or datetime.now(timezone.utc)
    items, used = [], 0
    updated = {"cursor": cursor.isoformat(), "seen": sorted(seen)}
    window_start = cursor
    while window_start < end and len(items) < max_items:
        window_end = min(window_start + LISTING_WINDOW, end)
        listing = client.list_between(window_start.isoformat(), window_end.isoformat(), LISTING_LIMIT)
        rows = sorted(({**row, "when": timestamp(row["date"])} for row in listing), key=lambda r: (r["when"], r["id"]))
        for row in rows:
            if row["when"] < cursor or (row["when"] == cursor and row["id"] in seen):
                continue
            sender = _address(row.get("from", ""))
            if subscription.get("exclude_automated", True) and sender not in mine and AUTOMATED_SENDER.search(sender):
                _advance(updated, row["when"], row["id"], cursor, seen)
                cursor, seen = timestamp(updated["cursor"]), set(updated["seen"])
                continue
            if len(items) >= max_items:
                return Batch(items, updated)
            body = client.get_email_body(row["id"])
            head, _, rest = body.partition("--- Email Body ---")
            body = head + "--- Email Body ---" + strip_quoted(rest) if rest else strip_quoted(body)
            text = _fit_text(body[:MAX_BODY_CHARS * 2], MAX_BODY_CHARS)
            # Provider ids run to 150 characters; a Sources line of them is unreadable. The
            # short form names the mail, the reference is what `co outlook read` needs.
            short = hashlib.sha256(row["id"].encode()).hexdigest()[:12]
            item = {"role": "user" if sender in mine else "other", "speaker": sender,
                    "text": text, "timestamp": row["when"].isoformat(),
                    "source": f"{kind}:{short}", "reference": f"{kind}:{row['id']}",
                    "project": "", "subject": row.get("subject", "")}
            room = max_chars - used - 300
            if room < 500:
                return Batch(items, updated)
            item["text"] = _fit_text(item["text"], room)
            size = len(json.dumps(item, ensure_ascii=False))
            if used + size > max_chars:
                return Batch(items, updated)
            items.append(item)
            used += size
            _advance(updated, row["when"], row["id"], cursor, seen)
            cursor, seen = timestamp(updated["cursor"]), set(updated["seen"])
        window_start = window_end
    return Batch(items, updated)


def _advance(updated: dict, when: datetime, email_id: str, cursor: datetime, seen: set) -> None:
    """Move the cursor; ids at the cursor's exact second are remembered, older ones dropped."""
    if when > cursor:
        updated["cursor"], updated["seen"] = when.isoformat(), [email_id]
    else:
        updated["seen"] = sorted(seen | {email_id})
