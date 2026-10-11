"""The handoff bundle: what crosses from one person's agent to another's.

One message, kept the way a compaction keeps a conversation: every message the
sender typed, word for word, and each stretch of the AI's replies summarised,
plus a short Task / Where it stands / Open questions on top and where the code is.
The AI's own text, tool output and the session file never leave the machine; the
recipient asks for anything missing (co handoff ask). `content_hash` covers
everything the sender saw in the preview, so the copy that arrives can be checked
against the one that was approved.
"""

import base64
import email
import email.policy
import hashlib
import html
import json
import re
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

FORMAT = "co-handoff/3"  # /2 carried decided/rejected/references and a clipped excerpt
BEGIN = "----- BEGIN CO HANDOFF BUNDLE -----"
END = "----- END CO HANDOFF BUNDLE -----"


class Reply(BaseModel):
    n: int = Field(description="The number of the [n] message the AI was answering")
    said: str = Field(description="What the AI said or did in reply")


class Replies(BaseModel):
    replies: list[Reply] = Field(default_factory=list, description="One per numbered message that has an AI part")


class Top(BaseModel):
    title: str = Field(description="The task in one line")
    task: str = Field(description="What the sender asked for, and what 'done' means")
    where_it_stands: str = Field(description="What is finished, what is in progress, what was tried, with the numbers")
    decided: list[str] = Field(default_factory=list, description="Each decision, with its reason")
    rejected: list[str] = Field(default_factory=list, description="Each option ruled out, with why")
    open_questions: list[str] = Field(default_factory=list, description="Each undecided question or action still owed, and who it waits on")


# One model call reads at most this much conversation; a longer session is summarised in pieces.
# 1.1M characters in one call took 241 s on a real 124 MB Claude Code session (study A, s12).
CHUNK_CHARS = 120_000

REPLIES_PROMPT = """These are numbered messages from a conversation between a person (Sender) and their
coding AI. The Sender's words travel to a colleague word for word; you summarise the AI's side.

For EVERY [n] that has an "AI:" part, even a short one, say what the AI said or did in reply:
its findings with their numbers, what it decided or ruled out and why, what it changed
(repository paths, commits, PRs, releases), and what it left unfinished. One to three
sentences; up to six for a long stretch, but never drop a number, decision or change.
Name things so a stranger understands them. Never copy a credential, token, key, invite
code, or a path under a home directory.

{transcript}"""

TOP_PROMPT = """A colleague's coding agent will continue this work from the conversation below: the
Sender's messages word for word, and a summary of each AI reply. Write the part they read first.

- task: the work the Sender names below ("own words"), not other work in the conversation, with
  what "done" means. A review stays a review and a question stays a question; never turn either
  into an order to fix or build.
- Permissions the Sender gave their own AI ("merge it yourself", "you may publish") are not the
  recipient's. Never pass one on.
- where_it_stands: what is finished, in progress and tried, with the numbers. Later messages
  override earlier ones: something requested early and done later is done.
- decided / rejected: every decision and every ruled-out option, each with its reason.
- open_questions: what is undecided or still owed (an action such as "revoke the key"), and who it waits on.
Write only what the conversation established; if something is uncertain, say so.

The Sender's own words about what to hand off: {what}

{transcript}"""


def new_id() -> str:
    return "ho-" + uuid.uuid4().hex[:8]


def draft(exchanges: list[dict], what: str, model: str = None) -> tuple[Top, dict[int, str]]:
    """The AI's side summarised in bounded pieces (in parallel), then the top written from all of it."""
    from concurrent.futures import ThreadPoolExecutor
    from ..llm_do import llm_do
    kwargs = {"model": model} if model else {}
    pieces = _pieces([(n, e) for n, e in enumerate(exchanges, 1) if e["ai"]])
    with ThreadPoolExecutor(max_workers=8) as pool:
        found = pool.map(lambda text: llm_do(REPLIES_PROMPT.format(transcript=text), output=Replies, **kwargs), pieces)
        said = {r.n: r.said for result in found for r in result.replies}
    transcript = "\n\n".join(f"[{n}] Sender: {e['user']}" + (f"\nAI, in summary: {said[n]}" if n in said else "")
                             for n, e in enumerate(exchanges, 1))
    top = llm_do(TOP_PROMPT.format(what=what or "(not stated; infer the task from the conversation)",
                                   transcript=transcript), output=Top, **kwargs)
    return top, said


