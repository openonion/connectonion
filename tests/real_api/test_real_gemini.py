"""
Real Google Gemini API tests.

These tests make actual API calls to Google Gemini and cost real money.
Run with: pytest test_real_gemini.py -v

Requires: GEMINI_API_KEY environment variable (GOOGLE_API_KEY also supported for backward compatibility)
"""

import os
import pytest
from pathlib import Path
from dotenv import load_dotenv
from connectonion import Agent
from connectonion.llm import GeminiLLM

# Load environment variables from tests/.env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


def word_counter(text: str) -> str:
    """Count words in text for testing."""
    words = text.split()
    return f"Word count: {len(words)}"


class TestRealGemini:
    """Test real Google Gemini API integration."""

    def test_gemini_basic_completion(self):
        """Test basic completion with Gemini."""
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        llm = GeminiLLM(api_key=api_key, model="gemini-2.5-pro")
        agent = Agent(name="gemini_test", llm=llm)

        response = agent.input("Say 'Hello from Gemini' exactly")
        assert response is not None
        assert "Hello from Gemini" in response

    def test_gemini_with_tools(self):
        """Test Gemini with tool calling."""
        agent = Agent(
            name="gemini_tools",
            model="gemini-2.5-pro",
            tools=[word_counter]
        )

        response = agent.input("Count the words in 'The quick brown fox'")
        assert response is not None
        assert "4" in response or "four" in response.lower()

    def test_gemini_multi_turn(self):
        """Test multi-turn conversation with Gemini."""
        agent = Agent(
            name="gemini_conversation",
            model="gemini-2.5-pro"
        )

        # First turn
        response = agent.input("My favorite color is blue. Remember this.")
        assert response is not None

        # Second turn - should remember context
        response = agent.input("What's my favorite color?")
        assert response is not None
        assert "blue" in response.lower()

    def test_gemini_different_models(self):
        """Test different Gemini models."""
        models = ["gemini-2.5-pro", "gemini-2.5-flash"]

        for model in models:

            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            agent = Agent(
                name=f"gemini_{model.replace('.', '_').replace('-', '_')}",
                llm=GeminiLLM(api_key=api_key, model=model)
            )

            response = agent.input("Reply with OK")
            assert response is not None
            assert len(response) > 0

    def test_gemini_system_prompt(self):
        """Test Gemini with custom system prompt."""
        agent = Agent(
            name="gemini_system",
            model="gemini-2.5-pro",
            system_prompt="You are a helpful math tutor. Always explain your reasoning step by step."
        )

        response = agent.input("What is 2 + 2?")
        assert response is not None
        assert "4" in response or "four" in response.lower()


class TestRealGemini3:
    """Test real Gemini 3 API integration (thinking models).

    Gemini 3 models use dynamic thinking by default and may return
    thought_signatures that must be echoed back for tool calling.
    See: https://ai.google.dev/gemini-api/docs/thinking
    """

    def test_gemini3_basic_completion(self):
        """Test basic completion with Gemini 3 Pro Preview."""
        agent = Agent(
            name="gemini3_basic",
            model="gemini-3-pro-preview"
        )

        response = agent.input("Say 'Hello from Gemini 3' exactly")
        assert response is not None
        assert "Hello" in response or "Gemini" in response

    def test_gemini3_with_tools_single_call(self):
        """Test Gemini 3 with single tool call.

        Verifies that null extra_content doesn't break tool calling.
        """
        agent = Agent(
            name="gemini3_tools_single",
            model="gemini-3-pro-preview",
            tools=[word_counter]
        )

        response = agent.input("Count words in 'one two three'")
        assert response is not None
        assert "3" in response or "three" in response.lower()

    def test_gemini3_with_tools_multi_turn(self):
        """Test Gemini 3 multi-turn tool calling.

        This specifically tests the fix for null value handling.
        The second turn requires messages from first turn to be
        sent back correctly without null values.
        """
        agent = Agent(
            name="gemini3_tools_multi",
            model="gemini-3-pro-preview",
            tools=[word_counter],
            max_iterations=5
        )

        # First turn - tool call
        response = agent.input("Count words in 'hello world'")
        assert response is not None
        assert "2" in response or "two" in response.lower()

        # Second turn - another tool call (tests message history handling)
        response = agent.input("Now count words in 'a b c d e'")
        assert response is not None
        assert "5" in response or "five" in response.lower()

    def test_gemini3_all_models(self):
        """Test all Gemini 3 model variants."""
        models = [
            "gemini-3-pro-preview",
            # "gemini-3-pro-image-preview",  # May have different capabilities
        ]

        for model in models:
            agent = Agent(
                name=f"gemini3_{model.replace('-', '_')}",
                model=model
            )

            response = agent.input("Reply with OK")
            assert response is not None
            assert len(response) > 0


class TestAllGeminiModelsWithTools:
    """Comprehensive test for all Gemini models with tool calling.

    These tests verify that null value handling works across all models.
    """

    @pytest.mark.parametrize("model", [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-3-pro-preview",
    ])
    def test_model_with_tool_calling(self, model):
        """Test each model can handle tool calling without null value errors."""
        agent = Agent(
            name=f"test_{model.replace('-', '_').replace('.', '_')}",
            model=model,
            tools=[word_counter],
            max_iterations=3
        )

        response = agent.input("Use the word_counter tool to count words in 'test'")
        assert response is not None
        # Should complete without "Value is not a struct: null" error