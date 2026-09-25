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


def _oo_api_401(detail):
    """A 401 exactly as oo-api sends it. Its HTTPException handler (main.py,
    checked at deployed tag v0.1.19) returns {"detail": ..., "request_id": ...}."""
    request = httpx.Request("POST", "https://oo.openonion.ai/v1/chat/completions")
    body = {"detail": detail, "request_id": "req-test"}
    response = httpx.Response(401, request=request, json=body)
    return openai.AuthenticationError(f"Error code: 401 - {body}", response=response, body=body)


def _make_fail(llm, exc):
    """Make the next provider call raise, whichever client shape it uses."""
    raiser = lambda **kw: (_ for _ in ()).throw(exc)
    if hasattr(llm.client, "messages"):          # anthropic
        llm.client.messages.create = raiser
    else:                                        # openai-compatible
        llm.client.chat.completions.create = raiser


OPENAI_LIKE = ["o4-mini", "groq/llama-3.3-70b-versatile", "grok/grok-4",
               "openrouter/meta-llama/llama-3-8b", "mistral/mistral-small"]


class TestAuthFailsTheSameWayEverywhere:
    @pytest.mark.parametrize("model", OPENAI_LIKE)
    def test_openai_compatible_providers(self, model, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        for var in ("GROQ_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY"):
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

    # Every upstream 401 path in oo-api llm/service.py at deployed tag v0.1.19:
    # forward_to_openai, forward_to_gemini, forward_to_anthropic, and the
    # LLM_PROXY_URL pass-through in route_completion.
    @pytest.mark.parametrize("detail", [
        'OpenAI API error: 401 - {"error": {"message": "Incorrect API key"}}',
        'Gemini API error: 401 - {"error": {"code": 401}}',
        'Anthropic API error: 401 - {"type": "error", "error": {"type": "authentication_error"}}',
        'Upstream proxy error 401: {"error": "invalid key"}',
    ])
    def test_managed_upstream_credential_failure_is_a_service_error(self, detail):
        """oo-api forwards an upstream provider's 401 with its own label
        ("Anthropic API error: 401 - ..."). That really is OpenOnion's key,
        so the user can do nothing but wait or report it."""
        llm = create_llm("co/claude-sonnet-4", api_key="caller-token")
        original = _oo_api_401(detail)
        _make_fail(llm, original)

        with pytest.raises(LLMAuthenticationError) as caught:
            llm.complete([{"role": "user", "content": "hi"}])

        assert caught.value.model == "co/claude-sonnet-4"
        assert "service-side configuration" in str(caught.value)
        assert "caller-token" not in str(caught.value)
        assert caught.value.__cause__ is original


class TestAManagedKeySaysWhoseItIs:
    """#1728: llm_do("say hi", api_key="bad-key") told the caller the problem was
    on OpenOnion's side and to retry later, so they waited instead of fixing
    their own key. oo-api rejects the caller's token with a bare 401 from its
    auth dependency; only an upstream provider's 401 carries an "API error" or
    "Upstream proxy error" label. The message must follow whose key it was."""

    def _llm_do_fails_with(self, monkeypatch, original):
        from openai.resources.chat.completions import Completions
        from connectonion import llm_do

        def reject(self, **kwargs):
            raise original

        monkeypatch.setattr(Completions, "create", reject)
        with pytest.raises(LLMAuthenticationError) as caught:
            llm_do("say hi", api_key="bad-key")
        return caught.value

    # Every 401 detail require_auth (auth/routes.py, deployed tag v0.1.19) can
    # send; a revoked token arrives as "Invalid token".
    @pytest.mark.parametrize("detail", [
        "Invalid token",
        "Authorization header missing",
        "Invalid authorization format. Use: Bearer {token}",
        "Token expired. Authenticate again with /api/v1/auth",
        "This account moved to 0xabc. This token was issued before the migration "
        "and names the old address. Authenticate again with the key you migrated to.",
    ])
    def test_a_rejected_caller_key_names_the_callers_fix(self, monkeypatch, detail):
        error = self._llm_do_fails_with(monkeypatch, _oo_api_401(detail))

        message = str(error)
        assert "service-side" not in message
        assert "retry later" not in message
        assert "Your OpenOnion API key was rejected" in message
        assert "co auth" in message
        assert "OPENONION_API_KEY" in message
        assert "bad-key" not in message

    def test_the_servers_reason_is_kept(self, monkeypatch):
        """An expired token and a moved account need different next steps;
        oo-api says which, so pass that on rather than flatten it."""
        error = self._llm_do_fails_with(
            monkeypatch,
            _oo_api_401("Token expired. Authenticate again with /api/v1/auth"),
        )

        assert "Token expired" in str(error)
        assert "co auth" in str(error)


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
