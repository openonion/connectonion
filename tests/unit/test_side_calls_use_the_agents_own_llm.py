"""The intent step and eval scoring spend the user's model, not ours (#1758).

Both read `getattr(agent, "model", None)`. A real Agent has no `.model` — the
model lives on `agent.llm` — so both always fell back to the managed default: a
user on `ollama/qwen3` or their own key still sent every prompt to co/ and
spent credits nothing recorded. The earlier tests passed because their fake
agent had a `.model` a real one never has, which is why these build a real
Agent.
"""

import importlib

import pytest

from connectonion import Agent
from connectonion.core.llm import LLM, LLMResponse
from connectonion.core.usage import TokenUsage

system_reminder = importlib.import_module("connectonion.cli.co_ai.plugins.system_reminder")
eval_plugin = importlib.import_module("connectonion.useful_plugins.eval")
llm_do_module = importlib.import_module("connectonion.llm_do")


class LocalLLM(LLM):
    """Stands in for a local model: answers everything, records who asked."""

    def __init__(self):
        self.model = "ollama/qwen3"
        self.calls = []

    def complete(self, messages, tools=None, **kwargs):
        self.calls.append("complete")
        return LLMResponse("the file is written", [], None,
                           TokenUsage(input_tokens=10, output_tokens=5, cost=0.0))

    def structured_complete(self, messages, output_schema, **kwargs):
        self.calls.append(output_schema.__name__)
        self.last_structured_usage = TokenUsage(input_tokens=10, output_tokens=5, cost=0.0)
        fields = {"ack": "Writing it.", "is_build": False,
                  "passed": True, "summary": "done"}
        return output_schema(**{k: v for k, v in fields.items()
                                if k in output_schema.model_fields})


@pytest.fixture
def agent(monkeypatch):
    def no_managed_model(*args, **kwargs):
        raise AssertionError("a side call built its own LLM instead of using agent.llm")

    monkeypatch.setattr(llm_do_module, "create_llm", no_managed_model)
    agent = Agent("t", llm=LocalLLM(), log=False, quiet=True)
    agent.current_session = {"messages": [], "trace": [], "turn": 1,
                             "iteration": 1, "user_prompt": "write a.py"}
    return agent


def test_the_intent_step_asks_the_agents_own_model(agent):
    system_reminder.detect_intent(agent)

    assert agent.llm.calls == ["IntentAnalysis"]
    assert agent.current_session["intent"]["ack"] == "Writing it."


def test_eval_scoring_asks_the_agents_own_model(agent):
    eval_plugin.generate_expected(agent)
    agent.current_session.update({"result": "the file is written", "mode": "normal"})
    eval_plugin.evaluate_completion(agent)

    assert agent.llm.calls == ["complete", "EvalResult"]
    assert agent.current_session["expected"] == "the file is written"
