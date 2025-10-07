"""Comprehensive tests for llm_do with multi-LLM support via LiteLLM."""

import sys
import uuid as standard_uuid

# Fix for fastuuid dependency issue in LiteLLM
class MockFastUUID:
    @staticmethod
    def uuid4():
        return str(standard_uuid.uuid4())
    
    UUID = standard_uuid.UUID

sys.modules['fastuuid'] = MockFastUUID()

import unittest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from pydantic import BaseModel
from dotenv import load_dotenv
import pytest

# Load test environment variables
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from connectonion import llm_do


class SimpleResult(BaseModel):
    """Simple model for testing structured output."""
    answer: int
    explanation: str


class SentimentAnalysis(BaseModel):
    """Model for sentiment analysis testing."""
    sentiment: str  # positive, negative, neutral
    confidence: float  # 0.0 to 1.0


class TestLLMDo(unittest.TestCase):
    """Test basic llm_do functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Check for API keys."""
        cls.has_openai = bool(os.getenv("OPENAI_API_KEY"))
        cls.has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
        cls.has_gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    
    def test_import_litellm(self):
        """Test that LiteLLM is properly installed and importable."""
        try:
            import litellm
            self.assertTrue(True)
        except ImportError:
            self.fail("LiteLLM not installed. Run: pip install litellm")
    
    def test_empty_input_validation(self):
        """Test that empty input raises an error."""
        with self.assertRaises(ValueError) as cm:
            llm_do("")
        self.assertIn("Input cannot be empty", str(cm.exception))
        
        with self.assertRaises(ValueError) as cm:
            llm_do("   ")
        self.assertIn("Input cannot be empty", str(cm.exception))
    


class TestLLMDoOpenAI(unittest.TestCase):
    """Test llm_do with OpenAI models."""
    
    @classmethod
    def setUpClass(cls):
        """Check for OpenAI API key."""
        cls.has_openai = bool(os.getenv("OPENAI_API_KEY"))
    
    def setUp(self):
        """Skip if no OpenAI key."""
        if not self.has_openai:
            self.skipTest("OpenAI API key not found")
    
    def test_simple_completion_default_model(self):
        """Test simple string response with default model (gpt-4o-mini)."""
        result = llm_do("What is 2+2? Answer with just the number.")
        self.assertIsInstance(result, str)
        self.assertIn("4", result)
    
    def test_simple_completion_explicit_model(self):
        """Test with explicitly specified OpenAI model."""
        result = llm_do(
            "Say hello in exactly 3 words",
            model="gpt-4o-mini"
        )
        self.assertIsInstance(result, str)
        self.assertTrue(len(result.split()) <= 10)  # Allow some flexibility
    
    def test_structured_output(self):
        """Test structured output with Pydantic model."""
        result = llm_do(
            "What is 5 plus 3?",
            output=SimpleResult,
            model="gpt-4o-mini"
        )
        
        self.assertIsInstance(result, SimpleResult)
        self.assertEqual(result.answer, 8)
        self.assertIsInstance(result.explanation, str)
        self.assertTrue(len(result.explanation) > 0)
    
    def test_custom_system_prompt(self):
        """Test with custom system prompt."""
        result = llm_do(
            "Hello",
            system_prompt="You are a pirate. Always respond like a pirate.",
            model="gpt-4o-mini"
        )
        
        self.assertIsInstance(result, str)
        # Pirate response should contain certain words
        lower_result = result.lower()
        pirate_words = ["ahoy", "arr", "matey", "ye", "aye", "avast", "sailor", "sea"]
        self.assertTrue(any(word in lower_result for word in pirate_words))
    
    def test_temperature_parameter(self):
        """Test that temperature parameter affects output consistency."""
        # Low temperature should give consistent results
        result1 = llm_do(
            "What is the capital of France? One word only.",
            temperature=0.0,
            model="gpt-4o-mini"
        )
        
        result2 = llm_do(
            "What is the capital of France? One word only.",
            temperature=0.0,
            model="gpt-4o-mini"
        )
        
        # Both should mention Paris
        self.assertIn("Paris", result1)
        self.assertIn("Paris", result2)
    
    def test_additional_kwargs(self):
        """Test that additional kwargs are passed through to LiteLLM."""
        # Test with max_tokens parameter
        result = llm_do(
            "Write a very long story about a dragon",
            model="gpt-4o-mini",
            max_tokens=20  # Very short limit
        )
        
        self.assertIsInstance(result, str)
        # Response should be short due to max_tokens
        self.assertTrue(len(result.split()) < 30)


