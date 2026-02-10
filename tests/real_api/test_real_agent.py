"""Real API tests for Agent input and tool execution."""

import pytest

from connectonion import Agent
from tests.real_api.conftest import requires_openai


pytestmark = pytest.mark.real_api


def calculator(expression: str) -> str:
    """Performs a mathematical calculation and returns the result."""
    try:
        allowed_chars = "0123456789+-*/(). "
        if all(c in allowed_chars for c in expression):
            return f"Result: {eval(expression)}"
        return "Error: Invalid characters in expression"
    except Exception as e:
        return f"Error: {str(e)}"


def get_current_time() -> str:
    """Returns the current time."""
    from datetime import datetime
    return datetime.now().isoformat()


@requires_openai
def test_agent_run_no_tools_needed():
    agent = Agent(name="test_no_tools", model="gpt-4o-mini", log=False)
    result = agent.input("Simply say 'Hello test'")
    assert result is not None
    assert isinstance(result, str)
    assert agent.current_session is not None
    assert agent.current_session.get("user_prompt") == "Simply say 'Hello test'"


@requires_openai
def test_agent_run_with_single_tool_call():
    agent = Agent(
        name="test_single_tool",
        tools=[calculator],
        model="gpt-4o-mini",
        system_prompt="You are a calculator assistant. When asked to calculate, use the calculator tool.",
        log=False,
    )

    result = agent.input("What is 40 + 2?")
    assert result is not None
    assert isinstance(result, str)
    tool_executions = [e for e in agent.current_session.get("trace", []) if e.get("type") == "tool_result"]
    # Must have at least one tool execution
    assert len(tool_executions) > 0, "Expected calculator tool to be executed"
    assert tool_executions[0].get("name") == "calculator"
    assert "42" in str(tool_executions[0].get("result", ""))


@requires_openai
def test_agent_run_with_multiple_tool_calls():
    agent = Agent(
        name="test_multi_tool",
        tools=[calculator, get_current_time],
        model="gpt-4o-mini",
        system_prompt="You have calculator and time tools. Use them when asked.",
        log=False,
    )

    result = agent.input("Calculate 10*5 and tell me the current time.")

    assert result is not None
    assert isinstance(result, str)
    tool_executions = [e for e in agent.current_session.get("trace", []) if e.get("type") == "tool_result"]
    # Must have tool executions
    assert len(tool_executions) > 0, "Expected tools to be executed"
    tool_names = [e.get("name") for e in tool_executions]
    # Should use both calculator and time tools
    assert "calculator" in tool_names, "Expected calculator to be called"
    assert "get_current_time" in tool_names, "Expected get_current_time to be called"
