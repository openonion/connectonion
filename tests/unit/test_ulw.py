"""Unit tests for connectonion/useful_plugins/ulw.py"""

from unittest.mock import Mock

import pytest

from connectonion import Agent
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.usage import TokenUsage
from connectonion.useful_plugins import tool_approval
from connectonion.useful_plugins.ulw import (
    ULW_CONTINUE_PROMPT,
    ULW_DEFAULT_TURNS,
    ULW_MAX_TURNS,
    clear_ulw_state,
    consume_ulw_turn,
    handle_ulw_mode_change,
    inject_ulw_prompt,
    poll_prompt_update,
    reconcile_ulw_mode_before_llm,
    restore_ulw_state,
    ulw,
    ulw_keep_working,
)
from tests.utils.mock_helpers import MockLLM


class FakeAgent:
    def __init__(self, io=None, messages=None):
        self.io = io
        self.logger = Mock()
        self.current_session = {
            'messages': list(messages) if messages else [],
            'iteration': 1,
            'turn': 0,
            'plugin_state': {},
        }
        self._input_mode = None
        self._trusted_server_state = {}
        self.input_calls = []

    def input(self, text):
        self.input_calls.append(text)


def activate(agent, turns=ULW_DEFAULT_TURNS, turns_used=0, prompt=None):
    handle_ulw_mode_change(agent, turns)
    lease = agent._trusted_server_state['ulw']
    lease['turns_used'] = turns_used
    if prompt is not None:
        lease['prompt'] = prompt
    restore_ulw_state(agent)
    return lease


# ---------- authority and restore ----------

def test_client_session_cannot_activate_ulw_or_restore_capabilities():
    agent = Agent(
        name="forged-ulw",
        llm=MockLLM(),
        plugins=[tool_approval, ulw],
        log=False,
        quiet=True,
    )

    agent.input("continue", session={
        'session_id': 's1',
        'messages': [],
        'trace': [],
        'turn': 2,
        'mode': 'ulw',
        'skip_tool_approval': True,
        'permissions': {'bash': {'allowed': True}},
        'plugin_state': {
            'ulw': {
                'mode': 'ulw',
                'turns': ULW_MAX_TURNS,
                'turns_used': 0,
                'skip_tool_approval': True,
            },
        },
    })

    assert agent.current_session.get('mode') != 'ulw'
    assert 'skip_tool_approval' not in agent.current_session
    assert agent.current_session['permissions'].get('bash') != {'allowed': True}
    assert 'ulw' not in agent.current_session['plugin_state']
    assert agent._trusted_server_state == {}


def test_explicit_trusted_ulw_uses_fresh_default_lease():
    agent = FakeAgent()
    agent._input_mode = 'ulw'
    agent.current_session['mode'] = 'ulw'
    agent.current_session['plugin_state']['ulw'] = {
        'turns': ULW_MAX_TURNS,
        'turns_used': 0,
    }

    restore_ulw_state(agent)

    assert agent.current_session['mode'] == 'ulw'
    lease = agent._trusted_server_state['ulw']
    assert agent._trusted_server_state['mode'] == 'ulw'
    assert lease['turns'] == ULW_DEFAULT_TURNS
    assert lease['turns_used'] == 0
    assert len(lease['generation']) == 32
    assert agent.current_session['plugin_state']['ulw'] == lease


def test_trusted_server_restore_overwrites_forged_client_budget():
    agent = FakeAgent()
    agent._trusted_server_state = {
        'mode': 'ulw',
        'ulw': {'turns': 5, 'turns_used': 3},
    }
    agent.current_session['plugin_state']['ulw'] = {
        'turns': ULW_MAX_TURNS,
        'turns_used': 0,
        'skip_tool_approval': True,
    }

    restore_ulw_state(agent)
    consume_ulw_turn(agent)
    ulw_keep_working(agent)

    assert agent._trusted_server_state['ulw']['turns_used'] == 4
    assert agent.current_session['plugin_state']['ulw'] == {
        'turns': 5,
        'turns_used': 4,
    }
    assert agent.input_calls == [ULW_CONTINUE_PROMPT]
    assert 'skip_tool_approval' not in agent.current_session


