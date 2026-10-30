"""The eval plugin scores the work. It is not the work.

Both tests come from one deployed agent that failed every fifteen minutes for
an hour: the account was out of credits, and the call that wanted the credits
was a one-sentence guess at what success would look like — $0.0025 for a
sentence, and the run it was describing never happened.
"""

import importlib
from unittest.mock import patch

import pytest

from connectonion import Agent
from connectonion.core.llm import OpenAICompatibleLLM

# The package exports a plugin list under this name, which shadows the module.
eval_plugin = importlib.import_module("connectonion.useful_plugins.eval")


def make_agent(prompt="整理合同"):
    # A real Agent: the fake this replaced had an `agent.model` a real one
    # never has, which is how scoring went to co/ unnoticed (#1758).
    def bash(command: str) -> str:
        """Run a command."""
        return ""

    llm = OpenAICompatibleLLM(model="qwen3", base_url="http://localhost:11434/v1")
    agent = Agent("t", llm=llm, tools=[bash], log=False, quiet=True)
    agent.current_session = {"user_prompt": prompt}
    return agent


def test_a_refused_call_does_not_stop_the_turn():
    """The failure that motivated this: out of credits, before the first tool."""
    agent = make_agent()

    with patch.object(eval_plugin, "llm_do",
                      side_effect=RuntimeError("Insufficient ConnectOnion Credits")):
        eval_plugin.generate_expected(agent)      # must not raise

    # No expectation to score against, and that is the whole cost.
    assert not agent.current_session.get("expected")


def test_the_call_follows_the_model_the_agent_was_built_with():
    """A hardcoded co/ model billed an account the agent was configured away from."""
    agent = make_agent()

    with patch.object(eval_plugin, "llm_do", return_value="ok") as called:
        eval_plugin.generate_expected(agent)

    assert called.call_args.kwargs["llm"] is agent.llm


def test_a_working_call_is_still_stored():
    agent = make_agent()

    with patch.object(eval_plugin, "llm_do", return_value="the ledger is updated"):
        eval_plugin.generate_expected(agent)

    assert agent.current_session["expected"] == "the ledger is updated"


def test_scoring_after_the_work_is_also_not_fatal():
    """on_complete is safer — the work is done — but it can still turn a
    successful run into a failed one."""
    agent = make_agent()
    agent.current_session.update({
        "mode": "normal", "expected": "x", "trace": [], "messages": [],
    })

    with patch.object(eval_plugin, "llm_do",
                      side_effect=RuntimeError("Insufficient ConnectOnion Credits")):
        eval_plugin.evaluate_completion(agent)    # must not raise


def test_scoring_calls_leave_temperature_to_the_model():
    """o4-mini (the OpenAILLM default) and the gpt-5 family accept only the
    default temperature; a hard-coded one is a 400 on every call (#2701)."""
    agent = make_agent()
    agent.current_session.update({"mode": "normal", "trace": [], "messages": []})

    with patch.object(eval_plugin, "llm_do", return_value="ok") as called:
        eval_plugin.generate_expected(agent)
        agent.current_session.pop("expected")
        eval_plugin.evaluate_completion(agent)

    # generate_expected, then the fallback expectation and the evaluation.
    assert called.call_count == 3
    for call in called.call_args_list:
        assert "temperature" not in call.kwargs


def test_a_refused_fallback_expectation_does_not_fail_the_finished_turn():
    """With no expectation stored, on_complete asks for one itself; that call
    used to sit outside any try, so a refusal raised out of agent.input()."""
    agent = make_agent()
    agent.current_session.update({"mode": "normal", "trace": [], "messages": []})

    def refuse_expectation(prompt, **kwargs):
        if "output" not in kwargs:
            raise RuntimeError("Unsupported value: 'temperature'")
        return "scored"

    with patch.object(eval_plugin, "llm_do", side_effect=refuse_expectation) as called:
        eval_plugin.evaluate_completion(agent)    # must not raise

    assert agent.current_session["expected"] == ""
    # Scoring still ran, just without an expectation to compare against.
    assert "output" in called.call_args.kwargs
    assert agent.current_session["evaluation"] == "scored"
