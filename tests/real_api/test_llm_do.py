"""Pytest-based tests for llm_do with multi-LLM support via LiteLLM."""

import sys
import uuid as standard_uuid

# Fix for fastuuid dependency issue in LiteLLM
class MockFastUUID:
    @staticmethod
    def uuid4():
        return str(standard_uuid.uuid4())
    
    UUID = standard_uuid.UUID

sys.modules['fastuuid'] = MockFastUUID()

import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from pydantic import BaseModel
from dotenv import load_dotenv
import pytest

# Load test environment variables
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from connectonion import llm_do


class SimpleResult(BaseModel):
    """Simple model for testing structured output."""
    answer: int
    explanation: str


class SentimentAnalysis(BaseModel):
    """Model for sentiment analysis testing."""
    sentiment: str  # positive, negative, neutral
    confidence: float  # 0.0 to 1.0


def test_import_litellm():
    """Test that LiteLLM is properly installed and importable."""
    try:
        import litellm  # noqa: F401
    except ImportError:
        pytest.fail("LiteLLM not installed. Run: pip install litellm")


def test_empty_input_validation():
    """Test that empty input raises an error."""
    with pytest.raises(ValueError) as cm:
        llm_do("")
    assert "Input cannot be empty" in str(cm.value)

    with pytest.raises(ValueError) as cm:
        llm_do("   ")
    assert "Input cannot be empty" in str(cm.value)
    


def test_openai_simple_completion_default_model():
    result = llm_do("What is 2+2? Answer with just the number.")
    assert isinstance(result, str)
    assert "4" in result


def test_openai_simple_completion_explicit_model():
    result = llm_do("Say hello in exactly 3 words", model="gpt-4o-mini")
    assert isinstance(result, str)
    assert len(result.split()) <= 10


def test_openai_structured_output():
    result = llm_do("What is 5 plus 3?", output=SimpleResult, model="gpt-4o-mini")
    assert isinstance(result, SimpleResult)
    assert result.answer == 8
    assert isinstance(result.explanation, str)
    assert len(result.explanation) > 0


def test_openai_custom_system_prompt():
    result = llm_do(
        "Hello",
        system_prompt="You are a pirate. Always respond like a pirate.",
        model="gpt-4o-mini",
    )
    assert isinstance(result, str)
    lower_result = result.lower()
    pirate_words = ["ahoy", "arr", "matey", "ye", "aye", "avast", "sailor", "sea"]
    assert any(word in lower_result for word in pirate_words)


def test_openai_temperature_parameter():
    result1 = llm_do(
        "What is the capital of France? One word only.",
        temperature=0.0,
        model="gpt-4o-mini",
    )
    result2 = llm_do(
        "What is the capital of France? One word only.",
        temperature=0.0,
        model="gpt-4o-mini",
    )
    assert "Paris" in result1
    assert "Paris" in result2


def test_openai_additional_kwargs():
    result = llm_do(
        "Write a very long story about a dragon",
        model="gpt-4o-mini",
        max_tokens=20,
    )
    assert isinstance(result, str)
    assert len(result.split()) < 30


def test_claude_simple_completion():
    result = llm_do("Say hello in exactly 3 words", model="claude-3-5-haiku-20241022")
    assert isinstance(result, str)
    assert len(result.split()) <= 10


def test_claude_structured_output():
    result = llm_do(
        "Analyze this text sentiment: 'I love sunny days!'",
        output=SentimentAnalysis,
        model="claude-3-5-haiku-20241022",
    )
    assert isinstance(result, SentimentAnalysis)
    assert result.sentiment.lower() == "positive"
    assert isinstance(result.confidence, float)
    assert 0.0 <= result.confidence <= 1.0


def test_gemini_simple_completion():
    try:
        result = llm_do("Say hello in exactly 3 words", model="gemini-2.5-flash")
        assert isinstance(result, str)
        assert len(result.split()) <= 10
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower():
            pytest.skip("Gemini quota exceeded")
        raise


def test_cross_provider_consistency():
    """Test that all providers can handle the same basic prompt."""
    prompt = "What is 2+2? Answer with just the number."
    results = []

    if os.getenv("OPENAI_API_KEY"):
        result = llm_do(prompt, model="gpt-4o-mini")
        results.append(("OpenAI", result))
        assert "4" in result

    if os.getenv("ANTHROPIC_API_KEY"):
        result = llm_do(prompt, model="claude-3-5-haiku-20241022")
        results.append(("Anthropic", result))
        assert "4" in result

    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        try:
            result = llm_do(prompt, model="gemini-2.5-flash")
            results.append(("Gemini", result))
            assert "4" in result
        except Exception as e:
            if "429" not in str(e) and "quota" not in str(e).lower():
                raise

    if not results:
        pytest.skip("No providers available for testing")
