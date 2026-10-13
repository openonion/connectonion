"""
Purpose: Outlook as an inbox (#1733) — Graph delta query on chosen folders writes files, replies go out through the Outlook tool
LLM-Note:
  Dependencies: imports from [os, time, json, fnmatch, asyncio, inbox/__init__.py (ListenerStopped), inbox/store.py, useful_tools/outlook.py (the token), charter (the `outlook` extra: Graph's delta, paging and delta links)] | imported by [inbox/__init__.py via provider()]
  Data flow: run(inbox) → for each folder: messages_delta(next_link=<saved delta link>) a page at a time until a delta_link → to_message() → sender filter → inbox.deliver() → save the delta link → sleep CO_OUTLOOK_EVERY | send() → Outlook().reply(reply_to) or Outlook().send(chat)
  State/Effects: one delta link per folder in <inbox>/outlook-delta.json, written only after a whole round was delivered, so a crash repeats a round (the inbox drops the duplicates) and never skips one | reads CO_OUTLOOK_FROM, CO_OUTLOOK_FOLDERS, CO_OUTLOOK_EVERY, CO_OUTLOOK_SINCE
  Integration: message ids are Graph message ids; chat is the conversationId, so the agent sees one email thread as one chat; reply_to is the message to answer
  Errors: a timeout or 5xx is logged and retried with backoff up to 5 min | Graph's 410 (sync state gone) restarts that folder from the last message it delivered, never from now | a refused grant (401, invalid_grant) ends the listener with ListenerStopped, because "no new mail" must never be the silent result of a dead token
"""

import asyncio
import fnmatch
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import ListenerStopped
from .store import Inbox, Message, iso_utc

# Why delta and not a search or a "last N" listing, from #1733: a last-10 window
# showed 7 of 24 student emails, and `$search` timed out repeatedly on a healthy
# network. A delta link names a point in the folder's history; following it
# returns exactly what was created since, a page at a time, however much that is.
SELECT = "subject,from,receivedDateTime,conversationId,bodyPreview,uniqueBody,isRead"

# A page, not a limit. Graph's `$top` on a delta round ends the round early and
# the messages past it are never returned; Charter's `max_page_size` sends
# `Prefer: odata.maxpagesize` instead, which pages through all of them.
PAGE = 50


