"""
Purpose: Discord as the owner's own account (experimental) — the Gateway as the web client, replies through the user REST API
LLM-Note:
  Dependencies: imports from [base64, json, os, random, signal, sys, time, uuid, datetime, httpx, inbox/discord.py (Discord, LIMIT), inbox/store.py] and lazily from [websockets] | imported by [inbox/__init__.py via provider() → account()] | tested by [tests/unit/test_inbox_discord_user.py]
  Data flow: account() → DiscordUser when a linked session or DISCORD_USER_TOKEN exists, else the bot Discord | run(inbox) → wss gateway v9 → Identify as the web client → READY (learns the account's DMs) → MESSAGE_CREATE in a DM, a group DM or an allowlisted channel → inbox.deliver() | send() → refuse unknown channels and over-cap sends → POST /typing → a pause scaled to the length → POST /messages
  State/Effects: <inbox>/user-session.json (0600: the token, written by `co discord link`) | user-channels.json (the DM and group-DM channels the listener has seen) | user-stopped.json (written when Discord disables, limits or challenges the account; while it exists nothing logs in) | reads DISCORD_USER_TOKEN and DISCORD_USER_CHANNELS
  Integration: the bot's Gateway loop, heartbeat, resume, backoff and message shape are inherited unchanged; only the identity (token without "Bot ", web-client properties and headers, v9) and the safety rules differ | the CLIENT constant is the one place to update when Discord ships a new web build
  Errors: a 401, a "verify your account"/"limited" code or a captcha from REST, and Gateway close 4004, record user-stopped.json, stop the listener and never log in again by themselves | refusals name why in one line and send nothing

Automating a user account is against Discord's terms (support article
115002192352) and can get the account limited or terminated. Everything here
is shaped by what gets accounts flagged in the wild: no new DMs, no friend
requests, no joining servers, guild channels only by allowlist, a typing
indicator and a pause before each message, a per-channel and a global cap,
and a session that stops for good the first time Discord objects.

The protocol was learned from discord.py-self (MIT) and the community docs at
docs.discord.food; the property values match beeper/discordgo's web-client
profile. No code was copied from them.
"""

import base64
import json
import os
import random
import signal
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import httpx

from .discord import FATAL_CLOSES, Discord
from .store import Inbox, default_home, iso_utc

API = "https://discord.com/api/v9"
GATEWAY = "wss://gateway.discord.gg/?encoding=json&v=9"

# The web client this account presents as. One constant, so a new Discord
# build is a one-line change. Values from the stable web client (Chrome 144,
# build 497254), as beeper/discordgo pins them; nothing is fetched at runtime.
CLIENT = {
    "chrome": "144.0.0.0",
    "client_build_number": 497254,
    "capabilities": 1734653,
    "locale": "en-US",
}

SESSION_FILE = "user-session.json"
CHANNELS_FILE = "user-channels.json"
STOPPED_FILE = "user-stopped.json"

# Sends in the last minute: per channel, and across the account.
PER_CHANNEL_PER_MINUTE = 3
PER_MINUTE = 10

# DM and group DM, the only channel types this account may write to unasked.
_PRIVATE = (1, 3)
_DISCORD_EPOCH_MS = 1420070400000

NO_SESSION = ("No Discord account is linked. Next: co discord link (shows a QR for the "
              "Discord phone app), or set DISCORD_BOT_TOKEN to use a bot instead")

USER_FATAL_CLOSES = {
    4004: "Discord rejected this account's token: it was logged out, its password changed, "
          "or the account was disabled or limited. co will not log in again by itself. "
          "Next: check the account in the official Discord app, then co discord link --yes",
    4012: FATAL_CLOSES[4012],
}


def account():
    """The Discord provider: your own account when one is linked, else the bot."""
    if _read(default_home("discord") / SESSION_FILE).get("token") or os.environ.get("DISCORD_USER_TOKEN"):
        return DiscordUser()
    return Discord()


