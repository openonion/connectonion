#!/usr/bin/env python3
"""Test co/o4-mini model directly."""

import sys
import os
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectonion.llm import create_llm, OpenOnionLLM


def test_direct_llm():
    """Test the co/o4-mini model directly."""
    print("Testing co/o4-mini model")
    print("-" * 50)

    # Check for config
    config_path = Path(__file__).parent / ".co" / "config.toml"
    print(f"Config path: {config_path}")
    print(f"Config exists: {config_path.exists()}")

    if config_path.exists():
        import toml
        config = toml.load(config_path)
        if "auth" in config and "token" in config["auth"]:
            print(f"✓ Found token: {config['auth']['token'][:20]}...")
        else:
            print("✗ No token in config")
            return

    # Test environment
    env = os.getenv("ENVIRONMENT", "production")
    print(f"Environment: {env}")

    # Try to create the LLM
    try:
        print("\nCreating co/o4-mini LLM...")
        llm = create_llm("co/o4-mini")
        print(f"✓ LLM created successfully")
        print(f"  Base URL: {llm.client.base_url}")
        print(f"  Model: {llm.model}")
    except Exception as e:
        print(f"✗ Failed to create LLM: {e}")
        return

    # Try a simple completion
    try:
        print("\nTesting completion...")
        messages = [
            {"role": "user", "content": "Answer in one word: What is 2+2?"}
        ]

        response = llm.complete(messages)
        print(f"✓ Completion successful")
        print(f"  Response: {response.content}")
    except Exception as e:
        print(f"✗ Completion failed: {e}")

        # Try with a different endpoint for testing
        print("\nTrying with development endpoint...")
        os.environ["OPENONION_DEV"] = "1"

        try:
            llm = create_llm("co/o4-mini")
            response = llm.complete(messages)
            print(f"✓ Dev endpoint worked!")
            print(f"  Response: {response.content}")
        except Exception as e2:
            print(f"✗ Dev endpoint also failed: {e2}")


if __name__ == "__main__":
    test_direct_llm()