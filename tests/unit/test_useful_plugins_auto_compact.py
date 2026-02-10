"""Tests for auto_compact plugin."""

from types import SimpleNamespace
import importlib

auto_compact = importlib.import_module("connectonion.useful_plugins.auto_compact")
llm_do_mod = importlib.import_module("connectonion.llm_do")


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


def test_check_and_compact_triggers(monkeypatch):
    agent = SimpleNamespace(
        context_percent=95,
        current_session={"messages": [{"role": "user", "content": "m"}] * 10},
        io=FakeIO(),
        logger=FakeLogger(),
    )

    monkeypatch.setattr(auto_compact, "_do_compact", lambda a: "done")

    auto_compact.check_and_compact(agent)

    assert any(e.get("type") == "compact" for e in agent.io.sent)


def test_do_compact_updates_messages(monkeypatch):
    monkeypatch.setattr(llm_do_mod, "llm_do", lambda *a, **k: "summary")

    messages = [{"role": "system", "content": "sys"}]
    for i in range(10):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})

    agent = SimpleNamespace(current_session={"messages": messages})

    result = auto_compact._do_compact(agent)
    assert "messages" in result
    assert any("Previous Conversation Summary" in m["content"] for m in agent.current_session["messages"])
