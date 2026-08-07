"""Flash-Lite is billed as Flash, and shown as a known price.

The prefix fallback accepts any name that starts with a table key, on the
assumption that a longer name is the same model with a date pinned:

    o4-mini-2025-04-16  ->  o4-mini

True for a date. False for a suffix that names a different model. Measured
against the provider's live list — 13 real, callable Gemini models take a price
that belongs to something else, and `is_estimated_price` says False for every
one of them, so `console.py` shows the figure without its `~`:

    gemini-2.5-flash-lite                  -> gemini-2.5-flash   $0.15/$0.60
    gemini-2.5-flash-image                 -> gemini-2.5-flash   $0.15/$0.60
    gemini-2.5-flash-preview-tts           -> gemini-2.5-flash   $0.15/$0.60
    gemini-2.5-flash-native-audio-latest   -> gemini-2.5-flash   $0.15/$0.60
    gemini-3.5-flash-lite                  -> gemini-3.5-flash   $1.50/$9.00
    gemini-2.0-flash-lite                  -> gemini-2.0-flash   $0.10/$0.40

Lite is cheaper than Flash, image and audio are priced on different units
entirely. A wrong number is bad; a wrong number with the confidence of a looked-up
one is what `is_estimated_price` exists to prevent:

    DEFAULT_PRICING is returned exactly like a real entry, so a fabricated
    number reaches a display with the same confidence as a known one.

Same shape as the shadowing rule already enforced *inside* the table
(test_the_longest_price_match_wins): a shorter entry must not answer for a longer
one. This is that rule at the table's edge, where the longer name is a real model
nobody listed.

So a prefix match is accepted only when what follows the key is a version — digits,
dots, dashes, or `latest`. A remainder carrying a new word is a different model,
and its price is honestly unknown, which prints as `~`.
"""

import pytest

from connectonion.core.usage import (
    DEFAULT_PRICING,
    get_context_limit,
    get_pricing,
    is_estimated_price,
)


class TestAVariantSuffixIsNotADate:

    @pytest.mark.parametrize(
        "model",
        [
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash-image",
            "gemini-2.5-flash-preview-tts",
            "gemini-2.5-flash-native-audio-latest",
            "gemini-3.5-flash-lite",
            "gemini-2.0-flash-lite",
            "gemini-2.5-pro-preview-tts",
        ],
    )
    def test_it_does_not_borrow_the_shorter_models_price(self, model):
        assert is_estimated_price(model), (
            f"{model} is a different model from the key it starts with, and is "
            f"being shown that model's price as if it were looked up"
        )

    def test_lite_is_not_charged_as_flash(self):
        assert get_pricing("gemini-2.5-flash-lite") is DEFAULT_PRICING

    def test_the_estimate_is_marked_for_the_display(self):
        """console.py prefixes `~` on exactly this signal."""
        assert is_estimated_price("gemini-2.5-flash-lite") is True


class TestADateSuffixStillResolves:
    """The case the fallback was built for must keep working."""

    @pytest.mark.parametrize(
        "model,expected_input",
        [
            ("o4-mini-2025-04-16", 1.10),
            ("gemini-2.0-flash-001", 0.10),
            ("claude-sonnet-4-20250514", 3.00),
            ("claude-opus-4-20250514", 15.00),
            ("claude-opus-4-1-20250805", 15.00),
            ("claude-3-7-sonnet-20250219", 3.00),
        ],
    )
    def test_it_takes_the_family_price(self, model, expected_input):
        assert get_pricing(model)["input"] == expected_input

    @pytest.mark.parametrize(
        "model", ["claude-sonnet-4-0", "claude-opus-4-0", "claude-opus-4.1"]
    )
    def test_a_bare_alias_still_resolves(self, model):
        assert not is_estimated_price(model)

    def test_latest_still_resolves(self):
        assert not is_estimated_price("claude-3-7-sonnet-latest")

    def test_a_dated_preview_is_the_same_model(self):
        """`gemini-2.5-pro-preview-05-06` is 2.5 Pro before release.

        A first version of this rule rejected every `-preview`, which broke
        test_doctor_mentions_a_model_it_no_longer_prices — it asserts this exact
        name is priced, and it is right to. `preview` counts as part of a version
        only when digits follow it.
        """
        assert not is_estimated_price("gemini-2.5-pro-preview-05-06")

    def test_a_preview_of_something_else_is_not(self):
        assert is_estimated_price("gemini-2.5-pro-preview-tts")

    def test_the_context_limit_follows_the_same_rule(self):
        assert get_context_limit("claude-sonnet-4-20250514") == 200_000


class TestTheContextLimitDoesNotOverstateAVariant:
    """Believing a window the model does not have is worse than not knowing."""

    def test_a_variant_falls_back(self):
        from connectonion.core.usage import DEFAULT_CONTEXT_LIMIT

        assert get_context_limit("gemini-2.5-flash-lite") == DEFAULT_CONTEXT_LIMIT

    def test_a_dated_name_does_not(self):
        assert get_context_limit("gemini-2.0-flash-001") == 1_000_000


class TestExactMatchesAreUntouched:

    @pytest.mark.parametrize(
        "model", ["gemini-2.5-flash", "gemini-3.6-flash", "o4-mini", "claude-sonnet-4"]
    )
    def test_a_listed_model_is_never_an_estimate(self, model):
        assert not is_estimated_price(model)

    def test_the_managed_prefix_still_resolves(self):
        assert not is_estimated_price("co/gemini-3.6-flash")

    def test_a_managed_variant_is_an_estimate_too(self):
        assert is_estimated_price("co/gemini-2.5-flash-lite")
