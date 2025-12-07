"""Unit tests for connectonion/useful_events_handlers/reflect.py

Tests cover:
- reflect: reflection after tool execution
- _compress_messages: message compression helper
- Event registration
"""

import pytest
import importlib
from unittest.mock import Mock, patch

# Import the module directly
reflect_module = importlib.import_module('connectonion.useful_events_handlers.reflect')
reflect = reflect_module.reflect
_compress_messages = reflect_module._compress_messages


class FakeAgent:
    """Fake agent for testing handlers."""

    def __init__(self):
        self.current_session = {
            'messages': [],
            'trace': [],
            'user_prompt': 'test prompt',
            'iteration': 1,
        }
        self.logger = Mock()


class TestCompressMessages:
    """Tests for _compress_messages helper function."""

    def test_compress_user_messages(self):
        """Test that user messages are kept full."""
        messages = [
            {'role': 'user', 'content': 'This is a full user message that should be preserved'}
        ]
        result = _compress_messages(messages)
        assert 'USER: This is a full user message that should be preserved' in result

    def test_compress_assistant_tool_calls(self):
        """Test that assistant tool calls are formatted properly."""
        messages = [
            {
                'role': 'assistant',
                'tool_calls': [
                    {
                        'function': {
                            'name': 'search',
                            'arguments': '{"query": "python"}'
                        }
                    }
                ]
            }
        ]
        result = _compress_messages(messages)
        assert 'ASSISTANT: search({"query": "python"})' in result

    def test_compress_assistant_text(self):
        """Test that assistant text responses are kept full."""
        messages = [
            {'role': 'assistant', 'content': 'Here is the answer to your question'}
        ]
        result = _compress_messages(messages)
        assert 'ASSISTANT: Here is the answer to your question' in result

    def test_compress_tool_results_truncated(self):
        """Test that tool results are truncated."""
        long_result = 'A' * 200
        messages = [
            {'role': 'tool', 'content': long_result}
        ]
        result = _compress_messages(messages, tool_result_limit=50)
        assert 'TOOL:' in result
        assert '...' in result
        # Should be truncated
        assert len(result) < len(long_result)

    def test_compress_multiple_messages(self):
        """Test compressing a conversation."""
        messages = [
            {'role': 'user', 'content': 'Search for Python'},
            {
                'role': 'assistant',
                'tool_calls': [
                    {'function': {'name': 'search', 'arguments': '{"q": "Python"}'}}
                ]
            },
            {'role': 'tool', 'content': 'Found 10 results'},
            {'role': 'assistant', 'content': 'Here are the results'}
        ]
        result = _compress_messages(messages)

        lines = result.split('\n')
        assert len(lines) == 4
        assert 'USER: Search for Python' in result
        assert 'ASSISTANT: search' in result
        assert 'TOOL: Found 10 results' in result
        assert 'ASSISTANT: Here are the results' in result


class TestReflect:
    """Tests for reflect event handler."""

    def test_reflect_adds_reasoning_message(self):
        """Test that reflect adds a reasoning message after tool execution."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Find Python docs'
        agent.current_session['trace'] = [
            {
                'type': 'tool_execution',
                'tool_name': 'search',
                'arguments': {'query': 'python'},
                'status': 'success',
                'result': 'Found Python documentation'
            }
        ]
        agent.current_session['messages'] = [
            {'role': 'user', 'content': 'Find Python docs'}
        ]

        with patch.object(reflect_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Good progress, now summarize the results'

            reflect(agent)

            # Verify llm_do was called
            mock_llm_do.assert_called_once()

            # Verify reasoning message was added
            assert len(agent.current_session['messages']) == 2
            msg = agent.current_session['messages'][1]
            assert msg['role'] == 'assistant'
            assert 'Good progress' in msg['content']

    def test_reflect_prints_status(self):
        """Test that reflect prints reflecting status."""
        agent = FakeAgent()
        agent.current_session['trace'] = [
            {
                'type': 'tool_execution',
                'tool_name': 'calc',
                'arguments': {},
                'status': 'success',
                'result': '42'
            }
        ]

        with patch.object(reflect_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Calculation done'

            reflect(agent)

            # Verify logger.print was called
            agent.logger.print.assert_called_once()
            call_args = agent.logger.print.call_args[0][0]
            assert 'reflecting' in call_args.lower()

    def test_reflect_skips_non_tool_trace(self):
        """Test that reflect skips if last trace is not tool execution."""
        agent = FakeAgent()
        agent.current_session['trace'] = [
            {'type': 'llm_call', 'model': 'gpt-4'}
        ]

        with patch.object(reflect_module, 'llm_do') as mock_llm_do:
            reflect(agent)

            mock_llm_do.assert_not_called()
            assert len(agent.current_session['messages']) == 0

    def test_reflect_handles_error_status(self):
        """Test reflect with failed tool execution."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Write file'
        agent.current_session['trace'] = [
            {
                'type': 'tool_execution',
                'tool_name': 'write_file',
                'arguments': {'path': '/etc/passwd'},
                'status': 'error',
                'error': 'Permission denied'
            }
        ]

        with patch.object(reflect_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Need to try different path'

            reflect(agent)

            # Verify error was passed to LLM
            call_args = mock_llm_do.call_args[0][0]
            assert 'Error' in call_args
            assert 'Permission denied' in call_args

    def test_reflect_includes_conversation_context(self):
        """Test that reflect includes compressed conversation context."""
        agent = FakeAgent()
        agent.current_session['user_prompt'] = 'Search and summarize'
        agent.current_session['messages'] = [
            {'role': 'user', 'content': 'Search and summarize Python'},
            {'role': 'tool', 'content': 'Found results'}
        ]
        agent.current_session['trace'] = [
            {
                'type': 'tool_execution',
                'tool_name': 'search',
                'arguments': {'q': 'python'},
                'status': 'success',
                'result': 'Results'
            }
        ]

        with patch.object(reflect_module, 'llm_do') as mock_llm_do:
            mock_llm_do.return_value = 'Good'

            reflect(agent)

            # Verify context was passed
            call_args = mock_llm_do.call_args[0][0]
            assert 'Search and summarize' in call_args


class TestReflectEventRegistration:
    """Tests for reflect event registration."""

    def test_reflect_has_event_type(self):
        """Test that reflect has correct event type."""
        assert hasattr(reflect, '_event_type')
        assert reflect._event_type == 'after_tools'

    def test_reflect_integrates_with_agent(self):
        """Test that reflect can be registered with agent."""
        from connectonion import Agent
        from connectonion.llm import LLMResponse
        from connectonion.usage import TokenUsage

        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponse(
            content="Test",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        # Should not raise
        agent = Agent(
            "test",
            llm=mock_llm,
            on_events=[reflect],
            log=False,
        )

        assert 'after_tools' in agent.events
        assert len(agent.events['after_tools']) >= 1
