"""Tests for LLM functionality including multi-LLM support."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dotenv import load_dotenv
import pytest
from pydantic import BaseModel, ValidationError
from typing import Optional

# Load environment variables from tests/.env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()


# Test models for structured output
class SimpleModel(BaseModel):
    """Simple test model."""
    value: str
    count: int


class Analysis(BaseModel):
    """Test analysis model."""
    sentiment: str
    confidence: float
    keywords: list[str]


class ComplexModel(BaseModel):
    """Complex nested model for testing."""
    title: str
    metadata: dict
    items: list[str]
    score: Optional[float] = None


class TestLLMFunction:
    """Test the llm_do() one-shot function."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.api_key = os.getenv("OPENAI_API_KEY")
        yield
        # Teardown
        import shutil
        shutil.rmtree(self.temp_dir)

    # -------------------------------------------------------------------------
    # Real API Tests (marked for separate execution)
    # -------------------------------------------------------------------------

    @pytest.mark.real_api
    def test_real_api_simple_call(self):
        """Test real API call with simple string."""
        if not self.api_key:
            pytest.skip("OPENAI_API_KEY not found")

        from connectonion import llm_do
        result = llm_do("What is 2+2? Reply with just the number.", model="gpt-4o-mini")

        assert result is not None
        assert "4" in result

    @pytest.mark.real_api
    def test_real_api_structured_output(self):
        """Test real API with structured Pydantic output."""
        if not self.api_key:
            pytest.skip("OPENAI_API_KEY not found")

        from connectonion import llm_do

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

    @pytest.mark.real_api
    def test_real_api_with_system_prompt(self):
        """Test real API with custom system prompt."""
        if not self.api_key:
            pytest.skip("OPENAI_API_KEY not found")

        from connectonion import llm_do
        result = llm_do(
            "Bonjour",
            system_prompt="You are a translator. Translate from French to English only. Be concise.",
            model="gpt-4o-mini"
        )

        assert result is not None
        # Check for common translations
        result_lower = result.lower()
        assert "hello" in result_lower or "good" in result_lower

    # -------------------------------------------------------------------------
    # Edge Cases
    # -------------------------------------------------------------------------

    def test_empty_input(self):
        """Test handling of empty input."""
        from connectonion import llm_do
        with pytest.raises(ValueError):
            llm_do("")


