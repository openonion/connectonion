"""Which entry a model name falls back to when it is not listed exactly.

`get_pricing` and `get_context_limit` walk their table and take a key the name
starts with. Taking the *first* one let dict order decide, and that was wrong
whenever one entry was a prefix of another:

    gpt-4o  ⊂  gpt-4o-mini          gpt-4o-mini-2024-07-18 → gpt-4o's price
    o1      ⊂  o1-mini              o1-mini-2024-09-12     → o1's 200000 limit

Seventeen times the cost, and seventy-two thousand tokens of context the model
did not have. Exact matches are tried first, so listed names were safe; a
pinned, dated name is not listed, and pinning a date is what production does.

Those two pairs are gone — every pre-2025 model was dropped — so this asserts
the rule against a table built for the purpose. The rule is what has to
survive: the next time two entries share a prefix, nobody will be looking.
"""

import pytest

from connectonion.core import usage


SHADOWED = {
    "aurora":        {"input": 10.0, "output": 30.0, "cached": 5.0},
    "aurora-mini":   {"input": 0.5,  "output": 1.5,  "cached": 0.25},
}
SHADOWED_LIMITS = {"aurora": 200_000, "aurora-mini": 128_000}


@pytest.fixture
def shadowed(monkeypatch):
    monkeypatch.setattr(usage, "MODEL_PRICING", SHADOWED)
    monkeypatch.setattr(usage, "MODEL_CONTEXT_LIMITS", SHADOWED_LIMITS)


class TestTheMoreSpecificNameWins:

    def test_a_dated_variant_takes_its_own_price(self, shadowed):
        assert usage.get_pricing("aurora-mini-2025-06-01") == SHADOWED["aurora-mini"]

    def test_not_the_shorter_entry_it_also_starts_with(self, shadowed):
        assert usage.get_pricing("aurora-mini-2025-06-01") != SHADOWED["aurora"]

    def test_the_same_holds_for_the_context_limit(self, shadowed):
        assert usage.get_context_limit("aurora-mini-2025-06-01") == 128_000

    def test_the_shorter_name_still_matches_its_own_variants(self, shadowed):
        assert usage.get_pricing("aurora-2025-06-01") == SHADOWED["aurora"]

    def test_the_managed_route_resolves_the_same_way(self, shadowed):
        assert usage.get_pricing("co/aurora-mini-2025-06-01") == SHADOWED["aurora-mini"]


class TestTheRealTableHasNoneOfThis:
    """Kept as a check rather than an assumption: if a prefix pair is ever
    added back, the rule above is what stands between it and a wrong bill."""

    def test_no_entry_shadows_another(self):
        names = list(usage.MODEL_PRICING)
        pairs = [(a, b) for a in names for b in names
                 if a != b and b.startswith(a)]

        assert pairs == [], f"prefix pairs are back: {pairs}"

    def test_the_two_tables_cover_the_same_models(self):
        assert set(usage.MODEL_PRICING) == set(usage.MODEL_CONTEXT_LIMITS)
