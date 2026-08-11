"""
Purpose: Ask user a question during agent execution — via live io, or an explicit bounded email fallback
LLM-Note:
  Dependencies: imports from [hashlib, html, os, pathlib, re, secrets, threading, time, typing, dotenv, send_email, get_emails] | imported by [useful_tools/__init__.py]
  Data flow: agent calls ask_user tool → live io takes priority | without io, explicit opt-in resolves the configured owner → sends escaped HTML with a correlation tag → server-filtered inbox poll → returns the bound reply
  State/Effects: default no-io path returns immediately | opt-in path sends at most one rate-limited email, waits for bounded/cancellable time, marks the matched reply read | process-local pending/cooldown state stores only a hash of the owner address
  Integration: email fallback requires CONNECTONION_ASK_USER_EMAIL=1 and OWNER_EMAIL | never satisfies Host/ACP tool approval | agent parameter injected by tool_executor
"""

import hashlib
import html
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import List

from dotenv import dotenv_values

from ..core.interrupt import UserInterrupt
from .get_emails import SubjectFilterUnsupportedError, get_emails, mark_read
from .send_email import send_email

EMAIL_FALLBACK_ENV = "CONNECTONION_ASK_USER_EMAIL"
EMAIL_TIMEOUT_ENV = "CONNECTONION_ASK_USER_EMAIL_TIMEOUT_SECONDS"
EMAIL_POLL_ENV = "CONNECTONION_ASK_USER_EMAIL_POLL_SECONDS"
DEFAULT_REPLY_TIMEOUT = 900.0
DEFAULT_POLL_INTERVAL = 20.0
MAX_REPLY_TIMEOUT = 900.0
MAX_POLL_INTERVAL = 60.0
OWNER_COOLDOWN = 60.0
CANCEL_CHECK_INTERVAL = 0.25
MAX_INBOX_REQUEST_TIMEOUT = 2.0

_SENSITIVE_FIELD_TYPES = frozenset({
    "password", "secret", "token", "otp", "one-time-code", "hidden",
})
_SENSITIVE_TEXT = re.compile(
    r"\b(?:password|passcode|secret|otp|one[- ]time(?: password| code)?|"
    r"verification code|sms code|auth(?:entication|orization)? code|"
    r"recovery code|credential|access token|api key|private key)\b",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?:\b\d{4,8}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:sk-(?:proj-)?|rk_(?:live|test)_|glpat-|npm_|pypi-|hf_|"
    r"gh[pousr]_|xox[baprs]-|AKIA|AIza)[A-Za-z0-9_-]{8,}|"
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}\b)",
    re.IGNORECASE,
)
_OPAQUE_VALUE = re.compile(
    r"(?<![A-Za-z0-9_+/=-])"
    r"(?=[A-Za-z0-9_+/=-]{20,}(?![A-Za-z0-9_+/=-]))"
    r"(?=[A-Za-z0-9_+/=-]*[a-z])"
    r"(?=[A-Za-z0-9_+/=-]*[A-Z])"
    r"(?=[A-Za-z0-9_+/=-]*\d)"
    r"[A-Za-z0-9_+/=-]{20,}"
    r"(?![A-Za-z0-9_+/=-])"
)

# One address cannot receive a burst from concurrent agents in the same
# process. Store only a digest of the address; the configured contact itself
# does not become process-global application state.
_OWNER_STATE_LOCK = threading.Lock()
_PENDING_OWNER_KEYS = set()
_LAST_OWNER_ATTEMPT = {}

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
        # DD-043 preserves the historical immediate fail-closed default. An
        # email is an outward side effect and a blocking wait, so an owner must
        # opt in instead of acquiring both merely by defining an address.
        if not _email_fallback_enabled():
            return (
                NOT_ANSWERED
                + f" (Email fallback is disabled. Set {EMAIL_FALLBACK_ENV}=1 "
                "only when this application should send and wait for email.)"
            )
        return ask_owner_by_email(agent, question, options, multi_select, fields)

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


