"""
Purpose: Telegram as an inbox — getUpdates long polling writes files, replies go out through sendMessage
LLM-Note:
  Dependencies: imports from [os, time, requests, inbox/__init__.py (ListenerStopped), inbox/store.py, useful_tools/telegram.py (API, NO_TOKEN)] | imported by [inbox/__init__.py via provider()] | tested by [tests/unit/test_inbox_telegram.py]
  Data flow: run(inbox) → POST /bot<token>/getUpdates {offset, timeout=50} → to_message() → inbox.deliver() → offset = update_id + 1 | send() → POST /bot<token>/sendMessage → "<chat>.<message_id>"
  State/Effects: reads TELEGRAM_BOT_TOKEN, the same token `co telegram send` uses | one outbound long poll at a time, so no port is opened | the offset lives only in memory (see run) | writes connection.json on every transition so `check` can report the real state
  Integration: message ids are "<chat>.<message_id>" because Telegram's message_id is only unique within a chat; send() parses that back for reply_parameters | a group message counts as mentioned when it @s the bot's username, is a /command@bot, or replies to one of the bot's own messages; in a private chat everything is
  Errors: check() names the missing token and the BotFather steps | a transport error in the poll loop is logged and retried with backoff up to 30 s | a revoked token or a second poller ends the listener with ListenerStopped, because no restart fixes either | send() raises RuntimeError with Telegram's own description, minus the token, after honouring one retry_after
"""

import os
import time
from typing import Optional

import requests

from ..useful_tools.telegram import API, NO_TOKEN
from . import ListenerStopped
from .store import Inbox, Message, iso_utc

# Long poll length. Telegram holds the request open this long when nothing is
# happening; 50 keeps well under the usual 60 s proxy idle limit.
POLL_SECONDS = 50

# What a non-text message is called, in the order Telegram's own clients would
# describe it. The name becomes `kind` and, bracketed, the text.
_MEDIA = ("photo", "document", "voice", "audio", "video", "video_note", "sticker",
          "animation", "location", "contact", "poll")

# The answers no amount of polling recovers from. 401: the token was revoked in
# @BotFather. 404: the token is not a token (Telegram answers a malformed one
# with "Not Found"). 409: a webhook is set, or another process is polling with
# this token — Telegram delivers each update to exactly one of them, so two
# listeners would each see a random half of the conversation.
_STOPPING = {401, 404, 409}


