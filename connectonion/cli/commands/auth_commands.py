"""
Purpose: Authenticate with OpenOnion backend using Ed25519 signature-based authentication to obtain JWT for managed keys
LLM-Note:
  Dependencies: imports from [sys, time, yaml, requests, pathlib, rich.console, rich.progress, rich.panel, address] | imported by [cli/main.py via handle_auth(), cli/commands/init.py, cli/commands/create.py] | calls backend at [https://oo.openonion.ai/api/v1/auth] | tested by [tests/e2e/cli/test_cli_auth.py]
  Data flow: receives co_dir: Path from caller → address.load(co_dir) reads Ed25519 keypair from .co/keys/ → creates auth message with timestamp → address.sign() creates signature → POST to /api/v1/auth with {public_key, message, signature, timestamp} → backend verifies signature → receives JWT token → saves to ~/.co/keys.env as OPENONION_API_KEY → optionally saves to project .env if save_to_project=True → displays balance and email status → returns success bool
  State/Effects: modifies ~/.co/keys.env (adds/updates OPENONION_API_KEY and AGENT_EMAIL) | optionally modifies project .env if save_to_project=True | makes network POST request to oo.openonion.ai | chmod 0o600 on .env files (Unix/Mac) | writes to stdout via rich.Console with progress spinner | updates ~/.co/keys.env with IS_EMAIL_ACTIVE
  Integration: exposes handle_auth() for CLI and authenticate(co_dir, save_to_project) for programmatic use | called by init.py and create.py during project setup | relies on address module for Ed25519 keypair operations | uses requests for HTTP calls | displays Rich progress spinner during network call | backend creates account on first auth (no separate registration)
  Performance: network call to backend (2-5s) | signature generation is fast (<10ms) | file I/O for .env and keys.env | retries on network errors (up to 3 attempts with exponential backoff)
  Errors: fails if ~/.co/keys/ missing (no keypair) | fails if backend unreachable (network error) | fails if signature invalid (backend 401) | fails if timestamp expired (5min window) | prints error messages to console and returns False | backend 500 errors bubble up with error details
"""

import sys
import time
import requests
import json
import webbrowser
import os
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from dotenv import load_dotenv

from ... import address
from .project_cmd_lib import load_api_key, upsert_env

console = Console()


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

    try:
        response = requests.post(auth_url, json={
            "public_key": public_key,
            "signature": signature,
            "message": message
        }, timeout=15)
    except requests.exceptions.RequestException:
        # First-run must survive a bad/offline network: a traceback wall here used to
        # abort `co init` before any scaffolding. One friendly line, keep going.
        console.print("⚠️  Could not reach the ConnectOnion backend — continuing offline.", style="yellow")
        console.print("   Run [bold]co auth[/bold] once you're online to activate co/* models and agent email.", style="yellow")
        return False

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
            # Note: AGENT_ADDRESS and AGENT_CONFIG_PATH are NOT overwritten here —
            # they are set by ensure_global_config() / co reset only.
            # upsert_env will add them if missing but won't touch existing values.
            global_keys_env = co_dir / "keys.env"
            upsert_env(global_keys_env, {
                "OPENONION_API_KEY": token,
                "AGENT_EMAIL": agent_email,
                "IS_EMAIL_ACTIVE": "true",
            })
            # Ensure AGENT_ADDRESS and AGENT_CONFIG_PATH exist (append-only, don't overwrite)
            if global_keys_env.exists():
                existing = global_keys_env.read_text()
                append_lines = []
                if 'AGENT_ADDRESS=' not in existing:
                    append_lines.append(f"AGENT_ADDRESS={public_key}\n")
                if 'AGENT_CONFIG_PATH=' not in existing:
                    append_lines.append(f"AGENT_CONFIG_PATH={co_dir}\n")
                if append_lines:
                    with open(global_keys_env, 'a', encoding='utf-8') as f:
                        f.writelines(append_lines)

            console.print(f"✓ Saved to {global_keys_env}", style="green")

            # Also save to current directory's .env (always create if using global keys and save_to_project=True)
            if save_to_project:
                local_env_path = Path(".co") if Path(".co").exists() else co_dir
                upsert_env(local_env_path.parent / ".env", {
                    "OPENONION_API_KEY": token,
                    "AGENT_EMAIL": agent_email,
                    "AGENT_ADDRESS": public_key,
                })
                local_env_file = Path.cwd() / ".env"
                console.print(f"✓ Saved to {local_env_file}", style="green")
        else:
            # Save to local project .env
            upsert_env(co_dir.parent / ".env", {
                "OPENONION_API_KEY": token,
                "AGENT_EMAIL": agent_email,
                "AGENT_ADDRESS": public_key,
            })

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
            # Auto-create global config with keypair
            console.print("\n[cyan]No agent keys found. Setting up global configuration...[/cyan]")
            from .project_cmd_lib import ensure_global_config
            ensure_global_config()
            co_dir = Path.home() / ".co"
        else:
            console.print("📂 Using global ConnectOnion keys (~/.co)", style="cyan")

    # Use the unified authenticate function
    success = authenticate(co_dir)

    if not success:
        console.print("\n[yellow]Need help?[/yellow]")
        console.print("   • Check your internet connection")
        console.print("   • Try 'co init' to reinitialize your keys")
        console.print("   • Visit https://discord.gg/4xfD9k8AUF for support")


