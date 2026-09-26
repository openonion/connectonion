"""File/timer events become durable user turns in a continuing Host session."""

import asyncio
import json
import threading
import time

from connectonion import Agent
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.network.host.session import SessionStorage
from connectonion.network.host.session.ui import session_to_chat_items
from connectonion.network.host.watch import (
    create_watch_lifespan,
    emit_event,
    load_watches,
    observe,
    process_one,
    retry_event,
    watch_status,
)


def _co_dir(tmp_path, yaml_text):
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    (co_dir / "host.yaml").write_text(yaml_text, encoding="utf-8")
    return co_dir


def _agent_factory(asked):
    class FakeLLM:
        model = "fake"

        def complete(self, messages, tools=None, **kwargs):
            asked.append([m["content"] for m in messages if m["role"] == "user"])
            return LLMResponse(content="handled", tool_calls=[], raw_response=None)

    return lambda: Agent("watch-test", llm=FakeLLM(), log=False, quiet=True)


def test_file_event_is_a_user_message_in_the_same_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    co_dir = _co_dir(tmp_path, "watch:\n  - name: notes\n    source: file\n    path: notes.md\n")
    storage = SessionStorage(co_dir / "session_results.jsonl")
    asked = []
    make_agent = _agent_factory(asked)
    watches = load_watches(co_dir)
    observe(co_dir, watches)
    assert process_one(co_dir, make_agent, storage, 3600) is None
    file = tmp_path / "notes.md"
    file.write_text("one")
    observe(co_dir, watches)
    first = process_one(co_dir, make_agent, storage, 3600)
    assert first["status"] == "done"
    assert asked and json.loads(asked[0][0].split("\n", 1)[1])["data"]["event"] == "created"
    assert process_one(co_dir, make_agent, storage, 3600) is None

    file.write_text("two, changed")
    observe(co_dir, watches)
    second = process_one(co_dir, make_agent, storage, 3600)
    assert second["status"] == "done"
    assert asked[-1][0] == asked[0][0]
    assert len(asked[-1]) == 2
    assert watch_status(co_dir)[0]["last_event"]["session_id"] == storage.list()[0].session_id


