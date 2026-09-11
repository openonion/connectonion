"""
LLM-Note: Tests for connectonion.cli.co_ai.listen — the consumer that turns an
inbox message into an agent turn and its answer into a reply. Fake agent, fake
provider: no model call and no network.
"""

import threading
import time

import pytest

from connectonion.cli.co_ai import listen as co_ai_listen
from connectonion.inbox.settings import Channel
from connectonion.inbox.store import Inbox, Message


class FakeAgent:
    """Records what it was asked and what session it was given."""

    def __init__(self, answer="answered"):
        self.answer = answer
        self.calls = []
        self.current_session = None

    def input(self, prompt, session=None, **kwargs):
        self.calls.append({"prompt": prompt, "session": session})
        turn = (session or {}).get("turn", 0) + 1
        self.current_session = {"turn": turn, "messages": [prompt], "requester": (session or {}).get("requester")}
        return self.answer(prompt) if callable(self.answer) else self.answer


class FakeProvider:
    def __init__(self):
        self.sent = []

    def send(self, chat, text, *, reply_to=None, fresh=False):
        self.sent.append({"chat": chat, "text": text, "reply_to": reply_to})
        return f"sent-{len(self.sent)}"


@pytest.fixture
def rig(tmp_path, monkeypatch):
    inbox = Inbox("feishu", home=tmp_path / "feishu")
    provider = FakeProvider()
    agent = FakeAgent()
    monkeypatch.setattr(co_ai_listen, "_inbox_for", lambda name: inbox)
    monkeypatch.setattr(co_ai_listen, "_provider_for", lambda name: provider)
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)
    return inbox, provider, agent


def put(inbox, message_id="m1", chat="c1", text="hello", mentioned=True, thread=None):
    inbox.deliver(Message(id=message_id, chat=chat, thread=thread, sender="u1",
                          text=text, at="2026-09-11T00:00:00Z", mentioned=mentioned))


def run(agent, channels, *, until, timeout=10, **options):
    stop = threading.Event()
    thread = threading.Thread(
        target=co_ai_listen.listen,
        args=(channels, lambda: agent),
        kwargs={"should_stop": stop, "idle_seconds": 0.2, **options}, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not until():
        time.sleep(0.02)
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive(), "listen did not stop when asked"


class TestAnswering:
    def test_a_message_becomes_a_turn_and_the_answer_becomes_a_reply(self, rig):
        inbox, provider, agent = rig
        put(inbox, text="what is broken?")
        run(agent, [Channel("feishu")], until=lambda: provider.sent)
        assert agent.calls[0]["prompt"] == "what is broken?"
        assert provider.sent == [{"chat": "c1", "text": "answered", "reply_to": "m1"}]
        assert "m1" in inbox.completed.read_text()
        assert "m1" in inbox.sent.read_text()

    def test_an_empty_answer_is_silence_not_an_empty_message(self, rig):
        inbox, provider, agent = rig
        agent.answer = "   "
        put(inbox)
        run(agent, [Channel("feishu")], until=lambda: inbox.completed.exists())
        assert provider.sent == [], "an agent with nothing to say must not post whitespace"
        assert "m1" in inbox.completed.read_text()

    def test_a_failing_turn_leaves_the_message_for_the_sweep(self, rig):
        inbox, provider, agent = rig

        def explode(prompt):
            raise RuntimeError("the model was down")

        agent.answer = explode
        put(inbox)
        run(agent, [Channel("feishu")], until=lambda: inbox.logfile.exists() and "not finished" in inbox.logfile.read_text())
        assert provider.sent == []
        assert not inbox.completed.exists(), "a failed turn must not look answered"
        assert [p.name.split("-", 1)[1] for p in inbox.cur.iterdir()] == ["m1"]


class TestTheGate:
    def test_a_group_message_that_did_not_address_the_bot_is_finished_unanswered(self, rig):
        inbox, provider, agent = rig
        put(inbox, mentioned=False)
        run(agent, [Channel("feishu")], until=lambda: inbox.completed.exists())
        assert agent.calls == [], "other people's conversation reached the model"
        assert provider.sent == []
        # Finished, not left: it will never become ours, so the sweep must not
        # offer it again every hour for the rest of the week.
        assert "m1" in inbox.completed.read_text()

    def test_a_chat_outside_the_configured_list_is_ignored(self, rig):
        inbox, provider, agent = rig
        put(inbox, chat="oc_other")
        run(agent, [Channel("feishu", chats=("oc_allowed",))],
            until=lambda: inbox.completed.exists())
        assert agent.calls == []


class TestMemory:
    def test_one_conversation_keeps_its_session_across_messages(self, rig):
        inbox, provider, agent = rig
        put(inbox, "m1", chat="c1", text="first")
        put(inbox, "m2", chat="c1", text="second")
        run(agent, [Channel("feishu")], until=lambda: len(agent.calls) == 2)
        assert agent.calls[0]["session"] is None, "a new conversation starts fresh"
        assert agent.calls[1]["session"] is not None, "a follow-up lost the conversation"
        assert agent.calls[1]["session"]["turn"] == 1

    def test_two_conversations_do_not_share_a_session(self, rig):
        inbox, provider, agent = rig
        put(inbox, "m1", chat="c1")
        put(inbox, "m2", chat="c2")
        run(agent, [Channel("feishu")], until=lambda: len(agent.calls) == 2)
        assert all(call["session"] is None for call in agent.calls), \
            "one chat's history was handed to another chat"

    def test_a_thread_is_its_own_conversation(self, rig):
        inbox, provider, agent = rig
        put(inbox, "m1", chat="c1", thread="t1")
        put(inbox, "m2", chat="c1", thread="t2")
        run(agent, [Channel("feishu")], until=lambda: len(agent.calls) == 2)
        assert all(call["session"] is None for call in agent.calls)


class TestRequester:
    def test_the_sender_is_recorded_even_though_nothing_checks_it_yet(self, rig):
        # 1.8.5 answers anyone who can address the bot. The requester is still
        # written down, so the allowlist in 1.9 has its data without a migration.
        inbox, provider, agent = rig
        put(inbox)
        run(agent, [Channel("feishu")], until=lambda: agent.calls)
        assert agent.current_session["requester"] == {"address": "feishu:u1", "level": "open"}
