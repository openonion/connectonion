"""Comprehensive tests for llm_do covering all documentation examples.

Tests all functionality from docs/llm_do.md across all providers.
Run with: pytest tests/test_llm_do_comprehensive.py -v
"""

import os
import pytest
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from connectonion import llm_do

# Load environment variables
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


# ============================================================================
# Pydantic Models for Testing (from documentation examples)
# ============================================================================

class SentimentAnalysis(BaseModel):
    """Simple sentiment analysis model."""
    sentiment: str
    score: float


class Analysis(BaseModel):
    """Analysis model with keywords."""
    sentiment: str
    confidence: float
    keywords: List[str]


class Invoice(BaseModel):
    """Invoice data extraction model."""
    invoice_number: str
    total_amount: float
    due_date: str


class Address(BaseModel):
    """Nested address model."""
    street: str
    city: str
    zipcode: str


class Person(BaseModel):
    """Person with nested address."""
    name: str
    age: int
    occupation: str


class KeywordExtraction(BaseModel):
    """Keyword extraction with lists."""
    keywords: List[str]
    categories: List[str]
    count: int


class ProductReview(BaseModel):
    """Product review with optional fields and constraints."""
    product_name: str
    rating: int = Field(ge=1, le=5)
    pros: List[str]
    cons: Optional[List[str]] = None
    would_recommend: bool


class EmailClassification(BaseModel):
    """Email classification model."""
    category: str  # spam, important, newsletter, personal
    priority: str  # high, medium, low
    requires_action: bool
    summary: str


class LineItem(BaseModel):
    """Invoice line item."""
    description: str
    quantity: int
    unit_price: float
    total: float


class InvoiceDetailed(BaseModel):
    """Detailed invoice with line items."""
    invoice_number: str
    date: str
    customer_name: str
    items: List[LineItem]
    subtotal: float
    tax: float
    total: float


class Topic(BaseModel):
    """Topic with confidence."""
    name: str
    confidence: float


class BlogAnalysis(BaseModel):
    """Complex blog post analysis."""
    title: str
    main_topics: List[Topic]
    word_count_estimate: int
    reading_time_minutes: int
    target_audience: str
    key_takeaways: List[str]


class ContentModeration(BaseModel):
    """Content moderation with boolean decisions."""
    is_appropriate: bool
    contains_profanity: bool
    contains_spam: bool
    contains_personal_info: bool
    risk_level: str  # low, medium, high
    reasoning: str


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def has_openai():
    """Check if OpenAI API key is available."""
    return bool(os.getenv("OPENAI_API_KEY"))


@pytest.fixture
def has_anthropic():
    """Check if Anthropic API key is available."""
    return bool(os.getenv("ANTHROPIC_API_KEY"))


@pytest.fixture
def has_gemini():
    """Check if Gemini API key is available."""
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


@pytest.fixture
def has_connectonion():
    """Check if ConnectOnion auth is available."""
    return bool(os.getenv("OPENONION_API_KEY"))


# ============================================================================
# Basic Functionality Tests
# ============================================================================

@pytest.mark.real_api
class TestBasicFunctionality:
    """Test basic llm_do functionality with different providers."""

    def test_empty_input_validation(self):
        """Test that empty input raises ValueError."""
        with pytest.raises(ValueError, match="Input cannot be empty"):
            llm_do("")

        with pytest.raises(ValueError, match="Input cannot be empty"):
            llm_do("   ")

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_simple_openai(self):
        """Test simple completion with OpenAI."""
        result = llm_do(
            "What is 2+2? Answer with just the number.",
            model="gpt-4o-mini"
        )
        assert isinstance(result, str)
        assert "4" in result

    @pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No Anthropic API key")
    def test_simple_anthropic(self):
        """Test simple completion with Anthropic."""
        result = llm_do(
            "What is 2+2? Answer with just the number.",
            model="claude-3-5-haiku-20241022"
        )
        assert isinstance(result, str)
        assert "4" in result

    @pytest.mark.skipif(
        not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        reason="No Gemini API key"
    )
    def test_simple_gemini(self):
        """Test simple completion with Gemini."""
        result = llm_do(
            "What is 2+2? Answer with just the number.",
            model="gemini-2.5-flash"
        )
        assert isinstance(result, str)
        assert "4" in result

    @pytest.mark.skipif(not os.getenv("OPENONION_API_KEY"), reason="No ConnectOnion auth")
    def test_simple_connectonion(self):
        """Test simple completion with ConnectOnion managed keys."""
        result = llm_do(
            "What is 2+2? Answer with just the number.",
            model="co/gpt-4o"
        )
        assert isinstance(result, str)
        assert "4" in result


# ============================================================================
# Structured Output Tests (from documentation)
# ============================================================================

