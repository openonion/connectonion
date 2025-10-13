#!/usr/bin/env python3
"""
Demo showcasing the new LLM preview feature in debug mode.
This shows how the debugger now displays what the agent will do next.
"""

from connectonion import Agent, xray


@xray
def search_database(query: str) -> str:
    """Search the database for information."""
    return f"Found 3 results for '{query}': [Result1, Result2, Result3]"


@xray
def analyze_results(data: str) -> str:
    """Analyze the search results."""
    count = data.count("Result")
    return f"Analysis complete: Found {count} relevant items"


def format_output(text: str) -> str:
    """Format the final output (no @xray)."""
    return f"📊 Final Report: {text}"


def main():
    print("=" * 60)
    print("🔮 LLM Preview Feature Demo")
    print("=" * 60)
    print()
    print("This demo shows the new preview feature that displays")
    print("what the agent plans to do NEXT at each breakpoint.")
    print()
    print("Features demonstrated:")
    print("  • Real-time LLM preview of next planned action")
    print("  • Shows actual tool names and arguments")
    print("  • Indicates when task will be complete")
    print("  • No more hardcoded 'pending' placeholders")
    print()
    print("-" * 60)

    # Create agent
    agent = Agent(
        name="preview_demo",
        tools=[search_database, analyze_results, format_output],
        system_prompt="""You are a data assistant. When given a query:
        1. Search the database
        2. Analyze the results
        3. Format the output
        Always use all three tools in sequence."""
    )

    # Run in normal mode
    print("\n🚀 Running in NORMAL mode first:")
    print("-" * 40)

    result = agent.input("Find information about Python")
    print(f"\nResult: {result}")

    print("\n" + "=" * 60)
    print("✨ Demo Complete!")
    print()
    print("To see the preview feature in DEBUG mode:")
    print("  1. Run: python agent_debug.py")
    print("  2. Choose option 2 (Debug mode)")
    print("  3. Enter a task like 'Search, analyze and format data about testing'")
    print()
    print("At each @xray breakpoint, you'll see:")
    print("  • Current tool execution result")
    print("  • 🔮 LLM's Next Planned Action section")
    print("  • Actual next tool that will be called")
    print()


if __name__ == "__main__":
    main()