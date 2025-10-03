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


@pytest.mark.real_api
@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"),
    reason="No Gemini API key"
)
class TestRealGemini:
    """Test real Google Gemini API integration."""

    def test_gemini_basic_completion(self):
        """Test basic completion with Gemini."""
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        llm = GeminiLLM(api_key=api_key, model="gemini-pro")
        agent = Agent(name="gemini_test", llm=llm)

        response = agent.input("Say 'Hello from Gemini' exactly")
        assert response.content is not None
        assert "Hello from Gemini" in response.content

    def test_gemini_with_tools(self):
        """Test Gemini with tool calling."""
        agent = Agent(
            name="gemini_tools",
            model="gemini-pro",
            tools=[word_counter]
        )

        response = agent.input("Count the words in 'The quick brown fox'")
        assert response.content is not None
        assert "4" in response.content or "four" in response.content.lower()

    def test_gemini_multi_turn(self):
        """Test multi-turn conversation with Gemini."""
        agent = Agent(
            name="gemini_conversation",
            model="gemini-pro"
        )

        # First turn
        response = agent.input("My favorite color is blue. Remember this.")
        assert response.content is not None

        # Second turn - should remember context
        response = agent.input("What's my favorite color?")
        assert response.content is not None
        assert "blue" in response.content.lower()

    def test_gemini_different_models(self):
        """Test different Gemini models."""
        models = ["gemini-pro", "gemini-1.5-pro-latest"]

        for model in models:
            if "1.5-pro" in model and not os.getenv("TEST_EXPENSIVE_MODELS"):
                continue  # Skip expensive models unless explicitly enabled

            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            agent = Agent(
                name=f"gemini_{model.replace('.', '_').replace('-', '_')}",
                llm=GeminiLLM(api_key=api_key, model=model)
            )

            response = agent.input("Reply with OK")
            assert response.content is not None
            assert len(response.content) > 0

    def test_gemini_system_prompt(self):
        """Test Gemini with custom system prompt."""
        agent = Agent(
            name="gemini_system",
            model="gemini-pro",
            system_prompt="You are a helpful math tutor. Always explain your reasoning step by step."
        )

        response = agent.input("What is 2 + 2?")
        assert response.content is not None
        assert "4" in response.content or "four" in response.content.lower()