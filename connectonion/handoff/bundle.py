"""The handoff bundle: what crosses from one person's agent to another's.

One message: every message the sender typed, word for word, and the AI's own text
after each, quoted (a long one keeps its start and end), with a short report on
top (Discussed, Concluded, Still open, a diagram) as a guide to the quotes, and
where the code is. Originals over summaries (decision 076): a summary drops what
its writer thought unimportant, and the reader cannot tell what is missing. Tool
output and the session file stay on the machine until the first answer; the
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


class Top(BaseModel):
    title: str = Field(description="The task in one line")
    headline: str = Field(default="", description="Who worked on what, and when, in one line a stranger understands")
    discussed: list[str] = Field(default_factory=list, description="3 to 5 things the conversation covered, in plain words")
    task: str = Field(description="What the sender asked for, and what 'done' means")
    where_it_stands: str = Field(description="What is finished, what is in progress, what was tried, with the numbers")
    decided: list[str] = Field(default_factory=list, description="Each decision, with its reason")
    rejected: list[str] = Field(default_factory=list, description="Each option ruled out, with why")
    open_questions: list[str] = Field(default_factory=list, description="Each undecided question or action still owed, and who it waits on")
    diagram: str = Field(default="", description="A small ASCII diagram of the flow or decision, or empty")


# The AI's text for one turn, quoted: past this it keeps its start and (mostly) its end, where a
# turn reports what it found and did. The report call reads at most TOP_CHARS, newest first.
QUOTE_CHARS = 2_000
TOP_CHARS = 400_000

TOP_PROMPT = """A colleague's coding agent will continue this work from the conversation below: the
Sender's messages and the AI's replies, word for word (a long reply is cut in the middle). Write the
part they read first; it is a guide to the quotes, which go with it.

- task: the work the Sender names below ("own words"), not other work in the conversation, with
  what "done" means. A review stays a review and a question stays a question; never turn either
  into an order to fix or build.
- Permissions the Sender gave their own AI ("merge it yourself", "you may publish") are not the
  recipient's. Never pass one on, and never mention one. An owed action that needs permission
  (merge, publish, release, deploy, pay, delete) waits on the Sender, unless the Sender gave that
  permission to the recipient by name.
- Limits the Sender put on their own AI ("don't change files", "just explain", "read only") are not
  passed on either: they were for that session. The Sender's own words about what to hand off say what
  the recipient does, and "done" is that. Never list such a limit as decided, rejected or open.
- where_it_stands: what is finished, in progress and tried, with the numbers. Later messages
  override earlier ones: something requested early and done later is done.
