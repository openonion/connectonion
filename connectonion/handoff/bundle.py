"""The handoff bundle: what crosses from one person's agent to another's.

A bundle is one JSON document whose fields are the handoff skill's brief sections
(Task / Where it stands / Decided / Rejected / Open questions / Code and
references), plus the raw transcript excerpt. Task, state and open questions are
what a person reads first; the rest is there on request. `content_hash` covers everything the sender saw in the preview,
so the copy that arrives can be checked against the one that was approved.
"""

import base64
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

FORMAT = "co-handoff/2"  # /1 was the pre-release shape (goal/decisions); never shipped
BEGIN = "----- BEGIN CO HANDOFF BUNDLE -----"
END = "----- END CO HANDOFF BUNDLE -----"


class Decided(BaseModel):
    decision: str = Field(description="What was decided")
    why: str = Field(description="The reason, as stated in the conversation")


class Rejected(BaseModel):
    option: str = Field(description="The alternative that was dropped, named so a stranger knows what it is")
    why_not: str = Field(description="The reason given in the conversation for dropping it")


class Reference(BaseModel):
    reference: str = Field(description="Repository URL, branch, commit, PR, issue, or a file by its path in the repository")
    note: str = Field(description="What it is or shows")


class Draft(BaseModel):
    """The brief, in the same sections as the handoff skill (Codex's compaction structure)."""
    title: str = Field(description="The task in one line")
    task: str = Field(description="What to do, and what 'done' means")
    may_do: list[str] = Field(default_factory=list, description="What the recipient may do, only as the sender stated; empty if not discussed")
    where_it_stands: str = Field(description="What is finished, what is in progress, what was tried")
    decided: list[Decided] = Field(default_factory=list)
    rejected: list[Rejected] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list, description="Each undecided question, and who is waiting on it")
    references: list[Reference] = Field(default_factory=list)


DRAFT_PROMPT = """You write a handoff brief so a colleague's coding agent can continue a task
without the sender rewriting the background. Use ONLY the conversation below.

- Write only what the conversation established. If something is uncertain, say so.
- Readable on its own: "the file", "option B" and "what we said" mean nothing to a
  stranger, so name the thing ("option B (localStorage)").
- Record every decision with its reason, and every rejected alternative with the
  reason it was rejected. The recipient will ask "why not X?".
- Proposals that were not settled go in open_questions.
- References are concrete: repository, branch, commit, PR, issue, or a file by its
  path inside the repository. Never a path under a home directory (/Users/..., /home/...,
  ~/...), never an internal hostname or IP, never invented.
- may_do lists only permissions the sender stated; leave it empty otherwise.
- Never copy a credential, token, password, key or invite code.
- A "summary" turn is the client's own summary of earlier conversation; "earlier"
  turns are the user's messages kept from before a compaction.

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
}


def find_private(bundle: dict) -> list[str]:
    """Private paths in the bundle, as 'field: match' (deduplicated)."""
    hits = []
    for field, text in _strings(bundle):
        for pattern in PRIVATE_PATTERNS.values():
            hits += [f"{field}: {m}" for m in re.findall(pattern, text)]
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

def to_mail(bundle: dict) -> tuple[str, str]:
    """(subject, body). The body opens with the readable summary; the bundle follows, base64 so no mail system rewrites it."""
    subject = f"[co handoff] {bundle['id']}: {_one_line(bundle['title'], 80)}"
    encoded = base64.b64encode(json.dumps(bundle, ensure_ascii=False).encode()).decode()
    wrapped = "\n".join(encoded[i:i + 76] for i in range(0, len(encoded), 76))
    body = (f"{brief_markdown(bundle)}\n"
            f"Continue this with your AI: run co handoff inbox, then co handoff open {bundle['id']}.\n"
            f"Not using ConnectOnion? Reply to this email; your questions reach the sender.\n\n"
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


# ---- what a person reads: one format everywhere ----

def task_section(bundle: dict) -> str:
    lines = [bundle["task"]]
    lines.append("You may: " + ("; ".join(bundle["may_do"]) if bundle.get("may_do") else "not stated by the sender"))
    return "\n\n".join(lines)


def decided_text(bundle: dict) -> str:
    return "\n".join(f"- {d['decision']} (why: {d['why']})" for d in bundle.get("decided", [])) or "- none recorded"


def rejected_text(bundle: dict) -> str:
    return "\n".join(f"- {r['option']}: {r['why_not']}" for r in bundle.get("rejected", [])) or "- none recorded"


def questions_text(bundle: dict) -> str:
    return "\n".join(f"- {q}" for q in bundle.get("open_questions", [])) or "- none"


def references_text(bundle: dict) -> str:
    lines = [f"- {r['reference']}: {r['note']}" for r in bundle.get("references", [])]
    source = bundle.get("source", {})
    lines.append(f"- Transcript excerpt: {len(bundle.get('excerpt', []))} turns of the sender's "
                 f"{source.get('kind', '?')} session{' (compacted; earlier part as kept by the client)' if source.get('compacted') else ''}")
    return "\n".join(lines)


def excerpt_text(bundle: dict) -> str:
    return "\n\n".join(f"[{t['role']}] {t['text']}" for t in bundle.get("excerpt", []))


def header(bundle: dict) -> str:
    return (f"# Handoff: {bundle['title']}\n"
            f"From: {bundle['from']} · To: {bundle['to']} · {bundle['created_at'][:10]} · {bundle['id']}")


def summary_text(bundle: dict) -> str:
    """The first screen: task, where it stands, open questions, and what else there is."""
    return (f"{header(bundle)}\n\n## Task\n{task_section(bundle)}\n\n"
            f"## Where it stands\n{bundle['where_it_stands']}\n\n## Open questions\n{questions_text(bundle)}\n\n"
            f"{_count(bundle.get('decided'), 'decision')}, {_count(bundle.get('rejected'), 'rejected option')}, "
            f"{_count(bundle.get('references'), 'reference')}, {len(bundle.get('excerpt', []))}-turn excerpt.")


def brief_markdown(bundle: dict) -> str:
    """The whole brief in the handoff skill's sections: preview, mail body and HANDOFF.md."""
    return (f"{header(bundle)}\n\n"
            f"## Task\n{task_section(bundle)}\n\n"
            f"## Where it stands\n{bundle['where_it_stands']}\n\n"
            f"## Decided\n{decided_text(bundle)}\n\n"
            f"## Rejected\n{rejected_text(bundle)}\n\n"
            f"## Open questions\n{questions_text(bundle)}\n\n"
            f"## Code and references\n{references_text(bundle)}\n")


def _count(items, noun: str) -> str:
    n = len(items or [])
    return f"{n} {noun}" + ("" if n == 1 else "s")
