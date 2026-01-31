#!/usr/bin/env python3
"""
Test network features: host() with relay and connect()

This script tests:
1. Agent can be hosted with HTTP + relay and serve requests
2. RemoteAgent can connect and send input
"""

import sys
from connectonion import Agent, connect, host


def greet(name: str) -> str:
    """Simple greeting tool."""
    return f"Hello {name}! I'm a networked agent."


def test_serve():
    """Test host() with relay - makes agent available on network."""
    print("=== Testing host() with relay ===\n")

    # Create agent with tool
    agent = Agent(
        name="greeter",
        tools=[greet],
        system_prompt="You are a friendly greeting agent that uses the greet tool."
    )

    print("Starting agent on HTTP + relay network...")
    print("This will:")
    print("  1. Load or generate Ed25519 keys from .co/")
    print("  2. Start HTTP server on port 8000")
    print("  3. Connect to relay server in background")
    print("  4. Wait for HTTP or relay requests")
    print("\nPress Ctrl+C to stop\n")

    # This blocks forever until Ctrl+C
    host(agent, port=8000, relay_url="ws://localhost:8000")


def test_connect():
    """Test connect() - use a remote agent."""
    print("=== Testing connect() ===\n")

    # You need an agent address from test_serve() output
    print("To test connect(), you need to:")
    print("  1. Run test_serve() in another terminal")
    print("  2. Copy the agent address from the output")
    print("  3. Paste it below and uncomment")
    print()

    # Example:
    # remote_agent = connect("0x...", relay_url="ws://localhost:8000")
    # response = remote_agent.input("Greet Alice")
    # print(f"Response: {response}")

    print("Not implemented - see comments above")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_network.py serve    - Start serving agent")
        print("  python test_network.py connect  - Connect to remote agent")
        sys.exit(1)

    command = sys.argv[1]

    if command == "serve":
        test_serve()
    elif command == "connect":
        test_connect()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
