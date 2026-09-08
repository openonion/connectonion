"""
Purpose: Feishu and Lark as a mailbox — the official SDK's long connection writes files, replies go out through the REST API
LLM-Note:
  Dependencies: imports from [json, os, time, uuid, datetime, requests, listen/mailbox.py] and lazily from [lark_oapi] | imported by [listen/__init__.py via provider()] | tested by [tests/unit/test_listen_feishu.py]
  Data flow: run(mailbox) → lark_oapi.ws.Client long connection → im.message.receive_v1 event → to_message() → mailbox.deliver() | send()/reply → tenant token → POST /open-apis/im/v1/messages or /messages/{id}/reply → message_id
  State/Effects: reads FEISHU_APP_ID/FEISHU_APP_SECRET (LARK_* for Lark) from the environment | one outbound WebSocket that dials out, so no port is opened | caches the tenant token in memory for its lifetime
  Integration: the same class serves `co feishu` and `co lark`; only the domain and the env prefix differ | the event handler does nothing but convert and write, acknowledgement follows the durable mailbox write; storage failures remain retryable
  Errors: check() returns the missing item and the next action instead of raising | send() raises RuntimeError with Feishu's own code and message, after retrying a rate limit three times | a missing SDK is reported with the pip command
"""

import hashlib
import json
import os
import time
import uuid
from typing import Optional

import requests

from .mailbox import Mailbox, Message, iso_utc

DOMAINS = {
    "feishu": "https://open.feishu.cn",
    "lark": "https://open.larksuite.com",
}

SDK_MISSING = "The Feishu SDK is not installed. Run: pip install lark-oapi"

# Feishu's reply endpoint dedupes on this for an hour, so a retried reply to
# the same message cannot post twice even across processes.
_REPLY_NAMESPACE = uuid.UUID("7d2a5b1e-0c4f-4e8a-9b3d-2f6c1a0e5d47")

# 99991400 is a per-minute frequency limit: wait and retry. 99991403 is the
# tenant's monthly API quota (10,000 calls on the free edition, across every
# self-built app): retrying only burns time. Receiving messages and fetching
# the tenant token are not counted; replies are.
_RATE_LIMITED = {99991400}
QUOTA_EXHAUSTED = 99991403
# The tenant token Feishu gave us is no longer good: rotated secret, or
# invalidated on their side. The cache is wrong, not the clock.
_TOKEN_INVALID = {99991663, 99991664, 99991665, 99991668}


class CredentialsRefused(RuntimeError):
    """Feishu answered the token request and said no to this app_id and
    app_secret. The one error that no retry and no reconnect can fix."""
QUOTA_MESSAGE = (
    "Feishu's monthly API quota for this tenant is used up (error 99991403). "
    "Replies count against it, receiving does not. It resets on the 1st of the "
    "month; a paid Feishu edition removes the cap. Usage: 管理后台 > 费用中心 > 权益数据."
)


def _sdk():
    try:
        import lark_oapi
    except ImportError as exc:
        raise RuntimeError(SDK_MISSING) from exc
    return lark_oapi