class Outlook:
    """A personal Outlook mailbox, read through the same `co auth microsoft` grant the Outlook tool uses."""

    name = "outlook"
    unwired = {
        "edit": "Outlook cannot edit a sent message",
        "delete": "Graph has the endpoint for it (DELETE /me/messages/{id})",
        "react": "Graph has no reactions on mail",
    }

    def __init__(self, credentials=None):
        # Every option is an environment variable, like TELEGRAM_BOT_TOKEN, so
        # `co outlook listen` needs no flags of its own to work.
        self.senders = _split(os.environ.get("CO_OUTLOOK_FROM", ""))
        self.folders = _split(os.environ.get("CO_OUTLOOK_FOLDERS", "")) or ["inbox", "junkemail"]
        self.every = _seconds(os.environ.get("CO_OUTLOOK_EVERY", "30m"))
        self.since = os.environ.get("CO_OUTLOOK_SINCE", "")  # ISO date; first round only
        self.page = int(os.environ.get("CO_OUTLOOK_PAGE", PAGE))
        self._credentials = credentials

    # ---- setup -------------------------------------------------------------

    def missing(self) -> list:
        try:
            import charter  # noqa: F401
        except ImportError:
            return ["The Outlook inbox needs Charter for Graph's delta query. "
                    "Next: pip install 'connectonion[outlook]'"]
        return []

    def check(self) -> list:
        problems = self.missing()
        if problems:
            return problems
        try:
            self._run(self._tools().mail_folders_get.ainvoke({"folder_id": self.folders[0]}))
        except Exception as exc:
            problems.append(f"Outlook did not answer: {exc}. Next: co auth microsoft")
        return problems

    # ---- inbound -----------------------------------------------------------

    def run(self, inbox: Inbox, *, raw: bool = False) -> None:
        """Poll every folder once a round, forever. Blocks."""
        state = _State(inbox.root / "outlook-delta.json")
        inbox.log(f"watching {', '.join(self.folders)} every {self.every}s"
                  + (f" for {', '.join(self.senders)}" if self.senders else ""))
        delay = 5.0
        connected = False
        while True:
            try:
                for folder in self.folders:
                    self._round(inbox, state, folder, raw)
            except ListenerStopped:
                raise
            except Exception as exc:
                if _refused(exc):
                    inbox.record_connection("stopped", reason=str(exc))
                    raise ListenerStopped(f"Microsoft refused the grant: {exc}. Next: co auth microsoft") from None
                inbox.log(f"poll failed ({type(exc).__name__}: {exc}); retrying in {delay:.0f}s")
                if connected:
                    inbox.record_connection("disconnected", reason=str(exc))
                    connected = False
                time.sleep(delay)
                delay = min(delay * 2, 300.0)
                continue
            delay = 5.0
            if not connected:
                inbox.record_connection("connected", account="outlook")
                connected = True
            time.sleep(self.every)

    def _round(self, inbox: Inbox, state: "_State", folder: str, raw: bool) -> None:
        """One delta round on one folder: every page, then save where it ended."""
        tools = self._tools()
        link = state.link(folder)
        args = {"folder_id": folder, "next_link": link, "max_page_size": self.page} if link else self._first_round(state, folder)
        delivered = 0
        while True:
            try:
                page = self._run(tools.messages_delta.ainvoke(args))
            except Exception as exc:
                if _status(exc) == 410 and link:
                    # Graph forgot this sync state. Start the folder again from
                    # the last message we delivered rather than from now, so the
                    # gap is re-read instead of lost.
                    inbox.log(f"{folder}: sync state expired; re-reading from {state.last(folder)}")
                    state.forget(folder)
                    return self._round(inbox, state, folder, raw)
                raise
            for item in page.get("value", []):
                if "removed" in item:
                    continue
                message = self.to_message(item, raw=raw)
                if message is None or not self._wanted(message):
                    continue
                if inbox.deliver(message, raw=raw):
                    delivered += 1
                    inbox.log(f"received {message.id[-12:]} from={message.sender} folder={folder}")
                state.saw(folder, message.at)
            if page.get("next_link"):
                args = {"folder_id": folder, "next_link": page["next_link"], "max_page_size": self.page}
                continue
            # Saved only now: a crash mid-round repeats the round and the inbox
            # drops what it already holds; saving per page could skip mail.
            state.save(folder, page["delta_link"])
            if delivered:
                inbox.log(f"{folder}: {delivered} new")
            return

    def _first_round(self, state: "_State", folder: str) -> dict:
        """No saved link: start the folder's history at CO_OUTLOOK_SINCE, the
        last message delivered before a 410, or now — never at the beginning,
        which would answer years of mail."""
        start = state.last(folder) or self.since or iso_utc()
        return {"folder_id": folder, "change_type": "created", "select": SELECT,
                "max_page_size": self.page, "filter": f"receivedDateTime ge {_iso_z(start)}"}

    def _wanted(self, message: Message) -> bool:
        if not self.senders:
            return True
        address = message.sender.lower()
        return any(fnmatch.fnmatch(address, pattern.lower()) for pattern in self.senders)

    def to_message(self, item: dict, *, raw: bool = False) -> Optional[Message]:
        sender = item.get("from") or ""
        address, name = _parse_address(sender)
        if not address:
            return None
        unique = item.get("uniqueBody") or {}
        body = unique.get("content") if isinstance(unique, dict) else None
        text = "\n\n".join(part for part in (item.get("subject"), _text(body) or item.get("bodyPreview")) if part)
        return Message(
            id=item["id"],
            chat=item.get("conversationId") or item["id"],
            sender=address,
            sender_name=name,
            text=text or "[empty email]",
            at=item.get("receivedDateTime") or iso_utc(),
            mentioned=True,  # a mailbox has no group to be addressed in
            raw=item if raw else None,
        )

    # ---- outbound ----------------------------------------------------------

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None, fresh: bool = False,
             plain: bool = False) -> str:
        """Answer in the thread when reply_to is a received message id; otherwise
        `chat` is an address. Delegates to the Outlook tool, which already keeps
        Cc and threading right (#1247)."""
        from ..useful_tools.outlook import Outlook as OutlookTool
        tool = OutlookTool()
        if reply_to:
            tool.reply(reply_to, text)
            return reply_to
        tool.send(chat, "", text)
        return chat

    # ---- plumbing ----------------------------------------------------------

    def _tools(self):
        from charter.packs import outlook
        outlook.configure(self._credentials or _connectonion_grant())
        return outlook

    @staticmethod
    def _run(coroutine):
        return asyncio.run(coroutine)


class _State:
    """Per folder: the delta link to resume from, and the newest message
    delivered, for restarting after Graph drops a sync state."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = json.loads(path.read_text())
        except (OSError, ValueError):
            self.data = {}

    def link(self, folder: str) -> Optional[str]:
        return (self.data.get(folder) or {}).get("delta_link")

    def last(self, folder: str) -> Optional[str]:
        return (self.data.get(folder) or {}).get("last_received")

    def saw(self, folder: str, received: str) -> None:
        entry = self.data.setdefault(folder, {})
        if received > (entry.get("last_received") or ""):
            entry["last_received"] = received

    def forget(self, folder: str) -> None:
        self.data.setdefault(folder, {}).pop("delta_link", None)
        self._write()

    def save(self, folder: str, link: str) -> None:
        self.data.setdefault(folder, {})["delta_link"] = link
        self._write()

    def _write(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        os.replace(tmp, self.path)


def _connectonion_grant():
    """The `co auth microsoft` grant, refreshed by the Outlook tool's own logic."""
    from charter.auth import CallbackProvider, Credentials
    from ..useful_tools.outlook import Outlook as OutlookTool
    tool = OutlookTool()
    return CallbackProvider(lambda _provider: Credentials(token=tool._get_access_token()))


def _parse_address(value: str):
    """Charter renders a sender as "Name <address>" or a bare address."""
    if "<" in value and value.endswith(">"):
        name, address = value[:-1].split("<", 1)
        return address.strip(), name.strip()
    return value.strip(), ""


def _text(html: Optional[str]) -> str:
    if not html:
        return ""
    from charter.text import html_to_text
    return html_to_text(html).strip()


def _split(value: str) -> list:
    return [part.strip() for part in value.split(",") if part.strip()]


def _seconds(value: str) -> int:
    value = value.strip().lower()
    units = {"s": 1, "m": 60, "h": 3600}
    if value and value[-1] in units:
        return int(float(value[:-1]) * units[value[-1]])
    return int(value or 1800)


def _iso_z(value: str) -> str:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status(exc: Exception) -> Optional[int]:
    return getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)


def _refused(exc: Exception) -> bool:
    from charter.types.errors import CredentialError
    return isinstance(exc, CredentialError) or _status(exc) == 401
