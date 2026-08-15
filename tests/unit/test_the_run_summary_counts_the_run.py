"""The line that closes every agent run reports zero, always.

    [co] ✓ complete · 0 tokens · $0.0000 · 8.9s

That is a real run: two model calls, a tool call, nine seconds, $0.0016 off the
balance. The summary sums the trace entries whose `type` is `llm_call`, and
usage is recorded on the `llm_result` entries — `llm_call` is written when the
request goes out, before there is anything to count:

    llm_call    keys: id, iteration, model, status, ts, type
    llm_result  keys: ..., usage: {input_tokens: 80, output_tokens: 18, cost: ...}

So the total is not merely wrong for one provider or one model. It is
structurally zero for every run there has ever been, which is why nobody read
it as a bug: a number that is always the same stops being read.

The pair matters more than either half. #601 and #602 made the price table
trustworthy and the managed route now reports what the server actually charged
— and all of that arrived at a line that prints $0.0000.
"""

import pytest

from connectonion.console import Console
from connectonion.core.usage import TokenUsage


def _session(*calls):
    """A trace shaped the way agent.py writes one: request, then result."""
    trace = [{"type": "user_input", "content": "hi"}]
    for input_tokens, output_tokens, cost in calls:
        trace.append({"type": "llm_call", "model": "co/gemini-3.7-flash",
                      "status": "pending"})
        # model_dump(), because that is what agent.py records — building the
        # TokenUsage object here instead made every test below pass over code
        # that raised AttributeError on the first real run.
        trace.append({"type": "llm_result", "model": "co/gemini-3.7-flash",
                      "usage": TokenUsage(input_tokens=input_tokens,
                                          output_tokens=output_tokens,
                                          cost=cost).model_dump()})
    return {"trace": trace}


def _summary(session, capsys) -> str:
    Console().print_completion(9.4, session)
    return capsys.readouterr().err


class TestASingleCall:

    def test_the_tokens_are_the_ones_that_were_used(self, capsys):
        line = _summary(_session((80, 18, 0.00102)), capsys)

        assert "98 tokens" in line, line

    def test_the_cost_is_the_one_that_was_charged(self, capsys):
        line = _summary(_session((80, 18, 0.00102)), capsys)

        assert "$0.0010" in line, line


class TestAWholeRun:
    """The run in the docstring: two calls around one tool call."""

    def test_every_call_is_counted(self, capsys):
        line = _summary(_session((80, 18, 0.00102), (213, 11, 0.00053)), capsys)

        assert "322 tokens" in line, line

    def test_the_costs_add_up(self, capsys):
        line = _summary(_session((80, 18, 0.00102), (213, 11, 0.00053)), capsys)

        assert "$0.0016" in line, line

    def test_thousands_are_still_abbreviated(self, capsys):
        line = _summary(_session((1200, 300, 0.01)), capsys)

        assert "1.5k tokens" in line, line


class TestNothingToCount:

    def test_a_run_with_no_model_call_is_zero(self, capsys):
        """Zero is the right answer here, and only here."""
        line = _summary({"trace": [{"type": "user_input", "content": "hi"}]}, capsys)

        assert "0 tokens" in line, line

    def test_a_result_without_usage_does_not_crash(self, capsys):
        """Some providers return no usage block at all."""
        session = {"trace": [{"type": "llm_result", "model": "x", "usage": None}]}

        line = _summary(session, capsys)

        assert "0 tokens" in line, line
