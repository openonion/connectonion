"""Gemini 3.8 Flash compatibility at the direct ConnectOnion client boundary."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from connectonion.core.llm import GeminiLLM, OpenAILLM, create_llm
from connectonion.core.usage import MODEL_CONTEXT_LIMITS, MODEL_PRICING


MODEL = "gemini-3.8-flash"


def _gemini_response(*, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="done",
            tool_calls=tool_calls,
        ))],
        usage=SimpleNamespace(
            prompt_tokens=12,
            completion_tokens=4,
            prompt_tokens_details=SimpleNamespace(cached_tokens=2),
        ),
    )


class TestGemini38Registration:

    def test_factory_routes_to_google(self):
        llm = create_llm(MODEL, api_key="test-key")
        assert isinstance(llm, GeminiLLM)
        assert llm.model == MODEL

    def test_price_and_context_are_published_values(self):
        assert MODEL_PRICING[MODEL] == {
            "input": 0.75,
            "output": 3.75,
            "cached": 0.075,
        }
        assert MODEL_CONTEXT_LIMITS[MODEL] == 1_048_576

    def test_openai_remains_selectable(self):
        assert isinstance(create_llm("o4-mini", api_key="test-key"), OpenAILLM)


class TestGemini38Completion:

    def test_tools_thought_signature_usage_and_compatibility_parameters(self):
        tool_call = SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(name="lookup", arguments='{"q":"Sydney"}'),
            extra_content={"thought_signature": "signed"},
        )
        llm = GeminiLLM(api_key="test-key", model=MODEL)
        llm.client.chat.completions.create = Mock(
            return_value=_gemini_response(tool_calls=[tool_call])
        )

        response = llm.complete(
            [{"role": "user", "content": "weather"}],
            tools=[{
                "name": "lookup",
                "description": "Look up weather",
                "parameters": {"type": "object", "properties": {}},
            }],
            reasoning_effort="medium",
            temperature=0.1,
            top_p=0.8,
            stream=True,
            stream_options={"include_usage": True},
        )

        sent = llm.client.chat.completions.create.call_args.kwargs
        assert sent["model"] == MODEL
        assert sent["reasoning_effort"] == "medium"
        assert sent["tool_choice"] == "auto"
        assert sent["tools"][0]["function"]["name"] == "lookup"
        assert {"temperature", "top_p", "stream", "stream_options"}.isdisjoint(sent)
        assert response.content == "done"
        assert response.tool_calls[0].arguments == {"q": "Sydney"}
        assert response.tool_calls[0].extra_content == {"thought_signature": "signed"}
        assert response.usage.cached_tokens == 2

    @pytest.mark.parametrize(
        "kwargs,match",
        [
            ({"thinking_budget": 100}, "thinking_budget"),
            ({"reasoning_effort": "minimal"}, "low.*medium.*high"),
        ],
    )
    def test_unsupported_reasoning_parameters_fail_before_network(self, kwargs, match):
        llm = GeminiLLM(api_key="test-key", model=MODEL)
        llm.client.chat.completions.create = Mock()

        with pytest.raises(ValueError, match=match):
            llm.complete([{"role": "user", "content": "hello"}], **kwargs)

        llm.client.chat.completions.create.assert_not_called()

    def test_missing_google_key_does_not_fall_back_to_openai(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        with pytest.raises(ValueError, match="Gemini API key required"):
            create_llm(MODEL)


class TestGemini38StructuredOutput:

    def test_uses_the_same_parameter_compatibility_rules(self):
        class Answer(SimpleNamespace):
            pass

        parsed = Answer(value=4)
        llm = GeminiLLM(api_key="test-key", model=MODEL)
        llm.client.beta.chat.completions.parse = Mock(return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))]
        ))

        result = llm.structured_complete(
            [{"role": "user", "content": "2+2"}],
            Answer,
            reasoning_effort="low",
            top_k=20,
            stream=True,
        )

        sent = llm.client.beta.chat.completions.parse.call_args.kwargs
        assert sent["model"] == MODEL
        assert sent["reasoning_effort"] == "low"
        assert {"top_k", "stream"}.isdisjoint(sent)
        assert result is parsed
