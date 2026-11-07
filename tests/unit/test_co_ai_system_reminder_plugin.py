"""Tests for co_ai system_reminder plugin."""
"""
LLM-Note: Tests for co ai system reminder plugin

What it tests:
- Co Ai System Reminder Plugin functionality

Components under test:
- Module: co_ai_system_reminder_plugin
"""


from types import SimpleNamespace
import importlib

plugin = importlib.import_module("connectonion.cli.co_ai.plugins.system_reminder")


class FakeIO:
    def __init__(self):
        self.sent = []

    def send(self, event):
        self.sent.append(event)


class FakeConsole:
    def print(self, *args, **kwargs):
        return None


class FakeLogger:
    def __init__(self):
        self.console = FakeConsole()


def test_parse_and_find_reminders():
    text = "---\nname: test\ntriggers: []\nintent: build\n---\nBody"
    meta, body = plugin._parse_frontmatter(text)
    assert meta["name"] == "test"
    assert body == "Body"

    reminders = {
        "r": {
            "content": "Use ${tool_name} ${file_path}",
            "triggers": [{"tool": "write", "path_pattern": "*.py"}],
            "intent": "build",
        }
    }

    content = plugin._find_tool_reminder(reminders, "write", {"path": "a.py"})
    assert "write" in content
    assert "a.py" in content

    intent = plugin._find_intent_reminder(reminders, "build")
    assert "Use" in intent


def test_browser_lifecycle_reminder_triggers_on_open_browser():
    content = plugin._find_tool_reminder(plugin._REMINDERS, "open_browser", {})

    assert content is not None
    assert "previous server-side browser" in content
    assert "Leave the browser open after a successful login" in content
    assert "close_browser" not in content


def test_detect_intent_and_inject_tool(monkeypatch):
    class Intent:
        def __init__(self, ack, is_connectonion_agent_build):
            self.ack = ack
            self.is_connectonion_agent_build = is_connectonion_agent_build

    monkeypatch.setattr(plugin, "_REMINDERS", {"r": {"content": "REM", "intent": "build", "triggers": []}})
    monkeypatch.setattr(plugin, "llm_do", lambda *a, **k: Intent("understood", True))
    # detect_intent injects build context (workflow + index + examples), not reminders
    monkeypatch.setattr(plugin, "_load_build_context", lambda: "BUILD_CONTEXT")

    agent = SimpleNamespace(
        current_session={"user_prompt": "build", "messages": [], "trace": []},
        io=FakeIO(),
        logger=FakeLogger(),
        llm=object(),  # the intent step calls the agent's own LLM (#1758)
    )
    agent._record_trace = lambda entry: agent.current_session.setdefault("trace", []).append(entry)

    plugin.detect_intent(agent)

    assert agent.current_session["intent"]["is_connectonion_agent_build"] is True
    assert any("BUILD_CONTEXT" in m["content"] for m in agent.current_session["messages"])

    # tool reminder injection
    plugin._REMINDERS = {
        "r": {
            "content": "TOOL REM",
            "triggers": [{"tool": "read_file"}],
        }
    }
    agent.current_session = {
        "trace": [{"type": "tool_result", "name": "read_file", "args": {}}],
        "messages": [{"role": "tool", "content": "result"}],
    }

    plugin.inject_tool_reminder(agent)
    assert "TOOL REM" in agent.current_session["messages"][0]["content"]


def test_intent_prompt_labels_tasks_without_promising_outcomes():
    assert "3-8 words" in plugin.INTENT_PROMPT
    assert "no first person" in plugin.INTENT_PROMPT
    assert "no promise" in plugin.INTENT_PROMPT
    assert "I'll" not in plugin.INTENT_PROMPT
    assert "deploy to production" not in plugin.INTENT_PROMPT


def test_intent_schema_scopes_workflow_to_connectonion_agents():
    fields = plugin.IntentAnalysis.model_fields
    assert "is_build" not in fields
    assert "is_connectonion_agent_build" in fields
    assert '"create a login page"' in plugin.INTENT_PROMPT
    assert '"create a login page" → ack: "Login page implementation", is_connectonion_agent_build: false' in plugin.INTENT_PROMPT


def test_generic_coding_does_not_load_agent_workflow(monkeypatch):
    monkeypatch.setattr(plugin, "llm_do", lambda *a, **k: SimpleNamespace(
        ack="Authentication bug investigation", is_connectonion_agent_build=False))
    monkeypatch.setattr(plugin, "_load_build_context", lambda: (_ for _ in ()).throw(
        AssertionError("generic coding loaded the agent workflow")))
    agent = SimpleNamespace(
        current_session={"user_prompt": "fix auth", "messages": [], "trace": []},
        io=FakeIO(), logger=FakeLogger(), llm=object())
    agent._record_trace = agent.current_session["trace"].append

    plugin.detect_intent(agent)

    assert agent.current_session["intent"]["is_connectonion_agent_build"] is False
    assert agent.io.sent[-1]["is_build"] is False
    assert "is_connectonion_agent_build" not in agent.io.sent[-1]
    assert agent.current_session["trace"][-1]["is_build"] is False


import pytest


@pytest.mark.parametrize(("state", "expected"), [
    ({"mode": "auto"}, "Mode: Auto —"),
    ({"mode": "read-only"}, "Mode: Ask first —"),
    ({"mode": "full-access", "turns_left": 2}, "Mode: Full access —"),
    ({"mode": "full-access", "turns_left": 0}, "Mode: Auto —"),
    ({"mode": "unknown"}, "Mode: Auto —"),
])
def test_first_turn_includes_real_mode_even_if_intent_call_fails(monkeypatch, state, expected):
    def unavailable(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(plugin, "llm_do", unavailable)
    agent = SimpleNamespace(
        current_session={**state, "user_prompt": "inspect", "messages": [], "trace": []},
        io=FakeIO(), logger=FakeLogger(), llm=object())
    plugin.detect_intent(agent)

    reminders = agent.current_session["messages"]
    assert len(reminders) == 1
    assert reminders[0]["internal"] is True
    assert expected in reminders[0]["content"]


@pytest.mark.parametrize("intent_available", [True, False])
def test_mode_reminder_only_on_first_turn_or_mode_change(monkeypatch, intent_available):
    def analyze(*args, **kwargs):
        if not intent_available:
            raise RuntimeError("model unavailable")
        return SimpleNamespace(ack="Workspace inspection", is_connectonion_agent_build=False)

    monkeypatch.setattr(plugin, "llm_do", analyze)
    agent = SimpleNamespace(
        current_session={"user_prompt": "inspect", "messages": [], "trace": []},
        io=FakeIO(), logger=FakeLogger(), llm=object())
    agent._record_trace = agent.current_session["trace"].append

    for state, expected in [
        ({"mode": "auto"}, ["Auto"]),
        ({"mode": "auto"}, ["Auto"]),
        ({"mode": "unknown"}, ["Auto"]),
        ({"mode": "read-only"}, ["Auto", "Ask first"]),
        ({"mode": "read-only"}, ["Auto", "Ask first"]),
        ({"mode": "full-access", "turns_left": 2}, ["Auto", "Ask first", "Full access"]),
        ({"mode": "full-access", "turns_left": 1}, ["Auto", "Ask first", "Full access"]),
        ({"mode": "full-access", "turns_left": 0}, ["Auto", "Ask first", "Full access", "Auto"]),
    ]:
        agent.current_session.update(state)
        plugin.detect_intent(agent)
        reminders = agent.current_session["messages"]
        assert len(reminders) == len(expected)
        assert all(f"Mode: {label} —" in message["content"]
                   for message, label in zip(reminders, expected))
