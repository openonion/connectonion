"""The eval plugin scores the work. It is not the work.

Both tests come from one deployed agent that failed every fifteen minutes for
an hour: the account was out of credits, and the call that wanted the credits
was a one-sentence guess at what success would look like — $0.0025 for a
sentence, and the run it was describing never happened.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest

# The package exports a plugin list under this name, which shadows the module.
eval_plugin = importlib.import_module("connectonion.useful_plugins.eval")


def make_agent(model="gemini-2.5-pro", prompt="整理合同"):
    agent = MagicMock()
    agent.model = model
    agent.current_session = {"user_prompt": prompt}
    agent.tools.names.return_value = ["bash"]
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
    agent = make_agent(model="gemini-2.5-pro")

    with patch.object(eval_plugin, "llm_do", return_value="ok") as called:
        eval_plugin.generate_expected(agent)

    assert called.call_args.kwargs["model"] == "gemini-2.5-pro"


def test_an_agent_with_no_model_still_has_a_default():
    agent = make_agent()
    del agent.model

    with patch.object(eval_plugin, "llm_do", return_value="ok") as called:
        eval_plugin.generate_expected(agent)

    assert called.call_args.kwargs["model"]


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
