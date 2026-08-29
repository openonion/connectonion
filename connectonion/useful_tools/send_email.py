"""
Purpose: Send emails via OpenOnion API using agent's authenticated email address
LLM-Note:
  Dependencies: imports from [os, json, yaml, requests, pathlib, typing, dotenv, credentials, project] | imported by [__init__.py, useful_tools/__init__.py] | tested by [tests/unit/test_email_functions.py, tests/test_real_email.py]
  Data flow: Agent calls send_email(to, subject, message) → preserves environment precedence and fills missing values from project-root .env then ~/.co/keys.env → validates the selected ambient token against the canonical project identity → validates email format → POST to /api/v1/email/send → returns {success, message_id, from, error}
  State/Effects: reads canonical credential files and loads missing values into the process environment | makes one HTTP POST only after credential validation | no local state persistence
  Integration: exposes send_email(to, subject, message) → returns dict | used as agent tool function | requires prior 'co auth' to set OPENONION_API_KEY and AGENT_EMAIL | API endpoint: POST /api/v1/email/send with Bearer token
  Performance: canonical project-root lookup plus at most two dotenv reads | one HTTP request per email | no caching | synchronous (blocks on network)
  Errors: returns {success: False, error: str} for missing/mismatched credentials, invalid email format, and API failures | credential errors are redacted and non-retryable | HTTP errors caught and wrapped
"""

import os
import uuid
from pathlib import Path
from typing import Dict, Optional

import requests
import yaml
from dotenv import load_dotenv

from ..backend import backend_url
from ..credentials import AmbientCredentialError, require_ambient_api_key
from ..project import project_co_dir, project_root


def send_email(
    to: str,
    subject: str,
    message: str,
    idempotency_key: Optional[str] = None,
    from_address: Optional[str] = None,
) -> Dict:
    """Send an email using the agent's email address.

    Args:
        to: Recipient email address
        subject: Email subject line
        message: Email body (plain text or HTML)
        idempotency_key: Reuse the key from a failed result to retry without
            sending the same email twice while the provider retry window is
            still active. A new key is generated when omitted.
        from_address: Send as one of this account's owned addresses instead of
            the default. The server verifies ownership and answers 403 for an
            address this account does not hold.

    Returns:
        dict: Success status and details
            - success (bool): Whether email was sent
            - message_id (str): ID of sent message
            - from (str): Sender email address
            - error (str): Error message if failed
            - request_id (str): Correlation ID for support and server logs
            - idempotency_key (str): Correlation key for this send attempt
            - retryable (bool): Whether retrying this key is currently safe
    """
    send_key = idempotency_key or str(uuid.uuid4())
    # Environment values (container, CI, systemd, or an importing application)
    # keep precedence. Canonical project/global files only fill missing values;
    # the arbitrary five-parent crawl used here before disagreed with every
    # other project boundary in the framework.
    for env_file in (
        project_root() / ".env",
        Path.home() / ".co" / "keys.env",
    ):
        if env_file.is_file():
            load_dotenv(env_file)

    try:
        token = require_ambient_api_key()
    except AmbientCredentialError as exc:
        return {
            "success": False,
            "error": str(exc),
            "request_id": send_key,
            "idempotency_key": send_key,
            "retryable": False,
        }

    from_email = os.getenv("AGENT_EMAIL")

    if not from_email:
        return {
            "success": False,
            "error": "AGENT_EMAIL not set. Run 'co auth' to set up email.",
            "request_id": send_key,
            "idempotency_key": send_key,
            "retryable": False,
        }

    # Validate recipient email
    if "@" not in to or "." not in to.split("@")[-1]:
        return {
            "success": False,
            "error": f"Invalid email address: {to}",
            "request_id": send_key,
            "idempotency_key": send_key,
            "retryable": False,
        }

    # Prepare email payload
    payload = {
        "to": to,
        "subject": subject,
        # The body goes as-is. A local `is_html = "<" in message and ">" in
        # message` used to be computed here and thrown away — the payload has no
        # html field to put it in — while the header claimed the function
        # "detects HTML vs plain text". Whether a body renders as HTML is the
        # backend's decision, and nothing here influences it.
        "body": message
    }
    if from_address:
        payload["from_address"] = from_address

    # Send email via backend API
    endpoint = f"{backend_url()}/api/v1/email/send"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Request-ID": send_key,
        "Idempotency-Key": send_key,
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "message_id": data.get("message_id", "msg_unknown"),
                "from": data.get("from", from_email),
                "request_id": data.get("request_id", _response_header(response, "X-Request-ID", send_key)),
                "idempotency_key": data.get("idempotency_key", send_key),
            }
        elif response.status_code == 429:
            error_msg, request_id, returned_key, retryable = _email_error(
                response, "Rate limit exceeded", send_key, default_retryable=False
            )
            return {
                "success": False,
                "error": error_msg,
                "request_id": request_id,
                "idempotency_key": returned_key,
                "retryable": retryable,
            }
        elif response.status_code == 401:
            _, request_id, returned_key, retryable = _email_error(
                response, "Authentication failed", send_key, default_retryable=False
            )
            return {
                "success": False,
                "error": "Authentication failed. Run 'co auth' to re-authenticate.",
                "request_id": request_id,
                "idempotency_key": returned_key,
                "retryable": retryable,
            }
        else:
            # The backend answers errors in JSON; the gateway in front of it
            # does not. A 502 HTML page made .json() raise out of a *tool*,
            # which is worse than a traceback in a CLI: every other failure
            # here returns {"success": False, "error": …} for the model to read
            # and relay, and an exception unwinds the turn instead.
            #
            # deploy_commands._error_text and server_commands._report_failure
            # already guard the same call; auth (fixed above) and this were the
            # two that were missed.
            error_msg, request_id, returned_key, retryable = _email_error(
                response,
                f"HTTP {response.status_code} (the reply was not JSON)",
                send_key,
                default_retryable=response.status_code >= 500,
            )
            return {
                "success": False,
                "error": error_msg,
                "request_id": request_id,
                "idempotency_key": returned_key,
                "retryable": retryable,
            }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Request timed out. Retry with the same idempotency key.",
            "request_id": send_key,
            "idempotency_key": send_key,
            "retryable": True,
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "Cannot connect to email service. Retry with the same idempotency key when it is reachable.",
            "request_id": send_key,
            "idempotency_key": send_key,
            "retryable": True,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to send email: {str(e)}",
            "request_id": send_key,
            "idempotency_key": send_key,
            "retryable": False,
        }


