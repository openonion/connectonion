"""
Example demonstrating useful_plugins.

Shows how to use pre-built plugins like re_act.

Run with:
    python examples/useful_plugins_example.py
"""

from connectonion import Agent
from connectonion.useful_plugins import re_act


def search(query: str) -> str:
    """Search for information"""
    return f"Found results for '{query}': Python is a high-level programming language known for simplicity and readability."


def main():
    print("\n" + "="*60)
    print("Example: ReAct Plugin (Planning + Reflection)")
    print("="*60 + "\n")

    # Agent with ReAct plugin
    agent = Agent(
        name="react_agent",
        tools=[search],
        model="co/gpt-4o",
        plugins=[re_act]
    )

    result = agent.input("Search for Python and explain what you found")
    print(f"\nFinal result: {result}\n")


if __name__ == "__main__":
    main()
