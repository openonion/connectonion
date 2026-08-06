"""A model you can select must be one the provider still serves.

`MODEL_REGISTRY` offered three Gemini models that Google has retired. Asked for
any of them the provider answers 404 — including for this module's own class
default, so

    GeminiLLM(api_key=...)          # no model argument

could not complete a single call. Every one measured by sending a real request:

    DEAD      gemini-3-pro-preview           404 "no longer available"
    DEAD      gemini-2.0-flash-exp           404 "not found for API version v1main"
    DEAD      gemini-2.0-flash-thinking-exp  404 "not found for API version v1main"
    CALLABLE  gemini-3.6-flash               $0.00001200
    CALLABLE  gemini-3.5-flash               $0.00001350
    CALLABLE  gemini-3-pro-image-preview     $0.00000613
    CALLABLE  gemini-2.5-pro                 $0.00001375
    CALLABLE  gemini-2.5-flash               $0.00000105

"no longer available" rather than a quota or permission error, so this is not an
artefact of the key used.

## Why this test sends a request instead of reading ListModels

The first version of this test compared the registry against the ListModels
endpoint. It passed, and it was wrong: ListModels advertises both
gemini-3-pro-preview and gemini-2.0-flash, and neither can complete a call.
Comparing against that list found two of the three dead models and reported the
third as healthy — and on the strength of it I had briefly added gemini-2.0-flash
to the registry as a live replacement.

Listed is not callable. Only a call establishes that a name works, so that is
what this asks, once per model.

`gemini-2.0-flash` and `gemini-3-pro-preview` keep their rows in MODEL_PRICING
deliberately: a price for a retired model costs nothing and lets an old session's
tokens still cost correctly. The registry is the list of what a user may select,
and that is the one that has to be true.
"""

import inspect
import os

import pytest

from connectonion.core.llm import MODEL_REGISTRY, GeminiLLM
from connectonion.core.usage import is_estimated_price


GEMINI = sorted(m for m, p in MODEL_REGISTRY.items() if p == "google")
RETIRED = (
    "gemini-3-pro-preview",
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash-thinking-exp",
)


def _class_default():
    return inspect.signature(GeminiLLM.__init__).parameters["model"].default


class TestTheRetiredModelsAreGone:

    @pytest.mark.parametrize("model", RETIRED)
    def test_it_is_no_longer_offered(self, model):
        assert model not in MODEL_REGISTRY, (
            f"{model} answers 404 from Google; offering it hands the user a "
            "name that cannot complete a call"
        )


class TestTheClassDefaultCanActuallyBeCalled:
    """`GeminiLLM()` with no model must name something that exists."""

    def test_the_default_is_not_retired(self):
        assert _class_default() not in RETIRED

    def test_the_default_is_routable(self):
        assert _class_default() in MODEL_REGISTRY

    def test_the_default_is_priced(self):
        assert not is_estimated_price(_class_default())


class TestSomethingIsStillOnOffer:
    """Guard against fixing this by emptying the registry."""

    def test_gemini_models_remain(self):
        assert len(GEMINI) >= 4

    def test_the_flagship_is_there(self):
        assert "gemini-3.6-flash" in MODEL_REGISTRY


@pytest.mark.network
class TestEveryOfferedModelAnswers:
    """The only check that can notice the next retirement.

    One real request per model. Costs a few tokens; deselected in CI along with
    the rest of the network suite.
    """

    @pytest.fixture(scope="class")
    def key(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            pytest.skip("no GEMINI_API_KEY")
        return api_key

    @pytest.mark.parametrize("model", GEMINI)
    def test_it_completes_a_call(self, model, key):
        response = GeminiLLM(api_key=key, model=model).complete(
            [{"role": "user", "content": "Reply with the single word: ok"}]
        )

        assert response.usage.output_tokens > 0

    def test_the_class_default_completes_a_call(self, key):
        response = GeminiLLM(api_key=key).complete(
            [{"role": "user", "content": "Reply with the single word: ok"}]
        )

        assert response.usage.output_tokens > 0
