"""
Purpose: Ed25519 signature verification and trust-based authentication for hosted agents
LLM-Note:
  Dependencies: imports from [network/trust/, llm_do.py, nacl.signing] | imported by [network/host/routes.py, network/host/server.py] | tested by [tests/network/test_host_auth.py]
  Data flow: receives request dict with {payload, from, signature} → extract_and_authenticate() verifies Ed25519 signature via verify_signature() using nacl → checks timestamp expiry (5 min window) → applies trust policy (open/careful/strict/custom) → optionally evaluates via trust agent → returns (prompt, identity, sig_valid, error)
  State/Effects: reads trust settings from agent | calls trust agent for evaluation if custom policy | no persistent state
  Integration: exposes verify_signature(payload, signature, public_key) → bool, extract_and_authenticate(data, trust, blacklist, whitelist, agent_address) → (prompt, identity, sig_valid, error), get_agent_address(agent) → str, is_custom_trust(trust) → bool | used by host() to enforce authentication on all requests
  Performance: signature verification uses nacl (fast Ed25519) | 5 minute timestamp window prevents replay | whitelist bypass for trusted callers
  Errors: returns error strings: "unauthorized: ...", "forbidden: ...", "rejected: ..." | does NOT raise exceptions (caller checks error)
Authentication and signature verification for hosted agents.
"""

import hashlib
import json
import time

from ..trust import create_trust_agent, TRUST_LEVELS


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

    Trust levels control additional policies AFTER signature verification:
        - "open": Any valid signer allowed
        - "careful": Warnings for unknown signers (default)
        - "strict": Whitelist only
        - Custom policy/Agent: LLM evaluation

    Returns: (prompt, identity, sig_valid, error)
    """
    # Protocol requirement: ALL requests must be signed
    if "payload" not in data or "signature" not in data:
        return None, None, False, "unauthorized: signed request required"

    # Verify signature (protocol level - always required)
    prompt, identity, error = _authenticate_signed(
        data, blacklist=blacklist, whitelist=whitelist, agent_address=agent_address
    )
    if error:
        return prompt, identity, False, error

    # Trust level: additional policies AFTER signature verification
    if trust == "strict" and whitelist and identity not in whitelist:
        return None, identity, True, "forbidden: not in whitelist"

    # Custom trust policy/agent evaluation
    if is_custom_trust(trust):
        trust_agent = create_trust_agent(trust)
        accepted, reason = evaluate_with_trust_agent(trust_agent, prompt, identity, True)
        if not accepted:
            return None, identity, True, f"rejected: {reason}"

    return prompt, identity, True, None


def _authenticate_signed(data: dict, *, blacklist=None, whitelist=None, agent_address=None):
    """Authenticate signed request with Ed25519 - ALWAYS REQUIRED.

    Protocol-level signature verification. All requests must be signed.

    Returns: (prompt, identity, error) - error is None on success
    """
    payload = data.get("payload", {})
    identity = data.get("from")
    signature = data.get("signature")

    prompt = payload.get("prompt", "")
    timestamp = payload.get("timestamp")
    to_address = payload.get("to")

    # Check blacklist first
    if blacklist and identity in blacklist:
        return None, identity, "forbidden: blacklisted"

    # Check whitelist (bypass signature check - trusted caller)
    if whitelist and identity in whitelist:
        return prompt, identity, None

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

    # Verify signature
    if not verify_signature(payload, signature, identity):
        return None, identity, "unauthorized: invalid signature"

    return prompt, identity, None


def get_agent_address(agent) -> str:
    """Generate deterministic address from agent name."""
    h = hashlib.sha256(agent.name.encode()).hexdigest()
    return f"0x{h[:40]}"


def evaluate_with_trust_agent(trust_agent, prompt: str, identity: str, sig_valid: bool) -> tuple[bool, str]:
    """Evaluate request using a custom trust agent (policy or Agent).

    Only called when trust is a policy string or custom Agent - NOT for simple levels.

    Args:
        trust_agent: The trust agent created from policy or custom Agent
        prompt: The request prompt
        identity: The requester's identity/address
        sig_valid: Whether the signature is valid

    Returns:
        (accepted, reason) tuple
    """
    from pydantic import BaseModel
    from ...llm_do import llm_do

    class TrustDecision(BaseModel):
        accept: bool
        reason: str

    request_info = f"""Evaluate this request:
- prompt: {prompt[:200]}{'...' if len(prompt) > 200 else ''}
- identity: {identity or 'anonymous'}
- signature_valid: {sig_valid}"""

    decision = llm_do(
        request_info,
        output=TrustDecision,
        system_prompt=trust_agent.system_prompt,
    )
    return decision.accept, decision.reason


def is_custom_trust(trust) -> bool:
    """Check if trust needs a custom agent (policy or Agent, not a level)."""
    if not isinstance(trust, str):
        return True  # It's an Agent
    return trust not in TRUST_LEVELS  # It's a policy string
