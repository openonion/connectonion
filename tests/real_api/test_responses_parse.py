"""Test structured output with managed keys for ALL models from billing.py.

This ensures llm_do() with Pydantic output works for all providers via OpenOnion proxy.
Uses beta.chat.completions.parse() which routes through /v1/chat/completions.

Run selectively:
    pytest tests/real_api/test_responses_parse.py -v                    # All models
    pytest tests/real_api/test_responses_parse.py -k "openai" -v        # OpenAI only
    pytest tests/real_api/test_responses_parse.py -k "gemini" -v        # Gemini only
    pytest tests/real_api/test_responses_parse.py -k "anthropic" -v     # Anthropic only
"""

import pytest
from pydantic import BaseModel
from connectonion import llm_do


class MathAnswer(BaseModel):
    """Simple structured output for testing."""
    result: int
    explanation: str


# =============================================================================
# Model Lists from billing.py (grouped by provider)
# =============================================================================

OPENAI_MODELS = [
    "co/gpt-4o-mini",
    "co/gpt-4o",
    "co/gpt-5",
    "co/gpt-5-mini",
    "co/gpt-5-nano",
    "co/o4-mini",
]

GEMINI_MODELS = [
    "co/gemini-2.5-flash",
    "co/gemini-2.5-flash-lite",
    "co/gemini-2.5-pro",
    "co/gemini-2.0-flash",
    "co/gemini-2.0-flash-lite",
    "co/gemini-3-flash-preview",
    "co/gemini-3-pro-preview",
]

# Note: Only Claude 4.5/4.1 models support structured outputs (per Anthropic docs Dec 2025)
# Legacy models (claude-sonnet-4, claude-opus-4) do NOT support structured outputs
ANTHROPIC_MODELS = [
    "co/claude-haiku-4-5",
    "co/claude-sonnet-4-5",
    "co/claude-opus-4-5",
    "co/claude-opus-4-1",
]

# Combine all models for comprehensive testing
ALL_MANAGED_MODELS = OPENAI_MODELS + GEMINI_MODELS + ANTHROPIC_MODELS


# =============================================================================
# Parametrized Tests for Each Provider
# =============================================================================

@pytest.mark.parametrize("model", OPENAI_MODELS, ids=lambda m: m.replace("co/", ""))
def test_openai_structured_output(model, auth_token, monkeypatch):
    """Test structured output with OpenAI models via managed keys."""
    monkeypatch.setenv("OPENONION_API_KEY", auth_token)

    result = llm_do(
        "What is 2 + 2? Give the result and a brief explanation.",
        output=MathAnswer,
        model=model
    )

    assert isinstance(result, MathAnswer)
    assert result.result == 4
    assert len(result.explanation) > 0
    print(f"\n✓ {model}: result={result.result}, explanation={result.explanation[:50]}...")


@pytest.mark.parametrize("model", GEMINI_MODELS, ids=lambda m: m.replace("co/", ""))
def test_gemini_structured_output(model, auth_token, monkeypatch):
    """Test structured output with Gemini models via managed keys."""
    monkeypatch.setenv("OPENONION_API_KEY", auth_token)

    result = llm_do(
        "What is 2 + 2? Give the result and a brief explanation.",
        output=MathAnswer,
        model=model
    )

    assert isinstance(result, MathAnswer)
    assert result.result == 4
    assert len(result.explanation) > 0
    print(f"\n✓ {model}: result={result.result}, explanation={result.explanation[:50]}...")


@pytest.mark.parametrize("model", ANTHROPIC_MODELS, ids=lambda m: m.replace("co/", ""))
def test_anthropic_structured_output(model, auth_token, monkeypatch):
    """Test structured output with Anthropic models via managed keys."""
    monkeypatch.setenv("OPENONION_API_KEY", auth_token)

    result = llm_do(
        "What is 2 + 2? Give the result and a brief explanation.",
        output=MathAnswer,
        model=model
    )

    assert isinstance(result, MathAnswer)
    assert result.result == 4
    assert len(result.explanation) > 0
    print(f"\n✓ {model}: result={result.result}, explanation={result.explanation[:50]}...")


