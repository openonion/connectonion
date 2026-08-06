"""
Purpose: Token usage tracking and cost calculation for LLM calls
LLM-Note:
  Dependencies: pydantic | imported by [llm.py, agent.py]
  Data flow: receives model name + token counts → returns cost in USD
  Integration: exposes TokenUsage, MODEL_PRICING, MODEL_CONTEXT_LIMITS, calculate_cost(), get_context_limit()
"""

from pydantic import BaseModel


class TokenUsage(BaseModel):
    """Token usage from a single LLM call.

    Uses Pydantic BaseModel for:
    - Native JSON serialization via .model_dump()
    - Type validation at runtime
    - Future-proof API response compatibility
    """
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0      # Tokens read from cache (subset of input_tokens)
    cache_write_tokens: int = 0  # Tokens written to cache (Anthropic only)
    cost: float = 0.0           # USD cost for this call


# Pricing per 1M tokens (USD)
# Format: {"input": $, "output": $, "cached": $, "cache_write": $}
MODEL_PRICING = {
    # OpenAI models - cached = 50% of input
    "o3-mini": {"input": 1.10, "output": 4.40, "cached": 0.55},
    "o4-mini": {"input": 1.10, "output": 4.40, "cached": 0.55},

    # Anthropic Claude models - cached = 10% of input, cache_write = 125% of input
    #
    # Keyed on the family, not on a pinned date. The prefix fallback only widens
    # one way — a queried name may be longer than a key — so a table of dated
    # names left every bare alias in MODEL_REGISTRY (claude-sonnet-4,
    # claude-opus-4-1, claude-opus-4.1, ...) falling through to DEFAULT_PRICING
    # at 1.00/3.00. Sonnet 4 billed a quarter of its real cost that way.
    # One row per family covers the aliases and the dated names both.
    #
    # Opus 4 and 4.1 cost the same, so `claude-opus-4` prices the whole family
    # and no entry shadows another. If a future Opus prices differently, adding
    # it makes a prefix pair and the longest-first sort in get_pricing is what
    # keeps it correct — test_the_longest_price_match_wins covers that.
    #
    # A price here is not evidence the model still exists: the two Gemini
    # entries that were missing from this table turned out to be retired at the
    # provider, and one was a class default. MODEL_REGISTRY is where that is
    # checked.
    "claude-sonnet-4": {"input": 3.00, "output": 15.00, "cached": 0.30, "cache_write": 3.75},
    "claude-opus-4": {"input": 15.00, "output": 75.00, "cached": 1.50, "cache_write": 18.75},
    "claude-3-7-sonnet": {"input": 3.00, "output": 15.00, "cached": 0.30, "cache_write": 3.75},

    # Google Gemini models - cached = 25% of input (75% discount)
    "gemini-3.6-flash": {"input": 1.50, "output": 7.50, "cached": 0.15},
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00, "cached": 0.375},
    "gemini-3-pro-preview": {"input": 2.00, "output": 12.00, "cached": 0.50},
    "gemini-3-pro-image-preview": {"input": 2.00, "output": 0.134},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00, "cached": 0.3125},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60, "cached": 0.0375},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "cached": 0.025},
}

# Context window limits (tokens)
MODEL_CONTEXT_LIMITS = {
    # OpenAI
    "o3-mini": 200000,
    "o4-mini": 200000,

    # Anthropic - keyed on the family, as in MODEL_PRICING above
    "claude-sonnet-4": 200000,
    "claude-opus-4": 200000,
    "claude-3-7-sonnet": 200000,

    # Gemini
    "gemini-3.6-flash": 1000000,
    "gemini-3.5-flash": 1000000,
    "gemini-3-pro-preview": 1000000,
    "gemini-3-pro-image-preview": 65000,
    "gemini-2.5-pro": 1000000,
    "gemini-2.5-flash": 1000000,
    "gemini-2.0-flash": 1000000,
}

# Default values for unknown models
DEFAULT_PRICING = {"input": 1.00, "output": 3.00, "cached": 0.50}
DEFAULT_CONTEXT_LIMIT = 128000

