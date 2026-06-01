"""Unit tests for connectonion/useful_plugins/ulw.py"""

from unittest.mock import Mock

from connectonion.useful_plugins.ulw import (
    ULW_CONTINUE_PROMPT,
    ULW_DEFAULT_TURNS,
    handle_ulw_mode_change,
    inject_ulw_prompt,
    poll_prompt_update,
    ulw_keep_working,
)


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

    def input(self, text):
        self.input_calls.append(text)


# ---------- handle_ulw_mode_change ----------

def test_mode_change_defaults_to_100_turns():
    agent = FakeAgent()
    handle_ulw_mode_change(agent)
    assert agent.current_session['mode'] == 'ulw'
    assert agent.current_session['ulw_turns'] == ULW_DEFAULT_TURNS
    assert agent.current_session['ulw_turns_used'] == 0
    assert 'skip_tool_approval' not in agent.current_session


def test_mode_change_uses_explicit_turns():
    agent = FakeAgent()
    handle_ulw_mode_change(agent, turns=5)
    assert agent.current_session['ulw_turns'] == 5


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

