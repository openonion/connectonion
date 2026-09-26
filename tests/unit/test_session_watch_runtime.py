"""A session watch runs without the network Host and preserves the original turn."""

import json
import os
import shlex
import subprocess
import sys
import time

import pytest

from connectonion import Agent
from connectonion.cli.co_ai.session_watch import SessionWatchRuntime, SessionWatchStore
from connectonion.cli.co_ai.tools.background import _reset_for_testing, _tasks, run_background
from connectonion.core.llm import LLMResponse
from connectonion.network.host.session import Session, SessionStorage, session_to_chat_items
from connectonion.network.host.session.mode import HostPermissionPolicy
from connectonion.network.host.session.turn import input_handler
from connectonion.useful_plugins import watch_events

OWNER = {"address": "owner", "level": "admin"}


def _session(storage, *, status="done", mode="auto"):
    storage.save(Session(
        session_id="s1", status=status, prompt="start", result="started",
        created=time.time(), expires=time.time() + 3600,
        session={"session_id": "s1", "requester": OWNER, "messages": [],
                 "trace": [], "turn": 1, "mode": mode,
                 **({"turns_left": 1} if mode == "full-access" else {})},
    ))


def _events(store):
    with store.db() as db:
        return [dict(row) for row in db.execute("SELECT * FROM events ORDER BY rowid")]


def test_task_wakes_original_session_without_starting_host(tmp_path):
    store = SessionWatchStore(tmp_path)
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    _session(storage)
    store.register_task("bg_1", "s1", "owner")
    store.watch_task("s1", "owner", "bg_1")
    store.finish_task("bg_1", "completed", "done")
    calls = []

    def run(event):
        calls.append(event["session_id"])

        def complete(record):
            session = record.session.copy()
            session["trace"] = [*session["trace"],
                                {"watch_event_id": event["id"], "turn": 2},
                                {"type": "turn_result", "turn": 2,
                                 "reason": "natural"}]
            session["messages"] = [*session["messages"],
                                   {"role": "assistant", "content": "Finished"}]
            return record.model_copy(update={"status": "done", "session": session})

        storage.atomic_update(event["session_id"], complete)

    runtime = SessionWatchRuntime(store, storage, run)
    assert runtime.deliver_one() is True
    assert runtime.deliver_one() is False
    assert calls == ["s1"]
    assert _events(store)[0]["status"] == "done"


def test_finished_before_registration_and_unknown_after_restart(tmp_path):
    store = SessionWatchStore(tmp_path)
    store.register_task("bg_done", "s1", "owner")
    store.finish_task("bg_done", "failed", "exit 2")
    store.watch_task("s1", "owner", "bg_done")
    assert json.loads(_events(store)[0]["payload"])["status"] == "failed"

    store.register_task("bg_lost", "s1", "owner")
    store.watch_task("s1", "owner", "bg_lost")
    with store.db() as db:
        db.execute("UPDATE tasks SET pid=99999999 WHERE id='bg_lost'")
    store.recover_tasks()
    assert json.loads(_events(store)[1]["payload"])["status"] == "unknown"


def test_recurring_probe_diffs_and_rejects_stale_lease(tmp_path):
    store = SessionWatchStore(tmp_path)
    watch = store.watch_every("s1", "owner", minutes=30, probe="gmail_search",
                              query="subject:CRCD", initial_ids=["old"])
    with store.db() as db:
        db.execute("UPDATE watches SET next_at=0 WHERE id=?", (watch["watch_id"],))
    old_claim = store.due(now=1000)[0]
    assert store.checked(old_claim, [{"id": "old"}], now=1000) is True
    assert _events(store) == []

    with store.db() as db:
        db.execute("UPDATE watches SET next_at=0 WHERE id=?", (watch["watch_id"],))
    stale_claim = store.due(now=2000)[0]
    new_claim = store.due(now=2301)[0]
    assert store.checked(stale_claim, [{"id": "lost"}], now=2301) is False
    assert store.checked(new_claim, [{"id": "old"}, {"id": "new"}], now=2301) is True
    assert [item["id"] for item in json.loads(_events(store)[0]["payload"])["items"]] == ["new"]
    reopened = SessionWatchStore(tmp_path)
    with reopened.db() as db:
        assert json.loads(db.execute("SELECT cursor FROM watches").fetchone()[0]) == ["old", "new"]


def test_busy_turn_defers_delivery_and_full_access_defers_iteration(tmp_path):
    store = SessionWatchStore(tmp_path)
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    _session(storage, status="running", mode="full-access")
    store.register_task("bg_1", "s1", "owner")
    store.watch_task("s1", "owner", "bg_1")
    store.finish_task("bg_1", "completed", "done")
    assert store.claim_iteration({"session_id": "s1", "requester": OWNER,
                                  "turn": 2, "mode": "full-access", "turns_left": 1}) == []
    runtime = SessionWatchRuntime(store, storage, lambda event: None)
    assert runtime.deliver_one() is False
    assert _events(store)[0]["status"] == "pending"


def test_two_workers_do_not_reclaim_idle_event_before_session_claim(tmp_path):
    store = SessionWatchStore(tmp_path)
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    _session(storage)
    store.register_task("bg_1", "s1", "owner")
    store.watch_task("s1", "owner", "bg_1")
    store.finish_task("bg_1", "completed", "done")

    claimed = store.claim_idle(storage)
    another = SessionWatchStore(tmp_path)
    another.reconcile(storage)
    assert another.claim_idle(storage) is None
    assert _events(store)[0]["status"] == "running"

    with store.db() as db:
        db.execute("UPDATE events SET claimed_at=? WHERE id=?",
                   (time.time() - 31, claimed["id"]))
    another.reconcile(storage)
    assert _events(store)[0]["status"] == "pending"


