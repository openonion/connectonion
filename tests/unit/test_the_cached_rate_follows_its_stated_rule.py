"""Pin Gemini cached-input pricing, including the published 3.6 exception."""

import pytest

from connectonion.core.usage import MODEL_PRICING


GOOGLE_ROWS = {name: row for name, row in MODEL_PRICING.items()
               if name.startswith("gemini")}

PUBLISHED_EXCEPTIONS = {
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-4-argon",
}


class TestTheCommonGoogleRowsUseTheSeventyFivePercentDiscount:

    @pytest.mark.parametrize("name", sorted(set(GOOGLE_ROWS) - PUBLISHED_EXCEPTIONS))
    def test_cached_is_a_quarter_of_input(self, name):
        row = GOOGLE_ROWS[name]
        if "cached" not in row:
            pytest.skip(f"{name} states no cached price")

        assert row["cached"] == pytest.approx(row["input"] * 0.25), (
            f"{name}: cached {row['cached']} is "
            f"{row['cached'] / row['input']:.0%} of input {row['input']}"
        )

    def test_the_rows_were_actually_found(self):
        """A rename would otherwise empty the parametrize and pass silently."""
        assert len(GOOGLE_ROWS) >= 6


class TestTheProviderPublishedException:
    """Google lists 3.6 Flash cached input at $0.15/M, a 90% discount."""

    def test_gemini_3_6_flash_is_ten_percent_of_input(self):
        row = MODEL_PRICING["gemini-3.6-flash"]
        assert row["cached"] == pytest.approx(row["input"] * 0.10)
        assert row["cached"] == 0.15

    def test_gemini_3_7_flash_is_ten_percent_of_promotional_input(self):
        row = MODEL_PRICING["gemini-3.7-flash"]
        assert row == {"input": 0.75, "output": 3.75, "cached": 0.075}

    def test_gemini_3_8_flash_is_ten_percent_of_promotional_input(self):
        row = MODEL_PRICING["gemini-3.8-flash"]
        assert row == {"input": 0.75, "output": 3.75, "cached": 0.075}

    def test_gemini_4_argon_cached_is_five_percent_of_input(self):
        """Google publishes Argon's implicit-cache rate at $0.10/M against
        $2.00/M input — a 95% discount, not the 75% every other Gemini row
        follows. Pricing page, checked 2026-10-15. Explicit caching is not
        supported for this model; only implicit caching is."""
        row = MODEL_PRICING["gemini-4-argon"]
        assert row == {"input": 2.00, "output": 10.00, "cached": 0.10}
        assert row["cached"] == pytest.approx(row["input"] * 0.05)


class TestTheConfirmedRatesStay:
    """What the reconciliation above establishes, so a later edit cannot quietly
    move the two numbers that were measured against real charges."""

    def test_input_is_one_fifty(self):
        assert MODEL_PRICING["gemini-3.6-flash"]["input"] == 1.50

    def test_output_is_seven_fifty(self):
        assert MODEL_PRICING["gemini-3.6-flash"]["output"] == 7.50