def _pieces(numbered: list[tuple[int, dict]]) -> list[str]:
    """Consecutive exchanges packed into pieces of at most CHUNK_CHARS. One reply longer than that
    keeps its end, where an AI turn reports what it found and did."""
    pieces, current = [], ""
    for n, e in numbered:
        ai = e["ai"] if len(e["ai"]) <= CHUNK_CHARS // 2 else "[…start cut…]\n" + e["ai"][-(CHUNK_CHARS // 2):]
        text = f"[{n}] Sender: {e['user'][:CHUNK_CHARS // 4]}\nAI: {ai}"
        if current and len(current) + len(text) > CHUNK_CHARS:
            pieces.append(current)
            current = ""
        current += ("\n\n" if current else "") + text
    return pieces + ([current] if current else [])


def assemble(*, handoff_id: str, sender: str, to: str, what: str, source: dict, code: list[dict],
             top: Top, said: dict[int, str], exchanges: list[dict]) -> dict:
    bundle = {
        "format": FORMAT,
        "id": handoff_id,
        "from": sender,
        "to": to,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "asked": what,
        **top.model_dump(),
        "code": code,
        # The AI's own words stay here: only the summary of them goes.
        "conversation": [{"at": e["at"], "user": e["user"], "ai": said.get(n, "")}
                         for n, e in enumerate(exchanges, 1)],
    }
    return seal(bundle)


def seal(bundle: dict) -> dict:
    body = {k: v for k, v in bundle.items() if k != "content_hash"}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(body, content_hash=digest[:16])


# ---- credentials never leave the machine ----

CREDENTIAL_PATTERNS = {
    "OpenAI/Anthropic-style key": r"\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}",
    "GitHub token": r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}",
    "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "Slack token": r"\bxox[abposr]-[A-Za-z0-9-]{10,}",
    "Google API key": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "ConnectOnion invite code": r"\b[A-HJ-NP-Z2-9]{5}-[A-HJ-NP-Z2-9]{5}-[A-HJ-NP-Z2-9]{5}\b",
    "JWT": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "secret assignment": r"(?i)\b[A-Z0-9_]*(?:api[_-]?key|secret|token|password|passwd)[A-Z0-9_]*\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=.]{16,}",
}


def find_credentials(bundle: dict, known_secrets: list[str] = ()) -> list[str]:
    """Every credential-looking string in the bundle, as 'field: kind'. Empty means clean."""
    hits = []
    for field, text in _strings(bundle):
        for kind, pattern in CREDENTIAL_PATTERNS.items():
            if re.search(pattern, text):
                hits.append(f"{field}: {kind}")
        for secret in known_secrets:
            if secret in text:
                hits.append(f"{field}: a value from your keys.env")
    return hits


# Not secrets, but not the recipient's business either: they are shown in the
# preview so the sender removes or keeps each one knowingly (the skill's audit).
PRIVATE_PATTERNS = {
    "home directory path": r"(?:/Users|/home)/[A-Za-z0-9._-]+(?:/[^\s`'\")\]]*)?",
    "agent config path": r"~/\.(?:codex|claude|co)\b[^\s`'\")\]]*",
    "email address": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone number": r"\+\d[\d \-]{7,}\d",
    "IP address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
}


def find_private(bundle: dict) -> list[str]:
    """Private paths, email addresses and phone numbers in the bundle, as 'field: match' (deduplicated).
    The sender's and recipient's addresses are the header, and `code` holds repository URLs on purpose."""
    own = {bundle.get("from"), bundle.get("to")}
    hits = []
    for field, text in _strings({k: v for k, v in bundle.items() if k not in ("from", "to", "code")}):
        for pattern in PRIVATE_PATTERNS.values():
            hits += [f"{field}: {m}" for m in re.findall(pattern, text) if m not in own]
    return list(dict.fromkeys(hits))


def _strings(value, field: str = ""):
    if isinstance(value, str):
        yield field, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f"{field}.{key}" if field else key)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _strings(item, f"{field}[{i}]")


# ---- how a bundle travels in a mail body ----