def test_idle_watch_turn_is_read_only_and_has_separate_observation(tmp_path):
    store = SessionWatchStore(tmp_path)
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    _session(storage, mode="full-access")
    store.register_task("bg_1", "s1", "owner")
    store.watch_task("s1", "owner", "bg_1")
    store.finish_task("bg_1", "completed", "done")
    seen = []

    class AgentStub:
        def input(self, prompt, *, session, images, files, _watch_event):
            seen.append(session["mode"])
            self.current_session = session
            self.current_session["messages"].append({
                "role": "user", "content": prompt, "watch_event": _watch_event,
            })
            self.current_session["trace"].append({
                "type": "user_input", "watch_event_id": _watch_event["event_id"],
                "turn": session["turn"],
            })
            self.current_session["trace"].append({
                "type": "turn_result", "turn": session["turn"], "reason": "natural",
            })
            self.current_session["messages"].append({
                "role": "assistant", "content": "The task completed.",
            })
            return "The task completed."

    def run(event):
        record = storage.get(event["session_id"])
        input_handler(AgentStub, storage, event["content"], 3600,
                      session=record.session, requester=OWNER,
                      mode_policy=HostPermissionPolicy(full_access_turns=3),
                      is_admin=True, watch_event=event["metadata"])

    runtime = SessionWatchRuntime(store, storage, run)
    assert runtime.deliver_one() is True
    record = storage.get("s1")
    items = session_to_chat_items(record.session)
    assert seen == ["read-only"]
    assert record.session["mode"] == "auto"
    assert any(item.get("name") == "Watch observation" for item in items)
    assert any(item.get("content") == "The task completed." for item in items)
    assert _events(store)[0]["status"] == "done"


def test_iteration_sees_task_that_finishes_during_final_model_call(tmp_path):
    store = SessionWatchStore(tmp_path)
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    _session(storage)
    store.register_task("bg_1", "s1", "owner")
    store.watch_task("s1", "owner", "bg_1")
    calls = []
    holder = {}

    class LLM:
        model = "fake"

        def complete(self, messages, tools=None, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                store.finish_task("bg_1", "completed", "done")
            return LLMResponse(content="Checked", tool_calls=[], raw_response=None)

    plugin = watch_events(lambda: store.claim_iteration(holder["agent"].current_session))
    agent = Agent("watch-test", llm=LLM(), plugins=[plugin], log=False, quiet=True)
    holder["agent"] = agent
    agent.input("Wait for task", session=storage.get("s1").session)

    assert len(calls) == 2
    assert any(message.get("internal") and "task_completed" in message["content"]
               for message in calls[1])
    record = storage.get("s1")
    record.status = "done"
    record.session = agent.current_session
    storage.save(record)
    store.reconcile(storage)
    assert _events(store)[0]["status"] == "done"


def test_late_event_gets_one_more_iteration_at_limit(tmp_path):
    store = SessionWatchStore(tmp_path)
    store.register_task("bg_1", "s1", "owner")
    store.watch_task("s1", "owner", "bg_1")
    holder = {}
    calls = []

    class LLM:
        model = "fake"

        def complete(self, messages, tools=None, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                store.finish_task("bg_1", "completed", "done")
            return LLMResponse(content="First answer", tool_calls=[], raw_response=None)

    agent = Agent("watch-test", llm=LLM(), max_iterations=1,
                  plugins=[watch_events(lambda: store.claim_iteration(
                      holder["agent"].current_session))], log=False, quiet=True)
    holder["agent"] = agent
    agent.input("Wait", session={"session_id": "s1", "requester": OWNER,
                                 "messages": [], "trace": [], "turn": 0})

    assert len(calls) == 2
    assert _events(store)[0]["status"] == "running"
    assert any(entry.get("watch_event_ids") for entry in agent.current_session["trace"])


def test_managed_background_process_emits_task_receipt(tmp_path):
    store = SessionWatchStore(tmp_path)
    agent = type("AgentStub", (), {
        "_watch_store": store,
        "current_session": {"session_id": "s1", "requester": OWNER},
    })()
    try:
        args = [sys.executable, "-c", "print(42)"]
        command = subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)
        started = run_background(command, agent=agent)
        task_id = started.split()[1]
        store.watch_task("s1", "owner", task_id)
        _tasks[task_id].reader.join(timeout=5)
        assert not _tasks[task_id].reader.is_alive()
        assert json.loads(_events(store)[0]["payload"])["result"] == "42"
    finally:
        _reset_for_testing()


def test_watch_owner_is_bound_to_task_and_event(tmp_path):
    store = SessionWatchStore(tmp_path)
    store.register_task("bg_1", "s1", "owner")
    with pytest.raises(ValueError, match="Task not found"):
        store.watch_task("s1", "other", "bg_1")
    store.watch_task("s1", "owner", "bg_1")
    store.finish_task("bg_1", "completed", "done")
    assert store.claim_iteration({"session_id": "s1", "requester": {
        "address": "other", "level": "admin"}, "turn": 2}) == []
    assert _events(store)[0]["status"] == "pending"


def test_interrupted_turn_does_not_acknowledge_unseen_observation(tmp_path):
    store = SessionWatchStore(tmp_path)
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    _session(storage)
    store.register_task("bg_1", "s1", "owner")
    store.watch_task("s1", "owner", "bg_1")
    store.finish_task("bg_1", "completed", "done")
    event = store.claim_idle(storage)
    record = storage.get("s1")
    record.session["trace"] = [
        {"watch_event_id": event["id"], "turn": 2},
        {"type": "turn_result", "turn": 2, "reason": "interrupted"},
    ]
    storage.save(record)

    store.reconcile(storage)
    assert _events(store)[0]["status"] == "pending"
