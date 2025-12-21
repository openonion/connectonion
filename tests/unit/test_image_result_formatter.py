"""Unit tests for connectonion/useful_plugins/image_result_formatter.py

Tests cover:
- _is_base64_image: detecting base64 image data
- _format_image_result: formatting image results for LLM
- Plugin registration
"""

import pytest
from unittest.mock import Mock
from connectonion.useful_plugins.image_result_formatter import (
    _is_base64_image,
    _format_image_result,
    image_result_formatter,
)
from tests.utils.mock_helpers import MockLLM


class FakeAgent:
    """Fake agent for testing plugins."""

    def __init__(self):
        self.current_session = {
            'messages': [],
            'trace': [],
        }
        self.logger = Mock()


class TestIsBase64Image:
    """Tests for _is_base64_image detection function."""

    def test_detects_data_url_png(self):
        """Test detection of PNG data URL."""
        data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        is_image, mime_type, base64_data = _is_base64_image(data)

        assert is_image is True
        assert mime_type == "image/png"
        assert "iVBORw0KGgo" in base64_data

    def test_detects_data_url_jpeg(self):
        """Test detection of JPEG data URL."""
        data = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD"
        is_image, mime_type, base64_data = _is_base64_image(data)

        assert is_image is True
        assert mime_type == "image/jpeg"

    def test_detects_data_url_gif(self):
        """Test detection of GIF data URL."""
        data = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
        is_image, mime_type, base64_data = _is_base64_image(data)

        assert is_image is True
        assert mime_type == "image/gif"

    def test_detects_data_url_webp(self):
        """Test detection of WebP data URL."""
        data = "data:image/webp;base64,UklGRhoAAABXRUJQVlA4TA0AAAAvAAAAEAcQERGIiP4HAA=="
        is_image, mime_type, base64_data = _is_base64_image(data)

        assert is_image is True
        assert mime_type == "image/webp"

    def test_detects_raw_base64(self):
        """Test detection of raw base64 string (no data URL)."""
        # Long base64 string that looks like an image
        data = "A" * 150  # Base64 chars only
        is_image, mime_type, base64_data = _is_base64_image(data)

        assert is_image is True
        assert mime_type == "image/png"  # Default
        assert base64_data == data

    def test_rejects_short_string(self):
        """Test that short strings are not detected as images."""
        data = "short"
        is_image, mime_type, base64_data = _is_base64_image(data)

        assert is_image is False

    def test_rejects_non_base64_string(self):
        """Test that non-base64 strings are rejected."""
        data = "This is just a normal text response with special chars !@#$%"
        is_image, mime_type, base64_data = _is_base64_image(data)

        assert is_image is False

    def test_rejects_non_string(self):
        """Test that non-string input returns False."""
        is_image, mime_type, base64_data = _is_base64_image(123)
        assert is_image is False

        is_image, mime_type, base64_data = _is_base64_image(None)
        assert is_image is False

    def test_detects_embedded_data_url(self):
        """Test detection when data URL is embedded in text."""
        data = "Screenshot taken: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAE"
        is_image, mime_type, base64_data = _is_base64_image(data)

        assert is_image is True
        assert mime_type == "image/png"


