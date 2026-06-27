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
import os
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
    domain = os.getenv("AGENT_PUBLIC_DOMAIN", "").strip().rstrip("/")
    if domain:
        return [f"https://{domain}", f"wss://{domain}/ws"]

    endpoints = []
    for ip in get_ips():
        endpoints.append(f"http://{ip}:{port}")
        endpoints.append(f"ws://{ip}:{port}/ws")
    return endpoints


def create_announce_message(
    address_data: Dict[str, Any],
    summary: str,
    endpoints: List[str] = None,
    relay: str = None,
    profile: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Build and sign an ANNOUNCE message for relay registration.

    Args:
        address_data: dict from address.load()/generate() with 'address' + 'signing_key'
        summary: agent capability description (max 1000 chars)
        endpoints: direct connection URLs (http://host:port, ws://host:port/ws)
        relay: relay fallback URL (e.g. "wss://oo.openonion.ai")
        profile: optional publishable display profile. Shape varies by producer —
                 host() sends {alias, tools, model, skills: [{name, description}]} and
                 never inlines skill bodies; `co announce` sends {alias, bio, version,
                 skills: [{name, description, body?}]}, inlining a SKILL.md body per skill
                 gated by `publish: true`. When present, the signature covers it atomically
                 so the relay can trust the metadata (and any inlined bodies).

    Returns:
        Signed ANNOUNCE message ready to send to /ws/announce.
    """
    if endpoints is None:
        endpoints = []

    message = {
        "type": "ANNOUNCE",
        "address": address_data["address"],
        "timestamp": int(time.time()),
        "summary": summary,
        "endpoints": endpoints,
        "relay": relay,
    }
    if profile is not None:
        message["profile"] = profile

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
