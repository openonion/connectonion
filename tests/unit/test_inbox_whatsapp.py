"""Unit tests for the WhatsApp inbox provider.

LLM-Note: Tests for connectonion.inbox.whatsapp

What it tests:
- A MessageEv becomes the seven-field Message; a group @mention is told from a group message that is not for us
- Our own messages, echoed back over the same socket, are not delivered to ourselves
- check() names the missing extra, the unlinked device and a stale protocol snapshot, without a WhatsApp account
- missing() stays empty so the first `co whatsapp listen` is not told to run `co whatsapp listen`
- send() hands the text to the listener through the outbox spool, returns its id, surfaces its error, and says what to start when nobody answers

Components under test:
- Module: connectonion/inbox/whatsapp.py
"""

import json
import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import pytest

from connectonion.inbox import ANSWERING, PROVIDERS, SEEN, ListenerStopped, provider
from connectonion.inbox.store import Inbox, Message
from connectonion.inbox.whatsapp import GROUP_SERVER, USER_SERVER, WhatsApp, _context_info

OWN = "12025550100"
# The same account's LID. WhatsApp is migrating accounts to LID addressing, and
# a LID shares no digits with the phone number it belongs to — which is the
# whole reason matching one of them is not matching the account.
OWN_LID = "132754033377342"
PEER = "447700900123"
LID_SERVER = "lid"


@pytest.fixture(autouse=True)
def inbox_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.delenv("WHATSAPP_SESSION", raising=False)


@pytest.fixture
def sdk(monkeypatch):
    """A neonize stand-in. The real one is a 21MB compiled Go library behind an
    optional extra, so CI does not have it and these tests do not need it."""
    package = ModuleType("neonize")
    package.__file__ = "/nonexistent/neonize/__init__.py"
    utils = ModuleType("neonize.utils")
    message_utils = ModuleType("neonize.utils.message")
    message_utils.extract_text = lambda message: getattr(message, "text", "")
    jid_utils = ModuleType("neonize.utils.jid")
    jid_utils.build_jid = lambda user, server: SimpleNamespace(User=user, Server=server)
    # The protobuf types `_quoted` rebuilds a quoted message from. Only the
    # fields it sets are modelled; `test_a_quote_built_from_the_record_is_one_the
    # _sdk_accepts` runs the same code against the real ones, because a stand-in
    # agreeing with us proves nothing on its own.
    proto = ModuleType("neonize.proto")
    events = ModuleType("neonize.proto.Neonize_pb2")
    events.Message = lambda Info=None, Message=None: SimpleNamespace(Info=Info, Message=Message)
    events.MessageInfo = lambda ID="", MessageSource=None: SimpleNamespace(ID=ID, MessageSource=MessageSource)
    events.MessageSource = lambda Chat=None, Sender=None, IsGroup=False: SimpleNamespace(
        Chat=Chat, Sender=Sender, IsGroup=IsGroup)
    wa = ModuleType("neonize.proto.waE2E")
    e2e = ModuleType("neonize.proto.waE2E.WAWebProtobufsE2E_pb2")
    e2e.Message = lambda conversation="": SimpleNamespace(conversation=conversation)
    proto.Neonize_pb2 = events
    proto.waE2E = wa
    wa.WAWebProtobufsE2E_pb2 = e2e
    package.proto = proto
    # The connection's own events. Production imports these names from
    # neonize.events and registers handlers keyed on the class object, so the
    # sentinels here are the same objects a test fires — which is the whole
    # reason a stand-in can exercise the listener at all.
    connection = ModuleType("neonize.events")
    for name in ("ConnectedEv", "ConnectFailureEv", "DisconnectedEv", "KeepAliveRestoredEv",
                 "KeepAliveTimeoutEv", "LoggedOutEv", "MessageEv", "PairStatusEv",
                 "StreamReplacedEv", "TemporaryBanEv"):
        setattr(connection, name, type(name, (), {}))
    client_module = ModuleType("neonize.client")
    client_module.NewClient = lambda path: None      # each test replaces this
    package.events = connection
    package.client = client_module
    for name, module in [
        ("neonize", package), ("neonize.utils", utils),
        ("neonize.utils.message", message_utils), ("neonize.utils.jid", jid_utils),
        ("neonize.proto", proto), ("neonize.proto.Neonize_pb2", events),
        ("neonize.proto.waE2E", wa), ("neonize.proto.waE2E.WAWebProtobufsE2E_pb2", e2e),
        ("neonize.events", connection), ("neonize.client", client_module),
    ]:
        monkeypatch.setitem(sys.modules, name, module)
    return package


def jid(user, server=USER_SERVER, device=7):
    """A JID as the SDK hands it over, device part and all."""
    return SimpleNamespace(User=user, Server=server, Device=device)


def context(mentioned=(), participant="", name="extendedTextMessage"):
    # `name` is the protobuf field name, which is what says whether this is
    # text, an image or a reaction — the fake carries it because the real
    # descriptor does.
    descriptor = SimpleNamespace(name=name, label=1, LABEL_REPEATED=3, type=11, TYPE_MESSAGE=11)
    info = SimpleNamespace(mentionedJID=list(mentioned), participant=participant)
    variant = SimpleNamespace(contextInfo=info, HasField=lambda field: True)
    return descriptor, variant


def event(*, text="ship it", group=True, from_me=False, mentioned=(), participant="", message_id="3EB0A1"):
    descriptor, variant = context(mentioned, participant)
    message = SimpleNamespace(text=text, ListFields=lambda: [(descriptor, variant)])
    chat = jid("1203630000000", GROUP_SERVER) if group else jid(PEER)
    return SimpleNamespace(
        Info=SimpleNamespace(
            ID=message_id,
            Timestamp=SimpleNamespace(seconds=1756808267),
            MessageSource=SimpleNamespace(Chat=chat, Sender=jid(PEER), IsFromMe=from_me, IsGroup=group),
        ),
        Message=message,
    )


