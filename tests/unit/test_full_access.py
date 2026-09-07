"""Full access is a bounded permission mode, not an autonomous loop."""

from unittest.mock import Mock

import pytest

from connectonion import Agent
from connectonion.core.llm import LLMResponse
from connectonion.core.mode import AUTO, FULL_ACCESS
from connectonion.core.usage import TokenUsage
from connectonion.useful_plugins.full_access import (
    FULL_ACCESS_DEFAULT_TURNS,
    consume_configured_full_access_turn,
    enable_full_access,
    full_access,
    handle_full_access_mode_change,
)
from tests.utils.mock_helpers import MockLLM


class FakeAgent:
    def __init__(self, io=None, session=None):
        self.io = io
        self.logger = Mock()
        self.current_session = dict(session or {"mode": AUTO})


def _one_response_llm():
    return MockLLM(responses=[
        LLMResponse(
            content="done",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])


def test_full_access_defaults_to_a_positive_bounded_budget():
    agent = FakeAgent()

    handle_full_access_mode_change(agent)

    assert agent.current_session == {
        "mode": FULL_ACCESS,
        "turns_left": FULL_ACCESS_DEFAULT_TURNS,
    }


def test_full_access_uses_an_explicit_budget_and_notifies_the_frontend():
    io = Mock()
    agent = FakeAgent(io=io)

    handle_full_access_mode_change(agent, turns=7)

    assert agent.current_session == {"mode": FULL_ACCESS, "turns_left": 7}
    io.send.assert_called_once_with({
        "type": "mode_changed",
        "mode": FULL_ACCESS,
        "turns_left": 7,
        "triggered_by": "user",
    })


@pytest.mark.parametrize("turns", [0, -1, True, 1.5, "5"])
def test_full_access_rejects_malformed_budgets_without_granting(turns):
    agent = FakeAgent()

    with pytest.raises(ValueError, match="positive integer"):
        handle_full_access_mode_change(agent, turns=turns)

    assert agent.current_session == {"mode": AUTO}


def test_enable_full_access_before_input_runs_exactly_one_user_driven_agent_turn(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    llm = _one_response_llm()
    agent = Agent(
        name="bounded-full-access",
        llm=llm,
        plugins=[full_access],
        log=False,
        quiet=True,
    )

    enable_full_access(agent, turns=1)
    result = agent.input("create one file")

    assert result == "done"
    assert len(llm.calls) == 1
    assert agent.current_session["mode"] == AUTO
    assert "turns_left" not in agent.current_session


def test_completed_turn_decrements_without_synthesizing_another_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    llm = _one_response_llm()
    agent = Agent(
        name="two-turn-grant",
        llm=llm,
        plugins=[full_access],
        log=False,
        quiet=True,
    )

    enable_full_access(agent, turns=2)
    result = agent.input("do the bounded task")

    assert result == "done"
    assert len(llm.calls) == 1
    assert agent.current_session["mode"] == FULL_ACCESS
    assert agent.current_session["turns_left"] == 1
    user_messages = [
        message for message in agent.current_session["messages"]
        if message["role"] == "user"
    ]
    assert [message["content"] for message in user_messages] == ["do the bounded task"]


def test_expiry_emits_auto_without_a_checkpoint_or_extension_prompt():
    io = Mock()
    agent = FakeAgent(
        io=io,
        session={"mode": FULL_ACCESS, "turns_left": 1},
    )

    consume_configured_full_access_turn(agent)

    assert agent.current_session == {"mode": AUTO}
    io.send.assert_called_once_with({
        "type": "mode_changed",
        "mode": AUTO,
        "turns_left": None,
        "triggered_by": "full_access_expired",
    })


def test_plain_plugin_keeps_the_new_session_default_auto(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = Agent(
        name="auto-by-default",
        llm=_one_response_llm(),
        plugins=[full_access],
        log=False,
        quiet=True,
    )

    agent.input("hello")

    assert agent.current_session["mode"] == AUTO
    assert "turns_left" not in agent.current_session


def test_old_full_access_snapshot_does_not_translate_into_authority(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = Agent(
        name="old-snapshot",
        llm=_one_response_llm(),
        plugins=[full_access],
        log=False,
        quiet=True,
    )

    agent.input(
        "resume",
        session={
            "session_id": "old",
            "messages": [{"role": "system", "content": "system"}],
            "trace": [],
            "turn": 0,
            "mode": ":danger-full-access",
            "full_access_turns": 100,
            "full_access_turns_used": 0,
            "skip_tool_approval": True,
        },
    )

    assert agent.current_session["mode"] == AUTO
    assert "turns_left" not in agent.current_session
    assert "full_access_turns" not in agent.current_session
    assert "skip_tool_approval" not in agent.current_session
