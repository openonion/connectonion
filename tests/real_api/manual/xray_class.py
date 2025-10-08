#!/usr/bin/env python3
"""Test script to verify xray.trace() works with class methods."""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from connectonion import Agent, xray


class TestTools:
    """Test class with xray-decorated methods."""

    @xray
    def analyze(self, text: str) -> str:
        """Analyze the provided text and call trace."""
        print("\n=== Inside analyze method ===")
        print(f"xray.agent: {xray.agent}")
        print(f"xray.user_prompt: {xray.user_prompt}")
        print(f"xray.iteration: {xray.iteration}")

        # This should now work!
        print("\n=== Calling xray.trace() ===")
        xray.trace()

        return f"Analyzed: {text}"

    @xray
    def process(self, data: str, count: int = 1) -> str:
        """Process data multiple times."""
        result = data
        for i in range(count):
            result = f"Processed_{i+1}({result})"
        return result


def main():
    """Test the xray functionality with class methods."""
    print("Creating test tools instance...")
    tools = TestTools()

    print("Creating agent with class instance...")
    agent = Agent(
        name="xray_test_agent",
        tools=tools,
        # Using default model o4-mini
        system_prompt="You are a test agent. Use the analyze tool to test xray functionality."
    )

    print("\nTesting agent with xray-decorated class methods...")
    result = agent.input("Please analyze the text 'Hello World' using the analyze tool")

    print("\n=== Final Result ===")
    print(result)

    print("\n✅ Test completed successfully!")



if __name__ == "__main__":
    main()