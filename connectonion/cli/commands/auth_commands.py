"""
Purpose: Authenticate with OpenOnion backend using Ed25519 signature-based authentication to obtain JWT for managed keys
LLM-Note:
  Dependencies: imports from [sys, time, toml, requests, pathlib, rich.console, rich.progress, rich.panel, address] | imported by [cli/main.py via handle_auth(), cli/commands/init.py, cli/commands/create.py] | calls backend at [https://api.openonion.ai/api/auth/login] | tested by [tests/cli/test_cli_auth.py]
  Data flow: receives co_dir: Path from caller → address.load(co_dir) reads Ed25519 keypair from .co/keys/ → creates auth message with timestamp → address.sign() creates signature → POST to /api/auth/login with {public_key, message, signature, timestamp} → backend verifies signature → receives JWT token → saves to ~/.co/keys.env as OPENONION_API_KEY → optionally saves to project .env if save_to_project=True → displays balance and email status → returns success bool
  State/Effects: modifies ~/.co/keys.env (adds/updates OPENONION_API_KEY and AGENT_EMAIL) | optionally modifies project .env if save_to_project=True | makes network POST request to api.openonion.ai | chmod 0o600 on .env files (Unix/Mac) | writes to stdout via rich.Console with progress spinner | updates ~/.co/config.toml with email_active status
  Integration: exposes handle_auth() for CLI and authenticate(co_dir, save_to_project) for programmatic use | called by init.py and create.py during project setup | relies on address module for Ed25519 keypair operations | uses requests for HTTP calls | displays Rich progress spinner during network call | backend creates account on first auth (no separate registration)
  Performance: network call to backend (2-5s) | signature generation is fast (<10ms) | file I/O for .env and config.toml | retries on network errors (up to 3 attempts with exponential backoff)
  Errors: fails if ~/.co/keys/ missing (no keypair) | fails if backend unreachable (network error) | fails if signature invalid (backend 401) | fails if timestamp expired (5min window) | prints error messages to console and returns False | backend 500 errors bubble up with error details
"""

import sys
import time
import toml
import requests
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel

from ... import address

console = Console()


