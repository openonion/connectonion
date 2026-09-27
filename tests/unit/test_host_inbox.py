"""
LLM-Note: Tests for connectonion.network.host.inbox — the Host consuming the
inbox directory. Fake input_handler and fake provider: the point under test is
that a chat message becomes an ordinary Host turn, recorded like every other.
"""

import asyncio
import importlib
import threading
import time

import pytest

from connectonion.inbox.settings import Channel
from connectonion.inbox.store import Inbox, Message
from connectonion.network.host import inbox as host_inbox


class FakeProvider:
    def __init__(self):
        self.sent = []

    def send(self, chat, text, *, reply_to=None, fresh=False):
        self.sent.append({"chat": chat, "text": text, "reply_to": reply_to})
        return "provider-id-1"


@pytest.fixture
def rig(tmp_path, monkeypatch):
    # The real Inbox, pointed at a temp root the way an operator would point it.
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    box = Inbox("feishu")
    provider = FakeProvider()
    turns = []

    def fake_input_handler(create_agent, storage, prompt, result_ttl, session=None, **kwargs):
        turns.append({"prompt": prompt, "session": session})
        return {"result": "answered", "status": "done"}

    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: 1)
    # connectonion.network rebinds the name `host` to the host() function, so
    # the submodule is reached through importlib, not attribute traversal.
    http_router = importlib.import_module("connectonion.network.host.http_router")
    monkeypatch.setattr(http_router, "input_handler", fake_input_handler)
    return box, provider, turns


def put(box, message_id="m1", chat="c1", text="hello", mentioned=True, thread=None):
    box.deliver(Message(id=message_id, chat=chat, thread=thread, sender="u1",
                        text=text, at="2026-09-11T00:00:00Z", mentioned=mentioned))


def lifespan(tmp_path, provider, monkeypatch, channels=(Channel("feishu"),), console=None):
    import connectonion.inbox as inbox_package
    monkeypatch.setattr(inbox_package, "provider", lambda name: provider)
    return host_inbox.create_inbox_lifespan(
        tmp_path / ".co", lambda: None, object(), 60, console=console,
        channels=None if channels is None else list(channels))


def run_until(startup, shutdown, *, until, timeout=10):
    asyncio.run(startup())
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not until():
        time.sleep(0.02)
    asyncio.run(shutdown())


class TestTheHostAnswers:
    def test_a_message_becomes_an_ordinary_host_turn(self, tmp_path, rig, monkeypatch):
        box, provider, turns = rig
        put(box, text="what broke?")
        startup, shutdown = lifespan(tmp_path, provider, monkeypatch)
        run_until(startup, shutdown, until=lambda: provider.sent)
        assert turns[0]["prompt"] == "what broke?"
        assert provider.sent == [{"chat": "c1", "text": "answered", "reply_to": "m1"}]
        assert "m1" in box.completed.read_text()

    def test_the_turn_carries_the_channel_and_the_sender(self, tmp_path, rig, monkeypatch):
        # Gate 6 of #1462: a Feishu turn is findable in session_results.jsonl
        # as a Feishu turn, with whoever sent it.
        box, provider, turns = rig
        put(box)
        startup, shutdown = lifespan(tmp_path, provider, monkeypatch)
        run_until(startup, shutdown, until=lambda: turns)
        session = turns[0]["session"]
        assert session["via"] == "feishu"
        assert session["requester"] == {"address": "feishu:u1", "level": "open"}

    def test_one_conversation_is_one_session_across_restarts(self, tmp_path, rig, monkeypatch):
        box, provider, turns = rig
        put(box, "m1", chat="c1")
        startup, shutdown = lifespan(tmp_path, provider, monkeypatch)
        run_until(startup, shutdown, until=lambda: turns)
        put(box, "m2", chat="c1")
        startup, shutdown = lifespan(tmp_path, provider, monkeypatch)
        run_until(startup, shutdown, until=lambda: len(turns) == 2)
        # A stable id, not a fresh uuid: a reconnect must not start the
        # conversation over.
        assert turns[0]["session"]["session_id"] == turns[1]["session"]["session_id"]

    def test_two_chats_are_two_sessions(self, tmp_path, rig, monkeypatch):
        box, provider, turns = rig
        put(box, "m1", chat="c1")
        put(box, "m2", chat="c2")
        startup, shutdown = lifespan(tmp_path, provider, monkeypatch)
        run_until(startup, shutdown, until=lambda: len(turns) == 2)
        assert turns[0]["session"]["session_id"] != turns[1]["session"]["session_id"]

    def test_a_message_that_did_not_address_the_bot_never_reaches_a_turn(self, tmp_path, rig, monkeypatch):
        box, provider, turns = rig
        put(box, mentioned=False)
        startup, shutdown = lifespan(tmp_path, provider, monkeypatch)
        run_until(startup, shutdown, until=lambda: box.completed.exists())
        assert turns == []
        assert provider.sent == []


