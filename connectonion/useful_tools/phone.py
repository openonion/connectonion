"""
Purpose: Reach the owner on their phone when email will not be read in time
LLM-Note:
  Dependencies: imports from [os, requests, backend.backend_url] | imported by [useful_tools/__init__.py, cli/commands/phone_commands.py] | tested by [tests/unit/test_phone.py]
  Data flow: notify_owner(message, urgent) → POST {backend}/api/v1/phone/notify with OPENONION_API_KEY → returns {success, channel, error}
  State/Effects: one HTTP POST per notification | no local state | no carrier credential is held here — the backend owns it
  Integration: exposed as an agent tool and as `co phone notify` | set_owner_phone/get_owner_phone back `co phone number`
  Errors: returns {success: False, error} — a rate-limited or unconfigured account is a normal outcome the caller must read, not an exception
"""

import os
from typing import Dict

import requests

from ..backend import backend_url


NO_AUTH = (
    "OPENONION_API_KEY not found. Run 'co auth login' first — the phone "
    "channel is billed to your account, so it needs one."
)


def notify_owner(message: str, urgent: bool = False) -> Dict:
    """Get the owner's attention on their phone.

    Use this when a run cannot continue without a human and email would not be
    read in time — an overnight run, a deploy that needs a decision now. The
    answer still comes back by email; this only makes someone look.

    Args:
        message: What to tell them. Say which agent you are and what you need.
        urgent: True places a call that speaks the message; False sends an SMS.

    Returns:
        dict: {success, channel, error}
    """
    token = os.getenv("OPENONION_API_KEY")
    if not token:
        return {"success": False, "error": NO_AUTH}

    response = requests.post(
        f"{backend_url()}/api/v1/phone/notify",
        json={"message": message, "channel": "voice" if urgent else "sms"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )

    if response.status_code == 200:
        return {"success": True, **response.json()}

    # The backend's reasons are all actionable and all different: no number
    # configured, inside the cooldown, out of credit. Flattening them to
    # "failed" would throw away what the agent should do next.
    return {"success": False, "error": _reason(response)}


def set_owner_phone(phone: str) -> Dict:
    """Set the number your agents should reach you on. E.164, e.g. +61435525634."""
    token = os.getenv("OPENONION_API_KEY")
    if not token:
        return {"success": False, "error": NO_AUTH}

    response = requests.put(
        f"{backend_url()}/api/v1/phone/number",
        json={"phone": phone},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if response.status_code == 200:
        return {"success": True, **response.json()}
    return {"success": False, "error": _reason(response)}


def get_owner_phone() -> Dict:
    """What number your agents will reach you on, if any."""
    token = os.getenv("OPENONION_API_KEY")
    if not token:
        return {"success": False, "error": NO_AUTH}

    response = requests.get(
        f"{backend_url()}/api/v1/phone/number",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if response.status_code == 200:
        return {"success": True, **response.json()}
    return {"success": False, "error": _reason(response)}


def _reason(response) -> str:
    """The server's own explanation, with the retry delay kept attached."""
    detail = response.json().get("detail") if response.headers.get(
        "content-type", ""
    ).startswith("application/json") else None
    reason = detail if isinstance(detail, str) else response.text[:300]

    retry_after = response.headers.get("Retry-After")
    if retry_after and str(retry_after) not in reason:
        reason = f"{reason} (retry in {retry_after}s)"
    return reason
