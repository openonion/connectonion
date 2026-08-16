"""Compatibility coverage for the deprecated ULW/YOLO import names."""

from unittest.mock import Mock

from connectonion.useful_plugins.ulw import (
    ULW_CONTINUE_PROMPT,
    ULW_DEFAULT_TURNS,
    YOLO_CONTINUE_PROMPT,
    YOLO_DEFAULT_TURNS,
    handle_ulw_mode_change,
    handle_yolo_mode_change,
    inject_ulw_prompt,
    poll_prompt_update,
    ulw,
    yolo,
)


class FakeAgent:
    def __init__(self, io=None, messages=None):
        self.io = io
        self.logger = Mock()
        self.current_session = {
            "messages": list(messages) if messages else [],
            "iteration": 1,
            "turn": 0,
        }


def test_ulw_alias_uses_the_canonical_bounded_full_access_state():
    agent = FakeAgent()

    handle_ulw_mode_change(agent, turns=5)

    assert agent.current_session["mode"] == ":danger-full-access"
    assert agent.current_session["full_access_turns"] == 5
    assert agent.current_session["full_access_turns_used"] == 0
    assert agent.current_session["skip_tool_approval"] is True


def test_yolo_alias_has_the_same_canonical_state_and_plugin():
    agent = FakeAgent()

    handle_yolo_mode_change(agent, turns=4)

    assert yolo is ulw
    assert YOLO_DEFAULT_TURNS == ULW_DEFAULT_TURNS
    assert YOLO_CONTINUE_PROMPT == ULW_CONTINUE_PROMPT
    assert agent.current_session["mode"] == ":danger-full-access"
    assert agent.current_session["full_access_turns"] == 4


def test_prompt_aliases_keep_the_canonical_full_access_prompt_behavior():
    io = Mock()
    io.receive_all.return_value = [{"prompt": "finish the refactor"}]
    agent = FakeAgent(io=io, messages=[{"role": "system", "content": "base"}])

    poll_prompt_update(agent)
    inject_ulw_prompt(agent)

    assert agent.current_session["full_access_prompt"] == "finish the refactor"
    assert agent.current_session["messages"][0]["content"] == (
        "base\n\n[Prompt]\nfinish the refactor"
    )
