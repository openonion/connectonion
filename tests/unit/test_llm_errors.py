#!/usr/bin/env python3
"""
Unit tests for llm.py error handling.

Tests cover:
- Missing API key errors (all providers)
- Unknown model errors
- Structured output incomplete/refusal scenarios
- JSON parsing errors in tool calls
- Provider-specific error bubbling
- Model registry lookup failures

Critical error paths from coverage analysis:
- Missing API keys (lines 204-205, 276-277, 487-488, 597-601)
- Unknown models in create_llm (line 747)
- Structured output edge cases (lines 255-265, 702-712, 356)
- JSON parsing in tool arguments (lines 231, 385, 518, 682)
"""

import pytest
import os
from unittest.mock import Mock, MagicMock, patch
from pydantic import BaseModel
from connectonion.core.llm import (
    create_llm,
    OpenAILLM,
    AnthropicLLM,
    GeminiLLM,
    GroqLLM,
    GrokLLM,
    OpenRouterLLM,
    OpenOnionLLM,
    LLMResponse,
    ToolCall
)


class StructuredOutputSchema(BaseModel):
    """Test Pydantic model for structured output (renamed to avoid pytest collection)."""
    value: int
    message: str


class TestMissingAPIKeys:
    """Test error handling when API keys are missing."""

    def test_openai_missing_api_key_env(self):
        """Test OpenAI raises ValueError when API key missing from environment."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                OpenAILLM(model="gpt-4o-mini")

            assert "OpenAI API key required" in str(exc_info.value)
            assert "OPENAI_API_KEY" in str(exc_info.value)

    def test_openai_missing_api_key_explicit(self):
        """Test OpenAI raises ValueError when api_key parameter is None."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                OpenAILLM(api_key=None, model="gpt-4o-mini")

            assert "OpenAI API key required" in str(exc_info.value)

    def test_anthropic_missing_api_key_env(self):
        """Test Anthropic raises ValueError when API key missing from environment."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                AnthropicLLM(model="claude-3-5-sonnet-20241022")

            assert "Anthropic API key required" in str(exc_info.value)
            assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_gemini_missing_api_key_env(self):
        """Test Gemini raises ValueError when API key missing from environment."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                GeminiLLM(model="gemini-2.0-flash-exp")

            assert "Gemini API key required" in str(exc_info.value)
            assert "GEMINI_API_KEY" in str(exc_info.value)


    def test_groq_missing_api_key_env(self):
        """Test Groq raises ValueError when API key missing from environment."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                GroqLLM(model="groq/llama-3.3-70b-versatile")

            assert "Groq API key required" in str(exc_info.value)
            assert "GROQ_API_KEY" in str(exc_info.value)

    def test_openrouter_missing_api_key_env(self):
        """Test OpenRouter raises ValueError when API key missing from environment."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                OpenRouterLLM(model="openrouter/openai/gpt-4o-mini")

            assert "OpenRouter API key required" in str(exc_info.value)
            assert "OPENROUTER_API_KEY" in str(exc_info.value)

    def test_grok_missing_api_key_env(self):
        """Test Grok raises ValueError when API key missing from environment."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                GrokLLM(model="grok/grok-4")

            assert "Grok API key required" in str(exc_info.value)
            assert "XAI_API_KEY" in str(exc_info.value)

    def test_openonion_missing_api_key_helpful_message(self):
        """Test OpenOnion raises ValueError with helpful message about co init."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                OpenOnionLLM(model="co/gpt-4o")

            error_msg = str(exc_info.value)
            assert "OPENONION_API_KEY not found" in error_msg
            assert "co init" in error_msg


class TestUnknownModels:
    """Test error handling for unknown/unsupported models."""

    def test_unknown_model_in_create_llm(self):
        """Test create_llm raises ValueError for completely unknown model."""
        with pytest.raises(ValueError) as exc_info:
            create_llm("unknown-model-xyz-123")

        assert "Unknown model" in str(exc_info.value)
        assert "unknown-model-xyz-123" in str(exc_info.value)

    def test_unknown_provider_in_create_llm(self):
        """Test create_llm raises ValueError when provider not implemented."""
        # Test that unknown models raise appropriate error
        # Note: The error message depends on whether the model matches known prefixes
        with pytest.raises(ValueError) as exc_info:
            create_llm("totally-unknown-model-xyz")

        # Should get "Unknown model" error since no prefix matches
        assert "Unknown model" in str(exc_info.value) or "not implemented" in str(exc_info.value)


