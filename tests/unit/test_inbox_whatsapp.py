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

import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import pytest

from connectonion.inbox import PROVIDERS, provider
from connectonion.inbox.store import Inbox
from connectonion.inbox.whatsapp import GROUP_SERVER, USER_SERVER, WhatsApp

OWN = "12025550100"
PEER = "447700900123"


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
    for name, module in [
        ("neonize", package), ("neonize.utils", utils),
        ("neonize.utils.message", message_utils), ("neonize.utils.jid", jid_utils),
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


def linked(bot):
    bot._own_user = OWN
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


# ---- setup -----------------------------------------------------------------

def test_the_first_listen_is_not_told_to_run_listen():
    # missing() gates every verb, and linking happens inside listen itself.
    assert WhatsApp().missing() == []


def test_check_names_the_extra_when_the_library_is_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "neonize", None)

    problems = WhatsApp().check()

    assert len(problems) == 1
    assert "pip install 'connectonion[whatsapp]'" in problems[0]


def test_check_says_how_to_link_a_device_when_none_is(sdk, monkeypatch):
    monkeypatch.setattr(WhatsApp, "protocol_snapshot", lambda self: None)

    problems = WhatsApp().check()

    assert len(problems) == 1
    assert "co whatsapp listen" in problems[0]
    assert "Linked devices" in problems[0]


def test_check_passes_once_a_device_is_linked(sdk, tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_SESSION", str(tmp_path / "session.db"))
    (tmp_path / "session.db").write_bytes(b"linked")
    monkeypatch.setattr(WhatsApp, "protocol_snapshot", lambda self: time.time())

    assert WhatsApp().check() == []


def test_an_old_protocol_snapshot_is_reported_before_it_fails_namelessly(sdk, tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_SESSION", str(tmp_path / "session.db"))
    (tmp_path / "session.db").write_bytes(b"linked")
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

def drain_once(bot, inbox):
    """One pass of the listener's sender thread, then stop."""
    stop = threading.Event()
    thread = threading.Thread(target=bot._drain_outbox, args=(inbox, stop), daemon=True)
    thread.start()
    return stop, thread


def test_send_hands_the_text_to_the_listener_and_returns_its_id(sdk):
    bot = WhatsApp()
    bot._client = SimpleNamespace(send_message=lambda to, text: SimpleNamespace(ID="3EB0SENT"))
    stop, thread = drain_once(bot, Inbox("whatsapp"))
    try:
        assert bot.send(f"1203630000000@{GROUP_SERVER}", "on it") == "3EB0SENT"
    finally:
        stop.set()
        thread.join(timeout=5)


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
    # send() stages to .tmp and renames, so the listener's *.json glob only
    # ever sees a complete payload.
    bot = WhatsApp()
    sent = []
    bot._client = SimpleNamespace(send_message=lambda to, text: (sent.append(text), SimpleNamespace(ID="X"))[1])
    inbox = Inbox("whatsapp")
    spool = inbox.root / "outbox"
    spool.mkdir(parents=True, exist_ok=True)
    (spool / "1-partial.tmp").write_text('{"chat": "x@s.whats')

    stop, thread = drain_once(bot, inbox)
    try:
        bot.send(f"{PEER}@{USER_SERVER}", "complete")
    finally:
        stop.set()
        thread.join(timeout=5)

    assert sent == ["complete"]
