#!/usr/bin/env python3
"""Minimal ConnectOnion agent with a simple calculator tool."""

import os
from dotenv import load_dotenv
from connectonion import Agent, llm_do

# Load environment variables from .env file
load_dotenv()


def calculator(operation: str, a: float, b: float) -> float:
    """Simple calculator that performs basic arithmetic operations.

    Args:
        operation: The operation to perform (add, subtract, multiply, divide)
        a: First number
        b: Second number

    Returns:
        The result of the calculation
    """
    if operation == "add":
        return a + b
    elif operation == "subtract":
        return a - b
    elif operation == "multiply":
        return a * b
    elif operation == "divide":
        if b == 0:
            return "Error: Cannot divide by zero"
        return a / b
    else:
        return f"Error: Unknown operation '{operation}'"


def main():
    """Run the minimal calculator agent with interactive conversation."""

    # Create agent with calculator tool
    agent = Agent(
        name="calculator-agent",
        tools=[calculator],
        model=os.getenv("MODEL", "co/o4-mini")
    )

    print("🧮 Calculator Agent Started!")
    print("Ask me to perform calculations or chat with me.")
    print("Type 'quit' to exit.\n")

    # Interactive conversation loop
    while True:
        user_input = input("You: ").strip()

        if user_input.lower() in ['quit', 'exit', 'q']:
            print("👋 Goodbye!")
            break

        if not user_input:
            continue

        # Get response from agent (can use calculator tool if needed)
        response = agent.input(user_input)
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    # Quick demo before starting interactive mode
    print("=== Quick Demo ===\n")

    # Example 1: Using the agent with tools
    agent = Agent(
        name="calculator-agent",
        tools=[calculator],
        model=os.getenv("MODEL", "co/o4-mini")
    )

    demo_response = agent.input("What is 25 times 4?")
    print(f"Q: What is 25 times 4?")
    print(f"A: {demo_response}\n")

    # Example 2: Direct LLM call without tools (faster for simple queries)
    quick_response = llm_do("In one sentence, what is ConnectOnion?")
    print(f"Q: What is ConnectOnion?")
    print(f"A: {quick_response}\n")

    print("=" * 50 + "\n")

    # Start interactive mode
    main()
