"""A free account picking a paid model gets a raw provider exception.

The managed backend has a distinct code for this. Asked for co/gpt-5 on a
freshly opened account — which is what a new user has — it answers:

    403 {'detail': {'error': 'paid_account_required',
                    'message': "Model 'gpt-5' uses a paid provider. Your free $5
                                credits work with Google-routed models. Purchase
                                credits to unlock all models: https://o.openonion.ai",
                    'model_requested': 'gpt-5'}}

`_call` translates 402 to InsufficientCreditsError and 503 to
ProviderServiceError, then logs anything else and re-raises it. So this one
surfaces as `openai.PermissionDeniedError`, and the user gets the JSON twice —
once from the logger, once from the traceback. Captured from a real run:

    [co] ○ gpt-5                                           1/100
    APIStatusError: status=403, message=Error code: 403 - {'detail': ...
    RAISED openai.PermissionDeniedError
    Error code: 403 - {'detail': {'error': 'paid_account_required', ...

Two lines above that, the banner said:

    balance: $5.00
    credits on me, go build —aaron

which is the same $5 the error is about. This is the most likely first failure a
new user has, and 402 — a *depleted* balance, the rarer case — is the one with a
formatted message.

The two are different conditions: 402 means the money ran out, 403 here means
the money is there but does not cover this provider. The fix is a third entry in
the same table, not a widening of InsufficientCreditsError.

The frames below are the real response body, not a hand-written one. The
docstring on `_call` already says why: a translation table with a fake on the
other side of it drifts, and the half that drifts is the half nobody tested.
"""

import openai
import pytest

from connectonion.core.exceptions import (
    InsufficientCreditsError,
    LLMProviderError,
    PaidModelRequiredError,
)
from connectonion.core.llm import OpenOnionLLM


REAL_403_BODY = {
    "detail": {
        "error": "paid_account_required",
        "message": (
            "Model 'gpt-5' uses a paid provider. Your free $5 credits work with "
            "Google-routed models. Purchase credits to unlock all models: "
            "https://o.openonion.ai"
        ),
        "model_requested": "gpt-5",
    }
}


def _raise_403():
    request = openai._models.construct_type(type_=object, value={})  # placeholder
    raise openai.PermissionDeniedError(
        message=f"Error code: 403 - {REAL_403_BODY}",
        response=_FakeResponse(403),
        body=REAL_403_BODY,
    )


class _FakeResponse:
    """openai's error types read .status_code and .headers off the response."""

    def __init__(self, status_code):
        self.status_code = status_code
        self.headers = {}
        self.request = None


@pytest.fixture
def llm():
    return OpenOnionLLM(api_key="test-token", model="co/gpt-5")


class TestItBecomesOurOwnError:

    def test_it_is_translated(self, llm):
        with pytest.raises(PaidModelRequiredError):
            llm._call(_raise_403)

    def test_it_is_an_llm_provider_error(self, llm):
        """So `except LLMProviderError` written against the family catches it."""
        with pytest.raises(LLMProviderError):
            llm._call(_raise_403)

    def test_it_is_not_confused_with_a_depleted_balance(self, llm):
        with pytest.raises(PaidModelRequiredError) as excinfo:
            llm._call(_raise_403)

        assert not isinstance(excinfo.value, InsufficientCreditsError)

    def test_the_original_error_is_kept(self, llm):
        with pytest.raises(PaidModelRequiredError) as excinfo:
            llm._call(_raise_403)

        assert isinstance(excinfo.value.__cause__, openai.PermissionDeniedError)


class TestTheMessageSaysWhatToDo:

    @pytest.fixture
    def message(self, llm):
        with pytest.raises(PaidModelRequiredError) as excinfo:
            llm._call(_raise_403)
        return str(excinfo.value)

    def test_it_names_the_model_that_was_refused(self, message):
        assert "gpt-5" in message

    def test_it_names_models_that_do_work(self, message):
        # The whole point: a new user needs a next step, not a diagnosis.
        assert "co/gemini-3.7-flash" in message

    def test_it_links_where_to_buy_credits(self, message):
        assert "o.openonion.ai" in message

    def test_it_does_not_dump_the_raw_json(self, message):
        assert "'detail'" not in message
        assert "paid_account_required" not in message


class TestTheAttributesAreReadable:
    """A caller may want to route on this rather than print it."""

    @pytest.fixture
    def error(self, llm):
        with pytest.raises(PaidModelRequiredError) as excinfo:
            llm._call(_raise_403)
        return excinfo.value

    def test_it_carries_the_requested_model(self, error):
        assert error.model_requested == "gpt-5"

    def test_it_carries_the_free_models(self, error):
        assert "co/gemini-3.7-flash" in error.free_models


class TestTheOtherRowsStillWork:
    """A third entry must not disturb the two that were there."""

    def test_402_is_still_insufficient_credits(self, llm):
        def raise_402():
            raise openai.APIStatusError(
                message="Error code: 402",
                response=_FakeResponse(402),
                body={"detail": {"balance": 0.0, "required": 0.01}},
            )

        with pytest.raises(InsufficientCreditsError):
            llm._call(raise_402)

    def test_an_unrecognised_status_still_reaches_the_caller(self, llm):
        def raise_418():
            raise openai.APIStatusError(
                message="Error code: 418",
                response=_FakeResponse(418),
                body={},
            )

        with pytest.raises(openai.APIStatusError):
            llm._call(raise_418)

    def test_a_successful_call_is_returned_untouched(self, llm):
        assert llm._call(lambda: "the response") == "the response"


class TestAnotherKindOf403IsNotMistakenForThis:
    """Keyed on the backend's error code, not on the status number.

    A 403 can mean other things. Telling a suspended account to go buy credits
    would send someone to a checkout that cannot help them.
    """

    def test_a_different_403_reaches_the_caller(self, llm):
        def raise_forbidden():
            raise openai.PermissionDeniedError(
                message="Error code: 403",
                response=_FakeResponse(403),
                body={"detail": {"error": "account_suspended",
                                 "message": "This account is suspended"}},
            )

        with pytest.raises(openai.PermissionDeniedError):
            llm._call(raise_forbidden)

    def test_a_403_with_no_body_reaches_the_caller(self, llm):
        def raise_bare():
            raise openai.PermissionDeniedError(
                message="Error code: 403", response=_FakeResponse(403), body=None
            )

        with pytest.raises(openai.PermissionDeniedError):
            llm._call(raise_bare)
