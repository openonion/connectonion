"""Mail as a source, worked one correspondent at a time.

A notebook's people pages are written from mail, and a person's page written
from all of their mail at once is a different page from one assembled a week
at a time: the timeline is complete, the way they write is observed across
every mail rather than guessed from one, and nothing is spread over batches
that a later batch has to reconcile. So the unit of work is a correspondent,
not a week. The listing is scanned forward once (metadata only) into a queue
per correspondent; a batch takes whole people in order of their first mail,
oldest person first, and reads bodies only for the mail it takes. A person
with more mail than a batch holds is sliced oldest-first and the maintainer
extends their page on the next batch.

A mailbox has no byte offsets, so scanning progress is a timestamp plus the
ids already seen at that exact second (mail arrives in bursts). The adapter
needs two calls from a client -- an ascending, date-bounded listing and one
body -- and nothing else; `Outlook` and `Gmail` in useful_tools provide them.
The user's own mail speaks as `user` and is filed under the person it went to;
everyone else's speaks as `other`, with the sender kept as `speaker`, so the
maintainer can tell a request received from a commitment made.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from .files import WikiError
from .source import TRUNCATION_NOTE, Batch, timestamp

# Reservation confirmations, CI notifications and newsletters are the bulk of a
# mailbox and almost never say anything the user would want remembered. Off by
# setting `exclude_automated: false` on the subscription. The domain list is
# newsletter platforms measured in a real 60-day mailbox (32 mails from two
# platforms, none of them the user's knowledge).
AUTOMATED_SENDER = re.compile(r"(no-?reply|do-?not-?reply|notification|notifications|newsletter|mailer-daemon|"
                              r"postmaster|noreply|automated|alerts?|digest|updates?|info|marketing|support|team|hello)@"
                              r"|@(?:[a-z0-9-]+\.)*(?:substack\.com|beehiiv\.com)$",
                              re.IGNORECASE)
LISTING_WINDOW = timedelta(days=7)   # one listing call covers this much of the timeline
LISTING_LIMIT = 200                  # per window; a busier week continues on the next pass
MAX_BODY_CHARS = 8_000               # a mail body beyond this is a pasted log or a marketing template
SELF = "me"                          # the correspondent of a mail the user sent only to themselves
# Where the quoted thread below a reply begins. Those mails were already read on
# their own day; carrying them again turned a 17-mail batch into 370k tokens.
# Outlook's HTML-to-text collapses a mail into one line, so none of these may
# rely on line starts or ends; each is the first sign of the quoted thread.
# No word boundaries either: flattened text runs "…Program ManagerFrom: Vern…"
# straight through, so the header words themselves are the only signal.
QUOTED_REPLY = re.compile(
    r"(?:\bOn [^\n]{0,160}? wrote:|-{3,}\s*Original Message\s*-{3,}|_{10,}|"
    r"From: [^\n]{0,240}?Sent: |From: [^\n]{0,240}?Date: [^\n]{0,80}?Subject: |"
    r"在[^\n]{0,80}写道[：:]|(?:^|\n)> )",
    re.MULTILINE)
# Signature furniture: links wrapped in angle brackets (how Outlook renders a
# hyperlink), Outlook booking links, newsletter/unsubscribe links. Tokens, not
# facts; a plain URL in prose stays. Flattened text leaves no space after a
# URL, so each pattern names where the URL ends rather than reading to a space.
SIGNATURE_NOISE = re.compile(
    r"<https?://[^>]{0,400}>"
    r"|https?://outlook\.office\.com/bookwithme/(?:[^\s<>]*?ep=bwmEmailSignature|[^\s<>]*?\?anonymous)"
    r"|https?://[^\s<>]*?(?:typeform\.com/newsletter|unsubscribe|list-manage\.com|mailchimp)[^\s<>]*?(?=\s|<|$)",
    re.IGNORECASE)


def strip_quoted(body: str) -> str:
    """The reply itself, without the thread it quotes."""
    match = QUOTED_REPLY.search(body)
    return body[:match.start()] if match else body


def strip_noise(body: str) -> str:
    return SIGNATURE_NOISE.sub("", body)


def _address(value: str) -> str:
    match = re.search(r"<([^>]+)>", value or "")
    return (match.group(1) if match else (value or "")).strip().lower()


def _addresses(value) -> list[str]:
    """Every address in a To/Cc value: a list of addresses, a list of header strings
    ("A <a@x>, B <b@y>"), or one such string."""
    values = value if isinstance(value, (list, tuple)) else [value]
    parts = [part for item in values for part in re.split(r"[;,]", str(item or ""))]
    return [a for a in (_address(part) for part in parts) if a]


def is_own(sender: str, mine: set) -> bool:
    """The user's own mail. Exchange lists the owner's Sent Items under a legacy DN
    (`/o=first organization/…/cn=recipients/cn=…`) instead of an address -- 64 of the
    96 sent mails in a real 60-day mailbox -- and only the mailbox owner appears that
    way, so a sender that is not an address is the user."""
    return sender in mine or "@" not in sender


def correspondent(row: dict, mine: set) -> str:
    """The person a mail is about: its sender, or for the user's own mail, who it went to."""
    sender = _address(row.get("from", ""))
    if not is_own(sender, mine):
        return sender
    others = [a for a in _addresses(row.get("to")) + _addresses(row.get("cc")) if a not in mine]
    return others[0] if others else SELF


