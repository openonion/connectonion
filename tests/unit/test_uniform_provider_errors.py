"""The same failure must raise the same type whichever provider handled it.

Before this, an auth rejection surfaced as openai.AuthenticationError on gpt-*,
anthropic.AuthenticationError on claude-*, and a bare
ValueError("Groq API Error: ...") on groq/* — so the only handler that worked
everywhere was `except Exception`, which also swallows bugs.
"""

import anthropic
import httpx
import openai
import pytest

from connectonion.core.exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMProviderError,
    LLMRateLimitError,
)
from connectonion.core.llm import create_llm


def _openai_error(cls, code):
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(code, request=request, json={"error": {"message": "no"}})
    return cls("denied", response=response, body=None)


def _anthropic_error(cls, code):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(code, request=request, json={"error": {"message": "no"}})
    return cls("denied", response=response, body=None)


def _make_fail(llm, exc):
    """Make the next provider call raise, whichever client shape it uses."""
    raiser = lambda **kw: (_ for _ in ()).throw(exc)
    if hasattr(llm.client, "messages"):          # anthropic
        llm.client.messages.create = raiser
    else:                                        # openai-compatible
        llm.client.chat.completions.create = raiser


OPENAI_LIKE = ["o4-mini", "groq/llama-3.3-70b-versatile", "grok/grok-4",
               "openrouter/meta-llama/llama-3-8b", "orcarouter/openai/gpt-4o-mini",
               "mistral/mistral-small"]


class TestAuthFailsTheSameWayEverywhere:
    @pytest.mark.parametrize("model", OPENAI_LIKE)
    def test_openai_compatible_providers(self, model, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        for var in ("GROQ_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY",
                    "ORCAROUTER_API_KEY", "MISTRAL_API_KEY"):
            monkeypatch.setenv(var, "k")
        llm = create_llm(model, api_key="k")
        _make_fail(llm, _openai_error(openai.AuthenticationError, 401))

        with pytest.raises(LLMAuthenticationError):
            llm.complete([{"role": "user", "content": "hi"}])

    def test_anthropic(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        llm = create_llm("claude-sonnet-4-20250514", api_key="k")
        _make_fail(llm, _anthropic_error(anthropic.AuthenticationError, 401))

        with pytest.raises(LLMAuthenticationError):
            llm.complete([{"role": "user", "content": "hi"}])

    def test_groq_no_longer_raises_a_bare_ValueError(self, monkeypatch):
        """Groq was the loudest inconsistency: it caught openai.APIError and
        re-raised ValueError, so callers could not even tell an auth failure
        from a bad argument."""
        monkeypatch.setenv("GROQ_API_KEY", "k")
        llm = create_llm("groq/llama-3.3-70b-versatile", api_key="k")
        _make_fail(llm, _openai_error(openai.AuthenticationError, 401))

        with pytest.raises(LLMAuthenticationError):
            llm.complete([{"role": "user", "content": "hi"}])

    def test_managed_provider_auth_is_a_service_error_for_the_user(self):
        llm = create_llm("co/claude-sonnet-4", api_key="caller-token")
        original = _openai_error(openai.AuthenticationError, 401)
        _make_fail(llm, original)

        with pytest.raises(LLMAuthenticationError) as caught:
            llm.complete([{"role": "user", "content": "hi"}])

        assert caught.value.model == "co/claude-sonnet-4"
        assert "service-side configuration" in str(caught.value)
        assert "caller-token" not in str(caught.value)
        assert caught.value.__cause__ is original


class TestRateLimit:
    def test_openai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        llm = create_llm("o4-mini", api_key="k")
        _make_fail(llm, _openai_error(openai.RateLimitError, 429))

        with pytest.raises(LLMRateLimitError):
            llm.complete([{"role": "user", "content": "hi"}])

    def test_anthropic(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        llm = create_llm("claude-sonnet-4-20250514", api_key="k")
        _make_fail(llm, _anthropic_error(anthropic.RateLimitError, 429))

        with pytest.raises(LLMRateLimitError):
            llm.complete([{"role": "user", "content": "hi"}])


class TestOneBaseCatchesThemAll:
    def test_every_translated_type_is_an_LLMProviderError(self):
        """The point of the change: one `except` that means "the model call
        failed" without also swallowing TypeErrors from our own code."""
        from connectonion.core.exceptions import (
            InsufficientCreditsError, ProviderServiceError)

        for cls in (LLMAuthenticationError, LLMRateLimitError, LLMConnectionError,
                    InsufficientCreditsError, ProviderServiceError):
            assert issubclass(cls, LLMProviderError)

    def test_the_original_error_is_still_reachable(self, monkeypatch):
        """Translating must not cost the traceback that says what happened."""
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        llm = create_llm("o4-mini", api_key="k")
        original = _openai_error(openai.AuthenticationError, 401)
        _make_fail(llm, original)

        with pytest.raises(LLMAuthenticationError) as caught:
            llm.complete([{"role": "user", "content": "hi"}])

        assert caught.value.__cause__ is original

    def test_an_unmapped_status_is_not_reclassified(self, monkeypatch):
        """A 400 is a bad request, not an auth failure. Inventing a category for
        it would make the shared types mean less, not more."""
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        llm = create_llm("o4-mini", api_key="k")
        _make_fail(llm, _openai_error(openai.BadRequestError, 400))

        with pytest.raises(openai.BadRequestError):
            llm.complete([{"role": "user", "content": "hi"}])