class DiscordUser(Discord):
    """The owner's own Discord account, linked by `co discord link`."""

    fatal_closes = USER_FATAL_CLOSES

    def __init__(self, box: Optional[Inbox] = None, transport=None):
        super().__init__()
        self.box = box or Inbox("discord")
        session = _read(self.box.root / SESSION_FILE)
        self.token = session.get("token") or os.environ.get("DISCORD_USER_TOKEN", "")
        self.source = "co discord link" if session.get("token") else "DISCORD_USER_TOKEN"
        self._me_id = session.get("user_id")
        self._me_name = session.get("username")
        self._channels = set(_read(self.box.root / CHANNELS_FILE).get("private", []))
        self.http = httpx.Client(base_url=API, headers=self._headers(), timeout=15, transport=transport)
        self.sleep = time.sleep

    # ---- setup -------------------------------------------------------------

    def missing(self) -> list:
        stopped = _read(self.box.root / STOPPED_FILE)
        if stopped:
            return [f"Discord stopped this account's session on {stopped.get('at')}: {stopped.get('reason')}. "
                    "co will not log in again by itself. Next: check the account in the official "
                    "Discord app, then co discord link --yes"]
        return [] if self.token else [NO_SESSION]

    def check(self) -> list:
        problems = self.missing()
        if problems:
            return problems
        try:
            self.me()
        except RuntimeError as exc:
            problems.append(f"{exc}" if "Next:" in str(exc) else f"{exc}. Next: co discord link --yes")
        return problems

    def me(self) -> dict:
        result = self._result(self.http.get("/users/@me"))
        self._me_id = str(result.get("id", "")) or None
        self._me_name = result.get("username")
        return result

    def acting_as(self) -> str:
        who = f"@{self._me_name}" if self._me_name else "an unnamed account"
        return f"your own Discord account {who} (user session from {self.source}; experimental)"

    def _account(self) -> str:
        return f"@{self._me_name or self._me_id or 'unknown'} (your own account)"

    # ---- inbound -----------------------------------------------------------

    def _connect(self, websockets):
        # A user READY carries every guild and DM, far over the bot's 1 MiB.
        return websockets.connect(self._gateway_url(), open_timeout=15, close_timeout=5,
                                  max_size=64 * 1024 * 1024, user_agent_header=_user_agent(),
                                  additional_headers={"Origin": "https://discord.com",
                                                      "Accept-Language": "en-US,en;q=0.9"})

    def _gateway_url(self) -> str:
        base = self._resume_url or GATEWAY
        if "encoding=" in base:
            return base
        return f"{base}{'&' if '?' in base else '/?'}encoding=json&v=9"

    def _authentication_payload(self) -> dict:
        if self._session_id and self._sequence is not None:
            return super()._authentication_payload()
        return {
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": CLIENT["capabilities"],
                "properties": {**_properties(), "is_fast_connect": False},
                "presence": {"status": "invisible", "since": 0, "activities": [], "afk": False},
                "compress": False,
                "client_state": {"guild_versions": {}},
            },
        }

    def _dispatch(self, payload: dict, inbox: Inbox, *, raw: bool) -> None:
        event = payload.get("d") or {}
        kind = payload.get("t")
        if kind == "READY":
            self._learn(str(c.get("id")) for c in event.get("private_channels") or []
                        if c.get("type") in _PRIVATE)
            if event.get("auth_token"):
                self._refresh_token(str(event["auth_token"]))
        elif kind == "CHANNEL_CREATE" and event.get("type") in _PRIVATE:
            self._learn([str(event.get("id"))])
        elif kind == "MESSAGE_CREATE" and not self._wanted(event):
            return
        super()._dispatch(payload, inbox, raw=raw)

    def _wanted(self, event: dict) -> bool:
        """A DM or group DM, or a guild channel the owner allowlisted."""
        channel = str(event.get("channel_id", ""))
        if event.get("guild_id") is not None:
            return channel in _allowlist()
        self._learn([channel])
        return True

    def _learn(self, channels: Iterable[str]) -> None:
        fresh = {c for c in channels if c and c != "None"} - self._channels
        if not fresh:
            return
        self._channels |= fresh
        _write_private(self.box.root / CHANNELS_FILE, {"private": sorted(self._channels)})

    def _refresh_token(self, token: str) -> None:
        """Discord rotates the token in READY; the session file keeps the new one."""
        self.token = token
        self.http.headers["Authorization"] = token
        path = self.box.root / SESSION_FILE
        session = _read(path)
        if session.get("token"):
            _write_private(path, {**session, "token": token})

    def _stop(self, inbox: Inbox, code: int) -> None:
        if code == 4004:
            self._record_stopped("Gateway close 4004 (token rejected)")
        super()._stop(inbox, code)

    # ---- outbound ----------------------------------------------------------

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None, fresh: bool = False,
             plain: bool = False) -> str:
        """As the bot's send, after the refusals; then typing, a pause, the message."""
        self._refuse_unknown(chat)
        self._refuse_over_cap(chat)
        return super().send(chat, text, reply_to=reply_to, fresh=fresh, plain=plain)

    def _refuse_unknown(self, chat: str) -> None:
        if chat in self._channels or chat in _allowlist():
            return
        raise RuntimeError(
            f"refused: {chat} is not one of this account's existing DMs or group DMs, nor in "
            "DISCORD_USER_CHANNELS. As your own account co never opens a new DM, sends a friend "
            "request, joins a server or posts in other channels; nothing was sent. "
            "Next: co discord chats")

    def _refuse_over_cap(self, chat: str) -> None:
        now = time.time()
        recent = [r for r in self.box.recent_records(self.box.sent, 200)
                  if r.get("ok") and now - _epoch(r.get("at")) < 60]
        here = sum(1 for r in recent if r.get("chat") == chat)
        if here >= PER_CHANNEL_PER_MINUTE or len(recent) >= PER_MINUTE:
            raise RuntimeError(
                f"refused: rate cap, {here} sends to {chat} and {len(recent)} in all in the last minute "
                f"(caps {PER_CHANNEL_PER_MINUTE} per channel, {PER_MINUTE} in all, to look like a person); "
                "nothing was sent. Next: wait a minute, then co discord log")

    def _message_body(self, chat: str, text: str, reply_to: Optional[str], fresh: bool) -> dict:
        body = super()._message_body(chat, text, reply_to, fresh)
        body.setdefault("nonce", _snowflake())
        return {**body, "tts": False, "flags": 0}

    def _nonce(self, reply_to: str, text: str, fresh: bool) -> str:
        # The web client's nonces are snowflakes, digits only.
        return str(int(super()._nonce(reply_to, text, fresh)[:15], 16))

    def _post_message(self, chat: str, body: dict) -> str:
        response = self._post(f"/channels/{chat}/typing", None)
        self._fail_closed(response)
        if not 200 <= response.status_code < 300:
            self._result(response)  # Discord's own words for why it would not
        self.sleep(_typing_pause(body["content"]))
        return super()._post_message(chat, body)

    def _headers(self) -> dict:
        return web_headers(self.token)

    def _post(self, path: str, body: Optional[dict]):
        try:
            return self.http.post(path, json=body)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Discord request failed ({type(exc).__name__})") from None

    # ---- failing closed ------------------------------------------------------

    def _result(self, response) -> dict:
        self._fail_closed(response)
        return super()._result(response)

    def _fail_closed(self, response) -> None:
        why = _account_problem(response.status_code, _json_or_empty(response))
        if why is None:
            return
        self._record_stopped(why)
        self._stop_listener()
        raise RuntimeError(f"{why}. co stopped the Discord listener and will not log in again by itself. "
                           "Next: check the account in the official Discord app, then co discord link --yes")

    def _record_stopped(self, reason: str) -> None:
        _write_private(self.box.root / STOPPED_FILE, {"at": iso_utc(), "reason": reason})
        self.box.log(f"account stopped: {reason}")

    def _stop_listener(self) -> None:
        pid = self.box.listener_pid()
        if pid and pid != os.getpid():
            os.kill(pid, signal.SIGTERM)


