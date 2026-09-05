"""
Purpose: Telegram as a mailbox — getUpdates long polling writes files, replies go through sendMessage
LLM-Note:
  Dependencies: imports from [os, time, requests, listen/mailbox.py, useful_tools/telegram.py (API, NO_TOKEN)] | imported by [listen/__init__.py via provider()] | tested by [tests/unit/test_listen_telegram.py]
  Data flow: run(mailbox) → GET /bot<token>/getUpdates?offset&timeout=50 → to_message() → mailbox.deliver() → offset = update_id + 1 | send() → POST /bot<token>/sendMessage → message id
  State/Effects: reads TELEGRAM_BOT_TOKEN, the same token `co telegram send` uses | one outbound long poll at a time, so no port is opened | the offset lives only in memory: Telegram keeps unacknowledged updates for 24 hours, and re-randomises ids after a week idle, so a persisted cursor would be wrong more often than useful
  Integration: message ids are "<chat>.<message_id>" because Telegram's message_id is only unique within a chat; reply parses that back | a group message counts as mentioned when it @s the bot's username or replies to one of its messages; in a private chat everything is
  Errors: check() names the missing token and the BotFather steps | a transport error in the poll loop is logged and retried with backoff up to 30 s | send() raises RuntimeError with Telegram's own description, minus the token, after honouring one retry_after
"""

import os
import time
from typing import Optional

import requests

from ..useful_tools.telegram import API, NO_TOKEN
from .mailbox import Mailbox, Message, iso_utc

# Long poll length. Telegram holds the request open this long when nothing
# is happening; 50 keeps well under the usual 60 s proxy idle limit.
POLL_SECONDS = 50

_MEDIA = ("photo", "document", "voice", "audio", "video", "sticker", "animation", "location", "contact")


class Telegram:
    """One bot, the user's own, from @BotFather."""

    name = "telegram"

    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._me: Optional[dict] = None

    # ---- setup -------------------------------------------------------------

    def missing(self) -> list:
        return [] if self.token else [NO_TOKEN]

    def check(self) -> list:
        problems = self.missing()
        if problems:
            return problems
        try:
            self.me()
        except Exception as exc:
            problems.append(f"Telegram did not accept the token: {exc}")
        return problems

    def me(self) -> dict:
        """The bot's own id and username, for telling an @mention of us from
        one of someone else."""
        result = self._call("getMe", {}, method_kind="get")
        self._me = {"id": result.get("id"), "username": result.get("username")}
        return self._me

    # ---- inbound -----------------------------------------------------------

    def run(self, mailbox: Mailbox, *, raw: bool = False) -> None:
        """Long-poll forever, writing every message. Blocks."""
        try:
            me = self.me()
            mailbox.log(f"connected as @{me.get('username')}")
        except Exception as exc:
            mailbox.log(f"getMe failed: {exc}")
        offset = None
        delay = 1.0
        while True:
            try:
                updates = self._call(
                    "getUpdates",
                    {"timeout": POLL_SECONDS, "offset": offset, "allowed_updates": ["message"]},
                    timeout=POLL_SECONDS + 10,
                )
                delay = 1.0
            except Exception as exc:
                mailbox.log(f"getUpdates failed: {exc}; retrying in {delay:.0f}s")
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            for update in updates:
                # A redelivered older update must not move the cursor back.
                offset = max(offset or 0, int(update.get("update_id", 0)) + 1)
                message = self.to_message(update, raw=raw)
                if message is None:
                    continue
                if mailbox.deliver(message, raw=raw):
                    mailbox.log(f"received {message.id} chat={message.chat} sender={message.sender}")
                else:
                    mailbox.log(f"duplicate {message.id} dropped")

    def to_message(self, update: dict, *, raw: bool = False) -> Optional[Message]:
        """One update as a Message, or None when it is not a person talking
        to us (bots, channel posts, edits, service messages)."""
        m = update.get("message")
        if not isinstance(m, dict):
            return None
        sender = m.get("from") or {}
        chat = m.get("chat") or {}
        if not sender or sender.get("is_bot") or "id" not in chat:
            return None
        text = m.get("text") or m.get("caption") or ""
        if not text:
            kind = next((k for k in _MEDIA if k in m), None)
            if kind is None:
                return None
            text = f"[{kind}]"
        private = chat.get("type") == "private"
        return Message(
            id=f"{chat['id']}.{m.get('message_id')}",
            chat=str(chat["id"]),
            thread=str(m["message_thread_id"]) if m.get("is_topic_message") and m.get("message_thread_id") else None,
            sender=str(sender.get("id", "")),
            text=text,
            mentioned=True if private else self._mentions_us(m, text),
            at=_iso(m.get("date")),
            raw=update if raw else None,
        )

    def _mentions_us(self, m: dict, text: str) -> bool:
        me = self._me or {}
        replied = (m.get("reply_to_message") or {}).get("from") or {}
        if me.get("id") and replied.get("id") == me["id"]:
            return True
        # Telegram counts entity offsets in UTF-16 code units, so an emoji
        # before the @ is two units, not one; slice the UTF-16 form.
        utf16 = text.encode("utf-16-le")
        handles = []
        for entity in m.get("entities") or m.get("caption_entities") or []:
            if entity.get("type") in ("mention", "bot_command"):
                offset, length = int(entity.get("offset", 0)), int(entity.get("length", 0))
                handles.append(utf16[2 * offset:2 * (offset + length)].decode("utf-16-le", "replace"))
        if not me.get("username"):
            return any(h.startswith("@") for h in handles)
        needle = f"@{me['username']}".lower()
        return any(h.lower() == needle or h.lower().endswith(needle) for h in handles)

    # ---- outbound ----------------------------------------------------------

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None) -> str:
        """Send text to a chat, quoting a received message when reply_to is
        one of our "<chat>.<message_id>" ids. Returns the new message id."""
        body = {"chat_id": chat, "text": text}
        if reply_to and "." in reply_to:
            body["reply_parameters"] = {"message_id": int(reply_to.rsplit(".", 1)[1])}
        result = self._call("sendMessage", body)
        return f"{chat}.{result.get('message_id')}"

    # ---- REST -------------------------------------------------------------

    def _call(self, method: str, body: dict, *, timeout: float = 15, method_kind: str = "post") -> dict:
        url = f"{API}/bot{self.token}/{method}"
        retried = False
        while True:
            try:
                if method_kind == "get":
                    response = requests.get(url, timeout=timeout)
                else:
                    response = requests.post(url, json=body, timeout=timeout)
            except requests.RequestException as exc:
                # The URL carries the token; the class name is the diagnosis.
                raise RuntimeError(f"Telegram request failed ({type(exc).__name__})") from None
            try:
                payload = response.json()
            except ValueError:
                raise RuntimeError(f"Telegram returned HTTP {response.status_code} without JSON")
            if payload.get("ok"):
                return payload.get("result")
            retry_after = (payload.get("parameters") or {}).get("retry_after")
            if response.status_code == 429 and retry_after and not retried:
                retried = True  # honour Telegram's own wait once, then report
                time.sleep(float(retry_after))
                continue
            description = str(payload.get("description", f"HTTP {response.status_code}"))
            raise RuntimeError(f"Telegram refused: {description.replace(self.token, '[redacted]')}")


def _iso(date) -> str:
    try:
        return iso_utc(int(date))
    except (TypeError, ValueError):
        return iso_utc()