# Which managed models a free account can call. The backend refuses the rest
# with error='paid_account_required': "Your free $5 credits work with
# Google-routed models."
#
# Another model fact, so it lives with the other two tables. The CLI prints it
# after `co auth` and PaidModelRequiredError offers it when a free account picks
# a paid model — one list, because the two copies it replaced had gone stale in
# different directions. Verified by authenticating a fresh identity and
# completing a real call per model; see
# tests/unit/test_the_models_we_advertise_answer.py.
FREE_MANAGED_MODELS = (
    "co/gemini-3.6-flash",
    "co/gemini-3.5-flash",
    "co/gemini-2.5-pro",
    "co/gemini-2.5-flash",
)

# Real and reachable, once the account has credits.
PAID_MANAGED_MODELS = ("co/gpt-5", "co/o4-mini", "co/claude-sonnet-4")


def _priced_name(model: str) -> str:
    """The name this model is listed under, if it is listed at all.

    `co/` is the managed route to a model, not a different model — and not one
    of the priced entries carries the prefix, so every agent on the default
    setup (which is a `co/` model) had its tokens costed from the generic
    fallback. For co/gemini-3.6-flash that is 3.00 an output megatoken against
    the model's own 7.50.
    """
    return model[len("co/"):] if model.startswith("co/") else model


def get_pricing(model: str) -> dict:
    """Get pricing for a model, with fallback to default."""
    name = _priced_name(model)

    # Try exact match
    if name in MODEL_PRICING:
        return MODEL_PRICING[name]

    # Try prefix match (e.g., "gemini-2.5-pro-preview" -> "gemini-2.5-pro"),
    # longest first.
    #
    # Taking the first key that matched let dict order decide. Exact matches are
    # tried above, so a listed name was always fine — but a pinned, dated name is
    # not listed, and pinning a date is what production code does. When one entry
    # is a prefix of another, the shorter one used to win and charge its own
    # price for the longer model. The table no longer contains such a pair (a
    # test enforces that), but the ordering is what makes it safe to add one.
    # The longest match is the most specific one, which is what a prefix match
    # is for.
    for known_model in sorted(MODEL_PRICING, key=len, reverse=True):
        if name.startswith(known_model):
            return MODEL_PRICING[known_model]

    return DEFAULT_PRICING


def is_estimated_price(model: str) -> bool:
    """Whether this model's cost is a guess rather than a looked-up price.

    DEFAULT_PRICING is returned exactly like a real entry, so a fabricated
    number reaches a display with the same confidence as a known one. That is
    how the default model went mispriced without anyone noticing: the figure
    looked like every other figure.

    Callers that show money should say when it is an estimate. The next model
    the world ships is unknown here again.
    """
    return get_pricing(model) is DEFAULT_PRICING


def get_context_limit(model: str) -> int:
    """Get context limit for a model, with fallback to default."""
    name = _priced_name(model)

    if name in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[name]

    # Longest first, for the reason spelled out in get_pricing — and here the
    # consequence is worse than a wrong number on screen. A dated name that fell
    # through to a larger model's limit made the agent believe it had tens of
    # thousands of tokens it did not have: auto-compaction fired too late and the
    # provider rejected the request for length.
    for known_model in sorted(MODEL_CONTEXT_LIMITS, key=len, reverse=True):
        if name.startswith(known_model):
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


def totals_from_trace(trace: list) -> tuple:
    """Tokens and cost for a run, read off the trace the agent wrote.

    Three callers had their own copy of this and all three were wrong the same
    way: they summed the `llm_call` entries. `llm_call` is written when the
    request goes out, before there is anything to count — the usage is on the
    `llm_result` that follows. Every run summary and every saved eval therefore
    reported 0 tokens and $0.0000, for every run there has ever been.

    The usage is a dict, not a TokenUsage: agent.py records model_dump() to keep
    the trace JSON-serialisable. Attribute access would have raised the moment
    the list stopped being empty, which is how a copy of this was written three
    times without anyone noticing it never ran.
    """
    usages = [t.get('usage') for t in trace if t.get('type') == 'llm_result']
    usages = [u for u in usages if u]

    return (sum(u['input_tokens'] + u['output_tokens'] for u in usages),
            sum(u['cost'] for u in usages))
