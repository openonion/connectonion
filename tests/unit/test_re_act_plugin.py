"""Unit tests for connectonion/useful_plugins/re_act.py

Tests cover:
- plan_task: planning after user input
- Plugin registration with correct events

Note: evaluate_completion tests are in test_eval_plugin.py
"""

import pytest
import importlib
from unittest.mock import Mock, patch, MagicMock

# Import the module directly to avoid __init__.py shadowing
re_act_module = importlib.import_module('connectonion.useful_plugins.re_act')
plan_task = re_act_module.plan_task
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


class TestPlanTask:
    """Tests for plan_task event handler."""

    def test_plan_task_adds_plan_message(self):
        """Test that plan_task adds a planning message to session."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Search for Python docs'

        with patch.object(re_act_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Use search tool to find docs'

            plan_task(agent)

            # Verify llm_do was called
            mock_llm_do.assert_called_once()
            call_args = mock_llm_do.call_args

            # Check prompt contains user request and tools
            assert 'Search for Python docs' in call_args[0][0]
            assert 'tool1, tool2' in call_args[0][0]

            # Verify plan message was added
            assert len(agent.current_session['messages']) == 1
            msg = agent.current_session['messages'][0]
            assert msg['role'] == 'assistant'
            assert 'Use search tool to find docs' in msg['content']

    def test_plan_task_prints_planning_status(self):
        """Test that plan_task prints planning status."""
        agent = FakeAgent()

        with patch.object(re_act_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Plan'

            plan_task(agent)

            # Verify logger.print was called with planning message
            agent.logger.print.assert_called_once()
            call_args = agent.logger.print.call_args[0][0]
            assert 'planning' in call_args.lower()

    def test_plan_task_skips_if_no_user_prompt(self):
        """Test that plan_task does nothing if no user prompt."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = ''

        with patch.object(re_act_module, 'llm_do') as mock_llm_do:
            plan_task(agent)

            # llm_do should not be called
            mock_llm_do.assert_not_called()
            assert len(agent.current_session['messages']) == 0

    def test_plan_task_handles_no_tools(self):
        """Test plan_task when agent has no tools."""
        agent = FakeAgent()
        agent.tools.names.return_value = []

        with patch.object(re_act_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'No tools available'

            plan_task(agent)

            # Check prompt mentions no tools
            call_args = mock_llm_do.call_args[0][0]
            assert 'no tools' in call_args


class TestReActPlugin:
    """Tests for re_act plugin bundle."""

    def test_re_act_contains_two_handlers(self):
        """Test that re_act plugin has two handlers (plan + reflect)."""
        assert len(re_act) == 2

    def test_re_act_handlers_have_correct_event_types(self):
        """Test that handlers are registered for correct events."""
        # plan_task should be after_user_input
        assert hasattr(plan_task, '_event_type')
        assert plan_task._event_type == 'after_user_input'

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