def linked(bot, *, ids=(OWN,)):
    """A connected bot, and the ids the account answers to.

    Default is the phone number alone — what a pre-LID account looks like — so
    the migrated case has to say so explicitly and cannot pass by accident."""
    bot._own_user = OWN
    bot._own_ids = frozenset(ids)
    return bot


# ---- inbound ---------------------------------------------------------------

def test_a_group_mention_becomes_a_message_addressed_to_us(sdk):
    bot = linked(WhatsApp())

    message = bot.to_message(event(text=f"@{OWN} ship it", mentioned=[f"{OWN}@{USER_SERVER}"]))

    assert message.to_dict() == {
        "id": "3EB0A1", "chat": f"1203630000000@{GROUP_SERVER}", "thread": None,
        "sender": f"{PEER}@{USER_SERVER}", "text": f"@{OWN} ship it",
        "kind": "text", "quoted": None, "mentioned": True, "at": "2025-09-02T10:17:47Z",
    }


def test_a_group_message_for_someone_else_is_recorded_but_not_addressed_to_us(sdk):
    bot = linked(WhatsApp())

    message = bot.to_message(event(text="@447700900999 ship it", mentioned=[f"447700900999@{USER_SERVER}"]))

    assert message.mentioned is False
    assert message.text == "@447700900999 ship it"


def test_a_reply_to_something_we_said_counts_as_addressing_us(sdk):
    bot = linked(WhatsApp())

    assert bot.to_message(event(participant=f"{OWN}@{USER_SERVER}")).mentioned is True


def test_our_number_written_into_the_text_counts_too(sdk):
    bot = linked(WhatsApp())

    assert bot.to_message(event(text=f"ask @{OWN} about it")).mentioned is True


def test_a_direct_message_is_addressed_to_us_by_existing(sdk):
    bot = linked(WhatsApp())

    message = bot.to_message(event(group=False))

    assert message.mentioned is True
    assert message.chat == f"{PEER}@{USER_SERVER}"


def test_before_the_connection_is_up_nothing_in_a_group_counts_as_addressed(sdk):
    # A group channel with mention_only stays quiet rather than answering
    # every message in it, which is the failure that costs nothing.
    assert WhatsApp().to_message(event(mentioned=[f"{OWN}@{USER_SERVER}"])).mentioned is False


def test_our_own_message_echoed_back_is_not_delivered_to_ourselves(sdk):
    assert linked(WhatsApp()).to_message(event(from_me=True)) is None


def test_the_same_person_from_two_phones_is_one_sender(sdk):
    # Keyed on the raw JID, `…:7@…` and `…:12@…` are two senders and a group
    # conversation splits in two.
    bot = linked(WhatsApp())
    phone, laptop = event(message_id="A"), event(message_id="B")
    phone.Info.MessageSource.Sender = jid(PEER, device=7)
    laptop.Info.MessageSource.Sender = jid(PEER, device=12)

    assert bot.to_message(phone).sender == bot.to_message(laptop).sender == f"{PEER}@{USER_SERVER}"


def test_a_message_with_no_context_info_is_still_read(sdk):
    bot = linked(WhatsApp())
    bare = SimpleNamespace(text="plain", ListFields=lambda: [])
    raw = event()
    raw.Message = bare

    assert bot.to_message(raw).text == "plain"


def test_a_mention_is_read_from_a_descriptor_shaped_like_protobuf_7(sdk):
    # protobuf 7 removed FieldDescriptor.label; is_repeated is what is left. The
    # fake above carries `label`, which is why these tests stayed green while a
    # real install on protobuf 7 dropped every message as "event not understood".
    bot = linked(WhatsApp())
    raw = event(text=f"@{OWN} ship it", mentioned=[f"{OWN}@{USER_SERVER}"])
    (_, variant), = raw.Message.ListFields()
    modern = SimpleNamespace(is_repeated=False, type=11, TYPE_MESSAGE=11)
    raw.Message.ListFields = lambda: [(modern, variant)]

    assert bot.to_message(raw).mentioned is True


def test_real_protobuf_descriptors_are_read_on_whichever_major_version_is_installed():
    # No neonize needed: protobuf itself is a core dependency. A message with a
    # singular message field and a repeated field walks both branches.
    from google.protobuf import descriptor_pb2

    message = descriptor_pb2.FileDescriptorProto(name="x.proto", dependency=["y.proto"])
    message.options.java_package = "x"

    assert _context_info(message) is None


def test_an_at_mention_of_our_lid_is_addressed_to_us(sdk):
    # The exact shape from the 1.8.6 acceptance: WhatsApp had migrated the bot
    # number to LID addressing, so the @mention the owner typed arrived as the
    # account's LID. Matching only the phone number made it `mentioned: False`
    # and the bot sat silent in the group while being addressed.
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    message = bot.to_message(event(text=f"@{OWN_LID} 测试",
                                   mentioned=[f"{OWN_LID}@{LID_SERVER}"]))

    assert message.mentioned is True


def test_someone_elses_lid_is_not_us(sdk):
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    assert bot.to_message(event(text="@999888777666 ship it",
                                mentioned=[f"999888777666@{LID_SERVER}"])).mentioned is False


def test_a_reply_to_something_we_said_under_our_lid_counts(sdk):
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    assert bot.to_message(event(participant=f"{OWN_LID}@{LID_SERVER}")).mentioned is True


def test_the_phone_number_still_addresses_a_migrated_account(sdk):
    # Both ids stay live: groups migrate at different times, and older ones
    # still carry the number.
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    assert bot.to_message(event(text=f"@{OWN} ship it",
                                mentioned=[f"{OWN}@{USER_SERVER}"])).mentioned is True


