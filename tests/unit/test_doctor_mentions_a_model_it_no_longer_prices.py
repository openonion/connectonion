"""After the upgrade, `co doctor` says whether your model is still priced.

1.6.0 dropped thirty models released before 2025 (#603). Routing was left
alone on purpose — code that still names `gpt-4o-mini` reaches OpenAI exactly
as before — but the price table no longer has an entry, so every figure shown
for it is `DEFAULT_PRICING`, flagged with a `~`:

    MODEL from .env      gpt-4o-mini
    is_estimated_price   True
    cost for 1M/100k     $1.30        (the real price is $0.21)

Six times too high, on a project that upgraded and changed nothing. The `~`
says the number is a guess; it does not say why, and nothing else does either.

`co doctor` is the command people run after an upgrade when something looks
off. On a 1.5-era project it reported "1 problem" about an unrelated symlink
and said nothing about the model — the one thing that had actually changed
underneath them.

This is not a `✗`. The agent works; only the accounting is approximate. It is
an `○`, next to the model, saying what happened and what to do about it.
"""

import pytest

from connectonion.cli.commands.doctor_commands import model_pricing_note


class TestARetiredModel:

    @pytest.mark.parametrize("model", ["gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet-20241022"])
    def test_is_reported(self, model):
        note = model_pricing_note(model)

        assert note, f"{model} is unpriced since 1.6.0 and nothing said so"

    def test_the_note_names_the_model(self):
        assert "gpt-4o-mini" in model_pricing_note("gpt-4o-mini")

    def test_the_note_says_costs_are_estimates(self):
        note = model_pricing_note("gpt-4o-mini").lower()

        assert "estimate" in note

    def test_it_does_not_claim_the_agent_is_broken(self):
        """Routing still works — this is about the figure, not the run."""
        note = model_pricing_note("gpt-4o-mini").lower()

        assert "fail" not in note and "error" not in note


class TestASupportedModel:

    @pytest.mark.parametrize("model", [
        "co/gemini-3.7-flash", "gemini-2.5-pro", "o4-mini",
        "claude-sonnet-4-20250514",
    ])
    def test_is_not_reported(self, model):
        assert model_pricing_note(model) is None

    def test_a_dated_variant_is_not_reported(self):
        """Prefix matching prices these; the note must not fire on them."""
        assert model_pricing_note("gemini-2.5-pro-preview-05-06") is None


class TestNoModel:

    @pytest.mark.parametrize("model", [None, "", "   "])
    def test_nothing_to_say(self, model):
        assert model_pricing_note(model) is None
