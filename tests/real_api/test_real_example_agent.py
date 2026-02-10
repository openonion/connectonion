"""Real API end-to-end example agent tests."""

from pathlib import Path

import pytest

from connectonion import Agent, xray
from tests.real_api.conftest import requires_openai


pytestmark = [pytest.mark.real_api, pytest.mark.e2e_online]


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
    processed = data.upper()
    return f"Processed: {processed}"


@requires_openai
def test_complete_agent_workflow(tmp_path):
    """
    Test a complete agent workflow demonstrating all major features.
    """
    log_path = tmp_path / "agent.log"

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
        log=str(log_path)  # Log to file (console always on by default)
    )

    # Test 1: Simple conversation without tools
    response = agent.input("Hello! What can you help me with?")
    assert response is not None
    assert isinstance(response, str)

    # Test 2: Use calculator tool
    response = agent.input("Calculate 15 * 7 for me")
    assert response is not None
    assert isinstance(response, str)

    # Test 3: Multi-tool usage
    response = agent.input("What time is it? Also calculate 100 / 4")
    assert response is not None
    assert isinstance(response, str)

    # Test 4: Error handling
    response = agent.input("Calculate this invalid expression: 2 ++ 2")
    assert response is not None
    assert isinstance(response, str)

    # Test 5: Check log file was created
    assert Path(log_path).exists()


@requires_openai
def test_agent_with_real_conversation(tmp_path):
    """
    Test agent with a real multi-turn conversation.
    """
    log_path = tmp_path / "conversation.log"

    agent = Agent(
        name="conversation_example",
        tools=[calculator, get_current_time, search_web],
        model="gpt-4o-mini",
        log=str(log_path)
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
        assert response is not None
        assert isinstance(response, str)
        assert not response.startswith("Error")

    # Verify conversation history
    assert agent.current_session is not None


@requires_openai
def test_agent_with_decorators():
    """
    Test agent with xray decorators.
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

    response = agent.input("Use the custom tool with input 'test data'")
    assert response is not None
    assert isinstance(response, str)

    response = agent.input("Process the text 'hello world' with the process_data function")
    assert response is not None
    assert isinstance(response, str)
