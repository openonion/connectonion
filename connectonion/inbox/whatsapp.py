"""
Purpose: WhatsApp as an inbox — a linked device sees every chat the number is in, including groups a person created
LLM-Note:
  Dependencies: imports from [json, os, time, uuid, threading, pathlib, inbox/store.py] and lazily from [neonize] | imported by [inbox/__init__.py via provider()] | tested by [tests/unit/test_inbox_whatsapp.py]
  Data flow: run(inbox) → neonize client on the linked session → MessageEv → to_message() → inbox.deliver() | send()/reply → outbox spool → the listener's sender thread → client.send_message()
  State/Effects: reads WHATSAPP_SESSION (default <inbox>/session.db) | the session file is the linked device's key material, not a password: deleting it unlinks the device | one WebSocket dialled outwards, so no port is opened | send() writes and polls two files under <inbox>/outbox/
  Integration: the same nine verbs as every other provider | `chat` is the group JID (…@g.us) for a group and the peer JID for a direct message, so a reply lands where the question was asked | mention gating feeds Channel.mention_only in inbox/settings.py
  Errors: check() returns the missing item and the next action instead of raising | send() fails with "the listener is not running" rather than opening a second connection, because WhatsApp allows one socket per linked device and a second one would drop the first

Why `send()` goes through a spool instead of connecting.  Feishu replies are
plain REST, so any process can send with a token.  WhatsApp has no REST: every
byte rides the one authenticated socket that `listen` holds.  A second process
opening the same session would present the same device identity and take the
connection away from the listener, so `co whatsapp reply` hands the text to the
listener and waits for its answer.  That is why `send` needs `listen` running,
and says so when it is not.
"""

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from .store import Inbox, Message, default_home, iso_utc

SDK_MISSING = (
    "The WhatsApp library is not installed. Run: pip install 'connectonion[whatsapp]'"
)

# neonize imports python-magic, which is a binding: the library it binds to is
# an OS package, so `pip install 'connectonion[whatsapp]'` completes and the
# import still fails. These are the package names that supply it.
LIBMAGIC_INSTALL = {
    "darwin": "brew install libmagic",
    "linux": "apt install libmagic1  (on Fedora/RHEL: dnf install file-libs)",
    "win32": "pip install python-magic-bin",
}

# WhatsApp's own JID suffixes. The server half says what kind of conversation a
# JID names, and the group one is the only one this treats as a group.
GROUP_SERVER = "g.us"
USER_SERVER = "s.whatsapp.net"

# How long `send` waits for the listener to pick the request up and answer.
SEND_TIMEOUT_SECONDS = 30.0
_SEND_POLL = 0.05


def _sdk():
    try:
        import neonize  # noqa: F401
    except ImportError as exc:
        if getattr(exc, "name", None) == "neonize":
            raise RuntimeError(SDK_MISSING) from exc
        # The package is there and importing it failed anyway. Answering with
        # the extra here sends someone to rerun a pip command that already
        # succeeded and cannot help, which costs more than saying nothing.
        raise RuntimeError(_sdk_will_not_load(exc)) from exc
    return neonize


def _sdk_will_not_load(exc: ImportError) -> str:
    """Why an installed neonize would not import, and what to run about it.

    Only libmagic is recognised by name, because it is the one we have actually
    seen and can therefore give a real command for. Anything else keeps its own
    message: an error someone can paste into a search beats a fix we guessed.
    """
    detail = str(exc) or type(exc).__name__
    if "libmagic" in detail:
        fix = LIBMAGIC_INSTALL.get(sys.platform) or "install libmagic with your system package manager"
        return (
            "The WhatsApp library is installed but will not load: it needs libmagic, "
            f"which the whatsapp extra does not install. Next: {fix}"
        )
    return (
        f"The WhatsApp library is installed but will not load: {detail}. "
        "Next: python -c 'import neonize' for the full traceback."
    )


def _jid_str(jid) -> str:
    """A JID as `user@server`, without the device and agent parts.

    The same person arrives as `…:12@s.whatsapp.net` from one of their phones
    and `…:3@…` from another; keyed on the raw JID those are two senders and a
    group conversation splits in two."""
    user = getattr(jid, "User", "") or ""
    server = getattr(jid, "Server", "") or USER_SERVER
    return f"{user}@{server}"


def _build_jid(chat: str):
    """`user@server` back into the SDK's JID."""
    from neonize.utils.jid import build_jid

    user, _, server = chat.partition("@")
    return build_jid(user, server or USER_SERVER)


