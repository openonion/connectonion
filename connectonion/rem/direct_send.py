"""Who may get a reply from REM without the owner's click, set by REM from each person's page (D-101).

A co-founder or partner is `partner`; a close collaborator, or someone the owner writes
to informally and often, is `close`; everyone else, clients and prospects above all,
stays `none`. The rule reads the page REM already wrote and calls no model: the native
round's `co rem next` never does. A sentence the rule cannot place stays `none`.

REM writes `- Direct send: TIER (set by REM, DATE; change it any time)` into Facts. A
Direct send line without that note is the owner's own and is never touched. Every send
still waits ten minutes with Undo (approvals.send_direct).
"""

import json
import re
import sqlite3
from collections import Counter
from contextlib import closing

from .files import Notebook, read_json, state_path

PARTNER = re.compile(r"\bco-?founders?\b|\bbusiness partners?\b|\bfounding partners?\b|合伙人|联合创始人", re.I)
CLOSE = re.compile(r"\b(?:good|close|best|old|very good) friends?\b|\bclose collaborators?\b|\bteammates?\b|"
                   r"朋友|好友", re.I)
# Checked first: a client who is also called a collaborator is still a client.
NOT_CLOSE = re.compile(r"\bclients?\b|\bcustomers?\b|\bprospect(?:ive)?\b|\bvendors?\b|\bsuppliers?\b|"
                       r"\boutreach\b|\brecruit(?:er|ers|ing)\b|\bapplicants?\b|\bcandidates?\b|\bsales leads?\b|"
                       r"客户|供应商", re.I)
INFORMAL = re.compile(r"\binformal(?:ly)?\b|\bcasual(?:ly)?\b|\bfirst names?\b|随意|口语", re.I)
OFTEN = 10  # messages the owner has sent them
LINE = re.compile(r"^- Direct send:[^\n]*\n?", re.M)
MARK = "(set by REM"


def _section(text, title):
    match = re.search(r"^## " + re.escape(title) + r"\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return match.group(1) if match else ""


def _summary(section):
    """The section's first sentence: what the relationship is. Later sentences tell its history,
    where a customer setup or someone else's co-founder is not about this person."""
    text = section.strip().removeprefix("- ")
    return re.split(r"(?<=[.。!?])\s", text, maxsplit=1)[0]


def tier(page: str, sent: int) -> str:
    """partner, close or none, from what the relationship is and how the owner writes to them."""
    known = re.search(r"^- How we know them:(.*)$", _section(page, "Facts"), re.M)
    relationship = _summary(_section(page, "Our relationship")) + " " + (known.group(1) if known else "")
    if NOT_CLOSE.search(relationship):
        return "none"
    if PARTNER.search(relationship):
        return "partner"
    if CLOSE.search(relationship):
        return "close"
    return "close" if INFORMAL.search(_section(page, "How the user writes to them")) and sent >= OFTEN else "none"


def _sent_counts(root, owner_addresses):
    """Messages the owner sent, per recipient address, from the mail archive."""
    database = state_path(root, "rem.db")
    mine = sorted({address.casefold() for address in owner_addresses})
    if not mine or not database.is_file():
        return Counter()
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as db:
        rows = db.execute("select recipients from messages where lower(sender) in (" + ",".join("?" for _ in mine)
                          + ")", mine).fetchall()
    return Counter(address.casefold() for (recipients,) in rows for address in json.loads(recipients or "[]"))


def _addresses(page):
    line = re.search(r"^- Email:(.*)$", _section(page, "Facts"), re.M)
    return re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", line.group(1)) if line else []


def _with_tier(page, value, day):
    """The page with REM's line set to `value`, or removed when REM now says none."""
    line = f"- Direct send: {value} (set by REM, {day}; change it any time)\n" if value != "none" else ""
    if LINE.search(page):
        return LINE.sub(line, page, count=1)
    facts = re.search(r"^## Facts\n(?:- [^\n]*\n)*", page, re.M)
    return page[:facts.end()] + line + page[facts.end():] if facts and line else page


def refresh(root, day: str) -> list[str]:
    """Set REM's tier on every person page whose owner has not set one; the pages changed."""
    book, owner = Notebook(root), read_json(state_path(root, "map.json"), {}).get("owner") or {}
    sent, changed = _sent_counts(root, owner.get("addresses") or []), []
    for record in book.list():
        if not record.startswith("people/") or record == owner.get("record"):
            continue
        page = book.read(record)
        saved = LINE.search(page)
        if saved and MARK not in saved.group(0):
            continue  # the owner's own choice
        value = tier(page, sum(sent[address.casefold()] for address in _addresses(page)))
        if saved and re.match(r"- Direct send: " + value + r"\b", saved.group(0)):
            continue
        updated = _with_tier(page, value, day)
        if updated != page:
            book.write(record, updated)
            changed.append(record)
    return changed
