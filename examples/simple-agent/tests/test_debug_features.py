#!/usr/bin/env python3
"""
Comprehensive debug feature tests for ConnectOnion.

This file merges all debug-related tests:
- test_execution_analysis.py
- test_post_analysis.py
- test_menu_display.py
- test_shortcuts.py
- test_preview.py
- test_preview_direct.py
- quick_debug_demo.py
- demo_preview.py

Run specific tests:
    python tests/test_debug_features.py --test breakpoints
    python tests/test_debug_features.py --test post-analysis
    python tests/test_debug_features.py --test menu
    python tests/test_debug_features.py --test preview
    python tests/test_debug_features.py --demo quick
    python tests/test_debug_features.py --demo preview

Run all:
    python tests/test_debug_features.py
"""

import sys
from pathlib import Path
import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from connectonion import Agent, xray
from connectonion.debugger_ui import DebuggerUI, BreakpointAction, BreakpointContext
from connectonion.interactive_debugger import InteractiveDebugger


# ============================================================================
# Shared Test Tools
# ============================================================================

@xray
def calculate(operation: str, a: int, b: int) -> int:
    """Perform a calculation with @xray breakpoint.

    Args:
        operation: Operation to perform (add, subtract, multiply, divide)
        a: First number
        b: Second number

    Returns:
        Result of the calculation
    """
    if operation == "add":
        return a + b
    elif operation == "subtract":
        return a - b
    elif operation == "multiply":
        return a * b
    elif operation == "divide":
        return a // b if b != 0 else 0
    else:
        return 0


def get_weather(city: str) -> str:
    """Get weather information (mock).

    Args:
        city: City name

    Returns:
        Weather description
    """
    return f"The weather in {city} is sunny, 72°F"


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


@xray
def analyze_text(text: str) -> str:
    """Analyze the given text."""
    word_count = len(text.split())
    return f"Analysis: {word_count} words found. Content is about: {text[:30]}..."


def summarize(analysis: str) -> str:
    """Summarize the analysis (no @xray, won't pause)."""
    return f"Summary: {analysis.upper()}"


# ============================================================================
# Test 1: Debug with @xray Breakpoints
# ============================================================================

@pytest.mark.skip(reason="Interactive test - requires terminal. Run manually with: python test_debug_features.py --test breakpoints")
def test_debug_with_breakpoints():
    """Test post-execution analysis WITH @xray breakpoints."""
    print("\n" + "=" * 70)
    print("TEST 1: Debug with @xray Breakpoints")
    print("=" * 70 + "\n")

    print("This test demonstrates:")
    print("  • Agent pauses at @xray decorated tools")
    print("  • Shows execution context and results")
    print("  • Displays LLM's next planned action")
    print("  • Interactive menu with keyboard shortcuts\n")

    agent = Agent(
        name="test_breakpoints",
        tools=[calculate],
        model="gpt-4o-mini",
        system_prompt="You are a math assistant. Use the calculate tool."
    )

    print("Running: Calculate 5 + 3")
    print("-" * 70)
    agent.auto_debug("Calculate 5 + 3")

    print("\n✅ Test completed!")
    return True


# ============================================================================
# Test 2: Debug WITHOUT Breakpoints (Post-Analysis)
# ============================================================================

@pytest.mark.skip(reason="Interactive test - requires terminal. Run manually with: python test_debug_features.py --test post-analysis")
def test_debug_without_breakpoints():
    """Test post-execution analysis WITHOUT @xray breakpoints."""
    print("\n" + "=" * 70)
    print("TEST 2: Debug without Breakpoints (Post-Analysis)")
    print("=" * 70 + "\n")

    print("This test demonstrates:")
    print("  • Agent runs to completion without pausing")
    print("  • Shows post-execution analysis at the end")
    print("  • Works with tools that have NO @xray decorator\n")

    agent = Agent(
        name="test_post_analysis",
        tools=[calculate, get_weather],
        model="gpt-4o-mini",
        system_prompt="You are a helpful assistant. Use your tools."
    )

    print("Running: Calculate 10 + 5, then get weather for Tokyo")
    print("-" * 70)
    agent.auto_debug("First calculate 10 + 5, then tell me the weather in Tokyo")

    print("\n✅ Test completed!")
    return True


