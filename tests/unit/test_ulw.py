"""Unit tests for connectonion/useful_plugins/ulw.py"""

import pytest
from unittest.mock import Mock

from connectonion import Agent
from connectonion.core.events import after_user_input, on_complete
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.usage import TokenUsage
from connectonion.useful_plugins.ulw import (
    ULW_CONTINUE_PROMPT,
    ULW_DEFAULT_TURNS,
    YOLO_DEFAULT_TURNS,
    handle_ulw_mode_change,
    handle_yolo_mode_change,
    inject_ulw_prompt,
    poll_prompt_update,
    stop_autonomous_mode,
    ulw_keep_working,
    yolo,
)
from tests.utils.mock_helpers import MockLLM


class FakeAgent:
    def __init__(self, io=None, messages=None, mode=None):
        self.io = io
        self.logger = Mock()
        self.current_session = {
            'messages': list(messages) if messages else [],
            'iteration': 1,
            'turn': 0,
        }
        if mode is not None:
            self.current_session['mode'] = mode
        self.input_calls = []
        self._pending_inputs = []

    def input(self, text):
        self.input_calls.append(text)

    def _queue_input(self, text):
        self.input_calls.append(text)


# ---------- handle_ulw_mode_change ----------

def test_mode_change_defaults_to_100_turns():
    agent = FakeAgent()
    handle_ulw_mode_change(agent)
    assert agent.current_session['mode'] == 'ulw'
    assert agent.current_session['ulw_turns'] == ULW_DEFAULT_TURNS
    assert agent.current_session['ulw_turns_used'] == 0
    assert agent.current_session['skip_tool_approval'] is True


def test_mode_change_uses_explicit_turns():
    agent = FakeAgent()
    handle_ulw_mode_change(agent, turns=5)
    assert agent.current_session['ulw_turns'] == 5


def test_legacy_zero_turn_sentinel_uses_default():
    agent = FakeAgent()
    handle_ulw_mode_change(agent, turns=0)
    assert agent.current_session['ulw_turns'] == ULW_DEFAULT_TURNS


def test_mode_change_notifies_io_when_present():
    io = Mock()
    agent = FakeAgent(io=io)
    handle_ulw_mode_change(agent, turns=7)
    io.send.assert_called_once_with(
        {'type': 'mode_changed', 'mode': 'ulw', 'triggered_by': 'user'}
    )


def test_mode_change_skips_notify_without_io():
    agent = FakeAgent(io=None)
    handle_ulw_mode_change(agent)  # should not raise


def test_yolo_mode_uses_legacy_wire_mode_and_state_keys():
    io = Mock()
    agent = FakeAgent(io=io)

    handle_yolo_mode_change(agent, turns=8)

    assert agent.current_session['mode'] == 'ulw'
    assert agent.current_session['ulw_turns'] == 8
    assert agent.current_session['ulw_turns_used'] == 0
    assert agent.current_session['skip_tool_approval'] is True
    io.send.assert_called_once_with(
        {'type': 'mode_changed', 'mode': 'ulw', 'triggered_by': 'user'}
    )


@pytest.mark.parametrize("turns", [0, -1, True, 1.5, "10"])
def test_autonomous_mode_rejects_invalid_turn_budget(turns):
    with pytest.raises(ValueError, match="positive integer"):
        handle_yolo_mode_change(FakeAgent(), turns=turns)


def test_yolo_plugin_auto_activates_on_first_user_input():
    agent = FakeAgent(mode='safe')

    plugin = yolo(turns=6)
    plugin[0](agent)

    assert agent.current_session['mode'] == 'ulw'
    assert agent.current_session['ulw_turns'] == 6


def test_yolo_plugin_rejects_invalid_turn_budget_at_configuration_time():
    with pytest.raises(ValueError, match="positive integer"):
        yolo(turns=0)


# ---------- ulw_keep_working ----------

def test_keep_working_noop_when_mode_is_not_ulw():
    agent = FakeAgent(mode='safe')
    ulw_keep_working(agent)
    assert agent.input_calls == []
    assert 'ulw_turns_used' not in agent.current_session


def test_keep_working_increments_turns_and_calls_input_below_max():
    agent = FakeAgent(mode='ulw')
    agent.current_session['ulw_turns'] = 3
    agent.current_session['ulw_turns_used'] = 1
    ulw_keep_working(agent)
    assert agent.current_session['ulw_turns_used'] == 2
    assert agent.input_calls == [ULW_CONTINUE_PROMPT]


def test_keep_working_supports_yolo_mode():
    agent = FakeAgent(mode='yolo')
    agent.current_session['ulw_turns'] = YOLO_DEFAULT_TURNS
    agent.current_session['ulw_turns_used'] = 0

    ulw_keep_working(agent)

    assert agent.current_session['ulw_turns_used'] == 1
    assert agent.input_calls == [ULW_CONTINUE_PROMPT]


