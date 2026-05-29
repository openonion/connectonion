"""Unit tests for connectonion/core/exceptions.py — error transformation classes."""

import pytest

from connectonion.core.exceptions import (
    InsufficientCreditsError,
    LLMConnectionError,
    ProviderServiceError,
    ToolRejectedError,
)


# ---------- InsufficientCreditsError ----------

class _FakeAPIError(Exception):
    """Stand-in for openai.APIStatusError."""
    def __init__(self, detail=None):
        super().__init__("api")
        self.body = {'detail': detail} if detail is not None else {}


def test_insufficient_credits_extracts_billing_attrs():
    err = InsufficientCreditsError(_FakeAPIError({
        'balance': 0.12, 'required': 0.50, 'shortfall': 0.38,
        'address': '0xshort', 'public_key': '0xfullkey',
        'message': 'pay up',
    }))
    assert err.balance == 0.12
    assert err.required == 0.50
    assert err.shortfall == 0.38
    assert err.address == '0xshort'
    assert err.public_key == '0xfullkey'
    assert err.original_message == 'pay up'


def test_insufficient_credits_defaults_when_body_empty():
    """If the API didn't return billing fields, use safe defaults instead of crashing."""
    err = InsufficientCreditsError(_FakeAPIError())  # no detail
    assert err.balance == 0
    assert err.required == 0
    assert err.shortfall == 0
    assert err.address == 'unknown'
    assert err.public_key == 'unknown'


def test_insufficient_credits_message_includes_key_values():
    err = InsufficientCreditsError(_FakeAPIError({
        'balance': 0.10, 'required': 1.00, 'shortfall': 0.90,
        'address': '0xabcd',
    }))
    msg = str(err)
    assert 'Insufficient ConnectOnion Credits' in msg
    assert '0.1000' in msg
    assert '0.9000' in msg
    assert '0xabcd' in msg


def test_insufficient_credits_preserves_original_as_cause():
    original = _FakeAPIError({'balance': 1})
    err = InsufficientCreditsError(original)
    assert err.__cause__ is original


def test_insufficient_credits_handles_missing_body_attribute():
    """Some errors might not have `.body` at all — should use empty default."""
    class NoBody(Exception):
        pass

    err = InsufficientCreditsError(NoBody("x"))
    assert err.balance == 0  # default kicks in


# ---------- LLMConnectionError ----------

def test_llm_connection_captures_model_and_base_url():
    err = LLMConnectionError(
        TimeoutError("connect timed out"),
        model="gpt-4o",
        base_url="https://api.openai.com",
    )
    assert err.model == "gpt-4o"
    assert err.base_url == "https://api.openai.com"
    assert err.error_type == "TimeoutError"


def test_llm_connection_message_includes_model_and_diagnostics():
    err = LLMConnectionError(
        ConnectionRefusedError("nope"),
        model="claude-3-5-sonnet-latest",
        base_url="https://api.anthropic.com",
    )
    msg = str(err)
    assert 'Connection Failed' in msg
    assert 'claude-3-5-sonnet-latest' in msg
    assert 'api.anthropic.com' in msg
    assert 'ConnectionRefusedError' in msg


def test_llm_connection_preserves_cause():
    original = TimeoutError("timeout")
    err = LLMConnectionError(original, model="x", base_url="y")
    assert err.__cause__ is original


def test_llm_connection_defaults_when_no_model_or_url():
    err = LLMConnectionError(RuntimeError("?"))
    assert err.model == "unknown"
    assert err.base_url == ""


# ---------- ProviderServiceError ----------

class _StatusError(Exception):
    def __init__(self, body, status_code=503):
        super().__init__("upstream")
        self.body = body
        self.status_code = status_code


def test_provider_service_extracts_dict_detail():
    err = ProviderServiceError(_StatusError({'detail': 'upstream is down'}))
    assert err.detail == 'upstream is down'
    assert err.status_code == 503


def test_provider_service_extracts_string_body():
    err = ProviderServiceError(_StatusError("plain text body"))
    assert err.detail == "plain text body"


def test_provider_service_falls_back_to_message_attribute():
    """No `.body` → use `.message`; no `.message` → use str()."""
    class MsgOnly(Exception):
        message = "via message attr"

    err = ProviderServiceError(MsgOnly())
    assert "via message attr" in err.detail


def test_provider_service_status_code_defaults_to_503():
    class NoCode(Exception):
        body = "boom"

    err = ProviderServiceError(NoCode())
    assert err.status_code == 503


def test_provider_service_message_includes_status_and_detail():
    err = ProviderServiceError(_StatusError({'detail': 'gateway timeout'}, status_code=504))
    msg = str(err)
    assert '504' in msg
    assert 'gateway timeout' in msg


def test_provider_service_preserves_cause():
    original = _StatusError({'detail': 'x'})
    err = ProviderServiceError(original)
    assert err.__cause__ is original


# ---------- ToolRejectedError ----------

def test_tool_rejected_is_value_error_subclass():
    """ToolRejectedError must derive from ValueError so callers can catch either."""
    assert issubclass(ToolRejectedError, ValueError)


def test_tool_rejected_carries_message():
    with pytest.raises(ToolRejectedError, match="user said no"):
        raise ToolRejectedError("user said no")
