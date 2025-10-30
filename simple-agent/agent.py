#!/usr/bin/env python3
"""Minimal ConnectOnion agent example."""

import os
import sys
from connectonion import Agent, llm_do
from connectonion.xray import xray


@xray  # Add @xray to see debugging in action
def hello_world(name: str = "World") -> str:
    """Simple greeting function with @xray for debugging.

    Args:
        name: Name to greet

    Returns:
        A greeting message
    """
    return f"Hello, {name}! Welcome to ConnectOnion."


def main():
    """Run the minimal agent."""
    # Use co/o4-mini by default, can override with MODEL env var
    model = "co/o4-mini"
    print(f"🚀 ConnectOnion Simple Agent")
    print(f"📦 Using model: {model}")
    print("-" * 50)

    try:
        # Create agent with a simple tool
        agent = Agent(
            name="minimal-agent",
            tools=[hello_world],
            model=model
        )

        # Example interaction (use input method instead of run)
        print("🤖 Agent: Processing your request...")
        response = agent.input("Say hello to the user using the hello_world tool")
        print(f"✅ Response: {response}")

        # You can also use llm_do directly for simple queries
        print("\n📝 Direct LLM query...")
        simple_response = llm_do("What is ConnectOnion in one sentence?", model=model)
        print(f"✅ Response: {simple_response}")

        # Optional: Try debug mode (comment out the above and uncomment below)
        # print("\n🔍 Debug Mode: Run with agent.auto_debug() for interactive debugging")
        # print("   Uncomment the line below to try it:")
        # # agent.auto_debug()  # Interactive debugging with breakpoints at @xray tools

    except ValueError as e:
        if "Internal Server Error" in str(e):
            print(f"❌ Error: The API returned an internal server error.")
            print(f"   This often means the authentication token has expired.")
            print(f"   Please run 'co auth' to refresh your authentication.")
        elif "No authentication token found" in str(e):
            print(f"❌ Error: No authentication token found.")
            print(f"   Please run 'co auth' to authenticate first.")
        else:
            print(f"❌ Error: {e}")

        print("\n💡 Tip: You can also use your own API key:")
        print("   export OPENAI_API_KEY='sk-...'")
        print("   MODEL='gpt-4o-mini' python agent.py")
        return 1

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1

    print("\n" + "-" * 50)
    print("✅ Agent completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())