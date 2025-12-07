#!/usr/bin/env python3
"""
Simple test: Just connect and send ANNOUNCE once.

Tests connectivity without waiting for heartbeat or tasks.
"""

import sys
import asyncio
import os
import tempfile
import pytest

from pathlib import Path
from connectonion import address, announce, relay


@pytest.mark.asyncio
@pytest.mark.network
@pytest.mark.skipif(
    bool(os.getenv("CI") or os.getenv("GITHUB_ACTIONS")),
    reason="Skipped in CI - requires local relay server"
)
async def test_announce():
    """Test that we can connect and announce successfully."""
    print("=== Testing Client ANNOUNCE ===\n")

    # Use temp directory for keys in tests
    co_dir = Path(tempfile.gettempdir()) / ".co-test-announce"
    co_dir.mkdir(parents=True, exist_ok=True)
    addr_data = address.load(co_dir)

    if addr_data is None:
        print("Generating new keys...")
        addr_data = address.generate()
        address.save(addr_data, co_dir)
        print("✓ Keys saved\n")

    print(f"Address: {addr_data['address']}")
    print(f"Short: {addr_data['short_address']}\n")

    # Create ANNOUNCE message
    announce_msg = announce.create_announce_message(
        addr_data,
        "Test client agent for connectivity verification",
        []
    )

    print(f"ANNOUNCE message created:")
    print(f"  Type: {announce_msg['type']}")
    print(f"  Timestamp: {announce_msg['timestamp']}")
    print(f"  Signature: {announce_msg['signature'][:16]}...\n")

    # Connect to relay (production)
    relay_url = os.getenv("RELAY_URL", "wss://oo.openonion.ai/ws/announce")
    print(f"Connecting to {relay_url}...")
    ws = await relay.connect(relay_url)
    print("✓ Connected\n")

    # Send ANNOUNCE
    print("Sending ANNOUNCE...")
    await relay.send_announce(ws, announce_msg)
    print("✓ Sent\n")

    # Wait briefly to see if we get an error response
    print("Waiting for potential error response (2s timeout)...")
    try:
        response = await relay.wait_for_task(ws, timeout=2.0)
        print(f"✗ Received response: {response}")
    except asyncio.TimeoutError:
        print("✓ No error response (success!)\n")

    # Close connection
    await ws.close()
    print("Connection closed")
    print("\nNow verify agent appears in relay registry:")
    print(f"  GET /api/relay/agents")
    print(f"  Or query for: {addr_data['address']}")


if __name__ == "__main__":
    asyncio.run(test_announce())