def _fit_text(text: str, room: int) -> str:
    if len(text) <= room:
        return text
    keep = max(room - len(TRUNCATION_NOTE) - 12, 200)
    return text[:keep] + TRUNCATION_NOTE.format(dropped=len(text) - keep)


def collect_mail(subscription: dict, progress: dict, max_items: int, max_chars: int, client, *, now=None) -> Batch:
    if not subscription.get("enabled") or not subscription.get("consented"):
        raise WikiError("Source is disabled or not yet authorized; run start to confirm access")
    mine = {a.lower() for a in client.my_addresses()}
    end = now or datetime.now(timezone.utc)
    updated = _scan(subscription, progress, client, mine, end)
    items, used = [], 0
    for address, rows in _turns(updated["pending"], max_items - len(items)):
        for row in rows:
            body = client.get_email_body(row["id"])
            head, _, rest = body.partition("--- Email Body ---")
            body = head + "--- Email Body ---" + strip_noise(strip_quoted(rest)) if rest else strip_noise(strip_quoted(body))
            text = _fit_text(body[:MAX_BODY_CHARS * 2], MAX_BODY_CHARS)
            # Provider ids run to 150 characters; a Sources line of them is unreadable. The
            # short form names the mail, the reference is what `co outlook read` needs.
            short = hashlib.sha256(row["id"].encode()).hexdigest()[:12]
            item = {"role": "user" if is_own(row["from"], mine) else "other", "speaker": row["from"],
                    "correspondent": address, "text": text, "timestamp": row["when"],
                    "source": f"{subscription['kind']}:{short}", "reference": f"{subscription['kind']}:{row['id']}",
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
            _consume(updated["pending"], address, row["id"])
    return Batch(items, updated)


def _scan(subscription: dict, progress: dict, client, mine: set, end: datetime) -> dict:
    """Advance the listing scan to `end`, queueing every mail worth reading under its
    correspondent. Metadata only; a body is read when its person's turn comes."""
    since = timestamp(subscription["since"])
    scanned = timestamp(progress["scanned_until"]) if progress.get("scanned_until") else since
    seen = set(progress.get("seen", []))
    pending = {address: list(rows) for address, rows in progress.get("pending", {}).items()}
    updated = {"scanned_until": scanned.isoformat(), "seen": sorted(seen), "pending": pending}
    window_start = scanned
    while window_start < end:
        window_end = min(window_start + LISTING_WINDOW, end)
        listing = client.list_between(window_start.isoformat(), window_end.isoformat(), LISTING_LIMIT)
        rows = sorted(({**row, "when": timestamp(row["date"])} for row in listing), key=lambda r: (r["when"], r["id"]))
        for row in rows:
            if row["when"] < scanned or (row["when"] == scanned and row["id"] in seen):
                continue
            sender = _address(row.get("from", ""))
            skip = subscription.get("exclude_automated", True) and not is_own(sender, mine) and AUTOMATED_SENDER.search(sender)
            if not skip:
                pending.setdefault(correspondent(row, mine), []).append(
                    {"id": row["id"], "when": row["when"].isoformat(), "from": sender, "subject": row.get("subject", "")})
            _advance(updated, row["when"], row["id"], scanned, seen)
            scanned, seen = timestamp(updated["scanned_until"]), set(updated["seen"])
        window_start = window_end
    return updated


def _turns(pending: dict, max_items: int):
    """Whole correspondents in order of their first mail; the first one is sliced when
    it alone is more than a batch, so the largest correspondent cannot block the rest."""
    order = sorted(pending, key=lambda address: min(row["when"] for row in pending[address]))
    taken = 0
    for address in order:
        rows = sorted(pending[address], key=lambda row: (row["when"], row["id"]))
        if taken + len(rows) > max_items:
            if taken:
                return
            rows = rows[:max_items]
        taken += len(rows)
        yield address, rows
        if taken >= max_items:
            return


def _consume(pending: dict, address: str, email_id: str) -> None:
    pending[address] = [row for row in pending[address] if row["id"] != email_id]
    if not pending[address]:
        del pending[address]


def _advance(updated: dict, when: datetime, email_id: str, scanned: datetime, seen: set) -> None:
    """Move the scan point; ids at its exact second are remembered, older ones dropped."""
    if when > scanned:
        updated["scanned_until"], updated["seen"] = when.isoformat(), [email_id]
    else:
        updated["seen"] = sorted(seen | {email_id})