class Feishu:
    """One Feishu or Lark self-built application with bot capability."""

    def __init__(self, domain: str = "feishu"):
        if domain not in DOMAINS:
            raise ValueError(f"domain must be feishu or lark, not {domain!r}")
        self.name = domain
        self.base = DOMAINS[domain]
        # What the error messages call the platform. A `co lark` user who
        # reads "Feishu refused the credentials" goes looking in the wrong
        # console.
        self.brand = "Lark" if domain == "lark" else "Feishu"
        self.env_prefix = domain.upper()
        self.app_id = os.environ.get(f"{self.env_prefix}_APP_ID", "")
        self.app_secret = os.environ.get(f"{self.env_prefix}_APP_SECRET", "")
        self._token: Optional[str] = None
        self._token_expires_at = 0.0
        self._bot_open_id: Optional[str] = None

    # ---- setup -------------------------------------------------------------

    def missing(self) -> list:
        """Configuration problems, each with the fix. Empty means complete."""
        problems = []
        for key in ("APP_ID", "APP_SECRET"):
            if not os.environ.get(f"{self.env_prefix}_{key}"):
                problems.append(
                    f"{self.env_prefix}_{key} is not set. Create a self-built application at "
                    f"{self.base}/app, enable the bot, and put its credentials in ~/.co/keys.env."
                )
        return problems

    def listen_requirements(self) -> list:
        """What `listen` needs beyond the credentials: the SDK. send and
        reply are plain REST and work without it, so this is asked by
        listen alone and not by every verb."""
        try:
            _sdk()
        except RuntimeError as exc:
            return [str(exc)]
        return []

    def check(self) -> list:
        """Everything that must be true before `listen` can work. Each entry
        is a problem and its next action; an empty list is a pass."""
        problems = self.missing()
        if problems:
            return problems
        problems.extend(self.listen_requirements())
        try:
            info = self.bot_info()
        except Exception as exc:  # the API's own words are the diagnosis
            problems.append(f"Could not reach {self.base} with these credentials: {exc}")
            return problems
        if not info.get("open_id"):
            problems.append(
                "The application has no bot. Enable the bot capability in the application "
                "console, then subscribe to im.message.receive_v1."
            )
        return problems

    def bot_info(self) -> dict:
        """The bot's own identity, used to tell an @mention of us from an
        @mention of someone else."""
        body = self._get("/open-apis/bot/v3/info")
        bot = body.get("bot") or {}
        self._bot_open_id = bot.get("open_id")
        return {"open_id": bot.get("open_id"), "name": bot.get("app_name")}

    # ---- inbound -----------------------------------------------------------

    def run(self, mailbox: Mailbox, *, raw: bool = False) -> None:
        """Hold the long connection and write every message. Blocks."""
        lark = _sdk()
        try:
            info = self.bot_info()
            mailbox.log(f"connected as {info.get('name') or self.app_id}")
        except CredentialsRefused as exc:
            # Feishu answered and said no: wrong app_id, wrong secret, app not
            # published. Dialling the WebSocket with the same pair cannot
            # succeed, and the SDK would retry it every two minutes forever,
            # each attempt a "connect failed" line that hides the real reason.
            mailbox.log(f"bot info failed: {exc}")
            raise
        except Exception as exc:
            # Anything else is a bad minute, not a bad key: a 502 page from
            # the edge, a rate limit on the info call, no answer at all. The
            # long connection has its own reconnect and may well get
            # through; only the own-@mention check runs without the bot's
            # open_id until then.
            mailbox.log(f"bot info failed: {exc}")

        def on_message(data) -> None:
            # Parsing failures must not raise. The SDK answers a
            # raising handler with HTTP 500, and Feishu treats 500 as "not
            # delivered" and sends the same event again for hours. A payload
            # we cannot read is one log line, never a retry storm.
            try:
                message = self.to_message(data)
            except Exception as exc:
                mailbox.log(f"event not understood ({type(exc).__name__}: {exc}); skipped")
                return
            if message is None:
                return
            if raw:
                try:
                    message.raw = _raw_of(data)
                except Exception as exc:
                    mailbox.log(f"raw payload of {message.id} not kept: {exc}")
            # deliver() is left to raise on a full or unwritable disk: that
            # is the one case where "not delivered, send it again" is true.
            if mailbox.deliver(message, raw=raw):
                mailbox.log(f"received {message.id} chat={message.chat} sender={message.sender}")
            else:
                mailbox.log(f"duplicate {message.id} dropped")

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .build()
        )
        client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=handler,
            domain=self.base,
            log_level=lark.LogLevel.WARNING,
        )
        client.on_reconnecting = lambda: mailbox.log("reconnecting")
        client.on_reconnected = lambda: mailbox.log("reconnected")
        client.start()

    def to_message(self, data, *, raw: bool = False) -> Optional[Message]:
        """An im.message.receive_v1 event as a Message, or None for an event
        that is not a person talking to us (our own messages, other bots)."""
        event = getattr(data, "event", None)
        message = getattr(event, "message", None)
        sender = getattr(event, "sender", None)
        if message is None or sender is None:
            return None
        if getattr(sender, "sender_type", "user") != "user":
            return None

        mentions = list(getattr(message, "mentions", None) or [])
        text = _text_of(message, mentions)
        chat_type = getattr(message, "chat_type", None)
        if chat_type == "p2p":
            mentioned = True
        elif self._bot_open_id:
            mentioned = any(_open_id(m) == self._bot_open_id for m in mentions)
        else:
            mentioned = bool(mentions)

        sender_id = getattr(sender, "sender_id", None)
        create_time = getattr(message, "create_time", None)
        return Message(
            id=str(message.message_id),
            chat=str(message.chat_id),
            thread=getattr(message, "thread_id", None) or getattr(message, "root_id", None) or None,
            sender=str(getattr(sender_id, "union_id", None) or getattr(sender_id, "open_id", None) or ""),
            text=text,
            mentioned=mentioned,
            at=_iso(create_time),
            raw=_raw_of(data) if raw else None,
        )

    # ---- outbound ----------------------------------------------------------

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None, fresh: bool = False) -> str:
        """Send text to a chat, or as a reply to a message. Returns the new
        message id. `fresh` is `reply --again`: a deliberate second post,
        even of the same words."""
        content = json.dumps({"text": text}, ensure_ascii=False)
        if reply_to:
            # Same message, same text: a retry, and Feishu drops the second
            # copy for an hour. `--again` asks for a second post on purpose,
            # so it must not reuse the key, or Feishu swallows it while the
            # CLI reports an id: a fresh key for a fresh post.
            if fresh:
                key = str(uuid.uuid4())
            else:
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
                key = str(uuid.uuid5(_REPLY_NAMESPACE, f"{self.name}:{reply_to}:{digest}"))
            body = {
                "msg_type": "text",
                "content": content,
                "uuid": key,
            }
            result = self._post(f"/open-apis/im/v1/messages/{reply_to}/reply", body)
        else:
            body = {
                "receive_id": chat,
                "msg_type": "text",
                "content": content,
                "uuid": str(uuid.uuid4()),
            }
            result = self._post("/open-apis/im/v1/messages?receive_id_type=chat_id", body)
        return str(result.get("message_id", ""))

    # ---- REST -------------------------------------------------------------

    def _tenant_token(self) -> str:
        if self._token and time.time() < self._token_expires_at:
            return self._token
        response = requests.post(
            f"{self.base}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=15,
        )
        body = response.json()
        if body.get("code") != 0:
            raise CredentialsRefused(f"{self.brand} refused the credentials: {body.get('code')} {body.get('msg')}")
        self._token = body["tenant_access_token"]
        # Refresh a minute early; Feishu's own expiry is two hours.
        self._token_expires_at = time.time() + int(body.get("expire", 7200)) - 60
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._tenant_token()}"}

    def _call(self, send):
        """One request; a second one with a fresh token if Feishu says the
        cached token is no longer good. The token is otherwise cached by the
        clock, and a secret rotated in the console would leave `serve`
        failing every reply for up to two hours."""
        response = send()
        if _code(response) in _TOKEN_INVALID:
            self._token = None
            response = send()
        return response

    def _get(self, path: str) -> dict:
        url = f"{self.base}{path}"
        response = self._call(lambda: requests.get(url, headers=self._headers(), timeout=15))
        return _data(response, self.brand)

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base}{path}"
        delay = 1.0
        for attempt in range(3):
            response = self._call(lambda: requests.post(url, headers=self._headers(), json=body, timeout=15))
            code = _code(response)
            if code == QUOTA_EXHAUSTED:
                raise RuntimeError(QUOTA_MESSAGE)
            if response.status_code == 429 or code in _RATE_LIMITED:
                if attempt == 2:
                    break
                time.sleep(delay)
                delay *= 2
                continue
            return _data(response, self.brand)
        raise RuntimeError(f"{self.brand} rate-limited this chat three times in a row; try again later")


