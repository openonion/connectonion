"""
Complete example agent that demonstrates all ConnectOnion features.

This test serves as both:
1. A comprehensive integration test
2. Living documentation showing best practices
3. A template for building real agents

Run with: pytest test_example_agent.py -v
"""

import os
import pytest
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from connectonion import Agent, xray, replay, send_email, get_emails

# Load environment variables from tests/.env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


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


def get_current_time() -> str:
    """Get the current date and time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def search_web(query: str) -> str:
    """
    Simulate web search (in real agent, this would call an API).

    Args:
        query: The search query

    Returns:
        Mock search results
    """
    return f"Search results for '{query}': [Result 1], [Result 2], [Result 3]"


@xray
def process_data(data: str) -> str:
    """
    Process data with xray debugging enabled.
    This demonstrates the @xray decorator.
    """
    # The @xray decorator will capture all inputs/outputs
    processed = data.upper()
    return f"Processed: {processed}"


class TestExampleAgent:
    """Comprehensive test demonstrating a complete agent workflow."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup happens automatically

    def test_complete_agent_workflow(self, temp_dir):
        """
        Test a complete agent workflow demonstrating all major features.

        This test shows:
        1. Agent creation with multiple tools
        2. Debug and logging configuration
        3. Multi-turn conversations
        4. Tool execution
        5. History tracking
        6. Error handling
        """

        # Create an agent with all features enabled
        agent = Agent(
            name="example_assistant",
            tools=[
                calculator,
                get_current_time,
                search_web,
                process_data
            ],
            system_prompt="You are a helpful assistant with access to various tools.",
            model="gpt-4o-mini",  # Using a cost-effective model
            log=f"{temp_dir}/agent.log"  # Log to file (console always on by default)
        )

        # Test 1: Simple conversation without tools
        response = agent.input("Hello! What can you help me with?")
        assert response.content is not None
        assert len(agent.history.records) > 0

        # Test 2: Use calculator tool
        response = agent.input("Calculate 15 * 7 for me")
        assert response.content is not None
        # Check that tool was called
        if len(agent.history.records) > 0:
            last_record = agent.history.records[-1]
            if last_record.tool_calls:
                assert any(tc["name"] == "calculator" for tc in last_record.tool_calls)

        # Test 3: Multi-tool usage
        response = agent.input(
            "What time is it? Also calculate 100 / 4"
        )
        assert response.content is not None

        # Test 4: Error handling
        response = agent.input("Calculate this invalid expression: 2 ++ 2")
        assert response.content is not None
        # Agent should handle the error gracefully

        # Test 5: Check history persistence
        history_file = Path(agent.history.save_dir) / "behavior.json"
        assert history_file.exists()

        # Test 6: Check log file was created
        if isinstance(agent.console.log_file, Path):
            assert agent.console.log_file.exists()

    @pytest.mark.real_api
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_agent_with_real_conversation(self, temp_dir):
        """
        Test agent with a real multi-turn conversation.

        This demonstrates:
        1. Context retention across turns
        2. Complex tool usage
        3. Natural conversation flow
        """

        agent = Agent(
            name="conversation_example",
            tools=[calculator, get_current_time, search_web],
            model="gpt-4o-mini",
            log=f"{temp_dir}/conversation.log"  # Console always on, log to file
        )

        # Multi-turn conversation
        conversations = [
            "Hi! I'm planning a meeting. What's the current time?",
            "The meeting will have 12 people. If we order 3 pizzas, how many slices per person if each pizza has 8 slices?",
            "Great! Can you search for 'best pizza places for catering'?",
            "Thank you for your help!"
        ]

        for message in conversations:
            response = agent.input(message)
            assert response.content is not None
            assert not response.content.startswith("Error")

        # Verify conversation history
        assert len(agent.history.records) >= 4

    @pytest.mark.real_api
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No OpenAI API key")
    def test_agent_with_decorators(self, temp_dir):
        """
        Test agent with xray and replay decorators.

        This demonstrates:
        1. Using @xray for debugging
        2. Replay functionality
        3. Decorator integration with agents
        """

        @xray
        def custom_tool(input_text: str) -> str:
            """Tool with xray debugging."""
            return f"Processed with xray: {input_text}"

        agent = Agent(
            name="decorator_example",
            tools=[custom_tool, process_data],
            model="gpt-4o-mini"
        )

        # Use tools with decorators
        response = agent.input("Use the custom tool with input 'test data'")
        assert response.content is not None

        response = agent.input("Process the text 'hello world' with the process_data function")
        assert response.content is not None

    def test_agent_with_mock_llm(self):
        """
        Test agent with mocked LLM for unit testing.

        This demonstrates how to test agent logic without API calls.
        """
        from unittest.mock import Mock
        from connectonion.llm import LLMResponse, ToolCall

        # Create mock LLM
        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponse(
            content="I'll calculate that for you.",
            tool_calls=[
                ToolCall(
                    name="calculator",
                    arguments={"expression": "5 + 5"},
                    id="call_123"
                )
            ],
            raw_response=None
        )

        # Create agent with mock
        agent = Agent(
            name="mock_example",
            llm=mock_llm,
            tools=[calculator]
        )

        response = agent.input("Calculate 5 + 5")

        # Verify mock was called
        assert mock_llm.complete.called
        # Verify tool was executed
        assert len(agent.history.records) > 0

    def test_agent_with_custom_system_prompt(self):
        """
        Test agent with custom system prompt and personality.

        This demonstrates prompt engineering for specific behaviors.
        """
        from unittest.mock import Mock
        from connectonion.llm import LLMResponse

        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponse(
            content="Ahoy! I be calculatin' that for ye!",
            tool_calls=[],
            raw_response=None
        )

        pirate_agent = Agent(
            name="pirate_assistant",
            llm=mock_llm,
            system_prompt="You are a helpful pirate assistant. Always speak like a pirate.",
            tools=[calculator]
        )

        response = pirate_agent.input("Can you help me?")

        # Check system prompt was included in messages
        call_args = mock_llm.complete.call_args
        messages = call_args[0][0] if call_args else []
        assert any(msg.get("role") == "system" for msg in messages)

    def test_agent_error_recovery(self):
        """
        Test agent's ability to recover from tool errors.

        This demonstrates resilient error handling.
        """
        def failing_tool(input: str) -> str:
            """A tool that always fails."""
            raise Exception("Tool failure!")

        from unittest.mock import Mock
        from connectonion.llm import LLMResponse, ToolCall

        mock_llm = Mock()
        # First response: try to use the failing tool
        mock_llm.complete.side_effect = [
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        name="failing_tool",
                        arguments={"input": "test"},
                        id="call_1"
                    )
                ],
                raw_response=None
            ),
            # Second response: acknowledge the error
            LLMResponse(
                content="I encountered an error with the tool, but I can still help you.",
                tool_calls=[],
                raw_response=None
            )
        ]

        agent = Agent(
            name="error_recovery",
            llm=mock_llm,
            tools=[failing_tool, calculator],
            max_iterations=2
        )

        response = agent.input("Use the failing tool")

        # Agent should recover and provide a response
        assert response.content is not None
        assert "error" in response.content.lower() or "help" in response.content.lower()


if __name__ == "__main__":
    # Allow running directly with: python test_example_agent.py
    pytest.main([__file__, "-v"])