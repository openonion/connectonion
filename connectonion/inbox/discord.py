"""
Purpose: Discord as an inbox — the Gateway WebSocket writes files, replies go out through the REST API
LLM-Note:
  Dependencies: imports from [asyncio, hashlib, json, os, random, time, uuid, requests, inbox/__init__.py (ListenerStopped), inbox/store.py] and lazily from [websockets] | imported by [inbox/__init__.py via provider()] | tested by [tests/unit/test_inbox_discord.py]
  Data flow: run(inbox) → wss gateway v10 → Hello → Identify (or Resume) → heartbeats → MESSAGE_CREATE → to_message() → inbox.deliver() | send() → POST /channels/{chat}/messages → message id
  State/Effects: reads DISCORD_BOT_TOKEN | one outbound WebSocket that dials out, so no port is opened | session id, resume URL and last sequence live in memory only | writes connection.json on every transition so `check` can report the real state
  Integration: message ids are Discord snowflakes, unique across the platform, so the inbox dedupes on them unchanged | a DM is always addressed to the bot; a guild message only when it mentions the bot or replies to one of its messages
  Errors: check() names the missing token and the Developer Portal steps | a dropped socket or an unacknowledged heartbeat reconnects with backoff and resumes | a close code no reconnect fixes (bad token, Message Content intent not enabled) ends the listener with ListenerStopped | send() refuses >2000 characters before the network, honours one 429, and never echoes the token
"""

import asyncio
import hashlib
import json
import os
import random
import time
import uuid
from typing import Optional

import requests

from . import ListenerStopped
from .store import Inbox, Message, iso_utc

API = "https://discord.com/api/v10"
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"

# GUILDS, GUILD_MESSAGES, DIRECT_MESSAGES, MESSAGE_CONTENT. The last one is
# privileged: without it switched on in the Developer Portal, Discord closes
# the socket with 4014 — and if it were left out of this number instead, every
# guild message would arrive with empty content and look like an attachment.
INTENTS = (1 << 0) | (1 << 9) | (1 << 12) | (1 << 15)

LIMIT = 2000

NO_TOKEN = (
    "DISCORD_BOT_TOKEN is not set. Create an application and a bot at "
    "https://discord.com/developers/applications, turn on the Message Content "
    "intent under Bot, then put the bot token in ~/.co/keys.env as DISCORD_BOT_TOKEN."
)

# Close codes that no reconnect recovers from, with what a person has to do.
# Everything else (network drops, 4000 unknown error, 4007/4009 stale session)
# is transient and the listener reconnects.
FATAL_CLOSES = {
    4004: "Discord rejected the bot token. Next: copy a fresh token from the Bot page "
          "of the Developer Portal into ~/.co/keys.env as DISCORD_BOT_TOKEN",
    4010: "Discord rejected the shard. Next: co discord check",
    4011: "This bot is in too many servers for one connection (sharding required). "
          "Next: co discord check",
    4012: "Discord rejected the Gateway version. Next: co discord check",
    4013: "Discord rejected the intents this listener asked for. Next: co discord check",
    4014: "The Message Content intent is not enabled for this bot. Turn it on under "
          "Bot → Privileged Gateway Intents in the Developer Portal. Next: co discord listen",
}
# Closes after which the old session cannot be resumed: identify afresh.
_SESSION_GONE = {4007, 4009}

# Discord's nonce is at most 25 characters. Derived from what is being
# answered and with what, so a retried reply is recognised by Discord rather
# than posted twice (see send()).
_NONCE_NAMESPACE = uuid.UUID("0f3c9a52-8d1e-4b7a-a6c4-5e2d7b91f083")


class Reconnect(Exception):
    """Discord asked the client to reconnect (op 7) or said the session is invalid (op 9)."""


class GatewayClosed(Exception):
    """The socket closed with a code; the caller decides whether it is fatal."""

    def __init__(self, code: Optional[int]):
        super().__init__(f"gateway closed with code {code}")
        self.code = code


