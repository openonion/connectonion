#!/usr/bin/env python3
"""
Test to show what the menu looks like with shortcuts.
"""

from connectonion.debugger_ui import DebuggerUI, BreakpointAction, BreakpointContext

# Create UI and test context
ui = DebuggerUI()

# Create a dummy context
context = BreakpointContext(
    tool_name="test_tool",
    tool_args={"input": "test"},
    trace_entry={"result": "test result", "timing": 10},
    user_prompt="Test prompt",
    iteration=1,
    max_iterations=10,
    previous_tools=[],
    next_actions=[]
)

print("=" * 60)
print("Menu Display Test")
print("=" * 60)
print()
print("The interactive menu provides:")
print("- Arrow navigation (↑/↓)")
print("- Keyboard shortcuts (c/e/q + Enter)")
print("- Visual selection indicator (»)")
print()
print("Showing menu now...")
print()

# Show just the menu
action = ui._show_action_menu()
print(f"\nYou selected: {action.value}")

if action == BreakpointAction.QUIT:
    print("Successfully quit with keyboard shortcut!")
elif action == BreakpointAction.CONTINUE:
    print("Would continue execution...")
elif action == BreakpointAction.EDIT:
    print("Would open edit dialog...")