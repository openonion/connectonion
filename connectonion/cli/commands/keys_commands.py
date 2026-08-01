"""
Purpose: Display and manage agent keys, credentials, and OAuth connections with masked/revealed output
LLM-Note:
  Dependencies: imports from [os, pathlib, rich.console, rich.panel, rich.table, dotenv.load_dotenv, address] | imported by [cli/main.py via handle_keys()] | tested by [tests/e2e/cli/test_cli_keys.py]
  Data flow: receives reveal flag (bool) → _find_co_dir() searches for .co/keys/ (local first, then ~/.co) → address.load() reads Ed25519 keypair → _load_env_vars() loads from local .env and global ~/.co/keys.env → _mask() obscures secrets unless --reveal → displays Identity table (address, short ID, email, source, key file) → displays Secrets table (recovery phrase, API key) → displays OAuth table (Google/Microsoft email and tokens if connected) → displays Env Files table (global and local paths with ✓/✗ status)
  State/Effects: no state modifications | reads from .co/keys/agent.key, recovery.txt, .env, ~/.co/keys.env | writes to stdout via rich.Console | does NOT modify any files
  Integration: exposes handle_keys() for CLI | similar to status command but focuses on credentials | relies on address module for keypair loading | uses Rich for formatted panel output | checks env vars in priority order: OPENONION_API_KEY, GOOGLE_EMAIL/tokens, MICROSOFT_EMAIL/tokens | recovery phrase shown if recovery.txt exists
  Performance: file I/O for key loading and env vars (<50ms) | Rich table rendering is fast | no network calls
  Errors: prints message if no .co directory found (run 'co init' or 'co create') | prints message if keys fail to load | gracefully handles missing recovery.txt (shows "missing" message) | gracefully handles missing OAuth tokens (not shown in table) | gracefully handles missing env files (shows red ✗)
"""

import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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