def test_the_identity_read_at_connect_carries_both_the_number_and_the_lid():
    # `Device` has carried both fields all along; only JID was being read.
    device = SimpleNamespace(
        JID=SimpleNamespace(User=OWN, Server=USER_SERVER, Device=2),
        LID=SimpleNamespace(User=OWN_LID, Server=LID_SERVER, Device=2),
    )

    phone, ids = WhatsApp._read_identity(SimpleNamespace(get_me=lambda: device))

    assert phone == OWN
    assert ids == frozenset({OWN, OWN_LID})


def test_an_account_with_no_lid_yet_is_still_itself():
    device = SimpleNamespace(
        JID=SimpleNamespace(User=OWN, Server=USER_SERVER, Device=2),
        LID=SimpleNamespace(User="", Server="", Device=0),
    )

    phone, ids = WhatsApp._read_identity(SimpleNamespace(get_me=lambda: device))

    assert phone == OWN
    assert ids == frozenset({OWN})


def reply_to(participant, *, quoted_text="the price sheet is wrong", text="fix this",
             stanza="3EB0QUOTED", quoted_kind="extendedTextMessage"):
    """A group message that quotes an earlier one, the way WhatsApp sends it."""
    quoted_descriptor = SimpleNamespace(name=quoted_kind, label=1, LABEL_REPEATED=3,
                                        type=11, TYPE_MESSAGE=11)
    quoted_body = SimpleNamespace(text=quoted_text,
                                  ListFields=lambda: [(quoted_descriptor, SimpleNamespace())])
    info = SimpleNamespace(mentionedJID=[], participant=participant,
                           stanzaID=stanza, quotedMessage=quoted_body)
    descriptor = SimpleNamespace(name="extendedTextMessage", label=1, LABEL_REPEATED=3,
                                 type=11, TYPE_MESSAGE=11)
    value = SimpleNamespace(contextInfo=info, HasField=lambda field: True)
    raw = event(text=text)
    raw.Message = SimpleNamespace(text=text, ListFields=lambda: [(descriptor, value)])
    return raw


def test_a_reply_carries_what_it_replied_to(sdk):
    # Someone quotes a line and writes "fix this". Without the quote the record
    # is the two new words and no trace of what "this" was, so a consumer can
    # neither answer it nor tell it was addressed.
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    message = bot.to_message(reply_to(f"{OWN_LID}@{LID_SERVER}"))

    assert message.quoted == {
        "id": "3EB0QUOTED",
        "sender": f"{OWN_LID}@{LID_SERVER}",
        "text": "the price sheet is wrong",
        "kind": "text",
        "from_me": True,
    }


def test_replying_to_us_and_replying_to_someone_else_are_different_events(sdk):
    # The distinction the whole field exists for: a trigger policy of
    # "direct message, @mention, or reply to us" cannot be implemented without
    # separating these two.
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    to_us = bot.to_message(reply_to(f"{OWN_LID}@{LID_SERVER}"))
    to_someone_else = bot.to_message(reply_to(f"{PEER}@{USER_SERVER}"))

    assert (to_us.quoted["from_me"], to_us.mentioned) == (True, True)
    assert (to_someone_else.quoted["from_me"], to_someone_else.mentioned) == (False, False)


def test_a_reply_to_us_by_phone_number_counts_too(sdk):
    # Groups migrate to LID at different times; the older ones still quote by
    # number, and both are us.
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    assert bot.to_message(reply_to(f"{OWN}@{USER_SERVER}")).quoted["from_me"] is True


def test_the_record_and_the_gate_cannot_disagree(sdk):
    # `mentioned` reads the same from_me the record carries, rather than
    # recomputing it. Two copies of "was this addressed to us" can drift, and
    # when they do a `mentioned: false` on a reply is impossible to argue with
    # in either direction.
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    for participant in (f"{OWN_LID}@{LID_SERVER}", f"{PEER}@{USER_SERVER}"):
        message = bot.to_message(reply_to(participant))
        assert message.mentioned == message.quoted["from_me"]


def test_a_quoted_photo_says_it_was_a_photo(sdk):
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    quoted = bot.to_message(reply_to(f"{PEER}@{USER_SERVER}", quoted_kind="imageMessage",
                                     quoted_text="")).quoted

    assert quoted["kind"] == "image" and quoted["text"] == ""


def test_a_message_that_is_not_a_reply_has_no_quote(sdk):
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    assert bot.to_message(event(text="just talking")).quoted is None


def test_a_context_with_no_stanza_id_is_not_a_quote_but_still_reaches_us(sdk):
    # A reply always carries a stanzaID in practice. If one ever does not, the
    # reference is not worth carrying — and the message must still be seen as
    # addressed to us rather than silently downgraded because a field was
    # missing.
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))
    raw = reply_to(f"{OWN_LID}@{LID_SERVER}", stanza="")

    message = bot.to_message(raw)

    assert message.quoted is None
    assert message.mentioned is True


def test_a_quote_survives_the_queue_file(sdk):
    inbox = Inbox("whatsapp")
    reference = {"id": "3EB0Q", "sender": "x@s.whatsapp.net", "text": "earlier",
                 "kind": "text", "from_me": True}
    inbox.deliver(Message(id="A1", chat=f"1203630000000@{GROUP_SERVER}", sender=PEER,
                          text="fix this", kind="text", quoted=reference,
                          mentioned=True, at="2026-09-18T00:00:00Z", thread=None))

    assert [m.quoted for m in inbox.list_messages()] == [reference]


def test_a_record_written_before_quotes_existed_has_none():
    assert Message.from_dict({"id": "A1", "chat": "c", "text": "hi"}).quoted is None