def test_event_arriving_during_iteration_becomes_internal_reminder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    co_dir = _co_dir(tmp_path, "watch: []\n")
    storage = SessionStorage(co_dir / "session_results.jsonl")
    calls = []

    class LLM:
        model = "fake"

        def complete(self, messages, tools=None, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                emit_event(co_dir, "notes", "file", {"event": "changed", "revision": 2},
                           "event-2")
            return LLMResponse(content=f"answer-{len(calls)}", tool_calls=[], raw_response=None)

    emit_event(co_dir, "notes", "file", {"event": "changed", "revision": 1}, "event-1")
    result = process_one(co_dir, lambda: Agent("watch-test", llm=LLM(), log=False, quiet=True),
                         storage, 3600)

    assert result["status"] == "done"
    assert len(calls) == 2, "a late event must get another iteration before the turn ends"
    reminders = [message for message in calls[1]
                 if message.get("internal") and "<system-reminder>" in message["content"]]
    assert len(reminders) == 1
    assert '"id": "event-2"' in reminders[0]["content"]
    assert '"revision": 2' in reminders[0]["content"]
    record = storage.list()[0]
    assert record.status == "done"
    assert not any(item["type"] == "user" and "event-2" in item.get("content", "")
                   for item in session_to_chat_items(record.session))
    assert watch_status(co_dir)[0]["pending"] == 0
    assert watch_status(co_dir)[0]["last_event"]["status"] == "done"
    assert process_one(co_dir, lambda: None, storage, 3600) is None

    # The session commit can outlive its queue acknowledgement. Recovery reads
    # the persisted reminder and must not run the event a second time.
    import sqlite3

    with sqlite3.connect(co_dir / "watch-state.sqlite3") as db:
        db.execute("UPDATE events SET status='running' WHERE id='event-2'")
    assert process_one(co_dir, lambda: None, storage, 3600) is None
    assert watch_status(co_dir)[0]["last_event"]["status"] == "done"


def test_event_during_tool_batch_is_seen_before_next_iteration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    co_dir = _co_dir(tmp_path, "watch: []\n")
    storage = SessionStorage(co_dir / "session_results.jsonl")
    calls = []

    def change_file():
        emit_event(co_dir, "notes", "file", {"revision": 2}, "event-2")
        return "changed"

    class LLM:
        model = "fake"

        def complete(self, messages, tools=None, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                return LLMResponse(content=None, tool_calls=[
                    ToolCall(name="change_file", arguments={}, id="call-1")
                ], raw_response=None)
            return LLMResponse(content="handled", tool_calls=[], raw_response=None)

    emit_event(co_dir, "notes", "file", {"revision": 1}, "event-1")
    assert process_one(
        co_dir,
        lambda: Agent("watch-test", tools=[change_file], llm=LLM(), log=False, quiet=True),
        storage, 3600,
    )["status"] == "done"
    assert len(calls) == 2
    second = calls[1]
    tool_index = next(i for i, message in enumerate(second) if message["role"] == "tool")
    reminder_index = next(i for i, message in enumerate(second)
                          if message.get("internal") and '"id": "event-2"' in message["content"])
    assert tool_index < reminder_index


def test_live_reminders_are_bounded_and_remaining_events_stay_queued(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    co_dir = _co_dir(tmp_path, "watch: []\n")
    storage = SessionStorage(co_dir / "session_results.jsonl")
    calls = []

    class LLM:
        model = "fake"

        def complete(self, messages, tools=None, **kwargs):
            calls.append(messages)
            if len(calls) <= 5:
                emit_event(co_dir, "notes", "file", {"revision": len(calls) + 1},
                           f"event-{len(calls) + 1}")
            return LLMResponse(content="handled", tool_calls=[], raw_response=None)

    emit_event(co_dir, "notes", "file", {"revision": 1}, "event-1")

    def make_agent():
        return Agent("watch-test", llm=LLM(), log=False, quiet=True)

    assert process_one(co_dir, make_agent, storage, 3600)["status"] == "done"
    assert len(calls) == 5
    assert watch_status(co_dir)[0]["pending"] == 1
    assert process_one(co_dir, make_agent, storage, 3600)["status"] == "done"
    assert len(calls) == 6
    assert watch_status(co_dir)[0]["pending"] == 0


def test_timer_coalesces_gap_and_push_id_deduplicates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    co_dir = _co_dir(tmp_path, "watch:\n  - name: pulse\n    source: timer\n    every: 10s\n")
    storage = SessionStorage(co_dir / "session_results.jsonl")
    asked = []
    observe(co_dir, load_watches(co_dir), now=100)
    observe(co_dir, load_watches(co_dir), now=145)
    assert emit_event(co_dir, "callback", "webhook", {"value": 1}, "callback-1")
    assert not emit_event(co_dir, "callback", "webhook", {"value": 1}, "callback-1")
    assert process_one(co_dir, _agent_factory(asked), storage, 3600)["status"] == "done"
    assert json.loads(asked[0][0].split("\n", 1)[1])["data"]["missed_intervals"] == 3
    assert process_one(co_dir, _agent_factory(asked), storage, 3600)["status"] == "done"
    assert process_one(co_dir, _agent_factory(asked), storage, 3600) is None
    assert {row["name"] for row in watch_status(co_dir)} == {"pulse", "callback"}


def test_interrupted_delivery_reconciles_from_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    co_dir = _co_dir(tmp_path, "watch:\n  - name: notes\n    source: file\n    path: notes.md\n")
    storage = SessionStorage(co_dir / "session_results.jsonl")
    asked = []
    assert emit_event(co_dir, "notes", "file", {"event": "changed"}, "event-1")
    make_agent = _agent_factory(asked)
    assert process_one(co_dir, make_agent, storage, 3600)["status"] == "done"
    import sqlite3

    with sqlite3.connect(co_dir / "watch-state.sqlite3") as db:
        db.execute("UPDATE events SET status='running' WHERE id='event-1'")
    assert process_one(co_dir, make_agent, storage, 3600) is None
    assert len(asked) == 1


def test_interrupted_claim_releases_busy_session_and_retries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    co_dir = _co_dir(tmp_path, "watch:\n  - name: notes\n    source: file\n    path: notes.md\n")
    from connectonion.network.host.session.storage import Session
    from connectonion.network.host.watch import _session_id, event_prompt

    storage = SessionStorage(co_dir / "session_results.jsonl")
    asked = []
    emit_event(co_dir, "notes", "file", {"event": "changed"}, "event-1")
    import sqlite3

    with sqlite3.connect(co_dir / "watch-state.sqlite3") as db:
        db.row_factory = sqlite3.Row
        event = db.execute("SELECT * FROM events WHERE id='event-1'").fetchone()
        db.execute("UPDATE events SET status='running' WHERE id='event-1'")
    session_id = _session_id(co_dir, "notes")
    storage.save(Session(session_id=session_id, status="running", prompt=event_prompt(event),
                         session={"messages": [], "trace": [], "turn": 0}, expires=time.time() + 3600))
    assert process_one(co_dir, _agent_factory(asked), storage, 3600)["status"] == "done"
    assert len(asked) == 1


def test_lifespan_does_not_wait_for_slow_agent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    co_dir = _co_dir(tmp_path, "watch:\n  - name: notes\n    source: file\n    path: notes.md\n")
    storage = SessionStorage(co_dir / "session_results.jsonl")
    started = []

    def slow_agent():
        started.append(True)
        time.sleep(0.2)
        return _agent_factory([])()

    emit_event(co_dir, "notes", "file", {"event": "changed"}, "event-1")

    async def run():
        startup, shutdown = create_watch_lifespan(co_dir, slow_agent, storage, 3600)
        await asyncio.wait_for(startup(), 0.1)
        await asyncio.sleep(0.05)
        await asyncio.wait_for(shutdown(), 0.1)

    asyncio.run(run())
    assert started


def test_two_host_workers_cannot_deliver_the_same_event(tmp_path, monkeypatch):
    co_dir = _co_dir(tmp_path, "watch:\n  - name: pulse\n    source: timer\n    every: 10s\n")
    emit_event(co_dir, "pulse", "timer", {"event": "fired"}, "event-1")
    started, finish = threading.Event(), threading.Event()
    calls = []

    def input_handler(*args, **kwargs):
        calls.append(args[2])
        started.set()
        finish.wait(2)
        return {"status": "done"}

    from connectonion.network.host import http_router

    monkeypatch.setattr(http_router, "input_handler", input_handler)
    class EmptyStorage:
        def get(self, _):
            return None

    storage = EmptyStorage()
    worker = threading.Thread(target=process_one, args=(co_dir, lambda: None, storage, 3600))
    worker.start()
    assert started.wait(2)
    assert process_one(co_dir, lambda: None, storage, 3600) is None
    finish.set()
    worker.join(2)
    assert not worker.is_alive()
    assert len(calls) == 1


def test_slow_watch_does_not_block_another_watch(tmp_path, monkeypatch):
    co_dir = _co_dir(tmp_path, "watch: []\n")
    emit_event(co_dir, "slow", "webhook", {"value": 1}, "slow-1")
    emit_event(co_dir, "fast", "webhook", {"value": 2}, "fast-1")
    from connectonion.network.host import http_router

    slow_started, release_slow = threading.Event(), threading.Event()
    calls = []

    def input_handler(*args, **kwargs):
        calls.append(args[2])
        if '"watch": "slow"' in args[2]:
            slow_started.set()
            assert release_slow.wait(2)
        return {"status": "done"}

    monkeypatch.setattr(http_router, "input_handler", input_handler)

    class EmptyStorage:
        def get(self, _):
            return None

    storage = EmptyStorage()
    slow = threading.Thread(target=process_one, args=(co_dir, lambda: None, storage, 3600))
    slow.start()
    assert slow_started.wait(2)
    assert process_one(co_dir, lambda: None, storage, 3600)["id"] == "fast-1"
    release_slow.set()
    slow.join(2)
    assert not slow.is_alive()
    assert len(calls) == 2


def test_failed_event_is_visible_and_can_be_retried(tmp_path, monkeypatch):
    co_dir = _co_dir(tmp_path, "watch:\n  - name: pulse\n    source: timer\n    every: 10s\n")
    emit_event(co_dir, "pulse", "timer", {"event": "fired"}, "event-1")
    from connectonion.network.host import http_router

    def fail(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(http_router, "input_handler", fail)
    class EmptyStorage:
        def get(self, _):
            return None

    assert [process_one(co_dir, lambda: None, EmptyStorage(), 3600)["status"] for _ in range(3)] == [
        "pending", "pending", "failed"]
    assert watch_status(co_dir)[0]["failed"] == 1
    assert watch_status(co_dir)[0]["failed_events"][0]["id"] == "event-1"
    assert retry_event(co_dir, "event-1")
    assert watch_status(co_dir)[0]["pending"] == 1
    assert not retry_event(co_dir, "event-1")


def test_busy_session_defers_event_without_spending_retries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    co_dir = _co_dir(tmp_path, "watch:\n  - name: notes\n    source: file\n    path: notes.md\n")
    import sqlite3

    from connectonion.network.host.session.storage import Session
    from connectonion.network.host.watch import _session_id

    storage = SessionStorage(co_dir / "session_results.jsonl")
    session_id = _session_id(co_dir, "notes")
    storage.save(Session(session_id=session_id, status="running", prompt="earlier event",
                         session={"messages": [], "trace": [], "turn": 0},
                         expires=time.time() + 3600))
    emit_event(co_dir, "notes", "file", {"event": "changed"}, "event-2")
    emit_event(co_dir, "other", "webhook", {"value": 1}, "other-1")
    asked = []
    make_agent = _agent_factory(asked)
    assert process_one(co_dir, make_agent, storage, 3600)["id"] == "other-1"
    assert process_one(co_dir, make_agent, storage, 3600) is None
    with sqlite3.connect(co_dir / "watch-state.sqlite3") as db:
        assert db.execute("SELECT status, attempts FROM events WHERE id='event-2'").fetchone() == (
            "pending", 0)
    storage.save(Session(session_id=session_id, status="done", prompt="earlier event",
                         session={"messages": [], "trace": [], "turn": 0},
                         expires=time.time() + 3600))
    assert process_one(co_dir, make_agent, storage, 3600)["id"] == "event-2"


def test_session_that_becomes_busy_during_claim_is_deferred(tmp_path, monkeypatch):
    co_dir = _co_dir(tmp_path, "watch:\n  - name: notes\n    source: file\n    path: notes.md\n")
    emit_event(co_dir, "notes", "file", {"event": "changed"}, "event-1")
    from connectonion.network.host import http_router
    from connectonion.network.host.session.mode import ModeTransactionError

    def busy(*args, **kwargs):
        raise ModeTransactionError(-32000, "Session is busy", {"retryable": True})

    monkeypatch.setattr(http_router, "input_handler", busy)
    storage = SessionStorage(co_dir / "session_results.jsonl")
    assert process_one(co_dir, lambda: None, storage, 3600) is None
    assert watch_status(co_dir)[0]["pending"] == 1
    assert watch_status(co_dir)[0]["last_event"]["attempts"] == 0


def test_saved_turn_is_not_repeated_when_delivery_ack_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    co_dir = _co_dir(tmp_path, "watch:\n  - name: pulse\n    source: timer\n    every: 10s\n")
    storage = SessionStorage(co_dir / "session_results.jsonl")
    asked = []
    emit_event(co_dir, "pulse", "timer", {"event": "fired"}, "event-1")
    from connectonion.network.host import http_router

    real_handler = http_router.input_handler

    def saved_then_failed(*args, **kwargs):
        real_handler(*args, **kwargs)
        raise RuntimeError("ack lost")

    monkeypatch.setattr(http_router, "input_handler", saved_then_failed)
    make_agent = _agent_factory(asked)
    assert process_one(co_dir, make_agent, storage, 3600)["status"] == "pending"
    assert process_one(co_dir, make_agent, storage, 3600)["status"] == "done"
    assert len(asked) == 1