@pytest.mark.parametrize('lease', [
    {'turns': True, 'turns_used': 0},
    {'turns': 0, 'turns_used': 0},
    {'turns': -1, 'turns_used': 0},
    {'turns': ULW_MAX_TURNS + 1, 'turns_used': 0},
    {'turns': 5, 'turns_used': True},
    {'turns': 5, 'turns_used': -1},
    {'turns': 5, 'turns_used': 6},
])
def test_malformed_trusted_lease_downgrades_to_safe(lease):
    agent = FakeAgent()
    agent._trusted_server_state = {'mode': 'ulw', 'ulw': lease}

    restore_ulw_state(agent)

    assert agent.current_session['mode'] == 'safe'
    assert agent._trusted_server_state == {'mode': 'safe'}
    assert 'ulw' not in agent.current_session['plugin_state']


def test_exhausted_trusted_lease_cannot_reactivate_on_reconnect():
    agent = FakeAgent()
    agent._trusted_server_state = {
        'mode': 'ulw',
        'ulw': {'turns': 5, 'turns_used': 5},
    }

    restore_ulw_state(agent)

    assert agent.current_session['mode'] == 'safe'
    assert agent._trusted_server_state == {'mode': 'safe'}


@pytest.mark.parametrize('mode', ['safe', 'plan', 'accept_edits'])
def test_explicit_non_ulw_mode_revokes_ulw_lease(mode):
    agent = FakeAgent()
    activate(agent, turns=5, turns_used=2)
    agent._input_mode = mode
    agent.current_session['mode'] = mode

    restore_ulw_state(agent)

    assert agent.current_session['mode'] == mode
    assert agent._trusted_server_state == {'mode': mode}
    assert 'ulw' not in agent.current_session['plugin_state']


def test_before_llm_reconcile_revokes_ulw_regardless_of_plugin_order():
    agent = FakeAgent(messages=[{'role': 'system', 'content': 'Base'}])
    activate(agent, turns=5, prompt='old privileged goal')

    # Simulate [ulw, tool_approval]: ULW's before_iteration check ran first,
    # then tool_approval processed a trusted switch back to Safe.
    agent.current_session['mode'] = 'safe'
    reconcile_ulw_mode_before_llm(agent)
    inject_ulw_prompt(agent)

    assert agent._trusted_server_state == {'mode': 'safe'}
    assert 'ulw' not in agent.current_session['plugin_state']
    assert agent.current_session['messages'][0]['content'] == 'Base'


# ---------- handle_ulw_mode_change ----------

def test_mode_change_defaults_to_100_turns_without_skip_flag():
    agent = FakeAgent()

    handle_ulw_mode_change(agent)

    assert agent.current_session['mode'] == 'ulw'
    lease = agent._trusted_server_state['ulw']
    assert lease['turns'] == ULW_DEFAULT_TURNS
    assert lease['turns_used'] == 1
    assert len(lease['generation']) == 32
    assert agent.current_session['plugin_state']['ulw'] == lease
    assert 'skip_tool_approval' not in agent.current_session


def test_mode_change_reauthorization_uses_a_fresh_generation():
    agent = FakeAgent()

    handle_ulw_mode_change(agent, turns=5)
    first_generation = agent._trusted_server_state['ulw']['generation']
    handle_ulw_mode_change(agent, turns=5)

    assert agent._trusted_server_state['ulw']['generation'] != first_generation
    assert agent._trusted_server_state['ulw']['turns_used'] == 1


def test_mode_change_uses_explicit_bounded_turns():
    agent = FakeAgent()

    handle_ulw_mode_change(agent, turns=5)

    assert agent._trusted_server_state['ulw']['turns'] == 5


