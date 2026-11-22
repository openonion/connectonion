"""WhatsApp as a co rem source: read the files the listener already keeps, one chat at a time.

No second connection. WhatsApp allows one socket per linked device, and
`co whatsapp listen` holds it; a co rem that dialled in as well would drop the
listener. Everything co rem needs is already on disk under the inbox:

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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import RemError
from .source import MAX_MESSAGE_CHARS, TRUNCATION_NOTE, Batch, timestamp

CHAT_KINDS = ("whatsapp", "wechat")
# WeChat is read straight from WeChat for Mac's own databases (read-only), with no intermediate files;
# "*" stands for every one-to-one chat: people, never groups (@chatroom) or official accounts (gh_).
EVERY_PERSON = "*"
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
        raise RemError("Source is disabled or not yet authorized; run start to confirm access")
    kind = subscription.get("kind", "whatsapp")
    chats = set(subscription.get("chats") or [])
    updated = dict(progress)
    if not chats:
        return Batch([], updated)
    wanted = (lambda chat: chat in chats or (EVERY_PERSON in chats and _one_to_one(chat)))
    since = timestamp(subscription["since"])
    pending = defaultdict(list)
    if kind == "wechat":
        streams = _wechat_streams()  # read now, in memory; nothing is written to disk
    else:
        home = Path(subscription["root"])
        agent = {row.get("id") for row in _records(home / "sent.jsonl") if row.get("id")}
        streams = (("other", _records(home / "received.jsonl")),
                   ("user", [row for row in _records(home / "own.jsonl") if row.get("id") not in agent]))
    for role, rows in streams:
        for row in rows:
            chat = row["chat"]
            if not wanted(chat):
                continue
            if (row.get("kind") or "text") in NOT_SAID:
                continue
            try:
                when = timestamp(str(row.get("at") or ""))
            except RemError:
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


def _one_to_one(chat: str) -> bool:
    """A chat with one person: not a group, not an official account, not WeChat's own service chats."""
    return not (chat.endswith("@chatroom") or chat.startswith("gh_") or chat in ("filehelper", "weixin", "newsapp", "fmessage"))


def _wechat_streams():
    """WeChat's messages now, straight from WeChat for Mac's databases: ("other", rows) and ("user", rows).

    Read-only, in memory; nothing is written to ~/.co/inbox. The owner's own messages are the "user" side.
    """
    from ..useful_tools import wechat as engine
    db_storage = engine.db_storage_in_use()
    if db_storage is None:
        raise RemError("WeChat for Mac is not readable: run `co wechat` to grant access and capture keys")
    if not engine.KEY_MAP.is_file():
        raise RemError("No WeChat keys saved: run `co wechat key capture`")
    owner = engine.owner_username(db_storage)
    known = engine.names(engine.open_readonly(engine.decrypt_db(db_storage / "contact" / "contact.db",
                                                                engine.key_for(db_storage / "contact" / "contact.db"))))
    other, mine = [], []
    for row in engine.every_message(db_storage, known):
        (mine if row["sender"] == owner else other).append(row)
    return (("other", other), ("user", mine))


def wechat_people(min_messages: int = 1) -> list[dict]:
    """Candidate people from WeChat for Mac: every friend in the address book, plus anyone with a one-to-one chat.

    Shape matches the map's mail rows ({address, name, mails, sent, received}), with the bare WeChat id as
    the address so investigation's handle match finds the chat (its correspondent is that id). Read-only.
    `friend` marks an address-book friend (worth a page with no messages: the owner added them, #3347) and
    `remark` one the owner named. Counts come from the chats this Mac holds, else 0: WeChat for Mac keeps only
    what was synced to it, so most friends have none here. Groups, official and verified accounts (brands,
    companies, services), service chats and people only met in groups are left out. [] when WeChat isn't readable.
    """
    from ..useful_tools import wechat as engine
    db_storage = engine.db_storage_in_use()
    if db_storage is None or not engine.KEY_MAP.is_file():
        return []
    try:
        contacts = engine.open_readonly(engine.decrypt_db(
            db_storage / "contact" / "contact.db", engine.key_for(db_storage / "contact" / "contact.db")))
        known = engine.names(contacts)
        verified = engine.verified_accounts(contacts)
        book = engine.friends(contacts)
    except Exception:
        return []
    owner = engine.owner_username(db_storage)
    # When the owner last talked with each friend, and how much lately: People's columns read these (#3346).
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    counts = {}
    for row in engine.every_message(db_storage, known):
        chat = row["chat"]
        # A verified account (verify_flag set: a brand, a company or a service) is not a person (#3339).
        if not _one_to_one(chat) or chat == owner or chat in verified:
            continue
        c = counts.setdefault(chat, {"name": row["chat_name"], "mails": 0, "sent": 0, "received": 0,
                                     "last": "", "last_mine": None, "n90": 0})
        c["mails"] += 1
        c["sent" if row["sender"] == owner else "received"] += 1
        at = row.get("at") or ""
        if at >= c["last"]:
            c["last"], c["last_mine"] = at, row["sender"] == owner
        c["n90"] += at >= cutoff
    friend_ids = {f["username"] for f in book}
    remarked = {f["username"] for f in book if f["remark"].strip()}
    people = []
    for chat, c in counts.items():
        name = (c["name"] or "").strip()
        # A real name, not the raw id and not a group/service; the id is the handle, the name titles the page.
        if c["mails"] < min_messages or not name or name == chat:
            continue
        people.append({"address": chat, "name": name, "mails": c["mails"], "sent": c["sent"],
                       "received": c["received"], "kind": "wechat", "friend": chat in friend_ids,
                       "remark": chat in remarked, "last": c["last"], "last_mine": c["last_mine"], "n90": c["n90"]})
    # The rest of the address book: a friend with no chat on this Mac is still someone the owner knows (#3347).
    for f in book:
        chat, name = f["username"], (f["remark"] or f["nick_name"]).strip()
        if chat in counts or not _one_to_one(chat) or chat == owner or chat in verified or not name or name == chat:
            continue
        people.append({"address": chat, "name": name, "mails": 0, "sent": 0, "received": 0, "kind": "wechat",
                       "friend": True, "remark": chat in remarked})
    return people


def seed_chat_people(root, subscriptions: dict) -> list[str]:
    """The WeChat people pages a map of that source creates; the generic onboarding step does the work (#3331).

    Kept for its callers: additive and local, no model and no network. A contact already on a page by handle
    is left alone, a full-name match gains the WeChat id, the rest get mapped pages.
    """
    from . import onboard
    created = []
    for name, sub in (subscriptions or {}).items():
        if sub.get("kind") == "wechat" and sub.get("enabled") and sub.get("consented"):
            people = onboard.plan(root, onboard.rows(root, name, sub, 0), ("people",), write=True)["people"]
            created += [row["record"] for row in people["create"]]
    return created