def handle_keys(reveal: bool = False, ssh: bool = False, write: bool = False):
    """Show all agent keys and credentials.

    Args:
        reveal: If True, show full values instead of masked
        ssh: If True, print the SSH public key derived from the recovery phrase
        write: With ssh, also write the private half to ~/.ssh/
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

    if ssh:
        _show_ssh_key(addr_data, write=write)
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
    sec_table.add_column("value", overflow="fold", no_wrap=False)

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
        oauth_table.add_column("value", overflow="fold", no_wrap=False)

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


# Our copy of the derived key, in a directory we own. Not ~/.ssh: a file there
# may be the operator's, and writing only the half that happened to be missing
# once left a private key from one phrase beside a public key from another —
# ssh reports that as "contents do not match public" and refuses, which is a
# confusing way to learn that a server you just paid for is unreachable.
SSH_PRIVATE_KEY = Path.home() / ".co" / "ssh" / "id_ed25519"
SSH_PUBLIC_KEY = Path.home() / ".co" / "ssh" / "id_ed25519.pub"


def per_host_key_path(host: str) -> Path:
    """Where this machine's own key is cached.

    One file per server, named after it. The private key is derived from the
    phrase, so these are a cache and not the original — losing them costs a
    re-derivation, not access.
    """
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in host)
    return SSH_PRIVATE_KEY.parent / f"id_ed25519_{safe}"


def write_per_host_ssh_key(seed_phrase: str, host: str, user: str = "root") -> Path:
    """Cache the key that opens one particular server.

    Same rules as the shared key: both halves together, overwritten from the
    phrase, because a pair where one half is stale cannot authenticate.
    """
    from ... import address

    keys = address.derive_ssh_key(seed_phrase, host=host, user=user)
    path = per_host_key_path(host)

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(keys["private_key"])
    path.chmod(0o600)
    path.with_suffix(".pub").write_text(keys["public_line"] + "\n")
    path.with_suffix(".pub").chmod(0o644)
    return path


def write_derived_ssh_key(seed_phrase: str) -> Path:
    """Write the derived key pair where our own ssh calls look for it.

    Both halves, always together, overwriting whatever was there. Overwriting
    is safe precisely because the key is derived: the phrase is the original,
    the files are a cache of it. Writing one half and keeping the other is what
    produces a pair that cannot authenticate.
    """
    from ... import address

    keys = address.derive_ssh_key(seed_phrase)

    SSH_PRIVATE_KEY.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    SSH_PRIVATE_KEY.write_text(keys["private_key"])
    SSH_PRIVATE_KEY.chmod(0o600)
    SSH_PUBLIC_KEY.write_text(keys["public_line"] + "\n")
    SSH_PUBLIC_KEY.chmod(0o644)
    return SSH_PRIVATE_KEY


def _public_key_identity(public_line: str) -> str:
    """Return the key type and payload, excluding an optional comment."""
    return " ".join(public_line.split()[:2])


def _public_key_from_private(private_path: Path) -> str | None:
    """Read the public half of an OpenSSH private key."""
    try:
        result = subprocess.run(
            ["ssh-keygen", "-yf", str(private_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _backup_path(path: Path) -> Path:
    """Choose a backup name without overwriting an earlier backup."""
    candidate = path.with_name(path.name + ".bak")
    index = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak.{index}")
        index += 1
    return candidate


def _show_ssh_key(addr_data: dict, write: bool = False) -> None:
    """Print the SSH public key derived from the recovery phrase.

    Same phrase as the agent identity, different derivation — so there is still
    one thing to write down, and the operator can reach a provisioned server
    without a second secret to manage.
    """
    from ... import address

    seed = addr_data.get("seed_phrase")
    if not seed:
        console.print("\n[red]No recovery phrase available.[/red]")
        console.print("[dim]The SSH key is derived from it, so it cannot be rebuilt without it.[/dim]")
        console.print("[cyan]It lives in .co/keys/recovery.txt — restore that file, or run 'co init' in a new project.[/cyan]\n")
        return

    keys = address.derive_ssh_key(seed)

    console.print()
    console.print(keys["public_line"])
    console.print()

    if not write:
        console.print("[dim]Add that line to ~/.ssh/authorized_keys on any server you want to reach.[/dim]")
        console.print("[dim]Use [bold]--write[/bold] to also write the private half to ~/.ssh/.[/dim]\n")
        return

    # A human-facing export into ~/.ssh, which the operator owns. Our own copy
    # lives in ~/.co/ssh and is managed by write_derived_ssh_key().
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    private_path = ssh_dir / "connectonion_ed25519"
    public_path = ssh_dir / "connectonion_ed25519.pub"

    expected = _public_key_identity(keys["public_line"])
    existing_private_public = (
        _public_key_from_private(private_path) if private_path.exists() else None
    )
    existing_public = public_path.read_text().strip() if public_path.exists() else None

    if (
        existing_private_public
        and _public_key_identity(existing_private_public) == expected
        and existing_public
        and _public_key_identity(existing_public) == expected
    ):
        console.print(f"[green]✓[/green] {private_path} already contains the derived SSH key.")
        console.print("[dim]Nothing to do.[/dim]\n")
        return

    backups = []
    for path in (private_path, public_path):
        if path.exists():
            backup = _backup_path(path)
            shutil.copy2(path, backup)
            backups.append(backup)

    if backups:
        console.print("[yellow]The existing SSH key does not match the derived key used for new servers.[/yellow]")
        for backup in backups:
            console.print(f"[dim]Backed up {backup}[/dim]")

    private_path.write_text(keys["private_key"])
    private_path.chmod(0o600)
    public_path.write_text(keys["public_line"] + "\n")
    public_path.chmod(0o644)

    console.print(f"[green]✓[/green] wrote {private_path} [dim](0600)[/dim]")
    console.print(f"[green]✓[/green] wrote {public_path}")
    console.print(f"\n[dim]Use it with:[/dim] ssh -i {private_path} user@host\n")