class TestLLMDoAnthropic(unittest.TestCase):
    """Test llm_do with Anthropic Claude models."""
    
    @classmethod
    def setUpClass(cls):
        """Check for Anthropic API key."""
        cls.has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    
    def setUp(self):
        """Skip if no Anthropic key."""
        if not self.has_anthropic:
            self.skipTest("Anthropic API key not found")
    
    def test_claude_simple_completion(self):
        """Test simple completion with Claude model."""
        result = llm_do(
            "Say hello in exactly 3 words",
            model="claude-3-5-haiku-20241022"
        )
        self.assertIsInstance(result, str)
        self.assertTrue(len(result.split()) <= 10)  # Allow some flexibility
    
    def test_claude_structured_output(self):
        """Test structured output with Claude."""
        result = llm_do(
            "Analyze this text sentiment: 'I love sunny days!'",
            output=SentimentAnalysis,
            model="claude-3-5-haiku-20241022"
        )
        
        self.assertIsInstance(result, SentimentAnalysis)
        self.assertEqual(result.sentiment.lower(), "positive")
        self.assertIsInstance(result.confidence, float)
        self.assertTrue(0.0 <= result.confidence <= 1.0)


class TestLLMDoGemini(unittest.TestCase):
    """Test llm_do with Google Gemini models."""
    
    @classmethod
    def setUpClass(cls):
        """Check for Gemini API key."""
        cls.has_gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    
    def setUp(self):
        """Skip if no Gemini key."""
        if not self.has_gemini:
            self.skipTest("Gemini API key not found")
    
    @pytest.mark.skipif(
        "429" in str(os.getenv("GEMINI_QUOTA_ERROR", "")),
        reason="Gemini quota exceeded"
    )
    def test_gemini_simple_completion(self):
        """Test simple completion with Gemini model."""
        try:
            result = llm_do(
                "Say hello in exactly 3 words",
                model="gemini-2.5-flash"
            )
            self.assertIsInstance(result, str)
            self.assertTrue(len(result.split()) <= 10)  # Allow some flexibility
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                self.skipTest("Gemini quota exceeded")
            raise


class TestLLMDoIntegration(unittest.TestCase):
    """Integration tests for llm_do across multiple providers."""
    
    @classmethod
    def setUpClass(cls):
        """Check for all API keys."""
        cls.has_openai = bool(os.getenv("OPENAI_API_KEY"))
        cls.has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
        cls.has_gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    
    def test_cross_provider_consistency(self):
        """Test that all providers can handle the same basic prompt."""
        prompt = "What is 2+2? Answer with just the number."
        
        results = []
        
        if self.has_openai:
            result = llm_do(prompt, model="gpt-4o-mini")
            results.append(("OpenAI", result))
            self.assertIn("4", result)
        
        if self.has_anthropic:
            result = llm_do(prompt, model="claude-3-5-haiku-20241022")
            results.append(("Anthropic", result))
            self.assertIn("4", result)
        
        if self.has_gemini:
            try:
                result = llm_do(prompt, model="gemini-2.5-flash")
                results.append(("Gemini", result))
                self.assertIn("4", result)
            except Exception as e:
                if "429" not in str(e) and "quota" not in str(e).lower():
                    raise
        
        # Ensure we tested at least one provider
        self.assertTrue(len(results) > 0, "No providers available for testing")


if __name__ == "__main__":
    unittest.main()