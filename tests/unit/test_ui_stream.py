"""Unit tests for connectonion/useful_plugins/ui_stream.py"""

import pytest
from unittest.mock import Mock

from connectonion.useful_plugins.ui_stream import (
    ui_stream,
    stream_complete,
)


class TestStreamComplete:
    """Test stream_complete event handler."""

    def test_skips_when_no_connection(self):
        """Does nothing when agent.io is None."""
        agent = Mock()
        agent.io = None

        stream_complete(agent)

    def test_streams_complete_event(self):
        """Streams complete event with summary."""
        agent = Mock()
        agent.io = Mock()
        agent.current_session = {
            'trace': [
                {'type': 'llm_call'},
                {'type': 'tool_result', 'name': 'search'},
                {'type': 'tool_result', 'name': 'read'},
                {'type': 'llm_call'},
            ],
            'iteration': 2,
        }

        stream_complete(agent)

        agent.io.log.assert_called_once_with(
            'complete',
            tools_used=['search', 'read'],
            llm_calls=2,
            iterations=2,
        )

    def test_streams_empty_when_no_trace(self):
        """Streams complete event with empty data when no trace."""
        agent = Mock()
        agent.io = Mock()
        agent.current_session = {'trace': []}

        stream_complete(agent)

        agent.io.log.assert_called_once_with(
            'complete',
            tools_used=[],
            llm_calls=0,
            iterations=0,
        )


class TestUIStreamPlugin:
    """Test ui_stream plugin bundle."""

    def test_contains_stream_complete(self):
        """ui_stream contains stream_complete handler."""
        assert len(ui_stream) == 1
        assert stream_complete in ui_stream

    def test_handler_has_event_type(self):
        """Handler is tagged with _event_type."""
        assert stream_complete._event_type == 'on_complete'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
