"""Get emails functionality for ConnectOnion agents."""

import os
import json
import toml
import requests
from pathlib import Path
from typing import List, Dict, Optional, Union


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
    # Find .co directory in current or parent directories
    co_dir = Path(".co")
    if not co_dir.exists():
        co_dir = Path("../.co")
        if not co_dir.exists():
            # Return empty list if not in a ConnectOnion project
            return []
    
    # Load configuration
    config_path = co_dir / "config.toml"
    if not config_path.exists():
        return []
    
    try:
        config = toml.load(config_path)
    except Exception:
        return []
    
    # Check if email is activated
    agent_config = config.get("agent", {})
    email_active = agent_config.get("email_active", False)
    
    if not email_active:
        # Return empty list if email not activated
        return []
    
    # Get authentication token
    auth_config = config.get("auth", {})
    token = auth_config.get("token")
    
    if not token:
        # Return empty list if no token
        return []
    
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
    
    try:
        response = requests.get(
            endpoint,
            params=params,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
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
        else:
            # Return empty list on error
            return []
            
    except Exception:
        # Return empty list on any error
        return []


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
        return False
    
    # Find .co directory
    co_dir = Path(".co")
    if not co_dir.exists():
        co_dir = Path("../.co")
        if not co_dir.exists():
            return False
    
    # Load configuration
    config_path = co_dir / "config.toml"
    if not config_path.exists():
        return False
    
    try:
        config = toml.load(config_path)
    except Exception:
        return False
    
    # Get authentication token
    auth_config = config.get("auth", {})
    token = auth_config.get("token")
    
    if not token:
        return False
    
    # Mark emails as read via backend API
    backend_url = os.getenv("CONNECTONION_BACKEND_URL", "https://oo.openonion.ai")
    endpoint = f"{backend_url}/api/email/s/mark-read"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Mark each email as read individually
    all_success = True
    for email_id in email_ids:
        try:
            response = requests.post(
                f"{endpoint}?email_id={email_id}",
                headers=headers,
                timeout=10
            )
            if response.status_code != 200:
                all_success = False
        except Exception:
            all_success = False

    return all_success


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
        return False
    
    # Find .co directory
    co_dir = Path(".co")
    if not co_dir.exists():
        co_dir = Path("../.co")
        if not co_dir.exists():
            return False
    
    # Load configuration
    config_path = co_dir / "config.toml"
    if not config_path.exists():
        return False
    
    try:
        config = toml.load(config_path)
    except Exception:
        return False
    
    # Get authentication token
    auth_config = config.get("auth", {})
    token = auth_config.get("token")
    
    if not token:
        return False
    
    # Mark emails as unread via backend API
    backend_url = os.getenv("CONNECTONION_BACKEND_URL", "https://oo.openonion.ai")
    endpoint = f"{backend_url}/api/email/s/mark-unread"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Mark each email as unread individually
    all_success = True
    for email_id in email_ids:
        try:
            response = requests.post(
                f"{endpoint}?email_id={email_id}",
                headers=headers,
                timeout=10
            )
            if response.status_code != 200:
                all_success = False
        except Exception:
            all_success = False

    return all_success