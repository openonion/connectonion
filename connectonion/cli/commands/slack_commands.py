"""
Purpose: `co slack channels | history | thread | search` — read a Slack workspace through Slack's Web API, trimmed for an agent
LLM-Note:
  Dependencies: imports from [json, os, re, sys, time, datetime, itertools, urllib.parse, httpx, inbox/slack.py (API, APPS, scopes, token messages), inbox/store.py (iso_utc)] | imported by [cli/main.py (the slack group), cli/commands/slack_auth.py (SlackWeb, refuse)] | tested by [tests/unit/test_slack_read_commands.py]
  Data flow: channels → conversations.list | history → conversations.history | thread → conversations.replies | search → search.messages (user token) → one record per message {id "<channel>:<ts>", chat, thread, at, sender, sender_name, text, replies} → lines for a person, or one JSON object per line with --json | the Next: line comes after the results: stdout, or stderr under --json
  State/Effects: Read-only: nothing is posted, nothing is written to disk | reads SLACK_BOT_TOKEN (xoxb-) and, for search.messages only, SLACK_USER_TOKEN (xoxp-), each through environment.setting() so a --secret value counts | users.info with the bot token, once per user id per run
  Integration: ids are the inbox's own "<channel>:<ts>", so `co slack send <channel> --reply-to <id>` answers in the message's thread | the token is only ever in an Authorization header
  Errors: Slack's ok:false becomes one sentence and a next command, exit 1 (missing_scope names the scope Slack said it needed; not_in_channel the /invite step; channel_not_found `co slack channels`; a rejected token `co auth slack`) | a missing or misplaced token is named before any request | one HTTP 429 is waited out (Retry-After, at most 30s)
"""

import json
import re
import sys
import time
from datetime import datetime
from itertools import islice
from typing import Callable, Iterator, Optional
from urllib.parse import parse_qs, urlparse

import httpx

from ...inbox.slack import API, APPS, WRONG_BOT_TOKEN
from ...environment import setting
from ...inbox.store import iso_utc
from .. import style
from .command_tips import mark_next_step_named, print_tip, selected_tip

# Tests put an httpx.MockTransport here; None is the network.
transport = None

_CHANNEL_ID = re.compile(r"^[CGD][A-Z0-9]{8,}$")
_USER_ID = re.compile(r"^[UW][A-Z0-9]{8,}$")
_MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")
_REJECTED = {"invalid_auth", "not_authed", "token_revoked", "token_expired", "account_inactive"}

NO_BOT_TOKEN = ("SLACK_BOT_TOKEN is not set. Reading channels needs your Slack app's Bot User OAuth "
                "Token (xoxb-…). Next: co auth slack")
NO_USER_TOKEN = (
    "co slack search needs SLACK_USER_TOKEN, a user token (xoxp-…) with the scope search:read: "
    "Slack's search.messages runs as a person and refuses bot tokens. At "
    f"{APPS} open your app → OAuth & Permissions → User Token Scopes, add search:read, Reinstall to "
    "Workspace, and paste the User OAuth Token when asked. Next: co auth slack"
)
WRONG_USER_TOKEN = ("SLACK_USER_TOKEN does not start with xoxp-. It must be the User OAuth Token "
                    "(xoxp-…, from OAuth & Permissions), not the bot token (xoxb-…). Next: co auth slack")


