"""
LLM-Note: Tests for GroqLLM provider

What it tests:
- GroqLLM initialization and API key handling
- complete() method with text and tool call responses
- complete() API error handling (prevents system hangs)
- structured_complete() using JSON mode
- Model prefix stripping

Components under test:
- Module: connectonion.core.llm.GroqLLM
"""
import json
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from pydantic import BaseModel

import openai

from connectonion.core.llm import GroqLLM, LLMResponse, ToolCall, create_llm


class OutputSchema(BaseModel):
    """Test schema for structured output (avoid pytest collection by not naming TestXxx)."""
    answer: str
    score: int


class TestGroqLLMInit:
    """Test GroqLLM initialization."""

    def test_init_with_api_key_param(self):
        """GroqLLM accepts API key via parameter."""
        with patch.dict(os.environ, {}, clear=True):
            llm = GroqLLM(api_key="test-key", model="groq/llama-3.3-70b-versatile")
            assert llm.api_key == "test-key"

    def test_init_reads_env_var(self):
        """GroqLLM reads GROQ_API_KEY from environment."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "env-key"}):
            llm = GroqLLM(model="groq/llama-3.3-70b-versatile")
            assert llm.api_key == "env-key"

    def test_init_strips_groq_prefix(self):
        """GroqLLM strips the groq/ prefix from model name."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            llm = GroqLLM(model="groq/llama-3.3-70b-versatile")
            assert llm.model == "llama-3.3-70b-versatile"

    def test_init_missing_api_key_raises(self):
        """GroqLLM raises ValueError when no API key is available."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                GroqLLM(model="groq/llama-3.3-70b-versatile")
            assert "GROQ_API_KEY" in str(exc_info.value)

    def test_init_uses_groq_base_url(self):
        """GroqLLM configures the OpenAI client with Groq's base URL."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            llm = GroqLLM(model="groq/llama-3.3-70b-versatile")
            assert "groq.com" in str(llm.client.base_url)


class TestGroqLLMComplete:
    """Test GroqLLM.complete() method."""

    def _make_llm(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            return GroqLLM(model="groq/llama-3.3-70b-versatile")

    def test_complete_returns_text_response(self):
        """complete() returns LLMResponse with content for plain text replies."""
        llm = self._make_llm()

        mock_message = Mock()
        mock_message.content = "Hello from Groq!"
        mock_message.tool_calls = None

        mock_response = Mock()
        mock_response.choices = [Mock(message=mock_message)]
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5

        llm.client.chat.completions.create = Mock(return_value=mock_response)

        result = llm.complete([{"role": "user", "content": "Hi"}])

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello from Groq!"
        assert result.tool_calls == []

    def test_complete_returns_tool_calls(self):
        """complete() parses tool calls from the response."""
        llm = self._make_llm()

        mock_tool_call = Mock()
        mock_tool_call.id = "call_abc123"
        mock_tool_call.function.name = "search"
        mock_tool_call.function.arguments = '{"query": "python"}'

        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]

        mock_response = Mock()
        mock_response.choices = [Mock(message=mock_message)]
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 10

        llm.client.chat.completions.create = Mock(return_value=mock_response)

        tools = [{"name": "search", "description": "Search", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}]
        result = llm.complete([{"role": "user", "content": "Search Python"}], tools=tools)

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "search"
        assert result.tool_calls[0].arguments == {"query": "python"}
        assert result.tool_calls[0].id == "call_abc123"

    def test_complete_passes_tools_in_openai_format(self):
        """complete() wraps tools in OpenAI function format when sending to API."""
        llm = self._make_llm()

        mock_message = Mock()
        mock_message.content = "Done"
        mock_message.tool_calls = None

        mock_response = Mock()
        mock_response.choices = [Mock(message=mock_message)]
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 3

        llm.client.chat.completions.create = Mock(return_value=mock_response)

        tools = [{"name": "list_files", "description": "List files", "parameters": {"type": "object", "properties": {}}}]
        llm.complete([{"role": "user", "content": "List files"}], tools=tools)

        call_kwargs = llm.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["tools"] == [{"type": "function", "function": tools[0]}]
        assert call_kwargs["tool_choice"] == "auto"

    def test_complete_includes_usage(self):
        """complete() captures token usage from the response."""
        llm = self._make_llm()

        mock_message = Mock()
        mock_message.content = "Answer"
        mock_message.tool_calls = None

        mock_usage = Mock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50

        mock_response = Mock()
        mock_response.choices = [Mock(message=mock_message)]
        mock_response.usage = mock_usage

        llm.client.chat.completions.create = Mock(return_value=mock_response)

        result = llm.complete([{"role": "user", "content": "test"}])

        assert result.usage is not None
        assert result.usage.input_tokens == 100
        assert result.usage.output_tokens == 50

    def test_complete_api_error_raises_value_error(self):
        """complete() converts openai.APIError into ValueError with context."""
        llm = self._make_llm()

        mock_request = Mock()
        mock_request.method = "POST"
        mock_request.url = "https://api.groq.com/openai/v1/chat/completions"
        mock_request.headers = {}

        api_error = openai.APIStatusError(
            "rate_limit_exceeded",
            response=Mock(status_code=429),
            body={"error": {"message": "Rate limit exceeded"}}
        )

        llm.client.chat.completions.create = Mock(side_effect=api_error)

        with pytest.raises(ValueError) as exc_info:
            llm.complete([{"role": "user", "content": "test"}])

        assert "Groq API Error" in str(exc_info.value)

    def test_complete_parses_dict_tool_arguments(self):
        """complete() handles tool arguments that are already dicts (not JSON strings)."""
        llm = self._make_llm()

        mock_tool_call = Mock()
        mock_tool_call.id = "call_xyz"
        mock_tool_call.function.name = "calculator"
        mock_tool_call.function.arguments = {"a": 1, "b": 2}  # Already a dict

        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]

        mock_response = Mock()
        mock_response.choices = [Mock(message=mock_message)]
        mock_response.usage.prompt_tokens = 15
        mock_response.usage.completion_tokens = 8

        llm.client.chat.completions.create = Mock(return_value=mock_response)

        result = llm.complete([{"role": "user", "content": "Calculate"}])

        assert result.tool_calls[0].arguments == {"a": 1, "b": 2}


