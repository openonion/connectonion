"""
Example demonstrating useful_plugins.

Shows how to use pre-built plugins like reflection and react.

Run with:
    python examples/useful_plugins_example.py
"""

from connectonion import Agent
from connectonion.useful_plugins import reflection, react


def search(query: str) -> str:
    """Search for information"""
    return f"Found results for '{query}': Python is a high-level programming language known for simplicity and readability."


def main():
    print("\n" + "="*60)
    print("Example 1: Reflection Plugin")
    print("="*60 + "\n")

    # Agent with reflection plugin
    agent1 = Agent(
        name="reflective_agent",
        tools=[search],
        model="co/gpt-4o",
        plugins=[reflection]
    )

    result1 = agent1.input("Search for information about Python")
    print(f"\nFinal result: {result1}\n")


    print("\n" + "="*60)
    print("Example 2: ReAct Plugin")
    print("="*60 + "\n")

    # Agent with ReAct plugin
    agent2 = Agent(
        name="react_agent",
        tools=[search],
        model="co/gpt-4o",
        plugins=[react]
    )

    result2 = agent2.input("Search for Python and explain what you found")
    print(f"\nFinal result: {result2}\n")


    print("\n" + "="*60)
    print("Example 3: Both Plugins Together")
    print("="*60 + "\n")

    # Agent with both reflection and ReAct plugins
    agent3 = Agent(
        name="full_agent",
        tools=[search],
        model="co/gpt-4o",
        plugins=[reflection, react]
    )

    result3 = agent3.input("What is Python used for?")
    print(f"\nFinal result: {result3}\n")


if __name__ == "__main__":
    main()
