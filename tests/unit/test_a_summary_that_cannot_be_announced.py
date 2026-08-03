"""A summary the relay will not accept, caught before it is sent.

`create_announce_message` documents "summary: agent capability description
(max 1000 chars)" and does not apply it. The relay does:

    {"type": "ERROR", "error": "Summary too long (max 1000 chars)"}

verified against the live relay with a 5,400-character summary, while a short
one got ANNOUNCE_OK.

The code already knows the number. `host()` truncates the summary it derives
from the system prompt:

    summary = sample.system_prompt[:1000] if sample.system_prompt else …

but passes a `summary:` from host.yaml through whole. So an operator who writes
a long one gets an agent that starts, serves locally, and is never registered —
the relay refuses every announce, and the reconnect loop retries forever.

It is not silent: the client prints `Relay error: …` in red. It scrolls past in
startup output, though, next to a banner that still says the relay is on. The
limit is knowable here, so it is applied here, and the operator is told what
was sent rather than left to match a red line against a config file.
"""

import pytest

from connectonion.network.announce import ANNOUNCE_SUMMARY_LIMIT, fit_summary


class TestASummaryIsCutToWhatCanBeSent:

    def test_a_long_one_is_shortened(self, capsys):
        fitted = fit_summary("很长的摘要。" * 900)

        assert len(fitted) <= ANNOUNCE_SUMMARY_LIMIT

    def test_the_operator_is_told(self, capsys):
        fit_summary("x" * 5000)

        out = capsys.readouterr().out
        assert '5000' in out and str(ANNOUNCE_SUMMARY_LIMIT) in out, out

    def test_it_says_where_to_change_it(self, capsys):
        """The value came from host.yaml; that is where the fix goes."""
        fit_summary("x" * 5000)

        assert 'host.yaml' in capsys.readouterr().out


class TestAnOrdinarySummaryIsUntouched:

    def test_it_is_returned_as_written(self, capsys):
        text = "把飞书云盘里的合同扫描件整理成结构化台账。"

        assert fit_summary(text) == text

    def test_nothing_is_printed(self, capsys):
        fit_summary("a short summary")

        assert capsys.readouterr().out == ""

    def test_exactly_at_the_limit_is_fine(self, capsys):
        text = "x" * ANNOUNCE_SUMMARY_LIMIT

        assert fit_summary(text) == text
        assert capsys.readouterr().out == ""

    def test_an_empty_summary_is_left_alone(self):
        assert fit_summary("") == ""
        assert fit_summary(None) is None
