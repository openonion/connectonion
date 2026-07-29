"""Unit tests for Anthropic request conversion."""

from types import SimpleNamespace
from unittest.mock import Mock

from pydantic import BaseModel

from connectonion.core.llm import AnthropicLLM


class Answer(BaseModel):
    value: str


def make_llm(response):
    llm = AnthropicLLM(api_key="test-key")
    llm.client.messages.create = Mock(return_value=response)
    return llm


def test_complete_passes_combined_system_prompt():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    llm = make_llm(response)

    llm.complete(
        [
            {"role": "system", "content": "Follow the rules."},
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
        ]
    )

    request = llm.client.messages.create.call_args.kwargs
    assert request["system"] == "Follow the rules.\n\nBe concise."
    assert request["messages"] == [{"role": "user", "content": "Hello"}]


def test_complete_omits_system_parameter_when_absent():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    llm = make_llm(response)

    llm.complete([{"role": "user", "content": "Hello"}])

    assert "system" not in llm.client.messages.create.call_args.kwargs


def test_structured_complete_passes_system_prompt():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name="return_structured_output",
                input={"value": "ok"},
            )
        ]
    )
    llm = make_llm(response)

    result = llm.structured_complete(
        [
            {"role": "system", "content": "Return a short answer."},
            {"role": "user", "content": "Hello"},
        ],
        Answer,
    )

    assert result == Answer(value="ok")
    request = llm.client.messages.create.call_args.kwargs
    assert request["system"] == "Return a short answer."
    assert request["messages"] == [{"role": "user", "content": "Hello"}]
