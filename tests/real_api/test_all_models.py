"""Parametrized tests for all newest models from each provider.

Tests basic completion and tool calling for each model to ensure
the LLM abstraction works correctly across all supported models.

Run selectively to control costs:
    pytest tests/real_api/test_all_models.py -v                    # All models
    pytest tests/real_api/test_all_models.py -k "openai" -v        # OpenAI only
    pytest tests/real_api/test_all_models.py -k "anthropic" -v     # Anthropic only
    pytest tests/real_api/test_all_models.py -k "gemini" -v        # Gemini only
"""

import pytest
from connectonion import Agent

from tests.real_api.conftest import (
    requires_openai,
    requires_anthropic,
    requires_gemini,
)


# =============================================================================
# Model Lists - Newest models from each provider
# =============================================================================

OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "o1-mini",
    # "o1",        # Expensive, enable if needed
    # "o4-mini",   # May not be available yet
]

ANTHROPIC_MODELS = [
    "claude-sonnet-4",
    "claude-3-5-haiku-latest",
    # "claude-opus-4",  # Expensive, enable if needed
]

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3-pro-preview",
]

OPENONION_MODELS = [
    "co/gpt-4o-mini",
    "co/gemini-2.5-flash",
]


# =============================================================================
# Basic Completion Tests
# =============================================================================

@requires_openai
@pytest.mark.parametrize("model", OPENAI_MODELS)
def test_openai_basic_completion(model):
    """Test basic completion with OpenAI models."""
    agent = Agent("test", model=model)
    response = agent.input("What is 2+2? Reply with just the number.")
    assert "4" in response


@requires_anthropic
@pytest.mark.parametrize("model", ANTHROPIC_MODELS)
def test_anthropic_basic_completion(model):
    """Test basic completion with Anthropic Claude models."""
    agent = Agent("test", model=model)
    response = agent.input("What is 2+2? Reply with just the number.")
    assert "4" in response


@requires_gemini
@pytest.mark.parametrize("model", GEMINI_MODELS)
def test_gemini_basic_completion(model):
    """Test basic completion with Google Gemini models."""
    agent = Agent("test", model=model)
    response = agent.input("What is 2+2? Reply with just the number.")
    assert "4" in response


# =============================================================================
# Tool Calling Tests
# =============================================================================

def calculator(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


@requires_openai
@pytest.mark.parametrize("model", OPENAI_MODELS)
def test_openai_tool_calling(model):
    """Test tool calling with OpenAI models."""
    agent = Agent("test", model=model, tools=[calculator])
    response = agent.input("Use the calculator to add 5 and 3")
    assert "8" in response


@requires_anthropic
@pytest.mark.parametrize("model", ANTHROPIC_MODELS)
def test_anthropic_tool_calling(model):
    """Test tool calling with Anthropic Claude models."""
    agent = Agent("test", model=model, tools=[calculator])
    response = agent.input("Use the calculator to add 5 and 3")
    assert "8" in response


@requires_gemini
@pytest.mark.parametrize("model", GEMINI_MODELS)
def test_gemini_tool_calling(model):
    """Test tool calling with Google Gemini models."""
    agent = Agent("test", model=model, tools=[calculator])
    response = agent.input("Use the calculator to add 5 and 3")
    assert "8" in response


# =============================================================================
# OpenOnion Managed Keys Tests
# =============================================================================

@pytest.mark.parametrize("model", OPENONION_MODELS)
def test_openonion_basic_completion(model, auth_token, monkeypatch):
    """Test basic completion with OpenOnion managed keys."""
    monkeypatch.setenv("OPENONION_API_KEY", auth_token)
    agent = Agent("test", model=model)
    response = agent.input("What is 2+2? Reply with just the number.")
    assert "4" in response


@pytest.mark.parametrize("model", OPENONION_MODELS)
def test_openonion_tool_calling(model, auth_token, monkeypatch):
    """Test tool calling with OpenOnion managed keys."""
    monkeypatch.setenv("OPENONION_API_KEY", auth_token)
    agent = Agent("test", model=model, tools=[calculator])
    response = agent.input("Use the calculator to add 5 and 3")
    assert "8" in response
