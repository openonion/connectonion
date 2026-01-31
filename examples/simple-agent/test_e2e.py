#!/usr/bin/env python3
"""
End-to-end test: Start agent, connect to it, send input, verify output.

This tests the full INPUT/OUTPUT flow through the relay.
"""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file for API keys
load_dotenv()

from connectonion import Agent, connect
from connectonion import relay, announce, address


def greet(name: str) -> str:
    """Simple greeting tool."""
    return f"Hello {name}! I'm a networked ConnectOnion agent."


async def run_serving_agent():
    """Run agent in serve mode - this is the "server" side."""
    print("=== Starting Serving Agent ===\n")

    # Create agent with tool (uses real API from .env)
    agent = Agent(
        name="test-greeter",
        tools=[greet],
        system_prompt="You are a friendly greeting agent. Use the greet tool to greet people.",
        model="gpt-4o-mini"
    )

    # Load or generate keys
    co_dir = Path.cwd() / 'simple-agent' / '.co'
    co_dir.mkdir(parents=True, exist_ok=True)

    addr_data = address.load(co_dir)
    if addr_data is None:
        print("Generating new keys...")
        addr_data = address.generate()
        address.save(addr_data, co_dir)
        print("✓ Keys saved\n")

    # Create ANNOUNCE message
    summary = "Test greeter agent for e2e testing"
    announce_msg = announce.create_announce_message(addr_data, summary, [])

    print(f"Agent address: {addr_data['address']}")
    print(f"Short: {addr_data['short_address']}\n")

    # Define async task handler (uses real agent.input)
    async def task_handler(prompt: str) -> str:
        print(f"→ Received input: {prompt[:50]}...")
        result = agent.input(prompt)
        print(f"✓ Processed, sending output")
        return result

    # Connect to relay and start serving
    print("Connecting to relay...")
    ws = await relay.connect("ws://localhost:8000")
    print("✓ Connected\n")

    return addr_data['address'], ws, announce_msg, task_handler


async def run_client_side(agent_address: str):
    """Run client connecting to remote agent."""
    print("\n=== Testing Client Connection ===\n")

    # Give server a moment to fully announce
    await asyncio.sleep(1)

    # Connect to remote agent
    print(f"Connecting to remote agent: {agent_address[:16]}...")
    remote_agent = connect(agent_address, relay_url="ws://localhost:8000")

    # Send input (use async version since we're in async code)
    print("Sending INPUT: 'Greet Alice'")
    response = await remote_agent.input_async("Greet Alice")

    print(f"\n✓ Received OUTPUT: {response}\n")

    return response


async def main():
    """Run full e2e test."""
    print("=== ConnectOnion E2E Network Test ===\n")

    # Start serving agent
    agent_address, ws, announce_msg, task_handler = await run_serving_agent()

    # Start serve loop in background
    serve_task = asyncio.create_task(
        relay.serve_loop(ws, announce_msg, task_handler, heartbeat_interval=60)
    )

    # Wait a bit for ANNOUNCE to register
    await asyncio.sleep(2)

    # Test client connection
    response = await run_client_side(agent_address)

    # Verify response contains expected greeting
    if "Alice" in response and "Hello" in response:
        print("✅ E2E Test PASSED - Agent served request successfully!")
        return 0
    else:
        print(f"❌ E2E Test FAILED - Unexpected response: {response}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
