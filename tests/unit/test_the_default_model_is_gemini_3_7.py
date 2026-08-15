"""The product default is Gemini 3.7 everywhere a model can be omitted.

Issue #1002: when the user configures nothing, Agent, llm_do, and `co ai`
must all pick co/gemini-3.7-flash — the exact ID the managed backend
registered in oo-api#146. An explicitly chosen model is the user's and
stays untouched; the previous default remains available as the rollback.

Signature defaults are asserted directly: that is the value that applies
when the caller omits `model`, checked without a network or a home
directory in play.
"""

import inspect

from connectonion import Agent, llm_do
from connectonion.cli.co_ai.agent import create_agent
from connectonion.core.usage import FREE_MANAGED_MODELS

DEFAULT = "co/gemini-3.7-flash"
ROLLBACK = "co/gemini-3.6-flash"


def _model_default(fn):
    return inspect.signature(fn).parameters["model"].default


class TestOmittedModelSelectsGemini37:

    def test_agent(self):
        assert _model_default(Agent.__init__) == DEFAULT

    def test_llm_do(self):
        assert _model_default(llm_do) == DEFAULT

    def test_co_ai(self):
        assert _model_default(create_agent) == DEFAULT

    def test_the_three_agree(self):
        """The defaults drifted apart once; one constant now feeds them all."""
        assert (
            _model_default(Agent.__init__)
            == _model_default(llm_do)
            == _model_default(create_agent)
        )


class TestAnExplicitModelIsPreserved:

    def test_agent_keeps_what_the_user_chose(self):
        agent = Agent("t", api_key="fake_key", model="o4-mini")
        assert agent.llm.model == "o4-mini"

    def test_the_previous_default_is_still_accepted(self):
        # The managed route strips its co/ prefix; the model itself must
        # remain the one the user pinned, not the new default.
        agent = Agent("t", api_key="fake_key", model=ROLLBACK)
        assert agent.llm.model == ROLLBACK.removeprefix("co/")


class TestTheRollbackStaysAdvertised:

    def test_both_ids_are_on_the_free_list(self):
        assert DEFAULT in FREE_MANAGED_MODELS
        assert ROLLBACK in FREE_MANAGED_MODELS
