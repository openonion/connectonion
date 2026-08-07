"""A model we vouch for must not be costed from a made-up number.

`MODEL_REGISTRY` is not a gate on what a user may select — `create_llm` consults
it first and then infers the provider from the name's prefix, so any `gpt-*`,
`claude-*` or `gemini-*` name routes whether it is listed or not. What the
registry is, is the curated list: the names this project names, prices, and
holds itself to.

`MODEL_PRICING` and `MODEL_CONTEXT_LIMITS` are two other lists. Eleven of the
twenty-one curated models appeared in neither, so their tokens were costed from
`DEFAULT_PRICING` — 1.00/3.00, a figure that is not any real model's price.

An unlisted model falling back to a guess is the design working: it is marked
with a leading `~` where it is shown. A model on our own list falling back is
the bug.

The prefix fallback was meant to cover this, and it only widens in one
direction: a queried name may be *longer* than a table key.

    name.startswith(known_model)

For OpenAI and Gemini the table holds the bare family name and the world ships
dated variants, so that direction is the right one. The Claude rows are stocked
the opposite way — the table holds `claude-sonnet-4-20250514` while the registry
offers the bare alias `claude-sonnet-4` — and

    "claude-sonnet-4".startswith("claude-sonnet-4-20250514")  ->  False

so the alias falls through. Measured on the same token counts, one model with
two spellings:

    claude-sonnet-4-20250514   1M in + 1M out  ->  $18.00   (correct)
    claude-sonnet-4            1M in + 1M out  ->  $ 4.00   (fallback)

The whole `claude-opus-4-1` family is unpriced too, at $4.00 against a true
$90.00. Under-reporting by 4.5x to 22x is the wrong direction for a number a
user reads to decide whether to keep going.

The existing prefix tests use `o4-mini-2025-04-16` against a listed `o4-mini`
— the direction that works. That is why this survived: the test and the table
agreed with each other, and neither agreed with the registry.

So these tests assert the invariant across the registry rather than a
hand-written list of names. A model added to the registry tomorrow with no price
fails here, which is the point — `is_estimated_price` exists precisely because a
fabricated figure is indistinguishable from a real one at the point it is shown.
"""

import pytest

from connectonion.core.llm import MODEL_REGISTRY
from connectonion.core.usage import (
    DEFAULT_CONTEXT_LIMIT,
    DEFAULT_PRICING,
    MODEL_CONTEXT_LIMITS,
    MODEL_PRICING,
    calculate_cost,
    get_context_limit,
    get_pricing,
    is_estimated_price,
)


CURATED = sorted(MODEL_REGISTRY)


class TestNothingCuratedIsGuessed:

    @pytest.mark.parametrize("model", CURATED)
    def test_it_has_a_real_price(self, model):
        assert not is_estimated_price(model), (
            f"{model} is on our curated list but costed from DEFAULT_PRICING"
        )

    @pytest.mark.parametrize("model", CURATED)
    def test_it_has_a_real_context_limit(self, model):
        # No listed model's window is 128000, so getting it back means the
        # fallback fired. Believing a larger window than the model has is what
        # makes auto-compaction fire too late; believing a smaller one throws
        # away history the model could still have seen.
        assert get_context_limit(model) != DEFAULT_CONTEXT_LIMIT, (
            f"{model} is on our curated list but has no context limit of its own"
        )


class TestOneModelHasOnePrice:
    """Aliases of the same model must not disagree about what it costs."""

    ALIASES = [
        ("claude-sonnet-4-20250514", "claude-sonnet-4"),
        ("claude-sonnet-4-20250514", "claude-sonnet-4-0"),
        ("claude-opus-4-1-20250805", "claude-opus-4-1"),
        ("claude-opus-4-1-20250805", "claude-opus-4.1"),
        ("claude-opus-4-20250514", "claude-opus-4"),
        ("claude-opus-4-20250514", "claude-opus-4-0"),
        ("claude-3-7-sonnet-20250219", "claude-3-7-sonnet-latest"),
    ]

    @pytest.mark.parametrize("dated,alias", ALIASES)
    def test_the_alias_costs_what_the_dated_name_costs(self, dated, alias):
        assert calculate_cost(alias, 1_000_000, 1_000_000) == calculate_cost(
            dated, 1_000_000, 1_000_000
        ), f"{alias} and {dated} are the same model at two different prices"

    @pytest.mark.parametrize("dated,alias", ALIASES)
    def test_the_alias_has_the_same_context_limit(self, dated, alias):
        assert get_context_limit(alias) == get_context_limit(dated)


class TestTheClaudeRowsAreReachableBothWays:
    """Whichever spelling the table keys on, the other one must resolve."""

    def test_sonnet_4_costs_three_and_fifteen(self):
        pricing = get_pricing("claude-sonnet-4")
        assert (pricing["input"], pricing["output"]) == (3.00, 15.00)

    def test_opus_4_1_costs_fifteen_and_seventyfive(self):
        pricing = get_pricing("claude-opus-4-1")
        assert (pricing["input"], pricing["output"]) == (15.00, 75.00)

    def test_claude_carries_two_hundred_thousand(self):
        assert get_context_limit("claude-sonnet-4") == 200_000


class TestTheGeminiClassDefaultIsPriced:
    """`GeminiLLM()` used to default to an unpriced name.

    It defaulted to gemini-2.0-flash-exp, which is unpriced *and* retired — see
    test_the_registry_offers_models_that_exist. Both halves are fixed: the
    default now names a served model, and that model has a price.
    """

    def test_the_default_is_not_a_guess(self):
        import inspect

        from connectonion.core.llm import GeminiLLM

        default = inspect.signature(GeminiLLM.__init__).parameters["model"].default
        assert not is_estimated_price(default)


class TestTheFallbackStillFallsBack:
    """Widening the table must not turn every unknown name into a hit."""

    def test_a_model_nobody_ships_is_still_a_guess(self):
        assert is_estimated_price("some-model-from-2031")

    def test_it_still_returns_the_default_object(self):
        assert get_pricing("some-model-from-2031") is DEFAULT_PRICING

    def test_a_co_prefixed_unknown_is_still_a_guess(self):
        assert is_estimated_price("co/some-model-from-2031")

# Whether any key shadows a longer one is already asserted by
# test_the_longest_price_match_wins.py, which owns that rule.
