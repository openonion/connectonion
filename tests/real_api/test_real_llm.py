"""Real API tests for llm_do() and multi-provider LLM support."""

import os

import pytest
from pydantic import BaseModel

from connectonion import Agent, llm_do
from tests.real_api.conftest import (
    requires_openai,
    requires_anthropic,
    requires_gemini,
    requires_any_provider,
)


pytestmark = pytest.mark.real_api


class TestRealLLMDo:
    """Real API tests for the llm_do() one-shot function."""

    @requires_openai
    def test_real_api_simple_call(self):
        """Test real API call with simple string."""
        result = llm_do("What is 2+2? Reply with just the number.", model="gpt-4o-mini")

        assert result is not None
        assert "4" in result

    @requires_openai
    def test_real_api_structured_output(self):
        """Test real API with structured Pydantic output."""
        class TestResult(BaseModel):
            answer: int
            explanation: str

        result = llm_do(
            "What is 10 times 5?",
            output=TestResult,
            model="gpt-4o-mini"
        )

        assert isinstance(result, TestResult)
        assert result.answer == 50
        assert result.explanation is not None

    @requires_openai
    def test_real_api_with_system_prompt(self):
        """Test real API with custom system prompt."""
        result = llm_do(
            "Bonjour",
            system_prompt="You are a translator. Translate from French to English only. Be concise.",
            model="gpt-4o-mini"
        )

        assert result is not None
        # Check for common translations
        result_lower = result.lower()
        assert "hello" in result_lower or "good" in result_lower


class TestRealMultiLLMSupport:
    """Real API tests across OpenAI, Anthropic, and Google providers."""

    @requires_openai
    def test_openai_model(self):
        """Test OpenAI model integration."""
        agent = Agent("test_openai", model="gpt-4o-mini")
        response = agent.input("Say hello in 5 words or less")

        assert response is not None
        assert isinstance(response, str)
        assert len(response.split()) <= 10  # Allow some flexibility

    @requires_anthropic
    def test_anthropic_model(self):
        """Test Anthropic Claude model integration."""
        agent = Agent("test_anthropic", model="claude-3-5-haiku-20241022")
        response = agent.input("Say hello in 5 words or less")

        assert response is not None
        assert isinstance(response, str)

    @requires_gemini
    def test_google_gemini_model(self):
        """Test Google Gemini model integration."""
        agent = Agent("test_gemini", model="gemini-2.5-flash")
        response = agent.input("Say hello in 5 words or less")

        assert response is not None
        assert isinstance(response, str)

    @requires_any_provider
    def test_tool_use_across_models(self):
        """Test tool use functionality across different LLM providers."""
        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b

        # Test OpenAI with tools
        if os.getenv("OPENAI_API_KEY"):
            agent = Agent("openai_tools", model="gpt-4o-mini", tools=[add_numbers])
            response = agent.input("What is 25 plus 17?")
            assert "42" in str(response)

        # Test Anthropic with tools
        if os.getenv("ANTHROPIC_API_KEY"):
            agent = Agent("anthropic_tools", model="claude-3-5-haiku-20241022", tools=[add_numbers])
            response = agent.input("What is 25 plus 17?")
            assert "42" in str(response)

        # Test Gemini with tools
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            agent = Agent("gemini_tools", model="gemini-2.5-flash", tools=[add_numbers])
            response = agent.input("What is 25 plus 17?")
            assert "42" in str(response)


class TestRealGeminiTools:
    """Real API tests for Google Gemini tool calling."""

    @requires_gemini
    def test_gemini_simple_tool_call(self):
        """Test simple tool call with Gemini."""
        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b

        agent = Agent("gemini_calc", model="gemini-2.5-flash", tools=[add_numbers])
        response = agent.input("What is 15 plus 27? Please use the add_numbers tool.")

        assert response is not None
        assert "42" in str(response)

    @requires_gemini
    def test_gemini_multiple_tools(self):
        """Test Gemini with multiple tools available."""
        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b

        def multiply_numbers(x: float, y: float) -> float:
            """Multiply two numbers."""
            return x * y

        agent = Agent("gemini_multi", model="gemini-2.5-flash",
                     tools=[add_numbers, multiply_numbers])
        response = agent.input("First add 10 and 20, then multiply 5 by 6. Use the tools.")

        assert response is not None
        # Should mention both results
        response_str = str(response)
        assert "30" in response_str or "30.0" in response_str

    @requires_gemini
    def test_gemini_without_tools(self):
        """Test Gemini response without tools."""
        agent = Agent("gemini_chat", model="gemini-2.5-flash")
        response = agent.input("What is the capital of France?")

        assert response is not None
        assert "Paris" in response