def _context_info(message):
    """The `contextInfo` of whichever message variant is set, or None.

    Mentions and the quoted message live there, and every variant that can
    carry them (text, image, video, document, …) has its own copy, so this
    looks at the one field that is actually set rather than naming each type.
    """
    try:
        fields = message.ListFields()
    except AttributeError:
        return None
    for descriptor, value in fields:
        # protobuf 7 removed FieldDescriptor.label (6.x added is_repeated in its
        # place). Reading .label raised AttributeError on the first field of every
        # message, so with the protobuf a fresh install resolves, every message
        # was logged as "event not understood" and none reached the inbox.
        repeated = getattr(descriptor, "is_repeated", None)
        if repeated is None:
            repeated = descriptor.label == descriptor.LABEL_REPEATED
        if repeated:
            continue
        if descriptor.type != descriptor.TYPE_MESSAGE:
            continue
        try:
            if value.HasField("contextInfo"):
                return value.contextInfo
        except (ValueError, AttributeError):
            continue
    return None


def _user_of(jid_text: str) -> str:
    """The user half of a JID string, without device or server."""
    return str(jid_text or "").split("@", 1)[0].split(":", 1)[0]


def _publish(path: Path, payload: dict) -> None:
    """Write JSON so that `path` never exists half-written.

    Both ends of the outbox poll for a file by name, and `write_text` creates
    an empty file first: a reader that checks `exists()` in that gap gets zero
    bytes. CI caught it on the answer file — `JSONDecodeError: Expecting value:
    line 1 column 1` — where a loaded runner descheduled the writer between the
    create and the write. Staging beside the destination and renaming makes the
    gap unobservable, because rename within a directory is atomic.
    """
    staged = path.with_name(path.name + ".partial")
    staged.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    staged.replace(path)


