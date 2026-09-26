"""A watch produces one durable observation and one turn in its own session."""

import importlib
import json
import sqlite3
import threading
import time

import pytest

from connectonion import Agent
from connectonion.cli.co_ai.tools.background import _reset_for_testing, _tasks, run_background
from connectonion.cli.co_ai.tools.watch import watch_task
from connectonion.core.llm import LLMResponse
from connectonion.core.mode import FULL_ACCESS, set_mode
from connectonion.network.host.session import Session, SessionStorage, session_to_chat_items
from connectonion.network.host.session.mode import HostPermissionPolicy
from connectonion.network.host.session.watches import (
    WatchStore,
    check_due_watches,
)
from connectonion.network.host.watch import process_one

watch_module = importlib.import_module("connectonion.network.host.session.watches")
http_module = importlib.import_module("connectonion.network.host.http_router")


OWNER = {"address": "owner", "level": "admin"}


def _store(tmp_path):
    return WatchStore(tmp_path)


def _events(store, status="pending"):
    with store._connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM events WHERE status=? ORDER BY observed_at", (status,),
        )]


def _session(storage, status="done"):
    storage.save(Session(
        session_id="session-1", status=status, prompt="start a task",
        result="started", created=time.time(), expires=time.time() + 3600,
        session={"session_id": "session-1", "requester": OWNER,
                 "messages": [], "trace": [], "turn": 0},
    ))


def test_task_finished_before_watch_is_registered(tmp_path):
    store = _store(tmp_path)
    store.register_task("bg_123", "session-1", "owner")
    store.finish_task("bg_123", "failed", "exit 2")
    watch = store.watch_task("session-1", "owner", "bg_123")

    events = _events(store)
    assert len(events) == 1
    assert events[0]["name"] == f"session-watch:{watch['watch_id']}"
    assert json.loads(events[0]["payload"])["status"] == "failed"
    assert store.list_watches("session-1", "owner")[0]["status"] == "completed"


def test_recurring_watch_skips_unchanged_and_recovers_cursor(tmp_path, monkeypatch):
    store = _store(tmp_path)
    watch = store.watch_every("session-1", "owner", minutes=30,
                              probe="gmail_search", query="subject:CRCD",
                              initial_ids=["old"])
    now = time.time()
    with store._connect() as db:
        db.execute("UPDATE watches SET next_at=? WHERE watch_id=?",
                   (now - 1, watch["watch_id"]))
    monkeypatch.setattr(watch_module, "gmail_probe", lambda query: [{"id": "old"}])
    check_due_watches(store)
    assert _events(store) == []

    restarted = _store(tmp_path)
    with restarted._connect() as db:
        db.execute("UPDATE watches SET next_at=? WHERE watch_id=?",
                   (now - 1, watch["watch_id"]))
    monkeypatch.setattr(watch_module, "gmail_probe",
                        lambda query: [{"id": "new"}, {"id": "old"}])
    check_due_watches(restarted)
    events = _events(restarted)
    assert len(events) == 1
    assert [item["id"] for item in json.loads(events[0]["payload"])["items"]] == ["new"]


def test_watch_observation_wakes_same_session_once(tmp_path, monkeypatch):
    store = _store(tmp_path)
    storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
    storage.watch_store = store
    _session(storage)
    store.register_task("bg_123", "session-1", "owner")
    store.watch_task("session-1", "owner", "bg_123")
    store.finish_task("bg_123", "completed", "done")

    calls = []

    def fake_input_handler(factory, storage, prompt, ttl, *, session, requester,
                           mode_policy, is_admin, watch_event):
        calls.append((session["session_id"], watch_event))
        record = storage.get(session["session_id"])
        record.session["messages"].append({"role": "user", "content": prompt,
                                            "watch_event": watch_event})
        record.session["trace"].append({"watch_event_id": watch_event["event_id"]})
        storage.save(record)

    monkeypatch.setattr(http_module, "input_handler", fake_input_handler)
    process_one(tmp_path, lambda: None, storage, 3600, HostPermissionPolicy())
    process_one(tmp_path, lambda: None, storage, 3600, HostPermissionPolicy())

    assert len(calls) == 1
    assert calls[0][0] == "session-1"
    assert len([item for item in session_to_chat_items(storage.get("session-1").session)
                if item.get("source") == "watch_event"]) == 1


