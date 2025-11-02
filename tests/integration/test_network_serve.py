#!/usr/bin/env python3
"""Test agent.serve() - Run an agent on the relay network."""

from dotenv import load_dotenv

# Load .env file for API keys
load_dotenv()

from connectonion import Agent

def search(query: str) -> str:
    """Search the web for information."""
    return f"Here are results for: {query}"

# Create agent with tool
agent = Agent(
    name="Helper",
    tools=[search],
    system_prompt="You are a helpful assistant."
)

print("=== Testing agent.serve() ===\n")
print("Starting agent on relay network...")
print("This will:")
print("  1. Load or generate Ed25519 keys from .co/")
print("  2. Connect to relay server")
print("  3. Send ANNOUNCE message")
print("  4. Wait for INPUT messages")
print("  5. Send heartbeat every 60s")
print("\nPress Ctrl+C to stop\n")

# Use production relay by default
import os
relay_url = os.getenv("RELAY_URL", "wss://oo.openonion.ai/ws/announce")

print(f"Using relay: {relay_url}\n")

# Start serving (blocks until Ctrl+C)
agent.serve(relay_url=relay_url)
