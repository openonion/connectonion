"""The handoff bundle: what crosses from one person's agent to another's.

A bundle is one JSON document. The summary (goal, current state, next step, open
questions, what the recipient may do) is what a person reads first; decisions
with their rejected options, evidence pointers and the raw transcript excerpt are
there on request. `content_hash` covers everything the sender saw in the preview,
so the copy that arrives can be checked against the one that was approved.
"""

import base64
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

FORMAT = "co-handoff/1"
BEGIN = "----- BEGIN CO HANDOFF BUNDLE -----"
END = "----- END CO HANDOFF BUNDLE -----"


class Rejected(BaseModel):
    option: str = Field(description="The option that was considered and not taken")
    why_not: str = Field(description="The reason given in the conversation for rejecting it")


class Decision(BaseModel):
    decision: str = Field(description="What was decided")
    why: str = Field(description="The reason, as stated in the conversation")
    rejected: list[Rejected] = Field(default_factory=list, description="Alternatives turned down, each with its reason")


class Evidence(BaseModel):
    pointer: str = Field(description="A file path, URL, commit, issue or message the claim rests on")
    note: str = Field(description="What it shows")


class Draft(BaseModel):
    goal: str = Field(description="The task being handed off, in one or two sentences")
    decisions: list[Decision] = Field(default_factory=list)
    current_state: str = Field(description="Where the work stands now: done, in progress, not started")
    next_step: str = Field(description="The single next concrete step for the recipient")
    open_questions: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    recipient_may: list[str] = Field(default_factory=list, description="What the recipient is allowed to do, only as stated by the sender; empty if not discussed")


DRAFT_PROMPT = """You prepare a handoff so a colleague's coding agent can continue a task
without the sender rewriting the background. Use ONLY the conversation below.

- Record every decision with its reason, and every option that was rejected with
  the reason it was rejected. Rejected options matter most: the recipient will ask
  "why not X?".
- Separate what was decided from what was only proposed; proposals go in open_questions.
- Evidence pointers are concrete: file paths, commands, URLs, issue/PR numbers that
  appear in the conversation. Never invent one.
- recipient_may lists only permissions the sender stated; leave it empty otherwise.
- Never copy a credential, token, password or key.

The sender's own words about what to hand off: {what}

Conversation (oldest first):
{transcript}"""


def new_id() -> str:
    return "ho-" + uuid.uuid4().hex[:8]


def draft(turns: list[dict], what: str, model: str = None) -> Draft:
    """One llm_do call turns the excerpt into the structured summary."""
    from ..llm_do import llm_do
    transcript = "\n\n".join(f"[{t['role']}] {t['text']}" for t in turns)
    prompt = DRAFT_PROMPT.format(what=what or "(not stated; infer the task from the conversation)",
                                 transcript=transcript)
    kwargs = {"model": model} if model else {}
    return llm_do(prompt, output=Draft, **kwargs)


def assemble(*, handoff_id: str, sender: str, to: str, what: str, source: dict,
             summary: Draft, turns: list[dict]) -> dict:
    bundle = {
        "format": FORMAT,
        "id": handoff_id,
        "from": sender,
        "to": to,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task": what,
        "source": source,
        **summary.model_dump(),
        "excerpt": turns,
    }
    return seal(bundle)


def seal(bundle: dict) -> dict:
    body = {k: v for k, v in bundle.items() if k != "content_hash"}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(body, content_hash=digest[:16])


# ---- credentials never leave the machine ----

CREDENTIAL_PATTERNS = {
    "OpenAI/Anthropic-style key": r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}",
    "GitHub token": r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}",
    "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "Slack token": r"\bxox[abposr]-[A-Za-z0-9-]{10,}",
    "Google API key": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
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

def to_mail(bundle: dict) -> tuple[str, str]:
    """(subject, body). The body opens with the readable summary; the bundle follows, base64 so no mail system rewrites it."""
    subject = f"[co handoff] {bundle['id']}: {_one_line(bundle['goal'], 80)}"
    encoded = base64.b64encode(json.dumps(bundle, ensure_ascii=False).encode()).decode()
    wrapped = "\n".join(encoded[i:i + 76] for i in range(0, len(encoded), 76))
    body = (f"{summary_text(bundle)}\n\n"
            f"To continue this in your own coding agent: co handoff open {bundle['id']}\n\n"
            f"{BEGIN}\n{wrapped}\n{END}\n")
    return subject, body


def from_mail(body: str) -> dict | None:
    found = re.search(re.escape(BEGIN) + r"(.*?)" + re.escape(END), body or "", re.S)
    if not found:
        return None
    bundle = json.loads(base64.b64decode(re.sub(r"\s+", "", found.group(1))))
    if bundle.get("format") != FORMAT:
        return None
    bundle["verified"] = seal(bundle)["content_hash"] == bundle.get("content_hash")
    return bundle


def _one_line(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 1] + "…"


# ---- what a person reads ----

def summary_text(bundle: dict) -> str:
    lines = [f"Handoff {bundle['id']} from {bundle['from']}", "",
             f"Goal: {bundle['goal']}", "",
             f"Current state: {bundle['current_state']}", "",
             f"Next step: {bundle['next_step']}"]
    if bundle.get("open_questions"):
        lines += ["", "Open questions:"] + [f"- {q}" for q in bundle["open_questions"]]
    lines += ["", "You may: " + ("; ".join(bundle["recipient_may"]) if bundle.get("recipient_may")
                                 else "not stated by the sender")]
    lines += ["", f"{_count(bundle.get('decisions'), 'decision')}, {_count(bundle.get('evidence'), 'evidence pointer')}, "
                  f"{len(bundle.get('excerpt', []))}-turn transcript excerpt included."]
    return "\n".join(lines)


def _count(items, noun: str) -> str:
    n = len(items or [])
    return f"{n} {noun}" + ("" if n == 1 else "s")


def decisions_text(bundle: dict) -> str:
    lines = []
    for i, d in enumerate(bundle.get("decisions", []), 1):
        lines += [f"{i}. {d['decision']}", f"   Why: {d['why']}"]
        lines += [f"   Rejected: {r['option']} — {r['why_not']}" for r in d.get("rejected", [])]
    return "\n".join(lines) or "No decisions recorded."


def evidence_text(bundle: dict) -> str:
    lines = [f"- {e['pointer']}: {e['note']}" for e in bundle.get("evidence", [])] or ["No evidence pointers."]
    source = bundle.get("source", {})
    lines += ["", f"Transcript excerpt ({source.get('kind', '?')} session {source.get('session', '?')}, "
                  f"last {len(bundle.get('excerpt', []))} turns):"]
    lines += [f"[{t['role']}] {t['text']}" for t in bundle.get("excerpt", [])]
    return "\n".join(lines)


def brief_markdown(bundle: dict) -> str:
    """HANDOFF.md, the file the recipient's coding agent reads first."""
    return (f"# Handoff {bundle['id']}\n\n"
            f"From {bundle['from']} to {bundle['to']}, {bundle['created_at']}. "
            f"Sender's request: {bundle.get('task') or '(none)'}\n\n"
            f"## Summary\n\n{summary_text(bundle)}\n\n"
            f"## Decisions (with rejected options)\n\n{decisions_text(bundle)}\n\n"
            f"## Evidence\n\n" + "\n".join(f"- {e['pointer']}: {e['note']}" for e in bundle.get("evidence", []))
            + "\n\nThe raw transcript excerpt is in excerpt.md next to this file.\n")
