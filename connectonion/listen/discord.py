"""Discord Gateway messages as the shared local mailbox contract."""

import asyncio
import json
import os
import random
import time
from typing import Optional

import requests
import websockets

from .mailbox import Mailbox, Message, iso_utc


API = "https://discord.com/api/v10"
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
INTENTS = (1 << 0) | (1 << 9) | (1 << 12) | (1 << 15)
NO_TOKEN = (
    "DISCORD_BOT_TOKEN is not set. Create a bot in the Discord Developer "
    "Portal, enable Message Content intent, then put the token in ~/.co/keys.env."
)


class Reconnect(Exception):
    """Discord asked the client to resume its Gateway session."""


class Discord:
    name = "discord"

    def __init__(self):
        self.token = os.environ.get("DISCORD_BOT_TOKEN", "")
        self._me_id: Optional[str] = None
        self._session_id: Optional[str] = None
        self._resume_url: Optional[str] = None
        self._sequence: Optional[int] = None
        self._heartbeat_ack = True

    def missing(self) -> list[str]:
        return [] if self.token else [NO_TOKEN]

    def check(self) -> list[str]:
        problems = self.missing()
        if problems:
            return problems
        try:
            self.me()
            response = requests.get(
                f"{API}/gateway/bot", headers=self._headers(), timeout=15
            )
            self._result(response)
        except Exception as exc:
            problems.append(f"Discord did not accept the bot: {exc}")
        return problems

    def me(self) -> dict:
        response = requests.get(
            f"{API}/users/@me", headers=self._headers(), timeout=15
        )
        result = self._result(response)
        self._me_id = str(result.get("id", ""))
        return result

    def run(self, mailbox: Mailbox, *, raw: bool = False) -> None:
        asyncio.run(self._run(mailbox, raw=raw))

    async def _run(self, mailbox: Mailbox, *, raw: bool = False) -> None:
        delay = 1.0
        while True:
            url = self._gateway_url()
            try:
                async with websockets.connect(
                    url, open_timeout=15, close_timeout=5, max_size=1_048_576
                ) as socket:
                    await self._session(socket, mailbox, raw=raw)
                delay = 1.0
            except Reconnect:
                mailbox.log("gateway reconnect requested")
                delay = 1.0
            except Exception as exc:
                mailbox.log(
                    f"gateway {type(exc).__name__}; reconnecting in {delay:.0f}s"
                )
                await asyncio.sleep(delay + random.random())
                delay = min(delay * 2, 30.0)

    async def _session(self, socket, mailbox: Mailbox, *, raw: bool) -> None:
        hello = json.loads(await socket.recv())
        if hello.get("op") != 10:
            raise RuntimeError("Discord Gateway did not start with Hello")
        interval = float((hello.get("d") or {}).get("heartbeat_interval", 0)) / 1000
        if interval <= 0:
            raise RuntimeError("Discord Gateway returned no heartbeat interval")
        heartbeat = asyncio.create_task(self._heartbeat(socket, interval))
        try:
            await socket.send(json.dumps(self._authentication_payload()))
            async for frame in socket:
                payload = json.loads(frame)
                if payload.get("s") is not None:
                    self._sequence = int(payload["s"])
                op = payload.get("op")
                if op == 0:
                    self._dispatch(payload, mailbox, raw=raw)
                elif op == 1:
                    self._heartbeat_ack = False
                    await socket.send(json.dumps({"op": 1, "d": self._sequence}))
                elif op == 11:
                    self._heartbeat_ack = True
                elif op == 7:
                    raise Reconnect()
                elif op == 9:
                    if payload.get("d") is not True:
                        self._session_id = None
                        self._resume_url = None
                        self._sequence = None
                    raise Reconnect()
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _heartbeat(self, socket, interval: float) -> None:
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
            return {
                "op": 6,
                "d": {
                    "token": self.token,
                    "session_id": self._session_id,
                    "seq": self._sequence,
                },
            }
        return {
            "op": 2,
            "d": {
                "token": self.token,
                "intents": INTENTS,
                "properties": {
                    "os": os.name,
                    "browser": "connectonion",
                    "device": "connectonion",
                },
            },
        }

    def _dispatch(self, payload: dict, mailbox: Mailbox, *, raw: bool) -> None:
        event = payload.get("d") or {}
        if payload.get("t") == "READY":
            self._session_id = str(event.get("session_id", "")) or None
            self._resume_url = str(event.get("resume_gateway_url", "")) or None
            self._me_id = str((event.get("user") or {}).get("id", "")) or None
            mailbox.log(f"connected as bot {self._me_id or 'unknown'}")
            return
        if payload.get("t") != "MESSAGE_CREATE":
            return
        message = self.to_message(event, raw=raw)
        if message is None:
            return
        if mailbox.deliver(message, raw=raw):
            mailbox.log(
                f"received {message.id} chat={message.chat} sender={message.sender}"
            )
        else:
            mailbox.log(f"duplicate {message.id} dropped")

    def to_message(self, event: dict, *, raw: bool = False) -> Optional[Message]:
        author = event.get("author") or {}
        author_id = str(author.get("id", ""))
        channel_id = str(event.get("channel_id", ""))
        message_id = str(event.get("id", ""))
        if (
            not author_id
            or not channel_id
            or not message_id
            or author.get("bot")
            or event.get("webhook_id")
            or (self._me_id and author_id == self._me_id)
        ):
            return None
        content = str(event.get("content") or "")
        if not content:
            content = "[attachment]" if event.get("attachments") else "[message]"
        guild_id = event.get("guild_id")
        mentions = {str(user.get("id")) for user in event.get("mentions") or []}
        reference = event.get("referenced_message") or {}
        replied_to_us = str((reference.get("author") or {}).get("id", "")) == self._me_id
        return Message(
            id=message_id,
            chat=channel_id,
            thread=channel_id if event.get("thread") else None,
            sender=author_id,
            text=content,
            mentioned=(guild_id is None or self._me_id in mentions or replied_to_us),
            at=str(event.get("timestamp") or iso_utc()),
            raw=event if raw else None,
        )

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None) -> str:
        if len(text) > 2000:
            raise RuntimeError(
                f"Discord messages are limited to 2000 characters; got {len(text)}"
            )
        body = {"content": text, "allowed_mentions": {"replied_user": False}}
        if reply_to:
            body["message_reference"] = {
                "message_id": reply_to,
                "channel_id": chat,
                "fail_if_not_exists": False,
            }
        retried = False
        while True:
            try:
                response = requests.post(
                    f"{API}/channels/{chat}/messages",
                    headers=self._headers(),
                    json=body,
                    timeout=15,
                )
            except requests.RequestException as exc:
                raise RuntimeError(
                    f"Discord request failed ({type(exc).__name__})"
                ) from None
            if response.status_code == 429 and not retried:
                retried = True
                try:
                    retry_after = min(float(response.json()["retry_after"]), 30.0)
                except (KeyError, TypeError, ValueError):
                    retry_after = 1.0
                time.sleep(retry_after)
                continue
            result = self._result(response)
            return str(result.get("id", ""))

    def _gateway_url(self) -> str:
        base = self._resume_url or GATEWAY
        separator = "&" if "?" in base else "?"
        return base if "encoding=" in base else f"{base}{separator}v=10&encoding=json"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bot {self.token}",
            "User-Agent": "ConnectOnion (https://github.com/openonion/connectonion, 1.8.5)",
        }

    def _result(self, response) -> dict:
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError(
                f"Discord returned HTTP {response.status_code} without JSON"
            ) from None
        if not 200 <= response.status_code < 300 or not isinstance(result, dict):
            message = (
                str(result.get("message", f"HTTP {response.status_code}"))
                if isinstance(result, dict)
                else f"HTTP {response.status_code}"
            )
            raise RuntimeError(
                f"Discord refused: {message.replace(self.token, '[redacted]')}"
            )
        return result
