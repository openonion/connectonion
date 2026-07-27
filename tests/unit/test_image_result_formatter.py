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
    image_result_formatter,
)
from tests.utils.mock_helpers import MockLLM


UPLOADED_URL = "https://oo.openonion.ai/img/test"


@pytest.fixture(autouse=True)
def fake_upload(monkeypatch):
    """The formatter uploads every image to oo-api; stub the network call."""
    monkeypatch.setenv("OPENONION_API_KEY", "test-token")
    resp = Mock()
    resp.json.return_value = {"url": UPLOADED_URL}
    monkeypatch.setattr('requests.post', Mock(return_value=resp))


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
        base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
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
        assert content[1]['image_url']['url'] == UPLOADED_URL

    def test_drops_raw_base64_from_text_context(self):
        """Raw base64 image results should not be copied into text context."""
        agent = FakeAgent()
        base64_data = "A" * 152  # valid base64: length divisible by 4
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
        assert image_msg['content'][1]['image_url']['url'] == UPLOADED_URL

    def test_prints_formatting_message(self):
        """Test that formatting message is printed."""
        agent = FakeAgent()
        agent.current_session['trace'] = [
            {
                'type': 'tool_result',
                'name': 'capture',
                'status': 'success',
                'result': 'data:image/png;base64,iVBORw0KGgo=',
                'tool_id': 'call_456'
            }
        ]
        agent.current_session['messages'] = [
            {
                'role': 'tool',
                'content': 'data:image/png;base64,iVBORw0KGgo=',
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
        trace_result = agent.current_session['trace'][0]['result']
        assert 'screenshot' in trace_result
        assert 'image/png' in trace_result
        assert len(trace_result) < 100  # Much shorter than original

    def test_sends_image_to_io_when_available(self):
        """Image tool results are model-visible and sent to frontend IO."""
        agent = FakeAgent(with_io=True)
        base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
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

        agent.io.send_image.assert_called_once_with(UPLOADED_URL)
        image_msg = agent.current_session['messages'][1]
        image_part = next(item for item in image_msg['content'] if item['type'] == 'image_url')
        assert image_part['image_url']['url'] == UPLOADED_URL

    def test_skips_sending_to_io_when_not_available(self):
        """Test that no error occurs when io is None."""
        agent = FakeAgent(with_io=False)
        base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
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


class TestUploadToOoApi:
    """Every image is uploaded to oo-api and referenced by URL."""

    def test_uploads_and_uses_returned_url(self, monkeypatch):
        agent = FakeAgent(with_io=True)
        base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        data_url = f"data:image/png;base64,{base64_data}"
        agent.current_session['trace'] = [
            {
                'type': 'tool_result',
                'name': 'screenshot',
                'status': 'success',
                'result': data_url,
                'tool_id': 'call_789'
            }
        ]
        agent.current_session['messages'] = [
            {'role': 'tool', 'content': data_url, 'tool_call_id': 'call_789'}
        ]

        captured = {}

        def fake_post(url, headers=None, files=None, timeout=None):
            captured['url'] = url
            captured['auth'] = headers['Authorization']
            resp = Mock()
            resp.json.return_value = {"url": UPLOADED_URL}
            return resp

        monkeypatch.setattr('requests.post', fake_post)

        _format_image_result(agent)

        assert captured['url'] == "https://oo.openonion.ai/api/v1/images"
        assert captured['auth'] == "Bearer test-token"
        image_msg = agent.current_session['messages'][1]
        image_part = next(p for p in image_msg['content'] if p['type'] == 'image_url')
        assert image_part['image_url']['url'] == UPLOADED_URL
        agent.io.send_image.assert_called_once_with(UPLOADED_URL)
        assert base64_data not in str(agent.current_session['messages'])


class TestScreenshotPathDetection:
    """`co browser take_screenshot` prints a path, not base64.

    The daemon strips the payload so CLI output stays readable, which means an
    agent driving the browser through the CLI would be blind to its own
    screenshots — and the user would never see them — unless the formatter
    reads the file the path points at.
    """

    def _png(self, tmp_path):
        import base64 as b64
        data = b64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        path = tmp_path / "step_3.png"
        path.write_bytes(data)
        return path

    def test_reads_the_image_the_daemon_points_at(self, tmp_path):
        from connectonion.useful_plugins.image_result_formatter import _is_base64_image
        path = self._png(tmp_path)

        is_image, mime, data = _is_base64_image(f"Screenshot saved to: {path}")

        assert is_image is True
        assert mime == "image/png"
        assert data.startswith("iVBORw0KGgo")

    def test_jpeg_and_webp_paths(self, tmp_path):
        from connectonion.useful_plugins.image_result_formatter import _is_base64_image
        for ext, expected in (("jpg", "image/jpeg"), ("jpeg", "image/jpeg"), ("webp", "image/webp")):
            p = tmp_path / f"shot.{ext}"
            p.write_bytes(b"\xff\xd8\xff")
            assert _is_base64_image(f"Screenshot saved to: {p}")[1] == expected

    def test_a_path_that_does_not_exist_is_not_an_image(self):
        from connectonion.useful_plugins.image_result_formatter import _is_base64_image
        assert _is_base64_image("Screenshot saved to: /nope/missing.png")[0] is False

    def test_ordinary_tool_output_is_untouched(self):
        from connectonion.useful_plugins.image_result_formatter import _is_base64_image
        for text in ("done", "", "Created report.pdf", "see notes.md for details"):
            assert _is_base64_image(text)[0] is False

    def test_shell_output_that_merely_names_a_real_image_is_not_a_screenshot(self, tmp_path, monkeypatch):
        """`ls` and `git status` list real .png files all the time.

        A loose path scan treated those as screenshots: it uploaded unrelated
        user files to the backend and replaced the tool result with an image
        placeholder. Detection is anchored to the daemon's actual output.
        """
        from connectonion.useful_plugins.image_result_formatter import _is_base64_image
        monkeypatch.chdir(tmp_path)
        (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        for text in (
            "logo.png\nREADME.md",              # ls
            "modified:   logo.png",             # git status
            "docs/logo.png: matched",           # grep
            "Deleted logo.png",
        ):
            assert _is_base64_image(text)[0] is False, text

    def test_oversized_file_is_not_treated_as_an_image(self, tmp_path, monkeypatch):
        """Guards against base64-ing something huge into the request."""
        from importlib import import_module
        fmt = import_module("connectonion.useful_plugins.image_result_formatter")
        monkeypatch.chdir(tmp_path)
        (tmp_path / "big.png").write_bytes(b"x" * 64)
        monkeypatch.setattr(fmt, "_MAX_IMAGE_BYTES", 10)

        assert fmt._is_base64_image("Screenshot saved to: big.png")[0] is False

    def test_base64_still_wins_over_path_scanning(self):
        """In-process tools returning data URLs must keep working unchanged."""
        from connectonion.useful_plugins.image_result_formatter import _is_base64_image
        is_image, mime, data = _is_base64_image("data:image/png;base64,iVBORw0KGgo=")
        assert (is_image, mime) == (True, "image/png")
        assert data == "iVBORw0KGgo="


def test_screenshot_path_becomes_an_attached_image(tmp_path, monkeypatch):
    """The whole point of the path branch: a `co browser take_screenshot`
    result must end up as an image the model and the user can see.

    Detection alone isn't enough — this drives _format_image_result so a
    regression in the plumbing between them can't pass unnoticed.
    """
    import base64 as b64
    from importlib import import_module
    fmt = import_module("connectonion.useful_plugins.image_result_formatter")

    png = tmp_path / "shot.png"
    png.write_bytes(b64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    ))
    monkeypatch.setattr(fmt, "_upload_image", lambda *a, **k: "https://example.com/i.png", raising=False)

    class Logger:
        def print(self, *a, **k): pass

    class FakeAgent:
        logger = Logger()
        io = None

        def __init__(self):
            result = f"Screenshot saved to: {png}"
            self.current_session = {
                "messages": [
                    {"role": "assistant", "tool_calls": [{"id": "c1"}]},
                    {"role": "tool", "tool_call_id": "c1", "content": result},
                ],
                "trace": [{"type": "tool_result", "status": "success",
                           "tool_id": "c1", "name": "bash", "result": result}],
            }

    agent = FakeAgent()
    fmt._format_image_result(agent)
    messages = agent.current_session["messages"]

    assert any("image_url" in str(m.get("content", "")) for m in messages), \
        "no multimodal image message was inserted"
    assert "Screenshot saved to" not in str(messages[1].get("content")), \
        "the raw path should be replaced by a placeholder"
