#!/usr/bin/env python3
"""
Purpose: Interactive debugging example demonstrating @xray breakpoints and auto_debug workflow
LLM-Note:
  Dependencies: imports from [connectonion.Agent, connectonion.xray] | standalone example (not imported by other files) | no test files
  Data flow: receives sys.argv (command line args) → creates Agent with @xray decorated tools → calls agent.auto_debug(task) → pauses at @xray breakpoints → returns exit code
  State/Effects: prints to stdout/stderr via Rich console | reads sys.argv | agent writes to .co/logs/debug_demo.log | no state mutations
  Integration: exposes three example tools: search_info(), format_result(), save_to_memory() | demonstrates @xray decorator usage | shows interactive vs single-task debug modes
  Performance: synchronous execution | pauses at each @xray decorated tool | no caching or optimization
  Errors: no error handling (relies on Agent's error handling) | exits with code 0 or 1

This example shows:
- Creating an agent with @xray decorated tools
- Using agent.auto_debug() for interactive debugging
- Pausing at breakpoints and continuing execution

Run this example:
    python agent_debug.py
    python agent_debug.py "Your custom task"
    python agent_debug.py --interactive
"""

import os
import sys
from connectonion import Agent, xray  # xray is exported from main package


# Tool with @xray - will pause during debugging
@xray
def search_info(query: str) -> str:
    """Search for information. Has @xray decorator so will pause in debug mode.

    Args:
        query: What to search for

    Returns:
        Search results
    """
    # Simulate search
    if "python" in query.lower():
        return "Python is a high-level programming language known for its simplicity."
    elif "debug" in query.lower():
        return "Debugging is the process of finding and fixing bugs in code."
    else:
        return f"Information about '{query}' found in database."


# Tool without @xray - won't pause
def format_result(text: str) -> str:
    """Format the result. No @xray, so won't pause in debug mode.

    Args:
        text: Text to format

    Returns:
        Formatted text
    """
    return f"📋 Result: {text.upper()}"


# Another tool with @xray
@xray
def save_to_memory(data: str, key: str = "default") -> str:
    """Save data to memory. Has @xray decorator so will pause.

    Args:
        data: Data to save
        key: Storage key

    Returns:
        Confirmation message
    """
    # Simulate saving
    return f"Saved {len(data)} characters to memory with key '{key}'"


def main():
    """Run the agent with debugging."""
    print("=" * 60)
    print("🔍 ConnectOnion Auto Debug Mode")
    print("=" * 60)
    print()
    print("Interactive debugging session with breakpoints.")
    print("Tools marked with @xray will pause for inspection.")
    print()
    print("Available tools:")
    print("  • search_info    (@xray - WILL pause)")
    print("  • format_result  (no @xray - won't pause)")
    print("  • save_to_memory (@xray - WILL pause)")
    print()
    print("When paused at a breakpoint:")
    print("  • Review the tool arguments and results")
    print("  • Choose 'Continue' or 'Check and edit values'")
    print("  • See the LLM's next planned action (preview)")
    print()
    print("=" * 60)
    print()

    # Create agent
    agent = Agent(
        name="debug_demo",
        tools=[search_info, format_result, save_to_memory],
        system_prompt="""You are a helpful assistant that searches for information,
        formats it nicely, and saves important data. Use your tools to help the user."""
    )

    # Check if a task was provided via command line
    if len(sys.argv) > 1:
        # Check for special interactive flag
        if sys.argv[1] == "--interactive" or sys.argv[1] == "-i":
            # Interactive mode explicitly requested
            print("🔍 Starting interactive debug session...")
            print("-" * 40)
            print("Example tasks to try:")
            print("  - Search for Python info")
            print("  - Find debug information and save it")
            print("  - Search, format and save data about testing")
            print()
            agent.auto_debug()  # No prompt = interactive mode
        else:
            # Single task mode - run the provided task
            task = " ".join(sys.argv[1:])
            print(f"🔍 Debugging task: {task}")
            print("-" * 40)
            print()
            agent.auto_debug(task)
    else:
        # Default task mode - run a default example
        default_task = "Search for information about Python and format it"
        print(f"🔍 Running default debug example")
        print(f"Task: {default_task}")
        print("-" * 40)
        print()
        print("💡 Tip: You can provide your own task:")
        print("  python agent_debug.py \"Your custom task\"")
        print("  python agent_debug.py --interactive  # For interactive mode")
        print()
        agent.auto_debug(default_task)

    print("\n" + "=" * 60)
    print("✅ Debug session ended!")
    return 0


if __name__ == "__main__":
    sys.exit(main())