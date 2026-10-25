"""
Purpose: Outlook as an inbox (#1733) — Graph delta query on chosen folders writes files, replies go out through the Outlook tool
LLM-Note:
  Dependencies: imports from [os, time, json, fnmatch, httpx, inbox/__init__.py (ListenerStopped), inbox/store.py, provider_credentials.py (ProviderCredentialError), useful_tools/outlook.py (the Graph client: token, refresh, retries)] | imported by [inbox/__init__.py via provider()] | tested by [tests/unit/test_inbox_outlook.py]
  Data flow: run(inbox) → for each folder: GET /me/mailFolders/{folder}/messages/delta through Outlook._request(), following @odata.nextLink a page at a time until @odata.deltaLink → to_message() → sender filter → inbox.deliver() → save the delta link → sleep CO_OUTLOOK_EVERY | send() → Outlook().reply(reply_to)
  State/Effects: one delta link per folder in <inbox>/outlook-delta.json, written only after a whole round was delivered, so a crash repeats a round (the inbox drops the duplicates) and never skips one | reads CO_OUTLOOK_FROM, CO_OUTLOOK_FOLDERS, CO_OUTLOOK_EVERY, CO_OUTLOOK_SINCE
  Integration: message ids are Graph message ids; chat is the conversationId, so the agent sees one email thread as one chat; reply_to is the message to answer
  Errors: a timeout, a dropped connection, 429 or 5xx is logged and retried with backoff up to 5 min | Graph's 410 (sync state gone) restarts that folder from the last message it delivered, never from now | any other refusal (a grant Microsoft no longer accepts, a folder that does not exist) ends the listener with ListenerStopped, because "no new mail" must never be the silent result of a dead token | send() without reply_to raises ValueError
"""

import fnmatch
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from ..provider_credentials import ProviderCredentialError
from ..useful_tools.outlook import Outlook as OutlookTool
from . import ListenerStopped
from .store import Inbox, Message, iso_utc

# Why delta and not a search or a "last N" listing, from #1733: a last-10 window
# showed 7 of 24 student emails, and `$search` timed out repeatedly on a healthy
# network. A delta link names a point in the folder's history; following it
# returns exactly what was created since, a page at a time, however much that is.
SELECT = "subject,from,receivedDateTime,conversationId,bodyPreview,uniqueBody,isRead"

# A page size, not a limit. `$top` on a delta round ends the round early, and the
# messages past it are never returned; the Prefer header pages through all of
# them. The same header asks for bodies as text, so no HTML reaches the inbox.
PREFER = {"Prefer": 'odata.maxpagesize=50, outlook.body-content-type="text"'}

# What is worth waiting out: throttling, and a gateway that gave up. Every other
# refusal needs a person (a revoked grant, a folder that does not exist), so the
# listener stops rather than polling the same refusal forever.
TRANSIENT = {429, 500, 502, 503, 504}


