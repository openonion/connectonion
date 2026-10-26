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

A `coh4` code also carries the key the handoff was sealed with (sealing.py), and says both
sides open boxes: every reply about it is boxed to the other agent's key.
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
from . import private, sealing, sessions, transport

PREFIX = "coh2."
SEALED_PREFIX = "coh4."      # the drop is sealed with the key the code carries, and replies are boxed
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
    key = sealing.key_from(fields["key"]) if fields.get("key") else b""
    raw = (bytes.fromhex(fields["address"][2:]) + bytes.fromhex(fields["id"][3:]) + bytes.fromhex(fields["hash"])
           + bytes.fromhex(fields["secret"]) + drop + key + mailbox.encode())
    prefix = SEALED_PREFIX if key else DROP_PREFIX if drop else PREFIX
    return prefix + base64.urlsafe_b64encode(raw + hashlib.sha256(raw).digest()[:4]).decode().rstrip("=")


DROP_BYTES = 24   # oo-api's secrets.token_urlsafe(24)


def _unpadded(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def parse_code(code: str) -> dict:
    """{address, mailbox, id, hash, secret}, with drop and key when it has them. ValueError for anything
    else, including a typo."""
    code = "".join(code.split())   # a terminal or mail client may have wrapped it
    if not code.startswith((SEALED_PREFIX, DROP_PREFIX, PREFIX, MAIL_ONLY_PREFIX)):
        raise ValueError(f"a handoff code starts with {SEALED_PREFIX}")
    sealed = code.startswith(SEALED_PREFIX)
    inbox, dropped, body = not code.startswith(MAIL_ONLY_PREFIX), sealed or code.startswith(DROP_PREFIX), code[len(PREFIX):]
    try:
        data = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except ValueError as error:
        raise ValueError(_CHANGED) from error
    raw, check = data[:-4], data[-4:]
    if len(raw) < 54 or hashlib.sha256(raw).digest()[:4] != check:
        raise ValueError(_CHANGED)
    end = 54 + (DROP_BYTES if dropped else 0) + (sealing.KEY_BYTES if sealed else 0)
    address, rest = "0x" + raw[:32].hex(), raw[end:]
    code = {"address": address, "id": "ho-" + raw[32:36].hex(), "hash": raw[36:44].hex(),
            "secret": raw[44:54].hex(), "mailbox": rest.decode() or agent_email(address), "inbox": inbox}
    if dropped:
        code["drop"] = base64.urlsafe_b64encode(raw[54:54 + DROP_BYTES]).decode().rstrip("=")
    if sealed:   # as text, like the rest: accept saves the code as JSON
        code["key"] = sealing.key_text(raw[54 + DROP_BYTES:end])
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
# 1.9.2b27: the drop is read with the code's secret and claimed by its first reader (oo-api#267).
# 1.9.2: the recipient's defaults are the permission audit's (the work turn stays in its folder, a
# sender's folder name cannot leave it); a 1.9.2 sender pinning b27 installed none of that (Parrot,
# 2026-10-14). A test now holds this at each release's own version, so it cannot be forgotten again.
# 1.9.3b2: accept writes the sender's conversation as a thread of its own (#2513).
# 1.9.3b3: Codex lists that thread in /resume, and done repeats the line that names it.
# 1.9.3b4: the pasted line, the prompt and the mail say what arrives is the context of a session, not a task (#2523).
# 1.9.3b5: no handoff change; the floor is still the release that sent it.
# 1.9.3rc1: no handoff change; the floor is still the release that sent it.
# 1.9.3rc2: no handoff change; the floor is still the release that sent it.
# 1.9.3rc3: no handoff change; the floor is still the release that sent it.
# 1.9.3rc4: no handoff change; the floor is still the release that sent it.
# 1.9.3rc5: handoffs are sealed (coh4, #k= links) and replies boxed end to end; older co cannot read them.
# 1.9.3rc6: no handoff change for the recipient; the floor is still the release that sent it.
# 1.9.3rc9: the prompt and accept stop in a conversation that was about other work (#2569).
# 1.9.3rc10: no handoff change; the floor is still the release that sent it.
# 1.9.3rc11: no handoff change; the floor is still the release that sent it.
# 1.9.3rc12: no handoff change; the floor is still the release that sent it.
# 1.9.3rc13: no handoff change; the floor is still the release that sent it.
# 1.9.3rc14: no handoff change; the floor is still the release that sent it.
# 1.9.3rc15: no handoff change; the floor is still the release that sent it.
# 1.9.3rc16: Host watches only its own handoff root; the recipient installs this release too.
# 1.9.3rc17: no handoff transport change; the recipient installs this release too.
# 1.9.3rc22: no handoff transport change; the recipient installs this release too.
# 1.9.3rc23: no handoff transport change; the recipient installs this release too.
# 1.9.3rc24: no handoff transport change; the recipient installs this release too.
# 1.9.3rc25: no handoff transport change; the recipient installs this release too.
MIN_VERSION = "1.9.3rc25"
# From the floor's own tag, so what runs is the script that was released, not whatever main has now.
INSTALLER = f"https://raw.githubusercontent.com/openonion/connectonion/v{MIN_VERSION}/install.sh"


def older_than(version: str) -> str:
    """An agent reading "older than 1.9.2" may take 1.9.2b27 for 1.9.2 and keep it."""
    return f"older than {version}" + ("" if re.search(r"[a-z]", version) else
                                      f" (its previews, such as {version}b27, are older)")


def prompt(code: str, handoff_id: str, sender: str, title: str) -> str:
    """The block a person pastes into Codex or Claude Code: install co if needed, accept, do it.

    One paragraph with no line breaks: a mail cannot run a copy button (Aaron clicked "Copy from
    here" and nothing happened, 2026-10-13), and a triple-click selects a whole paragraph in any
    mail client. Nothing else (#2459): it is the first message of the recipient's thread, and
    `accept` fetches the handoff and says what to do next. It names the code, so it goes only
    inside the sealed page; the page's public copy is outer_prompt."""
    return (f"{sender} handed you the context of \"{title}\" (handoff {handoff_id}). {_install()} Then run co handoff accept {code} "
            f"yourself; it fetches the handoff and says what to do. {_then(sender)}")


def outer_prompt(handoff_id: str, sender: str, drop_id: str) -> str:
    """The prompt as the backend holds it, which the agent reads at the link its person pasted: no title and
    no code. The handoff is sealed, and its key is the link's #k= part, which reached the agent in the line
    it was given but never the page it fetched."""
    return (f"{sender} handed you the context of a session (handoff {handoff_id}). It is encrypted, and its key is the "
            f"#k= part of the link you were given. {_install()} Then run co handoff accept with that whole link, "
            f"#k= part included, in quotes: co handoff accept \"{transport.VIEWER}{drop_id}/codex#k=<the key from your link>\". "
            f"Run it yourself; it decrypts the handoff here and says what to do. {_then(sender)}")


def _install() -> str:
    return (f"If co --version prints nothing or a version {older_than(MIN_VERSION)}, install co first, which keeps to its "
            f"own environment (right after a release it can wait a few minutes for PyPI, so let it finish): on macOS or "
            f"Linux run curl -fsSL {INSTALLER} | CO_VERSION={MIN_VERSION} sh, and on Windows run "
            f"uv tool install \"connectonion=={MIN_VERSION}\" then co init --yes.")


def _then(sender: str) -> str:
    """Pasted into a conversation that was about something else, the work used to land there (a pricing
    handoff pasted into a marketing session, 2026-10-19): a handoff gets a conversation of its own."""
    return (f"This needs a conversation of its own: if this conversation had other work in it before my message, do not "
            f"start here; tell me to paste the line into a new Codex or Claude Code conversation, in the project folder "
            f"if there is one, and stop. Otherwise do that here, in this folder, without waiting for me: the work, "
            f"questions to {sender} with co handoff ask, and co handoff done when it is finished. Then tell me in a few "
            f"lines what {sender} was working on and what you did.\n")


PASTE = {   # one line a person pastes; the page it names holds the prompt above (Aaron, 2026-10-13)
    "en": "{sender} handed you the context of \"{title}\" with ConnectOnion. Read {url} and do what it says, here in this folder, "
          "without waiting for me. If you cannot open it, ask me to allow network access.",
    "zh": "{sender} 用 ConnectOnion 把「{title}」的上下文交给了你。读 {url} 并照着做，就在这个文件夹里，不用等我。"
          "如果打不开，请让我允许联网。",
}


def paste(sender: str, title: str, url: str, lang: str = "en") -> str:
    """The line to paste into a new Codex or Claude Code conversation (#2478): one action, any screen.

    Tested on melbourne-2 (Codex 0.156.1, empty HOME): with network it read the page, installed,
    accepted and finished with no person steps; without, it asked once for network access."""
    return PASTE[lang].format(sender=sender, title=bundles._one_line(title, 80), url=url) + "\n"


# ---- reply messages ----

def send(kind: str, code: dict, to: str, agent: str | None = None, **extra) -> dict:
    """One reply block about handoff code['id']: to `agent`'s inbox when given, else mailed to `to`.
    A sealed handoff's (its code has a key) is boxed to that agent: both sides of one open boxes."""
    block = {"kind": kind, "id": code["id"], "secret": code["secret"],
             "address": transport.my_address(), "at": _now(), **extra}
    encoded = base64.b64encode(json.dumps(block, ensure_ascii=False).encode()).decode()
    body = (f"<p>{html.escape(_human(kind, block))}</p>\n<pre>{REPLY_BEGIN}\n"
            + "\n".join(encoded[i:i + 76] for i in range(0, len(encoded), 76)) + f"\n{REPLY_END}</pre>\n")
    return transport.deliver(to, f"{transport.SUBJECT_PREFIX}{kind} {code['id']}", body,
                             idempotency_key=f"{code['id']}-{kind}-{secrets.token_hex(4)}", agent=agent,
                             sealed=bool(code.get("key")))


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
        if block and block.get("id") == handoff_id and block.get("kind") in KINDS and _from_who_it_says(block, mail):
            found.append(block)
    return sorted(found, key=lambda b: b.get("at", ""))


def _from_who_it_says(block: dict, mail: dict) -> bool:
    """An agent-inbox message counts only when the backend's authenticated poster is the address the block
    claims: the secret is in the public page's prompt, so the block's own `address` proves nothing."""
    return "sender" not in mail or str(block.get("address", "")).lower() == str(mail["sender"]).lower()


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
    state = {"accepted": record.get("accepted"), "questions": [], "done": [], "ignored": 0, "others": {}}
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
            state["others"][block["address"]] = block.get("reply_to") or ""   # another holder of the code
    record["accepted"] = state["accepted"]
    return state


# ---- the sender's agent answers by itself ----

WITH_COPY = ("Answered automatically by the sender's agent. A copy of the session this handoff came from, "
             "up to when it was sent, comes with this answer: every message and what the AI said, without "
             "tool calls or their output (credentials and other people's contact details removed). co handoff status shows where it is saved; "
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
        record["waiting"] = on_disk.get("waiting", [])
        news = []
        for question in [q for q in state["questions"] if question_key(q) not in record["answered"]]:
            sent, line = _answer(record, who, session, question, state["questions"])
            news.append(line)
            if not sent:
                break
        on_disk.update(answered=record["answered"], copy_sent=record["copy_sent"], copy_with=record["copy_with"],
                       waiting=record["waiting"])
        path.write_text(json.dumps(on_disk, indent=2) + "\n", encoding="utf-8")
    return news


# A question that says the copy does not answer it, or asks again, gets no second pointer to the copy
# (b24 demo: "I read the entire session.md… it contains no max-length discussion" got the pointer back).
COPY_WORDS = re.compile(r"session\.md|session copy|the copy|transcript|副本|会话记录|聊天记录", re.I)
NOT_THERE = re.compile(r"\b(?:no|not|nothing|none|without|doesn't|does not|isn't|missing)\b|没有|不包含|找不到|没提到", re.I)


def _past_the_copy(record: dict, question: dict, questions: list[dict]) -> bool:
    asked_before = any(q["text"].strip() == question["text"].strip() and question_key(q) in record["answered"]
                       for q in questions if q is not question)
    text = question["text"]
    return record["copy_sent"] and (asked_before or bool(COPY_WORDS.search(text) and NOT_THERE.search(text)))


def _answer(record: dict, who: dict, session: dict, question: dict, questions: list[dict] = ()) -> tuple[bool, str]:
    """One answer, and the line to tell the sender; marks the question answered in `record` when it went out."""
    if _past_the_copy(record, question, questions):
        record["answered"].append(question_key(question))
        record["waiting"].append(question_key(question))
        if record.get("owner"):
            _tell_owner(record, who, question, waiting=True)
        return True, f"[handoff] {record['id']} waits on you: {question['text']}"
    copy = not record["copy_sent"] and Path(session["path"]).exists()
    extra = {"context": _copy(record, session)} if copy else {}
    text = (POINTER if record["copy_sent"] else WITH_COPY if copy else NO_COPY) + _who_else(record)
    result = send("answer", code_of(record), who["mailbox"],
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


TAKEN = ("This handoff was already accepted by {mailbox} on {day}, so it is theirs to do. Stop here, and tell "
         "the person you are working with: to take part, they ask the sender to send them a handoff of their own.")


def tell_taken(record: dict, state: dict) -> None:
    """Each other holder of the code (a forwarded mail, a shared paste) is told once that it is taken,
    so their agent stops instead of waiting on a sender who ignores it (b26, melbourne-2)."""
    who = state["accepted"]
    if not who or not state["others"]:
        return
    path = global_config_dir() / "handoff" / "sent" / f"{record['id']}.json"
    with env_lock(path, timeout=300):
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        told = on_disk.get("told_taken", [])
        for address, mailbox in state["others"].items():
            if address in told or not mailbox:
                continue
            text = TAKEN.format(mailbox=who["mailbox"], day=who["at"][:10])
            if send("answer", code_of(record), mailbox,
                    agent=address if record.get("inbox") else None, text=text).get("success"):
                told.append(address)
        on_disk["told_taken"] = record["told_taken"] = told
        path.write_text(json.dumps(on_disk, indent=2) + "\n", encoding="utf-8")


def _tell_owner(record: dict, who: dict, question: dict, waiting: bool = False) -> None:
    """Mail the person who sent the handoff: the question, and the one line that answers it."""
    asked = html.escape(question["text"])
    how = ("They have your session already and say the answer is not in it, so only you can answer. Answer"
           if waiting else "Your agent sent them your session to search. If the answer is not in it (a decision you "
           "have not made yet, say), answer")
    body = (f"<p>{html.escape(who['mailbox'])} asked about your handoff <b>{html.escape(record.get('subject', record['id']))}</b>:</p>"
            f"<blockquote>{asked}</blockquote>"
            f"<p>{how} from any terminal on this machine, or ask your AI to:</p>"
            f"<pre>co handoff answer {record['id']} \"your answer\"</pre>")
    subject = "Waiting on you" if waiting else "Question"
    transport.mail_person(record["owner"], f"[co handoff] {subject} on {record['id']}: {_short(question['text'])}",
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


def _as_approved(exchange: dict, session: dict) -> dict:
    """A turn the sender changed with --edit goes as they left it; an untouched one keeps the AI's whole
    reply, of which the brief quotes 800 characters (b27 review: an edited sentence stayed in the copy)."""
    drafted = {t["at"]: t for t in session.get("drafted") or []}.get(exchange["at"])
    approved = {t["at"]: t for t in session.get("approved") or []}.get(exchange["at"])
    if drafted and approved and (drafted["user"], drafted["ai"]) != (approved["user"], approved["ai"]):
        return {**exchange, "user": approved["user"], "ai": approved["ai"]}
    return exchange


def copy_text(session: dict, until: str, keep=(), masked: bool = True, keep_names=()) -> str:
    """The session copy as text: the conversation the sender approved, each message whole and each AI
    turn in full, and nothing else. Never tool calls or their output (#2496): in a session that ran
    co rem they are whole pages about other people, and the sender's own mail."""
    turns = sessions.exchanges(sessions.read_turns(session["kind"], session["path"]))
    approved = None if session.get("keep") is None else set(session["keep"])   # None: a record from before keep
    since = session.get("since", "")
    kept = [e for e in turns if (approved is None or e["at"] in approved) and (not since or e["at"] >= since)
            and (not until or not e["at"] or e["at"] <= until)]
    kept = [_as_approved(_without_private(e, session), session) for e in kept]
    text = "\n\n".join(f"[{e['at'][:19]}] Sender:\n{e['user']}" + (f"\n\n[{e['at'][:19]}] AI:\n{e['ai']}" if e["ai"] else "")
                       for e in kept) + "\n"
    text = bundles.redact(text, bundles.known_secrets())
    to = next((k for k in keep if k), "")   # the recipient comes first in `keep`
    names = sorted({*bundles.rem_names(keep_names, to), *session.get("names", [])}, key=len, reverse=True)
    return bundles.mask(text, keep, names=names) if masked else text


def _without_private(exchange: dict, session: dict) -> dict:
    """The whole turn with the sentences the private pass removed from it at drafting (#2500): the copy
    carries each AI reply in full, and the private part of one is often past its quoted 800 characters."""
    found = (session.get("removed") or {}).get(exchange["at"])
    if not found:
        return exchange
    return {**exchange, "user": private.remove(exchange["user"], found), "ai": private.remove(exchange["ai"], found)}


def _copy(record: dict, session: dict, budget: int = None) -> str:
    """The session copy, packed; its newest part when the whole would not fit the inbox."""
    budget = budget or COPY_BUDGET
    text = copy_text(session, record["sent_at"], [record.get("to"), record.get("from"), record.get("owner")],
                     keep_names=record.get("keep_names", []))
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


def code_of(record: dict) -> dict:
    """What `send` needs of a sent handoff to answer about it: its id, secret, and key if it was sealed."""
    return {"id": record["id"], "secret": record["secret"], **({"key": record["key"]} if record.get("key") else {})}


def remember_peer(address: str, mailbox: str, handoff_id: str, to: str, inbox: bool = False, sealed: bool = False) -> str:
    """The acceptor may send this agent handoff messages, named after whoever `to` was; returns that name.
    Only that: a contact drives this agent and approves its own tool calls (audit, 2026-10-14).

    peers.json keeps which handoffs they took.
    """
    path = transport.contacts_file().parent / "peers.json"
    peers = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    peer = peers.setdefault(address, {"mailbox": mailbox, "scope": "handoff", "handoffs": []})
    if handoff_id not in peer["handoffs"]:
        peer["handoffs"].append(handoff_id)
    path.write_text(json.dumps(peers, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return transport.meet(to, address, inbox, f"accepted our handoff {handoff_id}", level="handoffs", sealed=sealed)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
