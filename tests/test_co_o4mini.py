#!/usr/bin/env python3
"""Test ConnectOnion agent with co/o4-mini model."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from connectonion import Agent


def hello_world(name: str = "World") -> str:
    """Simple greeting function.

    Args:
        name: Name to greet

    Returns:
        A greeting message
    """
    return f"Hello, {name}! Welcome to ConnectOnion."


def add_numbers(a: int, b: int) -> int:
    """Add two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        The sum of a and b
    """
    return a + b


def main():
    """Test co/o4-mini model with ConnectOnion agent."""

    print("Testing co/o4-mini model with ConnectOnion")
    print("-" * 50)

    # Check authentication
    config_paths = [
        Path.cwd() / ".co" / "config.toml",
        Path.home() / ".connectonion" / ".co" / "config.toml"
    ]

    auth_found = False
    for config_path in config_paths:
        if config_path.exists():
            auth_found = True
            print(f"✓ Found authentication config at: {config_path}")
            break

    if not auth_found:
        print("⚠️  No authentication found!")
        print("Run 'co auth' first to authenticate with OpenOnion")
        return 1

    # Test 1: Simple greeting with tool
    try:
        print("\n1. Testing simple greeting with tool:")
        agent = Agent(
            name="test-o4mini-greeting",
            tools=[hello_world],
            model="co/o4-mini"
        )

        response = agent.input("Use the hello_world tool to greet Alice")
        print(f"   Response: {response}")
        print("   ✓ Greeting with tool works!")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return 1

    # Test 2: Math with tool
    try:
        print("\n2. Testing math calculation with tool:")
        agent = Agent(
            name="test-o4mini-math",
            tools=[add_numbers],
            model="co/o4-mini"
        )

        response = agent.input("Use the add_numbers tool to calculate 42 plus 58")
        print(f"   Response: {response}")
        print("   ✓ Math with tool works!")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return 1

    # Test 3: Reasoning without tools
    try:
        print("\n3. Testing reasoning without tools:")
        agent = Agent(
            name="test-o4mini-reasoning",
            model="co/o4-mini"
        )

        response = agent.input("Think step by step: If I have 3 apples and buy 2 more, then give away 1, how many do I have?")
        print(f"   Response: {response}")
        print("   ✓ Reasoning works!")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return 1

    print("\n" + "-" * 50)
    print("✅ All tests passed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())