def _account_problem(status: int, payload: dict) -> Optional[str]:
    """What Discord said about the account itself, or None for any other answer."""
    if "captcha_key" in payload:
        return "Discord asked this account for a captcha"
    if status == 401:
        return "Discord rejected this account's token (HTTP 401)"
    if payload.get("code") in (40001, 40002):
        return f"Discord limited this account (code {payload['code']}: {payload.get('message', '')})"
    if status == 403 and "disabled" in str(payload.get("message", "")).lower():
        return f"Discord disabled this account ({payload.get('message')})"
    return None


def _json_or_empty(response) -> dict:
    if not response.content:
        return {}
    try:
        payload = response.json()
    except ValueError:  # a Cloudflare page, not JSON
        return {}
    return payload if isinstance(payload, dict) else {}


def _allowlist() -> set:
    return {c.strip() for c in os.environ.get("DISCORD_USER_CHANNELS", "").split(",") if c.strip()}


def _typing_pause(text: str) -> float:
    """Seconds between "typing…" and the message: longer for longer text, under
    Discord's ten-second typing window, never the same twice."""
    return min(1.5 + 0.03 * len(text), 8.0) + random.uniform(0, 1.0)


def _snowflake() -> str:
    return str((int(time.time() * 1000) - _DISCORD_EPOCH_MS) << 22)


