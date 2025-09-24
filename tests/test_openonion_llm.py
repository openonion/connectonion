#!/usr/bin/env python3
"""Test OpenOnion LLM implementation with co/ models."""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectonion.llm import OpenOnionLLM, create_llm


class TestOpenOnionLLM:
    """Test OpenOnion LLM implementation."""

    def test_initialization_production(self):
        """Test OpenOnionLLM initializes with production URL."""
        with patch.object(OpenOnionLLM, '_get_auth_token', return_value='mock-jwt-token'):
            with patch.dict(os.environ, {}, clear=True):
                llm = OpenOnionLLM(model="co/gpt-4o")

                assert hasattr(llm, 'client'), "Should have OpenAI client"
                assert llm.client.base_url == "https://oo.openonion.ai/v1/"
                assert llm.client.api_key == "mock-jwt-token"
                assert llm.model == "co/gpt-4o"

    def test_initialization_development(self):
        """Test OpenOnionLLM initializes with development URL."""
        with patch.object(OpenOnionLLM, '_get_auth_token', return_value='mock-jwt-token'):
            with patch.dict(os.environ, {'OPENONION_DEV': '1'}):
                llm = OpenOnionLLM(model="co/o4-mini")

                assert llm.client.base_url == "http://localhost:8000/v1/"
                assert llm.model == "co/o4-mini"

    def test_complete_gpt4o(self):
        """Test complete method with co/gpt-4o model."""
        with patch.object(OpenOnionLLM, '_get_auth_token', return_value='mock-jwt-token'):
            # Create mock response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test response"
            mock_response.choices[0].message.tool_calls = None

            llm = OpenOnionLLM(model="co/gpt-4o")

            with patch.object(llm.client.chat.completions, 'create', return_value=mock_response) as mock_create:
                result = llm.complete([{"role": "user", "content": "test"}])

                # Check call parameters
                call_kwargs = mock_create.call_args[1]
                assert call_kwargs['model'] == "co/gpt-4o"
                assert call_kwargs['max_tokens'] == 16384
                assert 'max_completion_tokens' not in call_kwargs

                # Check response
                assert result.content == "Test response"
                assert result.tool_calls == []

    def test_complete_o4mini(self):
        """Test complete method with co/o4-mini model."""
        with patch.object(OpenOnionLLM, '_get_auth_token', return_value='mock-jwt-token'):
            # Create mock response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test reasoning response"
            mock_response.choices[0].message.tool_calls = None

            llm = OpenOnionLLM(model="co/o4-mini")

            with patch.object(llm.client.chat.completions, 'create', return_value=mock_response) as mock_create:
                result = llm.complete([{"role": "user", "content": "test reasoning"}])

                # Check call parameters for o4-mini
                call_kwargs = mock_create.call_args[1]
                assert call_kwargs['model'] == "co/o4-mini"
                assert call_kwargs['max_completion_tokens'] == 16384
                assert call_kwargs['temperature'] == 1
                assert 'max_tokens' not in call_kwargs

                # Check response
                assert result.content == "Test reasoning response"

    def test_complete_with_tools(self):
        """Test complete method with tools."""
        with patch.object(OpenOnionLLM, '_get_auth_token', return_value='mock-jwt-token'):
            # Create mock response with tool call
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = None

            # Mock tool call
            mock_tool_call = MagicMock()
            mock_tool_call.function.name = "test_tool"
            mock_tool_call.function.arguments = '{"arg": "value"}'
            mock_tool_call.id = "call_123"
            mock_response.choices[0].message.tool_calls = [mock_tool_call]

            llm = OpenOnionLLM(model="co/gpt-4o")

            tools = [{
                "name": "test_tool",
                "description": "Test tool",
                "parameters": {
                    "type": "object",
                    "properties": {"arg": {"type": "string"}}
                }
            }]

            with patch.object(llm.client.chat.completions, 'create', return_value=mock_response) as mock_create:
                result = llm.complete([{"role": "user", "content": "use tool"}], tools=tools)

                # Check that tools were passed correctly
                call_kwargs = mock_create.call_args[1]
                assert 'tools' in call_kwargs
                assert call_kwargs['tool_choice'] == 'auto'

                # Check tool call in response
                assert len(result.tool_calls) == 1
                assert result.tool_calls[0].name == "test_tool"
                assert result.tool_calls[0].arguments == {"arg": "value"}
                assert result.tool_calls[0].id == "call_123"

    def test_create_llm_co_models(self):
        """Test create_llm function with co/ models."""
        with patch.object(OpenOnionLLM, '_get_auth_token', return_value='mock-jwt-token'):
            # Test various co/ models
            models = ["co/gpt-4o", "co/o4-mini", "co/claude-3-haiku", "co/gemini-1.5-pro"]

            for model in models:
                llm = create_llm(model)
                assert isinstance(llm, OpenOnionLLM)
                assert llm.model == model

    def test_no_auth_token_error(self):
        """Test error when no auth token is found."""
        with patch.object(OpenOnionLLM, '_get_auth_token', return_value=None):
            with pytest.raises(ValueError) as exc_info:
                OpenOnionLLM(model="co/gpt-4o")

            assert "No authentication token found" in str(exc_info.value)
            assert "Run 'co auth'" in str(exc_info.value)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])