def variant(name, text=""):
    """An event carrying one named message variant, the way the SDK hands it over."""
    raw = event(text=text)
    descriptor = SimpleNamespace(name=name, label=1, LABEL_REPEATED=3, type=11, TYPE_MESSAGE=11)
    value = SimpleNamespace(contextInfo=SimpleNamespace(mentionedJID=[], participant=""),
                            HasField=lambda field: True)
    raw.Message = SimpleNamespace(text=text, ListFields=lambda: [(descriptor, value)])
    return raw


def test_a_photo_is_not_the_same_input_as_an_empty_message(sdk):
    # Both arrive with no text. Without a kind beside it a consumer can neither
    # say "I can't read images yet" nor correctly ignore it, because it cannot
    # tell which one happened.
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    photo = bot.to_message(variant("imageMessage"))
    nothing = bot.to_message(variant("conversation"))

    assert (photo.kind, photo.text) == ("image", "")
    assert (nothing.kind, nothing.text) == ("text", "")


@pytest.mark.parametrize("field,kind", [
    ("conversation", "text"), ("extendedTextMessage", "text"),
    ("imageMessage", "image"), ("videoMessage", "video"), ("ptvMessage", "video"),
    ("audioMessage", "audio"), ("documentMessage", "document"),
    ("stickerMessage", "sticker"), ("locationMessage", "location"),
    ("contactMessage", "contact"), ("reactionMessage", "reaction"),
])
def test_each_variant_is_named_in_words_a_person_would_use(sdk, field, kind):
    assert linked(WhatsApp(), ids=(OWN,)).to_message(variant(field)).kind == kind


def test_a_variant_we_have_never_seen_still_arrives_as_something(sdk):
    # WhatsApp has 107 of these and adds more. An unknown one keeps the
    # protobuf's own name rather than being flattened into "text".
    assert linked(WhatsApp(), ids=(OWN,)).to_message(variant("pollCreationMessageV9")).kind \
        == "pollcreationv9"


def test_a_reaction_is_recorded_but_never_addressed_to_us(sdk):
    # Reactions come back over the same socket, including the ones this bot puts
    # on its own queue. They are worth having in the log and are not questions.
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))

    direct = variant("reactionMessage")
    direct.Info.MessageSource.IsGroup = False

    assert bot.to_message(variant("reactionMessage")).mentioned is False
    assert bot.to_message(direct).mentioned is False    # even one-to-one


def test_a_kind_survives_the_queue_file(sdk):
    inbox = Inbox("whatsapp")
    inbox.deliver(Message(id="A1", chat=f"1203630000000@{GROUP_SERVER}", sender=PEER,
                          text="", kind="image", mentioned=True, at="2026-09-18T00:00:00Z",
                          thread=None))

    assert [m.kind for m in inbox.list_messages()] == ["image"]


def test_a_queue_file_written_before_kinds_existed_reads_as_text():
    # Upgrading with messages already in new/ must not invent a kind for them.
    assert Message.from_dict({"id": "A1", "chat": "c", "text": "hi"}).kind == "text"


def test_a_descriptor_with_no_readable_name_costs_nothing(sdk):
    # Reading an attribute a protobuf release had removed is exactly how every
    # message stopped being delivered in 1.8.6a1. A kind we cannot read is not
    # worth a message.
    bot = linked(WhatsApp(), ids=(OWN,))
    raw = event(text="still here")
    nameless = SimpleNamespace(label=1, LABEL_REPEATED=3, type=11, TYPE_MESSAGE=11)
    value = SimpleNamespace(contextInfo=SimpleNamespace(mentionedJID=[], participant=""),
                            HasField=lambda field: True)
    raw.Message = SimpleNamespace(text="still here", ListFields=lambda: [(nameless, value)])

    message = bot.to_message(raw)

    assert message.text == "still here" and message.kind == "text"


def test_real_protobuf_variants_are_named_on_the_installed_version():
    # The fakes carry the fields we chose to model. This reads the name off a
    # real descriptor, so a protobuf that renames or removes it fails here
    # rather than in somebody's group.
    from google.protobuf import descriptor_pb2
    from connectonion.inbox.whatsapp import _kind

    message = descriptor_pb2.FileDescriptorProto(name="x.proto")
    message.options.java_package = "x"          # a singular message field is set

    assert _kind(message) == "options"          # the field's own name, lowercased


def test_sending_from_an_unlinked_device_says_what_to_do(sdk):
    # whatsmeow says "the store doesn't contain a device JID" — true, and it
    # names an internal structure rather than what happened.
    bot = WhatsApp()

    def refuse(*_args, **_kwargs):
        raise RuntimeError("the store doesn't contain a device JID")

    bot._client = SimpleNamespace(send_message=refuse, build_reply_message=refuse)
    inbox = Inbox("whatsapp")
    stop, thread = drain_once(bot, inbox)
    try:
        with pytest.raises(RuntimeError) as failed:
            bot.send(f"1203630000000@{GROUP_SERVER}", "on it")
    finally:
        stop.set()
        thread.join(timeout=5)

    assert "not linked any more" in str(failed.value)
    assert "co whatsapp listen" in str(failed.value)
    assert "device JID" not in str(failed.value)


def test_a_failure_we_do_not_recognise_keeps_its_own_words(sdk):
    # Guessing a fix for an error we have not seen is how the wrong advice gets
    # written; the real message is what somebody can search for.
    bot = WhatsApp()

    def refuse(*_args, **_kwargs):
        raise RuntimeError("websocket: close 1006 (abnormal closure)")

    bot._client = SimpleNamespace(send_message=refuse, build_reply_message=refuse)
    inbox = Inbox("whatsapp")
    stop, thread = drain_once(bot, inbox)
    try:
        with pytest.raises(RuntimeError) as failed:
            bot.send(f"1203630000000@{GROUP_SERVER}", "on it")
    finally:
        stop.set()
        thread.join(timeout=5)

    assert "close 1006" in str(failed.value)


