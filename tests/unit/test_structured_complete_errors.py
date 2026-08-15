"""structured_complete() must fail the same way complete() does.

A depleted balance is a depleted balance whichever method you called. The
documented InsufficientCreditsError carries balance/required/shortfall/address
(CLAUDE.md), and code is written to catch it specifically — so a raw
openai.APIStatusError from one of the two paths is a silent hole in that
contract.
"""

import httpx
import openai
import pytest
from pydantic import BaseModel

from connectonion.core.exceptions import (
    InsufficientCreditsError,
    LLMConnectionError,
    ProviderServiceError,
)
from connectonion.core.llm import OpenOnionLLM


class Answer(BaseModel):
    text: str


def _status_error(code: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://oo.openonion.ai/v1/chat/completions")
    body = {"detail": {"error": "insufficient_credits", "balance": 0.01,
                       "required": 0.5, "shortfall": 0.49, "address": "0xabc"}}
    response = httpx.Response(code, request=request, json=body)
    return openai.APIStatusError("boom", response=response, body=body)


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setenv("OPENONION_API_KEY", "test-key")
    return OpenOnionLLM(model="co/gemini-3.7-flash", api_key="test-key")


def _make_parse_raise(llm, exc):
    class FakeParse:
        def parse(self, **kwargs):
            raise exc

    class FakeCompletions:
        parse = None

    llm.client.beta.chat.completions.parse = lambda **kw: (_ for _ in ()).throw(exc)


class TestStructuredCompleteTranslatesFailures:
    def test_402_becomes_insufficient_credits(self, llm):
        """The case in the issue: an agent asking for structured output on a
        depleted account got a raw APIStatusError, so `except
        InsufficientCreditsError` never fired."""
        _make_parse_raise(llm, _status_error(402))

        with pytest.raises(InsufficientCreditsError):
            llm.structured_complete([{"role": "user", "content": "hi"}], Answer)

    def test_503_becomes_provider_service_error(self, llm):
        _make_parse_raise(llm, _status_error(503))

        with pytest.raises(ProviderServiceError):
            llm.structured_complete([{"role": "user", "content": "hi"}], Answer)

    def test_a_timeout_becomes_a_connection_error(self, llm):
        request = httpx.Request("POST", "https://oo.openonion.ai/v1/chat/completions")
        _make_parse_raise(llm, openai.APITimeoutError(request=request))

        with pytest.raises(LLMConnectionError):
            llm.structured_complete([{"role": "user", "content": "hi"}], Answer)

    def test_an_unmapped_status_still_surfaces(self, llm):
        """Translating is not swallowing — a 500 is still a 500."""
        _make_parse_raise(llm, _status_error(500))

        with pytest.raises(openai.APIStatusError):
            llm.structured_complete([{"role": "user", "content": "hi"}], Answer)


class TestCompleteStillBehavesTheSame:
    """The shared helper must not have changed the path that already worked."""

    def test_402_becomes_insufficient_credits(self, llm):
        llm.client.chat.completions.create = lambda **kw: (_ for _ in ()).throw(_status_error(402))

        with pytest.raises(InsufficientCreditsError):
            llm.complete([{"role": "user", "content": "hi"}])

    def test_a_timeout_becomes_a_connection_error(self, llm):
        request = httpx.Request("POST", "https://oo.openonion.ai/v1/chat/completions")
        llm.client.chat.completions.create = lambda **kw: (_ for _ in ()).throw(
            openai.APITimeoutError(request=request))

        with pytest.raises(LLMConnectionError):
            llm.complete([{"role": "user", "content": "hi"}])
