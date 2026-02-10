"""Show and manage agent keys and credentials."""

import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from dotenv import load_dotenv

console = Console()


def _find_co_dir() -> Path:
    """Find the .co directory (local first, then global)."""
    local = Path(".co")
    if local.exists() and (local / "keys" / "agent.key").exists():
        return local

    global_dir = Path.home() / ".co"
    if global_dir.exists() and (global_dir / "keys" / "agent.key").exists():
        return global_dir

    return None


def _load_env_vars() -> dict:
    """Load all relevant env vars from .env files."""
    # Load global first, then local (local overrides)
    global_env = Path.home() / ".co" / "keys.env"
    if global_env.exists():
        load_dotenv(global_env, override=False)

    local_env = Path(".env")
    if local_env.exists():
        load_dotenv(local_env, override=True)

    return {
        "OPENONION_API_KEY": os.getenv("OPENONION_API_KEY"),
        "AGENT_ADDRESS": os.getenv("AGENT_ADDRESS"),
        "AGENT_EMAIL": os.getenv("AGENT_EMAIL"),
        "GOOGLE_EMAIL": os.getenv("GOOGLE_EMAIL"),
        "GOOGLE_ACCESS_TOKEN": os.getenv("GOOGLE_ACCESS_TOKEN"),
        "GOOGLE_REFRESH_TOKEN": os.getenv("GOOGLE_REFRESH_TOKEN"),
        "MICROSOFT_EMAIL": os.getenv("MICROSOFT_EMAIL"),
        "MICROSOFT_ACCESS_TOKEN": os.getenv("MICROSOFT_ACCESS_TOKEN"),
        "MICROSOFT_REFRESH_TOKEN": os.getenv("MICROSOFT_REFRESH_TOKEN"),
    }


def _mask(value: str, show: int = 8) -> str:
    """Mask a secret, showing only first N chars."""
    if not value:
        return ""
    if len(value) <= show:
        return value
    return f"{value[:show]}...{'*' * 12}"


def _short_path(p: Path) -> str:
    """Shorten path by replacing home dir with ~."""
    resolved = str(p.resolve())
    home = str(Path.home())
    if resolved.startswith(home):
        return "~" + resolved[len(home):]
    return resolved


def _source_label(co_dir: Path) -> str:
    """Return human-readable source label for where keys are loaded from."""
    if co_dir.resolve() == (Path.home() / ".co").resolve():
        return "~/.co (global)"
    return f"{co_dir} (project)"


def handle_keys(reveal: bool = False):
    """Show all agent keys and credentials.

    Args:
        reveal: If True, show full values instead of masked
    """
    from ... import address

    co_dir = _find_co_dir()
    if not co_dir:
        console.print("\n[red]No agent keys found.[/red]")
        console.print("[cyan]Run 'co init' or 'co create' first.[/cyan]\n")
        return

    addr_data = address.load(co_dir)
    if not addr_data:
        console.print("\n[red]Failed to load keys.[/red]\n")
        return

    env_vars = _load_env_vars()

    # --- Identity Table ---
    id_table = Table(show_header=False, box=None, padding=(0, 2))
    id_table.add_column("key", style="cyan", min_width=14)
    id_table.add_column("value")

    id_table.add_row("Address", addr_data["address"])
    id_table.add_row("Short ID", addr_data["short_address"])
    id_table.add_row("Email", addr_data.get("email", "N/A"))
    id_table.add_row("Source", _source_label(co_dir))
    id_table.add_row("Key File", _short_path(co_dir / "keys" / "agent.key"))

    console.print()
    console.print(Panel(id_table, title="[bold]Identity[/bold]", border_style="cyan"))

    # --- Secrets Table ---
    sec_table = Table(show_header=False, box=None, padding=(0, 2))
    sec_table.add_column("key", style="cyan", min_width=14)
    sec_table.add_column("value")

    # Recovery phrase
    seed = addr_data.get("seed_phrase")
    if seed:
        sec_table.add_row("Recovery", seed if reveal else _mask(seed, 12))
    else:
        sec_table.add_row("Recovery", "[dim]missing (recovery.txt not found)[/dim]")

    # API key
    api_key = env_vars.get("OPENONION_API_KEY")
    if api_key:
        sec_table.add_row("API Key", api_key if reveal else _mask(api_key))
    else:
        sec_table.add_row("API Key", "[dim]not set — run 'co auth'[/dim]")

    console.print(Panel(sec_table, title="[bold]Secrets[/bold]", border_style="yellow"))

    # --- OAuth Connections ---
    google_email = env_vars.get("GOOGLE_EMAIL")
    microsoft_email = env_vars.get("MICROSOFT_EMAIL")

    if google_email or microsoft_email:
        oauth_table = Table(show_header=False, box=None, padding=(0, 2))
        oauth_table.add_column("key", style="cyan", min_width=14)
        oauth_table.add_column("value")

        if google_email:
            oauth_table.add_row("Google", f"[green]✓[/green] {google_email}")
            if reveal:
                token = env_vars.get("GOOGLE_ACCESS_TOKEN")
                if token:
                    oauth_table.add_row("  Access Token", token)
                refresh = env_vars.get("GOOGLE_REFRESH_TOKEN")
                if refresh:
                    oauth_table.add_row("  Refresh Token", refresh)

        if microsoft_email:
            oauth_table.add_row("Microsoft", f"[green]✓[/green] {microsoft_email}")
            if reveal:
                token = env_vars.get("MICROSOFT_ACCESS_TOKEN")
                if token:
                    oauth_table.add_row("  Access Token", token)
                refresh = env_vars.get("MICROSOFT_REFRESH_TOKEN")
                if refresh:
                    oauth_table.add_row("  Refresh Token", refresh)

        console.print(Panel(oauth_table, title="[bold]OAuth[/bold]", border_style="green"))

    # --- Env file locations ---
    files_table = Table(show_header=False, box=None, padding=(0, 2))
    files_table.add_column("key", style="cyan", min_width=14)
    files_table.add_column("value")

    global_env = Path.home() / ".co" / "keys.env"
    local_env = Path(".env")

    files_table.add_row("Global", f"{'[green]✓[/green]' if global_env.exists() else '[red]✗[/red]'} {_short_path(global_env)}")
    files_table.add_row("Local", f"{'[green]✓[/green]' if local_env.exists() else '[red]✗[/red]'} {_short_path(local_env)}")

    console.print(Panel(files_table, title="[bold]Env Files[/bold]", border_style="dim"))

    # Footer
    if not reveal:
        console.print("[dim]Secrets are masked. Use [bold]co keys --reveal[/bold] to show full values.[/dim]")
    else:
        console.print("[yellow]⚠ Secrets shown in full. Do not share these values.[/yellow]")
    console.print()
