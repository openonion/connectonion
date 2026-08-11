"""
Purpose: Ask user a question during agent execution — via io when someone is connected, by email when nobody is
LLM-Note:
  Dependencies: imports from [os, secrets, time, typing, send_email, get_emails] | imported by [useful_tools/__init__.py]
  Data flow: agent calls ask_user tool → if agent.io: send ask_user event → wait for response | else: email OWNER_EMAIL → poll agent inbox for a reply → return its text
  State/Effects: blocks until user responds via io, or up to REPLY_TIMEOUT seconds while polling the inbox | sends one email | marks the reply read
  Integration: requires agent.io OR the OWNER_EMAIL env var | agent parameter injected by tool_executor
"""

import os
import secrets
import time
from typing import List

from ..core.interrupt import UserInterrupt
from .send_email import send_email
from .get_emails import get_emails, mark_read


# An unattended agent can afford to wait a while — the alternative is dying. But
# it must not wait forever: a run that hangs overnight is worse than one that
# stops and reports.
REPLY_TIMEOUT = 900       # seconds to wait for an emailed reply
POLL_INTERVAL = 20        # seconds between inbox checks

NOT_ANSWERED = (
    "NOT ANSWERED — nobody is available to reply. This is not approval. "
    "Do not send, post, publish, delete, overwrite, deploy, or spend "
    "anything that this question was gating. Continue with any part of "
    "the task that does not depend on the answer, then end your turn by "
    "stating the question and what you would have done, so the user can "
    "decide."
)


def ask_user(
    agent,
    question: str,
    options: List[str],
    multi_select: bool = False,
    fields: List[dict] = None
) -> str:
    """Ask the user a question and wait for their response.

    Args:
        question: The question to ask the user
        options: List of choices for the user to select from
        multi_select: If True, user can select multiple options
        fields: Optional structured inputs to collect, e.g.
            [{"name": "username", "label": "Username", "type": "text"},
             {"name": "password", "label": "Password", "type": "password"}]

    Returns:
        The user's answer (or comma-separated answers if multi_select)
    """
    if not agent.io:
        # One-shot mode (co ai "prompt", and every deployed agent) has nobody
        # watching a socket — but the owner still has an inbox, and the agent
        # has an address of its own to write from. Ask there before giving up.
        return ask_owner_by_email(question, options, multi_select, fields)

    event = {
        "type": "ask_user",
        "question": question,
        "options": options,
        "multi_select": multi_select,
    }
    if fields:
        event["fields"] = fields
    agent.io.send(event)
    response = agent.io.receive()
    if response.get("type") == "INTERRUPT":
        agent.current_session["stop_signal"] = "Interrupted by user"
        raise UserInterrupt()
    return response.get("answer", "")


def ask_owner_by_email(question, options, multi_select, fields) -> str:
    """Email the question to the owner and wait for a reply in the agent's inbox."""
    owner = (os.getenv("OWNER_EMAIL") or "").strip()
    if not owner:
        return (
            NOT_ANSWERED
            + " (No OWNER_EMAIL is set, so there was no address to ask. Set "
            "OWNER_EMAIL in ~/.co/keys.env to let an unattended agent reach "
            "its owner by email.)"
        )

    # The sender alone is not enough: an unrelated owner email arriving after
    # the question must never become an approval, and concurrent questions must
    # not consume one another's replies. A high-entropy subject tag binds the
    # reply to exactly this wait without relying on clocks or shared state.
    request_tag = f"[CO-ASK:{secrets.token_hex(16)}]"
    result = send_email(
        to=owner,
        subject=f"{request_tag} Your agent is asking: {question[:60]}",
        message=_body(question, options, multi_select, fields, request_tag),
    )
    if not result.get("success"):
        return (
            NOT_ANSWERED
            + f" (Tried to ask {owner} by email and the send failed: "
            f"{result.get('error')})"
        )

    deadline = time.monotonic() + REPLY_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
        try:
            emails = get_emails(last=20)
        except Exception:
            # Inbox outages are not answers. Keep the bounded wait alive for a
            # transient failure, then return the ordinary fail-closed result.
            continue
        for email in emails:
            if not isinstance(email, dict):
                continue
            sender = str(email.get("from", "")).strip().casefold()
            subject = str(email.get("subject", "")).casefold()
            if (
                sender != owner.casefold()
                or request_tag.casefold() not in subject
            ):
                continue
            answer = _strip_quoted(str(email.get("message", "")))
            try:
                mark_read(str(email.get("id", "")))
            except Exception:
                # The correlated answer is already in hand. Read-state cleanup
                # is useful but must not discard it or cause an outward retry.
                pass
            if not answer:
                return (
                    NOT_ANSWERED
                    + " (The correlated email reply contained no answer.)"
                )
            return answer

    return (
        NOT_ANSWERED
        + f" (Asked {owner} by email and waited {REPLY_TIMEOUT // 60} "
        "minutes with no reply.)"
    )


def _body(question, options, multi_select, fields, request_tag) -> str:
    """The email a human reads. Plain text, answerable by hitting reply."""
    lines = [question, ""]
    if options:
        lines.append("Choose one:" if not multi_select else "Choose any that apply:")
        lines += [f"  - {option}" for option in options]
        lines.append("")
    if fields:
        lines.append("Please include:")
        lines += [f"  - {field.get('label', field['name'])}" for field in fields]
        lines.append("")
    lines.append(
        "Reply to this email with your answer and keep the reference in the "
        f"subject: {request_tag}"
    )
    return "\n".join(lines)


def _strip_quoted(reply: str) -> str:
    """Just what the human typed — not our own question quoted back at us."""
    answer = []
    for line in reply.splitlines():
        if line.startswith(">") or (
            line.startswith("On ") and line.rstrip().endswith("wrote:")
        ):
            break
        answer.append(line)
    return "\n".join(answer).strip()