class TestStructuredOutputErrors:
    """Test error handling in structured output generation."""

    def test_openai_structured_max_tokens_exceeded(self):
        """Test handling when OpenAI structured response exceeds max tokens."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = OpenAILLM(model="gpt-4o-mini")

            # Mock incomplete response due to max tokens
            mock_response = Mock()
            mock_response.status = "incomplete"
            mock_response.incomplete_details.reason = "max_output_tokens"

            llm.client.responses.parse = Mock(return_value=mock_response)

            with pytest.raises(ValueError) as exc_info:
                llm.structured_complete([{"role": "user", "content": "test"}], StructuredOutputSchema)

            assert "maximum output tokens" in str(exc_info.value)

    def test_openai_structured_content_filter(self):
        """Test handling when OpenAI filters content in structured response."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = OpenAILLM(model="gpt-4o-mini")

            # Mock incomplete response due to content filter
            mock_response = Mock()
            mock_response.status = "incomplete"
            mock_response.incomplete_details.reason = "content_filter"

            llm.client.responses.parse = Mock(return_value=mock_response)

            with pytest.raises(ValueError) as exc_info:
                llm.structured_complete([{"role": "user", "content": "test"}], StructuredOutputSchema)

            assert "content filtered" in str(exc_info.value)

    def test_openai_structured_refusal(self):
        """Test handling when OpenAI model refuses to generate structured output."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = OpenAILLM(model="gpt-4o-mini")

            # Mock refusal response
            mock_content = Mock()
            mock_content.type = "refusal"
            mock_content.refusal = "I cannot comply with this request"

            mock_output = Mock()
            mock_output.content = [mock_content]

            mock_response = Mock()
            mock_response.status = "complete"
            mock_response.output = [mock_output]

            llm.client.responses.parse = Mock(return_value=mock_response)

            with pytest.raises(ValueError) as exc_info:
                llm.structured_complete([{"role": "user", "content": "test"}], StructuredOutputSchema)

            assert "refused to respond" in str(exc_info.value)
            assert "cannot comply" in str(exc_info.value)

    def test_anthropic_structured_no_output(self):
        """Test Anthropic structured_complete raises error when no tool output received."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            llm = AnthropicLLM(model="claude-3-5-sonnet-20241022")

            # Mock response with no tool_use blocks
            mock_content_block = Mock()
            mock_content_block.type = "text"
            mock_content_block.text = "I don't want to use the tool"

            mock_response = Mock()
            mock_response.content = [mock_content_block]

            llm.client.messages.create = Mock(return_value=mock_response)

            with pytest.raises(ValueError) as exc_info:
                llm.structured_complete([{"role": "user", "content": "test"}], StructuredOutputSchema)

            assert "No structured output received" in str(exc_info.value)


class TestJSONParsingErrors:
    """Test handling of JSON parsing errors in tool calls."""

    def test_openai_malformed_tool_arguments(self):
        """Test handling when OpenAI returns malformed JSON in tool arguments."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = OpenAILLM(model="gpt-4o-mini")

            # Mock response with malformed JSON
            mock_tool_call = Mock()
            mock_tool_call.id = "call_123"
            mock_tool_call.function.name = "test_tool"
            mock_tool_call.function.arguments = "{invalid json"  # Malformed!

            mock_message = Mock()
            mock_message.content = None
            mock_message.tool_calls = [mock_tool_call]

            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message = mock_message

            llm.client.chat.completions.create = Mock(return_value=mock_response)

            # Should raise JSONDecodeError
            import json
            with pytest.raises(json.JSONDecodeError):
                llm.complete([{"role": "user", "content": "test"}], tools=[{
                    "name": "test_tool",
                    "description": "Test",
                    "parameters": {"type": "object", "properties": {}}
                }])

    def test_gemini_malformed_tool_arguments(self):
        """Test handling when Gemini returns malformed JSON in tool arguments."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            llm = GeminiLLM(model="gemini-2.0-flash-exp")

            # Mock response with malformed JSON
            mock_tool_call = Mock()
            mock_tool_call.id = "call_456"
            mock_tool_call.function.name = "search"
            mock_tool_call.function.arguments = '{"query": unclosed string'  # Malformed!

            mock_message = Mock()
            mock_message.content = None
            mock_message.tool_calls = [mock_tool_call]

            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message = mock_message

            llm.client.chat.completions.create = Mock(return_value=mock_response)

            # Should raise JSONDecodeError
            import json
            with pytest.raises(json.JSONDecodeError):
                llm.complete([{"role": "user", "content": "test"}], tools=[{
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}
                }])


