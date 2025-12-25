"""Unit tests for connectonion/useful_plugins/ui_stream.py"""

import pytest
from unittest.mock import Mock, MagicMock

from connectonion.useful_plugins.ui_stream import (
    ui_stream,
    stream_llm_response,
    stream_tool_start,
    stream_tool_result,
    stream_error,
    stream_complete,
)


class TestStreamLLMResponse:
    """Test stream_llm_response event handler."""

    def test_skips_when_no_connection(self):
        """Does nothing when agent.connection is None."""
        agent = Mock()
        agent.connection = None

        stream_llm_response(agent)
        # No assertion needed - just shouldn't raise

    def test_skips_when_trace_empty(self):
        """Does nothing when trace is empty."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {'trace': []}

        stream_llm_response(agent)

        agent.connection.log.assert_not_called()

    def test_skips_when_last_not_llm_call(self):
        """Does nothing when last trace entry is not llm_call."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {'trace': [{'type': 'tool_execution'}]}

        stream_llm_response(agent)

        agent.connection.log.assert_not_called()

    def test_streams_message_content(self):
        """Streams message content when present."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {
            'trace': [{'type': 'llm_call', 'content': 'Hello world', 'tool_calls': []}]
        }

        stream_llm_response(agent)

        agent.connection.log.assert_called_once_with('message', content='Hello world')

    def test_streams_tool_calls(self):
        """Streams tool_pending events for each tool call."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {
            'trace': [{
                'type': 'llm_call',
                'content': '',
                'tool_calls': [
                    {'id': 'call_1', 'function': {'name': 'search', 'arguments': {'q': 'test'}}},
                    {'id': 'call_2', 'function': {'name': 'read', 'arguments': {'path': '/tmp'}}},
                ]
            }]
        }

        stream_llm_response(agent)

        assert agent.connection.log.call_count == 2
        calls = agent.connection.log.call_args_list
        assert calls[0][0] == ('tool_pending',)
        assert calls[0][1] == {'name': 'search', 'arguments': {'q': 'test'}, 'id': 'call_1'}
        assert calls[1][0] == ('tool_pending',)
        assert calls[1][1] == {'name': 'read', 'arguments': {'path': '/tmp'}, 'id': 'call_2'}


class TestStreamToolStart:
    """Test stream_tool_start event handler."""

    def test_skips_when_no_connection(self):
        """Does nothing when agent.connection is None."""
        agent = Mock()
        agent.connection = None

        stream_tool_start(agent)
        # No assertion needed - just shouldn't raise

    def test_skips_when_no_pending_tool(self):
        """Does nothing when no pending_tool in session."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {}

        stream_tool_start(agent)

        agent.connection.log.assert_not_called()

    def test_streams_tool_start_event(self):
        """Streams tool_start event with tool details."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {
            'pending_tool': {
                'name': 'bash',
                'arguments': {'command': 'ls'},
                'id': 'call_123',
            }
        }

        stream_tool_start(agent)

        agent.connection.log.assert_called_once_with(
            'tool_start',
            name='bash',
            arguments={'command': 'ls'},
            id='call_123',
        )


class TestStreamToolResult:
    """Test stream_tool_result event handler."""

    def test_skips_when_no_connection(self):
        """Does nothing when agent.connection is None."""
        agent = Mock()
        agent.connection = None

        stream_tool_result(agent)
        # No assertion needed - just shouldn't raise

    def test_skips_when_trace_empty(self):
        """Does nothing when trace is empty."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {'trace': []}

        stream_tool_result(agent)

        agent.connection.log.assert_not_called()

    def test_skips_when_last_not_tool_execution(self):
        """Does nothing when last trace entry is not tool_execution."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {'trace': [{'type': 'llm_call'}]}

        stream_tool_result(agent)

        agent.connection.log.assert_not_called()

    def test_streams_tool_result_event(self):
        """Streams tool_result event with execution details."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {
            'trace': [{
                'type': 'tool_execution',
                'tool_name': 'search',
                'status': 'success',
                'result': 'Found 3 results',
                'timing': 150,
            }]
        }

        stream_tool_result(agent)

        agent.connection.log.assert_called_once_with(
            'tool_result',
            name='search',
            status='success',
            result='Found 3 results',
            timing_ms=150,
        )

    def test_truncates_large_results(self):
        """Truncates results over 1000 characters."""
        agent = Mock()
        agent.connection = Mock()
        large_result = 'x' * 2000
        agent.current_session = {
            'trace': [{
                'type': 'tool_execution',
                'tool_name': 'read',
                'status': 'success',
                'result': large_result,
                'timing': 50,
            }]
        }

        stream_tool_result(agent)

        call_kwargs = agent.connection.log.call_args[1]
        assert len(call_kwargs['result']) == 1003  # 1000 + '...'
        assert call_kwargs['result'].endswith('...')


class TestStreamError:
    """Test stream_error event handler."""

    def test_skips_when_no_connection(self):
        """Does nothing when agent.connection is None."""
        agent = Mock()
        agent.connection = None

        stream_error(agent)
        # No assertion needed - just shouldn't raise

    def test_skips_when_trace_empty(self):
        """Does nothing when trace is empty."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {'trace': []}

        stream_error(agent)

        agent.connection.log.assert_not_called()

    def test_skips_when_not_error_status(self):
        """Does nothing when last trace entry status is not error."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {'trace': [{'status': 'success'}]}

        stream_error(agent)

        agent.connection.log.assert_not_called()

    def test_streams_error_event(self):
        """Streams error event with error details."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {
            'trace': [{
                'status': 'error',
                'tool_name': 'bash',
                'error': 'Command not found',
            }]
        }

        stream_error(agent)

        agent.connection.log.assert_called_once_with(
            'error',
            tool_name='bash',
            error='Command not found',
        )


class TestStreamComplete:
    """Test stream_complete event handler."""

    def test_skips_when_no_connection(self):
        """Does nothing when agent.connection is None."""
        agent = Mock()
        agent.connection = None

        stream_complete(agent)
        # No assertion needed - just shouldn't raise

    def test_streams_complete_event(self):
        """Streams complete event with summary."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {
            'trace': [
                {'type': 'llm_call'},
                {'type': 'tool_execution', 'tool_name': 'search'},
                {'type': 'tool_execution', 'tool_name': 'read'},
                {'type': 'llm_call'},
            ],
            'iteration': 2,
        }

        stream_complete(agent)

        agent.connection.log.assert_called_once_with(
            'complete',
            tools_used=['search', 'read'],
            llm_calls=2,
            iterations=2,
        )

    def test_streams_empty_when_no_trace(self):
        """Streams complete event with empty data when no trace."""
        agent = Mock()
        agent.connection = Mock()
        agent.current_session = {'trace': []}

        stream_complete(agent)

        agent.connection.log.assert_called_once_with(
            'complete',
            tools_used=[],
            llm_calls=0,
            iterations=0,
        )


class TestUIStreamPlugin:
    """Test ui_stream plugin bundle."""

    def test_contains_all_handlers(self):
        """ui_stream contains all event handlers."""
        assert len(ui_stream) == 5
        assert stream_llm_response in ui_stream
        assert stream_tool_start in ui_stream
        assert stream_tool_result in ui_stream
        assert stream_error in ui_stream
        assert stream_complete in ui_stream

    def test_handlers_have_event_type(self):
        """All handlers are tagged with _event_type."""
        expected_types = {
            'after_llm',
            'before_each_tool',
            'after_each_tool',
            'on_error',
            'on_complete',
        }
        actual_types = {h._event_type for h in ui_stream}
        assert actual_types == expected_types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