def _code(response) -> Optional[int]:
    try:
        return response.json().get("code")
    except ValueError:
        return None


def _data(response, brand: str = "Feishu") -> dict:
    try:
        body = response.json()
    except ValueError:
        raise RuntimeError(f"{brand} returned HTTP {response.status_code} without JSON")
    if body.get("code") != 0:
        raise RuntimeError(f"{brand} error {body.get('code')}: {body.get('msg')}")
    # Most endpoints wrap the payload in `data`; /bot/v3/info puts `bot` at the
    # top level beside code and msg. Accept both.
    data = body.get("data")
    if isinstance(data, dict):
        return data
    return {k: v for k, v in body.items() if k not in ("code", "msg")}


def _open_id(mention) -> Optional[str]:
    return getattr(getattr(mention, "id", None), "open_id", None)


def _text_of(message, mentions) -> str:
    """The text a person typed. @mentions arrive as placeholders like
    `@_user_1` with the name beside them; put the name back so the text reads
    as it did on screen. A non-text message is named by its type."""
    message_type = getattr(message, "message_type", None) or "text"
    try:
        content = json.loads(getattr(message, "content", None) or "{}")
    except ValueError:
        content = {}
    if message_type == "text":
        text = str(content.get("text", ""))
    elif message_type == "post":
        text = _post_text(content)
    else:
        text = f"[{message_type}]"
    # Keys are @_user_1, @_user_2, … so @_user_1 is a prefix of @_user_10:
    # longest key first, or a message tagging ten people loses the tenth.
    for mention in sorted(mentions, key=lambda m: -len(getattr(m, "key", None) or "")):
        key = getattr(mention, "key", None)
        name = getattr(mention, "name", None)
        if key:
            text = text.replace(key, f"@{name}" if name else "")
    return " ".join(text.split())


def _post_text(content: dict) -> str:
    """Rich text is paragraphs of runs; keep the text runs, drop the rest."""
    runs = []
    for paragraph in content.get("content", []) or []:
        for run in paragraph or []:
            if isinstance(run, dict) and run.get("tag") == "text":
                runs.append(str(run.get("text", "")))
        runs.append("\n")
    return "".join(runs).strip()


def _iso(create_time) -> str:
    try:
        return iso_utc(int(create_time) / 1000)
    except (TypeError, ValueError):
        return iso_utc()


def _raw_of(data) -> dict:
    """The provider payload as plain JSON. Raises if the SDK cannot marshal
    it; the caller logs that, so a missing `raw` is never silent."""
    return json.loads(_sdk().JSON.marshal(data))