def _save_google_to_env(env_file: Path, credentials: dict) -> None:
    """Save Google OAuth credentials to .env file."""
    upsert_env(env_file, {
        "GOOGLE_ACCESS_TOKEN": credentials['access_token'],
        "GOOGLE_REFRESH_TOKEN": credentials['refresh_token'],
        "GOOGLE_TOKEN_EXPIRES_AT": credentials['expires_at'],
        "GOOGLE_SCOPES": credentials['scopes'],
        "GOOGLE_EMAIL": credentials['google_email'],
    }, strip_prefix="GOOGLE_")


def handle_google_auth():
    """Authenticate with Google OAuth for Gmail/Calendar access."""

    # Check if user is authenticated with OpenOnion first
    api_key = load_api_key()
    if not api_key:
        console.print("\n❌ [bold red]Not authenticated with OpenOnion[/bold red]")
        console.print("\n[cyan]Authenticate first:[/cyan]")
        console.print("  [bold]co auth[/bold]     Get your OpenOnion API key\n")
        return

    api_url = "https://oo.openonion.ai/api/v1/oauth"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Clear any existing connection first - this ensures we wait for NEW OAuth to complete
    # (otherwise /google/status returns connected=true immediately from old credentials)
    requests.delete(f"{api_url}/google/revoke", headers=headers)

    # Get OAuth URL
    console.print("🔑 Initializing Google OAuth...", style="cyan")

    response = requests.get(f"{api_url}/google/init", headers=headers)
    if response.status_code != 200:
        console.print(f"\n❌ Failed to initialize OAuth: {response.text}", style="red")
        return

    auth_url = response.json()['auth_url']

    # Open browser
    console.print(f"\n🌐 Opening browser for Google authentication...")
    console.print(f"    URL: {auth_url}\n", style="dim")

    webbrowser.open(auth_url)

    # Poll for completion
    console.print("⏳ Waiting for authorization...", style="yellow")
    console.print("   (Complete the authorization in your browser)\n", style="dim")

    max_attempts = 60  # 5 minutes (5 second intervals)
    for attempt in range(max_attempts):
        time.sleep(5)

        status_response = requests.get(f"{api_url}/google/status", headers=headers)
        if status_response.status_code == 200:
            status = status_response.json()
            if status.get('connected'):
                console.print("✓ Authorization successful!", style="green")
                break
    else:
        console.print("\n❌ Authorization timed out", style="red")
        console.print("Please try again with: [bold]co auth google[/bold]\n")
        return

    # Get credentials
    creds_response = requests.get(f"{api_url}/google/credentials", headers=headers)
    if creds_response.status_code != 200:
        console.print(f"\n❌ Failed to get credentials: {creds_response.text}", style="red")
        return

    credentials = creds_response.json()

    # Save credentials
    console.print("\n💾 Saving credentials...", style="cyan")

    # Save to global ~/.co/keys.env
    global_keys_env = Path.home() / ".co" / "keys.env"
    if global_keys_env.exists():
        _save_google_to_env(global_keys_env, credentials)
        console.print(f"   ✓ Saved to {global_keys_env}", style="green")

    # Save to local .env
    local_env = Path(".env")
    _save_google_to_env(local_env, credentials)
    console.print(f"   ✓ Saved to {local_env.absolute()}", style="green")

    # Success message
    console.print(f"\n✅ [bold green]Google account connected![/bold green]")
    console.print(f"   Email: {credentials['google_email']}", style="green")
    console.print(f"\n📧 You can now use Google tools in your agents:")
    console.print(f"   [dim]from connectonion.tools import gmail_send[/dim]")
    console.print(f"   [dim]agent = Agent('assistant', tools=[gmail_send])[/dim]\n")


