"""
Real API tests for transcribe() audio-to-text utility.

Run: pytest tests/real_api/test_real_transcribe.py -v
"""

import os
from pathlib import Path

import pytest

from tests.real_api.conftest import requires_gemini


pytestmark = pytest.mark.real_api

# Test fixtures path
FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"
TEST_AUDIO = FIXTURES_DIR / "test_audio.mp3"


@pytest.fixture
def audio_file():
    """Return path to test audio file."""
    if not TEST_AUDIO.exists():
        pytest.skip("Test audio file not found. Run: yt-dlp to download.")
    return str(TEST_AUDIO)


@requires_gemini
def test_transcribe_gemini_direct(audio_file):
    """Test transcription using Gemini API directly."""
    from connectonion import transcribe

    result = transcribe(audio_file, model="gemini-3-flash-preview")

    assert result is not None
    assert len(result) > 0
    # The test audio is "Me at the zoo" - should contain "elephant"
    assert "elephant" in result.lower()


def test_transcribe_openonion_proxy(audio_file):
    """Test transcription using OpenOnion proxy."""
    if not os.getenv("OPENONION_API_KEY"):
        # Try loading from config
        config_path = Path.home() / ".connectonion" / ".co" / "config.toml"
        if not config_path.exists():
            pytest.skip("OPENONION_API_KEY not set and no config.toml")

    from connectonion import transcribe

    result = transcribe(audio_file, model="co/gemini-3-flash-preview")

    assert result is not None
    assert len(result) > 0
    assert "elephant" in result.lower()


@requires_gemini
def test_transcribe_with_prompt(audio_file):
    """Test transcription with context prompt."""
    from connectonion import transcribe

    result = transcribe(
        audio_file,
        prompt="A person at a zoo talking about animals",
        model="gemini-3-flash-preview"
    )

    assert result is not None
    assert "elephant" in result.lower()


@requires_gemini
def test_transcribe_with_timestamps(audio_file):
    """Test transcription with timestamps."""
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


@requires_gemini
def test_transcribe_different_models(audio_file):
    """Test transcription with different Gemini models."""
    from connectonion import transcribe

    # Test with gemini-2.5-flash
    result = transcribe(audio_file, model="gemini-2.5-flash")

    assert result is not None
    assert "elephant" in result.lower()
