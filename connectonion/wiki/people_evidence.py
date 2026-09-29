"""A person's evidence, gathered by a script before any model reads it (#1943, #1850).

Investigating a person used to mean reading all of their mail through chunk
digests: 8.2M input tokens and 3 h 24 min for one 157-mail correspondent. The
direction since #1850 is an agent that searches prepared evidence. This is the
"prepared" half, and it is plain code: it may use the network, because it runs
before the model and outside the model's sandbox.

Per person, bounded and incremental:

1. their addresses: the map's, and the page's `Email:` line, never the owner's;
2. what is already on disk: init's private mail archive and source inventory;
3. what is missing: one server search per address for the window not yet
   searched, then every body not yet saved (at most MAX_FETCH a run), saved in
   the same archive init uses; attachments of newly fetched mail;
4. local sources: WhatsApp lines from the chats the user chose, and the user's
   own coding messages that name the person.

What it keeps, under `.state/people/<page>/`, is an index of references
(`index.jsonl`) and a small state (`state.json`), owner-only like the rest of
`.state/`. `materialize()` then copies one person's items into a task folder as
plain files the model can search with rg, sed and ls, each opening with its
source id, which is what the page cites.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import Notebook, WikiError, atomic_write, read_json, state_path, write_json
from .mail import _address, _addresses, strip_noise, strip_quoted
from .mail_archive import message_path, person_index_path
from .source import timestamp

# init's archive window, so a person prepared after init needs no server search
# for anything init already saved.
WINDOW_DAYS = 90
# Bodies fetched for one person in one run. The owner's busiest correspondent
# had 157 mails in 90 days (2026-09-27 map); twice that bounds a first fetch.
MAX_FETCH = 300
# Mails whose attachments are saved in one run: one extra provider call each.
MAX_ATTACHMENT_MAILS = 40
# One mail as the model reads it: the reply in full up to REPLY_CHARS, and a
# shortened quoted thread. The thread was already filed under its own date
# when it was mail to the user; a forward's thread is someone else's words.
REPLY_CHARS = 20_000
QUOTED_CHARS = 4_000
ATTACHMENT_CHARS = 20_000
CHAT_CHARS = 2_000
# A mail still arriving at the last search carries a time before it.
OVERLAP = timedelta(hours=1)


def _key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def mail_source(provider: str, message_id: str) -> str:
    """The id a page cites for one mail: the same one init's archive and gather use."""
    return f"{provider}:{_key(message_id)[:12]}"


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _home(root: Path, record: str) -> Path:
    if not record.startswith("people/") or not record.endswith(".md"):
        raise WikiError(f"{record}: people evidence is for people pages")
    return state_path(root, f"people/{Path(record).stem}")


def folder(root: Path, record: str) -> Path:
    """The person's private folder, made owner-only if it is new."""
    _private_dir(state_path(root, "people"))
    return _private_dir(_home(root, record))


def stored(root: Path, record: str) -> list[dict]:
    path = _home(root, record) / "index.jsonl"
    if path.is_symlink():
        raise WikiError("Refusing to read linked operational state")
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def person_state(root: Path, record: str) -> dict:
    return read_json(_home(root, record) / "state.json", {})


def _when(value) -> str:
    """ISO time in UTC, or '' for a date nobody can order."""
    try:
        return timestamp(str(value or "")).isoformat()
    except WikiError:
        return ""


def owner_addresses(root: Path) -> set[str]:
    state = read_json(state_path(root, "map.json"), {})
    own = {a.casefold() for a in (state.get("owner") or {}).get("addresses", [])}
    manifest = read_json(state_path(root, "mail/archive.json"), {})
    return own | {a.casefold() for a in manifest.get("owner_addresses", [])}


def map_row(root: Path, record: str) -> dict:
    state = read_json(state_path(root, "map.json"), {})
    return next((row for row in state.get("people", []) if row.get("record") == record), {})


def addresses(root: Path, record: str) -> list[str]:
    """The person's addresses, from the map and their page; never the owner's."""
    found = [a.casefold() for a in map_row(root, record).get("addresses", []) if "@" in str(a)]
    person = next((p for p in Notebook(root).people() if p["path"] == record), {})
    found += person.get("emails", [])
    return sorted(set(found) - owner_addresses(root))


def _page_handles(root: Path, record: str) -> dict:
    lines = Notebook(root).read(record).splitlines()
    title = next((line[2:].strip() for line in lines if line.startswith("# ")), "")
    phone = next((line.split(":", 1)[1] for line in lines if line.startswith("- Phone:")), "")
    digits = re.sub(r"\D", "", phone)
    return {"title": title, "phone": digits if len(digits) >= 8 else ""}


