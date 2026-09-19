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

from . import ANSWERING, SEEN, ListenerStopped, reactions_enabled
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


def _sending_failed(exc: Exception) -> str:
    """Why a send did not go out, in words the person can act on.

    whatsmeow says `the store doesn't contain a device JID` when the session has
    no registration — true, and it names an internal structure rather than the
    thing that happened, which is that this device is no longer linked. Only
    that one is translated; anything else keeps its own words, because a message
    somebody can search beats a fix we guessed at.
    """
    detail = str(exc) or type(exc).__name__
    if "device JID" in detail or "not logged in" in detail.lower():
        return ("this device is not linked any more — the phone unlinked it, or the QR was "
                "never scanned. Next: co whatsapp listen and scan the QR again")
    return detail


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


# What the variant is called, in the words a person would use. Anything not
# here keeps the protobuf's own name minus the Message suffix, so a variant
# WhatsApp adds tomorrow still arrives as something rather than as nothing.
KINDS = {
    "conversation": "text",
    "extendedTextMessage": "text",
    "imageMessage": "image",
    "videoMessage": "video",
    "ptvMessage": "video",
    "audioMessage": "audio",
    "documentMessage": "document",
    "documentWithCaptionMessage": "document",
    "stickerMessage": "sticker",
    "lottieStickerMessage": "sticker",
    "locationMessage": "location",
    "liveLocationMessage": "location",
    "contactMessage": "contact",
    "contactsArrayMessage": "contact",
    "reactionMessage": "reaction",
    "encReactionMessage": "reaction",
}


def _kind(message) -> str:
    """Which of WhatsApp's 107 message variants this is.

    The same walk `_context_info` does. A message whose body we cannot read is
    delivered with an empty `text` either way; without a kind beside it, that
    is indistinguishable from someone sending nothing, and a consumer can
    neither answer "I can't read images yet" nor correctly ignore it.
    """
    try:
        fields = message.ListFields()
    except AttributeError:
        return "text"
    for descriptor, _ in fields:
        repeated = getattr(descriptor, "is_repeated", None)
        if repeated is None:
            repeated = descriptor.label == descriptor.LABEL_REPEATED
        if repeated or descriptor.type != descriptor.TYPE_MESSAGE:
            continue
        # getattr, not attribute access: reading a descriptor attribute that a
        # protobuf release had removed is precisely how every message stopped
        # being delivered in 1.8.6a1. A kind we cannot read is worth nothing
        # and must cost nothing.
        name = getattr(descriptor, "name", "") or ""
        if name in KINDS:
            return KINDS[name]
        if name:
            # "Message" sits in the middle as often as at the end —
            # `pollCreationMessageV3`, `documentWithCaptionMessage` — so it is
            # removed wherever it is rather than stripped as a suffix.
            return name.replace("Message", "").lower() or "text"
    return "text"