class Discord:
    """One bot, the user's own, from the Discord Developer Portal."""

    name = "discord"
    unwired = {
        "edit": "Discord has the endpoint for it (PATCH /channels/<chat>/messages/<id>)",
        "delete": "Discord has the endpoint for it (DELETE /channels/<chat>/messages/<id>)",
        "react": "Discord has the endpoint for it (PUT /channels/<chat>/messages/<id>/reactions/<emoji>/@me)",
    }

    def __init__(self):
        self.token = os.environ.get("DISCORD_BOT_TOKEN", "")
        self._me_id: Optional[str] = None
        self._me_name: Optional[str] = None
        self._session_id: Optional[str] = None
        self._resume_url: Optional[str] = None
        self._sequence: Optional[int] = None
        self._heartbeat_ack = True

    # ---- setup -------------------------------------------------------------

    def missing(self) -> list:
        return [] if self.token else [NO_TOKEN]

    def check(self) -> list:
        problems = self.missing()
        if problems:
            return problems
        try:
            self.me()
            self._result(requests.get(f"{API}/gateway/bot", headers=self._headers(), timeout=15))
        except Exception as exc:  # Discord's own words are the diagnosis
            problems.append(f"Discord did not accept the bot: {exc}. "
                            f"Next: copy the token again from the Developer Portal into ~/.co/keys.env")
        return problems

    def me(self) -> dict:
        """The bot's own user, for telling a mention of us from one of somebody else."""
        result = self._result(requests.get(f"{API}/users/@me", headers=self._headers(), timeout=15))
        self._me_id = str(result.get("id", "")) or None
        self._me_name = result.get("username")
        return result

    # ---- inbound -----------------------------------------------------------

    def run(self, inbox: Inbox, *, raw: bool = False) -> None:
        """Hold the Gateway connection and write every message. Blocks."""
        asyncio.run(self._run(inbox, raw=raw))

    async def _run(self, inbox: Inbox, *, raw: bool = False) -> None:
        import websockets

        delay = 1.0
        while True:
            try:
                async with websockets.connect(self._gateway_url(), open_timeout=15,
                                              close_timeout=5, max_size=1_048_576) as socket:
                    await self._session(socket, inbox, raw=raw)
                delay = 1.0
            except Reconnect:
                inbox.log("gateway asked us to reconnect")
                delay = 1.0
                continue
            except GatewayClosed as exc:
                if exc.code in FATAL_CLOSES:
                    self._stop(inbox, exc.code)
                if exc.code in _SESSION_GONE:
                    self._forget_session()
                how = exc.code if exc.code is not None else "no close frame"
                inbox.log(f"gateway closed ({how}); reconnecting in {delay:.0f}s")
            except (OSError, RuntimeError, asyncio.TimeoutError,
                    websockets.exceptions.WebSocketException) as exc:
                inbox.log(f"gateway {type(exc).__name__}; reconnecting in {delay:.0f}s")
            inbox.record_connection("disconnected", account=self._account())
            await asyncio.sleep(delay + random.random())
            delay = min(delay * 2, 30.0)

    async def _session(self, socket, inbox: Inbox, *, raw: bool) -> None:
        """One connection, Hello to close. Returns when the socket closes
        cleanly; raises Reconnect or GatewayClosed otherwise."""
        from websockets.exceptions import ConnectionClosed

        hello = json.loads(await socket.recv())
        if hello.get("op") != 10:
            raise RuntimeError("Discord Gateway did not start with Hello")
        interval = float((hello.get("d") or {}).get("heartbeat_interval", 0)) / 1000
        if interval <= 0:
            raise RuntimeError("Discord Gateway returned no heartbeat interval")
        self._heartbeat_ack = True
        heartbeat = asyncio.create_task(self._heartbeat(socket, interval))
        try:
            await socket.send(json.dumps(self._authentication_payload()))
            async for frame in socket:
                payload = json.loads(frame)
                op = payload.get("op")
                if op == 0:
                    self._dispatch(payload, inbox, raw=raw)
                # The sequence moves only after the event is written. If the
                # write failed (a full disk), the resume asks Discord to replay
                # from before it rather than acknowledging a message we lost.
                if payload.get("s") is not None:
                    self._sequence = int(payload["s"])
                elif op == 1:
                    # Discord asking for a heartbeat now; the ACK follows.
                    await socket.send(json.dumps({"op": 1, "d": self._sequence}))
                elif op == 11:
                    self._heartbeat_ack = True
                elif op == 7:
                    raise Reconnect()
                elif op == 9:
                    if payload.get("d") is not True:
                        self._forget_session()
                        # Discord asks for a pause of 1–5 s before a fresh Identify.
                        await asyncio.sleep(1 + 4 * random.random())
                    raise Reconnect()
        except ConnectionClosed as exc:
            raise GatewayClosed(getattr(getattr(exc, "rcvd", None), "code", None)) from None
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        code = getattr(socket, "close_code", None)
        if code is not None and code >= 4000:
            raise GatewayClosed(code)

    async def _heartbeat(self, socket, interval: float) -> None:
        """Beat every interval; close the socket if the last beat went
        unacknowledged. An open socket that Discord has stopped answering is
        the failure a parser test cannot see: nothing crashes, nothing arrives."""
        await asyncio.sleep(interval * random.random())
        while True:
            if not self._heartbeat_ack:
                await socket.close(code=4000, reason="heartbeat not acknowledged")
                return
            self._heartbeat_ack = False
            await socket.send(json.dumps({"op": 1, "d": self._sequence}))
            await asyncio.sleep(interval)

    def _authentication_payload(self) -> dict:
        if self._session_id and self._sequence is not None:
            return {"op": 6, "d": {"token": self.token, "session_id": self._session_id,
                                   "seq": self._sequence}}
        return {
            "op": 2,
            "d": {
                "token": self.token,
                "intents": INTENTS,
                "properties": {"os": os.name, "browser": "connectonion", "device": "connectonion"},
            },
        }

    def _forget_session(self) -> None:
        self._session_id = None
        self._resume_url = None
        self._sequence = None

    def _dispatch(self, payload: dict, inbox: Inbox, *, raw: bool) -> None:
        event = payload.get("d") or {}
        kind = payload.get("t")
        if kind == "READY":
            self._session_id = str(event.get("session_id", "")) or None
            self._resume_url = str(event.get("resume_gateway_url", "")) or None
            user = event.get("user") or {}
            self._me_id = str(user.get("id", "")) or None
            self._me_name = user.get("username") or self._me_name
            inbox.log(f"connected as {self._account()}")
            inbox.record_connection("connected", account=self._account())
            return
        if kind == "RESUMED":
            inbox.log("resumed")
            inbox.record_connection("connected", account=self._account())
            return
        if kind != "MESSAGE_CREATE":
            return
        try:
            message = self.to_message(event, raw=raw)
        except Exception as exc:
            # One event we cannot read is one log line, never a dead listener.
            inbox.log(f"event not understood ({type(exc).__name__}: {exc}); skipped")
            return
        if message is None:
            return
        # A resumed session replays what it missed, so a duplicate here is
        # normal; the inbox's dedup on the snowflake is what makes it harmless.
        if inbox.deliver(message, raw=raw):
            inbox.log(f"received {message.id} chat={message.chat} sender={message.sender}")
        else:
            inbox.log(f"duplicate {message.id} dropped")

    def _stop(self, inbox: Inbox, code: int) -> None:
        reason = FATAL_CLOSES[code]
        inbox.record_connection("stopped", reason=f"close {code}")
        inbox.log(f"stopped: gateway close {code}")
        raise ListenerStopped(f"Discord closed the Gateway with {code}. {reason}")

    def _account(self) -> str:
        return self._me_name or self._me_id or "unknown"

    def to_message(self, event: dict, *, raw: bool = False) -> Optional[Message]:
        """A MESSAGE_CREATE as a Message, or None for bots, webhooks, our own
        messages and anything without an author, channel or id."""
        author = event.get("author") or {}
        author_id = str(author.get("id", ""))
        channel_id = str(event.get("channel_id", ""))
        message_id = str(event.get("id", ""))
        if (not author_id or not channel_id or not message_id or author.get("bot")
                or event.get("webhook_id") or (self._me_id and author_id == self._me_id)):
            return None
        attachments = event.get("attachments") or []
        kind = _kind_of(attachments[0]) if attachments else "text"
        text = str(event.get("content") or "")
        if not text:
            text = f"[{kind}]" if attachments else ""
        if not text:
            # A sticker, an embed-only message, a system message: nothing a
            # consumer can read and nothing it could answer.
            return None
        mentions = {str(user.get("id")) for user in event.get("mentions") or []}
        quoted = self._quoted(event)
        return Message(
            id=message_id,
            chat=channel_id,
            thread=None,
            sender=author_id,
            sender_name=str(author.get("global_name") or author.get("username") or ""),
            text=text,
            kind=kind,
            quoted=quoted,
            mentioned=(event.get("guild_id") is None
                       or (self._me_id is not None and self._me_id in mentions)
                       or bool(quoted and quoted["from_me"])),
            at=str(event.get("timestamp") or iso_utc()),
            raw=event if raw else None,
        )

    def _quoted(self, event: dict) -> Optional[dict]:
        replied = event.get("referenced_message")
        if not isinstance(replied, dict):
            return None
        author = replied.get("author") or {}
        attachments = replied.get("attachments") or []
        return {
            "id": str(replied.get("id", "")),
            "sender": str(author.get("id", "")),
            "text": str(replied.get("content") or ""),
            "kind": _kind_of(attachments[0]) if attachments else "text",
            "from_me": self._me_id is not None and str(author.get("id", "")) == self._me_id,
        }

    # ---- outbound ----------------------------------------------------------

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None, fresh: bool = False,
             plain: bool = False) -> str:
        """Send text to a channel, as a reply when reply_to is a message id.
        Returns the new message's id.

        `plain` is accepted so every provider takes the same arguments;
        Discord renders Markdown itself, so there is nothing to translate.
        A reply carries a nonce derived from the message and the text, with
        enforce_nonce, so a retried reply returns the message already posted
        instead of posting it twice; `fresh` (`reply --again`) is a deliberate
        second post and gets a new one."""
        if len(text) > LIMIT:
            raise RuntimeError(f"Discord messages are limited to {LIMIT} characters; got {len(text)}")
        # No `parse`: nothing in the text pings anyone — not @everyone, not a
        # role — and the person being replied to is not pinged either.
        body = {"content": text, "allowed_mentions": {"parse": [], "replied_user": False}}
        if reply_to:
            body["message_reference"] = {"message_id": reply_to, "channel_id": chat,
                                         "fail_if_not_exists": False}
            if fresh:
                body["nonce"] = uuid.uuid4().hex[:25]
            else:
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
                body["nonce"] = uuid.uuid5(_NONCE_NAMESPACE, f"{reply_to}:{digest}").hex[:25]
            body["enforce_nonce"] = True
        retried = False
        while True:
            try:
                response = requests.post(f"{API}/channels/{chat}/messages", headers=self._headers(),
                                         json=body, timeout=15)
            except requests.RequestException as exc:
                raise RuntimeError(f"Discord request failed ({type(exc).__name__})") from None
            if response.status_code == 429 and not retried:
                retried = True  # honour Discord's own wait once, then report
                try:
                    retry_after = min(float(response.json()["retry_after"]), 30.0)
                except (KeyError, TypeError, ValueError):
                    retry_after = 1.0
                time.sleep(retry_after)
                continue
            return str(self._result(response).get("id", ""))

    # ---- REST -------------------------------------------------------------

    def _gateway_url(self) -> str:
        base = self._resume_url or GATEWAY
        if "encoding=" in base:
            return base
        return f"{base}{'&' if '?' in base else '/?'}v=10&encoding=json"

    def _headers(self) -> dict:
        from .. import __version__

        return {
            "Authorization": f"Bot {self.token}",
            "User-Agent": f"DiscordBot (https://github.com/openonion/connectonion, {__version__})",
        }

    def _result(self, response) -> dict:
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError(f"Discord returned HTTP {response.status_code} without JSON") from None
        if not 200 <= response.status_code < 300 or not isinstance(result, dict):
            message = (str(result.get("message", f"HTTP {response.status_code}"))
                       if isinstance(result, dict) else f"HTTP {response.status_code}")
            if self.token:
                message = message.replace(self.token, "[redacted]")
            raise RuntimeError(f"Discord refused: {message}")
        return result


def _kind_of(attachment: dict) -> str:
    """image, audio or video from the attachment's MIME type; anything else is a document."""
    major = str(attachment.get("content_type") or "").split("/", 1)[0]
    return major if major in ("image", "audio", "video") else "document"
