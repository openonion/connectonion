"""
Purpose: Ask user a question during agent execution — via io when someone is connected, by email when nobody is
LLM-Note:
  Dependencies: imports from [os, time, typing, send_email, get_emails] | imported by [useful_tools/__init__.py]
  Data flow: agent calls ask_user tool → if agent.io: send ask_user event → wait for response | else: email OWNER_EMAIL → poll agent inbox for a reply → return its text
  State/Effects: blocks until user responds via io, or up to REPLY_TIMEOUT seconds while polling the inbox | sends one email | marks the reply read
  Integration: requires agent.io OR the OWNER_EMAIL env var | agent parameter injected by tool_executor
"""

import os
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
    owner = os.getenv("OWNER_EMAIL")
    if not owner:
        return (
            NOT_ANSWERED
            + " (No OWNER_EMAIL is set, so there was no address to ask. Set "
            "OWNER_EMAIL in ~/.co/keys.env to let an unattended agent reach its owner by email.)"
        )

    # Ids present before we ask, so a reply is anything from the owner that is
    # not one of them. Ids beat timestamps here: no clock skew, no parsing.
    already_seen = {email["id"] for email in get_emails(last=20) if email["from"] == owner}

    result = send_email(to=owner, subject=f"Your agent is asking: {question[:60]}",
                        message=_body(question, options, multi_select, fields))
    if not result.get("success"):
        return NOT_ANSWERED + f" (Tried to ask {owner} by email and the send failed: {result.get('error')})"

    deadline = time.time() + REPLY_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        for email in get_emails(last=20):
            if email["from"] == owner and email["id"] not in already_seen:
                mark_read(email["id"])
                return _strip_quoted(email["message"])

    return (
        NOT_ANSWERED
        + f" (Asked {owner} by email and waited {REPLY_TIMEOUT // 60} minutes with no reply.)"
    )


def _body(question, options, multi_select, fields) -> str:
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
    lines.append("Reply to this email with your answer. Anything you write becomes the answer.")
    return "\n".join(lines)


def _strip_quoted(reply: str) -> str:
    """Just what the human typed — not our own question quoted back at us."""
    answer = []
    for line in reply.splitlines():
        if line.startswith(">") or line.startswith("On ") and line.rstrip().endswith("wrote:"):
            break
        answer.append(line)
    return "\n".join(answer).strip()