def ask_owner_by_email(agent, question, options, multi_select, fields) -> str:
    """Email a non-secret question to the configured contact and await its reply."""
    owner = _configured_owner_email()
    if not owner:
        return (
            NOT_ANSWERED
            + " (No OWNER_EMAIL is set, so there was no address to ask. Set "
            "OWNER_EMAIL in ~/.co/keys.env to let an unattended agent reach "
            "its owner by email.)"
        )

    if _is_cancelled(agent):
        return NOT_ANSWERED + " (The email reply wait was cancelled before sending.)"

    if _contains_sensitive_input(question, options, fields):
        return (
            NOT_ANSWERED
            + " (Email fallback refuses sensitive password, secret, token, "
            "OTP, or verification-code input because received mail is "
            "persisted. Use a dedicated secret channel.)"
        )

    # Email is a persistent, unauthenticated response channel. Keep its data
    # contract deliberately smaller than live IO: no arbitrary fields or
    # free-form answers, only a response drawn from the supplied choices.
    if fields or not options:
        return (
            NOT_ANSWERED
            + " (Email fallback only supports non-sensitive choice questions "
            "without free-form fields.)"
        )
    choice_error = _choice_configuration_error(options)
    if choice_error:
        return NOT_ANSWERED + f" ({choice_error})"

    try:
        reply_timeout = _bounded_seconds(
            EMAIL_TIMEOUT_ENV,
            DEFAULT_REPLY_TIMEOUT,
            minimum=1.0,
            maximum=MAX_REPLY_TIMEOUT,
        )
        poll_interval = _bounded_seconds(
            EMAIL_POLL_ENV,
            DEFAULT_POLL_INTERVAL,
            minimum=0.1,
            maximum=MAX_POLL_INTERVAL,
        )
    except ValueError as exc:
        return NOT_ANSWERED + f" ({exc})"

    owner_key, claim_error = _claim_owner_slot(owner)
    if claim_error:
        return NOT_ANSWERED + f" ({claim_error})"

    try:
        if _is_cancelled(agent):
            return NOT_ANSWERED + " (The email reply wait was cancelled before sending.)"

        # The sender alone is not enough: an unrelated owner email arriving
        # later must not become the answer, and simultaneous questions must not
        # cross. The high-entropy tag is also the server-side inbox filter.
        request_tag = f"[CO-ASK:{secrets.token_hex(16)}]"
        result = send_email(
            to=owner,
            subject=_subject(question, request_tag),
            message=_body(question, options, multi_select, request_tag),
        )
        if not result.get("success"):
            return (
                NOT_ANSWERED
                + f" (Tried to ask {owner} by email and the send failed: "
                f"{result.get('error')})"
            )

        deadline = time.monotonic() + reply_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                emails = get_emails(
                    last=10,
                    subject_contains=request_tag,
                    request_timeout=min(MAX_INBOX_REQUEST_TIMEOUT, remaining),
                )
            except SubjectFilterUnsupportedError:
                return (
                    NOT_ANSWERED
                    + " (The email backend did not confirm server-side subject "
                    "filtering. Upgrade the backend before using this fallback.)"
                )
            except Exception:
                # Inbox outages are not answers. Keep the bounded wait alive
                # for a transient failure, then return the fail-closed result.
                emails = []
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
                answer = _validated_choice_answer(
                    _strip_quoted(str(email.get("message", ""))),
                    options,
                    multi_select,
                )
                try:
                    mark_read(str(email.get("id", "")))
                except Exception:
                    # The correlated answer is already in hand. Read-state
                    # cleanup must not discard it or cause an outward retry.
                    pass
                if not answer:
                    return (
                        NOT_ANSWERED
                        + " (The correlated email reply did not contain only "
                        "the offered choice or choices.)"
                    )
                return answer

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if not _wait_for_poll(agent, min(poll_interval, remaining)):
                return NOT_ANSWERED + " (The email reply wait was cancelled.)"

        return (
            NOT_ANSWERED
            + f" (Asked {owner} by email and waited {reply_timeout:g} "
            "seconds with no reply.)"
        )
    finally:
        _release_owner_slot(owner_key)


def _body(question, options, multi_select, request_tag) -> str:
    """Build escaped HTML for the backend's actual body contract."""
    lines = [question, ""]
    if options:
        lines.append("Choose one:" if not multi_select else "Choose any that apply:")
        lines += [f"  {index}. {option}" for index, option in enumerate(options, 1)]
        lines.append("")
    lines.append(
        "Reply with the choice number"
        + ("s separated by commas" if multi_select else "")
        + ", and keep the reference in the "
        f"subject: {request_tag}"
    )
    lines.extend([
        "",
        "This reply answers an ask_user question. It does not grant a Host/ACP "
        "tool permission or bypass an approval policy.",
    ])
    escaped = html.escape("\n".join(lines), quote=True)
    return (
        '<div style="font-family:system-ui,sans-serif">'
        '<pre style="white-space:pre-wrap;font:inherit">'
        f"{escaped}</pre></div>"
    )


