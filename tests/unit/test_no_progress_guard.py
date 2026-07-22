"""Unit tests for connectonion/useful_plugins/no_progress_guard.py

Tests cover:
- _last_tool_signature: signature ignores call ids, reads the most recent call
- no_progress_guard: stops on repeated identical calls, not on varying calls
"""

from unittest.mock import Mock

from connectonion.useful_plugins.no_progress_guard import (
    no_progress_guard,
    _last_tool_signature,
)


class FakeAgent:
    def __init__(self):
        self.current_session = {'messages': []}
        self.logger = Mock()


def _assistant_call(name, arguments):
    return {
        'role': 'assistant',
        'tool_calls': [
            {'id': 'irrelevant', 'type': 'function',
             'function': {'name': name, 'arguments': arguments}}
        ],
    }


class TestLastToolSignature:
    def test_ignores_call_id(self):
        a = [{'role': 'assistant', 'tool_calls': [
            {'id': '1', 'function': {'name': 'f', 'arguments': '{}'}}]}]
        b = [{'role': 'assistant', 'tool_calls': [
            {'id': '2', 'function': {'name': 'f', 'arguments': '{}'}}]}]
        assert _last_tool_signature(a) == _last_tool_signature(b)

    def test_reads_most_recent_call_past_tool_and_user_messages(self):
        messages = [
            _assistant_call('old', '{}'),
            {'role': 'tool', 'content': 'x', 'tool_call_id': 'irrelevant'},
            _assistant_call('new', '{}'),
            {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'd'}}]},
        ]
        assert 'new' in _last_tool_signature(messages)
        assert 'old' not in _last_tool_signature(messages)

    def test_none_when_no_tool_calls(self):
        assert _last_tool_signature([{'role': 'user', 'content': 'hi'}]) is None

    def test_final_text_does_not_reuse_previous_tool_call(self):
        messages = [
            _assistant_call('ping', '{}'),
            {'role': 'tool', 'content': 'pong', 'tool_call_id': 'irrelevant'},
            {'role': 'assistant', 'content': 'DONE'},
        ]

        assert _last_tool_signature(messages) is None


class TestNoProgressGuard:
    def test_stops_after_repeated_identical_calls(self):
        agent = FakeAgent()
        check = no_progress_guard(max_repeats=3)[0]

        agent.current_session['messages'].append(_assistant_call('take_screenshot', '{}'))
        check(agent)
        assert not agent.current_session.get('stop_signal')

        agent.current_session['messages'].append(_assistant_call('take_screenshot', '{}'))
        check(agent)
        assert not agent.current_session.get('stop_signal')

        agent.current_session['messages'].append(_assistant_call('take_screenshot', '{}'))
        check(agent)
        assert agent.current_session.get('stop_signal') is True

    def test_does_not_stop_when_calls_vary(self):
        agent = FakeAgent()
        check = no_progress_guard(max_repeats=3)[0]
        for selector in ['#a', '#b', '#c', '#d', '#e']:
            agent.current_session['messages'].append(
                _assistant_call('click_element_by_selector', f'{{"selector": "{selector}"}}'))
            check(agent)
            assert not agent.current_session.get('stop_signal')

    def test_counter_resets_after_a_different_call(self):
        agent = FakeAgent()
        check = no_progress_guard(max_repeats=3)[0]
        # two identical, then a different one resets the streak, then two identical again
        for name in ['scroll', 'scroll', 'screenshot', 'scroll', 'scroll']:
            agent.current_session['messages'].append(_assistant_call(name, '{}'))
            check(agent)
        assert not agent.current_session.get('stop_signal')

    def test_threshold_is_configurable(self):
        agent = FakeAgent()
        check = no_progress_guard(max_repeats=2)[0]
        agent.current_session['messages'].append(_assistant_call('f', '{}'))
        check(agent)
        assert not agent.current_session.get('stop_signal')
        agent.current_session['messages'].append(_assistant_call('f', '{}'))
        check(agent)
        assert agent.current_session.get('stop_signal') is True

    def test_counter_resets_at_turn_boundary(self):
        """The streak is per-turn. After a halt, the next user turn (after_user_input)
        clears the counter, so the turn's first identical call does not immediately
        re-halt and unrelated turns don't accumulate into a false stop."""
        agent = FakeAgent()
        check, reset = no_progress_guard(max_repeats=3)

        # Turn 1: three identical calls halt the loop.
        for _ in range(3):
            agent.current_session['messages'].append(_assistant_call('take_screenshot', '{}'))
            check(agent)
        assert agent.current_session.get('stop_signal') is True

        # New user turn: the loop popped stop_signal; after_user_input clears the streak.
        agent.current_session.pop('stop_signal', None)
        reset(agent)

        # Turn 2: one more identical call must NOT immediately re-halt.
        agent.current_session['messages'].append(_assistant_call('take_screenshot', '{}'))
        check(agent)
        assert not agent.current_session.get('stop_signal')

    def test_plugin_registers_after_iteration(self):
        from connectonion import Agent
        from tests.utils.mock_helpers import MockLLM
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

        mock_llm = MockLLM(responses=[
            LLMResponse(content="done", tool_calls=[], raw_response=None, usage=TokenUsage())
        ])
        agent = Agent("test", llm=mock_llm, plugins=[no_progress_guard()], log=False)
        assert 'after_iteration' in agent.events
