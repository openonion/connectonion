"""Unit tests for connectonion/useful_plugins/runtime_input.py"""

from unittest.mock import Mock

from connectonion.useful_plugins.runtime_input import (
    RUNTIME_INPUT_FRAME_PREFIX,
    apply_runtime_input,
)


class FakeAgent:
    def __init__(self, io=None):
        self.io = io
        self.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 3,
            'turn': 1,
        }

    def _record_trace(self, entry):
        self.current_session['trace'].append(entry)


def test_noop_when_io_is_none():
    agent = FakeAgent(io=None)
    apply_runtime_input(agent)
    assert agent.current_session['messages'] == []
    assert agent.current_session['trace'] == []


def test_noop_when_io_lacks_pop_runtime_inputs():
    agent = FakeAgent(io=Mock(spec=[]))  # spec=[] strips all attrs
    apply_runtime_input(agent)
    assert agent.current_session['messages'] == []
    assert agent.current_session['trace'] == []


def test_noop_when_pop_returns_empty():
    io = Mock()
    io.pop_runtime_inputs.return_value = []
    apply_runtime_input(FakeAgent(io=io))
    io.pop_runtime_inputs.assert_called_once()


def test_single_input_appended_with_frame_prefix():
    io = Mock()
    io.pop_runtime_inputs.return_value = [{'id': 'm1', 'prompt': 'hello'}]
    agent = FakeAgent(io=io)
    apply_runtime_input(agent)
    assert agent.current_session['messages'] == [
        {'role': 'user', 'content': RUNTIME_INPUT_FRAME_PREFIX + 'hello'}
    ]


def test_single_input_records_full_trace_entry():
    io = Mock()
    io.pop_runtime_inputs.return_value = [{'id': 'msg-42', 'prompt': 'hi'}]
    agent = FakeAgent(io=io)
    apply_runtime_input(agent)
    assert agent.current_session['trace'] == [{
        'type': 'user_input',
        'id': 'msg-42',
        'content': 'hi',
        'turn': 1,
        'iteration': 3,
        'runtime_input': True,
    }]


def test_multiple_inputs_all_appended_in_order():
    io = Mock()
    io.pop_runtime_inputs.return_value = [
        {'id': 'a', 'prompt': 'first'},
        {'id': 'b', 'prompt': 'second'},
    ]
    agent = FakeAgent(io=io)
    apply_runtime_input(agent)
    contents = [m['content'] for m in agent.current_session['messages']]
    assert contents == [
        RUNTIME_INPUT_FRAME_PREFIX + 'first',
        RUNTIME_INPUT_FRAME_PREFIX + 'second',
    ]
    assert [t['id'] for t in agent.current_session['trace']] == ['a', 'b']


def test_empty_and_missing_prompts_skipped():
    io = Mock()
    io.pop_runtime_inputs.return_value = [
        {'id': 'm1', 'prompt': ''},
        {'id': 'm2', 'prompt': None},
        {'id': 'm3'},                       # no prompt key
        {'id': 'm4', 'prompt': 'kept'},
    ]
    agent = FakeAgent(io=io)
    apply_runtime_input(agent)
    assert len(agent.current_session['messages']) == 1
    assert agent.current_session['messages'][0]['content'].endswith('kept')


def test_missing_id_still_records_trace_with_none():
    io = Mock()
    io.pop_runtime_inputs.return_value = [{'prompt': 'no id here'}]
    agent = FakeAgent(io=io)
    apply_runtime_input(agent)
    assert agent.current_session['trace'][0]['id'] is None


def test_turn_defaults_to_zero_when_missing():
    io = Mock()
    io.pop_runtime_inputs.return_value = [{'id': 'x', 'prompt': 'hi'}]
    agent = FakeAgent(io=io)
    del agent.current_session['turn']  # simulate older session
    apply_runtime_input(agent)
    assert agent.current_session['trace'][0]['turn'] == 0
