"""Unit tests for connectonion/useful_plugins/ulw.py"""

import pytest
from unittest.mock import Mock

from connectonion import Agent
from connectonion.core.llm import LLMResponse
from connectonion.core.usage import TokenUsage
from connectonion.useful_plugins.skills import skills
from connectonion.useful_plugins.ulw import (
    ULW_CONTINUE_PROMPT,
    ULW_DEFAULT_TURNS,
    YOLO_DEFAULT_TURNS,
    enable_yolo,
    handle_ulw_mode_change,
    handle_yolo_mode_change,
    inject_ulw_prompt,
    poll_prompt_update,
    yolo,
    ulw_keep_working,
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

    def input(self, text):
        self.input_calls.append(text)

    def _queue_input(self, text):
        """Mirrors Agent._queue_input: continuations are queued, not recursed.

        Recorded in the same list so the existing assertions still describe
        'the plugin asked for another turn' — which is the behaviour they were
        always about, independent of how the turn is dispatched.
        """
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


def test_yolo_public_api_uses_ulw_compatibility_state():
    agent = FakeAgent()

    handle_yolo_mode_change(agent, turns=4)

    assert YOLO_DEFAULT_TURNS == ULW_DEFAULT_TURNS
    assert agent.current_session['mode'] == 'ulw'
    assert agent.current_session['ulw_turns'] == 4
    assert agent.current_session['skip_tool_approval'] is True
    assert yolo


def test_enable_yolo_before_first_input_activates_on_the_first_turn(tmp_path, monkeypatch):
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
    assert agent.current_session['mode'] == 'ulw'
    assert agent.current_session['skip_tool_approval'] is True
    assert agent.current_session['ulw_turns'] == 1
    assert agent.current_session['ulw_turns_used'] == 1


def test_plain_ulw_plugin_does_not_enable_yolo_implicitly():
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


def test_configured_yolo_activates_after_hosted_session_restore():
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

    assert agent.current_session['mode'] == 'ulw'
    assert agent.current_session['skip_tool_approval'] is True
    assert agent.current_session['ulw_turns'] == 1
    assert agent.current_session['ulw_turns_used'] == 1


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


def _text(content):
    """A minimal terminal LLM response (no tool calls)."""
    return LLMResponse(content=content, tool_calls=[], raw_response={}, usage=TokenUsage())


class TestContinuationQueueSafety:
    """The queue replaced recursion, and inherited none of its accidental limits."""

    def test_a_callers_max_iterations_bounds_the_continuations_too(self):
        """Recursion passed the caller's bound only to the first turn.

        A caller that says max_iterations=3 means the whole request. Letting
        queued turns fall back to the agent's default (100 in co ai) would
        silently ignore the bound the caller asked for.
        """
        from connectonion import Agent
        from tests.utils.mock_helpers import MockLLM

        seen = []
        agent = Agent("q", llm=MockLLM(responses=[_text("a"), _text("b")]), log=False, quiet=True)
        original = agent._run_input_turn

        def spy(prompt, *, max_iterations, **kw):
            seen.append(max_iterations)
            if len(seen) == 1:
                agent._queue_input("continue")
            return original(prompt, max_iterations=max_iterations, **kw)

        agent._run_input_turn = spy
        agent.input("go", max_iterations=3)

        assert seen == [3, 3], f"continuation ran with {seen[1:]}, not the caller's bound"

    def test_a_plugin_that_never_stops_queueing_raises_instead_of_hanging(self):
        """Recursion was bounded, crudely, by Python's recursion limit.

        A queue has no such backstop: without a cap, a misbehaving plugin spins
        forever with no error and no output.
        """
        import connectonion.core.agent as agent_mod
        from connectonion import Agent
        from tests.utils.mock_helpers import MockLLM

        agent = Agent("q", llm=MockLLM(responses=[_text("x") for _ in range(50)]), log=False, quiet=True)
        original = agent._run_input_turn

        def never_stops(prompt, **kw):
            agent._queue_input("again")
            return original(prompt, **kw)

        agent._run_input_turn = never_stops
        limit = agent_mod.MAX_QUEUED_CONTINUATIONS
        agent_mod.MAX_QUEUED_CONTINUATIONS = 3
        try:
            with pytest.raises(RuntimeError, match="not terminating"):
                agent.input("go")
        finally:
            agent_mod.MAX_QUEUED_CONTINUATIONS = limit

    def test_a_failed_turn_does_not_leak_continuations_into_the_next_request(self):
        from connectonion import Agent
        from tests.utils.mock_helpers import MockLLM

        agent = Agent("q", llm=MockLLM(responses=[_text("a")]), log=False, quiet=True)
        agent._queue_input("stale")
        original = agent._run_input_turn

        def boom(prompt, **kw):
            raise RuntimeError("turn failed")

        agent._run_input_turn = boom
        with pytest.raises(RuntimeError, match="turn failed"):
            agent.input("go")

        assert agent._pending_inputs == []
