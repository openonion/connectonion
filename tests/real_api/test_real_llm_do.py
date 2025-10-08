"""
Real API tests for the llm_do function with structured output.

These tests make actual API calls to various providers and may cost money.
Run with: pytest tests/test_real_llm_do.py -v

Requires API keys for OpenAI, Anthropic, and Gemini set in the environment.
"""

import os
import pytest
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from connectonion import llm_do

# Load environment variables from tests/.env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


# Define a Pydantic model for testing structured output
class CharacterAnalysis(BaseModel):
    """A model to hold the analysis of a fictional character."""
    name: str = Field(description="The name of the character.")
    role: str = Field(description="The character's primary role in their story (e.g., protagonist, antagonist, sidekick).")
    power_level: int = Field(description="An estimated power level for the character, on a scale of 1 to 100.")


@pytest.mark.real_api
class TestRealLLMDoStructuredOutput:
    """Test llm_do with real API calls for structured output."""

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_structured_output_openai(self):
        """Test structured output with an OpenAI model."""
        result = llm_do(
            "Analyze the character 'Frodo Baggins' from The Lord of the Rings.",
            output=CharacterAnalysis,
            model="gpt-4o-mini"
        )
        assert isinstance(result, CharacterAnalysis)
        assert result.name.lower() == "frodo baggins"
        assert result.role.lower() == "protagonist"
        assert 1 <= result.power_level <= 100

    @pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No Anthropic API key")
    def test_structured_output_anthropic(self):
        """Test structured output with an Anthropic model."""
        result = llm_do(
            "Analyze the character 'Sherlock Holmes'.",
            output=CharacterAnalysis,
            model="claude-3-5-haiku-20241022"
        )
        assert isinstance(result, CharacterAnalysis)
        assert result.name.lower() == "sherlock holmes"
        assert result.role.lower() == "protagonist"
        assert 1 <= result.power_level <= 100

    @pytest.mark.skipif(not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")), reason="No Gemini API key")
    def test_structured_output_gemini(self):
        """Test structured output with a Google Gemini model."""
        result = llm_do(
            "Analyze the character 'Darth Vader' from Star Wars.",
            output=CharacterAnalysis,
            model="gemini-pro"
        )
        assert isinstance(result, CharacterAnalysis)
        assert result.name.lower() == "darth vader"
        assert result.role.lower() == "antagonist"
        assert 1 <= result.power_level <= 100

    @pytest.mark.skipif(not os.getenv("OPENONION_API_KEY"), reason="No OpenOnion API key for co/ models")
    def test_structured_output_connectonion(self):
        """Test structured output with a ConnectOnion managed (co/) model."""
        result = llm_do(
            "Analyze the character 'Harry Potter'.",
            output=CharacterAnalysis,
            model="co/gpt-4o-mini"
        )
        assert isinstance(result, CharacterAnalysis)
        assert result.name.lower() == "harry potter"
        assert result.role.lower() == "protagonist"
        assert 1 <= result.power_level <= 100
