"""Tests for co_ai miscellaneous tools (ask_user, load_guide, plan_mode, task, todo_list)."""

from types import SimpleNamespace

from connectonion.cli.co_ai.tools.ask_user import ask_user
from connectonion.cli.co_ai.tools.load_guide import load_guide
from connectonion.cli.co_ai.tools.plan_mode import (
    enter_plan_mode,
    exit_plan_mode,
    write_plan,
    is_plan_mode_active,
)
import importlib

task_mod = importlib.import_module("connectonion.cli.co_ai.tools.task")
task = task_mod.task
from connectonion.cli.co_ai.tools.todo_list import TodoList


class FakeIO:
    def __init__(self, responses=None):
        self.sent = []
        self._responses = list(responses or [])

    def send(self, event):
        self.sent.append(event)

    def receive(self):
        if self._responses:
            return self._responses.pop(0)
        return {}


def test_ask_user_round_trip():
    io = FakeIO([{"answer": "yes"}])
    agent = SimpleNamespace(io=io)

    result = ask_user(agent, "Continue?", options=["yes", "no"])
    assert result == "yes"
    assert io.sent[0]["type"] == "ask_user"


def test_load_guide_existing_and_missing():
    content = load_guide("concepts/agent")
    assert "Agent" in content

    missing = load_guide("nope/missing")
    assert "not found" in missing


def test_plan_mode_flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    msg = enter_plan_mode()
    assert "Entered plan mode" in msg
    assert is_plan_mode_active() is True

    plan_text = "# Plan\n\nDo things."
    write_msg = write_plan(plan_text)
    assert "Plan updated" in write_msg

    exit_msg = exit_plan_mode()
    assert "Exited plan mode" in exit_msg
    assert "Do things" in exit_msg
    assert is_plan_mode_active() is False


def test_task_delegation(monkeypatch):
    class FakeSubagent:
        def input(self, prompt):
            return f"handled: {prompt}"

    monkeypatch.setattr(task_mod, "get_subagent", lambda t: FakeSubagent())

    result = task("hello", agent_type="explore")
    assert "handled: hello" in result

    bad = task("oops", agent_type="unknown")
    assert "Unknown agent type" in bad


def test_todo_list_basic():
    todos = TodoList()

    assert todos.add("a", "doing a") == "Added: a"
    assert "already" in todos.add("a", "doing a")

    assert "Started" in todos.start("a")
    assert "Completed" in todos.complete("a")
    assert "Removed" in todos.remove("a")

    assert todos.list() == "No todos"
    assert todos.progress == 1.0