def test_keep_working_at_max_with_continue_action_extends_and_falls_through():
    io = Mock()
    io.receive.return_value = {'action': 'continue', 'turns': 10}
    agent = FakeAgent(io=io, mode='ulw')
    agent.current_session['ulw_turns'] = 5
    agent.current_session['ulw_turns_used'] = 4  # +1 = 5 hits max
    ulw_keep_working(agent)
    assert agent.current_session['ulw_turns'] == 15  # 5 + 10
    assert agent.input_calls == [ULW_CONTINUE_PROMPT]  # falls through


def test_keep_working_at_max_with_switch_mode_exits_to_new_mode():
    io = Mock()
    io.receive.return_value = {'action': 'switch_mode', 'mode': 'review'}
    agent = FakeAgent(io=io, mode='ulw')
    agent.current_session['ulw_turns'] = 2
    agent.current_session['ulw_turns_used'] = 1
    ulw_keep_working(agent)
    assert agent.current_session['mode'] == 'review'
    assert 'skip_tool_approval' not in agent.current_session
    assert 'ulw_turns' not in agent.current_session
    assert agent.input_calls == []


def test_keep_working_at_max_with_unknown_action_exits_to_safe():
    io = Mock()
    io.receive.return_value = {'action': 'mystery'}
    agent = FakeAgent(io=io, mode='ulw')
    agent.current_session['ulw_turns'] = 1
    agent.current_session['ulw_turns_used'] = 0
    ulw_keep_working(agent)
    assert agent.current_session['mode'] == 'safe'
    assert agent.input_calls == []


def test_keep_working_at_max_without_io_returns_silently():
    agent = FakeAgent(io=None, mode='ulw')
    agent.current_session['ulw_turns'] = 1
    agent.current_session['ulw_turns_used'] = 0
    ulw_keep_working(agent)
    assert agent.input_calls == []
    assert agent.current_session['mode'] == 'ulw'  # state untouched


def test_stop_signal_exits_autonomous_mode():
    io = Mock()
    agent = FakeAgent(io=io, mode='ulw')
    agent.current_session['ulw_turns'] = 5
    agent.current_session['ulw_turns_used'] = 2
    agent.current_session['skip_tool_approval'] = True

    stop_autonomous_mode(agent)

    assert agent.current_session['mode'] == 'safe'
    assert 'ulw_turns' not in agent.current_session
    assert 'ulw_turns_used' not in agent.current_session
    assert 'skip_tool_approval' not in agent.current_session
    io.send.assert_called_once_with(
        {'type': 'mode_changed', 'mode': 'safe', 'triggered_by': 'stop_signal'}
    )


def test_yolo_returns_and_persists_the_terminal_turn_result():
    llm = MockLLM(responses=[
        LLMResponse(content="turn-1", tool_calls=[], raw_response={}, usage=TokenUsage()),
        LLMResponse(content="turn-2", tool_calls=[], raw_response={}, usage=TokenUsage()),
        LLMResponse(content="turn-3", tool_calls=[], raw_response={}, usage=TokenUsage()),
    ])
    agent = Agent("yolo-result", llm=llm, plugins=[yolo(turns=3)], log=False, quiet=True)

    result = agent.input("start")

    assert result == "turn-3"
    assert agent.current_session['result'] == "turn-3"
    assert agent.current_session['turn'] == 3
    assert llm.call_count == 3


def test_yolo_continuations_are_iterative_beyond_python_recursion_depth():
    turn_budget = 400
    llm = MockLLM(on_complete=lambda messages, tools: LLMResponse(
        content=f"turn-{llm.call_count}",
        tool_calls=[],
        raw_response={},
        usage=TokenUsage(),
    ))
    agent = Agent(
        "yolo-iterative",
        llm=llm,
        plugins=[yolo(turns=turn_budget)],
        log=False,
        quiet=True,
    )

    result = agent.input("start")

    assert result == f"turn-{turn_budget}"
    assert agent.current_session['result'] == result
    assert llm.call_count == turn_budget


def test_yolo_preserves_chronological_turn_lifecycle():
    lifecycle = []

    @after_user_input
    def record_input(agent):
        lifecycle.append(f"input-{agent.current_session['turn']}")

    @on_complete
    def record_complete(agent):
        lifecycle.append(f"complete-{agent.current_session['turn']}")

    llm = MockLLM(responses=[
        LLMResponse(content="one", tool_calls=[], raw_response={}, usage=TokenUsage()),
        LLMResponse(content="two", tool_calls=[], raw_response={}, usage=TokenUsage()),
    ])
    agent = Agent(
        "yolo-lifecycle",
        llm=llm,
        plugins=[yolo(turns=2)],
        on_events=[record_input, record_complete],
        log=False,
        quiet=True,
    )

    agent.input("start")

    assert lifecycle == ["input-1", "complete-1", "input-2", "complete-2"]


