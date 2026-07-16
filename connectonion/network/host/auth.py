"""
Purpose: Ed25519 signature verification and trust-based authentication for hosted agents
LLM-Note:
  Dependencies: imports from [network/trust/TrustAgent, nacl.signing] | imported by [network/host/http_router.py, network/host/server.py, network/host/ws_router/connect.py] | tested by [tests/unit/test_host_auth.py]
  Data flow: receives request dict with {payload, from, signature} → extract_and_authenticate() verifies Ed25519 signature → uses TrustAgent.should_allow() for trust decisions (fast rules + LLM fallback) → returns (prompt, agent_address, sig_valid, error)
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
import math
import time

from ..trust import TrustAgent, TRUST_LEVELS


# Signature expiry window (5 minutes)
SIGNATURE_EXPIRY_SECONDS = 300
MAX_REQUEST_ID_LENGTH = 128
MAX_SESSION_ID_LENGTH = 256
VALID_INPUT_MODES = frozenset({"safe", "plan", "accept_edits", "ulw"})


def _canonical_sha256(value) -> str:
    """Return a deterministic SHA-256 digest for JSON-compatible data."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def canonical_attachments_sha256(images=None, files=None) -> str:
    """Bind relay-visible attachments to a signed INPUT payload."""
    return _canonical_sha256({"images": images or [], "files": files or []})


def canonical_session_sha256(session=None) -> str:
    """Bind a client-provided conversation snapshot to CONNECT/HTTP auth."""
    return _canonical_sha256({} if session is None else session)


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

    decision = trust_agent.should_allow(agent_address, request_data)

    if decision.allow:
        return prompt, agent_address, True, None
    else:
        return None, agent_address, True, f"forbidden: {decision.reason}"


def _authenticate_signed(data: dict, *, blacklist=None, recipient_address=None):
    """Authenticate signed request with Ed25519 - ALWAYS REQUIRED.

    Protocol-level signature verification. All requests must be signed.
    Whitelist is NOT checked here - it bypasses trust policy, not signature.

    Returns: (prompt, agent_address, error) - error is None on success
    """
    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        return None, None, "unauthorized: payload must be an object"
    agent_address = data.get("from")
    signature = data.get("signature")

    prompt = payload.get("prompt", "")
    timestamp = payload.get("timestamp")
    to_address = payload.get("to")

    # CONNECT carries its routing session_id at the top level.  New clients
    # bind that value into the signed payload as well; reject any disagreement
    # so a valid signature cannot be replayed against a different session.
    # A top-level id with no payload id is accepted for legacy clients, but the
    # WS layer marks that id as unbound and will not restore capabilities from it.
    if data.get("type") == "CONNECT" and "session_id" in payload:
        signed_session_id = payload.get("session_id")
        if not isinstance(signed_session_id, str) or not signed_session_id:
            return None, agent_address, "unauthorized: invalid session_id in payload"
        if len(signed_session_id) > MAX_SESSION_ID_LENGTH:
            return None, agent_address, "unauthorized: session_id is too long"
        if data.get("session_id") != signed_session_id:
            return None, agent_address, "unauthorized: session_id mismatch"

    # Explicit WS INPUT mode is a capability control, so it must be bound to
    # the per-frame signature rather than trusted from the relay-visible top
    # level.  The WS router verifies mode-bearing INPUT frames with this helper.
    if data.get("type") == "INPUT" and "mode" in data:
        if "mode" not in payload:
            return None, agent_address, "unauthorized: signed mode required"
        if data.get("mode") != payload.get("mode"):
            return None, agent_address, "unauthorized: mode mismatch"
    if data.get("type") == "INPUT" and (
        "session_id" in data or "session_id" in payload
    ):
        signed_session_id = payload.get("session_id")
        if not isinstance(signed_session_id, str) or not signed_session_id:
            return None, agent_address, "unauthorized: signed session_id required"
        if data.get("session_id") != signed_session_id:
            return None, agent_address, "unauthorized: session_id mismatch"
    if (data.get("type") == "INPUT" and "prompt" in data
            and payload.get("prompt") != data.get("prompt")):
        return None, agent_address, "unauthorized: prompt mismatch"

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
    if (not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool)
            or not math.isfinite(timestamp)):
        return None, agent_address, "unauthorized: timestamp must be numeric"

    # Check timestamp expiry (5 minute window)
    now = time.time()
    if abs(now - timestamp) > SIGNATURE_EXPIRY_SECONDS:
        return None, agent_address, "unauthorized: signature expired"

    # Reject an explicitly different audience.  Modern CONNECT/INPUT/GET
    # validators separately require `to`; keeping missing `to` compatible here
    # avoids breaking legacy admin and onboarding frames, which never carried
    # an audience and cannot restore modern session capabilities.
    if recipient_address and to_address and to_address != recipient_address:
        return None, agent_address, "unauthorized: wrong recipient"

    # Verify signature ALWAYS (no whitelist bypass - that's at policy level)
    if not verify_signature(payload, signature, agent_address):
        return None, agent_address, "unauthorized: invalid signature"

    return prompt, agent_address, None


