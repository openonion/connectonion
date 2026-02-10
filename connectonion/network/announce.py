"""
Purpose: Build and sign ANNOUNCE messages for agent relay network registration
LLM-Note:
  Dependencies: imports from [json, time, typing, address.py, ifaddr, httpx] | imported by [host.py] | tested by [tests/test_announce.py]
  Data flow: receives from host() → create_announce_message(address_data, summary, endpoints) → builds message dict without signature → serializes to deterministic JSON (sort_keys=True) → calls address.sign() to create Ed25519 signature → returns signed message ready for relay
  State/Effects: get_ips() makes HTTP request to ipify (one-time) | pure function otherwise | deterministic JSON serialization (matches server verification) | signature is hex string without 0x prefix
  Integration: exposes get_ips(), create_announce_message(address_data, summary, endpoints) | used by host() to announce agent presence to relay network | relay server verifies signature using address (public key) | heartbeat re-sends with updated timestamp
  Performance: Ed25519 signing is fast (sub-millisecond) | get_ips() ~300-500ms for ipify call (runs once at startup)
  Errors: raises KeyError if address_data missing required keys | address.sign() errors bubble up | ipify timeout returns without public IP

Build ANNOUNCE messages for relay registration.

Simple function-based approach - no classes needed for MVP.
"""

import json
import time
from typing import Dict, List, Any

import ifaddr
import httpx


def get_ips() -> List[str]:
    """Get all IP addresses (localhost, local network, public)."""
    ips = ["localhost"]

    # Local IPs
    for adapter in ifaddr.get_adapters():
        for ip in adapter.ips:
            if isinstance(ip.ip, str) and not ip.ip.startswith('127.'):
                ips.append(ip.ip)

    # Public IP
    ips.append(httpx.get("https://api.ipify.org", timeout=5).text)

    return ips


def get_endpoints(port: int) -> List[str]:
    """Get all endpoints as full URLs (http and ws for each IP)."""
    endpoints = []
    for ip in get_ips():
        endpoints.append(f"http://{ip}:{port}")
        endpoints.append(f"ws://{ip}:{port}/ws")
    return endpoints


def create_announce_message(
    address_data: Dict[str, Any],
    summary: str,
    endpoints: List[str] = None,
    relay: str = None
) -> Dict[str, Any]:
    """
    Build and sign an ANNOUNCE message for relay registration.

    Args:
        address_data: Dictionary from address.load() or address.generate()
                     containing 'address' and 'signing_key'
        summary: Description of agent's capabilities (max 1000 chars)
        endpoints: List of direct connection URLs
                  Format: ["http://host:port", "ws://host:port/ws"]
        relay: Relay server URL for fallback connection
               Format: "wss://oo.openonion.ai"

    Returns:
        Dictionary ready to send to relay's /ws/announce endpoint:
        {
            "type": "ANNOUNCE",
            "address": "0x...",
            "timestamp": 1234567890,
            "summary": "...",
            "endpoints": ["http://localhost:8000", "ws://localhost:8000/ws"],
            "relay": "wss://oo.openonion.ai",
            "signature": "abc123..."
        }

    Example:
        >>> import address
        >>> addr = address.load()
        >>> msg = create_announce_message(
        ...     addr,
        ...     "Translator agent with 50+ languages",
        ...     ["http://127.0.0.1:8080", "ws://127.0.0.1:8080/ws"],
        ...     relay="wss://oo.openonion.ai"
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
        "endpoints": endpoints,
        "relay": relay
    }

    # Create deterministic JSON for signing
    # MUST match server's verification: json.dumps(message, sort_keys=True)
    message_json = json.dumps(message, sort_keys=True)
    message_bytes = message_json.encode('utf-8')

    # Sign with Ed25519
    from .. import address
    signature_bytes = address.sign(address_data, message_bytes)

    # Convert to hex string (NO 0x prefix - matches auth system convention)
    signature_hex = signature_bytes.hex()

    # Add signature to message
    message["signature"] = signature_hex

    return message
