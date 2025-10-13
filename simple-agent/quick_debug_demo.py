#!/usr/bin/env python3
"""
Quick demo of the auto_debug feature with default task.
Just run: python quick_debug_demo.py
"""

from connectonion import Agent, xray


@xray  # This tool will pause during debugging
def analyze(text: str) -> str:
    """Analyze the given text."""
    word_count = len(text.split())
    return f"Analysis: {word_count} words found. Content is about: {text[:30]}..."


def summarize(analysis: str) -> str:
    """Summarize the analysis (no @xray, won't pause)."""
    return f"Summary: {analysis.upper()}"


# Create agent
agent = Agent(
    name="quick_demo",
    tools=[analyze, summarize],
    system_prompt="Analyze and summarize text. Use both tools."
)

# Run with default task - no user input needed!
print("=" * 60)
print("🚀 Quick Debug Demo - Zero Configuration")
print("=" * 60)
print("\nThis demo will:")
print("1. Run a default task automatically")
print("2. Pause at the @xray breakpoint")
print("3. Show the LLM's next planned action")
print("4. Complete the task\n")

# Debug the default task
agent.auto_debug("Analyze this text about debugging: Debugging helps find bugs")

print("\n✨ Demo complete! The debugger paused at @xray tools.")
print("\nTo try with your own task:")
print('  agent.auto_debug("Your custom text to analyze")')