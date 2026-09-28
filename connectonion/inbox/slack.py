"""
Purpose: Slack as an inbox — a Socket Mode WebSocket writes files, replies go out through chat.postMessage
LLM-Note:
  Dependencies: imports from [asyncio, json, os, random, time, requests, inbox/__init__.py (ListenerStopped), inbox/store.py] and lazily from [websockets] | imported by [inbox/__init__.py via provider()] | tested by [tests/unit/test_inbox_slack.py]
  Data flow: run(inbox) → auth.test (who the bot is) → apps.connections.open (a one-time wss URL) → hello → events_api envelopes → to_message() → inbox.deliver() → ACK {"envelope_id"} | send() → POST chat.postMessage (thread_ts on a reply) → "<channel>:<ts>"
  State/Effects: reads SLACK_APP_TOKEN (xapp-, opens the socket) and SLACK_BOT_TOKEN (xoxb-, reads and posts) | one outbound WebSocket that dials out, so no port is opened and no public URL exists | the threads the bot is part of live in memory, seeded from sent.jsonl at start | writes connection.json on every transition so `check` can report the real state
  Integration: Slack's ts is unique only inside a channel, so a message id is "<channel>:<ts>" | a DM and an @mention are addressed to the bot; so is a message in a thread the bot started or replied in | experimental: tested against fakes only, never a live workspace
  Errors: check() names each missing or misplaced token and the app-settings steps | a dropped socket or a Slack `disconnect` reconnects on a fresh URL with backoff | a token Slack rejects, or Socket Mode switched off (link_disabled), ends the listener with ListenerStopped | send() refuses >40000 characters before the network, honours one 429, and never echoes a token
"""

import asyncio
import json
import os
import random
import time
from typing import Optional

import requests

from . import ListenerStopped
from .store import Inbox, Message, iso_utc

API = "https://slack.com/api"

# Slack truncates a message over 40,000 characters instead of refusing it, so
# the caller would never learn its answer was cut. Refusing here is the only
# way it finds out. Slack's advisory 4,000 is not the limit: a longer message
# posts whole and shows "Show more", and refusing at 4,000 would drop answers
# Slack accepts (an agent's reply runs past that often enough).
LIMIT = 40000

APPS = "https://api.slack.com/apps"

NO_APP_TOKEN = (
    f"SLACK_APP_TOKEN is not set. At {APPS} open your app (or Create New App → From scratch), "
    "turn on Socket Mode, and create the app-level token it asks for with the scope "
    "connections:write. Put the xapp-… token in ~/.co/keys.env as SLACK_APP_TOKEN. Next: co slack check"
)
NO_BOT_TOKEN = (
    f"SLACK_BOT_TOKEN is not set. In your app at {APPS}: OAuth & Permissions → add the bot scopes "
    "chat:write, im:history and app_mentions:read; Event Subscriptions → subscribe to the bot events "
    "message.im and app_mention; App Home → turn on the Messages Tab; then Install to Workspace and "
    "put the Bot User OAuth Token (xoxb-…) in ~/.co/keys.env as SLACK_BOT_TOKEN. Next: co slack check"
)
WRONG_APP_TOKEN = (
    "SLACK_APP_TOKEN does not start with xapp-. It must be the app-level token (xapp-…, from Basic "
    "Information → App-Level Tokens), not the bot token (xoxb-…). Next: co slack check"
)
WRONG_BOT_TOKEN = (
    "SLACK_BOT_TOKEN does not start with xoxb-. It must be the Bot User OAuth Token (xoxb-…, from "
    "OAuth & Permissions), not the app-level token (xapp-…). Next: co slack check"
)

# Errors from Slack that no reconnect fixes, for each token. Anything else
# (ratelimited, internal_error, a network drop) is transient.
_REJECTED = {"invalid_auth", "not_authed", "token_revoked", "token_expired", "account_inactive",
             "missing_scope", "not_allowed_token_type"}
_APP_FIX = (f"Next: at {APPS} → Basic Information → App-Level Tokens, create a token with the scope "
            "connections:write and put it in ~/.co/keys.env as SLACK_APP_TOKEN")
_BOT_FIX = (f"Next: at {APPS} → Install App, reinstall to the workspace and put the Bot User OAuth "
            "Token (xoxb-…) in ~/.co/keys.env as SLACK_BOT_TOKEN")

# What to do about the refusals a send most often meets.
_SEND_HINTS = {
    "not_in_channel": "Next: invite the bot with /invite @<your bot> in that channel, then send again",
    "channel_not_found": "Next: co slack chats, for the channel ids the bot has seen",
    "is_archived": "Next: co slack chats",
    "msg_too_long": "Next: split the text and send each part",
}

