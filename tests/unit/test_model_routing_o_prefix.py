"""A model name starting with "o" is not automatically an OpenAI model.

`startswith("o")` sent every unprefixed name beginning with that letter to
OpenAI. The caller then got an OpenAI 404 for a model they never asked OpenAI
about — an error that describes the wrong problem, because the fault is the
routing, not the model choice.
"""

import pytest

from connectonion.core.llm import (
    OPENAI_REASONING_PREFIXES,
    AnthropicLLM,
    GeminiLLM,
    OpenAILLM,
    create_llm,
)


class TestUnknownModelsSaySo:
    @pytest.mark.parametrize("model", ["orca-2-13b", "olmo-7b", "openchat-3.5", "opus"])
    def test_a_non_openai_o_model_is_rejected_by_name(self, model):
        """All four are real open-model families. Each used to be routed to
        OpenAI, which answered about a model nobody had asked it for."""
        with pytest.raises(ValueError, match=model):
            create_llm(model, api_key="test-key")

    def test_the_error_names_the_model_the_caller_passed(self):
        """So the message points at the list to check, not at OpenAI."""
        with pytest.raises(ValueError) as caught:
            create_llm("orca-2-13b", api_key="test-key")

        assert "orca-2-13b" in str(caught.value)


class TestKnownModelsStillRoute:
    """The tightening must not strand the models it was protecting."""

    @pytest.mark.parametrize("model", ["o1", "o1-mini", "o1-preview", "o4-mini"])
    def test_registered_o_series_models_still_reach_openai(self, model):
        assert isinstance(create_llm(model, api_key="test-key"), OpenAILLM)

    @pytest.mark.parametrize("model", ["o3-mini", "o4-turbo"])
    def test_unregistered_but_real_o_series_families_still_infer(self, model):
        """The registry cannot list every variant OpenAI ships, so inference by
        family prefix has to keep working — that is what the allowlist is for."""
        assert isinstance(create_llm(model, api_key="test-key"), OpenAILLM)

    def test_gpt_models_are_untouched(self):
        assert isinstance(create_llm("gpt-4o", api_key="test-key"), OpenAILLM)

    def test_other_providers_are_untouched(self):
        assert isinstance(create_llm("claude-3-5-sonnet-20241022", api_key="k"), AnthropicLLM)
        assert isinstance(create_llm("gemini-1.5-pro", api_key="k"), GeminiLLM)

    def test_the_allowlist_is_prefixes_not_whole_names(self):
        """o1-mini must match on "o1" — listing whole names would need an entry
        per variant and go stale on the next OpenAI release."""
        assert "o1-mini".startswith(OPENAI_REASONING_PREFIXES)
        assert not "olmo-7b".startswith(OPENAI_REASONING_PREFIXES)