def authenticate_bound_input(
    data: dict,
    *,
    recipient_address: str | None,
    expected_session_id: str,
):
    """Validate a modern INPUT whose routing data is fully signature-bound.

    Returns ``(binding, error)``.  ``(None, None)`` means an older or
    signature-stripped frame: callers may execute it only as an unprivileged
    safe turn.  A non-None error means a frame claimed to be modern but one of
    its signed/top-level values disagreed, so it must be rejected rather than
    silently downgraded.
    """
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None, None

    request_field = _request_id_field(data, payload)
    required_payload = {
        "action", "prompt", "to", "timestamp", "session_id",
        "attachments_sha256",
    }
    required_top = {"prompt", "to", "session_id"}
    complete = (
        required_payload.issubset(payload)
        and required_top.issubset(data)
        and request_field is not None
        and request_field in payload
        and request_field in data
        and bool(data.get("from"))
        and bool(data.get("signature"))
    )
    if not complete:
        return None, None

    if data.get("type") not in (None, "INPUT"):
        return None, "unauthorized: wrong message type"

    prompt, agent_address, error = _authenticate_signed(
        data, recipient_address=recipient_address
    )
    if error:
        return None, error

    if payload.get("action") != "session.input":
        return None, "unauthorized: wrong signed action"

    if data.get("to") != payload.get("to"):
        return None, "unauthorized: recipient mismatch"
    if recipient_address and data.get("to") != recipient_address:
        return None, "unauthorized: wrong recipient"
    if data.get("prompt") != prompt:
        return None, "unauthorized: prompt mismatch"
    if not isinstance(prompt, str) or not prompt:
        return None, "prompt must be a non-empty string"

    signed_session_id = payload.get("session_id")
    if (
        not isinstance(signed_session_id, str)
        or not signed_session_id
        or len(signed_session_id) > MAX_SESSION_ID_LENGTH
        or data.get("session_id") != signed_session_id
        or expected_session_id != signed_session_id
    ):
        return None, "unauthorized: INPUT session_id mismatch"

    request_id = payload.get(request_field)
    if (
        not isinstance(request_id, str)
        or not request_id
        or len(request_id) > MAX_REQUEST_ID_LENGTH
        or data.get(request_field) != request_id
    ):
        return None, f"unauthorized: {request_field} mismatch"

    if "input_id" in data and "request_id" in data:
        if data["input_id"] != data["request_id"]:
            return None, "unauthorized: request id mismatch"
    if "input_id" in payload and "request_id" in payload:
        if payload["input_id"] != payload["request_id"]:
            return None, "unauthorized: request id mismatch"

    expected_attachments = canonical_attachments_sha256(
        data.get("images"), data.get("files")
    )
    if payload.get("attachments_sha256") != expected_attachments:
        return None, "unauthorized: attachments mismatch"

    top_has_mode = "mode" in data
    payload_has_mode = "mode" in payload
    if top_has_mode != payload_has_mode or (
        top_has_mode and data.get("mode") != payload.get("mode")
    ):
        return None, "unauthorized: mode mismatch"
    mode = payload.get("mode") if payload_has_mode else None
    if mode is not None and not isinstance(mode, str):
        return None, "mode must be a string"
    if mode is not None and mode not in VALID_INPUT_MODES:
        return None, "unsupported mode"

    return {
        "agent_address": agent_address,
        "prompt": prompt,
        "session_id": signed_session_id,
        "request_id": request_id,
        "timestamp": payload["timestamp"],
        "mode": mode,
    }, None


def _request_id_field(data: dict, payload: dict) -> str | None:
    """Choose the protocol request-id key without accepting aliases loosely."""
    if "input_id" in data or "input_id" in payload:
        return "input_id"
    if "request_id" in data or "request_id" in payload:
        return "request_id"
    return None


def get_agent_address(agent) -> str:
    """Generate deterministic address from agent name."""
    h = hashlib.sha256(agent.name.encode()).hexdigest()
    return f"0x{h[:40]}"


def is_custom_trust(trust) -> bool:
    """Check if trust needs a custom agent (policy or Agent, not a level)."""
    if not isinstance(trust, str):
        return True  # It's an Agent
    return trust not in TRUST_LEVELS  # It's a policy string
