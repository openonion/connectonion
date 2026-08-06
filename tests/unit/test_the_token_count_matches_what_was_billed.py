"""The token count printed next to a cost cannot be reconciled with it.

Measured against the real backend on `co/gemini-3.6-flash`:

    prompt: 17   completion: 3   total: 243   cost_usd: 0.00172
    what we display:  20 tok · $0.0017

20 tokens at this model's rates is $0.00005. The line is off by 34x against
itself, and the tokens are 12x under what the server billed.

The cause is half a decision. core/llm.py already knows about this and says so:

    # The server bills the account and says what it took. Use that, not the
    # local table: prompt_tokens + completion_tokens is 12 on a call whose
    # total_tokens is 114, because the reasoning models charge for tokens the
    # OpenAI-shaped fields never name. Arithmetic over those two numbers came
    # out 11.6x under what was charged.

It then takes the server's `cost_usd` — and leaves the token count summed from
the two fields it just described as untrustworthy. The cost was fixed in one of
the two places the same fact is shown. That is the failure this release keeps
finding, this time between a number and the number beside it.

`input_tokens` and `output_tokens` stay as they are: they are the context-window
figures, and reasoning tokens are not in the context window, so the `% ctx`
reading is correct off them. What is added is the billed total, reported only
when the server states it — inventing one locally is how the 11.6x arose.
"""

import pytest

from connectonion.core.usage import TokenUsage, totals_from_trace


class TestTheUsageCarriesTheBilledTotal:

    def test_the_server_total_is_kept(self):
        usage = TokenUsage(input_tokens=17, output_tokens=3, total_tokens=243,
                           cost=0.00172)

        assert usage.billed_tokens == 243

    def test_without_a_server_total_it_falls_back_to_the_sum(self):
        """A direct provider call has no cost_usd and no reasoning tokens to
        hide; input + output is the whole story there."""
        usage = TokenUsage(input_tokens=17, output_tokens=3, cost=0.00005)

        assert usage.billed_tokens == 20

    def test_a_zero_total_is_treated_as_absent(self):
        """Pydantic defaults it to 0, and 0 billed tokens on a call that had
        input is not something a server says."""
        usage = TokenUsage(input_tokens=17, output_tokens=3, total_tokens=0)

        assert usage.billed_tokens == 20

    def test_the_context_figures_are_untouched(self):
        """These drive `% ctx`, where reasoning tokens do not belong."""
        usage = TokenUsage(input_tokens=17, output_tokens=3, total_tokens=243)

        assert usage.input_tokens == 17
        assert usage.output_tokens == 3


class TestTheCallLineShowsTheBilledTokens:

    @staticmethod
    def _line(usage, capsys):
        """Console, not a name I assumed — and stderr, which is where it writes
        (test_the_run_summary_counts_the_run.py reads the same stream)."""
        from connectonion.console import Console

        Console().log_llm_response("co/gemini-3.6-flash", 1200.0, 0, usage)
        return capsys.readouterr().err

    def test_it_prints_the_server_total(self, capsys):
        usage = TokenUsage(input_tokens=17, output_tokens=3, total_tokens=243,
                           cost=0.00172)

        assert "243 tok" in self._line(usage, capsys)

    def test_it_does_not_print_the_unreconcilable_sum(self, capsys):
        usage = TokenUsage(input_tokens=17, output_tokens=3, total_tokens=243,
                           cost=0.00172)

        assert "20 tok" not in self._line(usage, capsys)

    def test_a_direct_provider_call_is_unchanged(self, capsys):
        usage = TokenUsage(input_tokens=17, output_tokens=3, cost=0.00005)

        assert "20 tok" in self._line(usage, capsys)


class TestTheRunSummaryAddsUpTheBilledTokens:
    """totals_from_trace feeds the completion line, and summing the same two
    under-reporting fields there reproduces the same gap over a whole run."""

    TRACE = [
        {"type": "llm_result", "usage": {"input_tokens": 17, "output_tokens": 3,
                                         "total_tokens": 243, "cost": 0.00172}},
        {"type": "llm_result", "usage": {"input_tokens": 40, "output_tokens": 5,
                                         "total_tokens": 300, "cost": 0.0021}},
    ]

    def test_the_totals_use_the_billed_tokens(self):
        tokens, cost = totals_from_trace(self.TRACE)

        assert tokens == 543
        assert cost == pytest.approx(0.00382)

    def test_a_trace_without_totals_still_adds_up(self):
        """Older sessions on disk have no total_tokens key — reading one must not
        raise, and the sum is the best that entry can support."""
        trace = [{"type": "llm_result",
                  "usage": {"input_tokens": 17, "output_tokens": 3, "cost": 0.00005}}]

        tokens, cost = totals_from_trace(trace)

        assert tokens == 20
