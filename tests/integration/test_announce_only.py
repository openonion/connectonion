#!/usr/bin/env python3
"""
Simple test: Just connect and send ANNOUNCE once.

Tests connectivity without waiting for heartbeat or tasks.
"""

import sys
import asyncio
import pytest
sys.path.insert(0, '/Users/changxing/project/OnCourse/platform/connectonion-network')

from pathlib import Path
from connectonion import address, announce, relay


@pytest.mark.asyncio
async def test_announce():
    """Test that we can connect and announce successfully."""
    print("=== Testing Client ANNOUNCE ===\n")

    # Generate or load keys
    co_dir = Path('/Users/changxing/project/OnCourse/platform/connectonion-network/.co')
    addr_data = address.load(co_dir)

    if addr_data is None:
        print("Generating new keys...")
        addr_data = address.generate()
        address.save(addr_data, co_dir)
        print(f"✓ Keys saved\n")

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

    # Connect to relay
    print("Connecting to ws://localhost:8000/ws/announce...")
    ws = await relay.connect("ws://localhost:8000/ws/announce")
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
