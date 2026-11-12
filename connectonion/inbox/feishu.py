"""
Purpose: Feishu and Lark as an inbox — the official SDK's long connection writes files, replies go out through the REST API
LLM-Note:
  Dependencies: imports from [json, os, time, uuid, datetime, requests, inbox/store.py] and lazily from [lark_oapi] | imported by [inbox/__init__.py via provider()] | tested by [tests/unit/test_inbox_feishu.py]
  Data flow: run(inbox) → lark_oapi.ws.Client long connection → im.message.receive_v1 event → to_message() → inbox.deliver(); reaction/recall/chat-member/chat-updated events → event_message() → inbox.deliver(); start/reconnect → HistoryRecovery.reconcile() (bounded, no timer) | send()/reply → tenant token → POST /open-apis/im/v1/messages or /messages/{id}/reply → message_id
  State/Effects: reads FEISHU_APP_ID/FEISHU_APP_SECRET (LARK_* for Lark) from the environment | one outbound WebSocket that dials out, so no port is opened | caches the tenant token in memory for its lifetime
  Integration: the same class serves `co feishu` and `co lark`; only the domain and the env prefix differ | the event handler does nothing but convert and write, acknowledgement follows the durable inbox write; storage failures remain retryable
  Errors: check() returns the missing item and the next action instead of raising | send() raises RuntimeError with Feishu's own code and message, after retrying a rate limit three times | a missing SDK is reported with the pip command
"""

import hashlib
import json
import os
import re
import time
import uuid
from typing import Optional

import requests

