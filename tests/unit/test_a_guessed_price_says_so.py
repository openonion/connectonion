"""What a cost figure means when the model is not in the table.

`get_pricing` falls back to DEFAULT_PRICING for anything it does not know, and
returns it exactly like a real entry. Nothing downstream can tell the
difference, so a fabricated number is displayed with the same confidence as a
looked-up one.

Two things that makes wrong today:

    gemini-3.6-flash      {'input': 1.5, 'output': 7.5, 'cached': 0.15}
    co/gemini-3.6-flash   {'input': 1.0, 'output': 3.0, 'cached': 0.5}   ← default

`co/` is the managed route — the default path, the one with the free credits —
and **not one of the 26 priced models carries that prefix**. Every agent on the
default setup has its output tokens costed at 3.00 when the model's own price
is 7.50.

The prefix fix is the easy half. The half that lasts is saying when the number
is a guess: the next model added to the world is unknown again, and a silent
default is how this went unnoticed while it was the default.
"""

import pytest

from connectonion.core.usage import (
    DEFAULT_PRICING,
    calculate_cost,
    get_pricing,
    is_estimated_price,
)


class TestTheManagedRouteFindsItsModel:

    @pytest.mark.parametrize("model", [
        "co/gemini-3.6-flash", "co/o4-mini", "co/claude-sonnet-4-5",
    ])
    def test_a_co_model_is_priced_like_the_model_it_is(self, model):
        bare = model[len("co/"):]

        if get_pricing(bare) is DEFAULT_PRICING:
            pytest.skip(f"{bare} is not priced either — nothing to compare")

        assert get_pricing(model) == get_pricing(bare)

    def test_the_default_model_is_not_costed_by_guesswork(self):
        assert not is_estimated_price("co/gemini-3.6-flash"), (
            "the default path prices its tokens from a generic fallback"
        )

    def test_the_output_price_actually_changes(self):
        """3.00 vs 7.50 is not a rounding difference."""
        guessed = 1_000_000 / 1_000_000 * DEFAULT_PRICING["output"]
        real = calculate_cost("co/gemini-3.6-flash", 0, 1_000_000)

        assert real != pytest.approx(guessed)


class TestAGuessAnnouncesItself:
    """The durable half. The next model the world ships is unknown again."""

    def test_an_unknown_model_is_flagged(self):
        assert is_estimated_price("some-model-nobody-has-heard-of")

    def test_a_known_model_is_not(self):
        assert not is_estimated_price("o4-mini")

    def test_a_dated_variant_is_not(self):
        """Prefix matching already handles o4-mini-2024-08-06."""
        assert not is_estimated_price("o4-mini-2024-08-06")


class TestNothingElseMoves:

    def test_known_models_cost_what_they_did(self):
        # 1M in at $1.25/M + 100k out at $10/M
        assert calculate_cost("gemini-2.5-pro", 1_000_000, 100_000) == pytest.approx(2.25)

    def test_an_unknown_model_still_returns_a_number(self):
        """A guess is better than a crash in a display path — it just has to
        be labelled."""
        assert calculate_cost("nobody-has-heard-of-this", 1_000_000, 0) > 0


class TestTheDisplaySaysWhichItIs:
    """A guess printed in the same shape as a fact is the whole problem."""

    def _line(self, model, capsys):
        """The console writes to stderr, not to a console object one can swap —
        which is why the first version of this test failed while the code was
        already right."""
        from connectonion.console import Console
        from connectonion.core.usage import TokenUsage

        Console().log_llm_response(model, 120.0, 0,
                                   TokenUsage(input_tokens=1000, output_tokens=100,
                                              cost=0.0042))
        return capsys.readouterr().err

    def test_a_known_model_prints_a_plain_figure(self, capsys):
        line = self._line("o4-mini", capsys)

        assert "$0.0042" in line
        assert "~$" not in line, line

    def test_an_unknown_model_is_marked(self, capsys):
        line = self._line("some-model-nobody-has-heard-of", capsys)

        assert "~$0.0042" in line, line