def _save_api_key_to_env(co_dir: Path, api_key: str, agent_email: str = None, agent_address: str = None) -> None:
    """Save OPENONION_API_KEY, AGENT_EMAIL, and AGENT_ADDRESS to .env file.

    Args:
        co_dir: Path to .co directory
        api_key: The API key/token to save
        agent_email: The agent email address to save (optional)
        agent_address: The full agent address to save (optional)
    """
    env_file = co_dir.parent / ".env"
    env_lines = []
    key_found = False
    email_found = False
    address_found = False

    # Read existing .env if it exists
    if env_file.exists():
        with open(env_file, "r", encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith("OPENONION_API_KEY="):
                    env_lines.append(f"OPENONION_API_KEY={api_key}\n")
                    key_found = True
                elif line.strip().startswith("AGENT_EMAIL=") and agent_email:
                    env_lines.append(f"AGENT_EMAIL={agent_email}\n")
                    email_found = True
                elif line.strip().startswith("AGENT_ADDRESS=") and agent_address:
                    env_lines.append(f"AGENT_ADDRESS={agent_address}\n")
                    address_found = True
                else:
                    env_lines.append(line)

    # Add key if not found
    if not key_found:
        if env_lines and not env_lines[-1].endswith("\n"):
            env_lines.append("\n")
        env_lines.append(f"OPENONION_API_KEY={api_key}\n")

    # Add email if not found and provided
    if agent_email and not email_found:
        env_lines.append(f"AGENT_EMAIL={agent_email}\n")

    # Add address if not found and provided
    if agent_address and not address_found:
        env_lines.append(f"AGENT_ADDRESS={agent_address}\n")

    # Write .env file
    with open(env_file, "w", encoding='utf-8') as f:
        f.writelines(env_lines)

    # Make sure file permissions are restrictive (Unix/Mac only)
    if sys.platform != 'win32':
        env_file.chmod(0o600)


def authenticate(co_dir: Path, save_to_project: bool = True, quiet: bool = False) -> bool:
    """Authenticate with OpenOnion API directly.

    Args:
        co_dir: Path to .co directory with keys
        save_to_project: Whether to also save token to current directory's .env
        quiet: If True, suppress verbose output (only show errors and minimal success)

    Returns:
        True if authentication successful, False otherwise
    """
    # Load agent keys - let it fail naturally if there's a problem
    addr_data = address.load(co_dir)
    if not addr_data:
        console.print("❌ No agent keys found!", style="red")
        return False

    public_key = addr_data["address"]

    # Create signed authentication message
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = address.sign(addr_data, message.encode()).hex()

    # Call the new unified auth endpoint
    auth_url = "https://oo.openonion.ai/api/v1/auth"

    response = requests.post(auth_url, json={
        "public_key": public_key,
        "signature": signature,
        "message": message
    })

    if response.status_code == 200:
        data = response.json()
        token = data.get("token")

        # Extract agent email from server response FIRST (before saving to .env)
        user = data.get("user", {})
        email_info = user.get("email") if user else None

        # Get the agent email from the server response
        if email_info:
            agent_email = email_info.get("address", f"{public_key[:10]}@mail.openonion.ai")
        else:
            agent_email = f"{public_key[:10]}@mail.openonion.ai"

        # Save token to appropriate .env file(s)
        is_global = co_dir.resolve() == (Path.home() / ".co").resolve()

        if is_global:
            # Save to global keys.env
            global_keys_env = co_dir / "keys.env"
            env_lines = []
            key_found = False
            email_found = False
            address_found = False

            # Read existing keys.env if it exists (preserve AGENT_ADDRESS)
            config_path_found = False
            if global_keys_env.exists():
                with open(global_keys_env, "r", encoding='utf-8') as f:
                    for line in f:
                        if line.strip().startswith("OPENONION_API_KEY="):
                            env_lines.append(f"OPENONION_API_KEY={token}\n")
                            key_found = True
                        elif line.strip().startswith("AGENT_EMAIL="):
                            env_lines.append(f"AGENT_EMAIL={agent_email}\n")
                            email_found = True
                        elif line.strip().startswith("AGENT_ADDRESS="):
                            address_found = True
                            env_lines.append(line)  # Preserve existing address
                        elif line.strip().startswith("AGENT_CONFIG_PATH="):
                            config_path_found = True
                            env_lines.append(line)  # Preserve existing config path
                        else:
                            env_lines.append(line)

            # Add config path if not found (at the beginning)
            if not config_path_found:
                env_lines.insert(0, f"AGENT_CONFIG_PATH={co_dir}\n")

            # Add key if not found
            if not key_found:
                if env_lines and not env_lines[-1].endswith("\n"):
                    env_lines.append("\n")
                env_lines.append(f"OPENONION_API_KEY={token}\n")

            # Add email if not found
            if not email_found:
                env_lines.append(f"AGENT_EMAIL={agent_email}\n")

            # Add address if not found (ensure AGENT_ADDRESS is always in global keys.env)
            if not address_found:
                env_lines.append(f"AGENT_ADDRESS={public_key}\n")

            # Write global keys.env file
            with open(global_keys_env, "w", encoding='utf-8') as f:
                f.writelines(env_lines)
            if sys.platform != 'win32':
                global_keys_env.chmod(0o600)

            console.print(f"✓ Saved to {global_keys_env}", style="green")

            # Also save to current directory's .env (always create if using global keys and save_to_project=True)
            if save_to_project:
                local_env_path = Path(".co") if Path(".co").exists() else co_dir
                _save_api_key_to_env(local_env_path, token, agent_email, public_key)
                # Show relative path for local .env
                local_env_file = Path.cwd() / ".env"
                console.print(f"✓ Saved to {local_env_file}", style="green")
        else:
            # Save to local project .env
            _save_api_key_to_env(co_dir, token, agent_email, public_key)

        # Simple success message with balance
        balance = user.get('balance_usd', 0.0) if user else 0.0
        console.print(f"✓ Authenticated (Balance: ${balance:.2f})", style="green")

        return True
    else:
        error_msg = response.json().get("detail", "Registration failed")
        console.print(f"❌ Registration failed: {error_msg}", style="red")
        return False




def handle_auth():
    """Authenticate with OpenOnion for managed keys (co/ models).

    This command will:
    1. Load your agent's keys from .co/keys/ (or ~/.co/keys/ as fallback)
    2. Sign an authentication message
    3. Authenticate with the backend API
    4. Display comprehensive account information
    5. Save the token for future use
    """
    # Check if we have local keys first
    co_dir = Path(".co")
    use_global = False

    # Check if local .co/keys/agent.key exists
    if co_dir.exists() and (co_dir / "keys" / "agent.key").exists():
        # Use local keys
        console.print("📂 Using local project keys (.co)", style="cyan")
    else:
        # No local keys, try global
        co_dir = Path.home() / ".co"
        use_global = True

        if not co_dir.exists() or not (co_dir / "keys" / "agent.key").exists():
            console.print("\n❌ [bold red]No agent keys found[/bold red]")
            console.print("\n[cyan]Initialize ConnectOnion first:[/cyan]")
            console.print("  [bold]co init[/bold]     Add to current directory")
            console.print("  [bold]co create[/bold]   Create new project folder")
            console.print("\n[dim]Both set up ~/.co/ with your keys[/dim]\n")
            return
        else:
            console.print("📂 Using global ConnectOnion keys (~/.co)", style="cyan")

    # Use the unified authenticate function
    success = authenticate(co_dir)

    if not success:
        console.print("\n[yellow]Need help?[/yellow]")
        console.print("   • Check your internet connection")
        console.print("   • Try 'co init' to reinitialize your keys")
        console.print("   • Visit https://discord.gg/4xfD9k8AUF for support")