def to_mail(bundle: dict, prompt: str) -> tuple[str, str]:
    """(subject, HTML body). The mail is the prompt to paste into a coding agent, brief inline,
    then the machine-readable bundle for co handoff open (base64, so no mail system rewrites it).

    HTML with <pre>, because the mail service sends the body as HTML: plain text arrived as
    one paragraph in every client (newlines collapse), and anything shaped like a tag vanished.
    """
    subject = f"[co handoff] {bundle['id']}: {_one_line(bundle['title'], 80)}"
    encoded = base64.b64encode(json.dumps(bundle, ensure_ascii=False).encode()).decode()
    wrapped = "\n".join(encoded[i:i + 76] for i in range(0, len(encoded), 76))
    body = (f"<pre>{html.escape(prompt)}</pre>\n"
            "<p>No AI agent at hand? Read the brief above, and reply to this email with any question.</p>\n"
            f"<pre>{BEGIN}\n{wrapped}\n{END}</pre>\n")
    return subject, body


def from_saved_mail(text: str) -> dict | None:
    """The bundle in a mail saved by any client: `co email read` output, the pasted body, or a downloaded .eml,
    whose text part may be quoted-printable or base64 encoded."""
    message = email.message_from_string(text, policy=email.policy.default)
    if message["MIME-Version"] or message["Content-Type"]:
        body = message.get_body(preferencelist=("plain",))
        text = body.get_content() if body else ""
    return from_mail(text)


def from_mail(body: str) -> dict | None:
    body = html.unescape(body or "")
    found = re.search(_marker(BEGIN) + r"(.*?)" + _marker(END), body or "", re.S)
    if not found:
        return None
    bundle = json.loads(base64.b64decode(re.sub(r"\s+", "", found.group(1))))
    if bundle.get("format") != FORMAT:
        return None
    bundle["verified"] = seal(bundle)["content_hash"] == bundle.get("content_hash")
    return bundle


def _marker(line: str) -> str:
    """Spaces inside a marker may come back as line breaks: a terminal wraps `co email read` at its width."""
    return r"\s+".join(map(re.escape, line.split()))


def _one_line(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 1] + "…"


# ---- what a person reads: one format everywhere ----

def questions_text(bundle: dict) -> str:
    return "\n".join(f"- {q}" for q in bundle.get("open_questions", [])) or "- none"


def code_text(bundle: dict) -> str:
    places = bundle.get("code") or []
    if not places:
        return "- The session did not work in a git repository. Ask the sender where the code is."
    lines = []
    for code in places:
        pushed = "pushed" if code["pushed"] else "not pushed yet: ask the sender to push it"
        branch = "detached" if code["branch"] == "HEAD" else f"branch {code['branch']}"
        lines.append(f"- {code['repository'] or 'a repository with no remote'}, {branch}, "
                     f"commit {code['commit']} ({pushed})")
        if code["uncommitted"]:
            lines.append(f"  {code['uncommitted']} changed file(s) on the sender's machine are not in that commit")
    return "\n".join(lines)


def _asked(bundle: dict) -> str:
    """The sender's own words about what to hand off lead the task, so the summary cannot replace them."""
    return f"Handed off as: {bundle['asked']}\n\n" if bundle.get("asked") else ""


def _listed(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "- none recorded"


def conversation_text(bundle: dict) -> str:
    turns = []
    for n, e in enumerate(bundle["conversation"], 1):
        turns.append(f"[{n}] {bundle['from']}:\n{e['user']}" + (f"\n\nAI, in summary: {e['ai']}" if e["ai"] else ""))
    return "\n\n".join(turns)


def header(bundle: dict) -> str:
    # A blank line, not a single newline: the mail service joins single newlines in the text part.
    return (f"# Handoff: {bundle['title']}\n\n"
            f"From: {bundle['from']} · To: {bundle['to']} · {bundle['created_at'][:10]} · {bundle['id']}")


def brief_markdown(bundle: dict) -> str:
    """The whole handoff: preview, mail, HANDOFF.md and co handoff show all print this."""
    return (f"{header(bundle)}\n\n"
            f"## Task\n{_asked(bundle)}{bundle['task']}\n\n"
            f"## Where it stands\n{bundle['where_it_stands']}\n\n"
            f"## Decided\n{_listed(bundle.get('decided', []))}\n\n"
            f"## Rejected\n{_listed(bundle.get('rejected', []))}\n\n"
            f"## Open questions\n{questions_text(bundle)}\n\n"
            f"## Code\n{code_text(bundle)}\n\n"
            f"## Conversation\nEvery message {bundle['from']} wrote, word for word; the AI's replies in summary. "
            f"Anything not here, ask the sender.\n\n{conversation_text(bundle)}\n")