from .store import Inbox, Message, iso_utc
from .recovery import HistoryRecovery, LarkError, MissingScope

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
                    f"{self.env_prefix}_{key} is not set. "
                    f"Next: co auth {self.name} — scan a QR and the application is "
                    f"created with both values saved. To authorize one you already "
                    f"have: co auth {self.name} --app-id cli_…  "
                    f"To build one by hand instead: {self.base}/app"
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

    def run(self, inbox: Inbox, *, raw: bool = False) -> None:
        """Hold the long connection and write every message. Blocks."""
        lark = _sdk()
        try:
            info = self.bot_info()
            inbox.log(f"connected as {info.get('name') or self.app_id}")
        except CredentialsRefused as exc:
            # Feishu answered and said no: wrong app_id, wrong secret, app not
            # published. Dialling the WebSocket with the same pair cannot
            # succeed, and the SDK would retry it every two minutes forever,
            # each attempt a "connect failed" line that hides the real reason.
            inbox.log(f"bot info failed: {exc}")
            raise
        except Exception as exc:
            # Anything else is a bad minute, not a bad key: a 502 page from
            # the edge, a rate limit on the info call, no answer at all. The
            # long connection has its own reconnect and may well get
            # through; only the own-@mention check runs without the bot's
            # open_id until then.
            inbox.log(f"bot info failed: {exc}")

        recovery = HistoryRecovery(self, inbox, raw=raw)

        def on_message(data) -> None:
            # Parsing failures must not raise. The SDK answers a
            # raising handler with HTTP 500, and Feishu treats 500 as "not
            # delivered" and sends the same event again for hours. A payload
            # we cannot read is one log line, never a retry storm.
            try:
                message = self.to_message(data)
            except Exception as exc:
                inbox.log(f"event not understood ({type(exc).__name__}: {exc}); skipped")
                return
            if message is None:
                return
            recovery.note_chat(message.chat, getattr(data.event.message, 'chat_type', None))
            if raw:
                try:
                    message.raw = _raw_of(data)
                except Exception as exc:
                    inbox.log(f"raw payload of {message.id} not kept: {exc}")
            # deliver() is left to raise on a full or unwritable disk: that
            # is the one case where "not delivered, send it again" is true.
            if inbox.deliver(message, raw=raw):
                inbox.log(f"received {message.id} chat={message.chat} sender={message.sender}")
            else:
                inbox.log(f"duplicate {message.id} dropped")

        # Things that happen in a chat which are not somebody typing, recorded
        # with their own `kind` the way the WhatsApp listener records them, so
        # a consumer reading a conversation back sees "she recalled that" and
        # "the bot was added". Only being added is addressed to us. Read
        # receipts and reaction removals are acknowledged and dropped: without
        # a processor the SDK answered "processor not found" and Lark retried
        # each one (#1618).
        def note(event_type):
            def handle(data) -> None:
                try:
                    message = self.event_message(event_type, data, inbox)
                except Exception as exc:
                    inbox.log(f"{event_type} event not understood ({type(exc).__name__}: {exc}); skipped")
                    return
                if message is None:
                    return
                if inbox.deliver(message):
                    inbox.log(f"received {event_type} {message.id} chat={message.chat}")
                else:
                    inbox.log(f"duplicate {message.id} dropped")
            return handle

        def ignore(data) -> None:
            return None

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .register_p2_im_message_reaction_created_v1(note("reaction"))
            .register_p2_im_message_recalled_v1(note("recall"))
            .register_p2_im_chat_member_bot_added_v1(note("bot-added"))
            .register_p2_im_chat_member_bot_deleted_v1(note("bot-removed"))
            .register_p2_im_chat_member_user_added_v1(note("user-added"))
            .register_p2_im_chat_member_user_deleted_v1(note("user-removed"))
            .register_p2_im_chat_member_user_withdrawn_v1(note("user-left"))
            .register_p2_im_chat_updated_v1(note("chat-updated"))
            .register_p2_im_chat_disbanded_v1(note("chat-disbanded"))
            .register_p2_im_message_reaction_deleted_v1(ignore)
            .register_p2_im_message_message_read_v1(ignore)
            .build()
        )
        client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=handler,
            domain=self.base,
            log_level=lark.LogLevel.WARNING,
        )

        def reconnecting():
            inbox.log("reconnecting")
            recovery.disconnected()

        def reconnected():
            inbox.log("reconnected; reconciling known conversation history")
            recovery.connected()
            recovery.request()

        client.on_reconnecting = reconnecting
        client.on_reconnected = reconnected
        recovery.start()
        recovery.connected()
        try:
            client.start()
        finally:
            recovery.stop()

    def event_message(self, event_type: str, data, inbox: Inbox) -> Optional[Message]:
        """A chat event as a Message with its own kind, or None when it is
        ours or names a message this inbox has never seen. The id is Lark's
        event_id, so a redelivered event is recorded once."""
        event = data.event
        header = data.header
        name = getattr(event, "name", None) or ""
        if event_type == "reaction":
            if getattr(event, "operator_type", "user") != "user":
                return None  # our own SEEN/ANSWERING marks coming back
            target = event.message_id
            known = inbox.lookup(target)
            chat = known.chat if known else (inbox.lookup_sent(target) or {}).get("chat")
            if not chat:
                inbox.log(f"reaction on {target} not recorded: that message is not in this inbox")
                return None
            emoji = getattr(event.reaction_type, "emoji_type", "") or ""
            kind, text, mentioned, operator = "reaction", f"reacted {emoji} to {target}", False, event.user_id
        elif event_type == "recall":
            chat, operator = event.chat_id, None
            kind, text, mentioned = "recall", f"recalled {event.message_id}", False
        elif event_type == "bot-added":
            chat, operator = event.chat_id, event.operator_id
            kind, text, mentioned = "joined", f"added to {name}".strip(), True
        else:
            chat, operator = event.chat_id, event.operator_id
            kind, mentioned = "group-info", False
            text = _group_change(event_type, event, name)
        return Message(
            id=str(header.event_id),
            chat=str(chat),
            sender=_user_id(operator),
            text=text,
            kind=kind,
            mentioned=mentioned,
            at=_iso(getattr(header, "create_time", None)),
        )

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
        content = _content_of(message)
        text = _text_of(message, mentions, content)
        attachments = _attachments_of(message, content)
        kind = getattr(message, "message_type", None) or "text"
        if kind == "post" and not attachments and text:
            kind = "text"
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
            kind=kind,
            attachments=attachments or None,
            sender_ids={key: value for key in ("union_id", "open_id")
                        if isinstance(value := getattr(sender_id, key, None), str) and value} or None,
            mentioned=mentioned,
            at=_iso(create_time),
            raw=_raw_of(data) if raw else None,
        )

    # ---- outbound ----------------------------------------------------------

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None, fresh: bool = False,
             plain: bool = False) -> str:
        """Send text to a chat, or as a reply to a message. Returns the new
        message id. `fresh` is `reply --again`: a deliberate second post,
        even of the same words.

        The text is Markdown, because a model writes Markdown: it goes out
        as a `post` whose one `md` element Feishu renders (bold, lists,
        links, code). A `text` message would show the `**` raw (#1872).
        `plain` sends a `text` message, the characters exactly as typed."""
        if plain:
            msg_type, content = "text", {"text": text}
        else:
            msg_type, content = "post", {"zh_cn": {"content": [[{"tag": "md", "text": text}]]}}
        content = json.dumps(content, ensure_ascii=False)
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
                "msg_type": msg_type,
                "content": content,
                "uuid": key,
            }
            result = self._post(f"/open-apis/im/v1/messages/{reply_to}/reply", body)
        else:
            body = {
                "receive_id": chat,
                "msg_type": msg_type,
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
    if body.get("code") == 230027:
        raise MissingScope(f"{brand} error 230027: {body.get('msg')}")
    if body.get("code") != 0:
        raise LarkError(f"{brand} error {body.get('code')}: {body.get('msg')}", body.get("code"))
    # Most endpoints wrap the payload in `data`; /bot/v3/info puts `bot` at the
    # top level beside code and msg. Accept both.
    data = body.get("data")
    if isinstance(data, dict):
        return data
    return {k: v for k, v in body.items() if k not in ("code", "msg")}


def _open_id(mention) -> Optional[str]:
    return getattr(getattr(mention, "id", None), "open_id", None)


def _content_of(message) -> dict:
    try:
        content = json.loads(getattr(message, "content", None) or "{}")
    except ValueError:
        return {}
    return content if isinstance(content, dict) else {}


def _text_of(message, mentions, content) -> str:
    """Keep typed words and readable mentions; name non-text messages by type."""
    message_type = getattr(message, "message_type", None) or "text"
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
    """Read the selected rich-text body; resource references travel separately."""
    content = next((body for body in _post_bodies(content) if body.get("title") or body.get("content")), content)
    runs = [str(content.get("title") or ""), "\n"]
    for paragraph in content.get("content", []) or []:
        for run in paragraph or []:
            if isinstance(run, dict) and run.get("tag") == "text":
                runs.append(str(run.get("text", "")))
        runs.append("\n")
    return "".join(runs).strip()


def _post_bodies(content):
    return [content, *(body for locale, body in content.items()
                       if re.fullmatch(r"[a-z]{2}_[a-z]{2}", locale)
                       and isinstance(body, dict) and any(key in body for key in ("title", "content", "files")))]


def _attachments_of(message, content):
    """Only resource type/key/name cross into consumer input, never arbitrary raw."""
    kind = getattr(message, "message_type", None)
    if kind == "image":
        return _resource("image", content.get("image_key"))
    if kind in {"file", "audio", "media"}:
        return _resource(kind, content.get("file_key"), content.get("file_name"))
    if kind != "post":
        return []
    resources = []
    for body in _post_bodies(content):
        for item in body.get("files", []) or []:
            if isinstance(item, dict):
                item_type = "folder" if item.get("is_folder") is True else "file"
                resources.extend(_resource(item_type, item.get("file_key"), item.get("file_name")))
        for row in body.get("content", []) or []:
            for item in row or []:
                if isinstance(item, dict) and item.get("tag") == "img":
                    resources.extend(_resource("image", item.get("image_key")))
                if isinstance(item, dict) and item.get("tag") == "media":
                    resources.extend(_resource("media", item.get("file_key")))
    return list({(item["type"], item["key"]): item for item in resources}.values())


def _resource(kind, key, name=None):
    if not isinstance(key, str) or not key:
        return []
    item = {"type": kind, "key": key}
    if isinstance(name, str) and name:
        item["name"] = name
    return [item]


def _user_id(user_id) -> str:
    return str(getattr(user_id, "union_id", None) or getattr(user_id, "open_id", None) or "")


def _group_change(event_type, event, name) -> str:
    """What changed in a group, in words: who came, who went, what was renamed."""
    people = ", ".join(getattr(user, "name", None) or _user_id(getattr(user, "user_id", None))
                       for user in getattr(event, "users", None) or [])
    if event_type == "user-added":
        return f"{people} joined {name}".strip()
    if event_type == "user-removed":
        return f"{people} removed from {name}".strip()
    if event_type == "user-left":
        return f"{people} left {name}".strip()
    if event_type == "bot-removed":
        return f"removed from {name}".strip()
    if event_type == "chat-disbanded":
        return f"group {name} disbanded".replace("  ", " ")
    renamed = getattr(getattr(event, "after_change", None), "name", None)
    return f"group renamed to {renamed}" if renamed else "group changed"


def _iso(create_time) -> str:
    try:
        return iso_utc(int(create_time) / 1000)
    except (TypeError, ValueError):
        return iso_utc()


def _raw_of(data) -> dict:
    """The provider payload as plain JSON. Raises if the SDK cannot marshal
    it; the caller logs that, so a missing `raw` is never silent."""
    return json.loads(_sdk().JSON.marshal(data))