class TestProviderErrorBubbling:
    """Test that provider-specific errors bubble up correctly."""

    def test_openai_api_error_bubbles_up(self):
        """Test that OpenAI API errors are not caught and bubble up."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = OpenAILLM(model="gpt-4o-mini")

            # Mock generic Exception (provider errors bubble up as-is)
            llm.client.chat.completions.create = Mock(
                side_effect=Exception("Rate limit exceeded")
            )

            # Should bubble up, not be caught
            with pytest.raises(Exception) as exc_info:
                llm.complete([{"role": "user", "content": "test"}])

            assert "Rate limit exceeded" in str(exc_info.value)

    def test_anthropic_api_error_bubbles_up(self):
        """Test that Anthropic API errors are not caught and bubble up."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            llm = AnthropicLLM(model="claude-3-5-sonnet-20241022")

            # Mock generic Exception (provider errors bubble up as-is)
            llm.client.messages.create = Mock(
                side_effect=Exception("Overloaded")
            )

            # Should bubble up, not be caught
            with pytest.raises(Exception):
                llm.complete([{"role": "user", "content": "test"}])


class TestOpenAICompatibleProviders:
    """Test Groq/OpenRouter OpenAI-compatible behavior."""

    def test_openrouter_default_headers_from_env(self):
        """OpenRouter should pass optional attribution headers when configured."""
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_HTTP_REFERER": "https://example.com",
            "OPENROUTER_X_TITLE": "My App",
        }):
            with patch("connectonion.core.llm.openai.OpenAI") as mock_openai:
                OpenRouterLLM(model="openrouter/openai/gpt-4o-mini")

                _, kwargs = mock_openai.call_args
                assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
                assert kwargs["default_headers"]["HTTP-Referer"] == "https://example.com"
                assert kwargs["default_headers"]["X-Title"] == "My App"

    def test_groq_structured_complete_json_mode(self):
        """Groq structured output should use JSON mode and validate with Pydantic."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            llm = GroqLLM(model="groq/llama-3.3-70b-versatile")

            mock_message = Mock()
            mock_message.content = '{"value": 7, "message": "ok"}'
            mock_response = Mock()
            mock_response.choices = [Mock(message=mock_message)]
            llm.client.chat.completions.create = Mock(return_value=mock_response)

            result = llm.structured_complete(
                [{"role": "user", "content": "Return test payload"}],
                StructuredOutputSchema
            )

            assert result.value == 7
            assert result.message == "ok"
            llm.client.chat.completions.create.assert_called_once()
            called = llm.client.chat.completions.create.call_args.kwargs
            assert called["response_format"] == {"type": "json_object"}

    def test_grok_structured_complete_json_mode(self):
        """Grok structured output should use JSON mode and validate with Pydantic."""
        with patch.dict(os.environ, {"XAI_API_KEY": "test-key"}):
            llm = GrokLLM(model="grok/grok-4")

            mock_message = Mock()
            mock_message.content = '{"value": 11, "message": "xai"}'
            mock_response = Mock()
            mock_response.choices = [Mock(message=mock_message)]
            llm.client.chat.completions.create = Mock(return_value=mock_response)

            result = llm.structured_complete(
                [{"role": "user", "content": "Return test payload"}],
                StructuredOutputSchema
            )

            assert result.value == 11
            assert result.message == "xai"
            llm.client.chat.completions.create.assert_called_once()
            called = llm.client.chat.completions.create.call_args.kwargs
            assert called["response_format"] == {"type": "json_object"}

    def test_openrouter_structured_complete_json_mode(self):
        """OpenRouter structured output should use JSON mode and validate with Pydantic."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            llm = OpenRouterLLM(model="openrouter/openai/gpt-4o-mini")

            mock_message = Mock()
            mock_message.content = '{"value": 9, "message": "great"}'
            mock_response = Mock()
            mock_response.choices = [Mock(message=mock_message)]
            llm.client.chat.completions.create = Mock(return_value=mock_response)

            result = llm.structured_complete(
                [{"role": "user", "content": "Return test payload"}],
                StructuredOutputSchema
            )

            assert result.value == 9
            assert result.message == "great"
            llm.client.chat.completions.create.assert_called_once()
            called = llm.client.chat.completions.create.call_args.kwargs
            assert called["response_format"] == {"type": "json_object"}


