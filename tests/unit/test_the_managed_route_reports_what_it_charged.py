"""The managed route knows the real price and prints its own guess instead.

Every `co/` response carries what the server actually billed:

    CompletionUsage(completion_tokens=9, prompt_tokens=3, total_tokens=114,
                    cost_usd=0.000837, balance_after=1245.371763)

`OpenOnionLLM.complete()` ignores `cost_usd` and recomputes from the local
price table. Measured against the default model, `co/gemini-3.7-flash`, on a
one-line prompt:

    shown      $0.000072
    charged    $0.000837        11.6x

The gap is not a rounding error and not a stale price. `prompt_tokens` plus
`completion_tokens` is 12; `total_tokens` is 114. The reasoning models bill for
tokens the OpenAI-shaped fields never mention, so no arithmetic over those two
numbers can arrive at the right answer — which is why the server sends the
answer.

This is the default route and the default model, so it is the number nearly
everyone sees. #601 and #602 made the local table trustworthy; that work only
reaches the screen if the screen uses the server's figure when there is one.

Local calculation stays for providers that report no cost — OpenAI, Anthropic
and the rest bill an account we cannot see.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from connectonion.core.llm import OpenOnionLLM


def _response(cost_usd=None, prompt=3, completion=9, total=114, cached=0):
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                            total_tokens=total,
                            prompt_tokens_details=SimpleNamespace(cached_tokens=cached))
    if cost_usd is not None:
        usage.cost_usd = cost_usd
    message = SimpleNamespace(content="hi", tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


@pytest.fixture
def llm():
    with patch.dict("os.environ", {"OPENONION_API_KEY": "test-token"}):
        with patch("openai.OpenAI"):
            return OpenOnionLLM(model="co/gemini-3.7-flash")


def _complete(llm, response):
    llm.client = MagicMock()
    llm.client.chat.completions.create.return_value = response
    return llm.complete([{"role": "user", "content": "Say hi"}])


class TestTheServersFigureWins:

    def test_the_cost_is_the_one_that_was_charged(self, llm):
        result = _complete(llm, _response(cost_usd=0.000837))

        assert result.usage.cost == 0.000837

    def test_not_the_one_the_local_table_would_give(self, llm):
        """3 in and 9 out of gemini-3.6-flash is $0.000072 by the table — the
        number that was on screen while $0.000837 left the account."""
        result = _complete(llm, _response(cost_usd=0.000837))

        assert result.usage.cost != pytest.approx(0.000072, abs=1e-6)

    def test_a_free_call_is_reported_as_free(self, llm):
        """0.0 is a figure, not a missing value. Treating it as absent would
        fall back to the table and invent a charge for a call that had none."""
        result = _complete(llm, _response(cost_usd=0.0))

        assert result.usage.cost == 0.0

    def test_the_token_counts_are_still_the_providers(self, llm):
        result = _complete(llm, _response(cost_usd=0.000837))

        assert result.usage.input_tokens == 3
        assert result.usage.output_tokens == 9

    def test_cached_prompt_tokens_reach_the_trace_contract(self, llm):
        result = _complete(
            llm,
            _response(cost_usd=0.000837, prompt=100, cached=80),
        )

        assert result.usage.input_tokens == 100
        assert result.usage.cached_tokens == 80


class TestWithoutOneNothingChanges:

    def test_a_response_with_no_cost_falls_back_to_the_table(self, llm):
        from connectonion.core.usage import calculate_cost

        result = _complete(llm, _response(cost_usd=None))

        assert result.usage.cost == calculate_cost("co/gemini-3.7-flash", 3, 9, 0)

    def test_and_it_is_not_zero(self, llm):
        """The fallback has to stay a real estimate: a provider that reports no
        cost is the common case, not an excuse to show nothing."""
        result = _complete(llm, _response(cost_usd=None))

        assert result.usage.cost > 0
