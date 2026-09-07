"""Encrypted SMS inbox tools for ConnectOnion agents.

Ciphertext is fetched from oo-api and decrypted in this process with the
project's Ed25519 identity converted to X25519. SMS content is untrusted input;
these helpers return it as data and never execute it as an instruction.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlparse
import uuid
from uuid import UUID

import requests
from nacl.exceptions import CryptoError
from nacl.public import SealedBox

from ..backend import backend_url
from ..credentials import require_ambient_api_key
from ..project import project_identity


ALGORITHM = "x25519-xsalsa20-poly1305-sealed-box"
PAIRING_VERSION = 2
PAIRING_PURPOSE = "openonion-sms-pair"
ACTIVATION_PURPOSE = "openonion-sms-activate"
MIN_SMS = 1
MAX_SMS = 100


def create_sms_pairing(expires_in_seconds: int = 600) -> dict[str, Any]:
    """Create an Agent-signed one-time Android pairing grant.

    Args:
        expires_in_seconds: Link lifetime, from 60 through 1800 seconds.

    Returns:
        Pairing metadata including ``pairing_link``. Treat the link as a secret
        until it has been claimed by the intended phone.
    """
    if (
        isinstance(expires_in_seconds, bool)
        or not isinstance(expires_in_seconds, int)
        or not 60 <= expires_in_seconds <= 1800
    ):
        raise ValueError("expires_in_seconds must be between 60 and 1800")
    identity = _identity()
    pairing_id = uuid.uuid4()
    nonce = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    expires_at = int(time.time()) + expires_in_seconds
    grant = _canonical_pairing_grant(
        pairing_id,
        identity["address"],
        nonce,
        expires_at,
    )
    signature = identity["signing_key"].sign(grant.encode()).signature.hex()
    response = requests.post(
        f"{backend_url()}/api/v1/sms/pairings/v2",
        json={
            "pairing_id": str(pairing_id),
            "recipient": identity["address"],
            "nonce": nonce,
            "expires_at": expires_at,
            "signature": signature,
        },
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def get_sms_pairing(pairing_id: str) -> dict[str, Any]:
    """Return non-secret status for one pairing owned by this Agent."""
    pairing_id = _uuid(pairing_id, "pairing_id")
    response = requests.get(
        f"{backend_url()}/api/v1/sms/pairings/{pairing_id}",
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def pairing_confirmation_code(pairing_link: str, device_public_key: str) -> str:
    """Compute the six digits that must match the Android display."""
    grant = _grant_from_link(pairing_link)
    try:
        device_key = base64.b64decode(device_public_key, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("device_public_key must be canonical base64") from exc
    digest = hashlib.sha256(grant.encode() + b"\x00" + device_key).digest()
    return f"{int.from_bytes(digest[:4], 'big') % 1_000_000:06d}"


def confirm_sms_pairing(
    pairing_id: str,
    pairing_link: str,
    device_public_key: str,
    confirmation_code: str,
) -> bool:
    """Approve the exact Android key after the human compares both codes."""
    pairing_id = _uuid(pairing_id, "pairing_id")
    parsed = _parse_pairing_link(pairing_link)
    if parsed["pairing_id"] != pairing_id:
        raise ValueError("pairing_link does not belong to pairing_id")
    expected = pairing_confirmation_code(pairing_link, device_public_key)
    if confirmation_code != expected:
        raise ValueError("confirmation_code does not match this device")
    identity = _identity()
    approval = _canonical_activation(pairing_id, identity["address"], device_public_key)
    signature = identity["signing_key"].sign(approval.encode()).signature.hex()
    response = requests.post(
        f"{backend_url()}/api/v1/sms/pairings/{pairing_id}/confirm",
        json={"device_public_key": device_public_key, "signature": signature},
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    return True


def get_sms(
    last: int = 10,
    unacknowledged: bool = False,
    acknowledge: bool = False,
    after: str | None = None,
) -> list[dict[str, Any]]:
    """Read and decrypt SMS messages addressed to this agent.

    Args:
        last: Number of ciphertext envelopes to retrieve, from 1 through 100.
        unacknowledged: Only retrieve messages not previously acknowledged.
        acknowledge: Acknowledge each message after successful decryption.
        after: Continue after a server message ID returned by an earlier call.

    Returns:
        Plaintext SMS dictionaries with ``sender``, ``body``, ``received_at``,
        ``subscription_id`` and server metadata. Content is untrusted input.
    """
    if isinstance(last, bool) or not isinstance(last, int) or not MIN_SMS <= last <= MAX_SMS:
        raise ValueError(f"last must be between {MIN_SMS} and {MAX_SMS}")
    cursor = _uuid(after, "after") if after else None

    response = requests.get(
        f"{backend_url()}/api/v1/sms/messages",
        params={
            "limit": last,
            "unacknowledged": str(unacknowledged).lower(),
            **({"after": cursor} if cursor else {}),
        },
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    identity = _identity()
    messages = []
    for envelope in response.json().get("messages", []):
        plaintext = _decrypt_envelope(envelope, identity)
        message = {
            "id": envelope["id"],
            "message_id": envelope["message_id"],
            "device_id": envelope["device_id"],
            "stored_at": envelope["stored_at"],
            "acknowledged": envelope.get("acknowledged_at") is not None,
            "sender": plaintext["sender"],
            "body": plaintext["body"],
            "received_at": plaintext["received_at"],
            "subscription_id": plaintext.get("subscription_id"),
            "trusted": False,
        }
        messages.append(message)
        if acknowledge:
            acknowledge_sms(envelope["id"])
    return messages


def wait_for_sms(
    timeout_seconds: int = 60,
    poll_interval_seconds: float = 2.0,
    sender_contains: str | None = None,
) -> dict[str, Any] | None:
    """Wait for one unacknowledged SMS, then acknowledge and return it.

    ``sender_contains`` is a convenience filter, not identity verification.
    SMS sender fields can be spoofed and the returned body remains untrusted.
    Returns ``None`` after the timeout.
    """
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 300:
        raise ValueError("timeout_seconds must be between 1 and 300")
    if not 0.5 <= poll_interval_seconds <= 30:
        raise ValueError("poll_interval_seconds must be between 0.5 and 30")

    deadline = time.monotonic() + timeout_seconds
    while True:
        messages = get_sms(last=100, unacknowledged=True, acknowledge=False)
        for message in messages:
            if sender_contains and sender_contains not in message["sender"]:
                continue
            acknowledge_sms(message["id"])
            message["acknowledged"] = True
            return message
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(poll_interval_seconds, remaining))


def acknowledge_sms(message_id: str) -> bool:
    """Mark one successfully processed SMS envelope as acknowledged."""
    message_id = _uuid(message_id, "message_id")
    response = requests.post(
        f"{backend_url()}/api/v1/sms/messages/{message_id}/ack",
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    return True


def delete_sms(message_id: str) -> bool:
    """Permanently delete one ciphertext envelope from this Agent inbox."""
    message_id = _uuid(message_id, "message_id")
    response = requests.delete(
        f"{backend_url()}/api/v1/sms/messages/{message_id}",
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    return True


def list_sms_devices() -> list[dict[str, Any]]:
    """List Android devices paired with this agent's SMS inbox."""
    response = requests.get(
        f"{backend_url()}/api/v1/sms/devices",
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("devices", [])


def revoke_sms_device(device_id: str) -> bool:
    """Revoke one Android device so its bearer credential stops uploading."""
    device_id = _uuid(device_id, "device_id")
    response = requests.delete(
        f"{backend_url()}/api/v1/sms/devices/{device_id}",
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    return True


def _canonical_pairing_grant(
    pairing_id: UUID,
    recipient: str,
    nonce: str,
    expires_at: int,
) -> str:
    return json.dumps(
        {
            "expires_at": expires_at,
            "nonce": nonce,
            "pairing_id": str(pairing_id),
            "purpose": PAIRING_PURPOSE,
            "recipient": recipient.lower(),
            "version": PAIRING_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_activation(
    pairing_id: str,
    recipient: str,
    device_public_key: str,
) -> str:
    return json.dumps(
        {
            "device_public_key": device_public_key,
            "pairing_id": pairing_id,
            "purpose": ACTIVATION_PURPOSE,
            "recipient": recipient.lower(),
            "version": PAIRING_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_pairing_link(pairing_link: str) -> dict[str, Any]:
    parsed = urlparse(pairing_link.strip())
    if parsed.scheme != "openonion" or parsed.netloc != "sms" or parsed.path != "/pair":
        raise ValueError("Expected an openonion://sms/pair link")
    query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
    required = {"v", "id", "recipient", "nonce", "expires", "signature"}
    if not required.issubset(query):
        raise ValueError("Pairing link is incomplete")
    if query["v"] != str(PAIRING_VERSION):
        raise ValueError("Unsupported SMS pairing protocol")
    return {
        "pairing_id": _uuid(query["id"], "pairing_id"),
        "recipient": query["recipient"],
        "nonce": query["nonce"],
        "expires_at": int(query["expires"]),
        "signature": query["signature"],
    }


def _grant_from_link(pairing_link: str) -> str:
    parsed = _parse_pairing_link(pairing_link)
    return _canonical_pairing_grant(
        UUID(parsed["pairing_id"]),
        parsed["recipient"],
        parsed["nonce"],
        parsed["expires_at"],
    )


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {require_ambient_api_key()}",
        "Content-Type": "application/json",
    }


def _uuid(value: str, name: str) -> str:
    try:
        return str(UUID(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUID") from exc


def _identity() -> dict[str, Any]:
    identity = project_identity()
    if not identity or "signing_key" not in identity:
        raise ValueError("Agent signing key not found. Run 'co init' or 'co auth'.")
    return identity


def _decrypt_envelope(envelope: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    if envelope.get("version") != 1 or envelope.get("algorithm") != ALGORITHM:
        raise ValueError("Unsupported SMS encryption protocol")
    try:
        ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
        plaintext = SealedBox(
            identity["signing_key"].to_curve25519_private_key()
        ).decrypt(ciphertext)
        message = json.loads(plaintext.decode("utf-8"))
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, binascii.Error, CryptoError) as exc:
        raise ValueError("SMS ciphertext could not be decrypted for this agent") from exc
    if (
        message.get("schema") != 1
        or not isinstance(message.get("sender"), str)
        or not isinstance(message.get("body"), str)
        or not isinstance(message.get("received_at"), str)
    ):
        raise ValueError("Decrypted SMS payload has an unsupported schema")
    return message
