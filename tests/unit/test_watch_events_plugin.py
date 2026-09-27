"""The watch iteration hook is a copyable Agent plugin, not Host lifecycle code."""

import importlib.util

from connectonion import Agent
from connectonion.cli.commands.copy_commands import handle_copy
from connectonion.core.llm import LLMResponse
from connectonion.useful_plugins import watch_events


def test_plugin_injects_at_iteration_boundary_and_can_extend_a_final_iteration(tmp_path):
    pending = [{"id": "first", "content": "The file now contains A."}]
    calls = []

    def poll():
        events = pending[:]
        pending.clear()
        return events

    class LLM:
        model = "fake"

        def complete(self, messages, tools=None, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                pending.append({"id": "second", "content": "The file now contains B."})
            return LLMResponse(content=f"answer-{len(calls)}", tool_calls=[], raw_response=None)

    agent = Agent("plugin-test", llm=LLM(), plugins=[watch_events(poll)],
                  log=False, quiet=True)
    agent.input("Begin")

    assert len(calls) == 2
    assert any(message.get("internal") and "contains A" in message["content"]
               for message in calls[0])
    assert any(message.get("internal") and "contains B" in message["content"]
               for message in calls[1])
    assert [entry["watch_event_ids"] for entry in agent.current_session["trace"]
            if entry.get("watch_event_ids")] == [["first"], ["second"]]


def test_copied_plugin_can_be_imported_and_edited(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    handle_copy(["watch_events"])
    copied = tmp_path / "plugins" / "watch_events.py"
    assert copied.is_file()
    spec = importlib.util.spec_from_file_location("custom_watch_events", copied)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.watch_events(lambda: [])) == 3


def test_batch_limit_resets_for_the_next_turn():
    pending = []
    calls = []

    def poll():
        events = pending[:]
        pending.clear()
        return events

    class LLM:
        model = "fake"

        def complete(self, messages, tools=None, **kwargs):
            calls.append(messages)
            return LLMResponse(content="done", tool_calls=[], raw_response=None)

    agent = Agent("plugin-test", llm=LLM(), plugins=[watch_events(poll, max_batches=1)],
                  log=False, quiet=True)
    pending.append({"id": "first", "content": "First observation"})
    agent.input("First turn")
    pending.append({"id": "second", "content": "Second observation"})
    agent.input("Second turn")

    assert len(calls) == 2
    assert any("First observation" in message["content"] for message in calls[0]
               if message.get("internal"))
    assert any("Second observation" in message["content"] for message in calls[1]
               if message.get("internal"))