def _collect(path: Path) -> Optional[dict]:
    """One published JSON file, consumed; None while it is not there yet.

    A spool is a directory anyone can write to, so "present but not readable"
    is one of its states, not an impossible one. `_publish` means our own
    writer never produces it; treating it as "not yet" rather than as a crash
    is what lets the caller keep waiting for the real thing.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    path.unlink(missing_ok=True)
    return payload


class WhatsApp:
    """One WhatsApp number linked as a companion device."""

    name = "whatsapp"

    def __init__(self):
        configured = os.environ.get("WHATSAPP_SESSION", "")
        self.session_path = Path(configured) if configured else default_home("whatsapp") / "session.db"
        self._client = None
        self._own_user = ""       # the phone number, for the log line
        self._own_ids = frozenset()  # every id that means us: the number and the LID

    # ---- setup -------------------------------------------------------------

    def missing(self) -> list:
        """Configuration problems, each with the fix. Empty means complete.

        Always empty, and deliberately: there is nothing to configure ahead of
        time. Feishu wants an app id and a secret before any verb can run, so
        its `missing()` has something to say; WhatsApp's only credential is the
        linked-device key, and that is created by `listen` itself when it shows
        the QR code. Reporting the absent session here would make the first
        `co whatsapp listen` exit 3 telling the operator to run
        `co whatsapp listen`. `check()` reports it instead.
        """
        return []

    def linked(self) -> list:
        """Whether a device is linked, as a problem and its next action.

        The session file exists from the moment `listen` shows its first QR
        code, before any phone has scanned it. A scan that failed or was never
        made leaves exactly that file, so its presence proved nothing and
        `check` reported a device that did not exist. whatsmeow writes one row
        to `whatsmeow_device` when the phone confirms the link; that row is the
        link."""
        how = ("Next: co whatsapp listen — a QR code appears, scan it from the phone "
               "under Settings > Linked devices. Use a number dedicated to this, "
               "never a personal or an employee's main one.")
        if not self.session_path.exists():
            return [f"No linked WhatsApp session at {self.session_path}. {how}"]
        if not self._device_confirmed():
            return [f"The WhatsApp session at {self.session_path} was never linked: a QR code "
                    f"was shown but no phone confirmed it. {how}"]
        return []

    def _device_confirmed(self) -> bool:
        import sqlite3

        try:
            with sqlite3.connect(f"file:{self.session_path}?mode=ro", uri=True) as db:
                return db.execute("select count(*) from whatsmeow_device").fetchone()[0] > 0
        except sqlite3.Error:
            # Not whatsmeow's database at all, or not one yet: not a linked device.
            return False

    def listen_requirements(self) -> list:
        """What `listen` needs beyond the session: the SDK.

        `send` and `reply` do not need it. They write to the outbox spool and
        wait, and the listener — which does have the SDK, or it would not be
        running — puts the bytes on the wire."""
        try:
            _sdk()
        except RuntimeError as exc:
            return [str(exc)]
        return []

    def check(self) -> list:
        """Everything that must be true before `listen` can work. Each entry is
        a problem and its next action; an empty list is a pass."""
        problems = self.listen_requirements()
        if problems:
            return problems
        problems.extend(self.linked())
        problems.extend(self.protocol_age())
        return problems

    def protocol_age(self) -> list:
        """The bundled WhatsApp protocol implementation, and whether it is old.

        neonize publishes no version for the whatsmeow snapshot compiled into
        its shared library, so this reads it out of the binary. A stale
        snapshot is how a working listener starts failing after WhatsApp
        changes something, and the failure does not name itself."""
        snapshot = self.protocol_snapshot()
        if snapshot is None:
            return []
        age_days = (time.time() - snapshot) / 86400
        if age_days < 180:
            return []
        return [
            f"The bundled WhatsApp protocol implementation is {int(age_days)} days old "
            f"({iso_utc(snapshot)[:10]}). WhatsApp changes it, and an old snapshot fails "
            "in ways that do not name themselves. Next: check for a newer neonize."
        ]

    def protocol_snapshot(self) -> Optional[float]:
        """Unix time of the whatsmeow snapshot inside neonize's shared library,
        or None when it cannot be read. Its Go pseudo-version carries the date:
        `go.mau.fi/whatsmeow@v0.0.0-20260709092057-73fe7355f59f`."""
        import re

        try:
            import neonize
        except ImportError:
            return None
        directory = Path(neonize.__file__).parent
        libraries = sorted(directory.glob("neonize-*.so")) + sorted(directory.glob("neonize-*.dll")) \
            + sorted(directory.glob("neonize-*.dylib"))
        pattern = re.compile(rb"whatsmeow@v[0-9.]+-(\d{14})-")
        for library in libraries:
            try:
                found = pattern.search(library.read_bytes())
            except OSError:
                continue
            if found:
                stamp = found.group(1).decode()
                try:
                    return time.mktime(time.strptime(stamp, "%Y%m%d%H%M%S"))
                except ValueError:
                    return None
        return None

    # ---- inbound -----------------------------------------------------------

    def run(self, inbox: Inbox, *, raw: bool = False) -> None:
        """Hold the linked connection and write every message. Blocks.

        Also drains the outbox, because this process owns the only socket."""
        _sdk()
        from neonize.client import NewClient
        from neonize.events import ConnectedEv, MessageEv, PairStatusEv

        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        client = NewClient(str(self.session_path))
        self._client = client

        @client.event(ConnectedEv)
        def _on_connected(_client, _event) -> None:
            self._own_user, self._own_ids = self._read_identity(_client)
            # Both ids in the log: which id a group addresses us by is exactly
            # what you need to know when a mention did not register.
            others = sorted(self._own_ids - {self._own_user})
            also = f" (also {', '.join(others)})" if others else ""
            inbox.log(f"connected as {self._own_user or 'unknown'}{also}")

        @client.event(PairStatusEv)
        def _on_paired(_client, event) -> None:
            inbox.log(f"paired {_jid_str(getattr(event, 'ID', None))}")

        @client.event(MessageEv)
        def _on_message(_client, event) -> None:
            # A raising handler would surface as a Go-side panic and take the
            # whole process down, listener and all. A payload we cannot read is
            # one log line.
            try:
                message = self.to_message(event)
            except Exception as exc:
                inbox.log(f"event not understood ({type(exc).__name__}: {exc}); skipped")
                return
            if message is None:
                return
            if raw:
                try:
                    message.raw = {"info": str(event.Info), "message": str(event.Message)}
                except Exception as exc:
                    inbox.log(f"raw payload of {message.id} not kept: {exc}")
            if inbox.deliver(message, raw=raw):
                inbox.log(f"received {message.id} chat={message.chat} sender={message.sender}")
            else:
                inbox.log(f"duplicate {message.id} dropped")

        stop = threading.Event()
        sender = threading.Thread(target=self._drain_outbox, args=(inbox, stop), daemon=True)
        sender.start()
        try:
            client.connect()
        finally:
            stop.set()

    @staticmethod
    def _read_identity(client) -> tuple:
        """Our phone number, and every id that means us.

        WhatsApp is migrating accounts to LID addressing (`…@lid`), and a LID
        shares no digits with the phone number it belongs to — the linked device
        this was found on holds `61410724095@s.whatsapp.net` and
        `132754033377342@lid` for the same account. In a migrated group an
        @mention carries the LID, so reading only `Device.JID` made a real
        mention arrive as `mentioned: False`: the bot sat silent while the
        person who addressed it watched nothing happen, which is the failure
        that costs the most because it looks like nothing went wrong.

        Both ids stay live. Groups migrate at different times and older ones
        still carry the number, so this is a set, not a replacement.
        """
        try:
            me = client.get_me()
        except Exception:
            return "", frozenset()
        phone = _user_of(_jid_str(getattr(me, "JID", None)))
        lid = _user_of(_jid_str(getattr(me, "LID", None)))
        return phone, frozenset(i for i in (phone, lid) if i)

    def to_message(self, event, *, raw: bool = False) -> Optional[Message]:
        """A MessageEv as a Message, or None for an event that is not someone
        talking to us."""
        from neonize.utils.message import extract_text

        source = event.Info.MessageSource
        # Our own messages come back over the same socket. Delivering them would
        # answer ourselves, and the answer would arrive as another message.
        if source.IsFromMe:
            return None

        text = extract_text(event.Message) or ""
        context = _context_info(event.Message)
        chat = _jid_str(source.Chat)
        sender = _jid_str(source.Sender)

        if source.IsGroup:
            mentioned = self._addressed_in_group(text, context)
        else:
            # A direct message is addressed to us by existing.
            mentioned = True

        return Message(
            id=str(event.Info.ID),
            chat=chat,
            sender=sender,
            text=text,
            mentioned=mentioned,
            at=_iso(getattr(event.Info, "Timestamp", None)),
            thread=None,
            raw=None,
        )

    def _addressed_in_group(self, text: str, context) -> bool:
        """Whether a group message is for us. Three ways, the same three every
        other group gateway settled on: a real @mention, a reply to something we
        said, and our own number written in the text.

        Each of the three is checked against every id the account answers to —
        its phone number and its LID — because which one a group uses is the
        group's choice, not ours.

        With no known ids — before the connection is up — nothing counts as
        addressed. A group channel with mention_only stays quiet, which is the
        failure that costs nothing."""
        own = self._own_ids
        if not own:
            return False
        if context is not None:
            for mentioned_jid in getattr(context, "mentionedJID", None) or []:
                if _user_of(mentioned_jid) in own:
                    return True
            if _user_of(getattr(context, "participant", "")) in own:
                return True
        return any(one in (text or "") for one in own)

    # ---- outbound ----------------------------------------------------------

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None, fresh: bool = False) -> str:
        """Send text to a chat. Returns the new message id.

        The listener owns the connection, so this hands the request over and
        waits for its answer. `fresh` is `reply --again`; WhatsApp does not
        dedupe on its side, so it changes nothing here and is accepted so every
        provider takes the same arguments."""
        inbox = Inbox(self.name)
        spool = inbox.root / "outbox"
        spool.mkdir(parents=True, exist_ok=True)
        ticket = f"{int(time.time() * 1000)}-{uuid.uuid4().hex}"
        request = spool / f"{ticket}.json"
        answer = spool / f"{ticket}.result"
        _publish(request, {"chat": chat, "text": text, "reply_to": reply_to})

        deadline = time.monotonic() + SEND_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            result = _collect(answer)
            if result is not None:
                if result.get("error"):
                    raise RuntimeError(result["error"])
                return str(result.get("id", ""))
            time.sleep(_SEND_POLL)

        request.unlink(missing_ok=True)
        answer.unlink(missing_ok=True)
        raise RuntimeError(
            f"No listener answered in {int(SEND_TIMEOUT_SECONDS)}s. WhatsApp allows one connection per linked "
            "device, so sending goes through the listener rather than opening a second "
            "one. Next: co whatsapp listen"
        )

    def _drain_outbox(self, inbox: Inbox, stop: threading.Event) -> None:
        """Send what other processes queued. Runs in the listener."""
        spool = inbox.root / "outbox"
        spool.mkdir(parents=True, exist_ok=True)
        while not stop.is_set():
            for request in sorted(spool.glob("*.json")):
                payload = _collect(request)
                if payload is None:
                    # Not ours, or not written by `send`. One log line, gone.
                    request.unlink(missing_ok=True)
                    inbox.log(f"outbox file {request.name} is not a send request; discarded")
                    continue
                answer = request.with_suffix(".result")
                try:
                    _publish(answer, {"id": self._send_now(payload["chat"], payload["text"])})
                except Exception as exc:
                    _publish(answer, {"error": str(exc)})
                    inbox.log(f"send to {payload.get('chat')} failed: {exc}")
            stop.wait(_SEND_POLL)

    def _send_now(self, chat: str, text: str) -> str:
        """The actual send, on the listener's own connection."""
        if self._client is None:
            raise RuntimeError("not connected")
        result = self._client.send_message(_build_jid(chat), text)
        return str(getattr(result, "ID", "") or "")


def _iso(timestamp) -> str:
    """WhatsApp timestamps arrive as protobuf Timestamps or as seconds."""
    seconds = getattr(timestamp, "seconds", None)
    if seconds is None:
        seconds = timestamp
    try:
        return iso_utc(int(seconds))
    except (TypeError, ValueError):
        return iso_utc()
