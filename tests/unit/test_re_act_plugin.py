"""Unit tests for connectonion/useful_plugins/re_act.py

Tests cover:
- acknowledge_request: intent recognition after user input
- Plugin registration with correct events

Note: evaluate_completion tests are in test_eval_plugin.py
"""

import pytest
import importlib
from unittest.mock import Mock, patch, MagicMock

# Import the module directly to avoid __init__.py shadowing
re_act_module = importlib.import_module('connectonion.useful_plugins.re_act')
acknowledge_request = re_act_module.acknowledge_request
re_act = re_act_module.re_act


class FakeAgent:
    """Fake agent for testing plugins."""

    def __init__(self):
        self.current_session = {
            'messages': [],
            'trace': [],
            'user_prompt': 'test prompt',
            'iteration': 1,
        }
        self.tools = Mock()
        self.tools.names.return_value = ['tool1', 'tool2']
        self.logger = Mock()
        self._trace_id = 0

    def _record_trace(self, entry):
        if 'id' not in entry:
            self._trace_id += 1
            entry['id'] = str(self._trace_id)
        self.current_session['trace'].append(entry)


class TestAcknowledgeRequest:
    """Tests for acknowledge_request event handler."""

    def test_acknowledge_request_records_intent_and_message(self):
        """Test that acknowledge_request records intent and adds message to session."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Search for Python docs'

        with patch.object(re_act_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Looking up Python documentation'

            acknowledge_request(agent)

            # Verify llm_do was called
            mock_llm_do.assert_called_once()
            call_args = mock_llm_do.call_args

            # Check prompt contains user request
            assert 'Search for Python docs' in call_args[0][0]

            # Verify intent was recorded
            assert agent.current_session['intent'] == 'Looking up Python documentation'

            # Verify message was added to session
            assert len(agent.current_session['messages']) == 1
            msg = agent.current_session['messages'][0]
            assert msg['role'] == 'assistant'
            assert msg['content'] == 'Looking up Python documentation'

    def test_acknowledge_request_prints_status_with_model(self):
        """Test that acknowledge_request prints understanding status with model name."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'test'

        with patch.object(re_act_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Got it'

            acknowledge_request(agent)

            # Verify logger.print was called with understanding message and model
            agent.logger.print.assert_called_once()
            call_args = agent.logger.print.call_args[0][0]
            assert 'understanding' in call_args.lower()
            assert 'gemini' in call_args.lower()  # Model name should be shown

    def test_acknowledge_request_records_trace(self):
        """Test that acknowledge_request records trace entry."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'test'

        with patch.object(re_act_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Got it'

            acknowledge_request(agent)

            # Verify trace was recorded
            assert len(agent.current_session['trace']) == 1
            trace = agent.current_session['trace'][0]
            assert trace['type'] == 'thinking'
            assert trace['kind'] == 'intent'
            assert trace['content'] == 'Got it'

    def test_acknowledge_request_skips_if_no_user_prompt(self):
        """Test that acknowledge_request does nothing if no user prompt."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = ''

        with patch.object(re_act_module, 'llm_do') as mock_llm_do:
            acknowledge_request(agent)

            # llm_do should not be called
            mock_llm_do.assert_not_called()
            assert 'intent' not in agent.current_session


class TestReActPlugin:
    """Tests for re_act plugin bundle."""

    def test_re_act_contains_two_handlers(self):
        """Test that re_act plugin has two handlers (acknowledge + reflect)."""
        assert len(re_act) == 2

    def test_re_act_handlers_have_correct_event_types(self):
        """Test that handlers are registered for correct events."""
        from connectonion.useful_plugins.re_act import acknowledge_request

        # acknowledge_request should be after_user_input
        assert hasattr(acknowledge_request, '_event_type')
        assert acknowledge_request._event_type == 'after_user_input'

        # reflect should be after_tools
        from connectonion.useful_events_handlers.reflect import reflect
        assert hasattr(reflect, '_event_type')
        assert reflect._event_type == 'after_tools'

    def test_plugin_integrates_with_agent(self):
        """Test that plugin can be registered with agent."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

        # Create mock LLM
        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="Test response",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        # Should not raise
        agent = Agent(
            "test",
            llm=mock_llm,
            plugins=[re_act],
            log=False,
        )

        # Verify events are registered
        assert 'after_user_input' in agent.events
        assert 'after_tools' in agent.events  # from reflect
