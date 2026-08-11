"""
Purpose: Retrieve emails from agent's inbox via OpenOnion API with filtering options
LLM-Note:
  Dependencies: imports from [requests, typing, backend, credentials] | imported by [__init__.py, useful_tools/__init__.py] | tested by [tests/unit/test_email_functions.py, tests/unit/test_credentials.py, tests/test_real_email.py]
  Data flow: Agent calls a mailbox function → require_ambient_api_key() checks the already-loaded environment token against the canonical project identity → request to the configured backend → normalized result
  State/Effects: reads the ambient token and local identity keys | makes HTTP GET/POST requests | no local caching | mark_read()/mark_unread() modify server-side read status
  Integration: exposes get_emails(last, unread), mark_read(email_id) | used as agent tool functions | requires 'co auth' setup | API endpoints: GET /api/v1/email/received?last=N&unread=true, PUT /api/v1/email/s/mark-read
  Performance: one HTTP request per call | no pagination (uses 'last' param) | synchronous blocking | no local cache
  Errors: missing/mismatched ambient credentials and HTTP failures raise | no credential value is included in errors
"""

import requests
from typing import List, Dict, Union
from ..backend import backend_url
from ..credentials import require_ambient_api_key


def get_emails(last: int = 10, unread: bool = False) -> List[Dict]:
    """Get emails sent to the agent's address.

    Args:
        last: Number of emails to retrieve (default: 10)
        unread: Only get unread emails (default: False)

    Returns:
        List of email dictionaries containing:
            - id: Unique message ID
            - from: Sender's email address
            - subject: Email subject
            - message: Email body content
            - timestamp: ISO format timestamp
            - read: Boolean read status
    """
    token = require_ambient_api_key()
    
    # Fetch emails from backend API
    endpoint = f"{backend_url()}/api/v1/email/received"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    params = {
        "limit": last,
        "unread_only": unread
    }

    response = requests.get(
        endpoint,
        params=params,
        headers=headers,
        timeout=10
    )

    # Raise error if API call failed
    response.raise_for_status()

    data = response.json()
    emails = data.get("emails", [])

    # Ensure consistent format
    formatted_emails = []
    for email in emails:
        formatted_emails.append({
            "id": email.get("id", ""),
            "from": email.get("from_email", email.get("from", "")),
            "subject": email.get("subject", ""),
            "message": email.get("text") or email.get("html") or email.get("text_body") or email.get("html_body", ""),
            "timestamp": email.get("received_at", ""),
            "read": email.get("is_read", False)
        })

    return formatted_emails


def get_sent(last: int = 10, to: str = None) -> List[Dict]:
    """Get emails the agent has sent (the Sent mailbox).

    Args:
        last: Number of emails to retrieve (default: 10)
        to: Only emails sent to this address (default: all)

    Returns:
        List of email dictionaries containing:
            - id: Record ID (use with `co email sent read <id>`)
            - to: Recipient's email address
            - from: The address it went out as
            - subject: Email subject
            - body: What was sent
            - status: Last known status (e.g. "sent")
            - message_id: Provider message ID
            - timestamp: ISO format send time
    """
    token = require_ambient_api_key()

    params = {"limit": last}
    if to:
        params["to"] = to

    response = requests.get(
        f"{backend_url()}/api/v1/email/sent",
        params=params,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=10,
    )
    response.raise_for_status()

    return [{
        "id": email.get("id", ""),
        "to": email.get("to", ""),
        "from": email.get("from", ""),
        "subject": email.get("subject", ""),
        "body": email.get("body", ""),
        "status": email.get("status", ""),
        "message_id": email.get("message_id", ""),
        "timestamp": email.get("sent_at", ""),
    } for email in response.json().get("emails", [])]


def mark_read(email_ids: Union[str, List[str]]) -> bool:
    """Mark email(s) as read.

    Args:
        email_ids: Single email ID or list of IDs to mark as read

    Returns:
        True if successful, False otherwise
    """
    # Normalize to list
    if isinstance(email_ids, str):
        email_ids = [email_ids]

    if not email_ids:
        raise ValueError("No email IDs provided to mark as read")

    token = require_ambient_api_key()
    
    # Mark emails as read via backend API
    endpoint = f"{backend_url()}/api/v1/email/s/mark-read"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Mark each email as read individually
    for email_id in email_ids:
        response = requests.post(
            f"{endpoint}?email_id={email_id}",
            headers=headers,
            timeout=10
        )
        # Raise error if API call failed
        response.raise_for_status()

    return True


def mark_unread(email_ids: Union[str, List[str]]) -> bool:
    """Mark email(s) as unread.

    Args:
        email_ids: Single email ID or list of IDs to mark as unread

    Returns:
        True if successful, False otherwise
    """
    # Normalize to list
    if isinstance(email_ids, str):
        email_ids = [email_ids]

    if not email_ids:
        raise ValueError("No email IDs provided to mark as unread")

    token = require_ambient_api_key()

    # Mark emails as unread via backend API
    endpoint = f"{backend_url()}/api/v1/email/s/mark-unread"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Mark each email as unread individually
    for email_id in email_ids:
        response = requests.post(
            f"{endpoint}?email_id={email_id}",
            headers=headers,
            timeout=10
        )
        # Raise error if API call failed
        response.raise_for_status()

    return True
