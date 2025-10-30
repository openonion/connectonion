#!/usr/bin/env python3
"""
Test the keyboard shortcuts in debug mode.
"""

from connectonion import Agent, xray

@xray
def test_tool(input: str) -> str:
    """A simple test tool."""
    return f"Processed: {input}"

# Create agent
agent = Agent(
    name="shortcut_test",
    tools=[test_tool],
    system_prompt="You are a test assistant. Use the test_tool."
)

print("=" * 60)
print("Testing Keyboard Shortcuts")
print("=" * 60)
print()
print("This test will:")
print("1. Execute a task that pauses at @xray breakpoint")
print("2. Show the new menu with shortcuts")
print("3. You can test:")
print("   - Press 'c' to continue")
print("   - Press 'e' to edit")
print("   - Press 'q' to quit")
print("   - Or use arrow keys + Enter")
print()

# Run with a simple task
agent.auto_debug("Test the keyboard shortcuts")