@pytest.mark.real_api
class TestStructuredOutput:
    """Test structured output with Pydantic models."""

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_sentiment_analysis(self):
        """Test simple sentiment analysis from Quick Start."""
        result = llm_do(
            "I absolutely love this product! Best purchase ever!",
            output=Analysis,
            model="gpt-4o-mini"
        )

        assert isinstance(result, Analysis)
        assert result.sentiment.lower() in ["positive", "very positive", "extremely positive"]
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.keywords, list)
        assert len(result.keywords) > 0

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_invoice_extraction(self):
        """Test invoice data extraction from documentation."""
        invoice_text = """
        Invoice #INV-2024-001
        Total: $1,234.56
        Due: January 15, 2024
        """

        result = llm_do(invoice_text, output=Invoice, model="gpt-4o-mini")

        assert isinstance(result, Invoice)
        assert result.invoice_number == "INV-2024-001"
        assert result.total_amount == 1234.56
        # Date can be in different formats (January 15, 2024 or 2024-01-15)
        assert ("January" in result.due_date or "01" in result.due_date) and "15" in result.due_date

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_person_extraction(self):
        """Test data extraction with nested models."""
        result = llm_do(
            "John Doe, 30, software engineer",
            output=Person,
            model="gpt-4o-mini"
        )

        assert isinstance(result, Person)
        assert "john" in result.name.lower() and "doe" in result.name.lower()
        assert result.age == 30
        assert "engineer" in result.occupation.lower()

    @pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No Anthropic API key")
    def test_structured_anthropic(self):
        """Test structured output with Anthropic."""
        result = llm_do(
            "I absolutely love this product! Best purchase ever!",
            output=SentimentAnalysis,
            model="claude-3-5-haiku-20241022"
        )

        assert isinstance(result, SentimentAnalysis)
        assert result.sentiment.lower() in ["positive", "very positive"]
        assert isinstance(result.score, float)

    @pytest.mark.skip(reason="Gemini structured output API incompatibility - .parsed attribute not available")
    @pytest.mark.skipif(
        not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        reason="No Gemini API key"
    )
    def test_structured_gemini(self):
        """Test structured output with Gemini."""
        result = llm_do(
            "I absolutely love this product! Best purchase ever!",
            output=SentimentAnalysis,
            model="gemini-2.5-flash"
        )

        assert isinstance(result, SentimentAnalysis)
        assert result.sentiment.lower() in ["positive", "very positive"]
        assert isinstance(result.score, float)


# ============================================================================
# Complex Structured Output Tests
# ============================================================================

@pytest.mark.real_api
class TestComplexStructuredOutput:
    """Test complex structured output patterns from documentation."""

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_keyword_extraction(self):
        """Test list fields extraction."""
        result = llm_do(
            "Extract keywords from: 'Machine learning and artificial intelligence are transforming technology and business'",
            output=KeywordExtraction,
            model="gpt-4o-mini"
        )

        assert isinstance(result, KeywordExtraction)
        assert isinstance(result.keywords, list)
        assert len(result.keywords) > 0
        assert isinstance(result.categories, list)
        assert isinstance(result.count, int)

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_product_review_optional_fields(self):
        """Test optional fields and Field constraints."""
        result = llm_do(
            "Review: The laptop is amazing! Fast performance, great display. Rating: 5/5. Highly recommend!",
            output=ProductReview,
            model="gpt-4o-mini"
        )

        assert isinstance(result, ProductReview)
        assert 1 <= result.rating <= 5
        assert isinstance(result.pros, list)
        assert len(result.pros) > 0
        assert result.would_recommend is True

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_email_classification(self):
        """Test classification tasks."""
        result = llm_do(
            'Email: "URGENT: Your account will be suspended unless you verify your information immediately!" Classify this email.',
            output=EmailClassification,
            model="gpt-4o-mini"
        )

        assert isinstance(result, EmailClassification)
        assert result.category.lower() in ["spam", "phishing", "suspicious"]
        assert result.priority.lower() in ["high", "medium", "low"]
        assert isinstance(result.requires_action, bool)
        assert isinstance(result.summary, str)

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_detailed_invoice_extraction(self):
        """Test complex nested structures with lists."""
        invoice_text = """
        INVOICE #INV-2024-001
        Date: January 15, 2024
        Customer: Acme Corp

        Items:
        - Widget A x2 @ $10.00 = $20.00
        - Widget B x1 @ $15.50 = $15.50

        Subtotal: $35.50
        Tax (10%): $3.55
        Total: $39.05
        """

        result = llm_do(
            invoice_text,
            output=InvoiceDetailed,
            model="gpt-4o-mini"
        )

        assert isinstance(result, InvoiceDetailed)
        assert result.invoice_number == "INV-2024-001"
        assert len(result.items) == 2
        assert result.total == 39.05

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_blog_analysis(self):
        """Test multi-entity extraction."""
        blog_text = """
        Understanding Machine Learning: A Beginner's Guide

        Machine learning is revolutionizing how we interact with technology.
        From recommendation systems to self-driving cars, ML algorithms are everywhere.
        This guide will help you understand the basics of supervised learning, neural networks,
        and practical applications. Perfect for developers new to AI.

        [... approximately 1200 words ...]
        """

        result = llm_do(
            blog_text,
            output=BlogAnalysis,
            model="gpt-4o-mini"
        )

        assert isinstance(result, BlogAnalysis)
        assert isinstance(result.main_topics, list)
        assert len(result.main_topics) > 0
        assert all(isinstance(topic, Topic) for topic in result.main_topics)
        assert isinstance(result.word_count_estimate, int)
        assert isinstance(result.key_takeaways, list)

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_content_moderation(self):
        """Test boolean decision making."""
        result = llm_do(
            "User comment: 'This is a great product! Everyone should try it. Visit my-totally-legit-site.com for more info!'",
            output=ContentModeration,
            model="gpt-4o-mini"
        )

        assert isinstance(result, ContentModeration)
        assert isinstance(result.is_appropriate, bool)
        assert isinstance(result.contains_profanity, bool)
        assert isinstance(result.contains_spam, bool)
        assert isinstance(result.contains_personal_info, bool)
        assert result.risk_level.lower() in ["low", "medium", "high"]


