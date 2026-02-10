"""Tests for co_ai system_reminder plugin."""

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


def test_detect_intent_and_inject_tool(monkeypatch):
    class Intent:
        def __init__(self, ack, is_build):
            self.ack = ack
            self.is_build = is_build

    monkeypatch.setattr(plugin, "_REMINDERS", {"r": {"content": "REM", "intent": "build", "triggers": []}})
    monkeypatch.setattr(plugin, "llm_do", lambda *a, **k: Intent("understood", True))

    agent = SimpleNamespace(
        current_session={"user_prompt": "build", "messages": []},
        io=FakeIO(),
        logger=FakeLogger(),
    )

    plugin.detect_intent(agent)

    assert agent.current_session["intent"]["is_build"] is True
    assert any("REM" in m["content"] for m in agent.current_session["messages"])

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