def _patient(call, *args):
    from .investigate import _patient as patient
    return patient(call, *args)


def _mail_row(provider: str, row: dict) -> dict:
    message_id = str(row.get("id") or "")
    return {"source": mail_source(provider, message_id), "kind": "mail", "provider": provider,
            "id": message_id, "date": _when(row.get("date")), "from": str(row.get("from") or ""),
            "to": [str(v) for v in (row.get("to") or [])] if isinstance(row.get("to"), list) else
                  ([str(row["to"])] if row.get("to") else []),
            "cc": [str(v) for v in (row.get("cc") or [])] if isinstance(row.get("cc"), list) else
                  ([str(row["cc"])] if row.get("cc") else []),
            "subject": str(row.get("subject") or ""), "message": "", "attachments": []}


def _involves(row: dict, wanted: set[str]) -> bool:
    return bool(wanted & ({_address(row.get("from", ""))} | set(_addresses(row.get("to")))
                          | set(_addresses(row.get("cc")))))


def _saved(root: Path, row: dict) -> str:
    """The archive path of this mail's body, relative to the root, or '' if not saved."""
    path = message_path(root, row["provider"], row["id"])
    if not path.is_file():
        return ""
    snapshot = read_json(path, {})
    if snapshot.get("id") != row["id"] or snapshot.get("provider") != row["provider"]:
        return ""
    return str(path.relative_to(root))


def _save_body(root: Path, row: dict, body: str) -> str:
    for name in ("mail", "mail/messages", f"mail/messages/{row['provider']}"):
        _private_dir(state_path(root, name))
    path = message_path(root, row["provider"], row["id"])
    write_json(path, {"provider": row["provider"], "id": row["id"], "date": row["date"], "from": row["from"],
                      "to": row["to"], "cc": row["cc"], "subject": row["subject"], "body": body,
                      "body_format": "provider-rendered text, not original MIME",
                      "fetched_at": datetime.now(timezone.utc).isoformat()})
    return str(path.relative_to(root))


def _archived(root: Path, record: str) -> list[dict]:
    """Mail init already saved for this page, by reference."""
    index = person_index_path(root, record)
    if not index.is_file():
        return []
    rows = []
    for line in index.read_text(encoding="utf-8").splitlines():
        ref = json.loads(line) if line.strip() else None
        if not ref or ref.get("provider") not in ("gmail", "outlook") or not ref.get("id"):
            continue
        snapshot = read_json(message_path(root, ref["provider"], ref["id"]), {})
        rows.append(_mail_row(ref["provider"], {**snapshot, "id": ref["id"], "date": snapshot.get("date") or ref.get("date")}))
    return rows


def _inventory(root: Path, wanted: set[str]) -> list[dict]:
    path = state_path(root, "source-inventory.jsonl")
    if not path.is_file() or not wanted:
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line) if line.strip() else {}
        if row.get("type") == "mail" and row.get("id") and row.get("source") in ("gmail", "outlook") \
                and _involves(row, wanted):
            rows.append(_mail_row(row["source"], row))
    return rows


def _chat_lines(root: Path, subscriptions: dict, handles: dict) -> list[dict]:
    """WhatsApp lines from the chats the user chose, when this person said them or the chat is theirs."""
    from .chat import CHAT_KINDS, NOT_SAID, _records, _text
    title, phone = handles["title"].casefold(), handles["phone"]
    found = []
    for name, sub in (subscriptions or {}).items():
        if sub.get("kind") not in CHAT_KINDS or sub.get("enabled") is False or not sub.get("chats"):
            continue
        home, chats = Path(sub.get("root", "")), set(sub["chats"])
        agent = {row.get("id") for row in _records(home / "sent.jsonl")}
        for role, file in (("other", "received.jsonl"), ("user", "own.jsonl")):
            for row in _records(home / file):
                if row["chat"] not in chats or row["id"] in agent or (row.get("kind") or "text") in NOT_SAID:
                    continue
                sender = str(row.get("sender_name") or "").casefold()
                theirs = bool(phone) and (phone in re.sub(r"\D", "", str(row.get("sender", "")))
                                          or phone in re.sub(r"\D", "", str(row["chat"])))
                if not (theirs or (title and sender == title)
                        or (role == "user" and phone and phone in re.sub(r"\D", "", str(row["chat"])))):
                    continue
                text = _text(row, sub.get("kind"))[:CHAT_CHARS]
                if text.strip():
                    found.append({"source": f"{sub['kind']}:" + _key(f"{row['chat']}/{row['id']}")[:12],
                                  "kind": "chat", "date": _when(row.get("at")), "chat": str(row["chat"]),
                                  "from": "user" if role == "user" else str(row.get("sender_name") or row.get("sender") or ""),
                                  "text": text})
    return found