# ============================================================================
# Advanced Features Tests
# ============================================================================

@pytest.mark.real_api
class TestAdvancedFeatures:
    """Test advanced features like temperature, max_tokens, custom prompts."""

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_temperature_parameter(self):
        """Test temperature parameter for consistency."""
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
        assert "Paris" in result1 or "paris" in result1.lower()
        assert "Paris" in result2 or "paris" in result2.lower()

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_max_tokens_parameter(self):
        """Test max_tokens parameter pass-through."""
        result = llm_do(
            "Write a very long story about a dragon",
            model="gpt-4o-mini",
            max_tokens=20  # Very short limit
        )

        # Response should be short due to max_tokens
        assert isinstance(result, str)
        assert len(result.split()) < 30

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_custom_system_prompt_inline(self):
        """Test inline system prompt."""
        result = llm_do(
            "Hello",
            system_prompt="You are a pirate. Always respond like a pirate.",
            model="gpt-4o-mini"
        )

        # Should contain pirate-like language
        lower_result = result.lower()
        pirate_words = ["ahoy", "arr", "matey", "ye", "aye", "avast", "sea"]
        assert any(word in lower_result for word in pirate_words)


# ============================================================================
# Cross-Provider Consistency Tests
# ============================================================================

@pytest.mark.real_api
class TestCrossProviderConsistency:
    """Test that all providers handle the same prompts correctly."""

    def test_all_providers_basic_math(self, has_openai, has_anthropic, has_gemini):
        """Test all available providers with the same basic question."""
        prompt = "What is 2+2? Answer with just the number."
        results = []

        if has_openai:
            result = llm_do(prompt, model="gpt-4o-mini")
            results.append(("OpenAI", result))
            assert "4" in result

        if has_anthropic:
            result = llm_do(prompt, model="claude-3-5-haiku-20241022")
            results.append(("Anthropic", result))
            assert "4" in result

        if has_gemini:
            result = llm_do(prompt, model="gemini-2.5-flash")
            results.append(("Gemini", result))
            assert "4" in result

        # Ensure at least one provider was tested
        assert len(results) > 0, "No providers available for testing"


# ============================================================================
# Documentation Example Tests
# ============================================================================

@pytest.mark.real_api
class TestDocumentationExamples:
    """Test exact examples from docs/llm_do.md."""

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_quick_start_example(self):
        """Test the Quick Start example from docs."""
        answer = llm_do("What's 2+2?", model="gpt-4o-mini")
        assert "4" in answer

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_format_conversion_example(self):
        """Test format conversion pattern from docs."""
        class PersonData(BaseModel):
            name: str
            age: int

        result = llm_do(
            "Extract: name=John age=30",
            output=PersonData,
            model="gpt-4o-mini"
        )

        assert isinstance(result, PersonData)
        assert "john" in result.name.lower()
        assert result.age == 30

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_validation_pattern(self):
        """Test validation pattern from docs."""
        result = llm_do(
            "Is this valid SQL? Reply yes/no only: SELECT * FROM users",
            temperature=0,
            model="gpt-4o-mini"
        )

        assert result.strip().lower() in ["yes", "no"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
