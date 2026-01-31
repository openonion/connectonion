#!/usr/bin/env python3
"""Test OpenOnion LLM implementation with co/ models."""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectonion.core.llm import OpenOnionLLM, create_llm


class TestOpenOnionLLM:
    """Test OpenOnion LLM implementation."""

    def test_initialization_production(self):
        """Test OpenOnionLLM initializes with production URL."""
        with patch.dict(os.environ, {'OPENONION_API_KEY': 'mock-jwt-token'}, clear=True):
            llm = OpenOnionLLM(model="co/gpt-4o")

            assert hasattr(llm, 'client'), "Should have OpenAI client"
            assert llm.client.base_url == "https://oo.openonion.ai/v1/"
            assert llm.client.api_key == "mock-jwt-token"
            assert llm.auth_token == "mock-jwt-token"
            assert llm.model == "gpt-4o"  # co/ prefix stripped by implementation

    def test_initialization_development(self):
        """Test OpenOnionLLM initializes with development URL."""
        with patch.dict(os.environ, {'OPENONION_DEV': '1', 'OPENONION_API_KEY': 'mock-jwt-token'}):
            llm = OpenOnionLLM(model="co/o4-mini")

            assert llm.client.base_url == "http://localhost:8000/v1/"
            assert llm.model == "o4-mini"  # co/ prefix stripped

    def test_complete_gpt4o(self):
        """Test complete method with co/gpt-4o model."""
        with patch.dict(os.environ, {'OPENONION_API_KEY': 'mock-jwt-token'}, clear=True):
            # Create mock response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test response"
            mock_response.choices[0].message.tool_calls = None
            # Mock usage data for cost calculation
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 20
            mock_response.usage.prompt_tokens_details = None

            llm = OpenOnionLLM(model="co/gpt-4o")

            with patch.object(llm.client.chat.completions, 'create', return_value=mock_response) as mock_create:
                result = llm.complete([{"role": "user", "content": "test"}])

                # Check call parameters
                call_kwargs = mock_create.call_args[1]
                assert call_kwargs['model'] == "gpt-4o"  # Sent to server without prefix

                # Check response
                assert result.content == "Test response"
                assert result.tool_calls == []

    def test_complete_o4mini(self):
        """Test complete method with co/o4-mini model."""
        with patch.dict(os.environ, {'OPENONION_API_KEY': 'mock-jwt-token'}, clear=True):
            # Create mock response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test reasoning response"
            mock_response.choices[0].message.tool_calls = None
            # Mock usage data for cost calculation
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 20
            mock_response.usage.prompt_tokens_details = None

            llm = OpenOnionLLM(model="co/o4-mini")

            with patch.object(llm.client.chat.completions, 'create', return_value=mock_response) as mock_create:
                result = llm.complete([{"role": "user", "content": "test reasoning"}])

                # Check call parameters for o4-mini
                call_kwargs = mock_create.call_args[1]
                assert call_kwargs['model'] == "o4-mini"  # Sent without prefix

                # Check response
                assert result.content == "Test reasoning response"

    def test_complete_with_tools(self):
        """Test complete method with tools."""
        with patch.dict(os.environ, {'OPENONION_API_KEY': 'mock-jwt-token'}, clear=True):
            # Create mock response with tool call
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = None
            # Mock usage data for cost calculation
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 20
            mock_response.usage.prompt_tokens_details = None

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
        with patch.dict(os.environ, {'OPENONION_API_KEY': 'mock-jwt-token'}, clear=True):
            # Test various co/ models
            models = ["co/gpt-4o", "co/o4-mini", "co/claude-3-haiku", "co/gemini-2.0-flash-exp"]

            for model in models:
                llm = create_llm(model)
                assert isinstance(llm, OpenOnionLLM)
                # Model stored without co/ prefix internally
                assert llm.model == model.removeprefix("co/")

    def test_no_auth_token_error(self):
        """Test error when no auth token is found."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                OpenOnionLLM(model="co/gpt-4o")

            assert "OPENONION_API_KEY not found" in str(exc_info.value)
            assert "Run 'co init'" in str(exc_info.value)

    def test_get_balance_success(self):
        """Test get_balance returns balance on successful request."""
        with patch.dict(os.environ, {'OPENONION_API_KEY': 'mock-jwt-token'}, clear=True):
            llm = OpenOnionLLM(model="co/gpt-4o")

            # Mock successful response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "public_key": "0xabc123",
                "balance_usd": 4.2224,
                "credits_usd": 5.0,
                "total_cost_usd": 0.7776
            }

            with patch('requests.get', return_value=mock_response) as mock_get:
                balance = llm.get_balance()

                # Check that request was made correctly
                mock_get.assert_called_once()
                call_args = mock_get.call_args
                assert call_args[0][0] == "https://oo.openonion.ai/api/v1/auth/me"
                assert call_args[1]['headers']['Authorization'] == "Bearer mock-jwt-token"
                assert call_args[1]['timeout'] == 2

                # Check balance returned
                assert balance == 4.2224

    def test_get_balance_network_error(self):
        """Test get_balance returns None on network error."""
        with patch.dict(os.environ, {'OPENONION_API_KEY': 'mock-jwt-token'}, clear=True):
            llm = OpenOnionLLM(model="co/gpt-4o")

            # Mock network error
            with patch('requests.get', side_effect=Exception("Network error")):
                balance = llm.get_balance()

                # Should return None on error
                assert balance is None

    def test_get_balance_auth_error(self):
        """Test get_balance returns None on 401 auth error."""
        with patch.dict(os.environ, {'OPENONION_API_KEY': 'mock-jwt-token'}, clear=True):
            llm = OpenOnionLLM(model="co/gpt-4o")

            # Mock auth error response
            mock_response = MagicMock()
            mock_response.status_code = 401

            with patch('requests.get', return_value=mock_response):
                balance = llm.get_balance()

                # Should return None on auth error
                assert balance is None

    def test_get_balance_invalid_response(self):
        """Test get_balance returns None when balance_usd missing."""
        with patch.dict(os.environ, {'OPENONION_API_KEY': 'mock-jwt-token'}, clear=True):
            llm = OpenOnionLLM(model="co/gpt-4o")

            # Mock response without balance_usd
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "public_key": "0xabc123"
                # Missing balance_usd
            }

            with patch('requests.get', return_value=mock_response):
                balance = llm.get_balance()

                # Should return None when balance_usd is missing
                assert balance is None

    def test_get_balance_development_url(self):
        """Test get_balance uses correct URL in development mode."""
        with patch.dict(os.environ, {'OPENONION_DEV': '1', 'OPENONION_API_KEY': 'mock-jwt-token'}):
            llm = OpenOnionLLM(model="co/o4-mini")

            # Mock successful response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"balance_usd": 10.0}

            with patch('requests.get', return_value=mock_response) as mock_get:
                balance = llm.get_balance()

                # Check development URL was used
                call_args = mock_get.call_args
                assert call_args[0][0] == "http://localhost:8000/api/v1/auth/me"
                assert balance == 10.0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])