class TestGroqLLMStructuredComplete:
    """Test GroqLLM.structured_complete() method."""

    def _make_llm(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            return GroqLLM(model="groq/llama-3.3-70b-versatile")

    def test_structured_complete_returns_pydantic_model(self):
        """structured_complete() returns a validated Pydantic model instance."""
        llm = self._make_llm()

        mock_message = Mock()
        mock_message.content = '{"answer": "Paris", "score": 10}'

        mock_response = Mock()
        mock_response.choices = [Mock(message=mock_message)]

        llm.client.chat.completions.create = Mock(return_value=mock_response)

        result = llm.structured_complete(
            [{"role": "user", "content": "What is the capital of France?"}],
            OutputSchema
        )

        assert isinstance(result, OutputSchema)
        assert result.answer == "Paris"
        assert result.score == 10

    def test_structured_complete_uses_json_mode(self):
        """structured_complete() uses JSON response format (not beta parse endpoint)."""
        llm = self._make_llm()

        mock_message = Mock()
        mock_message.content = '{"answer": "test", "score": 1}'

        mock_response = Mock()
        mock_response.choices = [Mock(message=mock_message)]

        llm.client.chat.completions.create = Mock(return_value=mock_response)

        llm.structured_complete([{"role": "user", "content": "test"}], OutputSchema)

        call_kwargs = llm.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_structured_complete_prepends_schema_instruction(self):
        """structured_complete() adds schema instruction as system message."""
        llm = self._make_llm()

        mock_message = Mock()
        mock_message.content = '{"answer": "x", "score": 0}'

        mock_response = Mock()
        mock_response.choices = [Mock(message=mock_message)]

        llm.client.chat.completions.create = Mock(return_value=mock_response)

        llm.structured_complete([{"role": "user", "content": "test"}], OutputSchema)

        call_kwargs = llm.client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        # First message should be the schema instruction
        assert messages[0]["role"] == "system"
        assert "JSON Schema" in messages[0]["content"]

    def test_structured_complete_empty_content_uses_empty_json(self):
        """structured_complete() handles empty content by using empty JSON object."""
        llm = self._make_llm()

        mock_message = Mock()
        mock_message.content = None  # Empty response

        mock_response = Mock()
        mock_response.choices = [Mock(message=mock_message)]

        llm.client.chat.completions.create = Mock(return_value=mock_response)

        # Should raise validation error (empty JSON doesn't match schema)
        with pytest.raises(Exception):
            llm.structured_complete([{"role": "user", "content": "test"}], OutputSchema)


class TestGroqLLMCreateFactory:
    """Test that create_llm() correctly routes to GroqLLM."""

    def test_create_llm_groq_prefix_returns_groq_llm(self):
        """create_llm() with groq/ prefix returns GroqLLM instance."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            llm = create_llm("groq/llama-3.3-70b-versatile")
            assert isinstance(llm, GroqLLM)

    def test_create_llm_passes_api_key(self):
        """create_llm() passes api_key to GroqLLM."""
        with patch.dict(os.environ, {}, clear=True):
            llm = create_llm("groq/llama-3.3-70b-versatile", api_key="direct-key")
            assert isinstance(llm, GroqLLM)
            assert llm.api_key == "direct-key"

    def test_create_llm_strips_prefix_from_model(self):
        """create_llm() with groq/ prefix strips it before storing model name."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            llm = create_llm("groq/llama-3.1-8b-instant")
            assert llm.model == "llama-3.1-8b-instant"