class TestModelInference:
    """Test model provider inference from model names."""


    def test_infer_groq_from_prefix(self):
        """Test that groq/* models are routed to GroqLLM."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            llm = create_llm("groq/llama-3.3-70b-versatile")
            assert isinstance(llm, GroqLLM)

    def test_infer_openrouter_from_prefix(self):
        """Test that openrouter/* models are routed to OpenRouterLLM."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            llm = create_llm("openrouter/openai/gpt-4o-mini")
            assert isinstance(llm, OpenRouterLLM)
    def test_infer_grok_from_prefix(self):
        """Test that grok/* models are routed to GrokLLM."""
        with patch.dict(os.environ, {"XAI_API_KEY": "test-key"}):
            llm = create_llm("grok/grok-4")
            assert isinstance(llm, GrokLLM)

    def test_infer_openai_from_gpt_prefix(self):
        """Test that gpt-* models are inferred as OpenAI."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = create_llm("gpt-unknown-model")
            assert isinstance(llm, OpenAILLM)

    def test_infer_openai_from_o_prefix(self):
        """Test that o* models are inferred as OpenAI."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = create_llm("o99-preview")
            assert isinstance(llm, OpenAILLM)

    def test_infer_anthropic_from_claude_prefix(self):
        """Test that claude-* models are inferred as Anthropic."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            llm = create_llm("claude-unknown-version")
            assert isinstance(llm, AnthropicLLM)

    def test_infer_gemini_from_gemini_prefix(self):
        """Test that gemini-* models are inferred as Google."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            llm = create_llm("gemini-unknown-version")
            assert isinstance(llm, GeminiLLM)


class TestOpenOnionAuthentication:
    """Test OpenOnion authentication and token retrieval."""

    def test_openonion_uses_env_variable_first(self):
        """Test that OPENONION_API_KEY from environment is used first."""
        with patch.dict(os.environ, {"OPENONION_API_KEY": "env-token"}):
            with patch('builtins.print'):  # Suppress warning message
                llm = OpenOnionLLM(model="co/gpt-4o")
                assert llm.auth_token == "env-token"

    def test_openonion_strips_co_prefix(self):
        """Test that co/ prefix is stripped from model name."""
        with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}):
            with patch('builtins.print'):  # Suppress warning
                llm = OpenOnionLLM(model="co/gpt-4o-mini")
                assert llm.model == "gpt-4o-mini"  # Prefix stripped

    def test_openonion_dev_mode_uses_localhost(self):
        """Test that OPENONION_DEV env var uses localhost."""
        with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token", "OPENONION_DEV": "1"}):
            with patch('builtins.print'):  # Suppress warning
                llm = OpenOnionLLM(model="co/gpt-4o")
                assert "localhost" in str(llm.client.base_url)

    def test_openonion_production_uses_oo_url(self):
        """Test that production mode uses oo.openonion.ai."""
        with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}, clear=True):
            with patch('builtins.print'):  # Suppress warning
                llm = OpenOnionLLM(model="co/gpt-4o")
                assert "oo.openonion.ai" in str(llm.client.base_url)


class TestAPIKeyFromParameter:
    """Test that API keys can be passed as parameters."""

    def test_openai_api_key_from_parameter(self):
        """Test OpenAI accepts API key via parameter."""
        with patch.dict(os.environ, {}, clear=True):
            llm = OpenAILLM(api_key="param-key", model="gpt-4o-mini")
            assert llm.api_key == "param-key"

    def test_anthropic_api_key_from_parameter(self):
        """Test Anthropic accepts API key via parameter."""
        with patch.dict(os.environ, {}, clear=True):
            llm = AnthropicLLM(api_key="param-key", model="claude-3-5-sonnet-20241022")
            assert llm.api_key == "param-key"

    def test_gemini_api_key_from_parameter(self):
        """Test Gemini accepts API key via parameter."""
        with patch.dict(os.environ, {}, clear=True):
            llm = GeminiLLM(api_key="param-key", model="gemini-2.0-flash-exp")
            assert llm.api_key == "param-key"

    def test_create_llm_passes_api_key_to_provider(self):
        """Test that create_llm passes api_key parameter to provider."""
        with patch.dict(os.environ, {}, clear=True):
            llm = create_llm("gpt-4o-mini", api_key="test-key")
            assert isinstance(llm, OpenAILLM)
            assert llm.api_key == "test-key"


class TestCoModelRouting:
    """Test that co/ prefixed models route to OpenOnion."""

    def test_co_prefix_routes_to_openonion(self):
        """Test that co/* models are routed to OpenOnionLLM."""
        with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}):
            with patch('builtins.print'):  # Suppress warning
                llm = create_llm("co/gpt-4o")
                assert isinstance(llm, OpenOnionLLM)

    def test_co_prefix_with_various_models(self):
        """Test that various co/* models all route to OpenOnion."""
        models = ["co/gpt-4o", "co/claude-3-5-sonnet", "co/gemini-2.0-flash-exp", "co/o4-mini"]

        with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}):
            with patch('builtins.print'):  # Suppress warning
                for model in models:
                    llm = create_llm(model)
                    assert isinstance(llm, OpenOnionLLM)
                    assert not llm.model.startswith("co/")  # Prefix should be stripped


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