def _subject(question: str, request_tag: str) -> str:
    """A single safe header line; later lines can never become mail headers."""
    first_line = re.split(r"[\r\n]", str(question), maxsplit=1)[0]
    printable = "".join(character for character in first_line if character.isprintable())
    summary = " ".join(printable.split())[:60]
    return f"{request_tag} Your agent is asking: {summary}"


def _email_fallback_enabled() -> bool:
    return os.getenv(EMAIL_FALLBACK_ENV, "").strip().casefold() in {
        "1", "true", "yes", "on",
    }


def _configured_owner_email() -> str:
    """Global owner config wins over project-loaded ambient configuration."""
    global_file = Path.home() / ".co" / "keys.env"
    global_owner = ""
    if global_file.is_file():
        try:
            global_owner = str(
                dotenv_values(global_file, interpolate=False).get("OWNER_EMAIL") or ""
            ).strip()
        except OSError:
            global_owner = ""
    return global_owner or (os.getenv("OWNER_EMAIL") or "").strip()


def _contains_sensitive_input(question: str, options, fields) -> bool:
    """Persistent mail is not a password, token, or one-time-code channel."""
    outbound_text = "\n".join([str(question), *(str(option) for option in options or [])])
    if (
        _SENSITIVE_TEXT.search(outbound_text)
        or _SECRET_VALUE.search(outbound_text)
        or _OPAQUE_VALUE.search(outbound_text)
    ):
        return True
    for field in fields or []:
        if not isinstance(field, dict):
            continue
        field_type = str(field.get("type", "")).strip().casefold()
        if field_type in _SENSITIVE_FIELD_TYPES:
            return True
        metadata = " ".join(
            str(field.get(key, ""))
            for key in ("name", "label", "autocomplete")
        )
        if _SENSITIVE_TEXT.search(metadata):
            return True
    return False


def _choice_configuration_error(options) -> str:
    """Reject ambiguous or oversized choice sets before creating an email."""
    if len(options) > 20:
        return "Email fallback supports at most 20 choices."
    normalized = []
    for option in options:
        label = str(option).strip()
        if not label or len(label) > 200:
            return "Each email choice must contain 1-200 characters."
        if any(ord(character) < 32 or ord(character) == 127 for character in label):
            return "Email choices cannot contain control characters."
        normalized.append(label.casefold())
    if len(normalized) != len(set(normalized)):
        return "Email choices must be unique ignoring case."
    return ""


def _validated_choice_answer(answer: str, options, multi_select: bool) -> str:
    """Map stable numeric reply IDs to choices; reject all free-form content."""
    if len(answer) > 128:
        return ""
    pattern = (
        r"\s*\d{1,2}(?:\s*,\s*\d{1,2})*\s*"
        if multi_select
        else r"\s*\d{1,2}\s*"
    )
    if not re.fullmatch(pattern, answer):
        return ""
    values = re.findall(r"\d{1,2}", answer)
    if len(values) > len(options):
        return ""
    indexes = [int(value) for value in values]
    if any(index < 1 or index > len(options) for index in indexes):
        return ""
    indexes = list(dict.fromkeys(indexes))
    return ",".join(str(options[index - 1]).strip() for index in indexes)


def _bounded_seconds(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = default if raw is None else float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g} seconds")
    return value


def _owner_key(owner: str) -> bytes:
    return hashlib.sha256(owner.strip().casefold().encode("utf-8")).digest()


def _claim_owner_slot(owner: str):
    key = _owner_key(owner)
    now = time.monotonic()
    with _OWNER_STATE_LOCK:
        if key in _PENDING_OWNER_KEYS:
            return key, "An email question is already pending for this owner."
        last_attempt = _LAST_OWNER_ATTEMPT.get(key)
        if last_attempt is not None and now - last_attempt < OWNER_COOLDOWN:
            return key, "The owner email question cooldown is still active."
        _PENDING_OWNER_KEYS.add(key)
        _LAST_OWNER_ATTEMPT[key] = now
    return key, None


def _release_owner_slot(key: bytes) -> None:
    with _OWNER_STATE_LOCK:
        _PENDING_OWNER_KEYS.discard(key)


def _wait_for_poll(agent, seconds: float) -> bool:
    """Sleep in short increments so another thread can cancel the agent."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _is_cancelled(agent):
            return False
        remaining = deadline - time.monotonic()
        time.sleep(min(CANCEL_CHECK_INTERVAL, max(0.0, remaining)))
    return not _is_cancelled(agent)


def _is_cancelled(agent) -> bool:
    if bool(getattr(agent, "current_session", {}).get("stop_signal")):
        return True
    checker = getattr(getattr(agent, "io", None), "is_cancelled", None)
    return bool(checker()) if callable(checker) else False


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
