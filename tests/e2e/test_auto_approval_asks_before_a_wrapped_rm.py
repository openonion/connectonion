"""
LLM-Note: #1750 end to end. A real Agent, the real bash tool and the real
approval plugin, in the default Auto mode. Only the model is scripted: it asks
for `nice rm -rf <dir>/precious`, which on main ran without a prompt and
deleted the directory. Now the call has to reach a person, and when the person
says no, the directory is still there.
"""

import pytest

from connectonion import Agent, bash
from connectonion.core.llm import LLM, LLMResponse, ToolCall
from connectonion.useful_plugins import tool_approval


class ScriptedLLM(LLM):
    """Asks for one shell command, then finishes."""

    model = "scripted"

    def __init__(self, command):
        self.pending = [command]

    def complete(self, messages, tools=None, **kwargs):
        if self.pending:
            call = ToolCall("bash", {"command": self.pending.pop()}, "call_1")
            return LLMResponse(None, [call], None, None)
        return LLMResponse("done", [], None, None)

    def structured_complete(self, *args, **kwargs):
        raise NotImplementedError


class PersonWhoSaysNo:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)

    def receive(self):
        return {"approved": False, "scope": "once"}

    def receive_all(self, timeout=None):
        return []

    def log(self, *args, **kwargs):
        pass


@pytest.mark.parametrize("wrapper", ["nice", "timeout 60", "nohup", "sudo"])
def test_a_wrapped_rm_does_not_run_without_approval(tmp_path, monkeypatch, wrapper):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    precious = tmp_path / "precious"
    precious.mkdir()
    (precious / "thesis.docx").write_text("four years")

    agent = Agent("t", llm=ScriptedLLM(f"{wrapper} rm -rf {precious}"),
                  tools=[bash], plugins=[tool_approval], log=False, quiet=True)
    agent.io = PersonWhoSaysNo()
    agent.input("clean up")

    assert (precious / "thesis.docx").read_text() == "four years"
    result = next(e for e in agent.current_session["trace"] if e.get("type") == "tool_result")
    assert result["status"] != "success", result