def _save_microsoft_to_env(env_file: Path, credentials: dict) -> None:
    """Save Microsoft OAuth credentials to .env file."""
    upsert_env(env_file, {
        "MICROSOFT_ACCESS_TOKEN": credentials['access_token'],
        "MICROSOFT_REFRESH_TOKEN": credentials['refresh_token'],
        "MICROSOFT_TOKEN_EXPIRES_AT": credentials['expires_at'],
        "MICROSOFT_SCOPES": credentials['scopes'],
        "MICROSOFT_EMAIL": credentials['microsoft_email'],
    }, strip_prefix="MICROSOFT_")


def handle_microsoft_auth():
    """Authenticate with Microsoft OAuth for Outlook/Calendar access."""

    # Check if user is authenticated with OpenOnion first
    api_key = load_api_key()
    if not api_key:
        console.print("\n❌ [bold red]Not authenticated with OpenOnion[/bold red]")
        console.print("\n[cyan]Authenticate first:[/cyan]")
        console.print("  [bold]co auth[/bold]     Get your OpenOnion API key\n")
        return

    api_url = "https://oo.openonion.ai/api/v1/oauth"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Clear any existing connection first
    requests.delete(f"{api_url}/microsoft/revoke", headers=headers)

    # Get OAuth URL
    console.print("🔑 Initializing Microsoft OAuth...", style="cyan")

    response = requests.get(f"{api_url}/microsoft/init", headers=headers)
    if response.status_code != 200:
        console.print(f"\n❌ Failed to initialize OAuth: {response.text}", style="red")
        return

    auth_url = response.json()['auth_url']

    # Open browser
    console.print(f"\n🌐 Opening browser for Microsoft authentication...")
    console.print(f"    URL: {auth_url}\n", style="dim")

    webbrowser.open(auth_url)

    # Poll for completion
    console.print("⏳ Waiting for authorization...", style="yellow")
    console.print("   (Complete the authorization in your browser)\n", style="dim")

    max_attempts = 60  # 5 minutes (5 second intervals)
    for attempt in range(max_attempts):
        time.sleep(5)

        status_response = requests.get(f"{api_url}/microsoft/status", headers=headers)
        if status_response.status_code == 200:
            status = status_response.json()
            if status.get('connected'):
                console.print("✓ Authorization successful!", style="green")
                break
    else:
        console.print("\n❌ Authorization timed out", style="red")
        console.print("Please try again with: [bold]co auth microsoft[/bold]\n")
        return

    # Get credentials
    creds_response = requests.get(f"{api_url}/microsoft/credentials", headers=headers)
    if creds_response.status_code != 200:
        console.print(f"\n❌ Failed to get credentials: {creds_response.text}", style="red")
        return

    credentials = creds_response.json()

    # Save credentials
    console.print("\n💾 Saving credentials...", style="cyan")

    # Save to global ~/.co/keys.env
    global_keys_env = Path.home() / ".co" / "keys.env"
    if global_keys_env.exists():
        _save_microsoft_to_env(global_keys_env, credentials)
        console.print(f"   ✓ Saved to {global_keys_env}", style="green")

    # Save to local .env
    local_env = Path(".env")
    _save_microsoft_to_env(local_env, credentials)
    console.print(f"   ✓ Saved to {local_env.absolute()}", style="green")

    # Success message
    console.print(f"\n✅ [bold green]Microsoft account connected![/bold green]")
    console.print(f"   Email: {credentials['microsoft_email']}", style="green")
    console.print(f"\n📧 You can now use Microsoft tools in your agents:")
    console.print(f"   [dim]from connectonion import Outlook, MicrosoftCalendar[/dim]")
    console.print(f"   [dim]agent = Agent('assistant', tools=[Outlook()])[/dim]\n")