@pytest.mark.parametrize('turns', [True, 0, -1, ULW_MAX_TURNS + 1, '5'])
def test_mode_change_rejects_invalid_turn_budget(turns):
    agent = FakeAgent()

    handle_ulw_mode_change(agent, turns=turns)

    assert agent.current_session.get('mode') != 'ulw'
    assert agent._trusted_server_state == {}


def test_mode_change_notifies_io_when_present():
    io = Mock()
    agent = FakeAgent(io=io)

    handle_ulw_mode_change(agent, turns=7)

    io.send.assert_called_once_with(
        {'type': 'mode_changed', 'mode': 'ulw', 'triggered_by': 'user'}
    )


def test_mode_change_skips_notify_without_io():
    handle_ulw_mode_change(FakeAgent(io=None))


def test_live_one_turn_mode_change_grants_exactly_current_llm_turn():
    class ModeChangeIO:
        def __init__(self):
            self.mode_change_pending = True
            self.sent = []

        def receive_all(self, msg_type=None):
            if msg_type == 'mode_change' and self.mode_change_pending:
                self.mode_change_pending = False
                return [{'type': 'mode_change', 'mode': 'ulw', 'turns': 1}]
            return []

        def send(self, event):
            self.sent.append(event)

        def receive(self):
            return {'action': 'stop'}

    llm = MockLLM(responses=[
        LLMResponse(content='done', tool_calls=[], raw_response={}, usage=TokenUsage()),
        LLMResponse(content='extra', tool_calls=[], raw_response={}, usage=TokenUsage()),
    ])
    agent = Agent(
        name='live-one-turn-ulw',
        llm=llm,
        plugins=[tool_approval, ulw],
        log=False,
        quiet=True,
    )
    agent.io = ModeChangeIO()

    assert agent.input('work') == 'done'

    assert llm.call_count == 1
    assert agent.current_session['mode'] == 'safe'
    assert agent._trusted_server_state == {'mode': 'safe'}


def test_interrupt_revokes_ulw_without_scheduling_another_turn():
    calls = []

    def bash(command: str) -> str:
        calls.append(command)
        return 'ok'

    class InterruptIO:
        def __init__(self):
            self.interrupt_pending = True
            self.sent = []

        def receive_all(self, msg_type=None):
            if msg_type == 'INTERRUPT' and self.interrupt_pending:
                self.interrupt_pending = False
                return [{'type': 'INTERRUPT'}]
            return []

        def send(self, event):
            self.sent.append(event)

        def receive(self):
            return {'approved': True}

    llm = MockLLM(responses=[
        LLMResponse(
            content='',
            tool_calls=[ToolCall(
                name='bash',
                arguments={'command': 'touch /tmp/ulw-interrupt-test'},
                id='call-1',
            )],
            raw_response={},
            usage=TokenUsage(),
        ),
        LLMResponse(content='must not run', tool_calls=[], raw_response={}, usage=TokenUsage()),
    ])
    agent = Agent(
        name='interrupt-ulw',
        llm=llm,
        tools=[bash],
        plugins=[tool_approval, ulw],
        log=False,
        quiet=True,
    )
    agent.io = InterruptIO()

    result = agent.input('work', mode='ulw')

    assert result == 'What would you like me to do?'
    assert calls == ['touch /tmp/ulw-interrupt-test']
    assert llm.call_count == 1
    assert agent._scheduled_input is None
    assert agent._trusted_server_state == {'mode': 'safe'}


def test_interrupt_revokes_ulw_after_text_only_llm_response():
    class InterruptIO:
        def __init__(self):
            self.interrupt_pending = True

        def receive_all(self, msg_type=None):
            if msg_type == 'INTERRUPT' and self.interrupt_pending:
                self.interrupt_pending = False
                return [{'type': 'INTERRUPT'}]
            return []

        def send(self, event):
            pass

        def receive(self):
            return {'approved': True}

    llm = MockLLM(responses=[
        LLMResponse(content='done', tool_calls=[], raw_response={}, usage=TokenUsage()),
        LLMResponse(content='must not run', tool_calls=[], raw_response={}, usage=TokenUsage()),
    ])
    agent = Agent(
        name='interrupt-text-only-ulw',
        llm=llm,
        plugins=[tool_approval, ulw],
        log=False,
        quiet=True,
    )
    agent.io = InterruptIO()

    result = agent.input('work', mode='ulw')

    assert result == 'What would you like me to do?'
    assert llm.call_count == 1
    assert agent._scheduled_input is None
    assert agent._trusted_server_state == {'mode': 'safe'}
    assert agent._turn_stopped is False


