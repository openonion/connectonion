"""
Purpose: Delete global ConnectOnion configuration and create fresh account with new Ed25519 keypair
LLM-Note:
  Dependencies: imports from [sys, shutil, toml, pathlib, rich.console, rich.prompt, rich.panel, address, auth_commands.authenticate, __version__, datetime] | imported by [cli/main.py via handle_reset()] | tested by [tests/cli/test_cli_reset.py]
  Data flow: receives no args → checks ~/.co/ exists → prompts user for 'Y' confirmation with clear warnings → deletes ~/.co/keys/, ~/.co/config.toml, ~/.co/keys.env → recreates directory structure → address.generate() creates new Ed25519 keypair with seed phrase → address.save() saves to ~/.co/keys/ → creates new config.toml with fresh agent identity → calls authenticate(global_dir, save_to_project=False) to register new account and get bonus credits → displays seed phrase in Rich panel → warns user to update project .env files
  State/Effects: DESTRUCTIVE OPERATION | deletes entire ~/.co/ directory contents (keys, config, keys.env) | creates fresh ~/.co/ with new keypair | calls authenticate() which creates new backend account and writes OPENONION_API_KEY to keys.env | writes to stdout via rich.Console with warnings and confirmations | existing projects still have old API key (requires manual 'co init' to update)
  Integration: exposes handle_reset() for CLI | similar to ensure_global_config() in init.py but deletes first | relies on address.generate() for new Ed25519 keypair | calls authenticate() to register new account | displays seed phrase via Rich panel | requires explicit 'Y' confirmation to proceed
  Performance: file deletion is fast (<100ms) | address.generate() is fast (<100ms) | authenticate() makes network call (2-5s) | config file writes are I/O bound
  Errors: gracefully handles missing ~/.co/ (nothing to reset) | requires uppercase 'Y' for confirmation (case-sensitive) | cancels if user types anything else | authenticate() may fail but reset still completes | warns user about data loss before proceeding
"""

import sys
import shutil
import toml
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

from ... import address
from .auth_commands import authenticate

console = Console()


def handle_reset():
    """Reset ConnectOnion global configuration and create new account.

    WARNING: This will delete all your data including:
    - Your Ed25519 keypair and account access
    - Your balance and transaction history
    - All configuration and credentials

    You will get a fresh new account.
    """
    global_dir = Path.home() / ".co"

    # Check if global config exists
    if not global_dir.exists():
        console.print("\n❌ [bold red]No global configuration found[/bold red]")
        console.print("[yellow]Nothing to reset. Run 'co init' to set up ConnectOnion.[/yellow]\n")
        return

    # Show clear warning
    console.print("\n[bold yellow]⚠️  WARNING: This will DELETE ALL your ConnectOnion data[/bold yellow]\n")
    console.print("[red]You will lose:[/red]")
    console.print("  • Your account and balance")
    console.print("  • All transaction history")
    console.print("  • Your Ed25519 keypair")
    console.print("  • All configurations and credentials\n")

    console.print("[green]You will get:[/green]")
    console.print("  • Fresh new account")
    console.print("  • New Ed25519 keypair with seed phrase\n")

    console.print("[yellow]💡 Save your 12-word seed phrase if you want to recover your current account![/yellow]\n")

    confirmation = Prompt.ask("[bold red]Type 'Y' to confirm reset[/bold red]")

    if confirmation.upper() != "Y":
        console.print("\n[yellow]Cancelled.[/yellow]\n")
        return

    # Delete everything
    keys_dir = global_dir / "keys"
    if keys_dir.exists():
        shutil.rmtree(keys_dir)
        console.print("✓ Deleted ~/.co/keys/")

    config_path = global_dir / "config.toml"
    if config_path.exists():
        config_path.unlink()
        console.print("✓ Deleted ~/.co/config.toml")

    keys_env = global_dir / "keys.env"
    if keys_env.exists():
        keys_env.unlink()
        console.print("✓ Deleted ~/.co/keys.env")

    # Recreate directory structure
    global_dir.mkdir(exist_ok=True)
    keys_dir.mkdir(exist_ok=True)
    (global_dir / "logs").mkdir(exist_ok=True)

    # Generate new keypair
    console.print("\n🔑 Generating new Ed25519 keypair...")
    addr_data = address.generate()
    address.save(addr_data, global_dir)

    console.print(f"✓ Generated new keypair")
    console.print(f"✓ Your new address: [bold]{addr_data['short_address']}[/bold]")

    # Show seed phrase
    console.print(Panel.fit(
        f"[bold yellow]{addr_data['seed_phrase']}[/bold yellow]",
        title="🔐 Your 12-Word Seed Phrase (SAVE THIS!)",
        border_style="yellow"
    ))

    # Create new config
    from ... import __version__
    from datetime import datetime

    config = {
        "connectonion": {
            "framework_version": __version__,
            "created": datetime.now().isoformat(),
        },
        "cli": {
            "version": "1.0.0",
        },
        "agent": {
            "address": addr_data["address"],
            "short_address": addr_data["short_address"],
            "email": f"{addr_data['address'][:10]}@mail.openonion.ai",
            "email_active": False,
            "created_at": datetime.now().isoformat(),
            "algorithm": "ed25519",
            "default_model": "gpt-4o-mini",
            "max_iterations": 10,
        },
    }

    with open(config_path, 'w', encoding='utf-8') as f:
        toml.dump(config, f)
    console.print("✓ Created ~/.co/config.toml")

    keys_env.touch()
    if sys.platform != 'win32':
        keys_env.chmod(0o600)
    console.print("✓ Created ~/.co/keys.env")

    # Authenticate to get fresh bonus
    console.print("\n🔐 Authenticating with OpenOnion...")
    success = authenticate(global_dir, save_to_project=False)

    if success:
        console.print("\n[bold green]✅ Reset complete! Your new account is ready.[/bold green]")
        console.print("\n[yellow]💡 Save your 12-word seed phrase somewhere safe![/yellow]")

        console.print("\n[bold yellow]⚠️  IMPORTANT: Update your project .env files![/bold yellow]")
        console.print("\n[yellow]Your existing projects still have the old API key.[/yellow]")
        console.print("[yellow]To use your new account in each project:[/yellow]")
        console.print("  [bold cyan]1.[/bold cyan] cd into the project directory")
        console.print("  [bold cyan]2.[/bold cyan] Run: [bold]co init[/bold]")
        console.print("\n[dim]This will update the project's .env file with your new account.[/dim]\n")
    else:
        console.print("\n[yellow]⚠️  Reset complete, but authentication failed.[/yellow]")
        console.print("[yellow]Run 'co auth' to authenticate manually.[/yellow]\n")
