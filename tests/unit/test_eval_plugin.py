"""Unit tests for connectonion/useful_plugins/eval.py

Tests cover:
- generate_expected: generating expected outcomes for tasks
- evaluate_completion: evaluating if tasks completed correctly
- _summarize_trace: summarizing tool execution trace
- Plugin registration with correct events
"""

import pytest
import importlib
from unittest.mock import Mock, patch

# Import the module directly to avoid __init__.py shadowing
eval_module = importlib.import_module('connectonion.useful_plugins.eval')
generate_expected = eval_module.generate_expected
evaluate_completion = eval_module.evaluate_completion
_summarize_trace = eval_module._summarize_trace
eval_plugin = eval_module.eval


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


class TestGenerateExpected:
    """Tests for generate_expected event handler."""

    def test_generate_expected_sets_expected(self):
        """Test that generate_expected sets expected outcome."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Search for Python docs'

        with patch.object(eval_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Should use search tool to find Python documentation'

            generate_expected(agent)

            mock_llm_do.assert_called_once()
            assert agent.current_session['expected'] == 'Should use search tool to find Python documentation'

    def test_generate_expected_skips_if_already_set(self):
        """Test that generate_expected skips if expected already set."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Search for Python docs'
        agent.current_session['expected'] = 'Already set by re_act'

        with patch.object(eval_module, 'llm_do') as mock_llm_do:
            generate_expected(agent)

            # llm_do should not be called
            mock_llm_do.assert_not_called()
            # Expected should remain unchanged
            assert agent.current_session['expected'] == 'Already set by re_act'

    def test_generate_expected_skips_if_no_user_prompt(self):
        """Test that generate_expected does nothing if no user prompt."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = ''

        with patch.object(eval_module, 'llm_do') as mock_llm_do:
            generate_expected(agent)

            mock_llm_do.assert_not_called()
            assert 'expected' not in agent.current_session

    def test_generate_expected_includes_tools_in_prompt(self):
        """Test that generate_expected includes available tools in prompt."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Do something'

        with patch.object(eval_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Expected outcome'

            generate_expected(agent)

            call_args = mock_llm_do.call_args[0][0]
            assert 'tool1, tool2' in call_args


class TestSummarizeTrace:
    """Tests for _summarize_trace helper function."""

    def test_summarize_empty_trace(self):
        """Test summarizing empty trace."""
        result = _summarize_trace([])
        assert result == "No tools were used."

    def test_summarize_successful_tool_execution(self):
        """Test summarizing successful tool execution."""
        trace = [{
            'type': 'tool_execution',
            'tool_name': 'search',
            'status': 'success',
            'result': 'Found 10 results'
        }]
        result = _summarize_trace(trace)
        assert '- search: Found 10 results' in result

    def test_summarize_failed_tool_execution(self):
        """Test summarizing failed tool execution."""
        trace = [{
            'type': 'tool_execution',
            'tool_name': 'api_call',
            'status': 'error',
            'error': 'Connection timeout'
        }]
        result = _summarize_trace(trace)
        assert '- api_call: failed (Connection timeout)' in result

    def test_summarize_multiple_tools(self):
        """Test summarizing multiple tool executions."""
        trace = [
            {'type': 'tool_execution', 'tool_name': 'search', 'status': 'success', 'result': 'Found results'},
            {'type': 'tool_execution', 'tool_name': 'read', 'status': 'success', 'result': 'File contents'},
        ]
        result = _summarize_trace(trace)
        assert '- search:' in result
        assert '- read:' in result

    def test_summarize_truncates_long_results(self):
        """Test that long results are truncated."""
        trace = [{
            'type': 'tool_execution',
            'tool_name': 'read',
            'status': 'success',
            'result': 'x' * 200  # Long result
        }]
        result = _summarize_trace(trace)
        # Result should be truncated to 100 chars
        assert len(result.split(': ')[1]) <= 100


class TestEvaluateCompletion:
    """Tests for evaluate_completion event handler."""

    def test_evaluate_completion_sets_evaluation(self):
        """Test that evaluate_completion sets evaluation result."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Search for Python docs'
        agent.current_session['result'] = 'Here are the Python docs'
        agent.current_session['trace'] = []

        with patch.object(eval_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Task completed successfully'

            evaluate_completion(agent)

            assert agent.current_session['evaluation'] == 'Task completed successfully'

    def test_evaluate_completion_includes_expected(self):
        """Test that evaluation includes expected outcome when available."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Do task'
        agent.current_session['expected'] = 'Should complete the task'
        agent.current_session['result'] = 'Done'
        agent.current_session['trace'] = []

        with patch.object(eval_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Complete'

            evaluate_completion(agent)

            call_args = mock_llm_do.call_args[0][0]
            assert 'Expected: Should complete the task' in call_args

    def test_evaluate_completion_includes_trace_summary(self):
        """Test that evaluation includes tool execution summary."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Search docs'
        agent.current_session['result'] = 'Found docs'
        agent.current_session['trace'] = [
            {'type': 'tool_execution', 'tool_name': 'search', 'status': 'success', 'result': 'Results'}
        ]

        with patch.object(eval_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Complete'

            evaluate_completion(agent)

            call_args = mock_llm_do.call_args[0][0]
            assert '- search:' in call_args

    def test_evaluate_completion_prints_status(self):
        """Test that evaluate_completion prints evaluation status."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Test task'
        agent.current_session['result'] = 'Result'
        agent.current_session['trace'] = []

        with patch.object(eval_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Task complete'

            evaluate_completion(agent)

            # Verify logger.print was called twice (evaluating... and result)
            assert agent.logger.print.call_count == 2

    def test_evaluate_completion_skips_if_no_user_prompt(self):
        """Test that evaluate_completion does nothing if no user prompt."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = ''

        with patch.object(eval_module, 'llm_do') as mock_llm_do:
            evaluate_completion(agent)

            mock_llm_do.assert_not_called()


class TestEvalPlugin:
    """Tests for eval plugin bundle."""

    def test_eval_contains_two_handlers(self):
        """Test that eval plugin has two handlers."""
        assert len(eval_plugin) == 2

    def test_eval_handlers_have_correct_event_types(self):
        """Test that handlers are registered for correct events."""
        # generate_expected should be after_user_input
        assert hasattr(generate_expected, '_event_type')
        assert generate_expected._event_type == 'after_user_input'

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
            plugins=[eval_plugin],
            log=False,
        )

        # Verify events are registered
        assert 'after_user_input' in agent.events
        assert 'on_complete' in agent.events
