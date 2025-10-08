"""
Real Anthropic API tests.

These tests make actual API calls to Anthropic and cost real money.
Run with: pytest test_real_anthropic.py -v

Requires: ANTHROPIC_API_KEY environment variable
"""

import os
import pytest
from pathlib import Path
from dotenv import load_dotenv
from connectonion import Agent
from connectonion.llm import AnthropicLLM

# Load environment variables from tests/.env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


def text_processor(text: str) -> str:
    """Simple text processor for testing."""
    return f"Processed: {text.upper()}"


@pytest.mark.real_api
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No Anthropic API key")
class TestRealAnthropic:
    """Test real Anthropic API integration."""

    def test_anthropic_basic_completion(self):
        """Test basic completion with Anthropic."""
        llm = AnthropicLLM(model="claude-3-haiku-20240307")
        agent = Agent(name="anthropic_test", llm=llm)

        response = agent.input("Say 'Hello from Claude' exactly")
        assert response.content is not None
        assert "Hello from Claude" in response.content

    def test_anthropic_with_tools(self):
        """Test Anthropic with tool calling."""
        agent = Agent(
            name="anthropic_tools",
            model="claude-3-haiku-20240307",
            tools=[text_processor]
        )

        response = agent.input("Process the text 'hello world'")
        assert response.content is not None
        assert "HELLO WORLD" in response.content or "processed" in response.content.lower()

    def test_anthropic_multi_turn(self):
        """Test multi-turn conversation with Anthropic."""
        agent = Agent(
            name="anthropic_conversation",
            model="claude-3-haiku-20240307"
        )

        # First turn
        response = agent.input("I'm learning Python. Remember this.")
        assert response.content is not None

        # Second turn - should remember context
        response = agent.input("What programming language am I learning?")
        assert response.content is not None
        assert "Python" in response.content

    def test_anthropic_different_models(self):
        """Test different Anthropic models."""
        models = [
            "claude-3-haiku-20240307",
            "claude-3-sonnet-20240229",
            "claude-3-opus-20240229"
        ]

        for model in models:
            if "opus" in model and not os.getenv("TEST_EXPENSIVE_MODELS"):
                continue  # Skip expensive models unless explicitly enabled

            agent = Agent(
                name=f"anthropic_{model.split('-')[2]}",
                model=model
            )

            response = agent.input("Reply with OK")
            assert response.content is not None
            assert len(response.content) > 0

    def test_anthropic_system_prompt(self):
        """Test Anthropic with custom system prompt."""
        agent = Agent(
            name="anthropic_system",
            model="claude-3-haiku-20240307",
            system_prompt="You are a helpful poetry assistant. Always respond in haiku format."
        )

        response = agent.input("Tell me about the weather")
        assert response.content is not None
        # Check it's attempting haiku format (3 lines, roughly)
        lines = response.content.strip().split('\n')
        assert len(lines) >= 1  # At least has content