"""Tests for co_ai miscellaneous tools (ask_user, load_guide, task, todo_list)."""
"""
LLM-Note: Tests for co ai tools misc

What it tests:
- Co Ai Tools Misc functionality

Components under test:
- Module: co_ai_tools_misc
"""


from types import SimpleNamespace

from connectonion.cli.co_ai.tools import ask_user
from connectonion.cli.co_ai.tools.load_guide import load_guide
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
    assert io.sent[0] == {
        "type": "ask_user",
        "question": "Continue?",
        "options": ["yes", "no"],
        "multi_select": False,
    }


def test_ask_user_with_fields():
    io = FakeIO([{"answer": '{"username":"me","password":"secret"}'}])
    agent = SimpleNamespace(io=io)
    fields = [
        {"name": "username", "label": "Username", "type": "text"},
        {"name": "password", "label": "Password", "type": "password"},
    ]

    result = ask_user(agent, "Enter your login.", options=[], fields=fields)
    assert result == '{"username":"me","password":"secret"}'
    assert io.sent[0] == {
        "type": "ask_user",
        "question": "Enter your login.",
        "options": [],
        "multi_select": False,
        "fields": fields,
    }


def test_load_guide_existing_and_missing():
    content = load_guide("concepts/agent")
    assert "Agent" in content

    missing = load_guide("nope/missing")
    assert "not found" in missing


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
