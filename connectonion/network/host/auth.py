"""
Purpose: Ed25519 signature verification and trust-based authentication for hosted agents
LLM-Note:
  Dependencies: imports from [network/trust/TrustAgent, nacl.signing] | imported by [network/host/http_router.py, network/host/server.py, network/host/ws_router/connect.py] | tested by [tests/unit/test_host_auth.py]
  Data flow: receives request dict with {payload, from, signature} → extract_and_authenticate() verifies Ed25519 signature → uses TrustAgent.should_allow() for trust decisions (fast rules + LLM fallback) → returns (prompt, agent_address, sig_valid, error)
  State/Effects: TrustAgent handles all trust state (whitelist, contacts, blocklist in ~/.co/)
  Integration: exposes verify_signature(), extract_and_authenticate(), get_agent_address(), is_custom_trust() | used by host() to enforce authentication
  Performance: TrustAgent.should_allow() runs fast rules first (zero tokens), only uses LLM for 'ask' cases
  Errors: returns error strings: "unauthorized: ...", "forbidden: ...", "misconfigured: ..." (a trust list the agent cannot read) | does NOT raise exceptions
Authentication and signature verification for hosted agents.

Trust evaluation (via TrustAgent.should_allow()):
1. Parameter whitelist (highest priority, instant allow)
2. Signature verification (protocol level)
3. TrustAgent handles fast rules + LLM fallback
"""

import hashlib
import json
import time
from typing import Dict

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


def extract_and_authenticate(data: dict, trust, *, blacklist=None, whitelist=None, recipient_address=None):
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

    Returns: (prompt, agent_address, sig_valid, error)
    """
    # Protocol requirement: ALL requests must be signed
    if "payload" not in data or "signature" not in data:
        return None, None, False, "unauthorized: signed request required"

    # Verify signature (protocol level - always required, even for whitelisted)
    prompt, agent_address, error = _authenticate_signed(
        data, blacklist=blacklist, recipient_address=recipient_address
    )
    if error:
        return prompt, agent_address, False, error

    # Parameter whitelist bypasses trust POLICY (not signature verification)
    if whitelist and agent_address in whitelist:
        return prompt, agent_address, True, None

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

    # A trust list this agent cannot read raises rather than answering "not
    # blocked" (#585). That is right, and it needs an exit here: the WebSocket
    # session loop lets exceptions propagate out, so an unhandled one closes the
    # socket with nothing sent — the client sees a connection that died and no
    # reason, which is #434 arriving by a new route.
    #
    # This module's contract is to return error strings, so it keeps it: refuse,
    # name the file, and let the ERROR frame carry it to whoever is holding the
    # other end. Fail closed, and say why.
    try:
        decision = trust_agent.should_allow(agent_address, request_data)
    except (OSError, UnicodeDecodeError) as exc:
        return None, agent_address, True, f"misconfigured: {exc}"

    if decision.allow:
        return prompt, agent_address, True, None
    else:
        return None, agent_address, True, f"forbidden: {decision.reason}"


# ─────────────────────────── signed GETs ───────────────────────────
#
# A GET has no body to sign, so `curl http://agent/sessions` returned every
# conversation on the agent -- prompts, answers and full message history -- to
# anyone who could reach the port (#683). It is also where #696's attack got
# its session ids.
#
# The signature travels in headers over {method, path, timestamp}, canonicalised
# exactly as CONNECT and INPUT already are, and is then verified by the same
# _authenticate_signed below. One canonicalisation, one freshness window, one
# blacklist check -- a second implementation of any of those is how the halves
# of a gate drift apart, which is most of what this release has been about.

FROM_HEADER = "x-co-from"
SIGNATURE_HEADER = "x-co-signature"
TIMESTAMP_HEADER = "x-co-timestamp"


def _canonical(payload: dict) -> bytes:
    """The bytes that get signed. Same shape as connect.py's."""
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()


def sign_request(keys: dict, method: str, path: str, timestamp=None) -> dict:
    """Headers a client sends with a signed GET.

    Exported so a client does not have to reconstruct the format -- and so the
    tests drive the real one rather than certifying their own idea of it.
    """
    from ... import address as _address

    payload = {"method": method.upper(), "path": path,
               "timestamp": int(timestamp if timestamp is not None else time.time())}
    return {
        FROM_HEADER: keys["address"],
        SIGNATURE_HEADER: _address.sign(keys, _canonical(payload)).hex(),
        TIMESTAMP_HEADER: str(payload["timestamp"]),
    }


def request_from_headers(headers: dict, method: str, path: str) -> dict:
    """Turn a signed GET into the dict every other authenticated frame is.

    The payload is rebuilt from the *actual* method and path, not from anything
    the client sent, so a signature made for one path does not verify against
    another.
    """
    lowered = {str(k).lower(): v for k, v in (headers or {}).items()}
    timestamp = lowered.get(TIMESTAMP_HEADER)
    return {
        "payload": {"method": method.upper(), "path": path,
                    "timestamp": int(timestamp) if timestamp is not None else None},
        "from": lowered.get(FROM_HEADER),
        "signature": lowered.get(SIGNATURE_HEADER),
    }


