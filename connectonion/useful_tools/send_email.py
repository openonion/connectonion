"""Send email functionality for ConnectOnion agents."""

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
    # Find .co directory in current or parent directories
    co_dir = Path(".co")
    if not co_dir.exists():
        # Try parent directory
        co_dir = Path("../.co")
        if not co_dir.exists():
            return {
                "success": False,
                "error": "Not in a ConnectOnion project. Run 'co init' first."
            }
    
    # Load configuration
    config_path = co_dir / "config.toml"
    if not config_path.exists():
        return {
            "success": False,
            "error": "Configuration not found. Run 'co init' first."
        }
    
    try:
        config = toml.load(config_path)
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load configuration: {str(e)}"
        }
    
    # Check if email is activated
    agent_config = config.get("agent", {})
    email_active = agent_config.get("email_active", False)
    
    if not email_active:
        return {
            "success": False,
            "error": "Email not activated. Run 'co auth' to activate."
        }
    
    # Get agent's email address
    from_email = agent_config.get("email")
    if not from_email:
        # Generate from address if not present
        address = agent_config.get("address", "")
        if address and address.startswith("0x"):
            from_email = f"{address[:10]}@mail.openonion.ai"
        else:
            return {
                "success": False,
                "error": "Agent email address not configured."
            }
    
    # Get authentication token
    auth_config = config.get("auth", {})
    token = auth_config.get("token")
    
    if not token:
        return {
            "success": False,
            "error": "Authentication token not found. Run 'co auth' to authenticate."
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