def _quoted_reference(context, own_ids) -> Optional[dict]:
    """The message a reply is answering, from the contextInfo we already read.

    All of it has been arriving in every reply since the beginning — stanzaID,
    participant and the quoted message itself — and none of it was carried out
    of the parser. Someone quoting the bot's own line and writing "this one is
    wrong" produced a record with the new text and no trace of what "this one"
    was, so a consumer could neither answer the question nor tell that it had
    been addressed.

    `from_me` is the field that decides behaviour. Replying to the bot and
    replying to another person in the same group are different events, and the
    documented trigger policy — direct message, @mention, or reply to us —
    cannot be implemented without separating them.
    """
    if context is None:
        return None
    stanza = str(getattr(context, "stanzaID", "") or "")
    if not stanza:
        return None
    sender = str(getattr(context, "participant", "") or "")
    quoted = getattr(context, "quotedMessage", None)
    text = ""
    if quoted is not None:
        try:
            from neonize.utils.message import extract_text

            text = extract_text(quoted) or ""
        except Exception:
            # A quoted body we cannot read is worth less than the reference to
            # it; the id and the sender are what a consumer needs most.
            text = ""
    return {
        "id": stanza,
        "sender": sender,
        "text": text,
        "kind": _kind(quoted) if quoted is not None else "text",
        "from_me": bool(own_ids) and _user_of(sender) in own_ids,
    }


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
        self._fatal_reason = ""   # why this listener can never receive again
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
            # Two stories, one file. whatsmeow clears device, identity_keys and
            # sessions together on logout, so a pairing that never completed and
            # a device the phone unlinked leave byte-identical evidence. Saying
            # "the QR was never scanned" to somebody who watched it work for a
            # week sends them looking for a scan that did happen.
            return [f"No linked device in {self.session_path} — either the QR was never "
                    f"scanned, or this device was logged out from the phone. {how}"]
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
        from neonize.events import (ConnectedEv, ConnectFailureEv, DisconnectedEv,
                                    GroupInfoEv, JoinedGroupEv, KeepAliveRestoredEv,
                                    KeepAliveTimeoutEv, LoggedOutEv, MessageEv,
                                    PairStatusEv, StreamReplacedEv, TemporaryBanEv,
                                    UndecryptableMessageEv)

        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        client = NewClient(str(self.session_path))
        self._client = client
        stop = threading.Event()

        @client.event(ConnectedEv)
        def _on_connected(_client, _event) -> None:
            self._own_user, self._own_ids = self._read_identity(_client)
            # Both ids in the log: which id a group addresses us by is exactly
            # what you need to know when a mention did not register.
            others = sorted(self._own_ids - {self._own_user})
            also = f" (also {', '.join(others)})" if others else ""
            inbox.log(f"connected as {self._own_user or 'unknown'}{also}")
            inbox.record_connection("connected", account=self._own_user,
                                    ids=sorted(self._own_ids))

        @client.event(PairStatusEv)
        def _on_paired(_client, event) -> None:
            inbox.log(f"paired {_jid_str(getattr(event, 'ID', None))}")

        # The socket has more ways to stop working than to work, and none of
        # them used to say anything. A listener whose phone unlinked it keeps
        # its process, prints nothing further, and receives nothing ever again
        # — so "nobody has messaged us" and "we were logged out yesterday"
        # produced identical evidence, which is the state this whole release
        # has been about.

        @client.event(LoggedOutEv)
        def _on_logged_out(_client, event) -> None:
            self._fatal(
                inbox, stop,
                f"logged out by the phone (reason {getattr(event, 'Reason', 'unknown')}). "
                "This device was unlinked under Settings > Linked devices. "
                "Next: co whatsapp listen — scan the QR again")

        @client.event(StreamReplacedEv)
        def _on_replaced(_client, _event) -> None:
            # WhatsApp allows one socket per linked device, so a second listener
            # on the same session silently takes this one's place.
            self._fatal(
                inbox, stop,
                "another client took this session over: WhatsApp allows one connection per "
                "linked device. Next: stop the other listener, then co whatsapp listen")

        @client.event(TemporaryBanEv)
        def _on_banned(_client, event) -> None:
            self._fatal(
                inbox, stop,
                f"temporarily banned by WhatsApp (code {getattr(event, 'Code', '?')}, "
                f"expires {getattr(event, 'Expire', '?')}). Nothing will arrive until it lifts.")

        @client.event(ConnectFailureEv)
        def _on_connect_failure(_client, event) -> None:
            inbox.log(f"connect failed: {getattr(event, 'Reason', '?')} "
                      f"{getattr(event, 'Message', '')}".strip())

        @client.event(DisconnectedEv)
        def _on_disconnected(_client, _event) -> None:
            # Not fatal: the SDK reconnects. Logged because a gap is exactly
            # what a later "did we miss anything" question needs to see.
            inbox.log("disconnected; waiting for the socket to come back")
            inbox.record_connection("disconnected")

        @client.event(KeepAliveTimeoutEv)
        def _on_keepalive_timeout(_client, event) -> None:
            inbox.log(f"keepalive timed out ({getattr(event, 'ErrorCount', '?')} in a row)")

        @client.event(KeepAliveRestoredEv)
        def _on_keepalive_restored(_client, _event) -> None:
            inbox.log("keepalive restored")

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
            self.take(inbox, message, raw=raw)

        # Things that happen to this account which are not somebody typing. They
        # become records with their own `kind` rather than log lines, because a
        # consumer reading a conversation back needs them — "he deleted that" and
        # "she was added" are part of what was said — and because the ones that
        # were only ever logged were invisible to everything except a person with
        # ssh. Only the ones actually about us raise `mentioned`.

        @client.event(UndecryptableMessageEv)
        def _on_undecryptable(_client, event) -> None:
            # Somebody sent something and we could not read it. This was the
            # worst silence left: the message exists, we know who and when, and
            # a consumer never learned it happened at all. An empty body is at
            # least a record; this was nothing.
            self._note(inbox, event, "undecryptable",
                       f"could not be decrypted ({getattr(event, 'DecryptFailMode', '')})".strip())

        @client.event(JoinedGroupEv)
        def _on_joined(_client, event) -> None:
            # The issue that asked for this called it the moment a consumer most
            # wants to know, and it is right: it is the bot's first sight of a
            # room. Addressed to us by definition — nobody else was added.
            info = getattr(event, "GroupInfo", None)
            chat = _jid_str(getattr(info, "JID", None))
            name = str(getattr(info, "GroupName", None) or getattr(info, "Name", "") or "")
            self.take(inbox, Message(
                id=f"joined-{chat}-{int(time.time())}", chat=chat, sender="", sender_name="",
                text=f"added to {name}".strip(), kind="joined", quoted=None,
                mentioned=True, at=iso_utc(), thread=None))

        @client.event(GroupInfoEv)
        def _on_group_info(_client, event) -> None:
            chat = _jid_str(getattr(event, "JID", None))
            what = "renamed" if str(getattr(event, "Name", "") or "") else "changed"
            self.take(inbox, Message(
                id=f"group-{chat}-{int(time.time())}", chat=chat,
                sender=_jid_str(getattr(event, "Sender", None)), sender_name="",
                text=f"group {what}", kind="group-info", quoted=None,
                mentioned=False, at=iso_utc(), thread=None))

        sender = threading.Thread(target=self._drain_outbox, args=(inbox, stop), daemon=True)
        sender.start()
        try:
            client.connect()
        finally:
            stop.set()
        if self._fatal_reason:
            raise ListenerStopped(self._fatal_reason)

    def _note(self, inbox: Inbox, event, kind: str, text: str) -> None:
        """Record something that carries a MessageInfo but is not a message body.

        Never raises: this runs inside an SDK callback, where an exception is a
        Go-side panic that ends the listener. A note we could not write is a log
        line; it must not cost the connection.
        """
        try:
            source = event.Info.MessageSource
            if source.IsFromMe:
                return
            chat, sender = _jid_str(source.Chat), _jid_str(source.Sender)
            self.take(inbox, Message(
                id=str(event.Info.ID), chat=chat, sender=sender,
                sender_name=self.name_of(sender), text=text, kind=kind, quoted=None,
                # A direct one is for us by existing; in a group, nothing in it
                # says it was addressed to us, so it joins the record quietly.
                mentioned=not source.IsGroup,
                at=_iso(getattr(event.Info, "Timestamp", None)), thread=None))
        except Exception as exc:
            inbox.log(f"{kind} event not recorded ({type(exc).__name__}: {exc})")

    def _fatal(self, inbox: Inbox, stop: threading.Event, reason: str) -> None:
        """Record why this listener can never receive again, and wind it down.

        Not every disconnection is fatal — the SDK reconnects from most of them,
        and those are log lines. These three are not: being unlinked, having the
        session taken by another client, and being banned all leave a process
        that holds a socket, prints nothing, and will never see another message.
        Staying up in that state is what made "nobody has messaged us"
        indistinguishable from "we were logged out yesterday".

        Never raises: this runs inside an SDK callback, where an exception is a
        Go-side panic. It records the reason, asks the connection to stop, and
        `run` raises on the way out where a caller can act on it.
        """
        inbox.log(f"listener stopped: {reason}")
        inbox.record_connection("stopped", reason=reason)
        self._fatal_reason = reason
        stop.set()
        try:
            self._client.disconnect()
        except Exception as exc:
            inbox.log(f"disconnect after stopping failed: {exc}")

    def name_of(self, jid: str) -> str:
        """What this sender is called, from the contacts whatsmeow already synced.

        `126121882435737@lid` tells nobody who spoke, and every consumer was
        otherwise going to build the same cache — we already maintain one for
        Lark, for the same reason, and it is a recurring source of "who said
        this?".

        Entirely local: `whatsmeow_contacts` holds ~2000 rows after history
        sync, keyed by both `@s.whatsapp.net` and `@lid`, and
        `whatsmeow_lid_map` bridges the two when only one side is present. No
        API call, so a name costs a point lookup on a file we already have open
        rather than a round trip on the path every message takes.

        Read per message rather than cached: names change, and a stale name is
        worse than an opaque id because it reads as authoritative. SQLite point
        lookups at this size are not worth a staleness bug.
        """
        user = _user_of(jid)
        if not user or not self.session_path.exists():
            return ""
        import sqlite3

        try:
            with sqlite3.connect(f"file:{self.session_path}?mode=ro", uri=True) as db:
                name = self._name_row(db, user)
                if name:
                    return name
                # A LID with no contact row of its own: the phone number it
                # belongs to may have one.
                for (other,) in db.execute(
                        "select pn from whatsmeow_lid_map where lid = ? limit 1", (user,)):
                    return self._name_row(db, str(other))
                for (other,) in db.execute(
                        "select lid from whatsmeow_lid_map where pn = ? limit 1", (user,)):
                    return self._name_row(db, str(other))
        except sqlite3.Error:
            # Not whatsmeow's database, or mid-write. A missing name is a
            # missing name; it must never cost the message.
            return ""
        return ""

    @staticmethod
    def _name_row(db, user: str) -> str:
        """The best name on a contact row: the one a person would recognise."""
        for (full, first, push, business) in db.execute(
                "select full_name, first_name, push_name, business_name "
                "from whatsmeow_contacts where their_jid like ? limit 1", (f"{user}@%",)):
            for candidate in (full, business, first, push):
                if candidate and str(candidate).strip() and str(candidate) != "None":
                    return str(candidate).strip()
        return ""

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
        kind = _kind(event.Message)
        # An edit arrives as a whole message with a flag on the envelope rather
        # than as its own event. A consumer that treats it as new text answers
        # the correction as though it were a fresh question; one that can see it
        # is an edit can go and look at what it replaced.
        if getattr(event, "IsEdit", False):
            kind = "edit"
        quoted = _quoted_reference(context, self._own_ids)
        chat = _jid_str(source.Chat)
        sender = _jid_str(source.Sender)

        if kind == "reaction":
            # Somebody put an emoji on a message — including the ones this bot
            # puts on its own queue, which come back over the same socket. It is
            # worth recording and is not a question, so it is never addressed to
            # us and a mention_only channel never wakes a consumer for it.
            mentioned = False
        elif source.IsGroup:
            mentioned = self._addressed_in_group(text, context, quoted)
        else:
            # A direct message is addressed to us by existing.
            mentioned = True

        return Message(
            id=str(event.Info.ID),
            chat=chat,
            sender=sender,
            text=text,
            kind=kind,
            quoted=quoted,
            sender_name=self.name_of(sender),
            mentioned=mentioned,
            at=_iso(getattr(event.Info, "Timestamp", None)),
            thread=None,
            raw=None,
        )

    def _addressed_in_group(self, text: str, context, quoted=None) -> bool:
        """Whether a group message is for us. Three ways, the same three every
        other group gateway settled on: a real @mention, a reply to something we
        said, and our own number written in the text.

        Each of the three is checked against every id the account answers to —
        its phone number and its LID — because which one a group uses is the
        group's choice, not ours.

        The reply arm reads `quoted["from_me"]`, the same value the record
        carries, rather than recomputing it. Two copies of "was this addressed
        to us" can disagree, and when they do the record says one thing and the
        behaviour does another — which is precisely the state that made a
        `mentioned: false` on a reply impossible to argue with either way.

        With no known ids — before the connection is up — nothing counts as
        addressed. A group channel with mention_only stays quiet, which is the
        failure that costs nothing."""
        own = self._own_ids
        if not own:
            return False
        if quoted and quoted.get("from_me"):
            return True
        if context is not None:
            for mentioned_jid in getattr(context, "mentionedJID", None) or []:
                if _user_of(mentioned_jid) in own:
                    return True
            # The same signal read straight from the context. A quoted reference
            # needs a stanzaID to be worth carrying, and this does not: a reply
            # whose contextInfo is shaped in some way we did not expect still
            # counts as one, rather than being silently downgraded to "not for
            # us" because one field was missing.
            if _user_of(getattr(context, "participant", "")) in own:
                return True
        return any(one in (text or "") for one in own)

    def take(self, inbox: Inbox, message: Message, *, raw: bool = False) -> bool:
        """Put a message in the queue, and mark it as seen where it was asked.

        Delivering and marking belong together: the mark has to follow the same
        "was this new" answer the queue gave, or a message WhatsApp retried gets
        a second receipt for work nobody is doing twice.
        """
        if not inbox.deliver(message, raw=raw):
            inbox.log(f"duplicate {message.id} dropped")
            return False
        inbox.log(f"received {message.id} chat={message.chat} sender={message.sender}")
        self._mark(inbox, message, SEEN)
        return True

    def _mark(self, inbox: Inbox, message: Message, emoji: str) -> None:
        """React on a queued message, on our own connection, never raising.

        This runs inside the MessageEv handler, where an exception is a Go-side
        panic that ends the listener. A receipt is never worth the process, and
        a mark that did not go out is a log line — the message is already
        safely in the queue by the time we get here.
        """
        if not reactions_enabled() or not message.mentioned:
            return
        try:
            sent = self._react_now(message.chat, message.id, emoji, message.sender)
        except Exception as exc:
            inbox.log(f"{emoji} on {message.id} not sent: {exc}")
            return
        # Logged on success as well as failure, and with the id the platform
        # gave back. Silence here would mean "sent" and "never attempted" look
        # the same in the log, which is the failure mode this whole release has
        # been about — and a receipt nobody can verify is not a receipt.
        inbox.log(f"{emoji} on {message.id} sent as {sent or 'no id'}")

    # ---- outbound ----------------------------------------------------------

    def react(self, chat: str, message_id: str, emoji: str, *, sender: str = "") -> str:
        """Put our reaction on a message, replacing whichever we left before.

        Queued like a send, because the caller is usually `reply` in another
        process and the listener owns the only socket."""
        return self._queue({"kind": "reaction", "chat": chat,
                            "message_id": message_id, "emoji": emoji, "sender": sender})

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None, fresh: bool = False) -> str:
        """Send text to a chat. Returns the new message id.

        The listener owns the connection, so this hands the request over and
        waits for its answer. `fresh` is `reply --again`; WhatsApp does not
        dedupe on its side, so it changes nothing here and is accepted so every
        provider takes the same arguments."""
        return self._queue({"chat": chat, "text": text, "reply_to": reply_to})

    def _queue(self, payload: dict) -> str:
        """Hand one outbound request to the listener and wait for its answer."""
        inbox = Inbox(self.name)
        spool = inbox.root / "outbox"
        spool.mkdir(parents=True, exist_ok=True)
        ticket = f"{int(time.time() * 1000)}-{uuid.uuid4().hex}"
        request = spool / f"{ticket}.json"
        answer = spool / f"{ticket}.result"
        _publish(request, payload)

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
                    _publish(answer, {"id": self._perform(payload)})
                except Exception as exc:
                    _publish(answer, {"error": str(exc)})
                    inbox.log(f"send to {payload.get('chat')} failed: {exc}")
            stop.wait(_SEND_POLL)

    def _perform(self, payload: dict) -> str:
        """One queued request, on the listener's own connection.

        A request with no kind is a send: the spool carried nothing but sends
        before reactions existed, and a listener that has not been restarted
        yet may still be draining one."""
        try:
            if payload.get("kind") == "reaction":
                return self._react_now(payload["chat"], payload["message_id"],
                                       payload["emoji"], payload.get("sender", ""))
            return self._send_now(payload["chat"], payload["text"], payload.get("reply_to"))
        except Exception as exc:
            raise RuntimeError(_sending_failed(exc)) from exc

    def _react_now(self, chat: str, message_id: str, emoji: str, sender: str) -> str:
        """The actual reaction, on the listener's own connection.

        `sender` is whoever sent the message being reacted to — WhatsApp needs
        it to address the reaction, and in a direct chat it is the chat itself.
        """
        if self._client is None:
            raise RuntimeError("not connected")
        to = _build_jid(chat)
        reaction = self._client.build_reaction(to, _build_jid(sender or chat), message_id, emoji)
        result = self._client.send_message(to, reaction)
        return str(getattr(result, "ID", "") or "")

    def _send_now(self, chat: str, text: str, reply_to: Optional[str] = None) -> str:
        """The actual send, on the listener's own connection."""
        if self._client is None:
            raise RuntimeError("not connected")
        quoted = self._quoted(reply_to) if reply_to else None
        body = text if quoted is None else self._client.build_reply_message(text, quoted)
        result = self._client.send_message(_build_jid(chat), body)
        return str(getattr(result, "ID", "") or "")

    def _quoted(self, message_id: str):
        """The message being answered, shaped as the SDK's quoted message.

        Feishu replies to a message id and the platform works out the rest;
        WhatsApp puts the quote in the outgoing message, so the original has to
        be handed back to it. We do not keep the raw event, and we do not need
        to: a quote is the original's id, who sent it, and its text, and all
        three are in `received.jsonl`. Rebuilding from the record also means a
        reply still quotes correctly after the listener has been restarted.

        None when the original is not in the record any more. An answer that
        reaches the right chat unquoted is worth more to the person waiting than
        an exception, so this degrades rather than fails.
        """
        original = Inbox(self.name).lookup(message_id)
        if original is None:
            return None
        from neonize.proto import Neonize_pb2 as events
        from neonize.proto.waE2E import WAWebProtobufsE2E_pb2 as e2e

        return events.Message(
            Info=events.MessageInfo(
                ID=original.id,
                MessageSource=events.MessageSource(
                    Chat=_build_jid(original.chat),
                    Sender=_build_jid(original.sender),
                    IsGroup=original.chat.endswith(f"@{GROUP_SERVER}"),
                ),
            ),
            Message=e2e.Message(conversation=original.text or ""),
        )


def _iso(timestamp) -> str:
    """WhatsApp timestamps arrive as protobuf Timestamps or as seconds."""
    seconds = getattr(timestamp, "seconds", None)
    if seconds is None:
        seconds = timestamp
    try:
        return iso_utc(int(seconds))
    except (TypeError, ValueError):
        return iso_utc()
