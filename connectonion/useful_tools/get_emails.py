"""Get emails functionality for ConnectOnion agents."""

import os
import json
import toml
import requests
from pathlib import Path
from typing import List, Dict, Optional, Union
from dotenv import load_dotenv


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
    # Load environment variables from .env file
    load_dotenv()

    # Get authentication token from environment
    # Emails are hosted by OpenOnion and require OPENONION_API_KEY for authentication
    token = os.getenv("OPENONION_API_KEY")

    if not token:
        raise ValueError(
            "OPENONION_API_KEY not found in .env file. "
            "Agent emails are hosted by OpenOnion and require authentication. "
            "Check your .env file for OPENONION_API_KEY, or run 'co init' to copy "
            "OPENONION_API_KEY from ~/.co/keys.env to your project."
        )
    
    # Fetch emails from backend API
    backend_url = os.getenv("CONNECTONION_BACKEND_URL", "https://oo.openonion.ai")
    endpoint = f"{backend_url}/api/email/received"

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
            "message": email.get("text_body", email.get("html_body", "")),
            "timestamp": email.get("received_at", ""),
            "read": email.get("is_read", False)
        })

    return formatted_emails


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

    # Load environment variables from .env file
    load_dotenv()

    # Get authentication token from environment
    token = os.getenv("OPENONION_API_KEY")

    if not token:
        raise ValueError(
            "OPENONION_API_KEY not found in .env file. "
            "Check your .env file for OPENONION_API_KEY, or run 'co init' to copy "
            "OPENONION_API_KEY from ~/.co/keys.env to your project."
        )
    
    # Mark emails as read via backend API
    backend_url = os.getenv("CONNECTONION_BACKEND_URL", "https://oo.openonion.ai")
    endpoint = f"{backend_url}/api/email/s/mark-read"

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

    # Load environment variables from .env file
    load_dotenv()

    # Get authentication token from environment
    token = os.getenv("OPENONION_API_KEY")

    if not token:
        raise ValueError(
            "OPENONION_API_KEY not found in .env file. "
            "Check your .env file for OPENONION_API_KEY, or run 'co init' to copy "
            "OPENONION_API_KEY from ~/.co/keys.env to your project."
        )

    # Mark emails as unread via backend API
    backend_url = os.getenv("CONNECTONION_BACKEND_URL", "https://oo.openonion.ai")
    endpoint = f"{backend_url}/api/email/s/mark-unread"

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