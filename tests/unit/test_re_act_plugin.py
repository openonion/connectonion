"""Unit tests for connectonion/useful_plugins/re_act.py

Tests cover:
- plan_task: planning after user input
- evaluate_completion: evaluation after task completion
- Plugin registration with correct events
"""

import pytest
import importlib
from unittest.mock import Mock, patch, MagicMock

# Import the module directly to avoid __init__.py shadowing
re_act_module = importlib.import_module('connectonion.useful_plugins.re_act')
plan_task = re_act_module.plan_task
evaluate_completion = re_act_module.evaluate_completion
_summarize_trace = re_act_module._summarize_trace
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


class TestSummarizeTrace:
    """Tests for _summarize_trace helper function."""

    def test_summarize_empty_trace(self):
        """Test summarizing empty trace."""
        result = _summarize_trace([])
        assert result == 'No tools were used.'

    def test_summarize_successful_tool_calls(self):
        """Test summarizing successful tool executions."""
        trace = [
            {
                'type': 'tool_execution',
                'tool_name': 'search',
                'status': 'success',
                'result': 'Found 10 results for Python'
            },
            {
                'type': 'tool_execution',
                'tool_name': 'read_file',
                'status': 'success',
                'result': 'File contents here'
            }
        ]
        result = _summarize_trace(trace)
        assert 'search: Found 10 results' in result
        assert 'read_file: File contents' in result

    def test_summarize_failed_tool_calls(self):
        """Test summarizing failed tool executions."""
        trace = [
            {
                'type': 'tool_execution',
                'tool_name': 'write_file',
                'status': 'error',
                'error': 'Permission denied'
            }
        ]
        result = _summarize_trace(trace)
        assert 'write_file: failed' in result
        assert 'Permission denied' in result

    def test_summarize_ignores_non_tool_entries(self):
        """Test that non-tool entries are ignored."""
        trace = [
            {'type': 'llm_call', 'model': 'gpt-4'},
            {'type': 'user_input', 'prompt': 'Hello'},
            {
                'type': 'tool_execution',
                'tool_name': 'calc',
                'status': 'success',
                'result': '42'
            }
        ]
        result = _summarize_trace(trace)
        # Only tool execution should be in result
        assert 'calc: 42' in result
        assert 'llm_call' not in result
        assert 'user_input' not in result

    def test_summarize_truncates_long_results(self):
        """Test that long results are truncated."""
        trace = [
            {
                'type': 'tool_execution',
                'tool_name': 'fetch',
                'status': 'success',
                'result': 'A' * 200  # 200 character result
            }
        ]
        result = _summarize_trace(trace)
        # Should be truncated to ~100 chars
        assert len(result) < 150


class TestEvaluateCompletion:
    """Tests for evaluate_completion event handler."""

    def test_evaluate_completion_prints_evaluation(self):
        """Test that evaluate_completion prints evaluation result."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Find Python docs'
        agent.current_session['trace'] = [
            {
                'type': 'tool_execution',
                'tool_name': 'search',
                'status': 'success',
                'result': 'Found docs'
            }
        ]

        with patch.object(re_act_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Task completed successfully'

            evaluate_completion(agent)

            # Verify llm_do was called with context
            mock_llm_do.assert_called_once()
            call_args = mock_llm_do.call_args[0][0]
            assert 'Find Python docs' in call_args

            # Verify logger.print was called twice (evaluating + result)
            assert agent.logger.print.call_count == 2

    def test_evaluate_completion_skips_if_no_user_prompt(self):
        """Test that evaluate_completion skips if no user prompt."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = ''

        with patch.object(re_act_module, 'llm_do') as mock_llm_do:
            evaluate_completion(agent)

            mock_llm_do.assert_not_called()


class TestReActPlugin:
    """Tests for re_act plugin bundle."""

    def test_re_act_contains_three_handlers(self):
        """Test that re_act plugin has three handlers."""
        assert len(re_act) == 3

    def test_re_act_handlers_have_correct_event_types(self):
        """Test that handlers are registered for correct events."""
        # plan_task should be after_user_input
        assert hasattr(plan_task, '_event_type')
        assert plan_task._event_type == 'after_user_input'

        # evaluate_completion should be on_complete
        assert hasattr(evaluate_completion, '_event_type')
        assert evaluate_completion._event_type == 'on_complete'

    def test_plugin_integrates_with_agent(self):
        """Test that plugin can be registered with agent."""
        from connectonion import Agent
        from connectonion.llm import LLMResponse
        from connectonion.usage import TokenUsage

        # Create mock LLM
        mock_llm = Mock()
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
        assert 'on_complete' in agent.events
        assert 'after_tool' in agent.events  # from reflect
