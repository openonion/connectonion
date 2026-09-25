"""A watch produces one durable observation and one turn in its own session."""

import json
import importlib
import time

import pytest

from connectonion.cli.co_ai.tools.watch import watch_task
from connectonion.cli.co_ai.tools.background import run_background, _tasks, _reset_for_testing
from connectonion.network.host.session import Session, SessionStorage, session_to_chat_items
from connectonion.network.host.session.mode import HostPermissionPolicy
from connectonion.network.host.session.watches import (
    WatchStore, check_due_watches, deliver_observations,
)

watch_module = importlib.import_module("connectonion.network.host.session.watches")
http_module = importlib.import_module("connectonion.network.host.http_router")


OWNER = {"address": "owner", "level": "admin"}


def _store(tmp_path):
    return WatchStore(tmp_path / "watches.sqlite3")


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

    events = store.pending()
    assert len(events) == 1
    assert events[0]["watch_id"] == watch["watch_id"]
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
    assert store.pending() == []

    restarted = _store(tmp_path)
    with restarted._connect() as db:
        db.execute("UPDATE watches SET next_at=? WHERE watch_id=?",
                   (now - 1, watch["watch_id"]))
    monkeypatch.setattr(watch_module, "gmail_probe",
                        lambda query: [{"id": "new"}, {"id": "old"}])
    check_due_watches(restarted)
    events = restarted.pending()
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
    deliver_observations(store, storage, lambda: None, None, 3600)
    deliver_observations(store, storage, lambda: None, None, 3600)

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

    deliver_observations(store, storage, lambda: None, None, 3600)
    with store._connect() as db:
        assert db.execute("SELECT status FROM observations").fetchone()[0] == "pending"


def test_restart_reports_unknown_and_one_shot_refuses_watch(tmp_path):
    store = _store(tmp_path)
    store.register_task("bg_123", "session-1", "owner")
    store.watch_task("session-1", "owner", "bg_123")
    with store._connect() as db:
        db.execute("UPDATE tasks SET host_pid=? WHERE task_id=?", (99999999, "bg_123"))
    _store(tmp_path).recover_tasks()
    event = store.pending()[0]
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
        payload = json.loads(store.pending()[0]["payload"])
        assert payload["task_id"] == task_id
        assert payload["status"] == "completed"
        assert payload["result"] == "42"
    finally:
        _reset_for_testing()