# ============================================================================
# Test 3: Menu Display and Keyboard Shortcuts
# ============================================================================

@pytest.mark.skip(reason="Interactive test - requires terminal. Run manually with: python test_debug_features.py --test menu")
def test_menu_display():
    """Test the interactive menu display and keyboard shortcuts."""
    print("\n" + "=" * 70)
    print("TEST 3: Menu Display and Keyboard Shortcuts")
    print("=" * 70 + "\n")

    print("This test demonstrates:")
    print("  • Interactive menu with arrow navigation (↑/↓)")
    print("  • Keyboard shortcuts (c/e/q + Enter)")
    print("  • Visual selection indicator (»)\n")

    # Create UI and test context
    ui = DebuggerUI()

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

    print("Showing interactive menu...")
    print("-" * 70)

    # Show the menu
    action = ui._show_action_menu()

    print(f"\n✅ You selected: {action.value}")

    if action == BreakpointAction.QUIT:
        print("   Successfully quit with keyboard shortcut!")
    elif action == BreakpointAction.CONTINUE:
        print("   Would continue execution...")
    elif action == BreakpointAction.EDIT:
        print("   Would open edit dialog...")

    return True


# ============================================================================
# Test 4: LLM Preview Generation
# ============================================================================

def test_llm_preview():
    """Test LLM preview feature that shows next planned action."""
    print("\n" + "=" * 70)
    print("TEST 4: LLM Preview Generation")
    print("=" * 70 + "\n")

    print("This test demonstrates:")
    print("  • Real-time preview of LLM's next planned action")
    print("  • Shows actual tool names and arguments")
    print("  • Indicates when task will be complete\n")

    # Create agent with multiple tools
    agent = Agent(
        name="test_preview",
        tools=[search_database, analyze_results, format_output],
        model="gpt-4o-mini",
        system_prompt="""You are a data assistant. When given a query:
        1. Search the database
        2. Analyze the results
        3. Format the output
        Always use all three tools in sequence."""
    )

    # Create debugger
    debugger = InteractiveDebugger(agent)

    # Simulate a tool execution
    trace_entry = {
        'tool_name': 'search_database',
        'tool_id': 'test_123',
        'result': 'Found 3 results',
        'status': 'success',
        'timing': 10.5
    }

    # Initialize session
    agent.current_session = {
        'messages': [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": "Find information about Python"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "test_123",
                    "type": "function",
                    "function": {
                        "name": "search_database",
                        "arguments": '{"query": "Python"}'
                    }
                }]
            }
        ],
        'trace': [],
        'turn': 1,
        'iteration': 1,
        'user_prompt': 'Find information about Python'
    }

    print("Generating LLM preview...")
    print("-" * 70)

    try:
        next_actions = debugger._get_llm_next_action_preview('search_database', trace_entry)

        if next_actions is not None:
            if next_actions:
                print(f"\n✅ Preview generated successfully!")
                print(f"   Next planned actions ({len(next_actions)}):")
                for i, action in enumerate(next_actions, 1):
                    print(f"     {i}. {action['name']}({action.get('args', {})})")
            else:
                print("\n✅ Preview shows task complete (no more tools needed)")
        else:
            print("\n⚠️  Preview unavailable (error occurred)")
    except Exception as e:
        print(f"\n❌ Error generating preview: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n✅ Test completed!")
    return True


# ============================================================================
# Demo 1: Quick Debug Demo (Zero Configuration)
# ============================================================================

def demo_quick_debug():
    """Zero-configuration debug demo with default task."""
    print("\n" + "=" * 70)
    print("DEMO 1: Quick Debug Demo - Zero Configuration")
    print("=" * 70 + "\n")

    print("This demo demonstrates:")
    print("  • Zero-configuration debugging")
    print("  • Automatic pause at @xray breakpoints")
    print("  • Default task execution")
    print("  • Interactive debugging workflow\n")

    # Create agent
    agent = Agent(
        name="quick_demo",
        tools=[analyze_text, summarize],
        model="gpt-4o-mini",
        system_prompt="Analyze and summarize text. Use both tools."
    )

    print("Running default task...")
    print("-" * 70)

    # Run with default task
    agent.auto_debug("Analyze this text about debugging: Debugging helps find bugs")

    print("\n✨ Demo complete!")
    print("\nTo try with your own task:")
    print('  agent.auto_debug("Your custom text to analyze")')

    return True


