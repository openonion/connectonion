"""
LLM-Note: Tests for connectonion.cli.co_ai.listen — the consumer that turns an
inbox message into an agent turn and its answer into a reply. A real Agent over
a fake LLM, and a fake provider: no model call and no network.

A real Agent, not a stand-in: the fake this file used to have started a fresh
conversation whenever it was given no session, which is exactly what Agent does
not do. Agent.input(session=None) carries on with the conversation it already
holds, so every chat after the first was answered from the first chat's history,
and the tests stayed green (#1751).
"""

import threading
import time

import pytest

from connectonion import Agent
from connectonion.cli.co_ai import listen as co_ai_listen
from connectonion.core.llm import LLMResponse
from connectonion.inbox.settings import Channel
from connectonion.inbox.store import Inbox, Message


class FakeLLM:
    """Answers every call, and remembers what each one was sent."""

    model = "fake"

    def __init__(self, answer="answered", delay=0.0):
        self.answer = answer
        self.delay = delay
        self.calls = []
        self.lock = threading.Lock()

    def complete(self, messages, tools=None, **kwargs):
        with self.lock:
            self.calls.append([dict(m) for m in messages])
        time.sleep(self.delay)
        last = [m["content"] for m in messages if m["role"] == "user"][-1]
        content = self.answer(last) if callable(self.answer) else self.answer
        return LLMResponse(content=content, tool_calls=[], raw_response=None)

    def users(self, call: int) -> list:
        return [m["content"] for m in self.calls[call] if m["role"] == "user"]

    def asked(self, text: str) -> list:
        """The user messages the model was sent on the call that answered `text`."""
        for messages in self.calls:
            users = [m["content"] for m in messages if m["role"] == "user"]
            if users and users[-1] == text:
                return users
        raise AssertionError(f"the model was never asked {text!r}")


class FakeProvider:
    def __init__(self):
        self.sent = []

    def send(self, chat, text, *, reply_to=None, fresh=False):
        self.sent.append({"chat": chat, "text": text, "reply_to": reply_to})
        return f"sent-{len(self.sent)}"


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inbox = Inbox("feishu", home=tmp_path / "feishu")
    provider = FakeProvider()
    llm = FakeLLM()
    agent = Agent("listen-test", llm=llm, system_prompt="You answer chats.", log=False, quiet=True)
    monkeypatch.setattr(co_ai_listen, "_inbox_for", lambda name: inbox)
    monkeypatch.setattr(co_ai_listen, "_provider_for", lambda name: provider)
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: 1)
    return inbox, provider, agent, llm


def put(inbox, message_id="m1", chat="c1", text="hello", mentioned=True, thread=None, sender="u1"):
    inbox.deliver(Message(id=message_id, chat=chat, thread=thread, sender=sender,
                          text=text, at="2026-09-11T00:00:00Z", mentioned=mentioned))


