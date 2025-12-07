"""Tests for multi-LLM model support across OpenAI, Google, and Anthropic.

Uses decorators from conftest.py for skip conditions - no inline skips.
"""

import os
import time
from unittest.mock import Mock, patch

import pytest
from connectonion import Agent

from tests.real_api.conftest import (
    requires_openai,
    requires_anthropic,
    requires_gemini,
    requires_any_provider,
    requires_multiple_providers,
)


# =============================================================================
# Test Tools
# =============================================================================

def simple_calculator(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


def get_greeting(name: str) -> str:
    """Generate a greeting for a person."""
    return f"Hello, {name}!"


def process_data(data: str, uppercase: bool = False) -> str:
    """Process text data with optional uppercase conversion."""
    return data.upper() if uppercase else data.lower()


def _tools():
    return [simple_calculator, get_greeting, process_data]


# =============================================================================
# Model Detection Tests (unit tests, no API needed)
# =============================================================================

def test_model_detection_openai():
    """Test OpenAI model name patterns."""
    models = ["o4-mini", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "o1", "o1-mini"]
    for model in models:
        assert model.startswith("gpt") or model.startswith("o")


def test_model_detection_google():
    """Test Gemini model name patterns."""
    models = [
        "gemini-2.5-pro",
        "gemini-2.0-flash-exp",
        "gemini-2.0-flash-thinking-exp",
        "gemini-2.5-flash",
        "gemini-1.5-flash-8b",
    ]
    for model in models:
        assert model.startswith("gemini")


def test_model_detection_anthropic():
    """Test Anthropic model name patterns."""
    models = [
        "claude-opus-4.1",
        "claude-opus-4",
        "claude-sonnet-4",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
    ]
    for model in models:
        assert model.startswith("claude")


def test_select_model_for_code_generation():
    """Test smart model selection based on use case."""
    def select_model_for_task(task_type):
        mapping = {
            "code": "o4-mini",
            "reasoning": "gemini-2.5-pro",
            "fast": "gpt-4o-mini",
            "long_context": "gemini-2.5-pro",
        }
        return mapping.get(task_type, "o4-mini")

    assert select_model_for_task("code") == "o4-mini"
    assert select_model_for_task("reasoning") == "gemini-2.5-pro"
    assert select_model_for_task("fast") == "gpt-4o-mini"
    assert select_model_for_task("long_context") == "gemini-2.5-pro"


# =============================================================================
# Agent Creation Tests (mocked)
# =============================================================================

@patch('connectonion.llm.OpenAILLM')
def test_create_agent_with_openai(mock_openai):
    """Test creating an agent with OpenAI model (mocked)."""
    mock_instance = Mock()
    mock_instance.model = "o4-mini"
    mock_openai.return_value = mock_instance

    agent = Agent("test_o4", model="o4-mini")
    assert agent.name == "test_o4"


# =============================================================================
# Tool Compatibility Tests
# =============================================================================

@requires_any_provider
def test_tools_work_across_all_models():
    """Test that the same tools work with all model providers."""
    tools = _tools()
    test_cases = []

    if os.getenv("OPENAI_API_KEY"):
        test_cases.append(("gpt-4o-mini", "openai"))
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        test_cases.append(("gemini-2.5-flash", "google"))
    if os.getenv("ANTHROPIC_API_KEY"):
        test_cases.append(("claude-3-5-haiku-latest", "anthropic"))

    for model, provider in test_cases:
        agent = Agent(f"test_{provider}", model=model, tools=tools)
        assert len(agent.tools) == 3
        assert "simple_calculator" in agent.tools
        assert "get_greeting" in agent.tools
        assert "process_data" in agent.tools


# =============================================================================
# Integration Tests (require actual API keys)
# =============================================================================

@requires_openai
def test_openai_real_call():
    """Test actual API call with OpenAI model."""
    tools = _tools()
    agent = Agent("test", model="gpt-4o-mini", tools=tools)
    response = agent.input("Use the simple_calculator tool to add 5 and 3")
    assert "8" in response


@requires_gemini
def test_gemini_real_call():
    """Test actual API call with Gemini model."""
    tools = _tools()
    agent = Agent("test", model="gemini-2.5-flash", tools=tools)
    response = agent.input("Use the get_greeting tool to greet 'Alice'")
    assert "Alice" in response


@requires_anthropic
def test_anthropic_real_call():
    """Test actual API call with Claude model."""
    tools = _tools()
    agent = Agent("test", model="claude-3-5-haiku-latest", tools=tools)
    response = agent.input("Use the process_data tool to convert 'Hello' to uppercase")
    assert "HELLO" in response


# =============================================================================
# Model Comparison Tests
# =============================================================================

@requires_multiple_providers
def test_flagship_model_comparison():
    """Test that flagship models from each provider can handle the same prompt."""
    prompt = "What is 2 + 2?"
    flagship_models = []

    if os.getenv("OPENAI_API_KEY"):
        flagship_models.append(("gpt-4o-mini", "openai"))
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        flagship_models.append(("gemini-2.5-flash", "google"))
    if os.getenv("ANTHROPIC_API_KEY"):
        flagship_models.append(("claude-3-5-haiku-latest", "anthropic"))

    for model, provider in flagship_models:
        agent = Agent(f"compare_{provider}", model=model)
        response = agent.input(prompt)
        assert "4" in response.lower()


# =============================================================================
# Performance Tests
# =============================================================================

@pytest.mark.benchmark
@requires_any_provider
def test_fast_model_performance():
    """Test that fast models initialize quickly."""
    fast_models = []

    if os.getenv("OPENAI_API_KEY"):
        fast_models.append("gpt-4o-mini")
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        fast_models.append("gemini-2.5-flash")
    if os.getenv("ANTHROPIC_API_KEY"):
        fast_models.append("claude-3-5-haiku-latest")

    for model in fast_models:
        start_time = time.time()
        Agent("perf_test", model=model)
        initialization_time = time.time() - start_time
        assert initialization_time < 2.0, f"Model {model} init took {initialization_time:.2f}s"
