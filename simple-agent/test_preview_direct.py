#!/usr/bin/env python3
"""
Direct test of the LLM preview feature to verify it's working.
"""

import sys
from connectonion import Agent, xray
from connectonion.interactive_debugger import InteractiveDebugger
from connectonion.debugger_ui import DebuggerUI, BreakpointContext


@xray
def step_one(data: str) -> str:
    """First step with @xray."""
    return f"Step 1 processed: {data}"


def step_two(text: str) -> str:
    """Second step without @xray."""
    return f"Step 2 result: {text.upper()}"


def step_three(content: str) -> str:
    """Third step without @xray."""
    return f"Final: {content}!!!"


def test_preview_generation():
    """Test that preview generation works."""
    print("Testing LLM Preview Generation")
    print("=" * 50)

    # Create agent with multiple tools
    agent = Agent(
        name="test_preview",
        tools=[step_one, step_two, step_three],
        system_prompt="Process data through multiple steps. Use all tools in sequence."
    )

    # Create debugger
    debugger = InteractiveDebugger(agent)

    # Simulate a tool execution result
    trace_entry = {
        'tool_name': 'step_one',
        'tool_id': 'test_123',
        'result': 'Step 1 processed: test data',
        'status': 'success',
        'timing': 10.5
    }

    # Initialize a session for testing
    agent.current_session = {
        'messages': [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": "Process this data: test data"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "test_123",
                    "type": "function",
                    "function": {
                        "name": "step_one",
                        "arguments": '{"data": "test data"}'
                    }
                }]
            }
        ],
        'trace': [],
        'turn': 1,
        'iteration': 1,
        'user_prompt': 'Process this data: test data'
    }

    # Test the preview generation
    print("\nCalling _get_llm_next_action_preview()...")
    try:
        next_actions = debugger._get_llm_next_action_preview('step_one', trace_entry)

        if next_actions is not None:
            if next_actions:
                print(f"\n✅ Preview generated successfully!")
                print(f"Next planned actions ({len(next_actions)}):")
                for i, action in enumerate(next_actions, 1):
                    print(f"  {i}. {action['name']}({action.get('args', {})})")
            else:
                print("\n✅ Preview shows task complete (no more tools needed)")
        else:
            print("\n⚠️ Preview unavailable (error occurred)")
    except Exception as e:
        print(f"\n❌ Error generating preview: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 50)
    print("Test complete!")


if __name__ == "__main__":
    test_preview_generation()