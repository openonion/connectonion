#!/usr/bin/env python3
"""
Test the LLM preview feature in auto_debug.
"""

import os
import sys
from connectonion import Agent, xray


@xray
def analyze_data(query: str) -> str:
    """Analyze data with @xray decorator."""
    if "python" in query.lower():
        return "Python: Popular for data science, web development, and automation"
    else:
        return f"Analysis of {query}: Data processed successfully"


def summarize_result(text: str) -> str:
    """Summarize the result (no @xray)."""
    words = text.split()
    return f"Summary ({len(words)} words): {text[:50]}..."


def main():
    """Test the preview feature."""
    print("Testing LLM Preview Feature in Debug Mode")
    print("-" * 40)

    # Create agent with tools
    agent = Agent(
        name="preview_test",
        tools=[analyze_data, summarize_result],
        system_prompt="You are a helpful assistant that analyzes data and summarizes results."
    )

    # Test with a simple task in normal mode first
    print("\n1. Testing normal execution:")
    result = agent.input("Analyze Python programming")
    print(f"Result: {result[:100]}...")

    print("\n" + "=" * 40)
    print("Preview test complete!")
    print("To test debug mode with preview, run:")
    print("  python -c \"from test_preview import *; agent = Agent('test', tools=[analyze_data, summarize_result]); agent.auto_debug()\"")


if __name__ == "__main__":
    main()