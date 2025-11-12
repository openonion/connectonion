"""
Purpose: Diagnose ConnectOnion installation and configuration issues
LLM-Note:
  Dependencies: imports from [sys, os, shutil, pathlib, requests, rich.console, rich.panel, rich.table, __version__] | imported by [cli/main.py via handle_doctor()] | checks local files and backend connectivity
  Data flow: receives no args → checks system info → checks config files → checks API key → tests backend connectivity → displays results with ✓/✗ indicators
  State/Effects: no state modifications | reads from filesystem | makes HTTP request | writes to stdout via rich.Console
  Integration: exposes handle_doctor() for CLI | helps users self-diagnose setup issues
  Performance: fast local checks (<100ms) | network check to backend (1-2s)
  Errors: lets errors crash naturally - no try-except unless absolutely needed
"""

import sys
import os
import shutil
from pathlib import Path
import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


def handle_doctor():
    """Run comprehensive diagnostics on ConnectOnion installation."""
    from ... import __version__

    console.print("\n[bold cyan]🔍 ConnectOnion Diagnostics[/bold cyan]\n")

    # System checks
    system_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    system_table.add_column("Check", style="cyan")
    system_table.add_column("Status")

    # Version
    system_table.add_row("Version", f"[green]✓[/green] {__version__}")

    # Python
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    python_path = sys.executable
    system_table.add_row("Python", f"[green]✓[/green] {python_version}")
    system_table.add_row("Python Path", f"[dim]{python_path}[/dim]")

    # Virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    venv_status = "[green]✓[/green] Virtual environment" if in_venv else "[yellow]○[/yellow] Global Python"
    system_table.add_row("Environment", venv_status)
    if in_venv:
        system_table.add_row("Venv Path", f"[dim]{sys.prefix}[/dim]")

    # Command location
    co_path = shutil.which('co')
    if co_path:
        system_table.add_row("Command", f"[green]✓[/green] {co_path}")
    else:
        system_table.add_row("Command", "[red]✗[/red] 'co' not found in PATH")

    # Package location
    import connectonion
    package_path = Path(connectonion.__file__).parent
    system_table.add_row("Package", f"[dim]{package_path}[/dim]")

    console.print(Panel(system_table, title="[bold]System[/bold]", border_style="blue"))
    console.print()

    # Configuration checks
    config_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
    config_table.add_column("Check", style="cyan")
    config_table.add_column("Status")

    # Check for config.toml
    local_config = Path(".co") / "config.toml"
    global_config = Path.home() / ".co" / "config.toml"

    if local_config.exists():
        config_table.add_row("Config", f"[green]✓[/green] {local_config}")
        import toml
        config = toml.load(local_config)
        agent_name = config.get("agent", {}).get("name", "Not set")
        config_table.add_row("Agent Name", f"[dim]{agent_name}[/dim]")
    elif global_config.exists():
        config_table.add_row("Config", f"[green]✓[/green] {global_config}")
    else:
        config_table.add_row("Config", "[yellow]○[/yellow] Not found (optional)")

    # Check for keys
    local_keys = Path(".co") / "keys" / "agent.key"
    global_keys = Path.home() / ".co" / "keys" / "agent.key"

    if local_keys.exists():
        config_table.add_row("Keys", f"[green]✓[/green] {local_keys}")
    elif global_keys.exists():
        config_table.add_row("Keys", f"[green]✓[/green] {global_keys}")
    else:
        config_table.add_row("Keys", "[yellow]○[/yellow] Not found (run 'co auth' to create)")

    # Check for API key
    api_key = os.getenv("OPENONION_API_KEY")
    if api_key:
        api_key_display = f"{api_key[:20]}..." if len(api_key) > 20 else api_key
        config_table.add_row("API Key", f"[green]✓[/green] Found in environment")
        config_table.add_row("Key Preview", f"[dim]{api_key_display}[/dim]")
    else:
        # Check .env files
        from dotenv import load_dotenv
        local_env = Path(".env")
        global_env = Path.home() / ".co" / "keys.env"

        if local_env.exists():
            load_dotenv(local_env)
            api_key = os.getenv("OPENONION_API_KEY")
            if api_key:
                config_table.add_row("API Key", f"[green]✓[/green] Found in .env")

        if not api_key and global_env.exists():
            load_dotenv(global_env)
            api_key = os.getenv("OPENONION_API_KEY")
            if api_key:
                config_table.add_row("API Key", f"[green]✓[/green] Found in ~/.co/keys.env")

        if not api_key:
            config_table.add_row("API Key", "[yellow]○[/yellow] Not configured (run 'co auth')")

    console.print(Panel(config_table, title="[bold]Configuration[/bold]", border_style="green"))
    console.print()

    # Connectivity checks (only if API key exists)
    if api_key:
        connectivity_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        connectivity_table.add_column("Check", style="cyan")
        connectivity_table.add_column("Status")

        # Check backend reachability
        response = requests.get("https://oo.openonion.ai/health", timeout=5)
        if response.status_code == 200:
            connectivity_table.add_row("Backend", "[green]✓[/green] https://oo.openonion.ai")
        else:
            connectivity_table.add_row("Backend", f"[yellow]⚠[/yellow] Status {response.status_code}")

        # Check authentication (if keys exist)
        if local_keys.exists() or global_keys.exists():
            from ... import address
            import time

            co_dir = Path(".co") if local_keys.exists() else Path.home() / ".co"
            addr_data = address.load(co_dir)

            public_key = addr_data["address"]
            timestamp = int(time.time())
            message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
            signature = address.sign(addr_data, message.encode()).hex()

            response = requests.post(
                "https://oo.openonion.ai/api/v1/auth",
                json={
                    "public_key": public_key,
                    "signature": signature,
                    "message": message
                },
                timeout=5
            )

            if response.status_code == 200:
                connectivity_table.add_row("Authentication", "[green]✓[/green] Valid credentials")
            else:
                connectivity_table.add_row("Authentication", f"[red]✗[/red] Failed (status {response.status_code})")

        console.print(Panel(connectivity_table, title="[bold]Connectivity[/bold]", border_style="magenta"))
        console.print()

    console.print("[bold green]✅ Diagnostics complete![/bold green]\n")
    console.print("[dim]Run 'co auth' if you need to authenticate[/dim]\n")
