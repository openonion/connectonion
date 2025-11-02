#!/usr/bin/env python3
"""Test connect() - Connect to a remote agent and send requests."""

import sys
from connectonion import connect

if len(sys.argv) < 2:
    print("Usage: python test_connect.py <agent_address>")
    print("\nExample:")
    print("  python test_connect.py 0xd5f4b57815bd62c715c9efaa8b9aa5e74bff0f6a1e8b4090f8127cb19faacace")
    sys.exit(1)

agent_address = sys.argv[1]

print(f"=== Testing connect() ===\n")
print(f"Connecting to agent: {agent_address[:16]}...")

# Use production relay by default
import os
relay_url = os.getenv("RELAY_URL", "wss://oo.openonion.ai/ws/announce")

print(f"Using relay: {relay_url}")

# Connect to remote agent
remote_agent = connect(agent_address, relay_url=relay_url)

print("✓ Connected!\n")

# Send a request
prompt = "What is 2+2?"
print(f"Sending: '{prompt}'")
response = remote_agent.input(prompt)

print(f"\n✅ Response: {response}")
