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

from connectonion.inbox import PROVIDERS, provider
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
    for name, module in [
        ("neonize", package), ("neonize.utils", utils),
        ("neonize.utils.message", message_utils), ("neonize.utils.jid", jid_utils),
        ("neonize.proto", proto), ("neonize.proto.Neonize_pb2", events),
        ("neonize.proto.waE2E", wa), ("neonize.proto.waE2E.WAWebProtobufsE2E_pb2", e2e),
    ]:
        monkeypatch.setitem(sys.modules, name, module)
    return package


def jid(user, server=USER_SERVER, device=7):
    """A JID as the SDK hands it over, device part and all."""
    return SimpleNamespace(User=user, Server=server, Device=device)


def context(mentioned=(), participant=""):
    descriptor = SimpleNamespace(label=1, LABEL_REPEATED=3, type=11, TYPE_MESSAGE=11)
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
        "mentioned": True, "at": "2025-09-02T10:17:47Z",
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
    assert "never linked" in problems[0]
    assert "co whatsapp listen" in problems[0]


def test_a_session_file_that_is_not_a_database_is_not_a_linked_device(sdk, tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_SESSION", str(tmp_path / "session.db"))
    (tmp_path / "session.db").write_bytes(b"not sqlite")
    monkeypatch.setattr(WhatsApp, "protocol_snapshot", lambda self: time.time())

    assert "never linked" in WhatsApp().check()[0]


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
