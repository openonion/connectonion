"""
Purpose: Build and sign ANNOUNCE messages for agent relay network registration
LLM-Note:
  Dependencies: imports from [json, time, typing, address.py] | imported by [agent.py] | tested by [tests/test_announce.py]
  Data flow: receives from Agent.serve() → create_announce_message(address_data, summary, endpoints) → builds message dict without signature → serializes to deterministic JSON (sort_keys=True) → calls address.sign() to create Ed25519 signature → returns signed message ready for relay
  State/Effects: no side effects | pure function | deterministic JSON serialization (matches server verification) | signature is hex string without 0x prefix
  Integration: exposes create_announce_message(address_data, summary, endpoints) | used by Agent.serve() to announce agent presence to relay network | relay server verifies signature using address (public key) | heartbeat re-sends with updated timestamp
  Performance: Ed25519 signing is fast (sub-millisecond) | JSON serialization minimal overhead | no I/O or network calls
  Errors: raises KeyError if address_data missing required keys | address.sign() errors bubble up | no validation of summary length or endpoint format

Build ANNOUNCE messages for relay registration.

Simple function-based approach - no classes needed for MVP.
"""

import json
import time
from typing import Dict, List, Any


def create_announce_message(
    address_data: Dict[str, Any],
    summary: str,
    endpoints: List[str] = None
) -> Dict[str, Any]:
    """
    Build and sign an ANNOUNCE message for relay registration.

    Args:
        address_data: Dictionary from address.load() or address.generate()
                     containing 'address' and 'signing_key'
        summary: Description of agent's capabilities (max 1000 chars)
        endpoints: List of connection endpoints (optional, default=[])
                  Format: ["tcp://host:port"] or ["ws://host:port"]

    Returns:
        Dictionary ready to send to relay's /ws/announce endpoint:
        {
            "type": "ANNOUNCE",
            "address": "0x...",
            "timestamp": 1234567890,
            "summary": "...",
            "endpoints": [],
            "signature": "abc123..."
        }

    Example:
        >>> import address
        >>> addr = address.load()
        >>> msg = create_announce_message(
        ...     addr,
        ...     "Translator agent with 50+ languages",
        ...     ["tcp://127.0.0.1:8080"]
        ... )
        >>> # Now send msg through WebSocket to relay
    """
    if endpoints is None:
        endpoints = []

    # Build message WITHOUT signature first
    message = {
        "type": "ANNOUNCE",
        "address": address_data["address"],
        "timestamp": int(time.time()),
        "summary": summary,
        "endpoints": endpoints
    }

    # Create deterministic JSON for signing
    # MUST match server's verification: json.dumps(message, sort_keys=True)
    message_json = json.dumps(message, sort_keys=True)
    message_bytes = message_json.encode('utf-8')

    # Sign with Ed25519
    from . import address
    signature_bytes = address.sign(address_data, message_bytes)

    # Convert to hex string (NO 0x prefix - matches auth system convention)
    signature_hex = signature_bytes.hex()

    # Add signature to message
    message["signature"] = signature_hex

    return message