def test_interrupt_exits_yolo_without_starting_another_turn():
    from connectonion.useful_plugins.tool_approval import poll_interrupt

    def note(text: str) -> str:
        """Record a note."""
        return "noted"

    class InterruptIO:
        def __init__(self):
            self.sent = []

        def receive_all(self, msg_type=None):
            return [{'type': 'INTERRUPT'}] if msg_type == 'INTERRUPT' else []

        def send(self, event):
            self.sent.append(event)

    llm = MockLLM(responses=[
        LLMResponse(
            content="",
            tool_calls=[ToolCall(name="note", arguments={"text": "x"}, id="c1")],
            raw_response={},
            usage=TokenUsage(),
        ),
        LLMResponse(
            content="continued-after-interrupt",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        ),
    ])
    agent = Agent(
        "yolo-interrupt",
        llm=llm,
        tools=[note],
        plugins=[yolo(turns=2)],
        on_events=[poll_interrupt],
        log=False,
        quiet=True,
    )
    agent.io = InterruptIO()

    result = agent.input("start")

    assert result == "What would you like me to do?"
    assert agent.current_session['result'] == result
    assert agent.current_session['mode'] == 'safe'
    assert llm.call_count == 1


def test_interrupt_exits_yolo_after_a_text_only_turn():
    from connectonion.useful_plugins.tool_approval import (
        poll_interrupt,
        poll_interrupt_after_text,
    )

    class InterruptIO:
        def __init__(self):
            self.sent = []

        def receive_all(self, msg_type=None):
            return [{'type': 'INTERRUPT'}] if msg_type == 'INTERRUPT' else []

        def send(self, event):
            self.sent.append(event)

    llm = MockLLM(responses=[
        LLMResponse(
            content="first-final",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        ),
        LLMResponse(
            content="second-final",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        ),
    ])
    agent = Agent(
        "yolo-text-interrupt",
        llm=llm,
        plugins=[yolo(turns=2)],
        on_events=[poll_interrupt, poll_interrupt_after_text],
        log=False,
        quiet=True,
    )
    agent.io = InterruptIO()

    result = agent.input("start")

    assert result == "What would you like me to do?"
    assert agent.current_session['result'] == result
    assert agent.current_session['mode'] == 'safe'
    assert llm.call_count == 1


# ---------- poll_prompt_update ----------

def test_poll_prompt_noop_without_io():
    agent = FakeAgent(io=None)
    poll_prompt_update(agent)
    assert 'ulw_prompt' not in agent.current_session


def test_poll_prompt_stores_latest_from_receive_all():
    io = Mock()
    io.receive_all.return_value = [
        {'prompt': 'first goal'},
        {'prompt': 'final goal'},
    ]
    agent = FakeAgent(io=io)
    poll_prompt_update(agent)
    io.receive_all.assert_called_once_with('prompt_update')
    assert agent.current_session['ulw_prompt'] == 'final goal'


# ---------- inject_ulw_prompt ----------

def test_inject_prompt_noop_when_no_prompt():
    agent = FakeAgent(messages=[{'role': 'system', 'content': 'base'}])
    inject_ulw_prompt(agent)
    assert agent.current_session['messages'][0]['content'] == 'base'


def test_inject_prompt_noop_when_no_system_message():
    agent = FakeAgent(messages=[{'role': 'user', 'content': 'hi'}])
    agent.current_session['ulw_prompt'] = 'goal'
    inject_ulw_prompt(agent)
    assert agent.current_session['messages'][0]['content'] == 'hi'


def test_inject_prompt_appends_to_system_message():
    agent = FakeAgent(messages=[{'role': 'system', 'content': 'base instructions'}])
    agent.current_session['ulw_prompt'] = 'finish the refactor'
    inject_ulw_prompt(agent)
    assert agent.current_session['messages'][0]['content'] == (
        'base instructions\n\n[Prompt]\nfinish the refactor'
    )


def test_inject_prompt_replaces_existing_prompt_section():
    agent = FakeAgent(messages=[
        {'role': 'system', 'content': 'base\n\n[Prompt]\nold goal'}
    ])
    agent.current_session['ulw_prompt'] = 'new goal'
    inject_ulw_prompt(agent)
    assert agent.current_session['messages'][0]['content'] == 'base\n\n[Prompt]\nnew goal'
