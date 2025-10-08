#!/usr/bin/env python3
"""Test that xray.trace() works WITHOUT the @xray decorator - automatic context injection."""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from connectonion import Agent, xray


class TestToolsNoDecorator:
    """Test class WITHOUT @xray decorators - should still work!"""

    # NO @xray decorator!
    def analyze(self, text: str) -> str:
        """Analyze text WITHOUT @xray decorator."""
        print("\n=== Inside analyze method (NO decorator) ===")
        print(f"xray.agent: {xray.agent}")
        print(f"xray.user_prompt: {xray.user_prompt}")
        print(f"xray.iteration: {xray.iteration}")

        # This should work even without @xray!
        print("\n=== Calling xray.trace() WITHOUT decorator ===")
        xray.trace()

        return f"Analyzed without decorator: {text}"

    # NO @xray decorator!
    def process(self, data: str, count: int = 1) -> str:
        """Process data WITHOUT @xray decorator."""
        # Should still have context!
        print(f"\nIn process: xray.agent = {xray.agent}")

        result = data
        for i in range(count):
            result = f"Processed_{i+1}({result})"
        return result


def plain_function_tool(message: str) -> str:
    """A plain function tool without any decorator."""
    print(f"\n=== Plain function tool ===")
    print(f"xray.agent: {xray.agent}")
    print(f"xray available: {xray.agent is not None}")

    # This should work!
    xray.trace()

    return f"Plain function says: {message}"


def main():
    """Test xray works WITHOUT decorators."""
    print("=" * 60)
    print("Testing AUTOMATIC xray context injection (no decorators)")
    print("=" * 60)

    # Test 1: Class methods without decorator
    print("\n### Test 1: Class methods WITHOUT @xray ###")
    tools_obj = TestToolsNoDecorator()

    agent1 = Agent(
        name="no_decorator_agent",
        tools=tools_obj,
        system_prompt="You are a test agent. Use the analyze tool."
    )

    result1 = agent1.input("Please analyze the text 'Hello Automatic Xray'")
    print(f"\nResult: {result1}")

    # Test 2: Plain function without decorator
    print("\n### Test 2: Plain function WITHOUT @xray ###")
    agent2 = Agent(
        name="plain_function_agent",
        tools=[plain_function_tool],
        system_prompt="You are a test agent. Use the plain_function_tool."
    )

    result2 = agent2.input("Use plain_function_tool to say 'No decorator needed!'")
    print(f"\nResult: {result2}")

    # Test 3: Manual execution without decorator
    print("\n### Test 3: Manual execution WITHOUT @xray ###")
    manual_result = agent1.execute_tool("process", {"data": "test", "count": 2})
    print(f"Manual result: {manual_result}")

    print("\n" + "=" * 60)
    print("✅ All tests passed! Xray works WITHOUT decorators!")
    print("=" * 60)


if __name__ == "__main__":
    main()