# Subtypes that carry a person's new message. Everything else (edits,
# deletions, joins, topic changes, bot_message) is not something to answer.
_READABLE_SUBTYPES = {None, "file_share", "thread_broadcast"}


class Reconnect(Exception):
    """Slack asked for a new connection (a `disconnect` envelope)."""


class SocketClosed(Exception):
    """The socket closed; the caller reconnects."""

    def __init__(self, code: Optional[int]):
        super().__init__(f"socket closed with code {code}")
        self.code = code


class SlackStopped(Exception):
    """A failure no reconnect fixes. `reason` is Slack's own error code."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


class SlackError(RuntimeError):
    """Slack answered ok: false. `error` is Slack's code."""

    def __init__(self, error: str, message: str):
        super().__init__(message)
        self.error = error


class Slack:
    """One Slack app, the user's own, from api.slack.com/apps."""

    name = "slack"
    unwired = {
        "edit": "Slack has the endpoint for it (chat.update)",
        "delete": "Slack has the endpoint for it (chat.delete)",
        "react": "Slack has the endpoint for it (reactions.add, with the reactions:write scope)",
    }

    def __init__(self):
        self.app_token = os.environ.get("SLACK_APP_TOKEN", "")
        self.bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
        self._me_id: Optional[str] = None
        self._me_name: Optional[str] = None
        self._bot_id: Optional[str] = None
        # (channel, thread root ts) of threads the bot is part of.
        self._threads: set = set()

    # ---- setup -------------------------------------------------------------

    def missing(self) -> list:
        problems = []
        if not self.app_token:
            problems.append(NO_APP_TOKEN)
        elif not self.app_token.startswith("xapp-"):
            problems.append(WRONG_APP_TOKEN)
        if not self.bot_token:
            problems.append(NO_BOT_TOKEN)
        elif not self.bot_token.startswith("xoxb-"):
            problems.append(WRONG_BOT_TOKEN)
        return problems

    def check(self) -> list:
        problems = self.missing()
        if problems:
            return problems
        for test, which, fix in ((self.me, "SLACK_BOT_TOKEN", _BOT_FIX),
                                 (self._open, "SLACK_APP_TOKEN", _APP_FIX)):
            try:
                test()
            except (SlackStopped, RuntimeError) as exc:  # Slack's own words are the diagnosis
                text = str(exc)
                problems.append(text if "Next:" in text else
                                f"Slack did not accept {which}: {text}. {fix}")
        return problems

    def me(self) -> dict:
        """The bot's own user, for telling a mention of us from somebody else's."""
        try:
            result = self._api("auth.test", self.bot_token)
        except SlackError as exc:
            if exc.error in _REJECTED:
                raise SlackStopped(exc.error, f"Slack rejected SLACK_BOT_TOKEN ({exc.error}). "
                                              f"{_BOT_FIX}") from None
            raise
        self._me_id = str(result.get("user_id", "")) or None
        self._me_name = result.get("user") or self._me_name
        self._bot_id = str(result.get("bot_id", "")) or None
        return result

    def _open(self) -> str:
        """A fresh wss URL for one Socket Mode connection."""
        try:
            result = self._api("apps.connections.open", self.app_token)
        except SlackError as exc:
            if exc.error == "not_allowed_token_type":
                raise SlackStopped(exc.error, f"Slack refused SLACK_APP_TOKEN ({exc.error}): it must be "
                                              f"the app-level token (xapp-…), not a bot token (xoxb-…). "
                                              f"{_APP_FIX}") from None
            if exc.error in _REJECTED:
                raise SlackStopped(exc.error, f"Slack rejected SLACK_APP_TOKEN ({exc.error}). "
                                              f"{_APP_FIX}") from None
            raise
        url = str(result.get("url", ""))
        if not url.startswith("wss://"):
            raise RuntimeError("Slack returned no Socket Mode URL")
        return url

    # ---- inbound -----------------------------------------------------------

    def run(self, inbox: Inbox, *, raw: bool = False) -> None:
        """Hold the Socket Mode connection and write every message. Blocks."""
        asyncio.run(self._run(inbox, raw=raw))

    async def _run(self, inbox: Inbox, *, raw: bool = False) -> None:
        import websockets

        self._seed_threads(inbox)
        known = False
        delay = 1.0
        while True:
            try:
                if not known:
                    self.me()
                    known = True
                async with websockets.connect(self._open(), open_timeout=15, close_timeout=5,
                                              max_size=1_048_576) as socket:
                    await self._session(socket, inbox, raw=raw)
                delay = 1.0
            except SlackStopped as exc:
                self._stop(inbox, exc)
            except Reconnect:
                delay = 1.0
                continue
            except SocketClosed as exc:
                how = exc.code if exc.code is not None else "no close frame"
                inbox.log(f"socket closed ({how}); reconnecting in {delay:.0f}s")
            except (OSError, RuntimeError, asyncio.TimeoutError,
                    websockets.exceptions.WebSocketException) as exc:
                inbox.log(f"socket {type(exc).__name__}; reconnecting in {delay:.0f}s")
            inbox.record_connection("disconnected", account=self._account())
            await asyncio.sleep(delay + random.random())
            delay = min(delay * 2, 30.0)

    async def _session(self, socket, inbox: Inbox, *, raw: bool) -> None:
        """One connection, hello to close. Returns when the socket closes
        cleanly; raises Reconnect, SocketClosed or SlackStopped otherwise."""
        from websockets.exceptions import ConnectionClosed

        try:
            async for frame in socket:
                envelope = json.loads(frame)
                kind = envelope.get("type")
                if kind == "hello":
                    inbox.log(f"connected as {self._account()}")
                    inbox.record_connection("connected", account=self._account())
                    continue
                if kind == "disconnect":
                    reason = str(envelope.get("reason", ""))
                    if reason == "link_disabled":
                        raise SlackStopped(reason, "Socket Mode was switched off for this app. Turn it "
                                                   f"on again under Socket Mode at {APPS}. "
                                                   "Next: co slack listen")
                    inbox.log(f"Slack asked for a new connection ({reason or 'no reason'})")
                    raise Reconnect()
                if kind == "events_api":
                    event = (envelope.get("payload") or {}).get("event") or {}
                    self._dispatch(event, inbox, raw=raw)
                # Acknowledged only after the write: if it raised (a full
                # disk), Slack is not told and delivers the event again.
                if envelope.get("envelope_id"):
                    await socket.send(json.dumps({"envelope_id": envelope["envelope_id"]}))
        except ConnectionClosed as exc:
            raise SocketClosed(getattr(getattr(exc, "rcvd", None), "code", None)) from None

    def _dispatch(self, event: dict, inbox: Inbox, *, raw: bool) -> None:
        self._remember_own(event)
        try:
            message = self.to_message(event, raw=raw)
        except Exception as exc:
            # One event we cannot read is one log line, never a dead listener.
            inbox.log(f"event not understood ({type(exc).__name__}: {exc}); skipped")
            return
        if message is None:
            return
        # With app_mention and message.channels both on, an @mention arrives
        # as both; the inbox's dedup on "<channel>:<ts>" keeps one.
        if inbox.deliver(message, raw=raw):
            inbox.log(f"received {message.id} chat={message.chat} sender={message.sender}")
        else:
            inbox.log(f"duplicate {message.id} dropped")

    def _is_me(self, event: dict) -> bool:
        return bool((self._me_id and event.get("user") == self._me_id)
                    or (self._bot_id and event.get("bot_id") == self._bot_id))

    def _remember_own(self, event: dict) -> None:
        """Our own post in a thread makes the thread ours: later messages in it
        are addressed to us without an @mention."""
        if event.get("type") == "message" and event.get("thread_ts") and self._is_me(event):
            self._threads.add((str(event.get("channel", "")), str(event["thread_ts"])))

    def _seed_threads(self, inbox: Inbox) -> None:
        """The threads we replied in before this listener started, from sent.jsonl."""
        replied = {record["reply_to"] for record in inbox.recent_records(inbox.sent, 500)
                   if record.get("ok") and record.get("reply_to")}
        for record in inbox.history():
            if record.get("id") in replied:
                ts = str(record["id"]).rpartition(":")[2]
                self._threads.add((str(record.get("chat", "")), str(record.get("thread") or ts)))

    def _stop(self, inbox: Inbox, exc: SlackStopped) -> None:
        inbox.record_connection("stopped", reason=exc.reason)
        inbox.log(f"stopped: {exc.reason}")
        raise ListenerStopped(str(exc))

    def _account(self) -> str:
        return self._me_name or self._me_id or "unknown"

    def to_message(self, event: dict, *, raw: bool = False) -> Optional[Message]:
        """A message or app_mention event as a Message, or None for bots, our
        own messages, edits and other system subtypes, and anything without a
        channel, ts or user."""
        if event.get("type") not in ("message", "app_mention"):
            return None
        if event.get("subtype") not in _READABLE_SUBTYPES:
            return None
        user = str(event.get("user") or "")
        channel = str(event.get("channel") or "")
        ts = str(event.get("ts") or "")
        if not user or not channel or not ts or event.get("bot_id") or self._is_me(event):
            return None
        files = event.get("files") or []
        kind = _kind_of(files[0]) if files else "text"
        text = str(event.get("text") or "") or (f"[{kind}]" if files else "")
        if not text:
            return None
        thread_ts = str(event.get("thread_ts") or "")
        thread = thread_ts if thread_ts and thread_ts != ts else None
        profile = event.get("user_profile") or {}
        return Message(
            id=f"{channel}:{ts}",
            chat=channel,
            thread=thread,
            sender=user,
            sender_name=str(profile.get("display_name") or profile.get("real_name")
                            or profile.get("name") or ""),
            text=text,
            kind=kind,
            quoted=None,
            mentioned=self._addressed(event, channel, thread, text),
            at=iso_utc(float(ts)),
            raw=event if raw else None,
        )

    def _addressed(self, event: dict, channel: str, thread: Optional[str], text: str) -> bool:
        if event.get("channel_type") == "im" or event.get("type") == "app_mention":
            return True
        if self._me_id and f"<@{self._me_id}" in text:
            return True
        return bool(thread and (event.get("parent_user_id") == self._me_id
                                or (channel, thread) in self._threads))

    # ---- outbound ----------------------------------------------------------

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None, fresh: bool = False,
             plain: bool = False) -> str:
        """Post text to a channel, in the thread of reply_to when given.
        Returns the new message's id, "<channel>:<ts>".

        `plain` and `fresh` are accepted so every provider takes the same
        arguments. Slack reads its own mrkdwn, so there is nothing to render,
        and it has no idempotency key, so a second reply is simply a post."""
        if len(text) > LIMIT:
            raise RuntimeError(f"Slack messages are limited to {LIMIT} characters here (Slack cuts "
                               f"longer ones without saying so); got {len(text)}. Nothing was sent. "
                               f"Next: split it and send each part with co slack send {chat} \"<part>\"")
        body = {"channel": chat, "text": text}
        if reply_to:
            body["thread_ts"] = self._thread_root(reply_to)
        retried = False
        while True:
            try:
                response = requests.post(f"{API}/chat.postMessage", headers=self._headers(self.bot_token),
                                         json=body, timeout=15)
            except requests.RequestException as exc:
                raise RuntimeError(f"Slack request failed ({type(exc).__name__})") from None
            if response.status_code == 429 and not retried:
                retried = True  # honour Slack's own wait once, then report
                try:
                    retry_after = min(float(response.headers.get("Retry-After", 1)), 30.0)
                except (TypeError, ValueError):
                    retry_after = 1.0
                time.sleep(retry_after)
                continue
            try:
                result = self._result(response)
            except SlackError as exc:
                hint = _SEND_HINTS.get(exc.error.split()[0] if exc.error else "")
                raise RuntimeError(f"{exc}. {hint}" if hint else str(exc)) from None
            return f"{result.get('channel') or chat}:{result.get('ts', '')}"

    def _thread_root(self, reply_to: str) -> str:
        """The ts to reply under: the thread's root when the message we are
        answering is itself in a thread (Slack: never a reply's own ts)."""
        known = Inbox(self.name).lookup(reply_to)
        if known is not None and known.thread:
            return known.thread
        return reply_to.rpartition(":")[2]

    # ---- Web API -----------------------------------------------------------

    def _api(self, method: str, token: str) -> dict:
        try:
            response = requests.post(f"{API}/{method}", headers=self._headers(token), timeout=15)
        except requests.RequestException as exc:
            raise RuntimeError(f"Slack request failed ({type(exc).__name__})") from None
        return self._result(response)

    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}

    def _result(self, response) -> dict:
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError(f"Slack returned HTTP {response.status_code} without JSON") from None
        if isinstance(result, dict) and result.get("ok") and 200 <= response.status_code < 300:
            return result
        error = (str(result.get("error") or f"HTTP {response.status_code}")
                 if isinstance(result, dict) else f"HTTP {response.status_code}")
        for token in (self.app_token, self.bot_token):
            if token:
                error = error.replace(token, "[redacted]")
        raise SlackError(error, f"Slack refused: {error}")


def _kind_of(file: dict) -> str:
    """image, audio or video from the file's MIME type; anything else is a document."""
    major = str(file.get("mimetype") or "").split("/", 1)[0]
    return major if major in ("image", "audio", "video") else "document"
