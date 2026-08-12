"""Unit tests for connectonion/useful_plugins/full_access.py"""

from unittest.mock import Mock

import pytest

from connectonion import Agent
from connectonion.core.llm import LLMResponse
from connectonion.core.usage import TokenUsage
from connectonion.useful_plugins.full_access import (
    FULL_ACCESS_CONTINUE_PROMPT,
    FULL_ACCESS_DEFAULT_TURNS,
    YOLO_DEFAULT_TURNS,
    enable_yolo,
    full_access_keep_working,
    handle_full_access_permission_profile_change,
    handle_yolo_mode_change,
    inject_full_access_prompt,
    poll_prompt_update,
    yolo,
)
from connectonion.useful_plugins.skills import skills
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

    def input(self, text):
        self.input_calls.append(text)


# ---------- handle_full_access_permission_profile_change ----------

def test_permission_profile_change_defaults_to_100_turns():
    agent = FakeAgent()
    handle_full_access_permission_profile_change(agent)
    assert agent.current_session['mode'] == ':danger-full-access'
    assert agent.current_session['full_access_turns'] == FULL_ACCESS_DEFAULT_TURNS
    assert agent.current_session['full_access_turns_used'] == 0
    assert agent.current_session['skip_tool_approval'] is True


def test_permission_profile_change_uses_explicit_turns():
    agent = FakeAgent()
    handle_full_access_permission_profile_change(agent, turns=5)
    assert agent.current_session['full_access_turns'] == 5


@pytest.mark.parametrize('turns', [0, -1, True, 1.5, '5'])
def test_permission_profile_change_rejects_malformed_turn_budgets_without_granting(turns):
    agent = FakeAgent(mode=':read-only')

    with pytest.raises(ValueError, match='positive integer'):
        handle_full_access_permission_profile_change(agent, turns=turns)

    assert agent.current_session['mode'] == ':read-only'
    assert 'skip_tool_approval' not in agent.current_session


def test_permission_profile_change_notifies_io_when_present():
    io = Mock()
    agent = FakeAgent(io=io)
    handle_full_access_permission_profile_change(agent, turns=7)
    io.send.assert_called_once_with(
        {'type': 'mode_changed', 'mode': ':danger-full-access', 'triggered_by': 'user'}
    )


def test_permission_profile_change_skips_notify_without_io():
    agent = FakeAgent(io=None)
    handle_full_access_permission_profile_change(agent)  # should not raise


def test_yolo_public_api_uses_full_access_compatibility_state():
    agent = FakeAgent()

    handle_yolo_mode_change(agent, turns=4)

    assert YOLO_DEFAULT_TURNS == FULL_ACCESS_DEFAULT_TURNS
    assert agent.current_session['mode'] == ':danger-full-access'
    assert agent.current_session['full_access_turns'] == 4
    assert agent.current_session['skip_tool_approval'] is True
    assert yolo


