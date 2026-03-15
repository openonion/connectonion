"""Tests for co_ai miscellaneous tools (ask_user, load_guide, plan_mode, task, todo_list)."""
"""
LLM-Note: Tests for co ai tools misc

What it tests:
- Co Ai Tools Misc functionality

Components under test:
- Module: co_ai_tools_misc
"""


from types import SimpleNamespace

from connectonion.cli.co_ai.tools.ask_user import ask_user
from connectonion.cli.co_ai.tools.load_guide import load_guide
from connectonion.cli.co_ai.tools.plan_mode import (
    enter_plan_mode,
    exit_plan_and_implement,
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

    # Create fake agent with io that returns plan_review response
    io = FakeIO([{"type": "plan_review", "approved": True, "message": "Looks good, implement it."}])
    agent = SimpleNamespace(
        current_session={'mode': 'safe'},
        io=io,
    )

    msg = enter_plan_mode(agent)
    assert "Entered plan mode" in msg
    assert is_plan_mode_active(agent) is True
    assert 'plan_path' in agent.current_session

    plan_text = "# Plan\n\nDo things."
    write_msg = write_plan(plan_text, agent=agent)
    assert "Plan updated" in write_msg

    exit_msg = exit_plan_and_implement(agent)
    assert "Looks good" in exit_msg
    # After exit, mode is restored to previous mode
    assert agent.current_session['mode'] == 'safe'
    # Session state cleaned up
    assert 'plan_path' not in agent.current_session
    assert 'previous_mode' not in agent.current_session
    # Verify plan_review was sent via io
    plan_review_sent = [m for m in io.sent if m.get('type') == 'plan_review']
    assert len(plan_review_sent) == 1
    assert "Do things" in plan_review_sent[0]['plan_content']


def test_task_delegation(monkeypatch):
    """Test task delegation uses SDK subagents."""
    # Mock the SDK task function
    monkeypatch.setattr(task_mod, "sdk_task", lambda agent, prompt, agent_type: f"handled: {prompt}")

    result = task("hello", agent_type="explore")
    assert "handled: hello" in result


def test_todo_list_basic():
    todos = TodoList()

    assert todos.add("a", "doing a") == "Added: a"
    assert "already" in todos.add("a", "doing a")

    assert "Started" in todos.start("a")
    assert "Completed" in todos.complete("a")
    assert "Removed" in todos.remove("a")

    assert todos.list() == "No todos"
    assert todos.progress == 1.0