class TestMultiLLMSupport:
    """Test multi-LLM support across OpenAI, Anthropic, and Google."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Set up test fixtures."""
        self.has_openai = bool(os.getenv("OPENAI_API_KEY"))
        self.has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
        self.has_google = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

    @pytest.mark.real_api
    def test_openai_model(self):
        """Test OpenAI model integration."""
        if not self.has_openai:
            pytest.skip("OPENAI_API_KEY not found")

        from connectonion import Agent
        agent = Agent("test_openai", model="gpt-4o-mini")
        response = agent.input("Say hello in 5 words or less")

        assert response is not None
        assert isinstance(response, str)
        assert len(response.split()) <= 10  # Allow some flexibility

    @pytest.mark.real_api
    def test_anthropic_model(self):
        """Test Anthropic Claude model integration."""
        if not self.has_anthropic:
            pytest.skip("ANTHROPIC_API_KEY not found")

        from connectonion import Agent
        agent = Agent("test_anthropic", model="claude-3-5-haiku-20241022")
        response = agent.input("Say hello in 5 words or less")

        assert response is not None
        assert isinstance(response, str)

    @pytest.mark.real_api
    def test_google_gemini_model(self):
        """Test Google Gemini model integration."""
        if not self.has_google:
            pytest.skip("GEMINI_API_KEY not found")

        from connectonion import Agent
        agent = Agent("test_gemini", model="gemini-2.5-flash")
        response = agent.input("Say hello in 5 words or less")

        assert response is not None
        assert isinstance(response, str)

    @pytest.mark.real_api
    def test_tool_use_across_models(self):
        """Test tool use functionality across different LLM providers."""
        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b

        # Test OpenAI with tools
        if self.has_openai:
            from connectonion import Agent
            agent = Agent("openai_tools", model="gpt-4o-mini", tools=[add_numbers])
            response = agent.input("What is 25 plus 17?")
            assert "42" in str(response)

        # Test Anthropic with tools
        if self.has_anthropic:
            from connectonion import Agent
            agent = Agent("anthropic_tools", model="claude-3-5-haiku-20241022", tools=[add_numbers])
            response = agent.input("What is 25 plus 17?")
            assert "42" in str(response)

        # Test Gemini with tools
        if self.has_google:
            from connectonion import Agent
            agent = Agent("gemini_tools", model="gemini-2.5-flash", tools=[add_numbers])
            response = agent.input("What is 25 plus 17?")
            assert "42" in str(response)

    def test_model_registry(self):
        """Test that model registry correctly maps models to providers."""
        from connectonion.core.llm import MODEL_REGISTRY

        # Test OpenAI models
        assert MODEL_REGISTRY["gpt-4o"] == "openai"
        assert MODEL_REGISTRY["gpt-4o-mini"] == "openai"
        assert MODEL_REGISTRY["o1"] == "openai"
        assert MODEL_REGISTRY["o4-mini"] == "openai"

        # Test Anthropic models
        assert MODEL_REGISTRY["claude-3-5-sonnet-20241022"] == "anthropic"
        assert MODEL_REGISTRY["claude-3-5-haiku-20241022"] == "anthropic"
        assert MODEL_REGISTRY["claude-opus-4.1"] == "anthropic"

        # Test Google models
        assert MODEL_REGISTRY["gemini-3-pro-preview"] == "google"
        assert MODEL_REGISTRY["gemini-3-pro-image-preview"] == "google"
        assert MODEL_REGISTRY["gemini-2.5-flash"] == "google"

    def test_create_llm_factory(self):
        """Test the create_llm factory function."""
        from connectonion.core.llm import create_llm, OpenAILLM, AnthropicLLM, GeminiLLM

        # Test OpenAI model creation
        if self.has_openai:
            llm = create_llm("gpt-4o-mini")
            assert isinstance(llm, OpenAILLM)

        # Test Anthropic model creation
        if self.has_anthropic:
            llm = create_llm("claude-3-5-haiku-20241022")
            assert isinstance(llm, AnthropicLLM)

        # Test Google model creation
        if self.has_google:
            llm = create_llm("gemini-2.5-flash")
            assert isinstance(llm, GeminiLLM)

    def test_model_inference_from_name(self):
        """Test that model provider is correctly inferred from model name."""
        from connectonion.core.llm import create_llm

        # Test inference for models not in registry
        if self.has_openai:
            llm = create_llm("gpt-new-model-xyz")  # Starts with 'gpt'
            from connectonion.core.llm import OpenAILLM
            assert isinstance(llm, OpenAILLM)

        if self.has_anthropic:
            llm = create_llm("claude-future-model")  # Starts with 'claude'
            from connectonion.core.llm import AnthropicLLM
            assert isinstance(llm, AnthropicLLM)

        if self.has_google:
            llm = create_llm("gemini-next-gen")  # Starts with 'gemini'
            from connectonion.core.llm import GeminiLLM
            assert isinstance(llm, GeminiLLM)


class TestGeminiTools:
    """Test Google Gemini tool calling specifically."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Set up test fixtures."""
        self.has_google = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

    @pytest.mark.real_api
    def test_gemini_simple_tool_call(self):
        """Test simple tool call with Gemini."""
        if not self.has_google:
            pytest.skip("GEMINI_API_KEY not found")

        from connectonion import Agent

        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b

        agent = Agent("gemini_calc", model="gemini-2.5-flash", tools=[add_numbers])
        response = agent.input("What is 15 plus 27? Please use the add_numbers tool.")

        assert response is not None
        assert "42" in str(response)

    @pytest.mark.real_api
    def test_gemini_multiple_tools(self):
        """Test Gemini with multiple tools available."""
        if not self.has_google:
            pytest.skip("GEMINI_API_KEY not found")

        from connectonion import Agent

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

    @pytest.mark.real_api
    def test_gemini_without_tools(self):
        """Test Gemini response without tools."""
        if not self.has_google:
            pytest.skip("GEMINI_API_KEY not found")

        from connectonion import Agent
        agent = Agent("gemini_chat", model="gemini-2.5-flash")
        response = agent.input("What is the capital of France?")

        assert response is not None
        assert "Paris" in response
