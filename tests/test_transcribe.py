"""
Tests for transcribe() audio-to-text utility.

Run: pytest tests/test_transcribe.py -v
Run with real API: pytest tests/test_transcribe.py -v -m real_api
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Test fixtures path
FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_AUDIO = FIXTURES_DIR / "test_audio.mp3"


class TestTranscribeUnit:
    """Unit tests for transcribe function (mocked API)."""

    def test_import(self):
        """Test that transcribe can be imported."""
        from connectonion import transcribe
        assert callable(transcribe)

    def test_file_not_found(self):
        """Test error when audio file doesn't exist."""
        from connectonion import transcribe

        with pytest.raises(FileNotFoundError):
            transcribe("nonexistent_file.mp3")

    def test_mime_type_detection(self):
        """Test MIME type detection for various formats."""
        from connectonion.transcribe import _get_mime_type

        assert _get_mime_type(Path("test.mp3")) == "audio/mp3"
        assert _get_mime_type(Path("test.wav")) == "audio/wav"
        assert _get_mime_type(Path("test.flac")) == "audio/flac"
        assert _get_mime_type(Path("test.ogg")) == "audio/ogg"
        assert _get_mime_type(Path("test.aac")) == "audio/aac"
        assert _get_mime_type(Path("test.m4a")) == "audio/mp4"

    def test_api_key_error_gemini(self):
        """Test error when Gemini API key is missing."""
        from connectonion.transcribe import transcribe

        # Clear all relevant env vars
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="Gemini API key required"):
                transcribe(str(TEST_AUDIO), model="gemini-3-flash-preview")

    def test_transcribe_calls_gemini(self):
        """Test that transcribe calls Gemini API for non-co models."""
        # Import directly from module file to avoid __init__.py shadowing
        import sys
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "transcribe_mod",
            Path(__file__).parent.parent / "connectonion" / "transcribe.py"
        )
        transcribe_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(transcribe_mod)

        # Mock the OpenAI client that Gemini uses
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test transcription"

        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
                result = transcribe_mod.transcribe(str(TEST_AUDIO), model="gemini-3-flash-preview")

            assert result == "Test transcription"
            mock_client.chat.completions.create.assert_called_once()

    def test_transcribe_calls_openonion(self):
        """Test that transcribe calls OpenOnion for co/ models."""
        # Import directly from module file
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "transcribe_mod",
            Path(__file__).parent.parent / "connectonion" / "transcribe.py"
        )
        transcribe_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(transcribe_mod)

        # Mock httpx.post for OpenOnion proxy
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test transcription via proxy"}}]
        }

        with patch("httpx.post") as mock_post:
            mock_post.return_value = mock_response

            with patch.dict("os.environ", {"OPENONION_API_KEY": "test-jwt"}):
                result = transcribe_mod.transcribe(str(TEST_AUDIO), model="co/gemini-3-flash-preview")

            assert result == "Test transcription via proxy"
            mock_post.assert_called_once()


@pytest.mark.real_api
class TestTranscribeRealAPI:
    """Real API tests (require GEMINI_API_KEY or OPENONION_API_KEY)."""

    @pytest.fixture
    def audio_file(self):
        """Return path to test audio file."""
        if not TEST_AUDIO.exists():
            pytest.skip("Test audio file not found. Run: yt-dlp to download.")
        return str(TEST_AUDIO)

    def test_transcribe_gemini_direct(self, audio_file):
        """Test transcription using Gemini API directly."""
        import os
        if not os.getenv("GEMINI_API_KEY"):
            pytest.skip("GEMINI_API_KEY not set")

        from connectonion import transcribe

        result = transcribe(audio_file, model="gemini-3-flash-preview")

        assert result is not None
        assert len(result) > 0
        # The test audio is "Me at the zoo" - should contain "elephant"
        assert "elephant" in result.lower()

    def test_transcribe_openonion_proxy(self, audio_file):
        """Test transcription using OpenOnion proxy."""
        import os
        if not os.getenv("OPENONION_API_KEY"):
            # Try loading from config
            from pathlib import Path
            config_path = Path.home() / ".connectonion" / ".co" / "config.toml"
            if not config_path.exists():
                pytest.skip("OPENONION_API_KEY not set and no config.toml")

        from connectonion import transcribe

        result = transcribe(audio_file, model="co/gemini-3-flash-preview")

        assert result is not None
        assert len(result) > 0
        assert "elephant" in result.lower()

    def test_transcribe_with_prompt(self, audio_file):
        """Test transcription with context prompt."""
        import os
        if not os.getenv("GEMINI_API_KEY"):
            pytest.skip("GEMINI_API_KEY not set")

        from connectonion import transcribe

        result = transcribe(
            audio_file,
            prompt="A person at a zoo talking about animals",
            model="gemini-3-flash-preview"
        )

        assert result is not None
        assert "elephant" in result.lower()

    def test_transcribe_with_timestamps(self, audio_file):
        """Test transcription with timestamps."""
        import os
        if not os.getenv("GEMINI_API_KEY"):
            pytest.skip("GEMINI_API_KEY not set")

        from connectonion import transcribe

        result = transcribe(
            audio_file,
            timestamps=True,
            model="gemini-3-flash-preview"
        )

        assert result is not None
        # Should contain timestamp markers like [00:00] or similar
        # Note: Gemini may format timestamps differently
        assert len(result) > 0

    def test_transcribe_different_models(self, audio_file):
        """Test transcription with different Gemini models."""
        import os
        if not os.getenv("GEMINI_API_KEY"):
            pytest.skip("GEMINI_API_KEY not set")

        from connectonion import transcribe

        # Test with gemini-2.5-flash
        result = transcribe(audio_file, model="gemini-2.5-flash")

        assert result is not None
        assert "elephant" in result.lower()