# ============================================================================
# Demo 2: Preview Feature Demo
# ============================================================================

def demo_preview_feature():
    """Demonstration of LLM preview feature."""
    print("\n" + "=" * 70)
    print("DEMO 2: LLM Preview Feature Demo")
    print("=" * 70 + "\n")

    print("This demo demonstrates:")
    print("  • Real-time LLM preview of next planned action")
    print("  • Shows actual tool names and arguments")
    print("  • Indicates when task will be complete")
    print("  • No more hardcoded 'pending' placeholders\n")

    # Create agent
    agent = Agent(
        name="preview_demo",
        tools=[search_database, analyze_results, format_output],
        model="gpt-4o-mini",
        system_prompt="""You are a data assistant. When given a query:
        1. Search the database
        2. Analyze the results
        3. Format the output
        Always use all three tools in sequence."""
    )

    print("Running in NORMAL mode first:")
    print("-" * 70)

    result = agent.input("Find information about Python")
    print(f"\n✅ Result: {result}")

    print("\n" + "=" * 70)
    print("✨ Demo Complete!")
    print("\nTo see the preview feature in DEBUG mode:")
    print("  Run: agent.auto_debug('Search and analyze data about testing')")
    print("\nAt each @xray breakpoint, you'll see:")
    print("  • Current tool execution result")
    print("  • 🔮 LLM's Next Planned Action section")
    print("  • Actual next tool that will be called")

    return True


# ============================================================================
# Main Test Runner
# ============================================================================

def run_all_tests():
    """Run all debug feature tests."""
    print("\n" + "=" * 70)
    print("RUNNING ALL DEBUG FEATURE TESTS")
    print("=" * 70)

    tests = [
        ("Debug with Breakpoints", test_debug_with_breakpoints),
        ("Debug without Breakpoints", test_debug_without_breakpoints),
        ("Menu Display", test_menu_display),
        ("LLM Preview", test_llm_preview),
    ]

    results = {}
    for name, test_func in tests:
        try:
            result = test_func()
            results[name] = result
        except Exception as e:
            print(f"\n❌ Test '{name}' failed with error: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {name}")

    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print("\n⚠️  Some tests failed")

    return all_passed


def main():
    """Main entry point with argument parsing."""
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "--test":
            if len(sys.argv) < 3:
                print("Usage: python test_debug_features.py --test [breakpoints|post-analysis|menu|preview]")
                return 1

            test_name = sys.argv[2]
            tests = {
                "breakpoints": test_debug_with_breakpoints,
                "post-analysis": test_debug_without_breakpoints,
                "menu": test_menu_display,
                "preview": test_llm_preview,
            }

            if test_name in tests:
                return 0 if tests[test_name]() else 1
            else:
                print(f"Unknown test: {test_name}")
                print(f"Available tests: {', '.join(tests.keys())}")
                return 1

        elif command == "--demo":
            if len(sys.argv) < 3:
                print("Usage: python test_debug_features.py --demo [quick|preview]")
                return 1

            demo_name = sys.argv[2]
            demos = {
                "quick": demo_quick_debug,
                "preview": demo_preview_feature,
            }

            if demo_name in demos:
                return 0 if demos[demo_name]() else 1
            else:
                print(f"Unknown demo: {demo_name}")
                print(f"Available demos: {', '.join(demos.keys())}")
                return 1

        else:
            print(f"Unknown command: {command}")
            print("Usage: python test_debug_features.py [--test TEST_NAME | --demo DEMO_NAME]")
            return 1

    # No arguments - run all tests
    return 0 if run_all_tests() else 1


if __name__ == "__main__":
    sys.exit(main())