- decided / rejected: every decision and every ruled-out option, each with its reason.
- open_questions: what is undecided or still owed (an action such as "revoke the key"), and who it waits on.
- headline: one line a stranger understands: who, on what, and when ("Alice and Codex, 11 Oct: storing
  the login token"). discussed: 3 to 5 plain bullets a person can read on a phone.
- diagram: at most 10 lines of ASCII (─ │ ├ └ ► and spaces) showing the flow or the decision, with the
  open branch marked "(open)"; empty when there is nothing to draw. Every box in it must come from the
  conversation.
Write only what the conversation established; if something is uncertain, say so.

{who}
The Sender's own words about what to hand off: {what}

{transcript}"""


def new_id() -> str:
    return "ho-" + uuid.uuid4().hex[:8]


AGENTS = {"codex": "Codex", "claude": "Claude Code"}


def draft(exchanges: list[dict], what: str, model: str = None, sender: str = "",
          agent: str = "") -> tuple[Top, dict[int, str]]:
    """The AI's side quoted, and the report on top written from the newest TOP_CHARS of it."""
    from ..llm_do import llm_do
    kwargs = {"model": model} if model else {}
    said = {n: quote(e["ai"]) for n, e in enumerate(exchanges, 1) if e["ai"]}
    turns = [f"[{n}] Sender: {e['user']}" + (f"\nAI: {said[n]}" if n in said else "") for n, e in enumerate(exchanges, 1)]
    kept = turns
    while len(kept) > 1 and sum(len(t) + 2 for t in kept) > TOP_CHARS:
        kept = kept[1:]
    transcript = (f"[Messages 1 to {len(turns) - len(kept)} are left out here.]\n\n" if len(kept) < len(turns) else "") + "\n\n".join(kept)
    day = next((e["at"][:10] for e in reversed(exchanges) if e["at"]), "")
    who = (f"The Sender is {sender or 'unnamed'}, working with {AGENTS.get(agent, 'their AI')}"
           + (f", on {day}." if day else "."))
    top = llm_do(TOP_PROMPT.format(who=who, what=what or "(not stated; infer the task from the conversation)",
                                   transcript=transcript), output=Top, **kwargs)
    top.diagram = diagram_lines(top.diagram)
    return top, said


def diagram_lines(diagram: str) -> str:
    """Models sometimes return the diagram's line breaks as a literal backslash-n (seen live, 1.9.2b21)."""
    return diagram.replace("\\n", "\n").rstrip()


def quote(text: str) -> str:
    """The AI's own words for one turn; a long one keeps its start and its end, and says how much was cut."""
    if len(text) <= QUOTE_CHARS:
        return text
    head, tail = QUOTE_CHARS // 4, QUOTE_CHARS - QUOTE_CHARS // 4
    return (f"{text[:head]}\n[… {len(text) - head - tail:,} characters cut; the full session comes with the first "
            f"answer]\n{text[-tail:]}")


def assemble(*, handoff_id: str, sender: str, to: str, what: str, source: dict, code: list[dict],
             top: Top, said: dict[int, str], exchanges: list[dict], titles: dict[str, str] = None,
             sender_name: str = "") -> dict:
    bundle = {
        "format": FORMAT,
        "id": handoff_id,
        "from": sender,
        **({"from_name": sender_name} if sender_name else {}),
        "to": to,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "asked": what,
        **top.model_dump(),
        "code": code,
        "conversation": [{"at": e["at"], "user": e["user"], "ai": said.get(n, "")}
                         for n, e in enumerate(exchanges, 1)],
        "ai_quoted": True,   # 1.9.2b21: "ai" is the AI's own text, not a summary of it
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
    "ConnectOnion handoff code": r"\bcoh[123]\.[A-Za-z0-9_-]{40,}",
    "JWT": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "secret assignment": r"(?i)\b[A-Z0-9_]*(?:api[_-]?key|secret|token|password|passwd)[A-Z0-9_]*\\*['\"]?\s*[:=]\s*\\*['\"]?[A-Za-z0-9_\-/+=.]{16,}",
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
# Outlook's Word engine ignores padding, border and wrapping on <pre>, so the frame is the cell.
_FRAME = f"padding:14px 16px;background:{_TINT};border:1px solid {_LINE}"
_PRE = ("margin:0;white-space:pre-wrap;word-break:normal;overflow-wrap:anywhere;"
        f"font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;line-height:1.5;color:{_INK}")
GUIDE = "https://github.com/openonion/connectonion/blob/main/docs/cli/handoff.md"


CLIENT_NAMES = {"claude": "Claude Code", "codex": "Codex"}

WORDS = {   # the mail in the language the sender wrote in (Aaron, 2026-10-13)
    "en": {"subject": "{name} passed you some work: {title}",
           "lead": "{name} has been working on “{title}” with {client}, and would like you to take it from here.",
           "talked": "They talked through: {point}.",
           "how": "To pick it up, start a new conversation in Codex or Claude Code and paste the block below. "
                  "{name}'s session continues there, with the code. Nothing runs until you paste it.",
           "select": "Triple-click the grey box to select all of it, then copy it (Cmd+C on a Mac, Ctrl+C elsewhere).",
           "footer": "Sent with co handoff, from ConnectOnion (open source).", "guide": "How it works",
           "space": " ", "colon": ": "},
    "zh": {"subject": "{name} 想把一项工作交给你：{title}",
           "lead": "{name} 一直在和 {client} 一起做「{title}」，想请你接着做下去。",
           "talked": "他们讨论了：{point}。",
           "how": "想接手的话，在 Codex 或 Claude Code 里新开一个对话，把下面这段粘贴进去，{name} 的会话就会在那里接着进行，"
                  "代码也会一起过来。粘贴之前，什么都不会运行。",
           "select": "在灰色框里连点三下即可全选，然后复制（Mac 按 Cmd+C，其他电脑按 Ctrl+C）。",
           "footer": "由 ConnectOnion（开源）的 co handoff 发送。", "guide": "了解更多",
           "space": "", "colon": "："},
}


def language(bundle: dict) -> str:
    """"zh" or "en": the bundle's own "lang", else whichever the sender's own words are mostly written in."""
    if bundle.get("lang") in WORDS:
        return bundle["lang"]
    said = " ".join([bundle.get("asked", "")] + [e["user"] for e in bundle.get("conversation", [])])
    han = len(re.findall(r"[\u4e00-\u9fff]", said))
    return "zh" if han > len(re.findall(r"[A-Za-z]+", said)) / 2 else "en"


def _sentence_case(text: str) -> str:
    """"Shortcomings of …" reads mid-sentence as "shortcomings of …"; "API limits" stays as it is."""
    return text[0].lower() + text[1:] if len(text) > 1 and text[1].islower() else text


def notice(bundle: dict, prompt: str) -> dict:
    """{subject, text, html}: the mail a person gets, short, like a note from someone they know (#2478).

    Aaron, 2026-10-13: the 1.9.2b22 mail ("[co handoff] … (from …)", a ConnectOnion banner, every
    finding laid out, from an agent mailbox) looked like spam and was overwhelming. So: a short
    subject without co's words, one or two sentences on who worked on what with their AI and what
    they talked through, the block, one line of footer, in the language the sender wrote in. What
    they decided reaches the agent when it accepts. It goes from the sender's own mailbox when there
    is one (transport.hand_over). The HTML keeps the block in the first <pre> and the bundle hidden
    at the end, which co handoff inbox and open read back."""
    words = WORDS[language(bundle)]
    name, title = sender_name(bundle), _one_line(bundle["title"], 80)
    client = CLIENT_NAMES.get(bundle.get("source", {}).get("kind"), "AI")
    lead = words["lead"].format(name=name, title=title, client=client)
    points = bundle.get("discussed") or []
    talked = words["talked"].format(point=_sentence_case(_one_line(points[0].rstrip(".。"), 160))) if points else ""
    said = words["space"].join(part for part in (lead, talked) if part)
    subject = words["subject"].format(name=name, title=_one_line(bundle["title"], 60))
    how = words["how"].format(name=name)
    text = (f"{said}\n\n{how}\n\n"
            f"{words['select']}\n\n{prompt.strip()}\n\n"
            f"{words['footer']}{words['space']}{words['guide']}{words['colon']}{GUIDE}\n")
    encoded = base64.b64encode(json.dumps(bundle, ensure_ascii=False).encode()).decode()
    wrapped = "\n".join(encoded[i:i + 76] for i in range(0, len(encoded), 76))
    e = html.escape
    page = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff">'
        '<tr><td style="padding:16px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:600px;{_FONT};font-size:15px;line-height:1.55;color:{_INK}"><tr><td>'
        f'<p style="margin:0 0 14px">{e(said)}</p>'
        f'<p style="margin:0 0 14px">{e(how)}</p>'
        f'<p style="margin:0 0 6px;color:{_MUTED};font-size:13px">{e(words["select"])}</p>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td style="{_FRAME}"><pre style="{_PRE}">{e(prompt.strip())}</pre></td></tr></table>'
        '<div style="height:18px"></div>'
        f'<p style="margin:0;color:{_MUTED};font-size:13px">{e(words["footer"])}{words["space"]}'
        f'<a href="{GUIDE}" style="color:{_GREEN}">{e(words["guide"])}</a></p>'
        '</td></tr></table></td></tr></table>'
        f'<div style="display:none;max-height:0;overflow:hidden;mso-hide:all">{BEGIN}\n{wrapped}\n{END}</div>\n'
    )
    return {"subject": subject, "text": text, "html": page}


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
        travels = "sha256" in (code.get("patch") or {})
        pushed = ("pushed" if code["pushed"] and not travels else
                  "not pushed; it goes with this handoff and accept rebuilds it" if travels else
                  "not pushed yet: ask the sender to push it")
        branch = "detached" if code["branch"] == "HEAD" else f"branch {code['branch']}"
        lines.append(f"- {code['repository'] or 'a repository with no remote'}, {branch}, "
                     f"commit {code['commit']} ({pushed})")
        if code["uncommitted"]:
            lines.append(f"  {code['uncommitted']} changed file(s) on the sender's machine are not in that commit"
                         + ("; they go with this handoff too" if travels else ""))
    return "\n".join(lines)


def _asked(bundle: dict) -> str:
    """The sender's own words about what to hand off lead the task, so the summary cannot replace them."""
    return f"Handed off as: {bundle['asked']}\n\n" if bundle.get("asked") else ""


def _mentioned(bundle: dict) -> str:
    return "\n".join(f"- #{n}: {title}" for n, title in bundle["mentioned"].items())


def _listed(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "- none recorded"


def conversation_text(bundle: dict, chars: int = None) -> str:
    label = "AI" if bundle.get("ai_quoted") else "AI, in summary"
    turns = [f"[{n}] {sender_name(bundle)}:\n{e['user']}" + (f"\n\n{label}: {e['ai']}" if e["ai"] else "")
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
            f"From: {_from(bundle)} · To: {bundle['to']} · {bundle['created_at'][:10]} · {bundle['id']}")


def sender_name(bundle: dict) -> str:
    """The sender as a person knows them: their name when the bundle carries it, else their address."""
    return bundle.get("from_name") or bundle["from"]


def _from(bundle: dict) -> str:
    return f"{bundle['from_name']} ({bundle['from']})" if bundle.get("from_name") else bundle["from"]


def report(bundle: dict) -> str:
    """What a person reads first (#2460): who and what, what was discussed and concluded, what is
    still open, and a small diagram. Bundles from before 1.9.2b21 have no headline: it is skipped."""
    parts = [bundle["headline"]] if bundle.get("headline") else []
    if bundle.get("discussed"):
        parts.append(f"## Discussed\n{_listed(bundle['discussed'])}")
    if bundle.get("decided"):
        parts.append(f"## Concluded\n{_listed(bundle['decided'])}")
    parts.append(f"## Still open\n{questions_text(bundle)}")
    if bundle.get("diagram", "").strip():
        parts.append(f"```\n{bundle['diagram'].rstrip()}\n```")
    return "\n\n".join(parts)


def brief_markdown(bundle: dict, conversation_chars: int = None) -> str:
    """The whole handoff: preview, HANDOFF.md and co handoff show all print this. The report
    first, then the detail for whoever wants it.

    `conversation_chars` keeps the newest messages that fit."""
    return (f"{header(bundle)}\n\n{report(bundle)}\n\n"
            f"## Task\n{_asked(bundle)}{bundle['task']}\n\n"
            f"## Where it stands\n{bundle['where_it_stands']}\n\n"
            + (f"## Rejected\n{_listed(bundle['rejected'])}\n\n" if bundle.get("rejected") else "")
            + f"## Code\n{code_text(bundle)}\n\n"
            + (f"## Issues and PRs mentioned\n{_mentioned(bundle)}\n\n" if bundle.get("mentioned") else "")
            + f"## Conversation\nEvery message {sender_name(bundle)} wrote, word for word; the AI's replies "
            + ("word for word, a long one cut in the middle. " if bundle.get("ai_quoted") else "in summary. ")
            + f"Anything not here, ask the sender.\n\n{conversation_text(bundle, conversation_chars)}\n")
