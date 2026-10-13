"""The handoff code, the pasted prompt, and the replies that come back over agent mail.

A handoff code (`coh2.…`) names the sender's agent (address and mailbox), the
handoff id, the bundle's content hash, and a random secret. It is not an invite:
it is never checked by the Host's trust rules as an invite code. It marks this
one handoff accepted (the first valid acceptance wins) and carries questions and
results about it. Once it is accepted, each side makes the other its agent's
contact (transport.meet); the acceptor is also recorded in
~/.co/handoff/peers.json with the handoffs it took.

Replies travel as a small base64 block, like the bundle itself. A `coh2` code says
its sender reads the agent inbox (#2410), so replies go there, addressed to the
agent the code names; a `coh1` code is from a sender that reads only mail.
"""

import base64
import gzip
import hashlib
import html
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from ..address import agent_email
from ..env_file import env_lock
from ..environment import global_config_dir
from . import bundle as bundles
from . import sessions, transport

PREFIX = "coh2."
DROP_PREFIX = "coh3."        # the handoff itself waits on the backend under a drop id (#2459)
MAIL_ONLY_PREFIX = "coh1."   # from senders before the agent inbox: reply by mail
REPLY_BEGIN = "----- BEGIN CO HANDOFF REPLY -----"
REPLY_END = "----- END CO HANDOFF REPLY -----"
KINDS = ("accept", "question", "answer", "done")


# ---- the code ----

def new_secret() -> str:
    return secrets.token_hex(10)


# Binary, then base64: the code is about 110 characters instead of 300, because an agent
# that retypes it (seen in a real run) is the commonest way to get it wrong. The last
# four bytes are a checksum, so a mistyped code is refused instead of decoding to a
# different mailbox, which a real run also did ("openonion.ai" became "openonion.as").
def make_code(fields: dict) -> str:
    mailbox = "" if fields["mailbox"] == agent_email(fields["address"]) else fields["mailbox"]
    drop = _unpadded(fields["drop"]) if fields.get("drop") else b""
    raw = (bytes.fromhex(fields["address"][2:]) + bytes.fromhex(fields["id"][3:]) + bytes.fromhex(fields["hash"])
           + bytes.fromhex(fields["secret"]) + drop + mailbox.encode())
    prefix = DROP_PREFIX if drop else PREFIX
    return prefix + base64.urlsafe_b64encode(raw + hashlib.sha256(raw).digest()[:4]).decode().rstrip("=")


DROP_BYTES = 24   # oo-api's secrets.token_urlsafe(24)


