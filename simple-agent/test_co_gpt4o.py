#!/usr/bin/env python3
"""Test co/gpt-4o model."""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectonion.llm import create_llm


def test_gpt4o():
    """Test co/gpt-4o model."""
    print("Testing co/gpt-4o model")
    print("-" * 50)

    try:
        llm = create_llm("co/gpt-4o")
        print("✓ Created co/gpt-4o LLM")

        messages = [
            {"role": "user", "content": "Say 'Hello' and nothing else."}
        ]

        response = llm.complete(messages)
        print(f"✓ Response: {response.content}")

    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    test_gpt4o()