"""
Purpose: Token usage tracking and cost calculation for LLM calls
LLM-Note:
  Dependencies: pydantic | imported by [cli/commands/doctor_commands.py, cli/commands/eval_commands.py, cli/commands/project_cmd_lib.py, console.py, core/__init__.py, core/agent.py, core/exceptions.py, core/llm.py, logger.py]
  Data flow: receives model name + token counts → returns cost in USD
  Integration: exposes TokenUsage, MODEL_PRICING, MODEL_CONTEXT_LIMITS, calculate_cost(), get_context_limit(), is_estimated_price(), FREE_MANAGED_MODELS and PAID_MANAGED_MODELS (read by exceptions.py for PaidModelRequiredError and by project_cmd_lib.py for what `co auth` prints)
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
    total_tokens: int = 0       # What the server says it billed for; 0 = it didn't say
    # Exact managed-backend contract. Optional keeps direct providers and old
    # saved sessions backward-compatible; co/ responses populate every field.
    input_tokens_total: int | None = None
    input_tokens_uncached: int | None = None
    cache_read_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    cache_write_5m_input_tokens: int | None = None
    cache_write_1h_input_tokens: int | None = None
    cache_metadata_status: str | None = None
    provider: str | None = None
    requested_model: str | None = None
    provider_model: str | None = None
    provider_reported_cost_usd: float | None = None
    pricing_version: str | None = None
    pricing_tier: str | None = None
    cost_details: dict | None = None

    @property
    def billed_tokens(self) -> int:
        """The token count that goes with `cost`, so the two can be reconciled.

        input + output is not that number on a reasoning model: measured against
        the real backend, prompt 17 + completion 3 accompanied a charge for 243.
        The OpenAI-shaped fields never name the reasoning tokens, and the cost
        already comes from the server for exactly that reason (see core/llm.py).
        Printing the sum beside that cost made a line that is 34x off itself.

        Only what the server states — never a locally reconstructed figure, which
        is how the 11.6x undercount arose in the first place. Absent, the sum is
        the whole story: a direct provider call has no hidden tokens.

        input_tokens/output_tokens keep their meaning: they are the
        context-window numbers, and reasoning tokens are not in the context
        window, so `% ctx` must go on reading those.
        """
        return self.total_tokens or (self.input_tokens + self.output_tokens)


# Pricing per 1M tokens (USD)
# Format: {"input": $, "output": $, "cached": $, "cache_write": $}
MODEL_PRICING = {
    # OpenAI models - cached = 50% of input
    "o3-mini": {"input": 1.10, "output": 4.40, "cached": 0.55},
    "o4-mini": {"input": 1.10, "output": 4.40, "cached": 0.55},
    # Solved from real charges and then pinned at scale: (in=9, total=83,
    # $0.000751) and (in=2010, total=2148, $0.003893) give 1.25/10.00, and
    # (in=150012, total=150150, $0.188895) reproduces at ratio 1.0000. It was on
    # PAID_MANAGED_MODELS — sold to users — with no row here at all, so every cost
    # shown for it was DEFAULT_PRICING at 1.00/3.00 behind a `~`.
    # cached: OpenAI rows above use 50% of input; not measured for this model.
    "gpt-5": {"input": 1.25, "output": 10.00, "cached": 0.625},

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

    # Google Gemini cached-input discounts vary by model. Most rows below are
    # 75% discounts; Gemini 3.6 Flash is a provider-published 90% discount:
    # https://ai.google.dev/gemini-api/docs/pricing#gemini-3.6-flash
    # input/output for gemini-3.6-flash are also confirmed
    # against real charges: input_tokens x 1.50/1M + (total - input) x 7.50/1M
    # reproduced what the backend billed to a ratio of 1.0000 and 1.0009 on two
    # calls — so the server bills every non-input token, reasoning included, at
    # the output rate. See test_the_cached_rate_follows_its_stated_rule.py.
    # Standard paid tier, per million tokens: input $1.50, output $7.50,
    # context-cached input $0.15 (Google pricing page, checked 2026-08-08).
    "gemini-3.6-flash": {"input": 1.50, "output": 7.50, "cached": 0.15},
    # 3.7 Flash introductory rates through 2026-12-31: input $0.75, output
    # $3.75, cached input $0.075 per million. Standard rates double in 2027.
    "gemini-3.7-flash": {"input": 0.75, "output": 3.75, "cached": 0.075},
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00, "cached": 0.375},
    # Solved from real charges, two calls: (in=4, total=28, $0.000074) and
    # (in=2006, total=2101, $0.001288) give input 0.50 / output 3.00 and both
    # reproduce to the cent. It was falling through to DEFAULT_PRICING at
    # 1.00/3.00 — twice the input rate — while one of our own agents
    # (browser-agent on chat.openonion.ai) runs on it. Not in
    # FREE_MANAGED_MODELS/PAID_MANAGED_MODELS: the CLI does not offer it, the
    # backend routes it. cached is the stated 25%, not a measurement.
    "gemini-3-flash-preview": {"input": 0.50, "output": 3.00, "cached": 0.125},
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
    # 272,000, stated by the provider itself when a deliberately oversized
    # request was refused (unbilled): "Input tokens exceed the configured limit
    # of 272000 tokens. Your messages resulted in 450012 tokens." 150,012 was
    # accepted. Not the 128k default it had been taking, and not a round number.
    "gpt-5": 272000,

    # Anthropic - keyed on the family, as in MODEL_PRICING above
    "claude-sonnet-4": 200000,
    "claude-opus-4": 200000,
    "claude-3-7-sonnet": 200000,

    # Gemini
    "gemini-3.7-flash": 1000000,
    "gemini-3.6-flash": 1000000,
    "gemini-3.5-flash": 1000000,
    # Without this row it took the 128,000 default, so `% ctx` read 7.8x high and
    # auto-compaction fired about eight times too early — discarding context that
    # was nowhere near full and paying for a compaction call to do it. A
    # 150,008-token prompt was accepted and answered, which rules 128,000 out;
    # 1,000,000 is what every other Gemini here carries.
    "gemini-3-flash-preview": 1000000,
    "gemini-3-pro-preview": 1000000,
    "gemini-3-pro-image-preview": 65000,
    "gemini-2.5-pro": 1000000,
    "gemini-2.5-flash": 1000000,
    "gemini-2.0-flash": 1000000,
}

# Default values for unknown models
DEFAULT_PRICING = {"input": 1.00, "output": 3.00, "cached": 0.50}
DEFAULT_CONTEXT_LIMIT = 128000

# The model every entry point uses when the user configures nothing. One
# constant, imported by Agent, llm_do, transcribe, and the CLI — because
# "what is the default model" was previously answered by separate literals
# that drifted apart. The previous default stays on FREE_MANAGED_MODELS
# below as the rollback (issue #1002).
DEFAULT_MODEL = "co/gemini-3.7-flash"

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
    "co/gemini-3.7-flash",
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


def _extends_same_model(name: str, key: str) -> bool:
    """Whether `name` is `key` with a version pinned, rather than another model.

    The prefix fallback was written for the first case and applied to both:

        o4-mini-2025-04-16      is o4-mini with a date          -> same price
        gemini-2.5-flash-lite   is a cheaper, different model   -> not Flash's price

    Thirteen real Gemini models were taking a price that belongs to something
    else — -lite, -image, -preview-tts, -native-audio — and because a borrowed
    price is returned exactly like a looked-up one, `is_estimated_price` said
    False and the figure was shown without its `~`. Lite is cheaper than Flash;
    image and audio are billed on different units entirely.

    So the remainder must read as a version. Every token in it has to be digits,
    or `latest`, or `preview` immediately followed by digits:

        -2025-04-16    -001    -0    .1    -latest       same model
        -preview-05-06                                   same model, dated preview
        -lite   -image   -preview-tts   -native-audio    another model

    `preview` is the one that needs the lookahead: `gemini-2.5-pro-preview-05-06`
    is 2.5 Pro before release and prices as it, while `gemini-2.5-pro-preview-tts`
    is a different model that happens to share the word.

    Known limit: a bare digit cannot say whether it is an alias or the next minor
    version. `claude-sonnet-4-0` is Sonnet 4 and `claude-sonnet-4-5` is Sonnet
    4.5, and both read as a version here. They cost the same today, so nothing is
    misreported — but if a future minor prices differently, it needs its own row
    rather than a cleverer rule. Adding one makes a prefix pair, which the
    longest-first sort handles and test_the_longest_price_match_wins currently
    forbids on purpose; that test is the place to record the decision.
    """
    remainder = name[len(key):]
    if not remainder or remainder[0] not in "-.":
        return False

    tokens = remainder.replace(".", "-").strip("-").split("-")
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.isdigit() or token == "latest":
            index += 1
        elif token == "preview" and index + 1 < len(tokens) and tokens[index + 1].isdigit():
            index += 2
        else:
            return False
    return bool(tokens)


def get_pricing(model: str) -> dict:
    """Get pricing for a model, with fallback to default."""
    name = _priced_name(model)

    # Try exact match
    if name in MODEL_PRICING:
        return MODEL_PRICING[name]

    # Try prefix match for a pinned version (e.g. "o4-mini-2025-04-16" ->
    # "o4-mini"), longest first.
    #
    # Taking the first key that matched let dict order decide. Exact matches are
    # tried above, so a listed name was always fine — but a pinned, dated name is
    # not listed, and pinning a date is what production code does. When one entry
    # is a prefix of another, the shorter one used to win and charge its own
    # price for the longer model. The table no longer contains such a pair (a
    # test enforces that), but the ordering is what makes it safe to add one.
    # The longest match is the most specific one, which is what a prefix match
    # is for.
    #
    # _extends_same_model is what keeps this to versions. "gemini-2.5-pro-preview"
    # used to be the example here and is exactly what it now rejects: -preview,
    # -lite, -image and -tts name other models, and lending them a price they did
    # not earn also hid it, because a borrowed price is indistinguishable from a
    # looked-up one at the display.
    for known_model in sorted(MODEL_PRICING, key=len, reverse=True):
        if name.startswith(known_model) and _extends_same_model(name, known_model):
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
        if name.startswith(known_model) and _extends_same_model(name, known_model):
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

    # Same reconciliation as TokenUsage.billed_tokens, over a trace read back
    # from disk: sessions written before total_tokens existed have no such key,
    # and .get() rather than [] is what lets one of those still be summed.
    return (sum(u.get('total_tokens') or u['input_tokens'] + u['output_tokens']
                for u in usages),
            sum(u['cost'] for u in usages))


def turn_usage_from_trace(trace: list) -> dict | None:
    """Aggregate measured usage entries from one already-sliced Agent turn.

    Callers choose the turn boundary. Keeping that choice out of this helper
    prevents restored or concurrent session history from being counted by
    accident. Missing usage stays missing instead of becoming a misleading
    all-zero measurement.
    """
    usages = [
        entry.get('usage')
        for entry in trace
        if isinstance(entry, dict) and entry.get('type') == 'llm_result'
    ]
    usages = [usage for usage in usages if isinstance(usage, dict) and usage]
    if not usages:
        return None

    totals = {
        'input_tokens': 0,
        'output_tokens': 0,
        'cached_tokens': 0,
        'cache_write_tokens': 0,
        'total_tokens': 0,
        'cost': 0.0,
    }
    measured_cache_fields = {
        'input_tokens_total': 0,
        'input_tokens_uncached': 0,
        'cache_read_input_tokens': 0,
        'cache_write_input_tokens': 0,
        'cache_write_5m_input_tokens': 0,
        'cache_write_1h_input_tokens': 0,
    }
    measured_present = {
        field: any(field in usage and usage[field] is not None for usage in usages)
        for field in measured_cache_fields
    }
    for usage in usages:
        input_tokens = _usage_int(usage, 'input_tokens')
        output_tokens = _usage_int(usage, 'output_tokens')
        explicit_total = _usage_int(usage, 'total_tokens')
        totals['input_tokens'] += input_tokens
        totals['output_tokens'] += output_tokens
        totals['cached_tokens'] += _usage_int(usage, 'cached_tokens')
        totals['cache_write_tokens'] += _usage_int(usage, 'cache_write_tokens')
        totals['total_tokens'] += explicit_total or input_tokens + output_tokens

        cost = usage.get('cost', 0.0)
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
            totals['cost'] += float(cost)
        for field in measured_cache_fields:
            if measured_present[field]:
                measured_cache_fields[field] += _usage_int(usage, field)

    totals.update(
        {
            field: value
            for field, value in measured_cache_fields.items()
            if measured_present[field]
        }
    )
    statuses = {
        usage.get('cache_metadata_status')
        for usage in usages
        if usage.get('cache_metadata_status')
    }
    if statuses:
        totals['cache_metadata_status'] = (
            next(iter(statuses)) if len(statuses) == 1 else 'mixed'
        )
    return totals


def _usage_int(usage: dict, field: str) -> int:
    value = usage.get(field, 0)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0
