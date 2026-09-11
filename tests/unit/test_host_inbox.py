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

    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)
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
        monkeypatch.setattr(Inbox, "ensure_listener", lambda self: None)
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
