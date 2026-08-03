"""Which entry a model name falls back to when it is not listed exactly.

`get_pricing` walks MODEL_PRICING and takes the first key the name starts
with. Dict order therefore decides, and three entries are prefixes of others:

    'gpt-4o'  ⊂  'gpt-4o-mini'
    'o1'      ⊂  'o1-mini'
    'o1'      ⊂  'o1-preview'

Exact matches are tried first, so the listed names are safe. The pinned,
dated forms are not — and pinning a date is what production code does:

    gpt-4o-mini              input 0.15   output 0.60
    gpt-4o-mini-2024-07-18   input 2.50   output 10.00     ← gpt-4o's price
    o1-mini                  input 3.00   output 12.00
    o1-mini-2024-09-12       input 15.00  output 60.00     ← o1's price

Seventeen times the cost for the same model, depending on whether the name
carries its date.

The longest matching name is the most specific one, and specificity is what a
prefix match is for.
"""

import pytest

from connectonion.core.usage import calculate_cost, get_pricing


class TestADatedNameKeepsItsOwnPrice:

    @pytest.mark.parametrize("pinned,plain", [
        ("gpt-4o-mini-2024-07-18", "gpt-4o-mini"),
        ("o1-mini-2024-09-12", "o1-mini"),
        ("o1-preview-2024-09-12", "o1-preview"),
    ])
    def test_it_matches_the_model_it_names(self, pinned, plain):
        assert get_pricing(pinned) == get_pricing(plain), (
            f"{pinned} is priced as something else"
        )

    def test_the_difference_was_seventeenfold(self):
        plain = calculate_cost("gpt-4o-mini", 1_000_000, 100_000)
        pinned = calculate_cost("gpt-4o-mini-2024-07-18", 1_000_000, 100_000)

        assert pinned == pytest.approx(plain)

    def test_the_managed_route_gets_it_too(self):
        assert get_pricing("co/gpt-4o-mini-2024-07-18") == get_pricing("gpt-4o-mini")


class TestNothingElseMoves:

    @pytest.mark.parametrize("model", ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini",
                                       "gemini-3.6-flash"])
    def test_an_exactly_listed_model_is_unchanged(self, model):
        from connectonion.core.usage import MODEL_PRICING

        assert get_pricing(model) == MODEL_PRICING[model]

    def test_a_dated_variant_of_a_leaf_still_works(self):
        """gpt-4o-2024-08-06 has no longer competitor; it still finds gpt-4o."""
        assert get_pricing("gpt-4o-2024-08-06") == get_pricing("gpt-4o")

    def test_something_unknown_is_still_a_guess(self):
        from connectonion.core.usage import is_estimated_price

        assert is_estimated_price("a-model-from-next-year")


class TestTheContextLimitHasTheSameHazard:
    """Same loop, same three collisions, and a worse failure than a wrong
    number on screen.

        o1          200000
        o1-mini     128000

    `o1-mini-2024-09-12` took o1's 200000, so the agent believed it had
    seventy-two thousand tokens it did not have: auto-compaction fires too
    late and the provider rejects the request for length.
    """

    @pytest.mark.parametrize("pinned,plain", [
        ("o1-mini-2024-09-12", "o1-mini"),
        ("o1-preview-2024-09-12", "o1-preview"),
        ("gpt-4o-mini-2024-07-18", "gpt-4o-mini"),
    ])
    def test_a_dated_name_keeps_its_own_limit(self, pinned, plain):
        from connectonion.core.usage import get_context_limit

        assert get_context_limit(pinned) == get_context_limit(plain)

    def test_the_listed_names_are_unchanged(self):
        from connectonion.core.usage import MODEL_CONTEXT_LIMITS, get_context_limit

        for model, limit in MODEL_CONTEXT_LIMITS.items():
            assert get_context_limit(model) == limit

    def test_the_managed_route_finds_it(self):
        from connectonion.core.usage import get_context_limit

        assert get_context_limit("co/o1-mini") == get_context_limit("o1-mini")
