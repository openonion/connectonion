"""Send email functionality for ConnectOnion agents."""

import os
import json
import toml
import requests
from pathlib import Path
from typing import Dict, Optional
from dotenv import load_dotenv


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

    # Load environment variables from the found .env file
    load_dotenv(env_file)

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
    endpoint = f"{backend_url}/api/email/send"
    
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