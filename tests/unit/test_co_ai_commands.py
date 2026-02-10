"""Tests for co_ai command handlers."""

import os
from types import SimpleNamespace

from connectonion.cli.co_ai.commands.init import cmd_init
from connectonion.cli.co_ai.commands.help import cmd_help
import connectonion.cli.co_ai.commands.cost as cost_mod
import connectonion.cli.co_ai.commands.compact as compact_mod
import connectonion.cli.co_ai.commands.export as export_mod
import connectonion.cli.co_ai.commands.sessions as sessions_mod
import connectonion.cli.co_ai.commands.tasks as tasks_mod
import connectonion.cli.co_ai.commands.undo as undo_mod


def test_cmd_init_creates_oo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    msg = cmd_init()
    assert msg == "Initialized"
    assert (tmp_path / ".co" / "OO.md").exists()

    msg = cmd_init()
    assert msg == "Already initialized"


def test_cmd_help_smoke():
    assert cmd_help() == "Help displayed"


def test_cmd_cost_no_session():
    cost_mod.set_agent(None)
    assert cost_mod.cmd_cost() == "No session"


def test_cmd_cost_with_agent():
    agent = SimpleNamespace(
        llm=SimpleNamespace(model="m"),
        total_cost=0.005,
        last_usage={"input_tokens": 10, "output_tokens": 5},
        context_percent=25,
        current_session={"messages": [1, 2, 3]},
    )
    cost_mod.set_agent(agent)
    msg = cost_mod.cmd_cost()
    assert msg.startswith("Cost:")


def test_cmd_compact_flow(monkeypatch):
    # Provide enough messages to compact
    messages = [{"role": "system", "content": "sys"}]
    for i in range(10):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})

    agent = SimpleNamespace(
        current_session={"messages": messages},
        context_percent=80,
    )

    compact_mod.set_agent(agent)
    monkeypatch.setattr(compact_mod, "llm_do", lambda *a, **k: "summary")

    msg = compact_mod.cmd_compact()
    assert msg.startswith("Compacted:")
    assert any("Previous Conversation Summary" in m["content"] for m in agent.current_session["messages"])


def test_cmd_compact_too_short():
    agent = SimpleNamespace(current_session={"messages": [{"role": "user", "content": "hi"}]})
    compact_mod.set_agent(agent)
    assert compact_mod.cmd_compact() == "Too short"


def test_cmd_export(monkeypatch, tmp_path):
    monkeypatch.setenv("EDITOR", "true")

    called = {}
    monkeypatch.setattr(export_mod.subprocess, "run", lambda cmd: called.setdefault("cmd", cmd))

    agent = SimpleNamespace(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
        llm=SimpleNamespace(model="m"),
    )
    export_mod.set_agent(agent)

    msg = export_mod.cmd_export()
    assert msg.startswith("Exported to")
    assert called["cmd"][0] == "true"


def test_cmd_sessions_new_resume(monkeypatch):
    class FakeManager:
        def __init__(self):
            self.messages = [{"role": "user", "content": "hi"}]
        def list_sessions(self, limit=10):
            return [{"id": "s1", "title": "t", "updated_at": "2020-01-01"}]
        def create_session(self, model=""):
            return "s2"
        def load_session(self, session_id):
            if session_id == "s1":
                return self.messages
            return None

    monkeypatch.setattr(sessions_mod, "get_session_manager", lambda: FakeManager())

    assert "Recent Sessions" in sessions_mod.cmd_sessions()

    agent = SimpleNamespace(messages=[], llm=SimpleNamespace(model="m"))
    sessions_mod.set_agent(agent)
    assert "Started new session" in sessions_mod.cmd_new()

    msg = sessions_mod.cmd_resume("s1")
    assert "Resumed session" in msg
    assert agent.messages and agent.messages[0]["content"] == "hi"


def test_cmd_tasks(monkeypatch):
    # No tasks
    tasks_mod._tasks.clear()
    assert tasks_mod.cmd_tasks() == "No background tasks"

    # With a fake task
    from connectonion.cli.co_ai.tools.background import BackgroundTask, TaskStatus
    fake = BackgroundTask(id="bg_1", command="echo hi", process=None)
    fake.status = TaskStatus.COMPLETED
    fake.start_time = 0.0
    fake.end_time = 1.0
    tasks_mod._tasks["bg_1"] = fake

    msg = tasks_mod.cmd_tasks()
    assert "Listed" in msg

    tasks_mod._tasks.clear()


def test_cmd_undo_redo(monkeypatch):
    undo_mod._undo_stack.clear()
    undo_mod._redo_stack.clear()

    monkeypatch.setattr(undo_mod, "_is_git_repo", lambda: True)
    monkeypatch.setattr(undo_mod, "_git_stash_push", lambda msg: True)
    monkeypatch.setattr(undo_mod, "_git_stash_pop", lambda: True)

    agent = SimpleNamespace(messages=[
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
    ])
    undo_mod.set_agent(agent)

    msg = undo_mod.cmd_undo()
    assert "Undone" in msg
    assert len(agent.messages) == 0

    msg = undo_mod.cmd_redo()
    assert "Restored" in msg
    assert len(agent.messages) == 2