class Socket:
    """A neonize client that hands the listener whichever events we name.

    `connect()` fires them and returns, which is what the real one does when
    the connection ends — the difference the listener has to notice is whether
    it can ever come back.
    """

    def __init__(self, *events):
        self.events, self.handlers = events, {}
        self.disconnected = False

    def event(self, kind):
        def register(handler):
            self.handlers[kind] = handler
            return handler
        return register

    def connect(self):
        for kind, payload in self.events:
            handler = self.handlers.get(kind)
            if handler:
                handler(self, payload)

    def disconnect(self):
        self.disconnected = True

    def get_me(self):
        return SimpleNamespace(JID=SimpleNamespace(User=OWN, Server=USER_SERVER, Device=1),
                               LID=SimpleNamespace(User=OWN_LID, Server=LID_SERVER, Device=1))


def listen_through(monkeypatch, inbox, *events):
    """Run the listener over a socket that fires `events`, and return the bot."""
    import neonize.events as ev

    bot = WhatsApp()
    monkeypatch.setattr("neonize.client.NewClient", lambda path: Socket(*events))
    bot.run(inbox)
    return bot


def test_being_unlinked_stops_the_listener_instead_of_leaving_it_running(sdk, monkeypatch):
    # The production failure: the phone unlinks the device, the process keeps
    # its socket, prints nothing more, and receives nothing ever again — so
    # "nobody has messaged us" and "we were logged out yesterday" look the same.
    import neonize.events as ev

    inbox = Inbox("whatsapp")

    with pytest.raises(ListenerStopped) as stopped:
        listen_through(monkeypatch, inbox, (ev.LoggedOutEv, SimpleNamespace(Reason="401")))

    assert "logged out" in str(stopped.value)
    assert "co whatsapp listen" in str(stopped.value)       # names the way back
    assert "logged out" in (inbox.root / "log").read_text(encoding="utf-8")


def test_another_client_taking_the_session_stops_this_one(sdk, monkeypatch):
    # WhatsApp allows one socket per linked device, so a second listener
    # silently displaces the first.
    import neonize.events as ev

    inbox = Inbox("whatsapp")

    with pytest.raises(ListenerStopped) as stopped:
        listen_through(monkeypatch, inbox, (ev.StreamReplacedEv, SimpleNamespace()))

    assert "took this session over" in str(stopped.value)


def test_a_temporary_ban_stops_the_listener_and_says_when(sdk, monkeypatch):
    import neonize.events as ev

    inbox = Inbox("whatsapp")

    with pytest.raises(ListenerStopped) as stopped:
        listen_through(monkeypatch, inbox,
                       (ev.TemporaryBanEv, SimpleNamespace(Code=402, Expire=3600)))

    assert "402" in str(stopped.value) and "3600" in str(stopped.value)


def test_an_ordinary_disconnection_is_logged_and_survived(sdk, monkeypatch):
    # The SDK reconnects from these. Logging them is what makes a later gap
    # visible; stopping on them would take the listener down every time a
    # laptop's wifi blinked.
    import neonize.events as ev

    inbox = Inbox("whatsapp")

    listen_through(monkeypatch, inbox,
                   (ev.DisconnectedEv, SimpleNamespace(status=0)),
                   (ev.KeepAliveTimeoutEv, SimpleNamespace(ErrorCount=2, LastSuccess=0)),
                   (ev.KeepAliveRestoredEv, SimpleNamespace()))

    log = (inbox.root / "log").read_text(encoding="utf-8")
    assert "disconnected" in log and "keepalive timed out" in log and "keepalive restored" in log


def test_a_fatal_event_asks_the_socket_to_close(sdk, monkeypatch):
    # Not just a flag: the connection has to actually be told to stop, or the
    # process keeps the socket it can no longer use.
    import neonize.events as ev

    sockets = []
    monkeypatch.setattr("neonize.client.NewClient",
                        lambda path: sockets.append(Socket((ev.LoggedOutEv, SimpleNamespace(Reason="401"))))
                        or sockets[-1])
    with pytest.raises(ListenerStopped):
        WhatsApp().run(Inbox("whatsapp"))

    assert sockets[0].disconnected is True


def test_a_healthy_connection_raises_nothing(sdk, monkeypatch):
    import neonize.events as ev

    inbox = Inbox("whatsapp")

    listen_through(monkeypatch, inbox, (ev.ConnectedEv, SimpleNamespace()))

    assert "connected as" in (inbox.root / "log").read_text(encoding="utf-8")


# ---- setup -----------------------------------------------------------------

def test_the_first_listen_is_not_told_to_run_listen():
    # missing() gates every verb, and linking happens inside listen itself.
    assert WhatsApp().missing() == []


def test_check_names_the_extra_when_the_library_is_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "neonize", None)

    problems = WhatsApp().check()

    assert len(problems) == 1
    assert "pip install 'connectonion[whatsapp]'" in problems[0]


def neonize_import_raises(monkeypatch, exc):
    """neonize installed, and importing it failing the way the OS made it fail.

    Not `sys.modules[...] = None`, which is how the test above stages an absent
    package: the distinction being tested is precisely between "pip has not run"
    and "pip ran and the import still fails", so the two have to be staged
    differently."""
    import builtins

    real = builtins.__import__

    def fake(name, *args, **kwargs):
        if name == "neonize":
            raise exc
        return real(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "neonize", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake)


