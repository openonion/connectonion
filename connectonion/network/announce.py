"""
Purpose: Build and sign ANNOUNCE messages for agent relay network registration
LLM-Note:
  Dependencies: imports from [json, time, typing, address.py, ifaddr, httpx] | imported by [host.py] | tested by [tests/unit/test_announce.py]
  Data flow: receives from host() → create_announce_message(address_data, summary, endpoints) → builds message dict without signature → serializes to deterministic JSON (sort_keys=True) → calls address.sign() to create Ed25519 signature → returns signed message ready for relay
  State/Effects: get_ips() makes HTTP request to ipify (one-time) | pure function otherwise | deterministic JSON serialization (matches server verification) | signature is hex string without 0x prefix
  Integration: exposes get_ips(), create_announce_message(address_data, summary, endpoints) | used by host() to announce agent presence to relay network | relay server verifies signature using address (public key) | heartbeat re-sends with updated timestamp
  Performance: Ed25519 signing is fast (sub-millisecond) | get_ips() ~300-500ms for ipify call (runs once at startup)
  Errors: raises KeyError if address_data missing required keys | address.sign() errors bubble up | any ipify failure (timeout, DNS, 5xx) returns the local addresses without a public one — it used to raise out of get_endpoints() into host startup, which this line already claimed it did not

Build ANNOUNCE messages for relay registration.

Simple function-based approach - no classes needed for MVP.
"""

import json
import os
import time
from typing import Dict, List, Any

import ifaddr
import httpx


# The relay's limit, stated here because this is where the message is built.
# Verified against the live relay: 5,400 characters comes back as
# {"type": "ERROR", "error": "Summary too long (max 1000 chars)"} while a short
# one gets ANNOUNCE_OK.
ANNOUNCE_SUMMARY_LIMIT = 1000

# The summary we last mentioned cutting, so a reconnect does not repeat it.
_summary_already_mentioned = None


def fit_summary(summary):
    """Cut a summary to what the relay will accept, and say so when it does.

    host() already truncates the summary it derives from the system prompt, but
    passed a `summary:` from host.yaml through whole — so an operator who wrote
    a long one got an agent that starts, serves locally, and is never
    registered: the relay refuses every announce and the reconnect loop retries
    forever.

    Not silent — the client prints `Relay error: …` — but it scrolls past in
    startup output beside a banner that still says the relay is on. The number
    is knowable here, so it is applied here, and the operator is told what was
    actually sent instead of matching a red line against a config file.
    """
    if not summary or len(summary) <= ANNOUNCE_SUMMARY_LIMIT:
        return summary

    # Said once per summary, not once per announce. This function is the relay
    # loop's callback — the message is rebuilt on every reconnect, deliberately,
    # because it is signed and has to be fresh for the socket it announces on
    # (#548). Printing here on every network blip fills the log with one line
    # and teaches the operator to stop reading it. A changed summary is news
    # again: host.yaml was edited.
    global _summary_already_mentioned
    if _summary_already_mentioned != summary:
        _summary_already_mentioned = summary
        print(f"[announce] summary is {len(summary)} characters and the relay takes "
              f"{ANNOUNCE_SUMMARY_LIMIT}; announcing the first {ANNOUNCE_SUMMARY_LIMIT}. "
              f"Shorten `summary:` in .co/host.yaml to choose what goes.")
    return summary[:ANNOUNCE_SUMMARY_LIMIT]


def get_ips() -> List[str]:
    """Get all IP addresses (localhost, local network, public)."""
    ips = ["localhost"]

    # Local IPs
    for adapter in ifaddr.get_adapters():
        for ip in adapter.ips:
            if isinstance(ip.ip, str) and not ip.ip.startswith('127.'):
                ips.append(ip.ip)

    # Public IP, from a third party, which is the one address this project cannot
    # work out for itself. Everything above is already collected, and those are
    # what a neighbour on the same LAN would use — so a service on the internet
    # being briefly unavailable must not cost the agent every endpoint it has.
    # ipify was answering 520 when this was written; unguarded, that raised out
    # of get_endpoints() and into host startup.
    #
    # This is the exception to fail-fast: losing the public address costs
    # reachability from outside NAT, losing the list costs the agent entirely.
    try:
        public_ip = httpx.get("https://api.ipify.org", timeout=5).text.strip()
    except Exception:
        public_ip = ""
    if public_ip:
        ips.append(public_ip)

    return ips


def _is_loopback(host: str) -> bool:
    """Whether this address only means anything on the machine that has it."""
    if host in ("localhost", "::1"):
        return True
    return host.startswith("127.")


def get_endpoints(port: int) -> List[str]:
    """Get all endpoints as full URLs (http and ws for each IP)."""
    domain = os.getenv("AGENT_PUBLIC_DOMAIN", "").strip().rstrip("/")
    if domain:
        return [f"https://{domain}", f"wss://{domain}/ws"]

    endpoints = []
    for ip in get_ips():
        if _is_loopback(ip):
            # Not a place another machine can go, and the relay record is read
            # by other machines. Published, it made a browser client walking the
            # list probe port `port` on *the reader's own* machine — the address
            # check was the only thing that stopped it talking to whatever
            # answered. Fixed on the client side in @connectonion/react 0.3.2;
            # this is the same bug at the source.
            #
            # Private addresses are deliberately kept: two agents in one VPC or
            # on one LAN can use them, and the relay would otherwise carry a
            # connection that did not need it.
            continue
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
        "summary": fit_summary(summary),
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
