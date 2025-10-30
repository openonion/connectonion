#!/usr/bin/env python3
"""Test co/o4-mini model with mock authentication."""

import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectonion import Agent


def hello_world(name: str = "World") -> str:
    """Simple greeting function."""
    return f"Hello, {name}! Welcome to ConnectOnion."


def main():
    """Test with mocked API response."""
    print("Testing co/o4-mini with mock response")
    print("-" * 50)

    # Create mock response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello! I've used the hello_world tool to greet you."

    # Mock tool call
    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "hello_world"
    mock_tool_call.function.arguments = '{"name": "User"}'
    mock_tool_call.id = "call_123"
    mock_response.choices[0].message.tool_calls = [mock_tool_call]

    # Mock the OpenAI client
    with patch('connectonion.llm.openai.OpenAI') as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.base_url = "https://oo.openonion.ai/v1/"
        mock_client.api_key = "mock-token"

        # First call returns tool call, second returns final response
        final_response = MagicMock()
        final_response.choices = [MagicMock()]
        final_response.choices[0].message.content = "Hello, User! Welcome to ConnectOnion. I've successfully greeted you using the hello_world tool."
        final_response.choices[0].message.tool_calls = None

        mock_client.chat.completions.create.side_effect = [mock_response, final_response]

        # Create agent with co/o4-mini
        print("Creating agent with co/o4-mini model...")
        agent = Agent(
            name="test-agent",
            tools=[hello_world],
            model="co/o4-mini"
        )

        print(f"✓ Agent created with model: {agent.llm.model}")
        print(f"✓ Base URL: {agent.llm.client.base_url}")

        # Test with tool
        print("\nTesting agent with hello_world tool...")
        response = agent.input("Say hello to the user")
        print(f"✓ Response: {response}")

        # Check that the correct parameters were used
        calls = mock_client.chat.completions.create.call_args_list
        print(f"\n✓ Made {len(calls)} API calls")

        # Check first call parameters
        first_call = calls[0][1]
        print(f"✓ First call used model: {first_call['model']}")
        print(f"✓ First call had max_completion_tokens: {first_call.get('max_completion_tokens', 'Not set')}")
        print(f"✓ First call had temperature: {first_call.get('temperature', 'Not set')}")
        print(f"✓ First call had tools: {'tools' in first_call}")

        # Verify o4-mini specific parameters
        assert first_call['model'] == 'co/o4-mini'
        assert first_call['max_completion_tokens'] == 16384
        assert first_call['temperature'] == 1
        assert 'max_tokens' not in first_call

        print("\n" + "-" * 50)
        print("✅ All tests passed! co/o4-mini integration works correctly.")
        print("\nNote: This test used mocked responses because the actual token is expired.")
        print("With a valid token, the agent would make real API calls to OpenOnion.")


if __name__ == "__main__":
    main()