def test_a_missing_system_library_is_not_reported_as_a_missing_pip_package(monkeypatch):
    # neonize imports python-magic, which binds to libmagic — a system library
    # pip cannot install. Answering with the extra sends someone to rerun a pip
    # command that already succeeded, and that will succeed again, and that will
    # never fix this.
    neonize_import_raises(monkeypatch, ImportError("failed to find libmagic.  Check your installation"))
    monkeypatch.setattr(sys, "platform", "darwin")

    problems = WhatsApp().check()

    assert len(problems) == 1
    assert "pip install" not in problems[0]
    assert "brew install libmagic" in problems[0]


def test_the_system_library_is_named_for_the_platform_in_hand(monkeypatch):
    neonize_import_raises(monkeypatch, ImportError("failed to find libmagic.  Check your installation"))
    monkeypatch.setattr(sys, "platform", "linux")

    problems = WhatsApp().check()

    assert "apt install libmagic1" in problems[0]
    assert "brew" not in problems[0]


def test_an_import_failure_we_cannot_name_still_carries_its_own_message(monkeypatch):
    # Guessing a fix for an error we do not recognise is how the libmagic
    # answer got written; the real message is what someone can search.
    neonize_import_raises(monkeypatch, ImportError("libz.so.1: cannot open shared object file"))

    problems = WhatsApp().check()

    assert "libz.so.1: cannot open shared object file" in problems[0]
    assert "pip install" not in problems[0]


def test_check_says_how_to_link_a_device_when_none_is(sdk, monkeypatch):
    monkeypatch.setattr(WhatsApp, "protocol_snapshot", lambda self: None)

    problems = WhatsApp().check()

    assert len(problems) == 1
    assert "co whatsapp listen" in problems[0]
    assert "Linked devices" in problems[0]


def session_db(path, *, devices):
    """A session file shaped like whatsmeow's: the device table, with a row
    only once a phone has confirmed the link."""
    import sqlite3

    with sqlite3.connect(path) as db:
        db.execute("create table whatsmeow_device (jid text primary key)")
        for n in range(devices):
            db.execute("insert into whatsmeow_device values (?)", (f"{OWN}.0:{n}@{USER_SERVER}",))
    return path


