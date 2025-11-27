"""Unit tests for connectonion/usage.py"""

import pytest
from connectonion.usage import (
    TokenUsage,
    MODEL_PRICING,
    MODEL_CONTEXT_LIMITS,
    get_pricing,
    get_context_limit,
    calculate_cost,
    DEFAULT_PRICING,
    DEFAULT_CONTEXT_LIMIT,
)


class TestTokenUsage:
    """Test TokenUsage dataclass."""

    def test_default_values(self):
        """Test TokenUsage with default values."""
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cached_tokens == 0
        assert usage.cache_write_tokens == 0
        assert usage.cost == 0.0

    def test_custom_values(self):
        """Test TokenUsage with custom values."""
        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=200,
            cache_write_tokens=100,
            cost=0.05
        )
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.cached_tokens == 200
        assert usage.cache_write_tokens == 100
        assert usage.cost == 0.05


class TestGetPricing:
    """Test get_pricing function."""

    def test_exact_match(self):
        """Test pricing lookup with exact model name."""
        pricing = get_pricing("gpt-4o")
        assert pricing["input"] == 2.50
        assert pricing["output"] == 10.00
        assert pricing["cached"] == 1.25

    def test_prefix_match(self):
        """Test pricing lookup with model name prefix."""
        # e.g., "gpt-4o-2024-08-06" should match "gpt-4o"
        pricing = get_pricing("gpt-4o-2024-08-06")
        assert pricing["input"] == 2.50

    def test_unknown_model_returns_default(self):
        """Test unknown model returns default pricing."""
        pricing = get_pricing("unknown-model-xyz")
        assert pricing == DEFAULT_PRICING

    def test_anthropic_model_has_cache_write(self):
        """Test Anthropic models include cache_write pricing."""
        pricing = get_pricing("claude-3-5-sonnet-20241022")
        assert "cache_write" in pricing
        assert pricing["cache_write"] == 3.75


class TestGetContextLimit:
    """Test get_context_limit function."""

    def test_exact_match(self):
        """Test context limit lookup with exact model name."""
        limit = get_context_limit("gpt-4o")
        assert limit == 128000

    def test_prefix_match(self):
        """Test context limit lookup with model name prefix."""
        limit = get_context_limit("gpt-4o-mini-2024")
        assert limit == 128000

    def test_unknown_model_returns_default(self):
        """Test unknown model returns default context limit."""
        limit = get_context_limit("unknown-model-xyz")
        assert limit == DEFAULT_CONTEXT_LIMIT

    def test_gemini_large_context(self):
        """Test Gemini models have large context windows."""
        limit = get_context_limit("gemini-2.5-pro")
        assert limit == 1_000_000

    def test_claude_context(self):
        """Test Claude models have 200k context."""
        limit = get_context_limit("claude-3-5-sonnet-20241022")
        assert limit == 200000


class TestCalculateCost:
    """Test calculate_cost function."""

    def test_basic_cost_no_cache(self):
        """Test cost calculation without caching."""
        cost = calculate_cost(
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
        )
        # gpt-4o-mini: input=$0.15/1M, output=$0.60/1M
        # 1000 * 0.15 / 1M + 500 * 0.60 / 1M = 0.00015 + 0.0003 = 0.00045
        expected = (1000 / 1_000_000) * 0.15 + (500 / 1_000_000) * 0.60
        assert abs(cost - expected) < 0.0001

    def test_cost_with_cached_tokens(self):
        """Test cost calculation with cached tokens."""
        cost = calculate_cost(
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=300,
        )
        # gpt-4o-mini: input=$0.15/1M, output=$0.60/1M, cached=$0.075/1M
        # Non-cached: 700 input, 500 output
        # Cached: 300
        non_cached_input = 1000 - 300
        expected = (
            (non_cached_input / 1_000_000) * 0.15 +
            (500 / 1_000_000) * 0.60 +
            (300 / 1_000_000) * 0.075
        )
        assert abs(cost - expected) < 0.0001

    def test_anthropic_cache_write_cost(self):
        """Test Anthropic cache write cost."""
        cost = calculate_cost(
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=0,
            cache_write_tokens=200,
        )
        # claude-3-5-sonnet: input=$3/1M, output=$15/1M, cache_write=$3.75/1M
        expected = (
            (1000 / 1_000_000) * 3.00 +
            (500 / 1_000_000) * 15.00 +
            (200 / 1_000_000) * 3.75
        )
        assert abs(cost - expected) < 0.0001

    def test_unknown_model_uses_default(self):
        """Test unknown model uses default pricing."""
        cost = calculate_cost(
            model="unknown-model",
            input_tokens=1000,
            output_tokens=500,
        )
        # Default: input=$1/1M, output=$3/1M
        expected = (1000 / 1_000_000) * 1.00 + (500 / 1_000_000) * 3.00
        assert abs(cost - expected) < 0.0001

    def test_zero_tokens_returns_zero(self):
        """Test zero tokens returns zero cost."""
        cost = calculate_cost(
            model="gpt-4o",
            input_tokens=0,
            output_tokens=0,
        )
        assert cost == 0.0


class TestModelPricing:
    """Test MODEL_PRICING dictionary."""

    def test_openai_models_exist(self):
        """Test OpenAI models are in pricing."""
        assert "gpt-4o" in MODEL_PRICING
        assert "gpt-4o-mini" in MODEL_PRICING
        assert "o4-mini" in MODEL_PRICING

    def test_anthropic_models_exist(self):
        """Test Anthropic models are in pricing."""
        assert "claude-3-5-sonnet-20241022" in MODEL_PRICING
        assert "claude-3-5-haiku-20241022" in MODEL_PRICING

    def test_gemini_models_exist(self):
        """Test Gemini models are in pricing."""
        assert "gemini-2.5-pro" in MODEL_PRICING
        assert "gemini-2.5-flash" in MODEL_PRICING


class TestModelContextLimits:
    """Test MODEL_CONTEXT_LIMITS dictionary."""

    def test_openai_models_exist(self):
        """Test OpenAI models are in context limits."""
        assert "gpt-4o" in MODEL_CONTEXT_LIMITS
        assert MODEL_CONTEXT_LIMITS["gpt-4o"] == 128000

    def test_anthropic_models_exist(self):
        """Test Anthropic models are in context limits."""
        assert "claude-3-5-sonnet-20241022" in MODEL_CONTEXT_LIMITS
        assert MODEL_CONTEXT_LIMITS["claude-3-5-sonnet-20241022"] == 200000

    def test_gemini_models_exist(self):
        """Test Gemini models are in context limits."""
        assert "gemini-2.5-pro" in MODEL_CONTEXT_LIMITS
        assert MODEL_CONTEXT_LIMITS["gemini-2.5-pro"] == 1_000_000