# ─────────────────────────── replay ───────────────────────────
#
# In protocol v1, EXEC carried no signature of its own: the signature authenticated
# the connection and every command on it was trusted because of who opened it. A
# captured CONNECT could therefore be replayed and followed by attacker-authored
# EXEC frames (#649, measured).
#
# One signature opens one connection. The attack has to *open* one; without a
# MITM position an attacker cannot inject into somebody else's live socket.
#
# Legitimate clients are unaffected: each builds a fresh CONNECT with a fresh
# timestamp, and the one place this codebase re-establishes a connection
# deliberately does not replay the frame -- see ws_router/connect.py, "no
# CONNECT replay, its signature may have aged past the 5-minute window".
#
# Protocol v2 advertises per-command signatures inside the signed CONNECT. Its
# commands include type, recipient and a random nonce in their signed payload;
# v1 remains accepted so an upgraded host does not strand an older client.

_seen_signatures: Dict[str, float] = {}


def signature_already_used(data: dict) -> bool:
    """True if this exact signature has opened a connection already.

    Records it if not. Entries past the freshness window are dropped as we go:
    they cannot be replayed anyway, so keeping them is memory the agent never
    gets back.
    """
    signature = data.get("signature")
    if not signature:
        return False          # refused by the signature check itself

    now = time.time()
    for old in [sig for sig, seen in _seen_signatures.items()
                if now - seen > SIGNATURE_EXPIRY_SECONDS]:
        del _seen_signatures[old]

    if signature in _seen_signatures:
        return True
    _seen_signatures[signature] = now
    return False


def authenticated_command_payload(
    data: dict, expected_address: str, expected_recipient: str = None
):
    """Return a verified command payload bound to the connected caller.

    CONNECT authenticates the socket. Protocol-v2 clients additionally sign
    every command with its type and a random nonce, so possession or injection
    into that socket is not enough to invent a different command.
    """
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None, "unauthorized: signed command required"

    _, caller, error = _authenticate_signed(
        data, recipient_address=expected_recipient
    )
    if error:
        return None, error
    if caller != expected_address:
        return None, "unauthorized: command signer does not own this connection"
    if payload.get("type") != data.get("type"):
        return None, "unauthorized: signed command type mismatch"
    nonce = payload.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        return None, "unauthorized: signed command nonce required"
    if signature_already_used(data):
        return None, "unauthorized: signed command already used"
    return payload, None


def _authenticate_signed(data: dict, *, blacklist=None, recipient_address=None):
    """Authenticate signed request with Ed25519 - ALWAYS REQUIRED.

    Protocol-level signature verification. All requests must be signed.
    Whitelist is NOT checked here - it bypasses trust policy, not signature.

    Returns: (prompt, agent_address, error) - error is None on success
    """
    payload = data.get("payload", {})
    agent_address = data.get("from")
    signature = data.get("signature")

    prompt = payload.get("prompt", "")
    timestamp = payload.get("timestamp")
    to_address = payload.get("to")

    # Check blacklist first (security: even before signature check)
    if blacklist and agent_address in blacklist:
        return None, agent_address, "forbidden: blacklisted"

    # Validate required fields
    if not agent_address:
        return None, None, "unauthorized: 'from' field required"
    if not signature:
        return None, agent_address, "unauthorized: signature required"
    if not timestamp:
        return None, agent_address, "unauthorized: timestamp required in payload"
    if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool):
        return None, agent_address, "unauthorized: timestamp must be numeric"

    # Check timestamp expiry (5 minute window)
    now = time.time()
    if abs(now - timestamp) > SIGNATURE_EXPIRY_SECONDS:
        return None, agent_address, "unauthorized: signature expired"

    # When the caller supplies the host address, the signed payload must name
    # that exact recipient. Treating a missing ``to`` as acceptable would let
    # the same otherwise-valid command be replayed against a different host,
    # whose replay cache is necessarily independent.
    if recipient_address and to_address != recipient_address:
        return None, agent_address, "unauthorized: wrong recipient"

    # Verify signature ALWAYS (no whitelist bypass - that's at policy level)
    if not verify_signature(payload, signature, agent_address):
        return None, agent_address, "unauthorized: invalid signature"

    return prompt, agent_address, None


def get_agent_address(agent) -> str:
    """Generate deterministic address from agent name."""
    h = hashlib.sha256(agent.name.encode()).hexdigest()
    return f"0x{h[:40]}"


def is_custom_trust(trust) -> bool:
    """Check if trust needs a custom agent (policy or Agent, not a level)."""
    if not isinstance(trust, str):
        return True  # It's an Agent
    return trust not in TRUST_LEVELS  # It's a policy string