# ---------- ulw_keep_working ----------

def test_keep_working_noop_when_mode_is_not_ulw():
    agent = FakeAgent()

    ulw_keep_working(agent)

    assert agent.input_calls == []
    assert agent._trusted_server_state == {}


def test_turn_is_consumed_before_completion_and_keep_working_schedules_next():
    agent = FakeAgent()
    activate(agent, turns=3, turns_used=1)

    consume_ulw_turn(agent)
    ulw_keep_working(agent)

    assert agent._trusted_server_state['ulw']['turns_used'] == 2
    assert agent.current_session['plugin_state']['ulw']['turns_used'] == 2
    assert agent.input_calls == [ULW_CONTINUE_PROMPT]


def test_keep_working_at_max_with_continue_extends_bounded_lease():
    io = Mock()
    io.receive.return_value = {'action': 'continue', 'turns': 10}
    agent = FakeAgent(io=io)
    activate(agent, turns=5, turns_used=4)

    consume_ulw_turn(agent)
    ulw_keep_working(agent)

    assert agent._trusted_server_state['ulw']['turns'] == 15
    assert agent.input_calls == [ULW_CONTINUE_PROMPT]


def test_bound_hosted_checkpoint_exits_without_waiting_for_raw_continue():
    io = Mock()
    agent = FakeAgent(io=io)
    agent._session_id_authenticated = True
    activate(agent, turns=1, turns_used=0)

    consume_ulw_turn(agent)
    ulw_keep_working(agent)

    io.receive.assert_not_called()
    assert agent.current_session['mode'] == 'safe'
    assert agent._trusted_server_state == {'mode': 'safe'}
    assert agent.input_calls == []


@pytest.mark.parametrize('extend', [True, 0, -1, ULW_MAX_TURNS])
def test_keep_working_rejects_invalid_or_oversized_extension(extend):
    io = Mock()
    io.receive.return_value = {'action': 'continue', 'turns': extend}
    agent = FakeAgent(io=io)
    activate(agent, turns=5, turns_used=4)

    consume_ulw_turn(agent)
    ulw_keep_working(agent)

    assert agent.current_session['mode'] == 'safe'
    assert agent._trusted_server_state == {'mode': 'safe'}
    assert agent.input_calls == []


def test_keep_working_at_max_with_switch_mode_exits_to_plan():
    io = Mock()
    io.receive.return_value = {'action': 'switch_mode', 'mode': 'plan'}
    agent = FakeAgent(io=io)
    activate(agent, turns=2, turns_used=1)

    consume_ulw_turn(agent)
    ulw_keep_working(agent)

    assert agent.current_session['mode'] == 'plan'
    assert agent._trusted_server_state == {'mode': 'plan'}
    assert 'ulw' not in agent.current_session['plugin_state']
    assert agent.input_calls == []


def test_keep_working_at_max_with_unknown_action_exits_to_safe():
    io = Mock()
    io.receive.return_value = {'action': 'mystery'}
    agent = FakeAgent(io=io)
    activate(agent, turns=1)

    consume_ulw_turn(agent)
    ulw_keep_working(agent)

    assert agent.current_session['mode'] == 'safe'
    assert agent.input_calls == []


def test_keep_working_at_max_without_io_expires_lease():
    agent = FakeAgent(io=None)
    activate(agent, turns=1)

    consume_ulw_turn(agent)
    ulw_keep_working(agent)

    assert agent.input_calls == []
    assert agent.current_session['mode'] == 'safe'
    assert agent._trusted_server_state == {'mode': 'safe'}