def _mentions(root: Path, handles: dict, wanted: set[str]) -> list[dict]:
    """The user's own coding messages that name this person by full name or address.

    A first name alone would pull in every other Mia; a full name or an address
    is what a mention of *this* person looks like.
    """
    title = handles["title"]
    needles = [a for a in wanted] + ([title.casefold()] if " " in title.strip() and len(title) >= 5 else [])
    base = state_path(root, "projects")
    found = []
    if not needles or not base.is_dir():
        return found
    for path in sorted(base.glob("*/messages.jsonl")):
        if path.is_symlink():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            message = json.loads(line) if line.strip() else {}
            text = str(message.get("text") or "")
            if any(needle in text.casefold() for needle in needles):
                found.append({"source": str(message.get("source") or ""), "kind": "session",
                              "date": _when(message.get("timestamp")), "from": "user",
                              "project": path.parent.name, "text": text[:CHAT_CHARS]})
    return [row for row in found if row["source"]]


def _download(root: Path, client, row: dict) -> list[str]:
    from .investigate import _download as download
    from .investigate import _saved_paths
    short = _key(row["id"])[:12]
    target = _private_dir(state_path(root, f"attachments/{row['provider']}/{short}"))
    return [str(Path(path).resolve().relative_to(root.resolve()))
            for path in _saved_paths(_patient(download, client, row["id"], str(target)))
            if Path(path).resolve().is_relative_to(root.resolve())]


