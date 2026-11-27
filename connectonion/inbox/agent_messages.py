"""Sealed agent-to-agent text over the existing Cloud message mailbox."""

import hashlib
import json
import re
import time

import requests
from nacl.exceptions import CryptoError

from ..backend import backend_url
from ..handoff import sealing
from ..network.agent_auth import signed_agent_token
from ..network.trust.tools import get_level, is_admin
from ..project import project_co_dir, project_identity
from .store import Inbox, Message

NOTE_TYPE = "co.agent.text.v1"
MAX_TEXT_BYTES = 16 * 1024
PAGE_SIZE = 100
POLL_SECONDS = 5
RESCAN_SECONDS = 300
_ADDRESS = re.compile(r"0x[0-9a-f]{64}")


def _valid_text(text) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False
    try:
        return len(text.encode()) <= MAX_TEXT_BYTES
    except UnicodeEncodeError:
        return False


def current_mailbox(session: requests.Session):
    co_dir = project_co_dir()
    keys = project_identity(co_dir)
    if not keys:
        raise ValueError("This project has no agent identity. Run co init first.")
    return AgentMailbox(session, keys, co_dir)


class AgentMailbox:
    def __init__(self, session, keys, co_dir):
        self.session = session
        self.keys = keys
        self.co_dir = co_dir
        self.origin = backend_url()
        origin_key = hashlib.sha256(self.origin.encode()).hexdigest()[:16]
        self.inbox = Inbox("agent", co_dir / "inbox" / "agent" / keys["address"] / origin_key)
        self.token = None

    def _request(self, method, **kwargs):
        if not self.token:
            self.token = signed_agent_token(self.keys, self.origin)
        url = f"{self.origin}/api/v1/messages"
        response = self.session.request(
            method, url, headers={"Authorization": f"Bearer {self.token}"}, timeout=30, **kwargs,
        )
        if response.status_code == 401:
            self.token = signed_agent_token(self.keys, self.origin)
            response = self.session.request(
                method, url, headers={"Authorization": f"Bearer {self.token}"}, timeout=30, **kwargs,
            )
        response.raise_for_status()
        return response.json()

    def send(self, to: str, text: str, reply_to: str | None = None) -> str:
        to = to.strip().lower()
        if not _ADDRESS.fullmatch(to):
            raise ValueError("Use the full 0x agent address (64 hex digits after 0x).")
        if not _valid_text(text):
            raise ValueError("Give a text message between 1 byte and 16 KiB.")
        try:
            sealed = sealing.box(self.keys["signing_key"], to, {
                "type": NOTE_TYPE, "text": text, "reply_to": reply_to,
            })
        except (RuntimeError, ValueError) as exc:
            raise ValueError("The recipient address is not a usable agent key.") from exc
        body = json.dumps({"type": NOTE_TYPE, "sealed": sealed})
        return str(self._request("POST", json={"to": to, "body": body})["id"])

    def reply(self, message_id: str, text: str) -> str:
        original = self.inbox.lookup(message_id)
        if original is None:
            raise ValueError(f"No local message {message_id!r}. Run co agent ls for message IDs.")
        if not self._trusted(original.sender):
            raise ValueError("The original sender is no longer trusted. Check with co trust level.")
        sent_id = self.send(original.sender, text, reply_to=original.id)
        self.inbox.done(original.id)
        return sent_id

    def _trusted(self, sender: str) -> bool:
        level = get_level(sender, self.co_dir)
        return level != "blocked" and (level in {"contact", "whitelist"} or is_admin(sender, self.co_dir))

    def _open(self, row: dict) -> Message | None:
        sender = row["from_address"]
        if not isinstance(sender, str) or not _ADDRESS.fullmatch(sender) or not self._trusted(sender):
            return None
        try:
            envelope = json.loads(row["body"])
            if envelope.get("type") != NOTE_TYPE or not isinstance(envelope.get("sealed"), str):
                return None
            note = sealing.unbox(self.keys["signing_key"], sender, envelope["sealed"])
        except (AttributeError, TypeError, ValueError, RuntimeError, CryptoError):
            return None
        if not isinstance(note, dict) or note.get("type") != NOTE_TYPE:
            return None
        text, reply_to = note.get("text"), note.get("reply_to")
        if not _valid_text(text):
            return None
        quoted = {"id": reply_to} if isinstance(reply_to, str) and reply_to.isascii() and reply_to.isdecimal() else None
        return Message(str(row["id"]), sender, sender, text, row["created_at"], quoted=quoted)

    def poll(self, after: int) -> tuple[int, int]:
        landed = 0
        while True:
            rows = self._request("GET", params={"after": after, "limit": PAGE_SIZE})["messages"]
            for row in rows:
                message = self._open(row)
                if message is not None and self.inbox.deliver(message):
                    landed += 1
                after = row["id"]
            if len(rows) < PAGE_SIZE:
                return after, landed

    def listen(self, report, retry) -> None:
        after, rescan_at = 0, time.monotonic() + RESCAN_SECONDS
        while True:
            if time.monotonic() >= rescan_at:
                # Cloud IDs can be allocated before another transaction commits.
                # Revisit older rows so a late commit is still received.
                after, rescan_at = 0, time.monotonic() + RESCAN_SECONDS
            try:
                after, count = self.poll(after)
            except requests.RequestException as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status is not None and status not in {408, 429} and status < 500:
                    raise
                retry()
                time.sleep(30)
                continue
            report(count)
            time.sleep(POLL_SECONDS)
