"""`co/gpt-5` is on the PAID advertised list and was in neither table.

PAID_MANAGED_MODELS is what `co auth` offers a paying customer. Checked against
the price table:

    co/gemini-3.7-flash   priced=True   ctx=1,000,000
    co/gemini-3.5-flash   priced=True   ctx=1,000,000
    co/gemini-2.5-pro     priced=True   ctx=1,000,000
    co/gemini-2.5-flash   priced=True   ctx=1,000,000
    co/gpt-5              priced=False  ctx=  128,000   ← sold, and not priced
    co/o4-mini            priced=True   ctx=  200,000
    co/claude-sonnet-4    priced=True   ctx=  200,000

So every cost shown for the one model on that list a user pays extra for was
DEFAULT_PRICING at 1.00/3.00, marked only by a `~`, and its `% ctx` was measured
against the 128,000 default.

Measured against the real backend. Two calls,

    in=   9  comp= 74  total=   83  charged=$0.000751
    in=2010  comp=138  total= 2148  charged=$0.003893

solve to input $1.25/1M and output $10.00/1M, and a third call pins them at a
scale where the input rate is no longer weakly constrained:

    accepted: in=150012 comp=138 total=150150 charged=$0.188895
    predicted at 1.25/10.00 = $0.188895   ratio=1.0000

The context window is not guessed either. A deliberately oversized request was
refused, unbilled, and the provider stated the figure:

    "Input tokens exceed the configured limit of 272000 tokens.
     Your messages resulted in 450012 tokens."

272,000 — not the 128,000 we were using, and not a round number anyone would have
picked. `% ctx` is computed from input tokens (agent.py: `input_tokens / limit`),
so an input limit is the right thing to record.

The guard below is the mechanical version of how this was found: a name on an
advertised list with no row in the tables. It is the other direction from
test_a_model_we_run_on_is_priced.py's TestEveryPricedModelHasAContextLimit —
that one catches priced-but-no-limit, this one catches sold-but-not-priced.
Between them, a model cannot be half-registered.
"""

import pytest

from connectonion.core.usage import (
    FREE_MANAGED_MODELS, MODEL_CONTEXT_LIMITS, MODEL_PRICING, PAID_MANAGED_MODELS,
    calculate_cost, get_context_limit, is_estimated_price,
)


ADVERTISED = FREE_MANAGED_MODELS + PAID_MANAGED_MODELS

MODEL = "gpt-5"

# (input_tokens, total_tokens, charged_usd) — measured against the real backend.
CHARGES = [(9, 83, 0.000751), (2010, 2148, 0.003893), (150012, 150150, 0.188895)]


class TestEveryAdvertisedModelIsRegistered:
    """The check that would have found this without a model in hand."""

    def test_the_lists_are_not_empty(self):
        """A rename would otherwise empty the parametrize and pass silently."""
        assert len(ADVERTISED) >= 7

    @pytest.mark.parametrize("name", ADVERTISED)
    def test_it_has_a_real_price(self, name):
        assert not is_estimated_price(name), (
            f"{name} is advertised to users but has no row in MODEL_PRICING, so "
            f"every cost shown for it is DEFAULT_PRICING with a `~`"
        )

    @pytest.mark.parametrize("name", ADVERTISED)
    def test_it_has_its_own_context_limit(self, name):
        bare = name.split("/", 1)[1] if "/" in name else name

        assert bare in MODEL_CONTEXT_LIMITS, (
            f"{name} takes the 128k default, so `% ctx` and auto-compaction are "
            f"measured against the wrong window"
        )


class TestTheRatesAreTheMeasuredOnes:

    def test_input_is_one_twenty_five(self):
        assert MODEL_PRICING[MODEL]["input"] == 1.25

    def test_output_is_ten_dollars(self):
        assert MODEL_PRICING[MODEL]["output"] == 10.00

    @pytest.mark.parametrize("input_tokens,total_tokens,charged", CHARGES)
    def test_the_table_reproduces_what_was_charged(self, input_tokens, total_tokens,
                                                   charged):
        computed = calculate_cost(MODEL, input_tokens, total_tokens - input_tokens)

        assert computed == pytest.approx(charged, abs=1e-6), (
            f"table says ${computed:.6f}, the backend charged ${charged:.6f}"
        )

    def test_the_old_default_did_not_reproduce_it(self):
        """Why the row is worth having, on the largest of the three calls."""
        from connectonion.core.usage import DEFAULT_PRICING

        input_tokens, total_tokens, charged = CHARGES[-1]
        by_default = (input_tokens * DEFAULT_PRICING["input"]
                      + (total_tokens - input_tokens) * DEFAULT_PRICING["output"]) / 1e6

        assert by_default != pytest.approx(charged, abs=1e-6)


class TestTheContextWindowIsThe272kTheProviderStated:

    def test_it_is_not_the_default(self):
        assert get_context_limit(MODEL) != 128000

    def test_it_is_the_stated_figure(self):
        assert get_context_limit(MODEL) == 272000

    def test_the_size_that_was_accepted_fits(self):
        assert get_context_limit(MODEL) > 150012

    def test_the_size_that_was_refused_does_not(self):
        assert get_context_limit(MODEL) < 450012