class TestTheHostKeepsServing:
    def test_a_channel_that_cannot_start_does_not_stop_the_host(self, tmp_path, rig, monkeypatch):
        box, provider, turns = rig
        monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: None)
        startup, shutdown = lifespan(tmp_path, provider, monkeypatch)
        asyncio.run(startup())           # must return, not raise
        asyncio.run(shutdown())

    def test_a_broken_host_yaml_is_reported_and_the_host_still_serves(self, tmp_path, rig, monkeypatch):
        box, provider, turns = rig
        co = tmp_path / ".co"
        co.mkdir()
        (co / "host.yaml").write_text("listen:\n  feishu: [unclosed\n")
        said = []

        class Console:
            def print(self, text):
                said.append(text)

        startup, shutdown = lifespan(tmp_path, provider, monkeypatch,
                                     channels=None, console=Console())
        asyncio.run(startup())
        asyncio.run(shutdown())
        assert any("host.yaml" in line for line in said)


class TestEachChatItsOwnConversation:
    """The property #1751 found broken in `co ai`, held here with the real
    input_handler, a real Agent and real session storage. The Host makes a
    fresh Agent per turn and keys the stored session by chat, so it was not
    broken; this keeps it that way."""

    def test_a_new_chat_never_sees_another_chats_messages(self, tmp_path, monkeypatch):
        import connectonion.inbox as inbox_package
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.network.host.session import SessionStorage

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
        monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: 1)
        asked = []

        class FakeLLM:
            model = "fake"

            def complete(self, messages, tools=None, **kwargs):
                asked.append([m["content"] for m in messages if m["role"] == "user"])
                return LLMResponse(content="ok", tool_calls=[], raw_response=None)

        llm = FakeLLM()
        box, provider = Inbox("feishu"), FakeProvider()
        monkeypatch.setattr(inbox_package, "provider", lambda name: provider)
        startup, shutdown = host_inbox.create_inbox_lifespan(
            tmp_path / ".co", lambda: Agent("host-test", llm=llm, log=False, quiet=True),
            SessionStorage(tmp_path / ".co" / "session_results.jsonl"), 60,
            channels=[Channel("feishu")])
        put(box, "m1", chat="clientA", text="SECRET: our margin is 42%")
        put(box, "m2", chat="clientB", text="hi, what do you know?")
        put(box, "m3", chat="clientA", text="and the price?")
        run_until(startup, shutdown, until=lambda: len(provider.sent) == 3)
        assert ["hi, what do you know?"] in asked
        assert ["SECRET: our margin is 42%", "and the price?"] in asked


class Listener:
    """Stands in for the child ensure_listener starts and exited_listener reports."""

    def __init__(self, monkeypatch):
        self.exited = None
        self.started = 0
        listener = self

        def ensure_listener(inbox, settle=0.0):
            listener.started += 1
            listener.exited = None
            return 1

        monkeypatch.setattr(Inbox, "ensure_listener", ensure_listener)
        monkeypatch.setattr(Inbox, "exited_listener", lambda inbox: listener.exited)


def wait(until, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not until():
        time.sleep(0.02)
    return until()


class TestTheHostWatchesTheListener:
    def test_a_listener_that_exits_3_is_said_with_its_reason_and_the_channel_stops(self, tmp_path, rig, monkeypatch):
        box, provider, turns = rig
        listener = Listener(monkeypatch)
        said = []

        class Console:
            def print(self, text):
                said.append(text)

        startup, shutdown = lifespan(tmp_path, provider, monkeypatch, console=Console())
        asyncio.run(startup())
        try:
            assert wait(lambda: listener.started == 1)
            thread = next(t for t in threading.enumerate() if t.name == "inbox-feishu")
            box.log("Feishu refused the app: app_id is invalid. Next: co feishu check")
            listener.exited = 3
            thread.join(timeout=10)
            assert not thread.is_alive(), "the Host went on polling for a listener that exited 3"
            put(box)
            time.sleep(0.3)
            assert turns == [], "a channel whose listener exited 3 was still being answered"
            assert any("exited 3" in line and "app_id is invalid" in line for line in said), said
            assert listener.started == 1, "a listener that exited 3 was restarted"
        finally:
            asyncio.run(shutdown())

    def test_a_listener_that_dies_another_way_is_restarted(self, tmp_path, rig, monkeypatch):
        box, provider, turns = rig
        listener = Listener(monkeypatch)
        startup, shutdown = lifespan(tmp_path, provider, monkeypatch)
        asyncio.run(startup())
        try:
            assert wait(lambda: listener.started == 1)
            listener.exited = 1
            assert wait(lambda: listener.started == 2), "a listener that died was not restarted"
            put(box)
            assert wait(lambda: provider.sent), "the Host stopped answering after restarting its listener"
        finally:
            asyncio.run(shutdown())