def prepare(root: Path, record: str, *, clients: dict | None = None, subscriptions: dict | None = None,
            days: int = WINDOW_DAYS, now: datetime | None = None, attachments: bool = True,
            fetch_limit: int = MAX_FETCH, progress=None) -> dict:
    """Bring one person's evidence up to date. Counts only: never a body, subject or name."""
    root = root.resolve()
    now = now or datetime.now(timezone.utc)
    clients = clients or {}
    home = folder(root, record)
    state = person_state(root, record)
    wanted = set(addresses(root, record))
    handles = _page_handles(root, record)
    rows = {row["source"]: row for row in stored(root, record) if row["kind"] == "mail"}
    report = {"record": record, "addresses": len(wanted), "archive": 0, "inventory": 0, "listed": {},
              "fetched": 0, "reused": 0, "failed": 0, "not_fetched": 0, "attachments": 0}

    def add(row: dict, origin: str) -> None:
        if row["id"] and row["source"] not in rows:
            rows[row["source"]] = row
            report[origin] = report.get(origin, 0) + 1

    for row in _archived(root, record):
        add(row, "archive")
    for row in _inventory(root, wanted):
        add(row, "inventory")
    searched = dict(state.get("searched_through") or {})
    for kind, client in clients.items():
        if not wanted or not hasattr(client, "list_with"):
            continue
        start = (timestamp(searched[kind]) - OVERLAP) if searched.get(kind) else now - timedelta(days=days)
        listed = 0
        for address in sorted(wanted):
            for found in _patient(client.list_with, address, start.isoformat(), now.isoformat()) or []:
                listed += 1
                add(_mail_row(kind, found), "server")
        report["listed"][kind] = listed
        searched[kind] = now.isoformat()
        if progress:
            progress(f"searched {kind} for {len(wanted)} address(es)", listed)
    missing = []
    for row in sorted(rows.values(), key=lambda r: (r["date"], r["source"]), reverse=True):
        row["message"] = _saved(root, row)
        if row["message"]:
            report["reused"] += 1
        else:
            missing.append(row)
    attached = 0
    for number, row in enumerate(missing, 1):
        client = clients.get(row["provider"])
        if client is None or number > fetch_limit:
            report["not_fetched"] += 1
            continue
        try:
            body = _patient(client.get_email_body, row["id"])
            if not isinstance(body, str):
                raise WikiError("Mail provider returned no text body")
            row["message"] = _save_body(root, row, body)
            report["fetched"] += 1
            if attachments and attached < MAX_ATTACHMENT_MAILS and hasattr(client, "download_attachments"):
                attached += 1
                row["attachments"] = _download(root, client, row)
                report["attachments"] += len(row["attachments"])
        except Exception:  # noqa: BLE001 -- one unavailable mail must not lose the others; it is counted
            report["failed"] += 1
        if progress and (number % 25 == 0 or number == len(missing)):
            progress("saving mail bodies", f"{number}/{len(missing)}")
    local = _chat_lines(root, subscriptions or {}, handles) + _mentions(root, handles, wanted)
    report["chats"] = sum(1 for row in local if row["kind"] == "chat")
    report["mentions"] = sum(1 for row in local if row["kind"] == "session")
    everything = sorted([*rows.values(), *local], key=lambda r: (r["date"], r["source"]))
    atomic_write(home / "index.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in everything))
    dates = [row["date"] for row in everything if row["date"]]
    state.update({"record": record, "addresses": sorted(wanted), "searched_through": searched,
                  "last_activity": max(dates) if dates else state.get("last_activity", ""),
                  "items": len(everything), "prepared_at": now.isoformat(),
                  "mailboxes": sorted(clients), "fetch_capped": report["not_fetched"]})
    state.setdefault("written_through", "")
    write_json(home / "state.json", state)
    report["items"] = len(everything)
    report["last_activity"] = state["last_activity"]
    return report


def pending(root: Path, record: str) -> tuple[list[dict], str]:
    """Items the page was not written from, and whether that is a first write or an update.

    A mail whose body could not be fetched is listed in the index but has no
    text to read; it is still an item, because its date and subject are facts.
    """
    through = person_state(root, record).get("written_through") or ""
    rows = stored(root, record)
    if through:
        return [row for row in rows if row["date"] > through], "update"
    return rows, "first"


def mark_written(root: Path, record: str, through: str, *, now: datetime | None = None) -> None:
    home = folder(root, record)
    state = person_state(root, record)
    state.update(written_through=through, written_at=(now or datetime.now(timezone.utc)).isoformat())
    write_json(home / "state.json", state)


def _direction(row: dict, wanted: set[str], own: set[str]) -> str:
    sender = _address(row.get("from", ""))
    if sender in wanted:
        return "from this person"
    if sender in own or "@" not in sender:
        return "from the user to this person" if _involves(row, wanted) else "from the user"
    return "from someone else; this person is on To or Cc"


def _mail_text(root: Path, row: dict) -> tuple[str, str]:
    """(the reply, the quoted thread below it), or ('', '') when no body was saved."""
    if not row.get("message"):
        return "", ""
    snapshot = read_json(root / row["message"], {})
    body = str(snapshot.get("body") or "")
    head, marker, rest = body.partition("--- Email Body ---")
    text = rest if marker else body
    reply = strip_quoted(text)
    return strip_noise(reply).strip(), strip_noise(text[len(reply):]).strip()


def _cap(text: str, limit: int, what: str) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[{what} shortened: {len(text) - limit:,} more characters not copied]"


def _safe(value: str) -> str:
    return re.sub(r"[^\w.-]+", "_", value)[:80] or "file"


def _write(path: Path, text: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(path, text)
    return len(text.encode("utf-8"))


def materialize(root: Path, record: str, directory: Path, rows: list[dict]) -> dict:
    """Write the rows as files under `directory/evidence`; return the index and the citable ids.

    Every file opens with `### <source id> · <date> · <sender>` so a search hit
    carries what to cite. Returns {"index": text, "items": [...], "files": n,
    "bytes": n}; the items are what the page validator accepts as sources.
    """
    root = root.resolve()
    evidence = _private_dir(directory / "evidence")
    wanted, own = set(addresses(root, record)), owner_addresses(root)
    lines, items, size, files = [], [], 0, 0
    chats: dict[str, list[str]] = {}
    mentions: list[str] = []
    for row in sorted(rows, key=lambda r: (r["date"], r["source"])):
        day = row["date"][:10] or "undated"
        if row["kind"] == "mail":
            reply, quoted = _mail_text(root, row)
            name = f"mail/{day}_{row['source'].replace(':', '-')}.md"
            header = [f"### {row['source']} · {row['date'] or 'undated'} · {row['from']}",
                      f"From: {row['from']}", f"To: {', '.join(row['to'])}", f"Cc: {', '.join(row['cc'])}",
                      f"Subject: {row['subject']}", f"Direction: {_direction(row, wanted, own)}", ""]
            body = (_cap(reply, REPLY_CHARS, "reply") if row.get("message") else
                    "[body not fetched: listed only; its date, sender and subject are all that is known]")
            if quoted:
                body += "\n\n----- quoted earlier thread below: someone's earlier words, not this mail's -----\n"
                body += _cap(quoted, QUOTED_CHARS, "quoted thread")
            written = _write(evidence / name, "\n".join(header) + "\n" + body + "\n")
            size, files = size + written, files + 1
            recipients = ", ".join(_addresses(row["to"]) + _addresses(row["cc"]))[:200]
            lines.append(f"- {day} · mail · {row['from'][:120]} → {recipients or '?'} · \"{row['subject'][:120]}\""
                         f" · {row['source']} · {name} · {written / 1024:.1f} KB")
            items.append({"source": row["source"], "role": "evidence", "timestamp": row["date"]})
            for saved in row.get("attachments") or []:
                path = root / saved
                if not path.is_file():
                    continue
                from .attachments import extract_text
                source = f"{row['source']}:{_safe(path.name)}"
                name = f"attachments/{row['source'].replace(':', '-')}/{_safe(path.name)}.txt"
                text = _cap(extract_text(path, limit=None), ATTACHMENT_CHARS, "attachment text")
                written = _write(evidence / name, f"### {source} · {row['date']} · attachment of "
                                                  f"{row['source']}: {path.name}\n\n{text}\n")
                size, files = size + written, files + 1
                lines.append(f"- {day} · attachment · {path.name[:120]} · {source} · {name} · {written / 1024:.1f} KB")
                items.append({"source": source, "role": "evidence", "timestamp": row["date"]})
        elif row["kind"] == "chat":
            chats.setdefault(row["chat"], []).append(
                f"### {row['source']} · {row['date']} · {row['from']}\n\n{row['text']}\n")
            items.append({"source": row["source"], "role": "evidence", "timestamp": row["date"]})
        elif row["kind"] == "session":
            mentions.append(f"### {row['source']} · {row['date']} · user (coding session, "
                            f"project {row['project']})\n\n{row['text']}\n")
            items.append({"source": row["source"], "role": "evidence", "timestamp": row["date"]})
    for chat, blocks in chats.items():
        name = f"chats/whatsapp-{_key(chat)[:12]}.md"
        written = _write(evidence / name, "\n".join(blocks))
        size, files = size + written, files + 1
        lines.append(f"- {len(blocks)} WhatsApp line(s) · chat {chat[:60]} · {name} · {written / 1024:.1f} KB")
    if mentions:
        written = _write(evidence / "sessions/mentions.md", "\n".join(mentions))
        size, files = size + written, files + 1
        lines.append(f"- {len(mentions)} of the user's coding messages naming this person · "
                     f"sessions/mentions.md · {written / 1024:.1f} KB")
    index = ("# Evidence index\n\nOne line per item, oldest first: date · kind · from → to · subject · "
             "source id · file · size. Files are under this folder.\n\n" + "\n".join(lines) + "\n")
    _write(evidence / "index.md", index)
    return {"index": index, "items": items, "files": files, "bytes": size}


def correspondents_since(root: Path, clients: dict, *, since: datetime, now: datetime | None = None) -> dict:
    """Which mapped people have mail since the last listing: one metadata listing per mailbox.

    The daily round's later runs follow what is new. Searching every person on
    the server each run would be one query per person; listing the mailbox
    since the last run and matching addresses is one listing, however many
    people there are. Returns {"records": [...], "listed": {kind: n}}; the
    cursor is kept in `.state/people/refresh.json`.
    """
    from .mail import _list_all
    now = now or datetime.now(timezone.utc)
    state = read_json(state_path(root, "map.json"), {})
    own = owner_addresses(root)
    by_address = {address.casefold(): row["record"] for row in state.get("people", [])
                  for address in row.get("addresses", []) if row.get("record") and address.casefold() not in own}
    _private_dir(state_path(root, "people"))
    cursor_path = state_path(root, "people/refresh.json")
    cursor = read_json(cursor_path, {})
    found, listed = set(), {}
    for kind, client in clients.items():
        start = (timestamp(cursor[kind]) - OVERLAP) if cursor.get(kind) else since
        rows = _list_all(client, start, now) if start < now else []
        listed[kind] = len(rows)
        for row in rows:
            for address in {_address(row.get("from", ""))} | set(_addresses(row.get("to"))) | set(_addresses(row.get("cc"))):
                if address in by_address:
                    found.add(by_address[address])
        cursor[kind] = now.isoformat()
    write_json(cursor_path, cursor)
    return {"records": sorted(found), "listed": listed}
