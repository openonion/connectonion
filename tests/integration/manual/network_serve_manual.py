#!/usr/bin/env python3
"""Test host() with relay - Run an agent on HTTP + relay network."""

from dotenv import load_dotenv

# Load .env file for API keys
load_dotenv()

from connectonion import Agent, host

def search(query: str) -> str:
    """Search the web for information."""
    return f"Here are results for: {query}"

# Create agent with tool
agent = Agent(
    name="Helper",
    tools=[search],
    system_prompt="You are a helpful assistant."
)

print("=== Testing host() with relay ===\n")
print("Starting agent on HTTP + relay network...")
print("This will:")
print("  1. Load or generate Ed25519 keys from .co/")
print("  2. Start HTTP server on port 8000")
print("  3. Connect to relay server in background")
print("  4. Accept requests via HTTP or relay")
print("\nPress Ctrl+C to stop\n")

# Use production relay by default
import os
relay_url = os.getenv("RELAY_URL", "wss://oo.openonion.ai/ws/announce")

print(f"Using relay: {relay_url}\n")

# Start hosting (HTTP + relay)
host(agent, port=8000, relay_url=relay_url)
