"""
Purpose: Display and manage agent keys, credentials, and OAuth connections with masked/revealed output
LLM-Note:
  Dependencies: imports from [os, pathlib, rich.console, rich.panel, rich.table, credentials, project, status_commands, address] | imported by [cli/main.py via handle_keys()] | tested by [tests/e2e/cli/test_cli_keys.py]
  Data flow: receives reveal flag (bool) → _find_co_dir() resolves project/global identity → _load_env_vars() inspects process/project-root/global sources without loading them → compares an inspectable OpenOnion account claim with that identity → masks secrets unless --reveal → displays Identity, Secrets, OAuth, and Env Files tables
  State/Effects: no state modifications | reads from .co/keys/agent.key, recovery.txt, project-root .env, ~/.co/keys.env | writes to stdout via rich.Console | does not mutate os.environ or credential files
  Integration: exposes handle_keys() for CLI | similar to status command but focuses on credentials | relies on address module for keypair loading | uses Rich for formatted panel output | checks env vars in priority order: OPENONION_API_KEY, GOOGLE_EMAIL/tokens, MICROSOFT_EMAIL/tokens | recovery phrase shown if recovery.txt exists
  Performance: file I/O for key loading and env vars (<50ms) | Rich table rendering is fast | no network calls
  Errors: prints message if no .co directory found (run 'co init' or 'co create') | prints message if keys fail to load | gracefully handles missing recovery.txt (shows "missing" message) | gracefully handles missing OAuth tokens (not shown in table) | gracefully handles missing env files (shows red ✗)
"""

import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...credentials import account_in_token, api_key_account_mismatch
from ...project import project_root
from .status_commands import _selected_credential_values, _short_account

console = Console()


def _find_co_dir() -> Path:
    """The identity this project uses: its own key, else the machine's.

    The project half is found by walking up, the way everything else has since
    #660. As a bare `Path(".co")` it was invisible one directory down, and the
    `~/.co` fallback then answered instead -- so `co keys` printed a different
    address depending on where in the project you stood:

        from the project root   Address 0xd72fbbd5…   Source .co (project)
        from a subdirectory     Address 0x10e68f6d…   Source ~/.co (global)

    Both stated as confidently as the other, and an operator reads one off this
    panel and hands it out.

    The fallback itself stays: a project with no key of its own is a real
    configuration -- `co init` usually produces one -- and it is what
    resolve_agent_identity does on the host side.
    """
    from ...project import project_co_dir

    local = project_co_dir()
    if local.exists() and (local / "keys" / "agent.key").exists():
        return local

    global_dir = Path.home() / ".co"
    if global_dir.exists() and (global_dir / "keys" / "agent.key").exists():
        return global_dir

    return None


def _load_env_vars(
    *,
    project_dir: Path | None = None,
    home: Path | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, str | None]:
    """Select credentials without mutating the process environment."""

    names = (
        "OPENONION_API_KEY",
        "GOOGLE_EMAIL",
        "GOOGLE_ACCESS_TOKEN",
        "GOOGLE_REFRESH_TOKEN",
        "MICROSOFT_EMAIL",
        "MICROSOFT_ACCESS_TOKEN",
        "MICROSOFT_REFRESH_TOKEN",
    )
    return _selected_credential_values(
        names,
        project_dir=project_dir,
        home=home,
        environ=environ,
    )


def _mask(value: str, show: int = 8, secret: bool = False) -> str:
    """Mask a value, showing a prefix — or nothing at all when `secret`.

    It is not useful for the recovery phrase, which was masked the same way and
    so printed its first two words under a panel that ends "Secrets are masked."
    Ten unknown words still carry ~110 bits, so nothing is brute-forced from it
    — but the prefix identifies nothing anyone needs, which leaves no benefit to
    weigh against showing part of the one credential that moves an identity and
    its balance, in output people paste because they were told it was hidden.

    `secret=True` also fixes the width, so the mask does not report how long the
    value was. `co keys --reveal` is unchanged.
    """
    if not value:
        return ""
    if secret:
        return "*" * 16
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
    """Return human-readable source label for where keys are loaded from.

    Relative to where you are standing, so it stays short and says which way the
    project lies: `.co` at the root, `../.co` from a subdirectory. It used to
    interpolate `co_dir` directly, which read fine only because that value was
    the relative `Path(".co")`; once it became the resolved project path the
    panel printed the machine's whole directory tree.
    """
    if co_dir.resolve() == (Path.home() / ".co").resolve():
        return "~/.co (global)"
    try:
        shown = co_dir.relative_to(Path.cwd())
    except ValueError:
        shown = Path(os.path.relpath(co_dir, Path.cwd()))
    return f"{shown} (project)"


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
        sec_table.add_row("Recovery", seed if reveal else _mask(seed, secret=True))
    else:
        sec_table.add_row("Recovery", "[dim]missing (recovery.txt not found)[/dim]")

    # API key
    api_key = env_vars.get("OPENONION_API_KEY")
    if api_key:
        sec_table.add_row(
            "API Key",
            api_key if reveal else _mask(api_key, secret=True),
        )
        claim = account_in_token(api_key)
        mismatch = api_key_account_mismatch(api_key, addr_data)
        if mismatch is not None:
            claimed, expected = mismatch
            sec_table.add_row(
                "Account",
                "[red]✗[/red] token account "
                f"{_short_account(claimed)} does not match identity "
                f"{_short_account(expected)} — run 'co auth'",
            )
        elif claim:
            sec_table.add_row(
                "Account",
                f"[green]✓[/green] matches {_short_account(claim)}",
            )
        else:
            sec_table.add_row(
                "Account",
                "[yellow]○[/yellow] not inspectable locally; server verifies it",
            )
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
    local_env = project_root() / ".env"

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


def _show_ssh_key(addr_data: dict, write: bool = False) -> None:
    """The SSH keys derived from the recovery phrase — one per server.

    There is no single key to print any more. #427 retired the one that was
    derived from a label and installed everywhere: a snapshot of one machine
    yielded the key that opened the rest, and rotating meant changing the
    recovery phrase. Each server now gets its own, derived from the same tree as
    the identity, so this prints the set rather than asking for a host nobody
    would remember.
    """
    from ... import address
    from .server_commands import _load

    seed = addr_data.get("seed_phrase")
    if not seed:
        console.print("\n[red]No recovery phrase available.[/red]")
        console.print("[dim]The SSH keys are derived from it, so they cannot be rebuilt without it.[/dim]")
        console.print("[cyan]It lives in .co/keys/recovery.txt — restore that file, or run 'co init' in a new project.[/cyan]\n")
        return

    servers = sorted((_load() or {}).keys())
    if not servers:
        console.print("\n[yellow]No servers registered.[/yellow]")
        console.print("[dim]Keys are per-server now. `co server new` or `co server add` first, "
                      "then this prints the line to install on each.[/dim]\n")
        return

    console.print()
    for name in servers:
        line = address.derive_ssh_key(seed, host=name)["public_line"]
        console.print(f"[cyan]{name}[/cyan]")
        # soft_wrap: an authorized_keys line that rich has folded at the
        # terminal width is a broken line once pasted, and pasting it is the
        # only reason to print it.
        console.print(f"  {line}", soft_wrap=True)
    console.print()

    if write:
        for name in servers:
            path = write_per_host_ssh_key(seed, name)
            console.print(f"[green]✓[/green] {name} → {path}")
        console.print()
    else:
        console.print("[dim]Each line goes in ~/.ssh/authorized_keys on that server only.[/dim]")
        console.print("[dim]Use [bold]--write[/bold] to cache the private halves under ~/.co/ssh/.[/dim]\n")