def _unpadded(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def parse_code(code: str) -> dict:
    """{address, mailbox, id, hash, secret}. ValueError for anything else, including a typo."""
    code = "".join(code.split())   # a terminal or mail client may have wrapped it
    if not code.startswith((DROP_PREFIX, PREFIX, MAIL_ONLY_PREFIX)):
        raise ValueError(f"a handoff code starts with {DROP_PREFIX}")
    inbox, dropped, body = not code.startswith(MAIL_ONLY_PREFIX), code.startswith(DROP_PREFIX), code[len(PREFIX):]
    try:
        data = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except ValueError as error:
        raise ValueError(_CHANGED) from error
    raw, check = data[:-4], data[-4:]
    if len(raw) < 54 or hashlib.sha256(raw).digest()[:4] != check:
        raise ValueError(_CHANGED)
    address, rest = "0x" + raw[:32].hex(), raw[54 + DROP_BYTES:] if dropped else raw[54:]
    code = {"address": address, "id": "ho-" + raw[32:36].hex(), "hash": raw[36:44].hex(),
            "secret": raw[44:54].hex(), "mailbox": rest.decode() or agent_email(address), "inbox": inbox}
    if dropped:
        code["drop"] = base64.urlsafe_b64encode(raw[54:54 + DROP_BYTES]).decode().rstrip("=")
    return code


_CHANGED = "this code is cut off or has a typo; copy it again, character for character, from the handoff"


# ---- the prompt a recipient pastes into their coding agent ----

# The oldest published co whose `co handoff accept` does everything this prompt promises. The
# install line names this, never __version__: a sender on a dev build pinned 1.9.2b10.dev1, which
# no index had, so the recipient could not install co at all (2026-10-11). Raise it whenever a
# release changes what the recipient's co does: 1.9.2b10 accept also makes the sender a contact
# (#2399), and a recipient on 1.9.2b8 would pass step 1 and never save them. 1.9.2b11: the prompt's
# step 5 runs `co handoff status --wait`, which 1.9.2b10 does not have. 1.9.2b12: the code is coh2 and
# replies go to the agent inbox; 1.9.2b11 cannot parse coh2 and never reads the inbox. 1.9.2b13: the first
# automatic answer carries the sender's session, and only 1.9.2b13 saves it where the prompt says to look.
MIN_VERSION = "1.9.2b22"   # 1.9.2b22: accept brings the code and the session copy, and the paste says to do the work (#2469, #2452). The install line is install.sh, which pins exactly this version
# From the floor's own tag, so what runs is the script that was released, not whatever main has now.
INSTALLER = f"https://raw.githubusercontent.com/openonion/connectonion/v{MIN_VERSION}/install.sh"


def prompt(code: str, handoff_id: str, sender: str, title: str) -> str:
    """The block a person pastes into Codex or Claude Code: install co if needed, then accept.

    Nothing else (#2459): it is the first message of the recipient's thread, and the install
    steps, rules and brief it used to carry buried the one thing they care about, the session
    handed to them. `accept` fetches the handoff and says what to do next."""
    return (f"{sender} handed you \"{title}\" with ConnectOnion (handoff {handoff_id}).\n\n"
            f"1. If co --version prints nothing or a version older than {MIN_VERSION}, install it (it keeps "
            f"to its own environment):\n"
            f"   macOS or Linux: curl -fsSL {INSTALLER} | CO_VERSION={MIN_VERSION} sh\n"
            f"   Windows: uv tool install \"connectonion=={MIN_VERSION}\", then co init --yes\n"
            f"2. Run this yourself; it fetches the handoff and says what to do next:\n"
            f"   co handoff accept {code}\n"
            f"3. Do what accept says, here in this folder, without waiting for me: the work, questions to {sender} "
            f"with co handoff ask, and co handoff done when it is finished. Then tell me, the person here, in a few "
            f"lines what {sender} was working on and what you did.\n")


# ---- reply messages ----

def send(kind: str, code: dict, to: str, agent: str | None = None, **extra) -> dict:
    """One reply block about handoff code['id']: to `agent`'s inbox when given, else mailed to `to`."""
    block = {"kind": kind, "id": code["id"], "secret": code["secret"],
             "address": transport.my_address(), "at": _now(), **extra}
    encoded = base64.b64encode(json.dumps(block, ensure_ascii=False).encode()).decode()
    body = (f"<p>{html.escape(_human(kind, block))}</p>\n<pre>{REPLY_BEGIN}\n"
            + "\n".join(encoded[i:i + 76] for i in range(0, len(encoded), 76)) + f"\n{REPLY_END}</pre>\n")
    return transport.deliver(to, f"{transport.SUBJECT_PREFIX}{kind} {code['id']}", body,
                             idempotency_key=f"{code['id']}-{kind}-{secrets.token_hex(4)}", agent=agent)


def _human(kind: str, block: dict) -> str:
    if kind == "accept":
        return f"Handoff {block['id']} was accepted by agent {block['address']}."
    if kind == "done":
        return f"Handoff {block['id']} is done: {block.get('text', '')}"
    return f"{kind.capitalize()} about handoff {block['id']}: {block.get('text', '')}"


def received(handoff_id: str, mails: list[dict] = None) -> list[dict]:
    """Reply blocks about this handoff in this agent's mailbox, oldest first."""
    found = []
    for mail in reversed(transport.fetch() if mails is None else mails):   # fetch is newest first
        block = _decode(mail.get("message", ""))
        if block and block.get("id") == handoff_id and block.get("kind") in KINDS:
            found.append(block)
    return sorted(found, key=lambda b: b.get("at", ""))


def _decode(body: str) -> dict | None:
    marker = lambda line: r"\s+".join(map(re.escape, line.split()))
    found = re.search(marker(REPLY_BEGIN) + r"(.*?)" + marker(REPLY_END), html.unescape(body or ""), re.S)
    return json.loads(base64.b64decode(re.sub(r"\s+", "", found.group(1)))) if found else None


def settle(record: dict, mails: list[dict] = None) -> dict:
    """The sender's view of one sent handoff from its replies: who accepted, which questions count.

    Only a block carrying this handoff's secret counts. The first acceptance binds
    the handoff to that agent; later acceptances, and questions from any other
    agent, are ignored and counted. The block's own fields are used, not the
    mail's From: the mail service delivers with a per-message sender address.
    """
    # The acceptance is kept in the record: on a busy mailbox it falls out of the newest 200 mails.
    state = {"accepted": record.get("accepted"), "questions": [], "done": [], "ignored": 0}
    for block in received(record["id"], mails):
        if block["secret"] != record["secret"] or block["kind"] == "answer":
            continue
        if block["kind"] == "accept" and state["accepted"] is None:
            state["accepted"] = {"address": block["address"], "mailbox": block["reply_to"], "at": block["at"]}
            continue
        ours = state["accepted"] and block["address"] == state["accepted"]["address"]
        if ours and block["kind"] == "question":
            state["questions"].append({"text": block["text"], "at": block["at"]})
        elif ours and block["kind"] == "done":
            state["done"].append({key: block[key] for key in ("text", "at", "file", "name") if key in block})
        elif not ours:
            state["ignored"] += 1
    record["accepted"] = state["accepted"]
    return state


# ---- the sender's agent answers by itself ----

WITH_COPY = ("Answered automatically by the sender's agent. A copy of the session this handoff came from, "
             "up to when it was sent, comes with this answer: every message, what the AI said, and every "
             "tool call with its output (credentials removed). co handoff status shows where it is saved; "
             "search it for your question.")
POINTER = ("Answered automatically by the sender's agent: search the session copy you already have "
           "(co handoff status shows where it is saved).")


NO_COPY = ("Answered automatically by the sender's agent, but the session this handoff came from is no longer "
           "on the sender's machine, so no copy comes with it.")


def _who_else(record: dict) -> str:
    """Whether a person was asked too (#2454): a question the sender left open is not in any copy."""
    if record.get("owner"):
        return (" The sender has been told by mail and can answer here. If the copy does not answer your "
                f"question, keep co handoff status {record['id']} --wait running in the background for their answer.")
    return " The sender sees your question when they next run co handoff status, and can answer it."


# The block is base64'd again inside the message and the inbox takes 5 MB, so the packed copy stays
# under 3.5 MB; a longer session keeps its newest part. 124 MB of Claude Code session packed to 5.76 MB.
COPY_BUDGET = 3_500_000
EARLIER_CUT = "[The earlier part of this session was cut so the copy fits the agent inbox.]\n\n"


def answer_automatically(record: dict, state: dict) -> list[str]:
    """Answer each question not answered yet, without asking the sender (Aaron, 2026-10-11).

    The first answer carries a copy of the session the handoff was drafted from, bounded to the
    handed-off messages and the moment it was sent; later answers point to it. The record on disk
    lists the questions answered, under a lock, so co ai's watcher and `co handoff status` running
    at once answer each question once; `record` gets the same fields."""
    who, session = state["accepted"], record.get("session")
    if not who or not session:
        return []
    path = global_config_dir() / "handoff" / "sent" / f"{record['id']}.json"
    with env_lock(path, timeout=300):
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        record["answered"] = answered_keys(on_disk, state["questions"])
        record["copy_sent"] = on_disk.get("copy_sent", False)
        record["copy_with"] = on_disk.get("copy_with")
        news = []
        for question in [q for q in state["questions"] if question_key(q) not in record["answered"]]:
            sent, line = _answer(record, who, session, question)
            news.append(line)
            if not sent:
                break
        on_disk.update(answered=record["answered"], copy_sent=record["copy_sent"], copy_with=record["copy_with"])
        path.write_text(json.dumps(on_disk, indent=2) + "\n", encoding="utf-8")
    return news


def _answer(record: dict, who: dict, session: dict, question: dict) -> tuple[bool, str]:
    """One answer, and the line to tell the sender; marks the question answered in `record` when it went out."""
    copy = not record["copy_sent"] and Path(session["path"]).exists()
    extra = {"context": _copy(record, session)} if copy else {}
    text = (POINTER if record["copy_sent"] else WITH_COPY if copy else NO_COPY) + _who_else(record)
    result = send("answer", {"id": record["id"], "secret": record["secret"]}, who["mailbox"],
                  agent=who["address"] if record.get("inbox") else None, text=text, **extra)
    if not result.get("success"):
        return False, f"[handoff] {record['id']} could not answer \"{question['text']}\": {result.get('error')}"
    record["answered"].append(question_key(question))
    record["copy_sent"] = record["copy_sent"] or copy
    record["copy_with"] = question_key(question) if copy else record["copy_with"]
    if record.get("owner"):
        _tell_owner(record, who, question)
    label = ", with the session copy" if copy else ""
    return True, f"[handoff] {record['id']} answered automatically{label}: {question['text']}"


def _tell_owner(record: dict, who: dict, question: dict) -> None:
    """Mail the person who sent the handoff: the question, and the one line that answers it."""
    asked = html.escape(question["text"])
    body = (f"<p>{html.escape(who['mailbox'])} asked about your handoff <b>{html.escape(record.get('subject', record['id']))}</b>:</p>"
            f"<blockquote>{asked}</blockquote>"
            "<p>Your agent sent them your session to search. If the answer is not in it (a decision you have not "
            "made yet, say), answer from any terminal on this machine, or ask your AI to:</p>"
            f"<pre>co handoff answer {record['id']} \"your answer\"</pre>")
    transport.mail_person(record["owner"], f"[co handoff] Question on {record['id']}: {_short(question['text'])}",
                          body, idempotency_key=f"{record['id']}-told-{hashlib.sha256(question_key(question).encode()).hexdigest()[:12]}")


def tell_owner_of_done(record: dict, state: dict) -> None:
    """Mail the person who sent the handoff each result once (#2470): the text and, inline, a short file.

    Whatever reads replies calls this (co handoff status, co ai's watcher); record["done_told"] keeps it to once."""
    if not record.get("owner"):
        return
    told = record.setdefault("done_told", [])
    for done in [d for d in state["done"] if d["at"] not in told]:
        transport.mail_person(record["owner"], f"[co handoff] Done: {_short(done['text'])}",
                              _done_body(record, state["accepted"], done), idempotency_key=f"{record['id']}-done-{done['at']}")
        told.append(done["at"])


INLINE_FILE = 20_000   # a patch this short reads in the mail; a longer one waits in co handoff status


def _done_body(record: dict, who: dict, done: dict) -> str:
    body = (f"<p>{html.escape(who['mailbox'])} finished your handoff "
            f"<b>{html.escape(record.get('subject', record['id']))}</b>:</p>"
            f"<blockquote>{html.escape(done['text'])}</blockquote>")
    if "file" in done:
        content = unpack_file(done["file"])
        text = content.decode("utf-8", errors="replace")
        body += (f"<p>{html.escape(done['name'])}:</p><pre>{html.escape(text)}</pre>" if len(content) <= INLINE_FILE
                 else f"<p>They sent {html.escape(done['name'])} ({len(content):,} bytes).</p>")
        body += f"<p>co handoff status {record['id']} saves it under ~/.co/handoff/results/{record['id']}/.</p>"
    return body


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 60 else text[:59] + "…"


def question_key(question: dict) -> str:
    return f"{question['at']} {question['text']}"


def answered_keys(record: dict, questions: list[dict]) -> list[str]:
    """The questions answered so far. Records from 1.9.2b13 kept a count of the oldest ones instead."""
    answered = record.get("answered", [])
    return [question_key(q) for q in questions[:answered]] if isinstance(answered, int) else answered


def _copy(record: dict, session: dict, budget: int = None) -> str:
    """The redacted session, packed; its newest part when the whole would not fit the inbox."""
    budget = budget or COPY_BUDGET
    text = bundles.redact(sessions.transcript(session["kind"], session["path"], session.get("since", ""),
                                              record["sent_at"]), bundles.known_secrets())
    packed = _pack(text)
    while len(packed) > budget:
        text = text[-int(len(text) * budget / len(packed) * 0.9):]
        packed = _pack(EARLIER_CUT + text)
    return packed


def _pack(text: str) -> str:
    return base64.b64encode(gzip.compress(text.encode())).decode()


def unpack(context: str) -> str:
    return gzip.decompress(base64.b64decode(context)).decode()


def pack_file(path: Path) -> str:
    """A file sent with `done`, packed like the session copy; it is held to COPY_BUDGET."""
    return base64.b64encode(gzip.compress(path.read_bytes())).decode()


def unpack_file(packed: str) -> bytes:
    return gzip.decompress(base64.b64decode(packed))


def remember_peer(address: str, mailbox: str, handoff_id: str, to: str, inbox: bool = False) -> str:
    """The acceptor becomes this agent's contact, named after whoever `to` was; returns that name.

    peers.json keeps which handoffs they took.
    """
    path = transport.contacts_file().parent / "peers.json"
    peers = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    peer = peers.setdefault(address, {"mailbox": mailbox, "scope": "handoff", "handoffs": []})
    if handoff_id not in peer["handoffs"]:
        peer["handoffs"].append(handoff_id)
    path.write_text(json.dumps(peers, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return transport.meet(to, address, inbox, f"accepted our handoff {handoff_id}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
