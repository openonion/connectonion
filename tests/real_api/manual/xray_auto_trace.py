#!/usr/bin/env python3
"""Test the new auto-tracing feature of @xray decorator."""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from connectonion import Agent, xray


class TestAutoTrace:
    """Test tools with auto-tracing."""

    @xray  # Should automatically trace!
    def process_data(self, data: str, count: int = 3) -> str:
        """Process data with automatic tracing."""
        result = data
        for i in range(count):
            result = f"Step_{i+1}({result})"
        return result

    @xray(trace=False)  # Should NOT auto-trace
    def silent_process(self, text: str) -> str:
        """Process without auto-tracing."""
        return text.upper()

    # No decorator - should still work but no auto-trace
    def normal_tool(self, msg: str) -> str:
        """Normal tool without decorator."""
        # Can still access xray context
        if xray.agent:
            return f"Agent {xray.agent.name} says: {msg}"
        return msg


@xray  # Function tools should also work
def standalone_tool(message: str, repeat: int = 2) -> str:
    """Standalone function with auto-trace."""
    return " | ".join([message] * repeat)


def main():
    print("=" * 80)
    print("Testing @xray Auto-Tracing Feature")
    print("=" * 80)

    # Create test instance
    tools_obj = TestAutoTrace()

    # Create agent with mixed tools
    agent = Agent(
        name="trace_test_agent",
        tools=[
            tools_obj.process_data,
            tools_obj.silent_process,
            tools_obj.normal_tool,
            standalone_tool
        ],
        system_prompt="You are a test agent. Use the tools as requested."
    )

    print("\n### Test 1: @xray with auto-trace ###")
    print("Should show beautiful entry/exit traces:")
    result1 = agent.execute_tool("process_data", {"data": "hello", "count": 2})
    print(f"Result: {result1['result']}")

    print("\n### Test 2: @xray(trace=False) ###")
    print("Should NOT show auto-traces:")
    result2 = agent.execute_tool("silent_process", {"text": "quiet"})
    print(f"Result: {result2['result']}")

    print("\n### Test 3: No decorator ###")
    print("Should work but no auto-trace:")
    result3 = agent.execute_tool("normal_tool", {"msg": "test"})
    print(f"Result: {result3['result']}")

    print("\n### Test 4: Standalone function with @xray ###")
    print("Should show auto-trace for function tool:")
    result4 = agent.execute_tool("standalone_tool", {"message": "Hi", "repeat": 3})
    print(f"Result: {result4['result']}")

    print("\n### Test 5: Via LLM (with auto-trace) ###")
    print("Testing through actual LLM call:")
    llm_result = agent.input("Use process_data to process 'LLM test' with count 1")
    print(f"LLM Result: {llm_result}")

    print("\n" + "=" * 80)
    print("✅ Auto-tracing tests completed!")
    print("=" * 80)


if __name__ == "__main__":
    main()