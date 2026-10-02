"""The raw material in co rem's index (#2067): mail, typed session messages and runs, by id.

Bodies stay where they are -- one JSON per archived mail, one JSONL per
project -- and a row says where: `body_path`, and `body_line` for a JSONL. The
index is for finding and ordering; reading a body is the thread view's job.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .files import read_json, state_path
from .store_build import dumps, insert, map_state, thread_key, utc

PREFIX = re.compile(r"^\s*(?:re|fw|fwd|aw|sv|回复|答复|转发)\s*[:：]\s*", re.I)


def subject_key(subject: str) -> str:
    """A subject without its Re:/Fwd: prefixes, casefolded: what a reply shares with its original."""
    previous, text = None, subject or ""
    while previous != text:
        previous, text = text, PREFIX.sub("", text)
    return " ".join(text.split()).casefold()


def owner_addresses(root: Path) -> set:
    state = map_state(root)
    archive = read_json(state_path(root, "mail/archive.json"), {})
    return {a.casefold() for a in [*(state.get("owner") or {}).get("addresses", []),
                                   *archive.get("owner_addresses", [])]}


def _mail_row(root: Path, row: dict, owner: set) -> dict:
    from .mail import _address, _addresses
    from .mail_archive import message_path
    provider, message_id = row["source"], row["id"]
    sender, to, cc = _address(row.get("from", "")), _addresses(row.get("to")), _addresses(row.get("cc"))
    # Who the conversation is with: From and To, never the owner, never Cc.
    counterparts = sorted(({sender, *to} - owner) - {""})
    path = message_path(root, provider, message_id)
    # The provider's thread when the inventory recorded it; before that, subject and counterparts.
    thread = (f"mail:{provider}:{row['thread']}" if row.get("thread") else
              "mail:" + thread_key(provider, subject_key(row.get("subject", "")), ",".join(counterparts)))
    return {"id": f"{provider}:{message_id}", "source": provider, "thread": thread,
            "sender": sender, "recipients": dumps(to + cc), "time": utc(row.get("date", "")),
            "subject": row.get("subject", ""), "body_line": None,
            "body_path": str(path.relative_to(root / ".state")) if path.is_file() else None}


def build_mail(db, root: Path) -> None:
    inventory = state_path(root, "source-inventory.jsonl")
    lines = inventory.read_text(encoding="utf-8").splitlines() if inventory.is_file() else []
    found = {}
    for line in lines:
        row = json.loads(line) if line.strip() else {}
        if row.get("type") == "mail" and row.get("id") and row.get("source") in ("gmail", "outlook"):
            found[(row["source"], row["id"])] = row
    owner = owner_addresses(root)
    db.execute("delete from messages where thread like 'mail:%'")
    insert(db, "messages", [_mail_row(root, row, owner) for row in found.values()])


def build_sessions(db, root: Path) -> None:
    """What the owner typed into a coding tool, one thread per session (`kind:session`)."""
    owner = (map_state(root).get("owner") or {}).get("record") or "owner"
    rows = []
    for path in sorted(state_path(root, "projects").glob("*/messages.jsonl")):
        record = read_json(path.parent / "state.json", {}).get("record", "")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            message = json.loads(line) if line.strip() else {}
            if not message.get("source"):
                continue
            rows.append({"id": message["source"], "source": message.get("tool", ""),
                         "thread": "session:" + message["source"].rsplit(":", 1)[0], "sender": owner,
                         "recipients": dumps([message.get("tool", "")]), "time": utc(message.get("timestamp", "")),
                         "subject": record, "body_path": str(path.relative_to(root / ".state")), "body_line": number})
    db.execute("delete from messages where thread like 'session:%'")
    insert(db, "messages", rows)


def build_runs(db, root: Path) -> None:
    rows = []
    for path in sorted(state_path(root, "runs").glob("*.json")):
        run = read_json(path, {})
        usage = run.get("usage") if isinstance(run.get("usage"), dict) else {}
        rows.append({"id": run.get("id") or path.stem, "record": run.get("record", ""), "stage": run.get("stage", ""),
                     "outcome": run.get("outcome", ""), "model": run.get("model", ""),
                     "started_at": run.get("started_at", ""), "finished_at": run.get("finished_at", ""),
                     "seconds": run.get("seconds"), "input_tokens": usage.get("input_tokens") or 0,
                     "cached_input_tokens": usage.get("cached_input_tokens") or 0,
                     "output_tokens": usage.get("output_tokens") or 0})
    db.execute("delete from runs")
    insert(db, "runs", rows)


def archived_message(root: Path, row: dict):
    """The saved source record, including its input limits; None if not archived."""
    if not row.get("body_path"):
        return None
    path = state_path(root, row["body_path"])
    if not path.is_file():
        return None
    if row.get("body_line"):
        lines = path.read_text(encoding="utf-8").splitlines()
        number = row["body_line"]
        return json.loads(lines[number - 1]) if number <= len(lines) else None
    return read_json(path, {})


def body(root: Path, row: dict):
    """The text of one message, read from its file; None when it was never archived."""
    saved = archived_message(root, row)
    return saved.get("text" if row.get("body_line") else "body") if saved else None
