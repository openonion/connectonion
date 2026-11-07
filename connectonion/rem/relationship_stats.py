"""Mail relationship metrics from the existing index, without reading bodies (#2843)."""

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from .store_messages import owner_addresses


def contact_messages(messages, people, owner):
    """Events (id, thread, sender, recipients, epoch), once per person exchanging mail."""
    addresses = defaultdict(set)
    for person in people:
        for address in person["emails"]:
            addresses[address.casefold()].add(person["record"])
    found = defaultdict(list)
    for message in messages:
        sender = message[2].casefold()
        recipients = {address.casefold() for address in message[3]}
        counterparts = recipients - owner if sender in owner else {sender} if recipients & owner else set()
        records = {record for address in counterparts for record in addresses[address]}
        for record in records:
            found[record].append(message)
    return found


def thread_stats(messages, owner, now, first_ids):
    starts, replies, previous = [], {True: [], False: []}, {}
    cutoff = (now - timedelta(days=90)).timestamp()
    for message_id, thread, sender, recipients, stamp in messages:
        incoming = sender.casefold() not in owner
        if thread not in previous:
            if stamp >= cutoff and (first_ids is None or message_id in first_ids):
                starts.append(incoming)
        else:
            side, when = previous[thread]
            if side != incoming:
                replies[incoming].append(stamp - when)
        previous[thread] = incoming, stamp
    return {"started_by_them": sum(starts), "threads_90d": len(starts),
            "started_by_them_percent": round(sum(starts) / len(starts) * 100, 1) if starts else None,
            "reply_seconds_them": median(replies[True]) if replies[True] else None,
            "reply_seconds_owner": median(replies[False]) if replies[False] else None}


def metrics(messages, owner, now, first_ids=None):
    """Rolling UTC windows, oldest week first; reply medians over all indexed history."""
    weeks, recent, prior = [0] * 52, 0, 0
    end = now.timestamp()
    for message in messages:
        age = (end - message[4]) / 86400
        if 0 < age <= 364:
            bucket = min(51, int((364 - age) // 7))
            weeks[bucket] += 1
        recent += 0 <= age <= 30
        prior += 30 < age <= 120
    change = round((recent * 3 / prior - 1) * 100, 1) if prior else None
    trend = ("warming" if change > 0 else "cooling" if change < 0 else "steady") if prior else (
        "new" if recent else "no activity")
    last = datetime.fromtimestamp(messages[-1][4], timezone.utc).isoformat(timespec="seconds") if messages else ""
    return {"weekly_messages": weeks, "messages_30d": recent, "messages_prior_90d": prior,
            "change_percent": change, "trend": trend, "last_mail": last,
            "quiet": bool(messages) and end - messages[-1][4] > 90 * 86400,
            **thread_stats(messages, owner, now, first_ids)}


def relationship_stats(root, people, *, today=None):
    """Recount the synced mail in one pass; no cached dates that go stale between syncs."""
    from .store import _rows
    owner = owner_addresses(root)
    if not people or not owner:
        return {}
    if today is None:
        from .service import notebook_today
        today = notebook_today(root).isoformat()
    now = datetime.fromisoformat(today).replace(tzinfo=timezone.utc) + timedelta(days=1)
    # Decode the batch once instead of running the generic row/JSON adapter per mail.
    rows = _rows(root, "select json_group_array(json_array(id, thread, sender, json(recipients), unixepoch(time))) as mail from ("
                 "select id, thread, sender, recipients, time from messages "
                 "where thread like 'mail:%' and time != '' and time < ? order by time, id)", (now.isoformat(),))
    messages = json.loads(rows[0]["mail"]) if rows else []
    first = {}
    for message in messages:
        first.setdefault(message[1], message[0])
    first_ids = set(first.values())
    contacts = contact_messages(messages, people, owner)
    return {person["record"]: metrics(contacts[person["record"]], owner, now, first_ids) for person in people}