class Outlook:
    """A personal Outlook mailbox, read with the Outlook tool's own `co auth microsoft` grant."""

    name = "outlook"
    unwired = {
        "edit": "Outlook cannot edit a sent message",
        "delete": "Graph has the endpoint for it (DELETE /me/messages/{id})",
        "react": "Graph has no reactions on mail",
    }

    def __init__(self):
        # Every option is an environment variable, like TELEGRAM_BOT_TOKEN, so
        # `co outlook listen` needs no flags of its own to work.
        self.senders = _split(os.environ.get("CO_OUTLOOK_FROM", ""))
        self.folders = _split(os.environ.get("CO_OUTLOOK_FOLDERS", "")) or ["inbox", "junkemail"]
        self.every = _seconds(os.environ.get("CO_OUTLOOK_EVERY", "30m"))
        self.since = os.environ.get("CO_OUTLOOK_SINCE", "")  # ISO date; first round only
        self._outlook: Optional[OutlookTool] = None

    # ---- setup -------------------------------------------------------------

    def missing(self) -> list:
        """The grant `co auth microsoft` has not given yet, in the Outlook tool's own words."""
        try:
            self._tool()
        except ValueError as exc:  # the tool's "not connected" and "no Mail scope", each naming its fix
            return [_said(exc)]
        return []

    def check(self) -> list:
        problems = self.missing()
        if problems:
            return problems
        for folder in self.folders:
            try:
                self._tool()._request("GET", f"/me/mailFolders/{folder}", params={"$select": "id"})
            except ProviderCredentialError as exc:
                if exc.status == 404:
                    problems.append(f"Outlook has no folder {folder!r}. CO_OUTLOOK_FOLDERS takes "
                                    "well-known names (inbox, junkemail) or folder ids. Next: co outlook check")
                else:
                    problems.append(_said(exc))
            except httpx.TransportError as exc:
                problems.append(f"Outlook did not answer ({type(exc).__name__}). Next: co outlook check")
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
            except (httpx.TransportError, ProviderCredentialError) as exc:
                if isinstance(exc, ProviderCredentialError) and exc.status not in TRANSIENT:
                    self._stop(inbox, exc)
                inbox.log(f"poll failed ({type(exc).__name__}: {_said(exc)}); retrying in {delay:.0f}s")
                if connected:
                    inbox.record_connection("disconnected", reason=_said(exc))
                    connected = False
                time.sleep(delay)
                delay = min(delay * 2, 300.0)
                continue
            delay = 5.0
            if not connected:
                inbox.record_connection("connected", account="outlook")
                connected = True
            time.sleep(self.every)

    def _stop(self, inbox: Inbox, exc: ProviderCredentialError) -> None:
        reason = _said(exc)
        inbox.record_connection("stopped", reason=reason)
        inbox.log(f"stopped: {reason}")
        raise ListenerStopped(reason) from None

    def _round(self, inbox: Inbox, state: "_State", folder: str, raw: bool) -> None:
        """One delta round on one folder: every page, then save where it ended."""
        link = state.link(folder)
        try:
            page = self._page(link) if link else self._first_page(state, folder)
        except ProviderCredentialError as exc:
            if exc.status != 410 or not link:
                raise
            # Graph forgot this sync state. Start the folder again from the last
            # message we delivered rather than from now, so the gap is re-read
            # instead of lost.
            inbox.log(f"{folder}: sync state expired; re-reading from {state.last(folder)}")
            state.forget(folder)
            return self._round(inbox, state, folder, raw)
        delivered = 0
        while True:
            for item in page.get("value", []):
                if "@removed" in item:
                    continue
                message = self.to_message(item, raw=raw)
                if message is None or not self._wanted(message):
                    continue
                if inbox.deliver(message, raw=raw):
                    delivered += 1
                    inbox.log(f"received {message.id[-12:]} from={message.sender} folder={folder}")
                state.saw(folder, message.at)
            if "@odata.nextLink" in page:
                page = self._page(page["@odata.nextLink"])
                continue
            # Saved only now: a crash mid-round repeats the round and the inbox
            # drops what it already holds; saving per page could skip mail.
            state.save(folder, page["@odata.deltaLink"])
            if delivered:
                inbox.log(f"{folder}: {delivered} new")
            return

    def _first_page(self, state: "_State", folder: str) -> dict:
        """No saved link: start the folder's history at CO_OUTLOOK_SINCE, the
        last message delivered before a 410, or now — never at the beginning,
        which would answer years of mail."""
        start = state.last(folder) or self.since or iso_utc()
        params = {"changeType": "created", "$select": SELECT, "$filter": f"receivedDateTime ge {_iso_z(start)}"}
        return self._tool()._request("GET", f"/me/mailFolders/{folder}/messages/delta",
                                     params=params, headers=PREFER)

    def _page(self, link: str) -> dict:
        """A next or delta link, which already carries the round's query."""
        return self._tool()._request("GET", link.replace(OutlookTool.GRAPH_API_URL, ""), headers=PREFER)

    def _wanted(self, message: Message) -> bool:
        if not self.senders:
            return True
        address = message.sender.lower()
        return any(fnmatch.fnmatch(address, pattern.lower()) for pattern in self.senders)

    def to_message(self, item: dict, *, raw: bool = False) -> Optional[Message]:
        sender = (item.get("from") or {}).get("emailAddress") or {}
        if not sender.get("address"):
            return None
        body = (item.get("uniqueBody") or {}).get("content") or item.get("bodyPreview")
        text = "\n\n".join(part.strip() for part in (item.get("subject"), body) if part and part.strip())
        return Message(
            id=item["id"],
            chat=item.get("conversationId") or item["id"],
            sender=sender["address"],
            sender_name=sender.get("name") or "",
            text=text or "[empty email]",
            at=item.get("receivedDateTime") or iso_utc(),
            mentioned=True,  # a mailbox has no group to be addressed in
            raw=item if raw else None,
        )

    # ---- outbound ----------------------------------------------------------

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None, fresh: bool = False,
             plain: bool = False) -> str:
        """Answer a received email in its thread, through the Outlook tool,
        which keeps Cc and threading right (#1247). Returns "": Graph's reply
        action answers 202 with no body, so there is no new message id to give.

        Only a reply: `chat` is a conversation id, not an address, and a new
        email needs a subject this interface does not carry. `co outlook send`
        writes new mail.

        `plain` and `fresh` are accepted so every provider takes the same
        arguments. The Outlook tool sends the text as written, escaped into
        paragraphs, so there is no Markdown to translate; and Graph's reply has
        no idempotency key to vary, so `reply --again` is decided by the
        inbox's already-replied check alone."""
        if not reply_to:
            raise ValueError("Outlook sends only replies from the inbox: pass the id of a received email "
                             "as reply_to. A new email needs a subject. Next: co outlook send <to> <subject> <body>")
        self._tool().reply(reply_to, text)
        return ""

    # ---- plumbing ----------------------------------------------------------

    def _tool(self) -> OutlookTool:
        """One Outlook tool for the listener's life, so its cached token is reused."""
        if self._outlook is None:
            self._outlook = OutlookTool()
        return self._outlook


class _State:
    """Per folder: the delta link to resume from, and the newest message
    delivered, for restarting after Graph drops a sync state."""

    def __init__(self, path: Path):
        self.path = path
        # Absent before the first round. A file that is there but unreadable
        # raises: starting over would answer mail twice or skip it.
        self.data = json.loads(path.read_text()) if path.exists() else {}

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


def _said(exc: Exception) -> str:
    """An error on one line; the tool's errors put their "Next:" on a second."""
    return " ".join(str(exc).split())


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
