#!/usr/bin/env python3
"""
MVP Example: Interactive debugging with auto_debug()

This example demonstrates:
1. Creating an agent with @xray decorated tools
2. Starting debug session with agent.auto_debug()
3. Pausing at breakpoints
4. Using /continue to resume

Run this example:
    python auto_debug_mvp_example.py
"""

from connectonion import Agent
from connectonion.decorators import xray


# Create some tools - one with @xray, one without
@xray
def search_database(query: str) -> str:
    """Search for information in database. Has @xray so will pause."""
    # Simulate database search
    results = {
        "python": "Python is a programming language",
        "debug": "Debugging is the process of finding bugs",
        "test": "Testing ensures code quality"
    }

    # Find matching result
    for key in results:
        if key in query.lower():
            return f"Found: {results[key]}"

    return "No results found"


def process_data(data: str) -> str:
    """Process the data. No @xray, won't pause."""
    return f"Processed: {data.upper()}"


@xray
def save_result(content: str, filename: str = "output.txt") -> str:
    """Save result to file. Has @xray so will pause."""
    # In real code, would save to file
    return f"Saved '{content[:20]}...' to {filename}"


def main():
    """Main function to demonstrate auto_debug."""

    print("=" * 60)
    print("ConnectOnion Auto Debug MVP Example")
    print("=" * 60)
    print()
    print("This example demonstrates:")
    print("- Pausing at @xray decorated tools")
    print("- Viewing tool execution context")
    print("- Using /continue to resume")
    print()
    print("Tools in this agent:")
    print("  1. search_database (has @xray - WILL pause)")
    print("  2. process_data (no @xray - won't pause)")
    print("  3. save_result (has @xray - WILL pause)")
    print()
    print("=" * 60)
    print()

    # Create agent with mixed tools
    agent = Agent(
        name="debug_example",
        tools=[search_database, process_data, save_result],
        system_prompt="""You are a helpful assistant that searches for information,
        processes it, and saves the results. Use your tools to complete tasks.""",
        model="gpt-4o-mini"
    )

    # Start debug session
    print("Starting auto_debug session...")
    print("Try these example tasks:")
    print("  - 'Search for information about Python'")
    print("  - 'Find debug info and save it'")
    print("  - 'Process and save test data'")
    print()

    agent.auto_debug()


if __name__ == "__main__":
    main()