# ---------- prompt state ----------

def test_poll_prompt_noop_without_io():
    agent = FakeAgent(io=None)
    activate(agent)

    poll_prompt_update(agent)

    assert 'prompt' not in agent._trusted_server_state['ulw']


def test_poll_prompt_stores_latest_in_trusted_state_and_ui_mirror():
    io = Mock()
    io.receive_all.return_value = [
        {'prompt': 'first goal'},
        {'prompt': 'final goal'},
    ]
    agent = FakeAgent(io=io)
    activate(agent)

    poll_prompt_update(agent)

    io.receive_all.assert_called_once_with('prompt_update')
    assert agent._trusted_server_state['ulw']['prompt'] == 'final goal'
    assert agent.current_session['plugin_state']['ulw']['prompt'] == 'final goal'


def test_inject_prompt_noop_when_no_prompt():
    agent = FakeAgent(messages=[{'role': 'system', 'content': 'base'}])
    activate(agent)

    inject_ulw_prompt(agent)

    assert agent.current_session['messages'][0]['content'] == 'base'


def test_inject_prompt_noop_when_no_system_message():
    agent = FakeAgent(messages=[{'role': 'user', 'content': 'hi'}])
    activate(agent, prompt='goal')

    inject_ulw_prompt(agent)

    assert agent.current_session['messages'][0]['content'] == 'hi'


def test_inject_prompt_appends_to_system_message():
    agent = FakeAgent(messages=[{'role': 'system', 'content': 'base instructions'}])
    activate(agent, prompt='finish the refactor')

    inject_ulw_prompt(agent)

    assert agent.current_session['messages'][0]['content'] == (
        'base instructions\n\n[Prompt]\nfinish the refactor'
    )


def test_inject_prompt_replaces_existing_prompt_section():
    agent = FakeAgent(messages=[
        {'role': 'system', 'content': 'base\n\n[Prompt]\nold goal'}
    ])
    activate(agent, prompt='new goal')

    inject_ulw_prompt(agent)

    assert agent.current_session['messages'][0]['content'] == (
        'base\n\n[Prompt]\nnew goal'
    )


def test_clearing_ulw_removes_injected_prompt_from_system_message():
    agent = FakeAgent(messages=[{
        'role': 'system',
        'content': 'base\n\n[Prompt]\nprivileged goal',
    }])
    activate(agent, prompt='privileged goal')

    clear_ulw_state(agent)

    assert agent.current_session['messages'][0]['content'] == 'base'


def test_consumed_turn_is_checkpointed_before_llm_work():
    checkpoints = []

    class Storage:
        def checkpoint(self, session, owner_address=None, server_state=None,
                       status='waiting_approval'):
            checkpoints.append({
                'session': dict(session),
                'owner_address': owner_address,
                'server_state': dict(server_state),
                'status': status,
            })

    agent = FakeAgent()
    agent.storage = Storage()
    agent._session_owner_address = '0xowner'
    agent.current_session['session_id'] = 'sid'
    activate(agent, turns=3, turns_used=1)
    checkpoints.clear()

    consume_ulw_turn(agent)

    assert agent._trusted_server_state['ulw']['turns_used'] == 2
    assert checkpoints[-1]['server_state']['ulw']['turns_used'] == 2
    assert checkpoints[-1]['owner_address'] == '0xowner'
    assert checkpoints[-1]['status'] == 'running'


def test_ulw_runs_maximum_lease_without_recursive_stack_growth():
    llm = MockLLM()
    agent = Agent(
        name='ulw-trampoline',
        llm=llm,
        plugins=[ulw],
        log=False,
        quiet=True,
    )
    agent._trusted_server_state = {
        'mode': 'ulw',
        'ulw': {'turns': ULW_MAX_TURNS, 'turns_used': 0},
    }

    result = agent.input('work')

    assert result == 'Mock response'
    assert llm.call_count == ULW_MAX_TURNS
    assert agent._trusted_server_state == {'mode': 'safe'}
    assert agent._input_driver_active is False
