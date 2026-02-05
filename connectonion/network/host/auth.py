"""
Purpose: Ed25519 signature verification and trust-based authentication for hosted agents
LLM-Note:
  Dependencies: imports from [network/trust/TrustAgent, nacl.signing] | imported by [network/host/routes.py, network/host/server.py] | tested by [tests/unit/test_host_auth.py]
  Data flow: receives request dict with {payload, from, signature} → extract_and_authenticate() verifies Ed25519 signature → uses TrustAgent.should_allow() for trust decisions (fast rules + LLM fallback) → returns (prompt, identity, sig_valid, error)
  State/Effects: TrustAgent handles all trust state (whitelist, contacts, blocklist in ~/.co/)
  Integration: exposes verify_signature(), extract_and_authenticate(), get_agent_address(), is_custom_trust() | used by host() to enforce authentication
  Performance: TrustAgent.should_allow() runs fast rules first (zero tokens), only uses LLM for 'ask' cases
  Errors: returns error strings: "unauthorized: ...", "forbidden: ..." | does NOT raise exceptions
Authentication and signature verification for hosted agents.

Trust evaluation (via TrustAgent.should_allow()):
1. Parameter whitelist (highest priority, instant allow)
2. Signature verification (protocol level)
3. TrustAgent handles fast rules + LLM fallback
"""

import hashlib
import json
import time

from ..trust import TrustAgent, TRUST_LEVELS


# Signature expiry window (5 minutes)
SIGNATURE_EXPIRY_SECONDS = 300


def verify_signature(payload: dict, signature: str, public_key: str) -> bool:
    """Verify Ed25519 signature.

    Args:
        payload: The payload that was signed
        signature: Hex-encoded signature (with or without 0x prefix)
        public_key: Hex-encoded public key (with or without 0x prefix)

    Returns:
        True if signature is valid, False otherwise
    """
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError

    # Remove 0x prefix if present
    sig_hex = signature[2:] if signature.startswith("0x") else signature
    key_hex = public_key[2:] if public_key.startswith("0x") else public_key

    # Canonicalize payload (deterministic JSON)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    try:
        verify_key = VerifyKey(bytes.fromhex(key_hex))
        verify_key.verify(canonical.encode(), bytes.fromhex(sig_hex))
        return True
    except (BadSignatureError, ValueError):
        # BadSignatureError: invalid signature
        # ValueError: invalid hex encoding
        return False


def extract_and_authenticate(data: dict, trust, *, blacklist=None, whitelist=None, agent_address=None):
    """Extract prompt and authenticate request.

    ALL requests must be signed - this is a protocol requirement.

    Required format (Ed25519 signed):
        {
            "payload": {"prompt": "...", "to": "0xAgentAddress", "timestamp": 123},
            "from": "0xCallerPublicKey",
            "signature": "0xEd25519Signature..."
        }

    Onboarding (in payload):
        {
            "payload": {"prompt": "...", "invite_code": "BETA2024", ...}
        }
        or:
        {
            "payload": {"prompt": "...", "payment": 10, ...}
        }

    Authentication flow:
        1. Signature verification (protocol level, always required)
        2. Parameter whitelist check (instant allow if match)
        3. Fast rules from YAML config:
           - allow: [whitelisted, contact]  → instant allow
           - deny: [blocked]                → instant deny
           - onboard: {invite_code, payment} → promote stranger to contact
           - default: allow | deny | ask    → final decision
        4. Trust agent (only if fast rules return None for 'ask' cases)

    Trust levels (predefined YAML configs):
        - "open": default=allow (development)
        - "careful": default=ask (staging)
        - "strict": allow=[whitelisted], default=deny (production)
        - Custom policy/Agent: LLM evaluation

    Returns: (prompt, identity, sig_valid, error)
    """
    # Protocol requirement: ALL requests must be signed
    if "payload" not in data or "signature" not in data:
        return None, None, False, "unauthorized: signed request required"

    # Verify signature (protocol level - always required, even for whitelisted)
    prompt, identity, error = _authenticate_signed(
        data, blacklist=blacklist, agent_address=agent_address
    )
    if error:
        return prompt, identity, False, error

    # Parameter whitelist bypasses trust POLICY (not signature verification)
    if whitelist and identity in whitelist:
        return prompt, identity, True, None

    # Use TrustAgent for all trust decisions (fast rules + LLM fallback)
    payload = data.get("payload", {})
    request_data = {
        "prompt": prompt,
        "invite_code": payload.get("invite_code"),
        "payment": payload.get("payment", 0),
    }

    # Trust should be TrustAgent (resolved by host/create_app)
    # But handle string for backwards compatibility with direct calls
    if isinstance(trust, TrustAgent):
        trust_agent = trust
    elif isinstance(trust, str):
        trust_agent = TrustAgent(trust)
    else:
        # Unknown type (e.g., Agent) - use default "careful"
        trust_agent = TrustAgent("careful")

    decision = trust_agent.should_allow(identity, request_data)

    if decision.allow:
        return prompt, identity, True, None
    else:
        return None, identity, True, f"forbidden: {decision.reason}"


def _authenticate_signed(data: dict, *, blacklist=None, agent_address=None):
    """Authenticate signed request with Ed25519 - ALWAYS REQUIRED.

    Protocol-level signature verification. All requests must be signed.
    Whitelist is NOT checked here - it bypasses trust policy, not signature.

    Returns: (prompt, identity, error) - error is None on success
    """
    payload = data.get("payload", {})
    identity = data.get("from")
    signature = data.get("signature")

    prompt = payload.get("prompt", "")
    timestamp = payload.get("timestamp")
    to_address = payload.get("to")

    # Check blacklist first (security: even before signature check)
    if blacklist and identity in blacklist:
        return None, identity, "forbidden: blacklisted"

    # Validate required fields
    if not identity:
        return None, None, "unauthorized: 'from' field required"
    if not signature:
        return None, identity, "unauthorized: signature required"
    if not timestamp:
        return None, identity, "unauthorized: timestamp required in payload"

    # Check timestamp expiry (5 minute window)
    now = time.time()
    if abs(now - timestamp) > SIGNATURE_EXPIRY_SECONDS:
        return None, identity, "unauthorized: signature expired"

    # Optionally verify 'to' matches agent address
    if agent_address and to_address and to_address != agent_address:
        return None, identity, "unauthorized: wrong recipient"

    # Verify signature ALWAYS (no whitelist bypass - that's at policy level)
    if not verify_signature(payload, signature, identity):
        return None, identity, "unauthorized: invalid signature"

    return prompt, identity, None


def get_agent_address(agent) -> str:
    """Generate deterministic address from agent name."""
    h = hashlib.sha256(agent.name.encode()).hexdigest()
    return f"0x{h[:40]}"


def is_custom_trust(trust) -> bool:
    """Check if trust needs a custom agent (policy or Agent, not a level)."""
    if not isinstance(trust, str):
        return True  # It's an Agent
    return trust not in TRUST_LEVELS  # It's a policy string
