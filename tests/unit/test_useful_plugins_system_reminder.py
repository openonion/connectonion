"""Tests for useful_plugins system_reminder."""

from types import SimpleNamespace
import importlib

sr = importlib.import_module("connectonion.useful_plugins.system_reminder")


def test_parse_frontmatter_and_match():
    text = "---\nname: test\ntriggers: []\n---\nBody"
    meta, body = sr._parse_frontmatter(text)
    assert meta["name"] == "test"
    assert body == "Body"

    assert sr._matches_pattern("*.py", "file.py") is True
    assert sr._matches_pattern("*.js", "file.py") is False


def test_find_reminder_and_inject():
    reminders = {
        "r1": {
            "content": "Remember ${tool_name} ${file_path}",
            "triggers": [{"tool": "read_file", "path_pattern": "*.py"}],
        }
    }

    content = sr._find_reminder(reminders, "read_file", {"path": "a.py"})
    assert "read_file" in content
    assert "a.py" in content

    # Inject into tool message
    agent = SimpleNamespace(
        current_session={
            "trace": [{"type": "tool_result", "name": "read_file", "args": {"path": "a.py"}}],
            "messages": [{"role": "tool", "content": "result"}],
        }
    )

    # Patch module reminders
    sr._REMINDERS = reminders
    sr.inject_reminder(agent)

    assert "Remember" in agent.current_session["messages"][0]["content"]