class SlackWeb:
    """Slack's Web API with one token. Display names are looked up once per run."""

    def __init__(self, token: str, which: str):
        self.which = which  # the env name, for error messages: never the token itself
        self.http = httpx.Client(base_url=API, transport=transport, timeout=15,
                                 headers={"Authorization": f"Bearer {token}"})
        self.names: dict = {}

    def post(self, method: str, **params) -> httpx.Response:
        response = self.http.post(f"/{method}", data=params)
        if response.status_code == 429:  # honour Slack's own wait once; a second is reported
            time.sleep(min(float(response.headers.get("Retry-After", "1")), 30.0))
            response = self.http.post(f"/{method}", data=params)
        return response

    def call(self, method: str, **params) -> dict:
        result = self.post(method, **params).json()
        if not result.get("ok"):
            refuse(method, result, params, self.which)
        return result

    def each(self, method: str, key: str, **params) -> Iterator[dict]:
        """Every item under `key`, following Slack's cursor page by page."""
        cursor = None
        while True:
            result = self.call(method, **params, **({"cursor": cursor} if cursor else {}))
            yield from result.get(key) or []
            cursor = (result.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return

    def name_of(self, user: str) -> str:
        if user not in self.names:
            found = self.call("users.info", user=user)["user"]
            profile = found.get("profile") or {}
            self.names[user] = (profile.get("display_name") or profile.get("real_name")
                                or found.get("name") or user)
        return self.names[user]


def refuse(method: str, result: dict, params: dict, which: str) -> None:
    """Slack's ok:false as one sentence and the command to run next. Exits 1."""
    error = str(result.get("error") or "unknown_error")
    channel = params.get("channel", "")
    if error == "missing_scope":
        needed = result.get("needed") or "a scope Slack did not name"
        person = which == "SLACK_USER_TOKEN"
        where, then = ("User Token Scopes", "co auth slack") if person else ("Bot Token Scopes", "co slack check")
        text = (f"{which} lacks the scope {needed}, which {method} needs: at {APPS} open your app → "
                f"OAuth & Permissions → {where}, add it, then Reinstall to Workspace. Next: {then}")
    elif error == "not_in_channel":
        text = (f"The bot is not in {channel}. In Slack, open that channel and type /invite @<your bot>. "
                "Next: co slack channels")
    elif error == "channel_not_found":
        text = f"Slack has no channel {channel} this token can see. Next: co slack channels"
    elif error == "thread_not_found":
        text = f"Slack has no message {params.get('ts')} in {channel}. Next: co slack history {channel}"
    elif error in _REJECTED:
        text = f"Slack rejected {which} ({error}). Next: co auth slack"
    elif error == "ratelimited":
        text = f"Slack is rate-limiting {method}; wait a minute and run it again. Next: co slack check"
    else:
        text = f"Slack refused {method}: {error}. Next: co slack check"
    print(text, file=sys.stderr)
    sys.exit(1)


def _fail(text: str) -> None:
    print(text, file=sys.stderr)
    sys.exit(1)


def _next(command: str, json_output: bool) -> None:
    """The Next: line, after the results: on stdout, so a pipe reads it last;
    on stderr under --json, so stdout stays parseable."""
    if not json_output:
        print_tip(f"Next: {command}")
        return
    style.console(stderr=True).print(style.markup(f"Next: {selected_tip(command)}"))
    mark_next_step_named()


def bot() -> SlackWeb:
    token = setting("SLACK_BOT_TOKEN") or ""
    if not token:
        _fail(NO_BOT_TOKEN)
    if not token.startswith("xoxb-"):
        _fail(WRONG_BOT_TOKEN)
    return SlackWeb(token, "SLACK_BOT_TOKEN")


def user() -> SlackWeb:
    token = setting("SLACK_USER_TOKEN") or ""
    if not token:
        _fail(NO_USER_TOKEN)
    if not token.startswith("xoxp-"):
        _fail(WRONG_USER_TOKEN)
    return SlackWeb(token, "SLACK_USER_TOKEN")


# ---- records ---------------------------------------------------------------

def record(message: dict, chat: str, name_of: Callable[[str], str], thread: Optional[str] = None) -> dict:
    """One message as the agent reads it: who, when, what, and the id to answer with."""
    ts = str(message["ts"])
    root = str(message.get("thread_ts") or thread or "")
    author = message.get("user")
    text = message.get("text") or ("[file]" if message.get("files") else "")
    return {
        "id": f"{chat}:{ts}",
        "chat": chat,
        "thread": root if root and root != ts else None,
        "at": iso_utc(float(ts)),
        "sender": author or message.get("bot_id") or "",
        "sender_name": name_of(author) if author else _bot_name(message),
        "text": _MENTION.sub(lambda m: "@" + name_of(m.group(1)), text),
        "replies": int(message.get("reply_count") or 0),
    }


def _bot_name(message: dict) -> str:
    return (message.get("bot_profile") or {}).get("name") or message.get("username") or "bot"


def show(records: list, json_output: bool) -> None:
    for item in records:
        if json_output:
            print(json.dumps(item, ensure_ascii=False))
            continue
        when = datetime.fromtimestamp(float(item["id"].rpartition(":")[2])).strftime("%Y-%m-%d %H:%M")
        where = f"#{item['chat_name']}  " if item.get("chat_name") else ""
        count = item.get("replies")
        replies = f"  ({count} {'reply' if count == 1 else 'replies'})" if count else ""
        print(f"{when}  {where}{item['sender_name']}  {item['id']}{replies}")
        for line in item["text"].splitlines() or [""]:
            print(f"  {line}")


def channel_id(web: SlackWeb, channel: str) -> str:
    """An id as given; `#ops` or `ops` looked up among the channels the token can see."""
    if _CHANNEL_ID.match(channel):
        return channel
    name = channel.lstrip("#")
    for found in web.each("conversations.list", "channels", types="public_channel,private_channel",
                          exclude_archived="true", limit=200):
        if found.get("name") == name:
            return found["id"]
    _fail(f"No channel #{name} that the bot can see. Next: co slack channels")


# ---- verbs -----------------------------------------------------------------

def handle_channels(json_output: bool) -> None:
    web = bot()
    rows = []
    for found in web.each("conversations.list", "channels", types="public_channel,private_channel,im",
                          exclude_archived="true", limit=200):
        if found.get("is_im"):
            rows.append({"id": found["id"], "name": "@" + web.name_of(found["user"]), "kind": "im",
                         "members": None})
        elif found.get("is_member"):
            rows.append({"id": found["id"], "name": "#" + found.get("name", ""),
                         "kind": "private" if found.get("is_private") else "public",
                         "members": found.get("num_members")})
    for row in rows:
        if json_output:
            print(json.dumps(row, ensure_ascii=False))
        else:
            members = "" if row["members"] is None else f"{row['members']} members"
            print(f"{row['id']}\t{row['name']}\t{row['kind']}\t{members}")
    if not rows and not json_output:
        print("The bot is in no channel and has no direct messages. In Slack, type /invite @<your bot> "
              "in a channel.", file=sys.stderr)
    _next("co slack history <channel> -n 50", json_output)


def handle_history(channel: str, last: int, json_output: bool) -> None:
    web = bot()
    chat = channel_id(web, channel)
    newest_first = islice(web.each("conversations.history", "messages", channel=chat, limit=min(last, 200)),
                          last)
    records = [record(message, chat, web.name_of) for message in reversed(list(newest_first))]
    show(records, json_output)
    threaded = next((item["id"] for item in records if item["replies"]), None)
    _next(f"co slack thread {threaded}" if threaded else
          f'co slack send {chat} "<text>" --reply-to <message-id>', json_output)


def handle_thread(message_id: str, json_output: bool) -> None:
    channel, _, ts = message_id.rpartition(":")
    if not channel or not ts:
        print(f"{message_id} is not a message id; it looks like C0123456789:1727500000.123456, as "
              "history and search print it. Next: co slack channels", file=sys.stderr)
        sys.exit(2)
    web = bot()
    chat = channel_id(web, channel)
    messages = list(web.each("conversations.replies", "messages", channel=chat, ts=ts, limit=200))
    root = str(messages[0].get("thread_ts") or "") if messages else ""
    if root and root != str(messages[0]["ts"]):
        # Slack answered with the reply alone; read the thread from its root.
        messages = list(web.each("conversations.replies", "messages", channel=chat, ts=root, limit=200))
    records = [record(message, chat, web.name_of) for message in messages]
    show(records, json_output)
    root = records[0]["id"] if records else message_id
    _next(f'co slack send {chat} "<text>" --reply-to {root}', json_output)


def search_query(text: str, where: Optional[str], who: Optional[str]) -> str:
    """Slack's own search modifiers: in:<#C…> or in:#name, from:<@U…> or from:@name."""
    parts = [text]
    if where:
        parts.append(f"in:<#{where}>" if _CHANNEL_ID.match(where) else f"in:#{where.lstrip('#')}")
    if who:
        parts.append(f"from:<@{who}>" if _USER_ID.match(who) else f"from:@{who.lstrip('@')}")
    return " ".join(parts)


def handle_search(text: str, where: Optional[str], who: Optional[str], last: int, json_output: bool) -> None:
    web = user()
    names = bot()  # users:read is a bot scope; the user token needs only search:read
    result = web.call("search.messages", query=search_query(text, where, who), count=last,
                      sort="timestamp", sort_dir="desc")
    records = []
    for match in (result.get("messages") or {}).get("matches") or []:
        found = match.get("channel") or {}
        thread = parse_qs(urlparse(match.get("permalink") or "").query).get("thread_ts", [None])[0]
        item = record(match, found.get("id", ""), names.name_of, thread=thread)
        item["chat_name"] = found.get("name") if not found.get("is_im") else None
        del item["replies"]  # search does not say; 0 would be a guess
        records.append(item)
    show(records, json_output)
    if not records:
        print(f"Slack found nothing for: {search_query(text, where, who)}", file=sys.stderr)
        _next('co slack search "<other words>"', json_output)
        return
    _next(f"co slack thread {records[0]['id']}", json_output)