def test_check_passes_once_a_device_is_linked(sdk, tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_SESSION", str(session_db(tmp_path / "session.db", devices=1)))
    monkeypatch.setattr(WhatsApp, "protocol_snapshot", lambda self: time.time())

    assert WhatsApp().check() == []


def test_a_session_whose_qr_was_never_scanned_is_not_a_linked_device(sdk, tmp_path, monkeypatch):
    # What a failed or abandoned scan leaves: listen created the file for the QR,
    # no phone confirmed. check used to pass here, so a user whose scan had
    # failed was told everything was ready. Reproduced live on 1.8.6a1.
    monkeypatch.setenv("WHATSAPP_SESSION", str(session_db(tmp_path / "session.db", devices=0)))
    monkeypatch.setattr(WhatsApp, "protocol_snapshot", lambda self: time.time())

    problems = WhatsApp().check()

    assert len(problems) == 1
    # Both stories, because the file cannot tell them apart.
    assert "No linked device" in problems[0]
    assert "logged out from the phone" in problems[0]
    assert "co whatsapp listen" in problems[0]


def test_a_session_file_that_is_not_a_database_is_not_a_linked_device(sdk, tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_SESSION", str(tmp_path / "session.db"))
    (tmp_path / "session.db").write_bytes(b"not sqlite")
    monkeypatch.setattr(WhatsApp, "protocol_snapshot", lambda self: time.time())

    assert "No linked device" in WhatsApp().check()[0]


def test_an_old_protocol_snapshot_is_reported_before_it_fails_namelessly(sdk, tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_SESSION", str(session_db(tmp_path / "session.db", devices=1)))
    monkeypatch.setattr(WhatsApp, "protocol_snapshot", lambda self: time.time() - 400 * 86400)

    problems = WhatsApp().check()

    assert len(problems) == 1
    assert "400 days old" in problems[0]
    assert "newer neonize" in problems[0]


def test_the_session_lives_under_the_inbox_unless_it_is_pointed_elsewhere(monkeypatch, tmp_path):
    assert WhatsApp().session_path.name == "session.db"
    monkeypatch.setenv("WHATSAPP_SESSION", str(tmp_path / "elsewhere.db"))
    assert WhatsApp().session_path == tmp_path / "elsewhere.db"


def test_whatsapp_is_a_provider_by_name():
    assert "whatsapp" in PROVIDERS
    assert provider("whatsapp").name == "whatsapp"


# ---- outbound --------------------------------------------------------------

def wait_for_ticket(spool, timeout=5.0):
    """The ticket of the request `send` just wrote, once it is on disk."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pending = list(spool.glob("*.json")) if spool.exists() else []
        if pending:
            return pending[0].name[: -len(".json")]
        time.sleep(0.01)
    raise AssertionError("send never wrote a request into the outbox")


def drain_once(bot, inbox):
    """One pass of the listener's sender thread, then stop."""
    stop = threading.Event()
    thread = threading.Thread(target=bot._drain_outbox, args=(inbox, stop), daemon=True)
    thread.start()
    return stop, thread


# ---- reactions: the queue, made visible from inside the chat ----------------

def reacting_bot(reactions):
    """A connected bot whose reactions are recorded instead of sent."""
    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))
    bot._react_now = lambda chat, message_id, emoji, sender: (
        reactions.append((chat, message_id, emoji, sender)) or "3EB0REACT")
    return bot


def addressed(message_id="AC8191", mentioned=True):
    return Message(id=message_id, chat=f"1203630000000@{GROUP_SERVER}",
                   sender=f"{PEER}@{USER_SERVER}", text="那个价格表还是不对",
                   mentioned=mentioned, at="2026-09-17T04:27:57Z", thread=None)


def test_a_message_we_would_answer_is_reacted_to_as_it_is_queued(sdk):
    # From the group's side, the gap between "asked" and "answered" is currently
    # indistinguishable from the bot being down. The reaction is the receipt.
    reactions = []
    bot = reacting_bot(reactions)
    inbox = Inbox("whatsapp")

    bot.take(inbox, addressed())

    assert reactions == [(f"1203630000000@{GROUP_SERVER}", "AC8191", SEEN, f"{PEER}@{USER_SERVER}")]
    assert [m.id for m in inbox.list_messages()] == ["AC8191"]


def test_a_group_message_not_addressed_to_us_is_not_reacted_to(sdk):
    # It is still recorded — context is kept — but the bot has no business
    # marking messages nobody asked it about.
    reactions = []
    bot = reacting_bot(reactions)
    inbox = Inbox("whatsapp")

    bot.take(inbox, addressed(mentioned=False))

    assert reactions == []
    assert [m.id for m in inbox.list_messages()] == ["AC8191"]


def test_a_duplicate_is_not_reacted_to_a_second_time(sdk):
    reactions = []
    bot = reacting_bot(reactions)
    inbox = Inbox("whatsapp")

    bot.take(inbox, addressed())
    bot.take(inbox, addressed())

    assert len(reactions) == 1


def test_a_reaction_that_fails_is_a_log_line_not_a_dead_listener(sdk):
    # This runs inside the MessageEv handler, where an exception is a Go-side
    # panic that takes the listener down. A receipt is never worth the process.
    def explode(*_args):
        raise RuntimeError("rate limited")

    bot = linked(WhatsApp(), ids=(OWN, OWN_LID))
    bot._react_now = explode
    inbox = Inbox("whatsapp")

    bot.take(inbox, addressed())

    assert [m.id for m in inbox.list_messages()] == ["AC8191"]
    assert "rate limited" in (inbox.root / "log").read_text(encoding="utf-8")


def test_reactions_can_be_turned_off(sdk, monkeypatch):
    # A visible action in someone else's group needs a way to stop.
    monkeypatch.setenv("CO_INBOX_REACT", "0")
    reactions = []
    bot = reacting_bot(reactions)

    bot.take(Inbox("whatsapp"), addressed())

    assert reactions == []


def test_a_reaction_reaches_the_listener_through_the_spool(sdk):
    # `react` is called from `reply`, which is a different process: WhatsApp
    # allows one socket per device, so it queues like every other outbound.
    built = {}
    bot = WhatsApp()
    bot._client = SimpleNamespace(
        send_message=lambda to, message: SimpleNamespace(ID="3EB0REACT"),
        build_reaction=lambda chat, sender, message_id, reaction: built.update(
            chat=chat.User, sender=sender.User, message_id=message_id, reaction=reaction) or "built",
    )
    inbox = Inbox("whatsapp")
    stop, thread = drain_once(bot, inbox)
    try:
        assert bot.react(f"1203630000000@{GROUP_SERVER}", "AC8191", ANSWERING,
                         sender=f"{PEER}@{USER_SERVER}") == "3EB0REACT"
    finally:
        stop.set()
        thread.join(timeout=5)

    assert built == {"chat": "1203630000000", "sender": PEER,
                     "message_id": "AC8191", "reaction": ANSWERING}


def test_the_two_reactions_are_different(sdk):
    # The pair is the point: one marker that never changes says nothing about
    # whether anything is happening.
    assert SEEN != ANSWERING


def test_send_hands_the_text_to_the_listener_and_returns_its_id(sdk):
    bot = WhatsApp()
    bot._client = SimpleNamespace(send_message=lambda to, text: SimpleNamespace(ID="3EB0SENT"))
    inbox = Inbox("whatsapp")
    stop, thread = drain_once(bot, inbox)
    try:
        assert bot.send(f"1203630000000@{GROUP_SERVER}", "on it") == "3EB0SENT"
    finally:
        stop.set()
        thread.join(timeout=5)

    # Request, answer and both staging files are consumed: a spool that grows
    # by two files per reply would fill a disk over a long-running listener.
    assert list((inbox.root / "outbox").iterdir()) == []


def test_a_reply_quotes_the_message_it_answers(sdk):
    # `reply` recorded reply_to in sent.jsonl while the message that left was a
    # loose one: the spool carried the id and the far end read only chat and
    # text. In a busy group the answer then has no visible link to the question,
    # and the ledger says it does.
    bot = WhatsApp()
    quoted_with = {}
    bot._client = SimpleNamespace(
        send_message=lambda to, message: SimpleNamespace(ID="3EB0SENT"),
        build_reply_message=lambda text, quoted: quoted_with.update(
            text=text, id=quoted.Info.ID, sender=quoted.Info.MessageSource.Sender.User,
            quoted_text=quoted.Message.conversation) or "built",
    )
    inbox = Inbox("whatsapp")
    inbox.deliver(Message(id="AC8191", chat=f"1203630000000@{GROUP_SERVER}",
                          sender=f"{PEER}@{USER_SERVER}", text="那个价格表还是不对",
                          mentioned=True, at="2026-09-17T04:27:57Z", thread=None))
    stop, thread = drain_once(bot, inbox)
    try:
        assert bot.send(f"1203630000000@{GROUP_SERVER}", "on it", reply_to="AC8191") == "3EB0SENT"
    finally:
        stop.set()
        thread.join(timeout=5)

    assert quoted_with == {"text": "on it", "id": "AC8191", "sender": PEER,
                           "quoted_text": "那个价格表还是不对"}


def test_a_plain_send_does_not_quote_anything(sdk):
    bot = WhatsApp()
    calls = []
    bot._client = SimpleNamespace(
        send_message=lambda to, message: SimpleNamespace(ID="3EB0SENT"),
        build_reply_message=lambda text, quoted: calls.append(text) or "built",
    )
    inbox = Inbox("whatsapp")
    stop, thread = drain_once(bot, inbox)
    try:
        bot.send(f"1203630000000@{GROUP_SERVER}", "on it")
    finally:
        stop.set()
        thread.join(timeout=5)

    assert calls == []


def test_a_reply_to_a_message_we_no_longer_have_still_goes_out(sdk):
    # The quote is reconstructed from the stored record. A message that aged out
    # of received.jsonl must not cost the person their answer — the reply lands
    # in the right chat, unquoted, rather than failing.
    bot = WhatsApp()
    bot._client = SimpleNamespace(
        send_message=lambda to, message: SimpleNamespace(ID="3EB0SENT"),
        build_reply_message=lambda text, quoted: (_ for _ in ()).throw(
            AssertionError("nothing to quote; should not have been called")),
    )
    inbox = Inbox("whatsapp")
    stop, thread = drain_once(bot, inbox)
    try:
        assert bot.send(f"1203630000000@{GROUP_SERVER}", "on it", reply_to="GONE") == "3EB0SENT"
    finally:
        stop.set()
        thread.join(timeout=5)


def test_an_answer_that_is_not_there_yet_is_waited_for_not_read(sdk, monkeypatch):
    """The failure CI found: `write_text` creates an empty file before it
    writes, so a reader polling `exists()` could read zero bytes and die with
    `JSONDecodeError: Expecting value: line 1 column 1`. `send` must treat an
    unreadable answer as one that has not arrived."""
    monkeypatch.setattr("connectonion.inbox.whatsapp.SEND_TIMEOUT_SECONDS", 10.0)
    spool = Inbox("whatsapp").root / "outbox"
    bot = WhatsApp()
    answered = {}

    def ask():
        try:
            answered["id"] = bot.send(f"{PEER}@{USER_SERVER}", "on it")
        except Exception as exc:  # recorded, so the assert names it
            answered["error"] = exc

    caller = threading.Thread(target=ask, daemon=True)
    caller.start()
    try:
        ticket = wait_for_ticket(spool)
        # Exactly what the racing writer exposed: the name is there, the
        # content is not.
        (spool / f"{ticket}.result").write_text("")
        time.sleep(0.3)
        assert answered == {}, f"send did not survive an empty answer: {answered}"

        (spool / f"{ticket}.result").write_text(json.dumps({"id": "3EB0LATE"}))
        caller.join(timeout=5)
    finally:
        caller.join(timeout=5)

    assert answered == {"id": "3EB0LATE"}


def test_the_listener_addresses_the_chat_the_question_was_asked_in(sdk):
    bot = WhatsApp()
    seen = {}

    def record(to, text):
        seen["to"] = (to.User, to.Server)
        seen["text"] = text
        return SimpleNamespace(ID="X")

    bot._client = SimpleNamespace(send_message=record)
    stop, thread = drain_once(bot, Inbox("whatsapp"))
    try:
        bot.send(f"1203630000000@{GROUP_SERVER}", "on it")
    finally:
        stop.set()
        thread.join(timeout=5)

    assert seen == {"to": ("1203630000000", GROUP_SERVER), "text": "on it"}


def test_a_refusal_from_whatsapp_reaches_the_process_that_asked(sdk):
    bot = WhatsApp()

    def refuse(to, text):
        raise RuntimeError("not-authorized")

    bot._client = SimpleNamespace(send_message=refuse)
    inbox = Inbox("whatsapp")
    stop, thread = drain_once(bot, inbox)
    try:
        with pytest.raises(RuntimeError, match="not-authorized"):
            bot.send(f"{PEER}@{USER_SERVER}", "on it")
    finally:
        stop.set()
        thread.join(timeout=5)

    assert "send to" in inbox.logfile.read_text()


def test_with_no_listener_send_says_what_to_start_instead_of_opening_a_second_socket(sdk, monkeypatch):
    monkeypatch.setattr("connectonion.inbox.whatsapp.SEND_TIMEOUT_SECONDS", 0.2)

    with pytest.raises(RuntimeError, match="co whatsapp listen"):
        WhatsApp().send(f"{PEER}@{USER_SERVER}", "anyone there")

    spool = Inbox("whatsapp").root / "outbox"
    assert list(spool.iterdir()) == []  # the abandoned request is not left to be sent later


def test_an_unreadable_spool_file_is_discarded_rather_than_retried_forever(sdk):
    bot = WhatsApp()
    inbox = Inbox("whatsapp")
    spool = inbox.root / "outbox"
    spool.mkdir(parents=True, exist_ok=True)
    (spool / "1-garbage.json").write_text("{not json")

    stop, thread = drain_once(bot, inbox)
    deadline = time.monotonic() + 5
    while (spool / "1-garbage.json").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    stop.set()
    thread.join(timeout=5)

    assert not (spool / "1-garbage.json").exists()


def test_a_half_written_request_is_never_glob_ed_as_a_send(sdk):
    # send() stages to `<ticket>.json.partial` and renames, so the listener's
    # *.json glob only ever sees a complete payload.
    bot = WhatsApp()
    sent = []
    bot._client = SimpleNamespace(send_message=lambda to, text: (sent.append(text), SimpleNamespace(ID="X"))[1])
    inbox = Inbox("whatsapp")
    spool = inbox.root / "outbox"
    spool.mkdir(parents=True, exist_ok=True)
    (spool / "1-partial.json.partial").write_text('{"chat": "x@s.whats')

    stop, thread = drain_once(bot, inbox)
    try:
        bot.send(f"{PEER}@{USER_SERVER}", "complete")
    finally:
        stop.set()
        thread.join(timeout=5)

    assert sent == ["complete"]
