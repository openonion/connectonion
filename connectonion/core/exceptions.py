"""
ConnectOnion exceptions.

Purpose: Custom exceptions for ConnectOnion framework with formatted, actionable error messages
LLM-Note:
  Dependencies: usage (FREE_MANAGED_MODELS, for the list PaidModelRequiredError offers) | imported by [llm.py] | tested by [test_a_paid_model_says_which_ones_are_free.py]
  Data flow: OpenOnionLLM._call catches openai.APIStatusError → 402 becomes InsufficientCreditsError, 503 becomes ProviderServiceError, 403 with error='paid_account_required' becomes PaidModelRequiredError, 401 becomes LLMAuthenticationError whose message names the caller's key unless oo-api labelled the 401 as an upstream provider's; any other status is logged and re-raised
  State/Effects: parses error detail from API response | formats a message naming what to do next | preserves original error in __cause__
  Integration: exposes InsufficientCreditsError, PaidModelRequiredError, ProviderServiceError and the LLM* error family
  Performance: lightweight exception creation | formats string message once on init
  Errors: none (this module defines error types)
"""


class LLMProviderError(Exception):
    """Base for every failure that came from an LLM provider.

    Exists so `except LLMProviderError` means "the model call failed" regardless
    of which provider handled it. Before this, the same auth failure surfaced as
    openai.AuthenticationError on gpt-*, anthropic.AuthenticationError on
    claude-*, and a bare ValueError("Groq API Error: ...") on groq/* — so the
    only portable handler was `except Exception`, which also swallows bugs.

    The original SDK exception is always chained as __cause__: translating must
    not cost the traceback that says what actually happened.
    """


# oo-api answers a co/ model's 401 in two different situations with the same
# status. Its auth dependency rejects the caller's own token with a bare detail
# ("Invalid token", "Token expired. ..."); a 401 from the upstream provider is
# passed through with a label naming it ("Anthropic API error: 401 - ...",
# "Upstream proxy error 401: ..."). Every co/ 401 used to be reported as the
# second, so a mistyped key sent people to wait or open a support ticket (#1728).
_UPSTREAM_LABELS = ("API error", "Upstream proxy error")


def _managed_auth_message(original_error, model: str) -> str:
    body = getattr(original_error, "body", None)
    detail = body.get("detail") if isinstance(body, dict) else None
    detail = detail if isinstance(detail, str) else ""
    if any(label in detail for label in _UPSTREAM_LABELS):
        return (
            f"The managed provider credential for {model} was rejected. "
            "This is a service-side configuration problem; retry later or "
            "contact OpenOnion support."
        )
    # Any other 401 comes from oo-api checking the caller's token, so name the
    # caller's fix. oo-api's own reason is short and never echoes the token;
    # it is kept because "expired" and "moved to <address>" need different
    # next steps. Upstream text is not echoed: it can carry provider internals.
    reason = f" ({detail.rstrip('.')})" if detail else ""
    return (
        f"Your OpenOnion API key was rejected{reason}. Run `co auth` to get a "
        "fresh one, or check the api_key you passed and OPENONION_API_KEY."
    )


class LLMAuthenticationError(LLMProviderError):
    """The provider rejected the credentials (401/403)."""

    def __init__(self, original_error, model: str = "unknown"):
        self.model = model
        self.status_code = getattr(original_error, "status_code", None)
        if model.startswith("co/"):
            message = _managed_auth_message(original_error, model)
        else:
            message = (
                f"Authentication failed for {model}. Check the API key for this "
                "provider — the key that works for one provider is not the key for "
                "another."
            )
        super().__init__(message)
        self.__cause__ = original_error


class LLMRateLimitError(LLMProviderError):
    """The provider is rate limiting or the quota is exhausted (429)."""

    def __init__(self, original_error, model: str = "unknown"):
        self.model = model
        self.status_code = getattr(original_error, "status_code", 429)
        super().__init__(
            f"Rate limited by the provider for {model}. Retry after a pause, or "
            f"check the plan's quota. Original: "
            f"{type(original_error).__name__}: {original_error}"
        )
        self.__cause__ = original_error


class InsufficientCreditsError(LLMProviderError):
    """
    Raised when an LLM request fails due to insufficient ConnectOnion credits.

    This indicates your ConnectOnion managed keys account needs more credits.
    Join Discord to add credits or ask Aaron for free credits to get started.

    Attributes:
        balance (float): Current account balance in USD
        required (float): Cost of the failed request in USD
        shortfall (float): Additional credits needed in USD
        address (str): Your ConnectOnion account address
    """

    def __init__(self, original_error):
        """
        Create InsufficientCreditsError from OpenAI API error.

        Args:
            original_error: The original openai.APIStatusError from the API
        """
        # Parse error details from API response
        body = getattr(original_error, 'body', {}) or {}
        detail = body.get('detail', {})

        # Extract billing information
        self.balance = detail.get('balance', 0)
        self.required = detail.get('required', 0)
        self.shortfall = detail.get('shortfall', 0)
        self.address = detail.get('address', 'unknown')  # Server provides formatted address
        self.public_key = detail.get('public_key', 'unknown')  # Full public key
        self.original_message = detail.get('message', '')

        # Create clear, beautiful error message
        message = self._format_message()
        super().__init__(message)

        # Keep original error for debugging
        self.__cause__ = original_error

    def _format_message(self):
        """Format a clear, actionable error message."""
        return (
            f"\n"
            f"{'='*70}\n"
            f"❌ Insufficient ConnectOnion Credits\n"
            f"{'='*70}\n"
            f"\n"
            f"Account:     {self.address}\n"
            f"Balance:     ${self.balance:.4f}\n"
            f"Required:    ${self.required:.4f}\n"
            f"Shortfall:   ${self.shortfall:.4f}\n"
            f"\n"
            f"💡 How to add credits:\n"
            f"   • Purchase: https://o.openonion.ai/purchase\n"
            f"   • Check balance: Run 'co status' in terminal\n"
            f"   • Pricing: https://docs.connectonion.com/models/pricing\n"
            f"\n"
            f"{'='*70}\n"
        )


