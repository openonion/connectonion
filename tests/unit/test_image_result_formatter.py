"""Unit tests for connectonion/useful_plugins/image_result_formatter.py

Tests cover:
- _is_base64_image: detecting base64 image data
- _format_image_result: formatting image results for LLM
- Plugin registration
"""
"""
LLM-Note: Tests for image result formatter

What it tests:
- Image Result Formatter functionality

Components under test:
- Module: image_result_formatter
"""


import pytest
from unittest.mock import Mock
from connectonion.useful_plugins.image_result_formatter import (
    _is_base64_image,
    _format_image_result,
    _is_image_message,
    _sanitize_image_urls,
    image_result_formatter,
    KEEP_LAST_N_SCREENSHOTS,
)
from tests.utils.mock_helpers import MockLLM


class FakeAgent:
    """Fake agent for testing plugins."""

    def __init__(self, with_io=False):
        self.current_session = {
            'messages': [],
            'trace': [],
        }
        self.logger = Mock()
        self.io = Mock() if with_io else None


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
                'type': 'tool_result',
                'name': 'screenshot',
                'status': 'success',
                'result': f"data:image/png;base64,{base64_data}",
                'tool_id': 'call_123'
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
        assert agent.current_session['messages'][0]['content'] == "Tool returned an image (provided below)"

        # Check user message with image was inserted (images are added as user messages)
        assert len(agent.current_session['messages']) == 2
        image_msg = agent.current_session['messages'][1]
        assert image_msg['role'] == 'user'
        assert isinstance(image_msg['content'], list)

        # Check image content structure
        content = image_msg['content']
        assert content[0]['type'] == 'text'
        assert content[1]['type'] == 'image_url'
        assert 'data:image/png;base64' in content[1]['image_url']['url']

    def test_drops_raw_base64_from_text_context(self):
        """Raw base64 image results should not be copied into text context."""
        agent = FakeAgent()
        base64_data = "A" * 150
        agent.current_session['trace'] = [
            {
                'type': 'tool_result',
                'name': 'take_screenshot',
                'status': 'success',
                'result': base64_data,
                'tool_id': 'call_123'
            }
        ]
        agent.current_session['messages'] = [
            {
                'role': 'tool',
                'content': base64_data,
                'tool_call_id': 'call_123'
            }
        ]

        _format_image_result(agent)

        tool_msg = agent.current_session['messages'][0]['content']
        image_msg = agent.current_session['messages'][1]
        image_text = image_msg['content'][0]['text']

        assert base64_data not in tool_msg
        assert base64_data not in image_text
        assert tool_msg == "Tool returned an image (provided below)"
        assert image_text == "Here is the image from 'take_screenshot':"
        assert image_msg['content'][1]['image_url']['url'].endswith(base64_data)

    def test_prints_formatting_message(self):
        """Test that formatting message is printed."""
        agent = FakeAgent()
        agent.current_session['trace'] = [
            {
                'type': 'tool_result',
                'name': 'capture',
                'status': 'success',
                'result': 'data:image/png;base64,iVBORw0KGgo',
                'tool_id': 'call_456'
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
                'type': 'tool_result',
                'name': 'screenshot',
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
                'type': 'tool_result',
                'name': 'search',
                'status': 'success',
                'result': 'Found 10 results for Python',
                'tool_id': 'call_789'
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
                'type': 'tool_result',
                'name': 'screenshot',
                'status': 'success',
                'result': 'data:image/png;base64,' + 'A' * 1000,
                'tool_id': 'call_abc'
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
        trace_entry = agent.current_session['trace'][0]
        trace_result = trace_entry['result']
        assert 'screenshot' in trace_result
        assert 'image/png' in trace_result
        assert len(trace_result) < 100  # Much shorter than original
        # Full data URL is retained out-of-band so session replay can re-emit it.
        assert trace_entry['image'] == 'data:image/png;base64,' + 'A' * 1000

    def test_sends_image_to_io_when_available(self):
        """Image tool results are model-visible and sent to frontend IO."""
        agent = FakeAgent(with_io=True)
        base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAE"
        data_url = f"data:image/png;base64,{base64_data}"
        agent.current_session['trace'] = [
            {
                'type': 'tool_result',
                'name': 'screenshot',
                'status': 'success',
                'result': data_url,
                'tool_id': 'call_123'
            }
        ]
        agent.current_session['messages'] = [
            {
                'role': 'tool',
                'content': data_url,
                'tool_call_id': 'call_123'
            }
        ]

        _format_image_result(agent)

        agent.io.send_image.assert_called_once_with(data_url)
        image_msg = agent.current_session['messages'][1]
        image_part = next(item for item in image_msg['content'] if item['type'] == 'image_url')
        assert image_part['image_url']['url'] == data_url

    def test_skips_sending_to_io_when_not_available(self):
        """Test that no error occurs when io is None."""
        agent = FakeAgent(with_io=False)
        base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAE"
        agent.current_session['trace'] = [
            {
                'type': 'tool_result',
                'name': 'screenshot',
                'status': 'success',
                'result': f"data:image/png;base64,{base64_data}",
                'tool_id': 'call_456'
            }
        ]
        agent.current_session['messages'] = [
            {
                'role': 'tool',
                'content': f"data:image/png;base64,{base64_data}",
                'tool_call_id': 'call_456'
            }
        ]

        # Should not raise error even without io
        _format_image_result(agent)


class TestScreenshotSlidingWindow:
    """The LLM context keeps only the last N screenshots; older ones are elided."""

    def _take_screenshot(self, agent, n):
        """Simulate one turn: a screenshot tool result that gets formatted."""
        b64 = "A" * 150
        tool_id = f"call_{n}"
        agent.current_session['messages'].append({
            'role': 'tool',
            'content': f"data:image/png;base64,{b64}",
            'tool_call_id': tool_id,
        })
        agent.current_session['trace'].append({
            'type': 'tool_result',
            'name': 'take_screenshot',
            'status': 'success',
            'result': f"data:image/png;base64,{b64}",
            'tool_id': tool_id,
        })
        _format_image_result(agent)

    def test_keeps_only_last_n_screenshots(self):
        agent = FakeAgent()
        for n in range(5):
            self._take_screenshot(agent, n)

        image_msgs = [m for m in agent.current_session['messages'] if _is_image_message(m)]
        assert len(image_msgs) == KEEP_LAST_N_SCREENSHOTS

        placeholders = [
            m for m in agent.current_session['messages']
            if m.get('content') == "[earlier screenshot removed to bound context]"
        ]
        assert len(placeholders) == 5 - KEEP_LAST_N_SCREENSHOTS

    def test_context_payload_stays_flat_not_linear(self):
        """The byte size the LLM receives must stop growing once the window fills."""
        def image_bytes(agent):
            return sum(
                len(part['image_url']['url'])
                for m in agent.current_session['messages'] if _is_image_message(m)
                for part in m['content'] if part.get('type') == 'image_url'
            )

        agent = FakeAgent()
        sizes = []
        for n in range(6):
            self._take_screenshot(agent, n)
            sizes.append(image_bytes(agent))

        # Grows while filling the window, then plateaus (never linear in turn count).
        assert sizes[-1] == sizes[KEEP_LAST_N_SCREENSHOTS - 1]
        assert sizes[-1] == sizes[-2]

    def test_replay_trace_keeps_every_screenshot(self):
        """Eliding the LLM context must not touch the trace the frontend replays."""
        agent = FakeAgent()
        for n in range(5):
            self._take_screenshot(agent, n)

        # Every screenshot is still recoverable out-of-band for session replay.
        assert all('image' in t for t in agent.current_session['trace'])


class TestSanitizeImageUrls:
    """before_llm sanitizer: stale/invalid image_url parts must not reach the LLM."""

    def _img_msg(self, url):
        return {"role": "user", "content": [
            {"type": "text", "text": "x"},
            {"type": "image_url", "image_url": {"url": url}},
        ]}

    def test_placeholder_url_becomes_text(self):
        agent = FakeAgent()
        agent.current_session['messages'] = [self._img_msg("[image]")]
        _sanitize_image_urls(agent)
        part = agent.current_session['messages'][0]['content'][1]
        assert part == {"type": "text", "text": "[image unavailable]"}

    def test_empty_url_becomes_text(self):
        agent = FakeAgent()
        agent.current_session['messages'] = [self._img_msg("")]
        _sanitize_image_urls(agent)
        assert agent.current_session['messages'][0]['content'][1]['type'] == 'text'

    def test_valid_data_url_kept(self):
        agent = FakeAgent()
        url = "data:image/png;base64,iVBORw0KGgo"
        agent.current_session['messages'] = [self._img_msg(url)]
        _sanitize_image_urls(agent)
        part = agent.current_session['messages'][0]['content'][1]
        assert part['type'] == 'image_url' and part['image_url']['url'] == url

    def test_https_url_kept(self):
        agent = FakeAgent()
        agent.current_session['messages'] = [self._img_msg("https://x/y.png")]
        _sanitize_image_urls(agent)
        assert agent.current_session['messages'][0]['content'][1]['type'] == 'image_url'

    def test_string_content_untouched(self):
        agent = FakeAgent()
        agent.current_session['messages'] = [{"role": "user", "content": "hello"}]
        _sanitize_image_urls(agent)
        assert agent.current_session['messages'][0]['content'] == "hello"


class TestImageResultFormatterPlugin:
    """Tests for image_result_formatter plugin."""

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
