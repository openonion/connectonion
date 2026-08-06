"""The Gemini rows state a rule for cached tokens; one of them breaks it.

MODEL_PRICING says, two lines above the data:

    # Google Gemini models - cached = 25% of input (75% discount)

Every row honours it except one:

    gemini-3.6-flash   input 1.50   cached 0.15     10%   ← and 0.15 is exactly
    gemini-3.5-flash   input 1.50   cached 0.375    25%      the row below's INPUT
    gemini-3-pro-preview  2.00      cached 0.50     25%
    gemini-2.5-pro        1.25      cached 0.3125   25%
    gemini-2.5-flash      0.15      cached 0.0375   25%
    gemini-2.0-flash      0.10      cached 0.025    25%

The input price is not the thing in doubt. Reconciled against what the backend
actually charged, twice:

    in=   4  total=  75   charged=$0.000539  predicted=$0.000539  ratio 1.0009
    in=2006  total=2092   charged=$0.003654  predicted=$0.003654  ratio 1.0000

where predicted = input_tokens x $1.50/1M + (total - input) x $7.50/1M. So 1.50
and 7.50 are exactly right for this model, and the billing model is: input at the
input rate, every remaining token — completion and reasoning both — at the output
rate. Which leaves cached at 10% of a confirmed input price, against a rule the
file states for itself.

It is NOT changed here. 0.375 would be a number I made up, and a made-up price is
what this release exists to remove — the `co/` path never reaches it either
(the server states the cost, and cached_tokens came back 0 even on an identical
6k-token prefix). It bites only a direct Gemini API call, where calculate_cost
uses this table and Gemini does report cached tokens.

So the discrepancy is recorded here, where a run will show it, instead of sitting
behind a comment that says the opposite. Filed for the authoritative figure.
"""

import pytest

from connectonion.core.usage import MODEL_PRICING


GOOGLE_ROWS = {name: row for name, row in MODEL_PRICING.items()
               if name.startswith("gemini")}

# The one row that does not follow the stated rule, and why it is still here.
UNRESOLVED = {"gemini-3.6-flash"}


class TestEveryGoogleRowFollowsTheStatedRule:

    @pytest.mark.parametrize("name", sorted(set(GOOGLE_ROWS) - UNRESOLVED))
    def test_cached_is_a_quarter_of_input(self, name):
        row = GOOGLE_ROWS[name]
        if "cached" not in row:
            pytest.skip(f"{name} states no cached price")

        assert row["cached"] == pytest.approx(row["input"] * 0.25), (
            f"{name}: cached {row['cached']} is "
            f"{row['cached'] / row['input']:.0%} of input {row['input']}, and the "
            f"comment above this table says 25%"
        )

    def test_the_rows_were_actually_found(self):
        """A rename would otherwise empty the parametrize and pass silently."""
        assert len(GOOGLE_ROWS) >= 6


class TestTheUnresolvedRowIsStillUnresolved:
    """When someone supplies the real figure, this fails and says what to do."""

    def test_gemini_3_6_flash_still_breaks_the_rule(self):
        row = MODEL_PRICING["gemini-3.6-flash"]

        assert row["cached"] != pytest.approx(row["input"] * 0.25), (
            "gemini-3.6-flash's cached price now follows the 25% rule. If that "
            "came from the provider's published figure, delete this test and "
            "drop the row from UNRESOLVED above — the rule now holds everywhere."
        )

    def test_it_is_flagged_where_the_price_is_written(self):
        """The table must say so too, or the next reader trusts the comment."""
        import inspect

        from connectonion.core import usage

        # The row spans several lines, so read from its key to its closing
        # brace. A same-line check passed only while the row was one line.
        lines = inspect.getsource(usage).splitlines()
        start = next(i for i, l in enumerate(lines) if '"gemini-3.6-flash": {' in l)
        row = []
        for line in lines[start:]:
            row.append(line)
            if "}" in line:
                break

        assert "unverified" in "\n".join(row).lower(), (
            "the row that breaks the documented rule carries no note saying so:\n"
            + "\n".join(row)
        )


class TestTheConfirmedRatesStay:
    """What the reconciliation above establishes, so a later edit cannot quietly
    move the two numbers that were measured against real charges."""

    def test_input_is_one_fifty(self):
        assert MODEL_PRICING["gemini-3.6-flash"]["input"] == 1.50

    def test_output_is_seven_fifty(self):
        assert MODEL_PRICING["gemini-3.6-flash"]["output"] == 7.50
