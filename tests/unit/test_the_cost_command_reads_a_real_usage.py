"""`/cost` in `co ai` reads its usage as a dict. It is a TokenUsage object.

    last_usage = getattr(agent, 'last_usage', None)
    if last_usage:
        input_tokens = last_usage.get('input_tokens', 0)

and agent.py sets it from the LLM response:

    self.last_usage = response.usage          # a TokenUsage

TokenUsage is a pydantic BaseModel, so there is no `.get`:

    AttributeError: 'TokenUsage' object has no attribute 'get'

The `if last_usage:` in front is why nobody hit it in a unit test — before the
first model call it is None and the block is skipped, so every path that never
called a model passes straight through. After one call, the command that reports
what you spent is the one that raises.

Two readers of the same attribute disagreeing about its type, and only one of
them is exercised: agent.py's own context_percent uses attribute access
(`self.last_usage.input_tokens`) three lines away and is correct.

Found while checking whether the billed_tokens fix had covered every place the
token total is computed. It had not — this file and tui/chat.py both rebuilt the
sum, and this one could not have run at all.
"""

import pytest

from connectonion.core.usage import TokenUsage


class _Agent:
    """Only what cmd_cost touches, with last_usage the type agent.py assigns."""

    def __init__(self, usage=None):
        self.llm = type("LLM", (), {"model": "co/gemini-3.6-flash"})()
        self.total_cost = 0.0014
        self.last_usage = usage
        self.context_percent = 12.0


@pytest.fixture
def cost_output(monkeypatch, capsys):
    from connectonion.cli.co_ai.commands import cost as cost_mod

    def _run(usage):
        cost_mod.set_agent(_Agent(usage))
        result = cost_mod.cmd_cost()
        return (capsys.readouterr().out or "") + (result or "")

    return _run


class TestItSurvivesARealUsageObject:

    def test_it_does_not_raise(self, cost_output):
        """The whole finding: one model call, then this command."""
        cost_output(TokenUsage(input_tokens=17, output_tokens=3,
                               total_tokens=205, cost=0.0014))

    def test_it_reports_the_input_and_output_tokens(self, cost_output):
        output = cost_output(TokenUsage(input_tokens=17, output_tokens=3,
                                        total_tokens=205, cost=0.0014))

        assert "17" in output
        assert "3" in output

    def test_the_total_is_the_billed_total(self, cost_output):
        """A cost report is the last place to print a token count that cannot be
        reconciled with the cost beside it — 20 next to $0.0014 is 29x off."""
        output = cost_output(TokenUsage(input_tokens=17, output_tokens=3,
                                        total_tokens=205, cost=0.0014))

        assert "205" in output

    def test_a_direct_provider_usage_totals_the_sum(self, cost_output):
        output = cost_output(TokenUsage(input_tokens=17, output_tokens=3,
                                        cost=0.00005))

        assert "20" in output


class TestNoUsageYetIsStillFine:
    """Before the first model call — the state in which this always worked."""

    def test_it_does_not_raise(self, cost_output):
        cost_output(None)

    def test_it_still_names_the_model(self, cost_output):
        assert "gemini" in cost_output(None)
