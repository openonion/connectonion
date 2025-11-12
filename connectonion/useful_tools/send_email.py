"""
Purpose: Send emails via OpenOnion API using agent's authenticated email address
LLM-Note:
  Dependencies: imports from [os, json, toml, requests, pathlib, typing, dotenv] | imported by [__init__.py, useful_tools/__init__.py] | tested by [tests/test_email_functions.py, tests/test_real_email.py]
  Data flow: Agent calls send_email(to, subject, message) → searches for .env file (cwd → parent dirs → ~/.co/keys.env) → loads OPENONION_API_KEY and AGENT_EMAIL → validates email format → detects HTML vs plain text → POST to oo.openonion.ai/api/email with auth token → returns {success, message_id, from, error}
  State/Effects: reads .env files from filesystem | loads environment variables via dotenv | makes HTTP POST request to OpenOnion API | no local state persistence
  Integration: exposes send_email(to, subject, message) → returns dict | used as agent tool function | requires prior 'co auth' to set OPENONION_API_KEY and AGENT_EMAIL | API endpoint: POST /api/email with Bearer token
  Performance: file search up to 5 parent dirs | one HTTP request per email | no caching | synchronous (blocks on network)
  Errors: returns {success: False, error: str} for: missing .env, missing keys, invalid email format, API failures | HTTP errors caught and wrapped | validates @ and . in email | let-it-crash pattern (returns errors, doesn't raise)
"""

import os
import json
import toml
import requests
from pathlib import Path
from typing import Dict, Optional


def send_email(to: str, subject: str, message: str) -> Dict:
    """Send an email using the agent's email address.

    Args:
        to: Recipient email address
        subject: Email subject line
        message: Email body (plain text or HTML)

    Returns:
        dict: Success status and details
            - success (bool): Whether email was sent
            - message_id (str): ID of sent message
            - from (str): Sender email address
            - error (str): Error message if failed
    """
    # Find .env file by searching up the directory tree
    env_file = None
    current_dir = Path.cwd()

    # Search up to 5 levels for .env
    for _ in range(5):
        potential_env = current_dir / ".env"
        if potential_env.exists():
            env_file = potential_env
            break
        if current_dir == current_dir.parent:  # Reached root
            break
        current_dir = current_dir.parent

    # If no local .env found, try global keys.env
    if not env_file:
        global_keys_env = Path.home() / ".co" / "keys.env"
        if global_keys_env.exists():
            env_file = global_keys_env

    if not env_file:
        return {
            "success": False,
            "error": "No .env file found. Run 'co init' or 'co auth' first."
        }

    # Get authentication token and agent email from environment
    token = os.getenv("OPENONION_API_KEY")
    from_email = os.getenv("AGENT_EMAIL")

    if not token:
        return {
            "success": False,
            "error": "OPENONION_API_KEY not found in .env. Run 'co auth' to authenticate."
        }

    if not from_email:
        return {
            "success": False,
            "error": "AGENT_EMAIL not found in .env. Run 'co auth' to set up email."
        }
    
    # Validate recipient email
    if not "@" in to or not "." in to.split("@")[-1]:
        return {
            "success": False,
            "error": f"Invalid email address: {to}"
        }
    
    # Detect if message contains HTML
    is_html = "<" in message and ">" in message
    
    # Prepare email payload
    payload = {
        "to": to,
        "subject": subject,
        "body": message  # Simple direct body
    }
    
    # Send email via backend API
    backend_url = os.getenv("CONNECTONION_BACKEND_URL", "https://oo.openonion.ai")
    endpoint = f"{backend_url}/api/v1/email/send"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
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
                "from": from_email
            }
        elif response.status_code == 429:
            return {
                "success": False,
                "error": "Rate limit exceeded"
            }
        elif response.status_code == 401:
            return {
                "success": False,
                "error": "Authentication failed. Run 'co auth' to re-authenticate."
            }
        else:
            error_msg = response.json().get("detail", "Unknown error")
            return {
                "success": False,
                "error": error_msg
            }
            
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Request timed out. Please try again."
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "Cannot connect to email service. Check your internet connection."
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to send email: {str(e)}"
        }


def get_agent_email() -> Optional[str]:
    """Get the agent's email address from configuration.
    
    Returns:
        str: Agent's email address or None if not configured
    """
    co_dir = Path(".co")
    if not co_dir.exists():
        co_dir = Path("../.co")
        if not co_dir.exists():
            return None
    
    config_path = co_dir / "config.toml"
    if not config_path.exists():
        return None
    
    try:
        config = toml.load(config_path)
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
    co_dir = Path(".co")
    if not co_dir.exists():
        co_dir = Path("../.co")
        if not co_dir.exists():
            return False
    
    config_path = co_dir / "config.toml"
    if not config_path.exists():
        return False
    
    try:
        config = toml.load(config_path)
        agent_config = config.get("agent", {})
        return agent_config.get("email_active", False)
    except Exception:
        return False