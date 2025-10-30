"""
Real OpenAI API tests.

These tests make actual API calls to OpenAI and cost real money.
Run with: pytest test_real_openai.py -v

Requires: OPENAI_API_KEY environment variable
"""

import os
import pytest
from pathlib import Path
from dotenv import load_dotenv
from connectonion import Agent
from connectonion.llm import OpenAILLM

# Load environment variables from tests/.env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


def calculator(expression: str) -> str:
    """Simple calculator for testing."""
    try:
        result = eval(expression)
        return f"Result: {result}"
    except:
        return "Error in calculation"


@pytest.mark.real_api
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
class TestRealOpenAI:
    """Test real OpenAI API integration."""

    def test_openai_basic_completion(self):
        """Test basic completion with OpenAI."""
        llm = OpenAILLM(model="gpt-4o-mini")
        agent = Agent(name="openai_test", llm=llm)

        response = agent.input("Say 'Hello from OpenAI' exactly")
        assert response.content is not None
        assert "Hello from OpenAI" in response.content

    def test_openai_with_tools(self):
        """Test OpenAI with tool calling."""
        agent = Agent(
            name="openai_tools",
            model="gpt-4o-mini",
            tools=[calculator]
        )

        response = agent.input("Calculate 42 * 2")
        assert response.content is not None
        assert "84" in response.content

    def test_openai_multi_turn(self):
        """Test multi-turn conversation with OpenAI."""
        agent = Agent(
            name="openai_conversation",
            model="gpt-4o-mini"
        )

        # First turn
        response = agent.input("My name is Alice. Remember this.")
        assert response.content is not None

        # Second turn - should remember context
        response = agent.input("What's my name?")
        assert response.content is not None
        assert "Alice" in response.content

    def test_openai_streaming(self):
        """Test streaming responses from OpenAI."""
        agent = Agent(
            name="openai_streaming",
            model="gpt-4o-mini",
            stream=True
        )

        response = agent.input("Count from 1 to 5")
        assert response.content is not None
        # Should contain numbers 1 through 5
        for num in ["1", "2", "3", "4", "5"]:
            assert num in response.content

    def test_openai_different_models(self):
        """Test different OpenAI models."""
        models = ["gpt-4o-mini", "gpt-4o"]

        for model in models:
            if model == "gpt-4o" and not os.getenv("TEST_EXPENSIVE_MODELS"):
                continue  # Skip expensive models unless explicitly enabled

            agent = Agent(
                name=f"openai_{model.replace('-', '_')}",
                model=model
            )

            response = agent.input("Reply with OK")
            assert response.content is not None
            assert len(response.content) > 0