"""Example agent tests that run without real API calls.

These tests use MockLLM for deterministic behavior while exercising
agent workflows and tool execution paths.
"""

import pytest

from connectonion import Agent
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.usage import TokenUsage
from tests.utils.mock_helpers import MockLLM


# Define example tools for the agent
def calculator(expression: str) -> str:
    """
    Evaluate a mathematical expression.

    Args:
        expression: A mathematical expression like "2 + 2" or "10 * 5"

    Returns:
        The result of the calculation
    """
    try:
        # Safe evaluation for basic math
        allowed_chars = "0123456789+-*/(). "
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return f"Result: {result}"
        return "Error: Invalid characters in expression"
    except Exception as e:
        return f"Error: {str(e)}"


@pytest.mark.e2e
class TestExampleAgent:
    """Example tests demonstrating agent workflows without network calls."""

    def test_agent_with_mock_llm(self):
        """
        Test agent with mocked LLM for unit testing.

        This demonstrates how to test agent logic without API calls.
        """
        # Create mock LLM with two responses (tool call + final)
        mock_llm = MockLLM(responses=[
            LLMResponse(
                content="I'll calculate that for you.",
                tool_calls=[
                    ToolCall(
                        name="calculator",
                        arguments={"expression": "5 + 5"},
                        id="call_123"
                    )
                ],
                raw_response=None, usage=TokenUsage()
            ),
            LLMResponse(
                content="The result is 10.",
                tool_calls=[],
                raw_response=None, usage=TokenUsage()
            )
        ])

        # Create agent with mock
        agent = Agent(
            name="mock_example",
            llm=mock_llm,
            tools=[calculator],
            log=False
        )

        response = agent.input("Calculate 5 + 5")

        # Verify mock was called
        assert mock_llm.call_count > 0
        assert response is not None

    def test_agent_with_custom_system_prompt(self):
        """
        Test agent with custom system prompt and personality.

        This demonstrates prompt engineering for specific behaviors.
        """
        mock_llm = MockLLM(responses=[
            LLMResponse(
                content="Ahoy! I be calculatin' that for ye!",
                tool_calls=[],
                raw_response=None, usage=TokenUsage()
            )
        ])

        pirate_agent = Agent(
            name="pirate_assistant",
            llm=mock_llm,
            system_prompt="You are a helpful pirate assistant. Always speak like a pirate.",
            tools=[calculator],
            log=False
        )

        response = pirate_agent.input("Can you help me?")

        # Check system prompt was included in messages
        assert mock_llm.call_count > 0
        messages = mock_llm.last_call["messages"]
        assert any(msg.get("role") == "system" for msg in messages)
        assert response is not None

    def test_agent_error_recovery(self):
        """
        Test agent's ability to recover from tool errors.

        This demonstrates resilient error handling.
        """
        def failing_tool(input: str) -> str:
            """A tool that always fails."""
            raise Exception("Tool failure!")

        mock_llm = MockLLM(responses=[
            # First response: try to use the failing tool
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        name="failing_tool",
                        arguments={"input": "test"},
                        id="call_1"
                    )
                ],
                raw_response=None, usage=TokenUsage()
            ),
            # Second response: acknowledge the error
            LLMResponse(
                content="I encountered an error with the tool, but I can still help you.",
                tool_calls=[],
                raw_response=None, usage=TokenUsage()
            )
        ])

        agent = Agent(
            name="error_recovery",
            llm=mock_llm,
            tools=[failing_tool, calculator],
            max_iterations=2,
            log=False
        )

        response = agent.input("Use the failing tool")

        # Agent should recover and provide a response
        assert response is not None
        assert isinstance(response, str)
        assert "error" in response.lower() or "help" in response.lower()


if __name__ == "__main__":
    # Allow running directly with: python test_example_agent.py
    pytest.main([__file__, "-v"])