def run(agent, channels, *, until, timeout=10, said=None, **options):
    stop = threading.Event()
    kwargs = {"should_stop": stop, "idle_seconds": 0.2, **options}
    if said is not None:
        kwargs["say"] = said.append
    thread = threading.Thread(target=co_ai_listen.listen, args=(channels, lambda: agent),
                              kwargs=kwargs, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not until():
        time.sleep(0.02)
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive(), "listen did not stop when asked"


class TestAnswering:
    def test_a_message_becomes_a_turn_and_the_answer_becomes_a_reply(self, rig):
        inbox, provider, agent, llm = rig
        put(inbox, text="what is broken?")
        run(agent, [Channel("feishu")], until=lambda: provider.sent)
        assert llm.users(0) == ["what is broken?"]
        assert provider.sent == [{"chat": "c1", "text": "answered", "reply_to": "m1"}]
        assert "m1" in inbox.completed.read_text()
        assert "m1" in inbox.sent.read_text()

    def test_an_empty_answer_is_silence_not_an_empty_message(self, rig, monkeypatch):
        # A real Agent raises on an empty answer from the model; one built by
        # a plugin or a subclass can still return whitespace.
        inbox, provider, agent, llm = rig
        def whitespace(*args, **kwargs):
            agent.current_session = {"messages": []}
            return "   "

        monkeypatch.setattr(agent, "input", whitespace)
        put(inbox)
        run(agent, [Channel("feishu")], until=lambda: inbox.completed.exists())
        assert provider.sent == [], "an agent with nothing to say must not post whitespace"
        assert "m1" in inbox.completed.read_text()

    def test_a_failing_turn_leaves_the_message_for_the_sweep(self, rig, monkeypatch):
        inbox, provider, agent, llm = rig

        def explode(*args, **kwargs):
            raise RuntimeError("the model was down")

        monkeypatch.setattr(agent, "input", explode)
        put(inbox)
        run(agent, [Channel("feishu")], until=lambda: inbox.logfile.exists() and "not finished" in inbox.logfile.read_text())
        assert provider.sent == []
        assert not inbox.completed.exists(), "a failed turn must not look answered"
        assert [p.name.split("-", 1)[1] for p in inbox.cur.iterdir()] == ["m1"]


class TestTheGate:
    def test_a_group_message_that_did_not_address_the_bot_is_finished_unanswered(self, rig):
        inbox, provider, agent, llm = rig
        put(inbox, mentioned=False)
        run(agent, [Channel("feishu")], until=lambda: inbox.completed.exists())
        assert llm.calls == [], "other people's conversation reached the model"
        assert provider.sent == []
        # Finished, not left: it will never become ours, so the sweep must not
        # offer it again every hour for the rest of the week.
        assert "m1" in inbox.completed.read_text()

    def test_a_chat_outside_the_configured_list_is_ignored(self, rig):
        inbox, provider, agent, llm = rig
        put(inbox, chat="oc_other")
        run(agent, [Channel("feishu", chats=("oc_allowed",))],
            until=lambda: inbox.completed.exists())
        assert llm.calls == []


class TestMemory:
    def test_one_conversation_keeps_its_history_across_messages(self, rig):
        inbox, provider, agent, llm = rig
        put(inbox, "m1", chat="c1", text="first")
        put(inbox, "m2", chat="c1", text="second")
        run(agent, [Channel("feishu")], until=lambda: len(provider.sent) == 2)
        assert llm.asked("second") == ["first", "second"], "a follow-up lost the conversation"

    def test_a_new_chat_never_sees_another_chats_messages(self, rig):
        # The #1751 reproduction: client A says something private, then
        # client B asks what the bot knows.
        inbox, provider, agent, llm = rig
        put(inbox, "m1", chat="clientA", text="SECRET: our margin is 42%")
        run(agent, [Channel("feishu")], until=lambda: len(provider.sent) == 1)
        put(inbox, "m2", chat="clientB", text="hi, what do you know?")
        run(agent, [Channel("feishu")], until=lambda: len(provider.sent) == 2)
        assert llm.asked("hi, what do you know?") == ["hi, what do you know?"], \
            "client A's message was sent to the model while answering client B"

    def test_a_new_chat_still_gets_the_system_prompt(self, rig):
        inbox, provider, agent, llm = rig
        put(inbox, "m1", chat="c1")
        put(inbox, "m2", chat="c2")
        run(agent, [Channel("feishu")], until=lambda: len(provider.sent) == 2)
        for call in llm.calls:
            assert call[0] == {"role": "system", "content": "You answer chats."}

    def test_going_back_to_a_chat_continues_that_chat_only(self, rig):
        inbox, provider, agent, llm = rig
        said = []
        stop, thread = listening(agent, [Channel("feishu")], said)
        for count, (message_id, chat, text) in enumerate(
                [("m1", "c1", "a1"), ("m2", "c2", "b1"), ("m3", "c1", "a2"), ("m4", "c2", "b2")], 1):
            put(inbox, message_id, chat=chat, text=text)
            assert wait(lambda: len(provider.sent) == count)
        stop.set()
        thread.join(timeout=5)
        assert llm.asked("a2") == ["a1", "a2"]
        assert llm.asked("b2") == ["b1", "b2"]

    def test_two_chats_talking_at_once_keep_two_histories(self, rig):
        # Two lanes, so both chats' turns are in flight together, and a slow
        # model so each one is still running when the other arrives.
        inbox, provider, agent, llm = rig
        llm.delay = 0.05
        for n in range(3):
            put(inbox, f"a{n}", chat="c1", text=f"a{n}", sender="alice")
            put(inbox, f"b{n}", chat="c2", text=f"b{n}", sender="bob")
        run(agent, [Channel("feishu")], until=lambda: len(provider.sent) == 6, workers=2)
        assert len(provider.sent) == 6
        for n in range(3):
            assert llm.asked(f"a{n}") == [f"a{i}" for i in range(n + 1)]
            assert llm.asked(f"b{n}") == [f"b{i}" for i in range(n + 1)]

    def test_a_thread_is_its_own_conversation(self, rig):
        inbox, provider, agent, llm = rig
        put(inbox, "m1", chat="c1", thread="t1", text="in t1")
        run(agent, [Channel("feishu")], until=lambda: len(provider.sent) == 1)
        put(inbox, "m2", chat="c1", thread="t2", text="in t2")
        run(agent, [Channel("feishu")], until=lambda: len(provider.sent) == 2)
        assert llm.asked("in t2") == ["in t2"]


class TestRequester:
    def test_the_sender_is_recorded_even_though_nothing_checks_it_yet(self, rig):
        # 1.8.5 answers anyone who can address the bot. The requester is still
        # written down, so the allowlist in 1.9 has its data without a migration.
        inbox, provider, agent, llm = rig
        put(inbox)
        run(agent, [Channel("feishu")], until=lambda: provider.sent)
        assert agent.current_session["requester"] == {"address": "feishu:u1", "level": "open"}

    def test_each_chat_records_its_own_sender(self, rig):
        inbox, provider, agent, llm = rig
        put(inbox, "m1", chat="c1", sender="alice")
        run(agent, [Channel("feishu")], until=lambda: len(provider.sent) == 1)
        first = agent.current_session
        put(inbox, "m2", chat="c2", sender="bob")
        run(agent, [Channel("feishu")], until=lambda: len(provider.sent) == 2)
        assert agent.current_session is not first
        assert first["requester"]["address"] == "feishu:alice"
        assert agent.current_session["requester"]["address"] == "feishu:bob"


class Listener:
    """What ensure_listener and exited_listener would say about a child."""

    def __init__(self, monkeypatch, starts=(1,), exits=None):
        self.starts = list(starts)   # what each ensure_listener returns, in turn
        self.exited = exits          # what exited_listener returns now
        self.started = 0
        listener = self

        def ensure_listener(inbox, settle=0.0):
            listener.started += 1
            pid = listener.starts.pop(0) if listener.starts else 1
            if pid is None:
                inbox.listener_exit_code = listener.exited
            else:
                listener.exited = None
            return pid

        monkeypatch.setattr(Inbox, "ensure_listener", ensure_listener)
        monkeypatch.setattr(Inbox, "exited_listener", lambda inbox: listener.exited)


def listening(agent, channels, said, **options):
    stop = threading.Event()
    thread = threading.Thread(target=co_ai_listen.listen, args=(channels, lambda: agent),
                              kwargs={"should_stop": stop, "idle_seconds": 0.2,
                                      "say": said.append, **options}, daemon=True)
    thread.start()
    return stop, thread


def wait(until, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not until():
        time.sleep(0.02)
    return until()


class TestTheListener:
    def test_a_listener_that_never_started_with_3_is_said_and_the_channel_is_not_served(self, rig, monkeypatch):
        inbox, provider, agent, llm = rig
        Listener(monkeypatch, starts=[None], exits=3)
        inbox.log("Telegram refused the token. Next: copy it again from @BotFather")
        put(inbox)
        said = []
        stop, thread = listening(agent, [Channel("feishu")], said)
        # It returns on its own: there is nothing left it can answer.
        assert wait(lambda: not thread.is_alive()), "co ai went on polling for a listener that exited 3"
        stop.set()
        assert llm.calls == []
        assert any("exited 3" in line and "@BotFather" in line for line in said), said

    def test_a_listener_that_dies_with_3_later_is_said_and_serving_stops(self, rig, monkeypatch):
        inbox, provider, agent, llm = rig
        listener = Listener(monkeypatch)
        said = []
        stop, thread = listening(agent, [Channel("feishu")], said)
        assert wait(lambda: listener.started == 1)
        inbox.log("Discord closed the Gateway with 4004. Next: copy the token again")
        listener.exited = 3
        assert wait(lambda: not thread.is_alive()), "co ai kept polling after its listener exited 3"
        stop.set()
        assert any("4004" in line for line in said), said
        assert listener.started == 1, "a listener that exited 3 was restarted"

    def test_a_listener_that_dies_another_way_is_restarted_and_answering_goes_on(self, rig, monkeypatch):
        inbox, provider, agent, llm = rig
        listener = Listener(monkeypatch)
        said = []
        stop, thread = listening(agent, [Channel("feishu")], said)
        assert wait(lambda: listener.started == 1)
        listener.exited = 1
        assert wait(lambda: listener.started == 2), "a dead listener was not restarted"
        put(inbox, text="still there?")
        assert wait(lambda: provider.sent)
        stop.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert said == [], "a restart that worked is not news"
