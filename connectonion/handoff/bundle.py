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
import os
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
  recipient's. Never pass one on, and never mention one. An owed action that needs permission
  (merge, publish, release, deploy, pay, delete) waits on the Sender, unless the Sender gave that
  permission to the recipient by name.
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
             top: Top, said: dict[int, str], exchanges: list[dict], titles: dict[str, str] = None) -> dict:
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
    # Each #N the handoff mentions, named from what the session itself read; numbers alone mean nothing.
    mentioned = dict.fromkeys(re.findall(r"#(\d{1,6})\b", json.dumps(bundle, ensure_ascii=False)))
    bundle["mentioned"] = {n: (titles or {})[n] for n in mentioned if n in (titles or {})}
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
    # A handoff code is the secret that accepts or asks on one handoff (replies.make_code).
    "ConnectOnion handoff code": r"\bcoh[12]\.[A-Za-z0-9_-]{40,}",
    "JWT": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "secret assignment": r"(?i)\b[A-Z0-9_]*(?:api[_-]?key|secret|token|password|passwd)[A-Z0-9_]*['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=.]{16,}",
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


def redact(text: str, known_secrets: list[str] = ()) -> str:
    """`text` with every credential-looking string replaced: for the session copy, which no one reviews
    line by line the way a person reviews the brief's preview."""
    for kind, pattern in CREDENTIAL_PATTERNS.items():
        text = re.sub(pattern, f"[removed: {kind}]", text)
    for secret in known_secrets:
        text = text.replace(secret, "[removed: a value from keys.env]")
    return text


def known_secrets() -> list[str]:
    """Values of credential-named keys in the environment: any of them in a handoff is a leak."""
    names = ("KEY", "TOKEN", "SECRET", "PASSWORD", "INVITE")
    return [v for k, v in os.environ.items() if any(n in k.upper() for n in names) and len(v) >= 12]


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

_FONT = "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
_INK, _MUTED, _GREEN, _TINT, _LINE = "#1f2a22", "#4b5b4f", "#15803d", "#f3f8f4", "#cfe3d4"
_LABEL = f"color:{_GREEN};font-size:13px;font-weight:700;letter-spacing:.05em"
# Outlook's Word engine ignores padding, border and wrapping on <pre>, so the frame is the cell.
_FRAME = f"padding:14px 16px;background:{_TINT};border:1px solid {_LINE}"
_PRE = ("margin:0;white-space:pre-wrap;word-break:break-all;"
        f"font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;line-height:1.5;color:{_INK}")
GUIDE = "https://github.com/openonion/connectonion/blob/main/docs/cli/handoff.md"
SITE = "https://github.com/openonion/connectonion"


def to_mail(bundle: dict, prompt: str) -> tuple[str, str]:
    """(subject, HTML body) for a person who has never heard of co, reading on any screen.

    In reading order (#2415): who sent what and what ConnectOnion is; the task, where it stands
    and the open questions; three numbered steps; the block to paste, labelled where it starts
    and ends because no mail client runs a copy button. A table layout, because Outlook ignores
    max-width on a div. Reviewed by a UI and product-flow pass (2026-10-12): one green box only,
    so "the box" is never ambiguous; step 3 promises only what the prompt does. Last, hidden, the
    bundle `co handoff open` reads from a saved mail (base64, so no mail system rewrites it); it
    is after the block, so a clipped mail loses only the bundle, never the block.
    """
    sender, title = html.escape(bundle["from"]), html.escape(bundle["title"])
    subject = f"[co handoff] {_one_line(bundle['title'], 70)} (from {bundle['from']})"
    encoded = base64.b64encode(json.dumps(bundle, ensure_ascii=False).encode()).decode()
    wrapped = "\n".join(encoded[i:i + 76] for i in range(0, len(encoded), 76))
    body = (
        f'<div style="display:none;max-height:0;overflow:hidden;mso-hide:all">{sender} handed you a task: '
        f'{title}. Paste one block into Codex or Claude Code to continue.</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff">'
        '<tr><td align="center" style="padding:24px 16px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:600px;{_FONT};font-size:15px;line-height:1.55;color:{_INK}">'
        f'<tr><td style="padding:0 0 14px;border-bottom:2px solid {_GREEN};{_LABEL}">CONNECTONION HANDOFF</td></tr>'
        f'<tr><td style="padding:20px 0 4px;color:{_MUTED};font-size:14px">{sender} handed you a task</td></tr>'
        f'<tr><td style="padding:0 0 10px"><h1 style="margin:0;font-size:24px;line-height:1.25">{title}</h1></td></tr>'
        f'<tr><td style="padding:0 0 18px;color:{_MUTED};font-size:14px">'
        f'<a href="{SITE}" style="color:{_GREEN}">ConnectOnion</a> is an open-source tool for AI agents. '
        f'{sender} used it to pass you this task. To continue, paste the block below into Codex or '
        'Claude Code on your computer. Nothing runs until you do.</td></tr>'
        f'<tr><td style="padding:2px 0 2px 16px;border-left:3px solid {_GREEN}">'
        + _field("The task", html.escape(bundle["task"]))
        + _field("Where it stands", html.escape(bundle["where_it_stands"]))
        + _questions(bundle.get("open_questions", []))
        + '</td></tr>'
        '<tr><td style="padding:28px 0 4px"><h2 style="margin:0;font-size:19px">Continue it with your AI agent</h2></td></tr>'
        '<tr><td style="padding:0 0 16px">'
        + _step(1, "Open <b>Codex</b> or <b>Claude Code</b> on your computer, in the folder where you want to work.")
        + _step(2, "Copy everything between START and END below and paste it into your agent. "
                   f'<span style="color:{_MUTED}">On your phone? Open this email on that computer.</span>')
        + _step(3, f"Your agent installs co if it is missing, tells {sender} you have picked the task up, "
                   "then explains the task and asks before touching your files.")
        + '</td></tr>'
        f'<tr><td style="padding:0 0 6px;{_LABEL}">START</td></tr>'
        f'<tr><td style="{_FRAME}"><pre style="{_PRE}">{html.escape(prompt.strip())}</pre></td></tr>'
        f'<tr><td style="padding:6px 0 0;{_LABEL}">END</td></tr>'
        f'<tr><td style="padding:22px 0 0;color:{_MUTED};font-size:14px">'
        f'First time? <a href="{GUIDE}" style="color:{_GREEN}">How a handoff works</a>.</td></tr>'
        f'<tr><td style="padding:22px 0 0;margin-top:22px;border-top:1px solid {_LINE};color:#5f6b62;font-size:13px">'
        f'Handoff {html.escape(bundle["id"])}, sent by {sender} with co handoff.</td></tr>'
        '</table></td></tr></table>'
        f'<div style="display:none;max-height:0;overflow:hidden;mso-hide:all">{BEGIN}\n{wrapped}\n{END}</div>\n'
    )
    return subject, body


