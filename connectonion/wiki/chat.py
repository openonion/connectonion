"""WhatsApp as a Wiki source: read the files the listener already keeps, one chat at a time.

No second connection. WhatsApp allows one socket per linked device, and
`co whatsapp listen` holds it; a Wiki that dialled in as well would drop the
listener. Everything the Wiki needs is already on disk under the inbox:

- received.jsonl -- what everyone else said, groups included;
- own.jsonl      -- what the account owner typed on their own phone;
- sent.jsonl     -- what the agent sent, which also comes back as "own" and is
                    left out, because it is execution, not the user.

Only the chats the user named are read. A linked device sees every group the
number is in -- family, unrelated communities, other clients -- and one
client's group must never feed another client's pages. Progress is per chat,
so naming a chat later still reads its history inside the lookback window.

Like mail, both sides are kept, because the other side is a person; like mail,
a batch takes whole chats, oldest chat first, so a page is written from a
conversation rather than from a week of several interleaved ones.
"""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from .files import WikiError
from .source import MAX_MESSAGE_CHARS, TRUNCATION_NOTE, Batch, timestamp

CHAT_KINDS = ("whatsapp",)
# Records that are not someone saying something: an emoji on a message, a
# group changing its subject. They stay in the inbox; they are not material.
NOT_SAID = {"reaction", "revoke", "protocol", "group", "senderkeydistribution"}


def chat_home(kind: str) -> Path:
    from ..inbox.store import default_home
    return default_home(kind)


def _records(path: Path) -> list[dict]:
    """Every complete record. A last line without its newline is the listener
    mid-write; it is read next time, whole."""
    if not path.is_file():
        return []
    data = path.read_bytes()
    rows = []
    for line in data[:data.rfind(b"\n") + 1].splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue   # a torn record the store isolated behind a newline
        if isinstance(row, dict) and row.get("id") and row.get("chat"):
            rows.append(row)
    return rows


def _text(row: dict, kind: str) -> str:
    text = str(row.get("text") or "")
    media = row.get("media") if isinstance(row.get("media"), dict) else None
    what = row.get("kind") or "text"
    if media and media.get("path"):
        text = (text + "\n" if text else "") + f"[{what} saved at {media['path']}]"
    elif media and media.get("error"):
        text = (text + "\n" if text else "") + f"[{what} could not be fetched: {media['error']}]"
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[:MAX_MESSAGE_CHARS] + TRUNCATION_NOTE.format(dropped=len(text) - MAX_MESSAGE_CHARS)
    return text


def collect_chat(subscription: dict, progress: dict, max_items: int, max_chars: int) -> Batch:
    if not subscription.get("enabled") or not subscription.get("consented"):
        raise WikiError("Source is disabled or not yet authorized; run start to confirm access")
    kind = subscription.get("kind", "whatsapp")
    chats = set(subscription.get("chats") or [])
    updated = dict(progress)
    if not chats:
        return Batch([], updated)
    home = Path(subscription["root"])
    since = timestamp(subscription["since"])
    agent = {row.get("id") for row in _records(home / "sent.jsonl") if row.get("id")}
    pending = defaultdict(list)
    for role, name in (("other", "received.jsonl"), ("user", "own.jsonl")):
        for row in _records(home / name):
            chat = row["chat"]
            if chat not in chats or (role == "user" and row["id"] in agent):
                continue
            if (row.get("kind") or "text") in NOT_SAID:
                continue
            try:
                when = timestamp(str(row.get("at") or ""))
            except WikiError:
                continue
            mark = progress.get(chat) or {}
            cursor = timestamp(mark["cursor"]) if mark.get("cursor") else None
            if when < since or (cursor and (when < cursor or (when == cursor and row["id"] in mark.get("seen", [])))):
                continue
            text = _text(row, kind)
            if not text.strip():
                continue
            pending[chat].append((when, row["id"], role, row, text))

    items, used = [], 0
    order = sorted(pending, key=lambda chat: min(entry[0] for entry in pending[chat]))
    for chat in order:
        rows = sorted(pending[chat], key=lambda entry: (entry[0], entry[1]))
        if items and len(items) + len(rows) > max_items:
            break   # the next chat waits whole for the next batch
        for when, message_id, role, row, text in rows:
            item = {"role": role,
                    "speaker": "user" if role == "user" else (row.get("sender_name") or row.get("sender") or ""),
                    "correspondent": chat, "text": text, "timestamp": when.isoformat(),
                    "source": f"{kind}:" + hashlib.sha256(f"{chat}/{message_id}".encode()).hexdigest()[:12],
                    "reference": f"{kind}:{chat}/{message_id}", "project": "", "subject": chat}
            size = len(json.dumps(item, ensure_ascii=False))
            if len(items) >= max_items or (items and used + size > max_chars):
                return Batch(items, updated)
            items.append(item)
            used += size
            mark = updated.get(chat) or {}
            if mark.get("cursor") and timestamp(mark["cursor"]) == when:
                updated[chat] = {"cursor": mark["cursor"], "seen": sorted(set(mark.get("seen", [])) | {message_id})}
            else:
                updated[chat] = {"cursor": when.isoformat(), "seen": [message_id]}
    return Batch(items, updated)