class Refused(RuntimeError):
    """Telegram answered and said no. Carries the HTTP status so the poll loop
    can tell "stop, a person has to act" from "try again in a second"."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


class Telegram:
    """One bot, the user's own, from @BotFather."""

    name = "telegram"
    # For `co telegram edit` and friends: the endpoints exist, nobody has wired
    # them up yet, and the refusal should say so in Telegram's words.
    unwired = {
        "edit": "Telegram has the endpoint for it (editMessageText)",
        "delete": "Telegram has the endpoint for it (deleteMessage)",
        "react": "Telegram has the endpoint for it (setMessageReaction)",
    }

    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._me: Optional[dict] = None

    # ---- setup -------------------------------------------------------------

    def missing(self) -> list:
        """The one thing Telegram needs, with the fix. The sentence is the one
        `co telegram send` already prints, so there is one set of instructions."""
        return [] if self.token else [NO_TOKEN]

    def check(self) -> list:
        problems = self.missing()
        if problems:
            return problems
        try:
            self.me()
        except Exception as exc:  # Telegram's own words are the diagnosis
            problems.append(f"Telegram did not accept the token: {exc}. "
                            f"Next: copy the token again from @BotFather into ~/.co/keys.env")
        return problems

    def me(self) -> dict:
        """The bot's own id and username, for telling an @mention of us from
        an @mention of somebody else."""
        result = self._call("getMe", {})
        self._me = {"id": result.get("id"), "username": result.get("username")}
        return self._me

    # ---- inbound -----------------------------------------------------------

    def run(self, inbox: Inbox, *, raw: bool = False) -> None:
        """Long-poll forever, writing every message. Blocks.

        The offset stays in memory on purpose. Telegram keeps unacknowledged
        updates for a day, and after a week with no updates it picks the next
        update_id at random, so a persisted cursor is right for a busy bot and
        wrong for a quiet one — and a quiet bot is the one whose owner would
        not notice. A restart asks for everything Telegram still holds and the
        inbox's own dedup drops what it has already logged: one mechanism, not
        two that disagree.
        """
        try:
            me = self.me()
            inbox.log(f"connected as @{me.get('username')}")
        except Exception as exc:
            if isinstance(exc, Refused) and exc.status in _STOPPING:
                self._stop(inbox, exc)
            # A bad minute, not a bad token: the poll below retries on its own,
            # and only the @mention check runs without our username until then.
            inbox.log(f"getMe failed: {exc}")
        account = f"@{(self._me or {}).get('username') or 'unknown'}"
        offset = None
        delay = 1.0
        connected = False
        while True:
            try:
                updates = self._call(
                    "getUpdates",
                    {"timeout": POLL_SECONDS, "offset": offset, "allowed_updates": ["message"]},
                    timeout=POLL_SECONDS + 10,
                )
            except RuntimeError as exc:  # Refused is one
                if isinstance(exc, Refused) and exc.status in _STOPPING:
                    self._stop(inbox, exc)
                inbox.log(f"getUpdates failed: {exc}; retrying in {delay:.0f}s")
                if connected:
                    inbox.record_connection("disconnected", account=account, reason=str(exc))
                    connected = False
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
                continue
            delay = 1.0
            if not connected:
                # Written on the transition, not every poll: check wants "the
                # socket is up, since when", not "something ran recently".
                inbox.record_connection("connected", account=account)
                connected = True
            for update in updates or []:
                # A redelivered older update must not move the cursor back.
                offset = max(offset or 0, int(update.get("update_id", 0)) + 1)
                self._deliver(inbox, update, raw)

    def _deliver(self, inbox: Inbox, update: dict, raw: bool) -> None:
        try:
            message = self.to_message(update, raw=raw)
        except Exception as exc:
            # One update we cannot read is one log line. Raising here would
            # leave the offset where it is and fetch the same update forever.
            inbox.log(f"update not understood ({type(exc).__name__}: {exc}); skipped")
            return
        if message is None:
            return
        # deliver() is left to raise on a full or unwritable disk. The offset
        # has already moved past this update, so the listener dies loudly
        # rather than acknowledging a message it could not keep.
        if inbox.deliver(message, raw=raw):
            inbox.log(f"received {message.id} chat={message.chat} sender={message.sender}")
        else:
            inbox.log(f"duplicate {message.id} dropped")

    def _stop(self, inbox: Inbox, exc: "Refused") -> None:
        reasons = {
            401: "Telegram no longer accepts this token; it was revoked or regenerated. "
                 "Next: copy the current token from @BotFather into ~/.co/keys.env",
            404: "Telegram does not recognise TELEGRAM_BOT_TOKEN as a bot token. "
                 "Next: copy it again from @BotFather into ~/.co/keys.env",
            409: "Telegram will not hand this bot's updates to two readers: a webhook is set, "
                 "or another `co telegram listen` is polling with the same token. "
                 "Stop the other one (or remove the webhook with deleteWebhook) and start again. "
                 "Next: co telegram listen",
        }
        reason = f"{exc}. {reasons.get(exc.status, '')}".strip()
        inbox.record_connection("stopped", reason=str(exc))
        inbox.log(f"stopped: {exc}")
        raise ListenerStopped(reason) from None

    def to_message(self, update: dict, *, raw: bool = False) -> Optional[Message]:
        """One update as a Message, or None when it is not a person talking to
        us (bots, channel posts, edits, service messages like "X joined")."""
        m = update.get("message")
        if not isinstance(m, dict):
            return None
        sender = m.get("from") or {}
        chat = m.get("chat") or {}
        if not sender or sender.get("is_bot") or "id" not in chat:
            return None
        text = m.get("text") or m.get("caption") or ""
        kind = "text"
        media = next((k for k in _MEDIA if k in m), None)
        if media:
            kind = media
            # A captioned photo keeps its caption as the text; an uncaptioned
            # one is named, so it is never an empty message.
            text = text or f"[{media}]"
        if not text:
            return None
        private = chat.get("type") == "private"
        topic = m.get("message_thread_id") if m.get("is_topic_message") else None
        return Message(
            id=_message_id(chat["id"], m.get("message_id")),
            chat=str(chat["id"]),
            thread=str(topic) if topic else None,
            sender=str(sender.get("id", "")),
            sender_name=_name_of(sender),
            text=text,
            kind=kind,
            quoted=self._quoted(m),
            mentioned=True if private else self._mentions_us(m, text),
            at=_iso(m.get("date")),
            raw=update if raw else None,
        )

    def _quoted(self, m: dict) -> Optional[dict]:
        """The message this one replies to, with `from_me` — the field that
        tells "replied to the bot" from "replied to somebody in the group".

        A reply in a forum topic arrives with reply_to_message set to the
        topic's opening service message; that is not a reply anyone typed, so
        it is not quoted."""
        replied = m.get("reply_to_message")
        if not isinstance(replied, dict) or replied.get("forum_topic_created"):
            return None
        author = replied.get("from") or {}
        me = (self._me or {}).get("id")
        return {
            "id": _message_id((m.get("chat") or {}).get("id"), replied.get("message_id")),
            "sender": str(author.get("id", "")),
            "text": replied.get("text") or replied.get("caption") or "",
            "kind": next((k for k in _MEDIA if k in replied), "text"),
            "from_me": bool(me) and author.get("id") == me,
        }

    def _mentions_us(self, m: dict, text: str) -> bool:
        me = self._me or {}
        quoted = self._quoted(m)
        if quoted and quoted["from_me"]:
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
            # getMe failed at start. Any @mention is a better guess than none:
            # the consumer still sees the message either way.
            return any("@" in h for h in handles)
        needle = f"@{me['username']}".lower()
        return any(h.lower() == needle or h.lower().endswith(needle) for h in handles)

    # ---- outbound ----------------------------------------------------------

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None, fresh: bool = False,
             plain: bool = False) -> str:
        """Send text to a chat, quoting a received message when reply_to is one
        of our "<chat>.<message_id>" ids. Returns the new message's id in the
        same form.

        `fresh` and `plain` are accepted so every provider takes the same
        arguments. Telegram has no idempotency key to vary, and the text goes
        out without a parse mode, exactly as `co telegram send` has always
        sent it, so there is no Markdown to leave untranslated."""
        body = {"chat_id": chat, "text": text}
        if reply_to and "." in reply_to:
            body["reply_parameters"] = {
                "message_id": int(reply_to.rsplit(".", 1)[1]),
                # The question was deleted while the answer was being written:
                # post the answer anyway rather than lose it.
                "allow_sending_without_reply": True,
            }
        result = self._call("sendMessage", body)
        return _message_id(chat, result.get("message_id"))

    # ---- REST -------------------------------------------------------------

    def _call(self, method: str, body: dict, *, timeout: float = 15):
        url = f"{API}/bot{self.token}/{method}"
        retried = False
        while True:
            try:
                response = requests.post(url, json=body, timeout=timeout)
            except requests.RequestException as exc:
                # The URL carries the token; the class name is the diagnosis.
                raise RuntimeError(f"Telegram request failed ({type(exc).__name__})") from None
            try:
                payload = response.json()
            except ValueError:
                raise RuntimeError(f"Telegram returned HTTP {response.status_code} without JSON") from None
            if payload.get("ok"):
                return payload.get("result")
            retry_after = (payload.get("parameters") or {}).get("retry_after")
            if response.status_code == 429 and retry_after and not retried:
                retried = True  # honour Telegram's own wait once, then report
                time.sleep(min(float(retry_after), 60.0))
                continue
            description = str(payload.get("description") or f"HTTP {response.status_code}")
            if self.token:
                description = description.replace(self.token, "[redacted]")
            raise Refused(f"Telegram refused: {description}", response.status_code)


def _message_id(chat, message_id) -> str:
    return f"{chat}.{message_id}"


def _name_of(user: dict) -> str:
    """The name a person shows in Telegram: first and last, else @username."""
    name = " ".join(part for part in (user.get("first_name"), user.get("last_name")) if part)
    return name or (f"@{user['username']}" if user.get("username") else "")


def _iso(date) -> str:
    try:
        return iso_utc(int(date))
    except (TypeError, ValueError):
        return iso_utc()