def _email_error(
    response,
    fallback: str,
    send_key: str,
    *,
    default_retryable: bool,
):
    """Read the stable API error shape, with a gateway-safe fallback."""
    request_id = _response_header(response, "X-Request-ID", send_key)
    returned_key = send_key
    retryable = default_retryable
    try:
        data = response.json()
        if not isinstance(data, dict):
            return fallback, request_id, returned_key, retryable
        request_id = data.get("request_id", request_id)
        returned_key = data.get("idempotency_key", returned_key)
        error = data.get("error")
        if isinstance(error, dict) and isinstance(error.get("retryable"), bool):
            retryable = error["retryable"]
        detail = data.get("detail")
        if detail:
            return str(detail), request_id, returned_key, retryable
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"]), request_id, returned_key, retryable
    except (ValueError, AttributeError):
        pass
    return fallback, request_id, returned_key, retryable


def _response_header(response, name: str, fallback: str) -> str:
    """Read a response header without requiring test doubles to provide it."""
    headers = getattr(response, "headers", None)
    if headers is None:
        return fallback
    value = headers.get(name, fallback)
    return value if isinstance(value, str) else fallback


def get_agent_email() -> Optional[str]:
    """Get the agent's email address from configuration.
    
    Returns:
        str: Agent's email address or None if not configured
    """
    # The project's `.co/`. This walked up exactly one level by hand --
    # `Path("../.co")` -- so it survived one subdirectory and returned None
    # from two. project.py does the same walk for any depth.
    co_dir = project_co_dir()
    if not co_dir.exists():
        return None

    config_path = co_dir / "host.yaml"
    if not config_path.exists():
        return None

    try:
        with open(config_path, 'r', encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        agent_config = config.get("agent", {})

        # Get email or generate from address
        email = agent_config.get("email")
        if not email:
            address = agent_config.get("address", "")
            if address and address.startswith("0x"):
                email = f"{address[:10]}@mail.openonion.ai"

        return email
    except Exception:
        return None


def is_email_active() -> bool:
    """Check if the agent's email is activated.

    Returns:
        bool: True if email is activated, False otherwise
    """
    return os.getenv("IS_EMAIL_ACTIVE", "").lower() == "true"