class TestFormatImageResult:
    """Tests for _format_image_result function."""

    def test_formats_image_result_correctly(self):
        """Test that image results are formatted as multimodal content."""
        agent = FakeAgent()
        base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAE"
        agent.current_session['trace'] = [
            {
                'type': 'tool_execution',
                'tool_name': 'screenshot',
                'status': 'success',
                'result': f"data:image/png;base64,{base64_data}",
                'call_id': 'call_123'
            }
        ]
        agent.current_session['messages'] = [
            {
                'role': 'tool',
                'content': f"data:image/png;base64,{base64_data}",
                'tool_call_id': 'call_123'
            }
        ]

        _format_image_result(agent)

        # Check tool message was shortened
        assert 'Screenshot captured' in agent.current_session['messages'][0]['content']

        # Check user message with image was inserted
        assert len(agent.current_session['messages']) == 2
        user_msg = agent.current_session['messages'][1]
        assert user_msg['role'] == 'user'
        assert isinstance(user_msg['content'], list)

        # Check image content structure
        content = user_msg['content']
        assert content[0]['type'] == 'text'
        assert content[1]['type'] == 'image_url'
        assert 'data:image/png;base64' in content[1]['image_url']['url']

    def test_prints_formatting_message(self):
        """Test that formatting message is printed."""
        agent = FakeAgent()
        agent.current_session['trace'] = [
            {
                'type': 'tool_execution',
                'tool_name': 'capture',
                'status': 'success',
                'result': 'data:image/png;base64,iVBORw0KGgo',
                'call_id': 'call_456'
            }
        ]
        agent.current_session['messages'] = [
            {
                'role': 'tool',
                'content': 'data:image/png;base64,iVBORw0KGgo',
                'tool_call_id': 'call_456'
            }
        ]

        _format_image_result(agent)

        agent.logger.print.assert_called_once()
        call_args = agent.logger.print.call_args[0][0]
        assert 'capture' in call_args
        assert 'image' in call_args.lower()

    def test_skips_non_tool_execution(self):
        """Test that non-tool executions are skipped."""
        agent = FakeAgent()
        agent.current_session['trace'] = [
            {'type': 'llm_call', 'model': 'gpt-4'}
        ]
        agent.current_session['messages'] = []

        _format_image_result(agent)

        # Nothing should be modified
        assert len(agent.current_session['messages']) == 0
        agent.logger.print.assert_not_called()

    def test_skips_error_status(self):
        """Test that error status is skipped."""
        agent = FakeAgent()
        agent.current_session['trace'] = [
            {
                'type': 'tool_execution',
                'tool_name': 'screenshot',
                'status': 'error',
                'error': 'Failed'
            }
        ]

        _format_image_result(agent)

        agent.logger.print.assert_not_called()

    def test_skips_non_image_result(self):
        """Test that non-image results are skipped."""
        agent = FakeAgent()
        agent.current_session['trace'] = [
            {
                'type': 'tool_execution',
                'tool_name': 'search',
                'status': 'success',
                'result': 'Found 10 results for Python',
                'call_id': 'call_789'
            }
        ]
        agent.current_session['messages'] = [
            {
                'role': 'tool',
                'content': 'Found 10 results for Python',
                'tool_call_id': 'call_789'
            }
        ]

        _format_image_result(agent)

        # Message should not be modified
        assert agent.current_session['messages'][0]['content'] == 'Found 10 results for Python'
        agent.logger.print.assert_not_called()

    def test_updates_trace_result(self):
        """Test that trace result is updated to short message."""
        agent = FakeAgent()
        agent.current_session['trace'] = [
            {
                'type': 'tool_execution',
                'tool_name': 'screenshot',
                'status': 'success',
                'result': 'data:image/png;base64,' + 'A' * 1000,
                'call_id': 'call_abc'
            }
        ]
        agent.current_session['messages'] = [
            {
                'role': 'tool',
                'content': 'data:image/png;base64,' + 'A' * 1000,
                'tool_call_id': 'call_abc'
            }
        ]

        _format_image_result(agent)

        # Trace result should be shortened
        trace_result = agent.current_session['trace'][0]['result']
        assert 'screenshot' in trace_result
        assert 'image/png' in trace_result
        assert len(trace_result) < 100  # Much shorter than original


class TestImageResultFormatterPlugin:
    """Tests for image_result_formatter plugin."""

    def test_plugin_is_list(self):
        """Test that plugin is a list of handlers."""
        assert isinstance(image_result_formatter, list)
        assert len(image_result_formatter) == 1

    def test_plugin_handler_has_event_type(self):
        """Test that handler has correct event type."""
        handler = image_result_formatter[0]
        assert hasattr(handler, '_event_type')
        assert handler._event_type == 'after_tools'

    def test_plugin_integrates_with_agent(self):
        """Test that plugin can be registered with agent."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

        mock_llm = MockLLM(responses=[
            LLMResponse(
                content="Test",
                tool_calls=[],
                raw_response=None,
                usage=TokenUsage(),
            )
        ])

        # Should not raise
        agent = Agent(
            "test",
            llm=mock_llm,
            plugins=[image_result_formatter],
            log=False,
        )

        assert 'after_tools' in agent.events
