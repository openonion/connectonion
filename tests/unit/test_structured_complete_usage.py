"""structured_complete() must record usage the same way complete() does.

#730: a structured call spent money and discarded completion.usage, so
session/eval accounting saw $0. Option 2 keeps the BaseModel return type and
stores TokenUsage on llm.last_usage.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from connectonion.core.llm import OpenOnionLLM


class Answer(BaseModel):
    value: int


def test_structured_complete_records_server_usage_and_cost():
    with patch.dict(os.environ, {"OPENONION_API_KEY": "mock-jwt-token"}, clear=True):
        llm = OpenOnionLLM(model="co/gemini-3.6-flash")

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.parsed = Answer(value=391)
        mock_completion.usage.prompt_tokens = 17
        mock_completion.usage.completion_tokens = 3
        mock_completion.usage.prompt_tokens_details = None
        # Server-billed total exceeds the OpenAI-shaped sum (reasoning tokens).
        mock_completion.usage.total_tokens = 243
        mock_completion.usage.cost_usd = 0.0007

        with patch.object(
            llm.client.beta.chat.completions, "parse", return_value=mock_completion
        ):
            result = llm.structured_complete(
                [{"role": "user", "content": "pick a number"}], Answer
            )

        assert result == Answer(value=391)
        assert llm.last_usage is not None
        assert llm.last_usage.input_tokens == 17
        assert llm.last_usage.output_tokens == 3
        assert llm.last_usage.total_tokens == 243
        assert llm.last_usage.cost == pytest.approx(0.0007)


def test_structured_complete_last_usage_matches_complete_path():
    """Same usage object shape whether the call was complete or structured."""
    with patch.dict(os.environ, {"OPENONION_API_KEY": "mock-jwt-token"}, clear=True):
        llm = OpenOnionLLM(model="co/o4-mini")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "hi"
        mock_response.choices[0].message.tool_calls = None
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.prompt_tokens_details = None
        mock_response.usage.total_tokens = 30
        mock_response.usage.cost_usd = 0.0012

        with patch.object(
            llm.client.chat.completions, "create", return_value=mock_response
        ):
            resp = llm.complete([{"role": "user", "content": "hi"}])

        assert resp.usage is not None
        assert llm.last_usage is resp.usage
        assert llm.last_usage.cost == pytest.approx(0.0012)
