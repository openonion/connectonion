"""
Purpose: Token usage tracking and cost calculation for LLM calls
LLM-Note:
  Dependencies: none | imported by [llm.py, agent.py]
  Data flow: receives model name + token counts → returns cost in USD
  Integration: exposes TokenUsage, MODEL_PRICING, MODEL_CONTEXT_LIMITS, calculate_cost(), get_context_limit()
"""

from dataclasses import dataclass


@dataclass
class TokenUsage:
    """Token usage from a single LLM call."""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0      # Tokens read from cache (subset of input_tokens)
    cache_write_tokens: int = 0  # Tokens written to cache (Anthropic only)
    cost: float = 0.0           # USD cost for this call


# Pricing per 1M tokens (USD)
# Format: {"input": $, "output": $, "cached": $, "cache_write": $}
MODEL_PRICING = {
    # OpenAI models - cached = 50% of input
    "gpt-4o": {"input": 2.50, "output": 10.00, "cached": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached": 0.075},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00, "cached": 5.00},
    "o1": {"input": 15.00, "output": 60.00, "cached": 7.50},
    "o1-mini": {"input": 3.00, "output": 12.00, "cached": 1.50},
    "o1-preview": {"input": 15.00, "output": 60.00, "cached": 7.50},
    "o3-mini": {"input": 1.10, "output": 4.40, "cached": 0.55},
    "o4-mini": {"input": 1.10, "output": 4.40, "cached": 0.55},

    # Anthropic Claude models - cached = 10% of input, cache_write = 125% of input
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00, "cached": 0.30, "cache_write": 3.75},
    "claude-3-5-sonnet-latest": {"input": 3.00, "output": 15.00, "cached": 0.30, "cache_write": 3.75},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00, "cached": 0.08, "cache_write": 1.00},
    "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.00, "cached": 0.08, "cache_write": 1.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00, "cached": 1.50, "cache_write": 18.75},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00, "cached": 0.30, "cache_write": 3.75},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25, "cached": 0.025, "cache_write": 0.3125},

    # Claude 4 models
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00, "cached": 0.30, "cache_write": 3.75},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00, "cached": 1.50, "cache_write": 18.75},

    # Google Gemini models - cached = 25% of input (75% discount)
    "gemini-3-pro-preview": {"input": 2.00, "output": 12.00, "cached": 0.50},
    "gemini-3-pro-image-preview": {"input": 2.00, "output": 0.134},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00, "cached": 0.3125},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60, "cached": 0.0375},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "cached": 0.025},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00, "cached": 0.3125},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30, "cached": 0.01875},
}

# Context window limits (tokens)
MODEL_CONTEXT_LIMITS = {
    # OpenAI
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "o1": 200000,
    "o1-mini": 128000,
    "o1-preview": 128000,
    "o3-mini": 200000,
    "o4-mini": 200000,

    # Anthropic
    "claude-3-5-sonnet-20241022": 200000,
    "claude-3-5-sonnet-latest": 200000,
    "claude-3-5-haiku-20241022": 200000,
    "claude-3-5-haiku-latest": 200000,
    "claude-3-opus-20240229": 200000,
    "claude-3-sonnet-20240229": 200000,
    "claude-3-haiku-20240307": 200000,
    "claude-sonnet-4-20250514": 200000,
    "claude-opus-4-20250514": 200000,

    # Gemini
    "gemini-3-pro-preview": 1000000,
    "gemini-3-pro-image-preview": 65000,
    "gemini-2.5-pro": 1000000,
    "gemini-2.5-flash": 1000000,
    "gemini-2.0-flash": 1000000,
    "gemini-1.5-pro": 2000000,
    "gemini-1.5-flash": 1000000,
}

# Default values for unknown models
DEFAULT_PRICING = {"input": 1.00, "output": 3.00, "cached": 0.50}
DEFAULT_CONTEXT_LIMIT = 128000


def get_pricing(model: str) -> dict:
    """Get pricing for a model, with fallback to default."""
    # Try exact match
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]

    # Try prefix match (e.g., "gpt-4o-2024-08-06" -> "gpt-4o")
    for known_model in MODEL_PRICING:
        if model.startswith(known_model):
            return MODEL_PRICING[known_model]

    return DEFAULT_PRICING


def get_context_limit(model: str) -> int:
    """Get context limit for a model, with fallback to default."""
    if model in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[model]

    for known_model in MODEL_CONTEXT_LIMITS:
        if model.startswith(known_model):
            return MODEL_CONTEXT_LIMITS[known_model]

    return DEFAULT_CONTEXT_LIMIT


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Calculate USD cost for token usage.

    Args:
        model: Model name
        input_tokens: Total input tokens (includes cached)
        output_tokens: Output/completion tokens
        cached_tokens: Tokens read from cache (subset of input_tokens)
        cache_write_tokens: Tokens written to cache (Anthropic)

    Returns:
        Cost in USD
    """
    pricing = get_pricing(model)

    # Non-cached input tokens = total input - cached
    non_cached_input = max(0, input_tokens - cached_tokens)

    # Calculate costs (pricing is per 1M tokens)
    input_cost = (non_cached_input / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    cached_cost = (cached_tokens / 1_000_000) * pricing.get("cached", pricing["input"] * 0.5)

    # Cache write cost (Anthropic only)
    cache_write_cost = 0.0
    if cache_write_tokens > 0 and "cache_write" in pricing:
        cache_write_cost = (cache_write_tokens / 1_000_000) * pricing["cache_write"]

    return input_cost + output_cost + cached_cost + cache_write_cost
