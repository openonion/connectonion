"""Authentication and registration commands for ConnectOnion CLI."""

import time
import json
import click
import toml
import webbrowser
import requests
from pathlib import Path
from typing import Optional

from ... import address


# ANSI color codes for authentication output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def do_direct_registration(co_dir: Path, registration_type: str = "star") -> bool:
    """Direct registration without browser flow.
    
    Args:
        co_dir: Path to .co directory with keys
        registration_type: Type of registration ("star" or "managed")
    
    Returns:
        True if registration successful, False otherwise
    """
    # Load agent keys
    try:
        addr_data = address.load(co_dir)
        if not addr_data:
            click.echo(f"{Colors.RED}❌ No agent keys found!{Colors.END}")
            return False
    except Exception as e:
        click.echo(f"{Colors.RED}❌ Error loading keys: {e}{Colors.END}")
        return False
    
    public_key = addr_data["address"]
    
    click.echo(f"{Colors.CYAN}🔐 Registering with ConnectOnion...{Colors.END}")
    click.echo(f"   Agent: {Colors.BOLD}{addr_data['short_address']}{Colors.END}")
    
    # Create signed registration message (same format as auth)
    timestamp = int(time.time())
    message_data = {
        "public_key": public_key,
        "timestamp": timestamp,
        "registration_type": registration_type  # Include registration type
    }
    message_json = json.dumps(message_data, separators=(',', ':'))
    signature = address.sign(addr_data, message_json.encode()).hex()
    
    # Make direct API call to authenticate
    backend_url = "https://oo.openonion.ai"
    
    try:
        # Use the standard auth endpoint with headers
        headers = {
            "X-Public-Key": public_key,
            "X-Signature": signature,
            "X-Message": message_json
        }
        
        response = requests.post(f"{backend_url}/auth", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("token")
            email = data.get("email_address") or f"{public_key[:10]}@mail.openonion.ai"
            
            # Save token to config
            config_path = co_dir / "config.toml"
            config = toml.load(config_path) if config_path.exists() else {}
            config["auth"] = {"token": token}
            if "agent" not in config:
                config["agent"] = {}
            config["agent"]["email"] = email
            config["agent"]["email_active"] = True
            
            with open(config_path, "w") as f:
                toml.dump(config, f)
            
            return True
        else:
            error_msg = response.json().get("detail", "Registration failed")
            click.echo(f"{Colors.RED}❌ Registration failed: {error_msg}{Colors.END}")
            return False
            
    except requests.exceptions.RequestException as e:
        click.echo(f"{Colors.RED}❌ Network error: {e}{Colors.END}")
        return False
    except Exception as e:
        click.echo(f"{Colors.RED}❌ Unexpected error: {e}{Colors.END}")
        return False


def do_auth_flow(co_dir: Path = None, use_global: bool = False) -> bool:
    """Helper function to perform authentication flow.
    
    Args:
        co_dir: Path to .co directory (defaults to current directory)
        use_global: If True, use global ConnectOnion config instead of project
        
    Returns:
        True if authentication successful, False otherwise
    """
    if use_global:
        # Use global ConnectOnion directory for authentication
        global_dir = Path.home() / ".connectonion" / ".co"
        if not global_dir.exists():
            # Create global directory and generate keys if needed
            global_dir.mkdir(parents=True, exist_ok=True)
            try:
                addr_data = address.generate()
                address.save(addr_data, global_dir)
            except Exception as e:
                click.echo(f"{Colors.RED}❌ Error creating global keys: {e}{Colors.END}")
                return False
        co_dir = global_dir
    elif co_dir is None:
        co_dir = Path(".co")
    
    # Check if directory exists (for non-global auth)
    if not use_global and not co_dir.exists():
        click.echo(f"{Colors.RED}❌ Not in a ConnectOnion project!{Colors.END}")
        click.echo(f"{Colors.YELLOW}Run 'co init' first to initialize a project.{Colors.END}")
        return False
    
    # Load agent keys
    try:
        addr_data = address.load(co_dir)
        if not addr_data:
            click.echo(f"{Colors.RED}❌ No agent keys found!{Colors.END}")
            click.echo(f"{Colors.YELLOW}Run 'co init' to generate agent keys.{Colors.END}")
            return False
    except Exception as e:
        click.echo(f"{Colors.RED}❌ Error loading keys: {e}{Colors.END}")
        return False
    
    public_key = addr_data["address"]
    signing_key = addr_data["signing_key"]
    
    click.echo(f"{Colors.CYAN}🔐 Authenticating with OpenOnion...{Colors.END}")
    click.echo(f"   Agent: {Colors.BOLD}{addr_data['short_address']}{Colors.END}")
    
    # Create signed authentication message
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = address.sign(addr_data, message.encode()).hex()
    
    # Build authentication URL - goes to frontend purchase page
    auth_url = f"https://o.openonion.ai/purchase?key={public_key}&message={message}&signature={signature}"
    
    click.echo(f"\n{Colors.CYAN}Opening browser for authentication...{Colors.END}")
    click.echo(f"   URL: {auth_url[:80]}...")
    
    # Open browser
    try:
        webbrowser.open(auth_url)
    except Exception as e:
        click.echo(f"{Colors.YELLOW}⚠️  Could not open browser automatically{Colors.END}")
        click.echo(f"Please visit: {Colors.CYAN}{auth_url}{Colors.END}")
    
    # Poll for authentication status
    click.echo(f"\n{Colors.YELLOW}⏳ Waiting for authentication...{Colors.END}")
    click.echo(f"   (This may take up to 2 minutes)")
    
    backend_url = "https://oo.openonion.ai"  # Production backend
    
    max_attempts = 24  # 2 minutes with 5-second intervals
    for attempt in range(max_attempts):
        try:
            # Check authentication status
            response = requests.get(f"{backend_url}/auth/status/{public_key}")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "authenticated":
                    token = data.get("token")
                    email = data.get("email_address") or f"{public_key[:10]}@mail.openonion.ai"
                    
                    # Save token to config
                    config_path = co_dir / "config.toml"
                    config = toml.load(config_path) if config_path.exists() else {}
                    config["auth"] = {"token": token}
                    if "agent" not in config:
                        config["agent"] = {}
                    config["agent"]["email"] = email
                    config["agent"]["email_active"] = True  # Activate email after authentication
                    
                    with open(config_path, "w") as f:
                        toml.dump(config, f)
                    
                    click.echo(f"\n{Colors.GREEN}✅ Authentication successful!{Colors.END}")
                    click.echo(f"   Token saved to .co/config.toml")
                    click.echo(f"   📧 Your email: {Colors.CYAN}{email}{Colors.END} {Colors.GREEN}(activated){Colors.END}")
                    click.echo(f"   You can now use {Colors.BOLD}co/{Colors.END} models without API keys!")
                    return True
                elif data.get("status") == "pending":
                    # Still waiting
                    time.sleep(5)
            else:
                # Not authenticated yet
                time.sleep(5)
        except Exception:
            # Backend might not be reachable, continue polling
            time.sleep(5)
    
    click.echo(f"\n{Colors.RED}❌ Authentication timed out{Colors.END}")
    click.echo(f"   Please try running {Colors.CYAN}co auth{Colors.END} again")
    return False


def handle_auth():
    """Authenticate with OpenOnion for managed keys (co/ models).
    
    This command will:
    1. Load your agent's keys from .co/keys/
    2. Sign an authentication message
    3. Open your browser to complete authentication
    4. Save the token for future use
    """
    # Check if we're in a ConnectOnion project
    co_dir = Path(".co")
    if not co_dir.exists():
        click.echo(f"{Colors.RED}❌ Not in a ConnectOnion project!{Colors.END}")
        click.echo(f"{Colors.YELLOW}Run 'co init' first to initialize a project.{Colors.END}")
        return
    
    # Load agent keys
    try:
        addr_data = address.load(co_dir)
        if not addr_data:
            click.echo(f"{Colors.RED}❌ No agent keys found!{Colors.END}")
            click.echo(f"{Colors.YELLOW}Run 'co init' to generate agent keys.{Colors.END}")
            return
    except Exception as e:
        click.echo(f"{Colors.RED}❌ Error loading keys: {e}{Colors.END}")
        return
    
    public_key = addr_data["address"]
    signing_key = addr_data["signing_key"]
    
    click.echo(f"{Colors.CYAN}🔐 Authenticating with OpenOnion...{Colors.END}")
    click.echo(f"   Agent: {Colors.BOLD}{addr_data['short_address']}{Colors.END}")
    
    # Create signed authentication message
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = address.sign(addr_data, message.encode()).hex()
    
    # Build authentication URL - goes to frontend purchase page
    # Frontend will handle the authentication and payment flow
    auth_url = f"https://o.openonion.ai/purchase?key={public_key}&message={message}&signature={signature}"
    
    click.echo(f"\n{Colors.CYAN}🌐 Opening browser for token purchase...{Colors.END}")
    click.echo(f"   Purchase tokens to use co/ models:")
    click.echo(f"   • $0.99 for 100K tokens")
    click.echo(f"   • $9.99 for 1M tokens")
    click.echo(f"\n   If browser doesn't open, visit:")
    click.echo(f"   {Colors.UNDERLINE}{auth_url}{Colors.END}")
    
    # Open browser
    webbrowser.open(auth_url)
    
    # Poll for authentication completion
    click.echo(f"\n{Colors.CYAN}⏳ Waiting for authentication...{Colors.END}")
    
    poll_url = f"https://oo.openonion.ai/auth/poll/{public_key}"
    
    max_attempts = 60  # 5 minutes (60 * 5 seconds)
    for i in range(max_attempts):
        try:
            response = requests.get(poll_url)
            if response.status_code == 200:
                data = response.json()
                if "token" in data:
                    # Authentication successful!
                    token = data["token"]
                    email = data.get("email_address") or f"{public_key[:10]}@mail.openonion.ai"
                    
                    # Save token and email to config.toml
                    config_path = co_dir / "config.toml"
                    config = toml.load(config_path)
                    config["auth"] = {"token": token}
                    if "agent" not in config:
                        config["agent"] = {}
                    config["agent"]["email"] = email
                    config["agent"]["email_active"] = True  # Activate email after authentication
                    
                    with open(config_path, "w") as f:
                        toml.dump(config, f)
                    
                    click.echo(f"\n{Colors.GREEN}✅ Authentication successful!{Colors.END}")
                    click.echo(f"   Token saved to .co/config.toml")
                    click.echo(f"   📧 Your email: {Colors.CYAN}{email}{Colors.END} {Colors.GREEN}(activated){Colors.END}")
                    click.echo(f"   You can now use {Colors.BOLD}co/{Colors.END} models without API keys!")
                    return
                elif data.get("status") == "pending":
                    # Still waiting
                    time.sleep(5)
                    continue
                else:
                    click.echo(f"{Colors.RED}❌ Authentication failed: {data.get('error', 'Unknown error')}{Colors.END}")
                    return
        except requests.exceptions.ConnectionError:
            click.echo(f"{Colors.RED}❌ Cannot connect to authentication server{Colors.END}")
            click.echo(f"{Colors.YELLOW}Please check your internet connection and try again.{Colors.END}")
            return
        except Exception as e:
            click.echo(f"{Colors.RED}❌ Error: {e}{Colors.END}")
            return
    
    click.echo(f"{Colors.YELLOW}⏱️ Authentication timed out. Please try again.{Colors.END}")


def handle_register():
    """Register/authenticate in headless mode (no browser needed).
    
    This command will:
    1. Load your agent's keys from .co/keys/
    2. Sign an authentication message
    3. Directly authenticate with the backend
    4. Save the token for future use
    """
    # Check if we're in a ConnectOnion project
    co_dir = Path(".co")
    if not co_dir.exists():
        click.echo(f"{Colors.RED}❌ Not in a ConnectOnion project!{Colors.END}")
        click.echo(f"{Colors.YELLOW}Run 'co init' first to initialize a project.{Colors.END}")
        return
    
    # Load agent keys
    try:
        addr_data = address.load(co_dir)
        if not addr_data:
            click.echo(f"{Colors.RED}❌ No agent keys found!{Colors.END}")
            click.echo(f"{Colors.YELLOW}Run 'co init' to generate agent keys.{Colors.END}")
            return
    except Exception as e:
        click.echo(f"{Colors.RED}❌ Error loading keys: {e}{Colors.END}")
        return
    
    public_key = addr_data["address"]
    signing_key = addr_data["signing_key"]
    
    click.echo(f"{Colors.CYAN}🔐 Registering with OpenOnion (headless mode)...{Colors.END}")
    click.echo(f"   Agent: {Colors.BOLD}{addr_data['short_address']}{Colors.END}")
    
    # Create signed authentication message
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = address.sign(addr_data, message.encode()).hex()
    
    # Directly call auth endpoint
    auth_url = "https://oo.openonion.ai/auth"
    
    click.echo(f"\n{Colors.CYAN}📡 Authenticating directly...{Colors.END}")
    
    try:
        response = requests.post(auth_url, json={
            "public_key": public_key,
            "message": message,
            "signature": signature
        })
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("token")
            
            if token:
                email = data.get("email_address") or f"{public_key[:10]}@mail.openonion.ai"
                
                # Save token and email to config.toml
                config_path = co_dir / "config.toml"
                config = toml.load(config_path)
                config["auth"] = {"token": token}
                if "agent" not in config:
                    config["agent"] = {}
                config["agent"]["email"] = email
                config["agent"]["email_active"] = True  # Activate email after authentication
                
                with open(config_path, "w") as f:
                    toml.dump(config, f)
                
                click.echo(f"\n{Colors.GREEN}✅ Registration successful!{Colors.END}")
                click.echo(f"   Token saved to .co/config.toml")
                click.echo(f"   📧 Your email: {Colors.CYAN}{email}{Colors.END} {Colors.GREEN}(activated){Colors.END}")
                click.echo(f"   You can now use {Colors.BOLD}co/{Colors.END} models without API keys!")
                click.echo(f"\n{Colors.CYAN}Example:{Colors.END}")
                click.echo(f"   from connectonion import llm_do")
                click.echo(f"   response = llm_do('Hello', model='co/gpt-4o-mini')")
                return
        else:
            error = response.json().get("detail", "Unknown error")
            click.echo(f"\n{Colors.RED}❌ Registration failed: {error}{Colors.END}")
            
    except requests.exceptions.ConnectionError:
        click.echo(f"{Colors.RED}❌ Cannot connect to authentication server{Colors.END}")
        click.echo(f"{Colors.YELLOW}Please check your internet connection and try again.{Colors.END}")
    except Exception as e:
        click.echo(f"\n{Colors.RED}❌ Error during registration: {e}{Colors.END}")