def test_enable_yolo_before_first_input_runs_one_bounded_turn(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    skill_dir = tmp_path / '.claude' / 'skills' / 'deploy-oo-chat'
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text(
        '---\n'
        'name: deploy-oo-chat\n'
        'description: Deploy oo-chat\n'
        'tools:\n'
        '  - Bash(pytest *)\n'
        '---\n'
        'Run the deployment checks without deploying.',
        encoding='utf-8',
    )
    llm = MockLLM(responses=[
        LLMResponse(
            content='done',
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])
    agent = Agent(
        name='yolo-skill',
        llm=llm,
        plugins=[skills, yolo],
        log=False,
        quiet=True,
    )

    enable_yolo(agent, turns=1)
    result = agent.input('/deploy-oo-chat')

    assert result == 'done'
    user_message = next(
        message
        for message in llm.last_call['messages']
        if message['role'] == 'user'
    )
    assert user_message['content'] == (
        'Run the deployment checks without deploying.'
    )
    assert agent.current_session['mode'] == ':read-only'
    assert 'skip_tool_approval' not in agent.current_session
    assert 'full_access_turns' not in agent.current_session
    assert 'full_access_prompt' not in agent.current_session
    assert 'full_access_turns_used' not in agent.current_session


def test_plain_full_access_plugin_does_not_enable_yolo_implicitly():
    llm = MockLLM(responses=[
        LLMResponse(
            content='done',
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])
    agent = Agent(
        name='safe-by-default',
        llm=llm,
        plugins=[yolo],
        log=False,
        quiet=True,
    )

    agent.input('hello')

    assert 'mode' not in agent.current_session
    assert 'skip_tool_approval' not in agent.current_session


def test_configured_yolo_runs_after_hosted_session_restore_then_expires():
    llm = MockLLM(responses=[
        LLMResponse(
            content='done',
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])
    agent = Agent(
        name='hosted-yolo',
        llm=llm,
        plugins=[yolo],
        log=False,
        quiet=True,
    )
    enable_yolo(agent, turns=1)

    agent.input(
        'continue',
        session={
            'session_id': 'session-1',
            'messages': [{'role': 'system', 'content': 'system'}],
            'trace': [],
            'turn': 0,
        },
    )

    assert agent.current_session['mode'] == ':read-only'
    assert 'skip_tool_approval' not in agent.current_session
    assert 'full_access_turns' not in agent.current_session
    assert 'full_access_turns_used' not in agent.current_session


def test_explicit_yolo_rearms_then_expires_an_exhausted_restored_session():
    llm = MockLLM(responses=[
        LLMResponse(
            content='done',
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])
    agent = Agent(
        name='resumed-yolo',
        llm=llm,
        plugins=[yolo],
        log=False,
        quiet=True,
    )
    enable_yolo(agent, turns=2)

    agent.input(
        'continue',
        session={
            'session_id': 'session-1',
            'messages': [{'role': 'system', 'content': 'system'}],
            'trace': [],
            'turn': 1,
            'mode': ':danger-full-access',
            'full_access_turns': 1,
            'full_access_turns_used': 1,
            'skip_tool_approval': True,
        },
    )

    assert agent.current_session['mode'] == ':read-only'
    assert 'full_access_turns' not in agent.current_session
    assert 'full_access_turns_used' not in agent.current_session
    assert 'skip_tool_approval' not in agent.current_session
    assert llm.call_count == 2


# ---------- full_access_keep_working ----------

def test_keep_working_noop_when_mode_is_not_full_access():
    agent = FakeAgent(mode=':read-only')
    full_access_keep_working(agent)
    assert agent.input_calls == []
    assert 'full_access_turns_used' not in agent.current_session


def test_keep_working_increments_turns_and_calls_input_below_max():
    agent = FakeAgent(mode=':danger-full-access')
    agent.current_session['full_access_turns'] = 3
    agent.current_session['full_access_turns_used'] = 1
    full_access_keep_working(agent)
    assert agent.current_session['full_access_turns_used'] == 2
    assert agent.input_calls == [FULL_ACCESS_CONTINUE_PROMPT]


def test_keep_working_at_max_with_continue_action_extends_and_falls_through():
    io = Mock()
    io.receive.return_value = {'action': 'continue', 'turns': 10}
    agent = FakeAgent(io=io, mode=':danger-full-access')
    agent.current_session['full_access_turns'] = 5
    agent.current_session['full_access_turns_used'] = 4  # +1 = 5 hits max
    full_access_keep_working(agent)
    assert agent.current_session['full_access_turns'] == 15  # 5 + 10
    assert agent.input_calls == [FULL_ACCESS_CONTINUE_PROMPT]  # falls through


def test_keep_working_at_max_with_switch_mode_exits_to_new_mode():
    io = Mock()
    io.receive.return_value = {'action': 'switch_mode', 'mode': ':workspace'}
    agent = FakeAgent(io=io, mode=':danger-full-access')
    agent.current_session['full_access_turns'] = 2
    agent.current_session['full_access_turns_used'] = 1
    full_access_keep_working(agent)
    assert agent.current_session['mode'] == ':workspace'
    assert 'skip_tool_approval' not in agent.current_session
    assert 'full_access_turns' not in agent.current_session
    assert agent.input_calls == []


def test_keep_working_at_max_with_unknown_action_exits_to_default():
    io = Mock()
    io.receive.return_value = {'action': 'mystery'}
    agent = FakeAgent(io=io, mode=':danger-full-access')
    agent.current_session['full_access_turns'] = 1
    agent.current_session['full_access_turns_used'] = 0
    full_access_keep_working(agent)
    assert agent.current_session['mode'] == ':read-only'
    assert agent.input_calls == []


@pytest.mark.parametrize('mode', [':danger-full-access', 'ulw', 'unknown'])
def test_checkpoint_cannot_reenter_or_invent_an_approval_mode(mode):
    io = Mock()
    io.receive.return_value = {'action': 'switch_mode', 'mode': mode}
    agent = FakeAgent(io=io, mode=':danger-full-access')
    agent.current_session['full_access_turns'] = 1
    agent.current_session['full_access_turns_used'] = 0
    agent.current_session['skip_tool_approval'] = True

    full_access_keep_working(agent)

    assert agent.current_session['mode'] == ':read-only'
    assert 'skip_tool_approval' not in agent.current_session


@pytest.mark.parametrize('turns', [0, -1, True, 1.5, '5'])
def test_checkpoint_rejects_malformed_extensions_and_exits_default(turns):
    io = Mock()
    io.receive.return_value = {'action': 'continue', 'turns': turns}
    agent = FakeAgent(io=io, mode=':danger-full-access')
    agent.current_session['full_access_turns'] = 1
    agent.current_session['full_access_turns_used'] = 0
    agent.current_session['skip_tool_approval'] = True

    full_access_keep_working(agent)

    assert agent.current_session['mode'] == ':read-only'
    assert 'skip_tool_approval' not in agent.current_session
    assert agent.input_calls == []


def test_keep_working_at_max_without_io_removes_the_expired_grant():
    agent = FakeAgent(io=None, mode=':danger-full-access')
    agent.current_session['full_access_turns'] = 1
    agent.current_session['full_access_turns_used'] = 0
    full_access_keep_working(agent)
    assert agent.input_calls == []
    assert agent.current_session['mode'] == ':read-only'
    assert 'skip_tool_approval' not in agent.current_session


@pytest.mark.parametrize(
    ('turns', 'used'),
    [(0, 0), (-1, 0), (True, 0), (1, -1), (1, True), (1, 1)],
)
def test_keep_working_rejects_malformed_or_exhausted_restored_state(turns, used):
    agent = FakeAgent(mode=':danger-full-access')
    agent.current_session['full_access_turns'] = turns
    agent.current_session['full_access_turns_used'] = used
    agent.current_session['skip_tool_approval'] = True

    full_access_keep_working(agent)

    assert agent.current_session['mode'] == ':read-only'
    assert 'skip_tool_approval' not in agent.current_session
    assert agent.input_calls == []


def test_host_bounded_full_access_checkpoint_exits_default_without_mailbox_extension():
    io = Mock()
    io.receive.return_value = {'action': 'continue', 'turns': 999999}
    agent = FakeAgent(io=io, mode=':danger-full-access')
    agent._host_full_access_turns_ceiling = 5
    agent.current_session['full_access_turns'] = 5
    agent.current_session['full_access_turns_used'] = 4
    agent.current_session['skip_tool_approval'] = True

    full_access_keep_working(agent)

    io.receive.assert_not_called()
    assert agent.current_session['mode'] == ':read-only'
    assert not {
        'full_access_turns', 'full_access_turns_used', 'skip_tool_approval'
    } & agent.current_session.keys()
    assert agent.input_calls == []


# ---------- poll_prompt_update ----------

def test_poll_prompt_noop_without_io():
    agent = FakeAgent(io=None)
    poll_prompt_update(agent)
    assert 'full_access_prompt' not in agent.current_session


def test_poll_prompt_stores_latest_from_receive_all():
    io = Mock()
    io.receive_all.return_value = [
        {'prompt': 'first goal'},
        {'prompt': 'final goal'},
    ]
    agent = FakeAgent(io=io)
    poll_prompt_update(agent)
    io.receive_all.assert_called_once_with('prompt_update')
    assert agent.current_session['full_access_prompt'] == 'final goal'


# ---------- inject_full_access_prompt ----------

def test_inject_prompt_noop_when_no_prompt():
    agent = FakeAgent(messages=[{'role': 'system', 'content': 'base'}])
    inject_full_access_prompt(agent)
    assert agent.current_session['messages'][0]['content'] == 'base'


def test_inject_prompt_noop_when_no_system_message():
    agent = FakeAgent(messages=[{'role': 'user', 'content': 'hi'}])
    agent.current_session['full_access_prompt'] = 'goal'
    inject_full_access_prompt(agent)
    assert agent.current_session['messages'][0]['content'] == 'hi'


def test_inject_prompt_appends_to_system_message():
    agent = FakeAgent(messages=[{'role': 'system', 'content': 'base instructions'}])
    agent.current_session['full_access_prompt'] = 'finish the refactor'
    inject_full_access_prompt(agent)
    assert agent.current_session['messages'][0]['content'] == (
        'base instructions\n\n[Prompt]\nfinish the refactor'
    )


def test_inject_prompt_replaces_existing_prompt_section():
    agent = FakeAgent(messages=[
        {'role': 'system', 'content': 'base\n\n[Prompt]\nold goal'}
    ])
    agent.current_session['full_access_prompt'] = 'new goal'
    inject_full_access_prompt(agent)
    assert agent.current_session['messages'][0]['content'] == 'base\n\n[Prompt]\nnew goal'