def _epoch(stamp) -> float:
    if not stamp:
        return 0.0
    return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()


# ---- the web client's identity ----------------------------------------------

_LAUNCH_ID = str(uuid.uuid4())


def _os() -> tuple:
    """(os, os_version, the user agent's platform part) for this machine:
    a user agent that disagrees with the machine is one more thing that looks odd."""
    if sys.platform == "darwin":
        return "Mac OS X", "10.15.7", "Macintosh; Intel Mac OS X 10_15_7"
    if sys.platform.startswith("win"):
        return "Windows", "10", "Windows NT 10.0; Win64; x64"
    return "Linux", "", "X11; Linux x86_64"


def _user_agent() -> str:
    return (f"Mozilla/5.0 ({_os()[2]}) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{CLIENT['chrome']} Safari/537.36")


def _properties() -> dict:
    name, version, _ = _os()
    return {
        "os": name, "browser": "Chrome", "device": "", "system_locale": CLIENT["locale"],
        "has_client_mods": False, "browser_user_agent": _user_agent(),
        "browser_version": CLIENT["chrome"], "os_version": version,
        "referrer": "", "referring_domain": "", "referrer_current": "", "referring_domain_current": "",
        "release_channel": "stable", "client_build_number": CLIENT["client_build_number"],
        "client_event_source": None, "client_launch_id": _LAUNCH_ID,
    }


def super_properties() -> str:
    return base64.b64encode(json.dumps(_properties(), separators=(",", ":")).encode()).decode()


def _timezone() -> Optional[str]:
    """The IANA zone name, as the browser reports it, or None when unknown."""
    if os.environ.get("TZ", "").count("/") == 1:
        return os.environ["TZ"]
    link = Path("/etc/localtime")
    if link.is_symlink():
        return str(os.readlink(link)).split("zoneinfo/", 1)[-1]
    return None


def web_headers(token: str = "") -> dict:
    """The headers the web client sends on every REST call."""
    headers = {
        "User-Agent": _user_agent(), "X-Super-Properties": super_properties(),
        "X-Discord-Locale": CLIENT["locale"], "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://discord.com", "Referer": "https://discord.com/channels/@me",
    }
    zone = _timezone()
    if zone:
        headers["X-Discord-Timezone"] = zone
    if token:
        headers["Authorization"] = token
    return headers


# ---- the session files -------------------------------------------------------

def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8") or "{}")
    return value if isinstance(value, dict) else {}


def _write_private(path: Path, value: dict) -> None:
    """Write a file only this user can read: it may hold the account's token."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle)
    os.chmod(path, 0o600)


def save_session(box: Inbox, token: str, user: dict, how: str) -> Path:
    """Keep a linked account: what `co discord link` writes. Clears a stop."""
    path = box.root / SESSION_FILE
    _write_private(path, {"token": token, "user_id": str(user.get("id", "")),
                          "username": user.get("username"), "linked_at": iso_utc(), "how": how})
    (box.root / STOPPED_FILE).unlink(missing_ok=True)
    return path
