"""Authentication and registration commands for ConnectOnion CLI."""

import time
import toml
import requests
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel

from ... import address

console = Console()


def _save_api_key_to_env(co_dir: Path, api_key: str, agent_email: str = None) -> None:
    """Save OPENONION_API_KEY and AGENT_EMAIL to .env file.

    Args:
        co_dir: Path to .co directory
        api_key: The API key/token to save
        agent_email: The agent email address to save (optional)
    """
    env_file = co_dir.parent / ".env"
    env_lines = []
    key_found = False
    email_found = False

    # Read existing .env if it exists
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                if line.strip().startswith("OPENONION_API_KEY="):
                    env_lines.append(f"OPENONION_API_KEY={api_key}\n")
                    key_found = True
                elif line.strip().startswith("AGENT_EMAIL=") and agent_email:
                    env_lines.append(f"AGENT_EMAIL={agent_email}\n")
                    email_found = True
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

    # Write .env file
    with open(env_file, "w") as f:
        f.writelines(env_lines)

    # Make sure file permissions are restrictive
    env_file.chmod(0o600)


def authenticate(co_dir: Path, save_to_project: bool = True) -> bool:
    """Authenticate with OpenOnion API directly.

    Args:
        co_dir: Path to .co directory with keys
        save_to_project: Whether to also save token to current directory's .env

    Returns:
        True if authentication successful, False otherwise
    """
    # Load agent keys - let it fail naturally if there's a problem
    addr_data = address.load(co_dir)
    if not addr_data:
        console.print("❌ No agent keys found!", style="red")
        return False

    public_key = addr_data["address"]

    console.print("🔐 Authenticating with OpenOnion...", style="cyan")
    console.print(f"   Agent: [bold]{addr_data['short_address']}[/bold]")

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
        is_global = co_dir == Path.home() / ".co"

        if is_global:
            # Save to global keys.env
            global_keys_env = co_dir / "keys.env"
            env_lines = []
            key_found = False
            email_found = False

            # Read existing keys.env if it exists
            if global_keys_env.exists():
                with open(global_keys_env, "r") as f:
                    for line in f:
                        if line.strip().startswith("OPENONION_API_KEY="):
                            env_lines.append(f"OPENONION_API_KEY={token}\n")
                            key_found = True
                        elif line.strip().startswith("AGENT_EMAIL="):
                            env_lines.append(f"AGENT_EMAIL={agent_email}\n")
                            email_found = True
                        else:
                            env_lines.append(line)

            # Add key if not found
            if not key_found:
                if env_lines and not env_lines[-1].endswith("\n"):
                    env_lines.append("\n")
                env_lines.append(f"OPENONION_API_KEY={token}\n")

            # Add email if not found
            if not email_found:
                env_lines.append(f"AGENT_EMAIL={agent_email}\n")

            # Write global keys.env file
            with open(global_keys_env, "w") as f:
                f.writelines(env_lines)
            global_keys_env.chmod(0o600)

            console.print("✅ Saved token and email to ~/.co/keys.env", style="green")

            # Also save to current directory's .env (always create if using global keys and save_to_project=True)
            if save_to_project:
                _save_api_key_to_env(Path(".co") if Path(".co").exists() else co_dir, token, agent_email)
                console.print("✅ Also saved to local .env file", style="green")
        else:
            # Save to local project .env
            _save_api_key_to_env(co_dir, token, agent_email)

        # Save email and activation status to config
        config_path = co_dir / "config.toml"
        config = toml.load(config_path) if config_path.exists() else {}
        if "agent" not in config:
            config["agent"] = {}
        config["agent"]["email"] = agent_email
        config["agent"]["email_active"] = True

        with open(config_path, "w") as f:
            toml.dump(config, f)

        # Display comprehensive auth success info
        console.print("\n✅ [bold green]Authentication successful![/bold green]")

        # Build info string based on available data
        info_lines = [
            f"[cyan]Agent ID:[/cyan] {addr_data['short_address']}",
            f"[cyan]Email:[/cyan] {agent_email}",
        ]

        if email_info:
            info_lines.append(f"[cyan]Email Tier:[/cyan] {email_info.get('tier', 'free').capitalize()}")
            info_lines.append(f"[cyan]Emails/Month:[/cyan] {email_info.get('quota', 100):,}")

        if user:
            info_lines.append(f"[cyan]Balance:[/cyan] ${user.get('balance_usd', 0.0):.4f}")
            info_lines.append(f"[cyan]Total Spent:[/cyan] ${user.get('total_cost_usd', 0.0):.4f}")
            info_lines.append(f"[cyan]New User:[/cyan] {'Yes' if user.get('is_new_user') else 'No'}")

        info_lines.append(f"[cyan]API Key:[/cyan] {token[:20]}...")

        console.print(Panel.fit(
            "\n".join(info_lines),
            title="🎯 Account Information",
            border_style="green"
        ))

        # Show additional tips based on tier
        console.print("\n[yellow]💡 Tips:[/yellow]")
        console.print("   • Your API key has been saved to .env")
        console.print("   • You can use managed models like 'co/gpt-4o' and 'co/o4-mini' in your agents")

        if email_info and email_info.get('tier') == 'free':
            console.print("   • Upgrade to Plus/Pro tier for more emails and custom domains")
            console.print("   • Visit https://oo.openonion.ai to manage your account")

        if user and user.get('balance_usd', 0) <= 0:
            console.print("   • Purchase tokens at https://oo.openonion.ai to use managed LLM models")

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