def test_busy_session_keeps_observation_pending(tmp_path, monkeypatch):
    store = _store(tmp_path)
    storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
    _session(storage, "running")
    store.register_task("bg_123", "session-1", "owner")
    store.watch_task("session-1", "owner", "bg_123")
    store.finish_task("bg_123", "completed", "done")
    monkeypatch.setattr(http_module, "input_handler",
                        lambda *args, **kwargs: pytest.fail("busy session woke"))

    process_one(tmp_path, lambda: None, storage, 3600, HostPermissionPolicy())
    with store._connect() as db:
        assert db.execute("SELECT status FROM events").fetchone()[0] == "pending"


def test_restart_reports_unknown_and_one_shot_refuses_watch(tmp_path):
    store = _store(tmp_path)
    store.register_task("bg_123", "session-1", "owner")
    store.watch_task("session-1", "owner", "bg_123")
    with store._connect() as db:
        db.execute("UPDATE tasks SET host_pid=? WHERE task_id=?", (99999999, "bg_123"))
    _store(tmp_path).recover_tasks()
    event = _events(store)[0]
    assert json.loads(event["payload"])["status"] == "unknown"
    with pytest.raises(RuntimeError, match="Host session"):
        watch_task("bg_123", agent=type("AgentStub", (), {"current_session": {}})())


def test_real_host_claim_runs_watch_turn_in_read_only_mode(tmp_path):
    store = _store(tmp_path)
    storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
    storage.watch_store = store
    _session(storage)
    seen = []

    class AgentStub:
        def input(self, prompt, *, session, images, files, _watch_event):
            seen.append((session["mode"], session["session_id"], _watch_event))
            self.current_session = session
            self.current_session["messages"].append({
                "role": "user", "content": prompt, "watch_event": _watch_event,
            })
            self.current_session["trace"].append({
                "watch_event_id": _watch_event["event_id"],
            })
            return "The task finished."

    event = {"event_id": "event-1", "watch_id": "watch-1",
             "kind": "task_completed", "summary": "Task finished"}
    from connectonion.network.host.http_router import input_handler
    result = input_handler(
        AgentStub, storage, "task finished", 3600,
        session=storage.get("session-1").session, requester=OWNER,
        mode_policy=HostPermissionPolicy(), is_admin=True, watch_event=event,
    )

    assert seen[0] == ("read-only", "session-1", event)
    assert result["session"]["mode"] == "auto"
    assert result["chat_items"][0]["source"] == "watch_event"
    assert storage.get("session-1").result == "The task finished."


def test_managed_background_process_writes_completion_receipt(tmp_path):
    store = _store(tmp_path)
    agent = type("AgentStub", (), {
        "_watch_store": store,
        "current_session": {"session_id": "session-1", "requester": OWNER},
    })()
    try:
        started = run_background("python -c 'print(42)'", agent=agent)
        task_id = started.split()[1]
        store.watch_task("session-1", "owner", task_id)
        _tasks[task_id].reader.join(timeout=5)

        assert not _tasks[task_id].reader.is_alive()
        payload = json.loads(_events(store)[0]["payload"])
        assert payload["task_id"] == task_id
        assert payload["status"] == "completed"
        assert payload["result"] == "42"
    finally:
        _reset_for_testing()


def test_event_queue_upgrade_adds_session_target_columns(tmp_path):
    with sqlite3.connect(tmp_path / "watch-state.sqlite3") as db:
        db.execute("CREATE TABLE events (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                   "source TEXT NOT NULL, payload TEXT NOT NULL, observed_at TEXT NOT NULL, "
                   "status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, "
                   "session_id TEXT, error TEXT, completed_at TEXT)")
    store = _store(tmp_path)
    store.register_task("bg_123", "session-1", "owner")
    store.watch_task("session-1", "owner", "bg_123")
    store.finish_task("bg_123", "completed", "done")

    assert _events(store)[0]["target_session_id"] == "session-1"
    assert _events(store)[0]["owner_address"] == "owner"


def test_real_agent_wakes_original_session_with_provenance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = _store(tmp_path)
    storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
    storage.watch_store = store
    _session(storage)
    store.register_task("bg_123", "session-1", "owner")
    store.watch_task("session-1", "owner", "bg_123")
    store.finish_task("bg_123", "failed", "exit 2")
    calls = []

    class FakeLLM:
        model = "fake"

        def complete(self, messages, tools=None, **kwargs):
            calls.append(messages)
            return LLMResponse(content="The task failed.", tool_calls=[], raw_response=None)

    def factory():
        return Agent("watch-test", llm=FakeLLM(), log=False, quiet=True)
    result = process_one(tmp_path, factory, storage, 3600, HostPermissionPolicy())
    record = storage.get("session-1")

    assert result["status"] == "done"
    assert len(calls) == 1
    assert record.result == "The task failed."
    assert record.session["mode"] == "auto"
    assert record.session["requester"] == OWNER
    assert any(entry.get("watch_event_id") == result["id"]
               for entry in record.session["trace"])
    assert [item["source"] for item in session_to_chat_items(record.session)
            if item.get("source") == "watch_event"] == ["watch_event"]
    assert process_one(tmp_path, factory, storage, 3600, HostPermissionPolicy()) is None


