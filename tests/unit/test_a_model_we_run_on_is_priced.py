"""One of our own agents runs on a model with no price of its own.

chat.openonion.ai shows browser-agent (0x156b17…f62a, online) as:

    gemini-3-flash-preview · careful · v1.1.0

That name is not in MODEL_PRICING. It falls through to DEFAULT_PRICING at
1.00/3.00, and `is_estimated_price` correctly returns True so the cost prints
with a `~` — the mechanism this release added, working. Honest, and still twice
the real input rate.

Solved from what the backend actually charged, two calls on co/gemini-3-flash-preview:

    in=   4  total=  28  charged=$0.000074
    in=2006  total=2101  charged=$0.001288

With cost = input x a + (total - input) x b, those two equations give

    a = $0.50 / 1M input      b = $3.00 / 1M output

and both reproduce their charge to the cent — a solve, not a fit. So the fallback
overstated input by 2x and matched output by coincidence.

The model is in neither FREE_MANAGED_MODELS nor PAID_MANAGED_MODELS, so the CLI
does not offer it; the backend routes it anyway and one of our production agents
uses it. A row it is, then, priced from measurement rather than left to a default
that happens to be wrong.

cached is not measured — this backend reports cached_tokens as 0 — so it follows
the 25% rule the table states for Google models, the same convention every row
but one obeys. See test_the_cached_rate_follows_its_stated_rule.py, which owns
that rule and the confirmed rates for gemini-3.6-flash.
"""

import pytest

from connectonion.core.usage import (
    DEFAULT_PRICING, MODEL_PRICING, calculate_cost, get_pricing, is_estimated_price,
)


MODEL = "gemini-3-flash-preview"

# (input_tokens, total_tokens, charged_usd) — measured against the real backend.
CHARGES = [(4, 28, 0.000074), (2006, 2101, 0.001288)]


class TestItHasAPriceOfItsOwn:

    def test_it_is_in_the_table(self):
        assert MODEL in MODEL_PRICING

    def test_it_is_not_the_default(self):
        assert get_pricing(MODEL) != DEFAULT_PRICING

    def test_the_cost_is_no_longer_flagged_as_a_guess(self):
        assert not is_estimated_price(MODEL)

    def test_the_co_prefixed_name_resolves_too(self):
        """Every caller passes co/<model>; the bare name is what the table holds."""
        assert get_pricing(f"co/{MODEL}") == get_pricing(MODEL)


class TestTheRatesAreTheMeasuredOnes:

    def test_input_is_fifty_cents(self):
        assert MODEL_PRICING[MODEL]["input"] == 0.50

    def test_output_is_three_dollars(self):
        assert MODEL_PRICING[MODEL]["output"] == 3.00

    @pytest.mark.parametrize("input_tokens,total_tokens,charged", CHARGES)
    def test_the_table_reproduces_what_was_charged(self, input_tokens, total_tokens,
                                                   charged):
        """The billing model, confirmed here and for gemini-3.6-flash: input at
        the input rate, every remaining token — completion and reasoning both —
        at the output rate."""
        output_tokens = total_tokens - input_tokens

        computed = calculate_cost(MODEL, input_tokens, output_tokens)

        assert computed == pytest.approx(charged, abs=5e-7), (
            f"table says ${computed:.6f}, the backend charged ${charged:.6f}"
        )

    def test_the_old_default_did_not_reproduce_it(self):
        """Why the row is worth having: the fallback was 2x on input."""
        input_tokens, total_tokens, charged = CHARGES[1]
        by_default = (input_tokens * DEFAULT_PRICING["input"]
                      + (total_tokens - input_tokens) * DEFAULT_PRICING["output"]) / 1e6

        assert by_default != pytest.approx(charged, abs=5e-7)


class TestCachedFollowsTheStatedRule:
    """Not measured — this backend reports cached_tokens as 0 — so it takes the
    convention the table states rather than a number I would be inventing."""

    def test_it_is_a_quarter_of_input(self):
        row = MODEL_PRICING[MODEL]

        assert row["cached"] == pytest.approx(row["input"] * 0.25)


class TestItHasTheRightContextWindow:
    """The same gap in the other table, with a functional cost rather than a
    cosmetic one.

    With no entry in MODEL_CONTEXT_LIMITS the model got the 128,000 default while
    every other Gemini in the table is 1,000,000. So `% ctx` read 7.8x high for
    browser-agent, and auto-compaction — which triggers off that reading — fired
    about eight times earlier than it should, discarding context that was not
    close to full and paying for a compaction call to do it.

    Measured: a 150,008-token prompt was accepted and answered.

        accepted: in=150008 total=150075 charged=$0.07520
        reply: ok

    which rules out 128,000 outright. The recorded 1,000,000 is the figure every
    other Gemini row in this table carries; what the test pins is the part that
    was measured — that 150k fits, and that the 128k default is gone.

    (That charge also re-confirms the rates above at 75,000x the token scale of
    the two small calls: 150008 x 0.50/1M + 67 x 3.00/1M = $0.07520.)
    """

    def test_it_is_not_the_default_limit(self):
        from connectonion.core.usage import get_context_limit

        assert get_context_limit(MODEL) != 128000

    def test_a_prompt_of_the_size_that_worked_fits(self):
        from connectonion.core.usage import get_context_limit

        assert get_context_limit(MODEL) > 150008

    def test_it_matches_the_other_gemini_models(self):
        from connectonion.core.usage import MODEL_CONTEXT_LIMITS

        assert MODEL_CONTEXT_LIMITS[MODEL] == MODEL_CONTEXT_LIMITS["gemini-3.6-flash"]


class TestEveryPricedModelHasAContextLimit:
    """The gap was findable without a model in hand: a row in one table and not
    the other. This is the check that would have found it."""

    def test_no_priced_model_falls_back_to_the_default_limit(self):
        from connectonion.core.usage import MODEL_CONTEXT_LIMITS

        missing = [m for m in MODEL_PRICING if m not in MODEL_CONTEXT_LIMITS]

        assert not missing, (
            "priced but with no context limit, so `% ctx` and auto-compaction "
            f"use the 128k default: {missing}"
        )