class LLMConnectionError(LLMProviderError):
    """
    Raised when the LLM API request times out or fails to connect.

    Common causes: proxy/VPN adding latency, network issues, API server down.
    """

    def __init__(self, original_error, model: str = "unknown", base_url: str = ""):
        self.model = model
        self.base_url = base_url
        self.error_type = type(original_error).__name__

        message = self._format_message()
        super().__init__(message)
        self.__cause__ = original_error

    def _format_message(self):
        return (
            f"\n"
            f"{'='*70}\n"
            f"Connection Failed\n"
            f"{'='*70}\n"
            f"\n"
            f"Model:       {self.model}\n"
            f"Server:      {self.base_url}\n"
            f"Error:       {self.error_type}\n"
            f"\n"
            f"{self._advice()}"
            f"\n"
            f"{'='*70}\n"
        )

    def _advice(self) -> str:
        """What to try, addressed to the server that was actually unreachable.

        A request to 127.0.0.1 does not involve the user's internet connection
        and no VPN will fix it, so saying so sends someone to debug a working
        network while `ollama serve` sits there not running. The local case is
        both the more likely one for these addresses and the cheaper one to fix,
        and it deserves its own words.
        """
        if self._is_local():
            start = "   - ollama serve\n" if self._looks_like_ollama() else ""
            return (
                f"Possible causes:\n"
                f"   - The server is not running\n"
                f"   - It is listening on a different port\n"
                f"\n"
                f"Try:\n"
                f"{start}"
                f"   - Start the local server, then retry\n"
                f"   - Check the server URL shown above directly\n"
            )
        return (
            f"Possible causes:\n"
            f"   - Proxy/VPN slowing down the connection\n"
            f"   - Network connectivity issue\n"
            f"   - API server temporarily unavailable\n"
            f"\n"
            f"Try:\n"
            f"   - Check your internet connection\n"
            f"   - Disable proxy/VPN and retry\n"
            f"   - Check the server URL shown above directly\n"
        )

    def _is_local(self) -> bool:
        """Whether the unreachable server was on this machine."""
        host = str(self.base_url or "").split("//")[-1].split("/")[0].split(":")[0].strip("[]")
        return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local")

    def _looks_like_ollama(self) -> bool:
        """Ollama's own port, so the one command worth naming can be named."""
        return ":11434" in str(self.base_url or "")


class PaidModelRequiredError(LLMProviderError):
    """Raised when a free account asks for a model behind a paid provider (403).

    Not the same as InsufficientCreditsError. That one means the money ran out;
    this one means the money is there and does not cover this provider. A new
    account has $5 of free credits that work with Google-routed models, so this
    is the most likely first failure anyone has — and until now the only one of
    the three without a formatted message, so it reached the user as a raw
    openai.PermissionDeniedError with the response JSON printed twice.

    Attributes:
        model_requested (str): The model the backend refused
        free_models (tuple): Managed models a free account can call
    """

    def __init__(self, original_error):
        # Read the list from the one place that maintains it, rather than
        # restating it here. The CLI prints the same tuple after `co auth`, and a
        # second copy would be the next thing to go stale.
        from .usage import FREE_MANAGED_MODELS

        body = getattr(original_error, 'body', {}) or {}
        detail = body.get('detail', {}) if isinstance(body, dict) else {}

        self.model_requested = detail.get('model_requested', 'unknown')
        self.free_models = FREE_MANAGED_MODELS
        self.original_message = detail.get('message', '')

        super().__init__(self._format_message())
        self.__cause__ = original_error

    def _format_message(self):
        offered = "\n".join(f"   • {m}" for m in self.free_models)
        return (
            f"\n"
            f"{'='*70}\n"
            f"❌ '{self.model_requested}' needs purchased credits\n"
            f"{'='*70}\n"
            f"\n"
            f"Free credits cover Google-routed models. These work now:\n"
            f"{offered}\n"
            f"\n"
            f"💡 To use {self.model_requested}:\n"
            f"   • Purchase credits: https://o.openonion.ai\n"
            f"   • Check balance: Run 'co status' in terminal\n"
            f"\n"
            f"{'='*70}\n"
        )


class ProviderServiceError(LLMProviderError):
    """Raised when the LLM provider API returns a service error (503)."""

    def __init__(self, original_error):
        self.status_code = getattr(original_error, 'status_code', 503)
        body = getattr(original_error, 'body', getattr(original_error, 'message', str(original_error)))

        # Extract detail from body if it's a dict
        if isinstance(body, dict):
            self.detail = body.get('detail', str(body))
        else:
            self.detail = str(body)

        message = (
            f"\n{'='*70}\n"
            f"❌ Provider Service Error (HTTP {self.status_code})\n"
            f"{'='*70}\n\n"
            f"{self.detail}\n\n"
            f"{'='*70}\n"
        )
        super().__init__(message)
        self.__cause__ = original_error


class ToolRejectedError(ValueError):
    """Raised when a user rejects a tool execution request."""