def _field(label: str, text: str) -> str:
    return f'<p style="margin:0 0 2px;{_LABEL}">{label.upper()}</p><p style="margin:0 0 12px">{text}</p>'


def _questions(questions: list[str]) -> str:
    if not questions:
        return ""
    items = "".join(f'<li style="margin:0 0 4px">{html.escape(q)}</li>' for q in questions)
    return f'<p style="margin:0 0 2px;{_LABEL}">OPEN QUESTIONS</p><ul style="margin:0 0 8px;padding-left:20px">{items}</ul>'


def _step(number: int, text: str) -> str:
    return ('<table role="presentation" cellpadding="0" cellspacing="0" style="margin:10px 0 0"><tr>'
            '<td valign="top" style="width:30px"><div style="width:22px;height:22px;border-radius:11px;'
            f'background:{_GREEN};color:#ffffff;font-size:12px;font-weight:700;line-height:22px;'
            f'text-align:center">{number}</div></td><td style="font-size:15px">{text}</td></tr></table>')


def from_saved_mail(text: str) -> dict | None:
    """The bundle in a mail saved by any client: `co email read` output, the pasted body, or a downloaded .eml,
    whose text part may be quoted-printable or base64 encoded."""
    message = email.message_from_string(text, policy=email.policy.default)
    if message["MIME-Version"] or message["Content-Type"]:
        parts = [message.get_body(preferencelist=(kind,)) for kind in ("plain", "html")]
        text = "\n".join(part.get_content() for part in parts if part)
    return from_mail(text)


def prompt_in(body: str) -> str:
    """The block a person pastes: the first <pre> of a handoff mail, or for a mail read as plain text,
    everything before its bundle block."""
    box = re.search(r"(?s)<pre[^>]*>(.*?)</pre>", body or "")
    if box and not re.search(_marker(BEGIN), box.group(1)):
        return html.unescape(box.group(1)).strip()
    found = re.search(r"(?s)(.*?)" + _marker(BEGIN), html.unescape(re.sub(r"<[^>]+>", "", body or "")))
    return found.group(1).strip() if found else ""


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


def _mentioned(bundle: dict) -> str:
    return "\n".join(f"- #{n}: {title}" for n, title in bundle["mentioned"].items())


def _listed(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "- none recorded"


def conversation_text(bundle: dict, chars: int = None) -> str:
    turns = [f"[{n}] {bundle['from']}:\n{e['user']}" + (f"\n\nAI, in summary: {e['ai']}" if e["ai"] else "")
             for n, e in enumerate(bundle["conversation"], 1)]
    kept = turns
    while chars and len(kept) > 1 and sum(len(t) + 2 for t in kept) > chars:
        kept = kept[1:]
    if len(kept) == len(turns):
        return "\n\n".join(turns)
    return (f"[Messages 1 to {len(turns) - len(kept)} are left out to keep this mail short; the sender's agent "
            f"sends the whole session with its first answer.]\n\n" + "\n\n".join(kept))


def header(bundle: dict) -> str:
    # A blank line, not a single newline: the mail service joins single newlines in the text part.
    return (f"# Handoff: {bundle['title']}\n\n"
            f"From: {bundle['from']} · To: {bundle['to']} · {bundle['created_at'][:10]} · {bundle['id']}")


def brief_markdown(bundle: dict, conversation_chars: int = None) -> str:
    """The whole handoff: preview, mail, HANDOFF.md and co handoff show all print this.

    `conversation_chars` keeps the newest messages that fit, for the block pasted from a mail."""
    return (f"{header(bundle)}\n\n"
            f"## Task\n{_asked(bundle)}{bundle['task']}\n\n"
            f"## Where it stands\n{bundle['where_it_stands']}\n\n"
            + "".join(f"## {name}\n{_listed(bundle[key])}\n\n"
                      for name, key in (("Decided", "decided"), ("Rejected", "rejected")) if bundle.get(key))
            + f"## Open questions\n{questions_text(bundle)}\n\n"
            f"## Code\n{code_text(bundle)}\n\n"
            + (f"## Issues and PRs mentioned\n{_mentioned(bundle)}\n\n" if bundle.get("mentioned") else "")
            + f"## Conversation\nEvery message {bundle['from']} wrote, word for word; the AI's replies in summary. "
            f"Anything not here, ask the sender.\n\n{conversation_text(bundle, conversation_chars)}\n")