def test_failed_watch_turn_cannot_retain_full_access(tmp_path):
    storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
    _session(storage)
    record = storage.get("session-1")
    set_mode(record.session, FULL_ACCESS, turns_left=2)
    storage.save(record)

    class FailingAgent:
        def input(self, prompt, *, session, images, files, _watch_event):
            assert session["mode"] == "read-only"
            raise RuntimeError("model unavailable")

    from connectonion.network.host.http_router import input_handler
    with pytest.raises(RuntimeError, match="model unavailable"):
        input_handler(
            FailingAgent, storage, "task finished", 3600,
            session=storage.get("session-1").session, requester=OWNER,
            mode_policy=HostPermissionPolicy(full_access_turns=2), is_admin=True,
            watch_event={"event_id": "event-1", "watch_id": "watch-1"},
        )

    record = storage.get("session-1")
    assert record.status == "failed"
    assert record.session["mode"] == "read-only"
    assert "turns_left" not in record.session


def test_two_watches_for_one_session_serialize_agent_turns(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = _store(tmp_path)
    storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
    storage.watch_store = store
    _session(storage)
    for task_id in ("bg_first", "bg_second"):
        store.register_task(task_id, "session-1", "owner")
        store.watch_task("session-1", "owner", task_id)
        store.finish_task(task_id, "completed", task_id)

    started, release = threading.Event(), threading.Event()
    calls = []

    class SlowLLM:
        model = "fake"

        def complete(self, messages, tools=None, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                started.set()
                assert release.wait(3)
            return LLMResponse(content="handled", tool_calls=[], raw_response=None)

    def factory():
        return Agent("watch-test", llm=SlowLLM(), log=False, quiet=True)

    worker = threading.Thread(
        target=process_one,
        args=(tmp_path, factory, storage, 3600, HostPermissionPolicy()),
    )
    worker.start()
    assert started.wait(3)
    assert process_one(tmp_path, factory, storage, 3600, HostPermissionPolicy()) is None
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM events WHERE status='pending' AND attempts=0").fetchone()[0] == 1
    release.set()
    worker.join(3)
    assert not worker.is_alive()
    assert process_one(tmp_path, factory, storage, 3600, HostPermissionPolicy())["status"] == "done"
    assert len(calls) == 2


def test_internal_watch_reminders_render_as_observations():
    event = {"event_id": "event-2", "watch_id": "watch-1",
             "kind": "task_completed", "summary": "Background task completed"}
    items = session_to_chat_items({
        "messages": [{"role": "user", "content": "untrusted event",
                      "internal": True, "watch_events": [event]}],
        "trace": [{"type": "user_input", "watch_event_ids": ["event-2"]}],
    })
    assert len(items) == 1
    assert items[0]["source"] == "watch_event"
    assert items[0]["id"] == "event-2"


def test_owner_cancel_removes_pending_wake(tmp_path):
    store = _store(tmp_path)
    store.register_task("bg_123", "session-1", "owner")
    watch = store.watch_task("session-1", "owner", "bg_123")
    store.finish_task("bg_123", "completed", "done")

    with pytest.raises(ValueError, match="not found"):
        store.cancel("session-1", "another-owner", watch["watch_id"])
    assert len(_events(store)) == 1
    assert store.cancel("session-1", "owner", watch["watch_id"])["status"] == "cancelled"
    assert _events(store) == []
    assert process_one(tmp_path, lambda: None, SessionStorage(str(tmp_path / "sessions.jsonl")), 3600) is None


def test_probe_failure_pauses_watch_and_queues_error(tmp_path, monkeypatch):
    store = _store(tmp_path)
    watch = store.watch_every("session-1", "owner", minutes=30,
                              probe="gmail_search", query="subject:CRCD",
                              initial_ids=[])
    with store._connect() as db:
        db.execute("UPDATE watches SET next_at=0 WHERE watch_id=?",
                   (watch["watch_id"],))

    def unavailable(query):
        raise RuntimeError("mail unavailable")

    monkeypatch.setattr(watch_module, "gmail_probe", unavailable)
    check_due_watches(store)

    assert store.list_watches("session-1", "owner")[0]["status"] == "paused"
    assert json.loads(_events(store)[0]["payload"])["kind"] == "watch_error"
