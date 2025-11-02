#!/usr/bin/env python3
"""
Test network features: agent.serve() and connect()

This script tests:
1. Agent can announce to relay and serve requests
2. RemoteAgent can connect and send input
"""

import sys
from connectonion import Agent, connect


def greet(name: str) -> str:
    """Simple greeting tool."""
    return f"Hello {name}! I'm a networked agent."


def test_serve():
    """Test agent.serve() - makes agent available on network."""
    print("=== Testing agent.serve() ===\n")

    # Create agent with tool
    agent = Agent(
        name="greeter",
        tools=[greet],
        system_prompt="You are a friendly greeting agent that uses the greet tool."
    )

    print("Starting agent on relay network...")
    print("This will:")
    print("  1. Load or generate Ed25519 keys from .co/")
    print("  2. Connect to relay server")
    print("  3. Send ANNOUNCE message")
    print("  4. Wait for INPUT messages")
    print("  5. Send heartbeat every 60s")
    print("\nPress Ctrl+C to stop\n")

    # This blocks forever until Ctrl+C
    agent.serve(relay_url="ws://localhost:8000/ws/announce")


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
    # remote_agent = connect("0x...", relay_url="ws://localhost:8000/ws/announce")
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
