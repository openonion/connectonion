"""
CLI commands for managing trust lists (contacts, whitelist, blocklist, admins).

Addresses are shown in full (not truncated) so users can easily copy them
for use in other commands or configuration files.

Usage:
    co trust list                    # List all trust lists
    co trust level <address>         # Check trust level of address
    co trust add <address>           # Add to contacts (default)
    co trust add <address> -w        # Add to whitelist
    co trust remove <address>        # Remove from all lists
    co trust block <address>         # Block an address
    co trust unblock <address>       # Unblock an address
    co trust admin add <address>     # Add admin (super admin only)
    co trust admin remove <address>  # Remove admin (super admin only)
"""

from pathlib import Path
from rich.console import Console
from rich.table import Table

from ...network.trust.tools import (
    CO_DIR,
    get_level,
    promote_to_contact,
    promote_to_whitelist,
    demote_to_stranger,
    block,
    unblock,
    add_admin,
    remove_admin,
    load_admins,
    get_self_address,
)

console = Console()


def _read_list(list_name: str) -> list[str]:
    """Read entries from a list file."""
    list_path = CO_DIR / f"{list_name}.txt"
    if not list_path.exists():
        return []
    content = list_path.read_text(encoding='utf-8')
    return [line.strip() for line in content.splitlines()
            if line.strip() and not line.startswith('#')]


def handle_trust_list():
    """List all trust lists."""
    contacts = _read_list("contacts")
    whitelist = _read_list("whitelist")
    blocklist = _read_list("blocklist")
    admins = load_admins()
    self_addr = get_self_address()

    console.print()

    # Admins
    console.print("[bold]Admins[/bold]")
    if admins:
        for addr in admins:
            label = " [dim](self)[/dim]" if addr == self_addr else ""
            console.print(f"  {addr}{label}")
    else:
        console.print("  [dim]No admins configured[/dim]")
    console.print()

    # Whitelist
    console.print("[bold]Whitelist[/bold] [dim](full trust)[/dim]")
    if whitelist:
        for addr in whitelist:
            console.print(f"  {addr}")
    else:
        console.print("  [dim]Empty[/dim]")
    console.print()

    # Contacts
    console.print("[bold]Contacts[/bold] [dim](verified via invite/payment)[/dim]")
    if contacts:
        for addr in contacts:
            console.print(f"  {addr}")
    else:
        console.print("  [dim]Empty[/dim]")
    console.print()

    # Blocklist
    console.print("[bold]Blocklist[/bold] [dim](denied access)[/dim]")
    if blocklist:
        for addr in blocklist:
            console.print(f"  [red]{addr}[/red]")
    else:
        console.print("  [dim]Empty[/dim]")
    console.print()

    console.print(f"[dim]Lists stored in: {CO_DIR}[/dim]")


def handle_trust_level(address: str):
    """Check trust level of an address."""
    level = get_level(address)

    level_colors = {
        "stranger": "dim",
        "contact": "cyan",
        "whitelist": "green",
        "blocked": "red",
    }
    color = level_colors.get(level, "white")

    console.print(f"\n{address}: [{color}]{level}[/{color}]\n")


def handle_trust_add(address: str, whitelist: bool = False):
    """Add address to contacts or whitelist."""
    if whitelist:
        result = promote_to_whitelist(address)
        console.print(f"\n[green]✓[/green] {result}\n")
    else:
        result = promote_to_contact(address)
        console.print(f"\n[green]✓[/green] {result}\n")


def handle_trust_remove(address: str):
    """Remove address from all lists (demote to stranger)."""
    result = demote_to_stranger(address)
    console.print(f"\n[yellow]✓[/yellow] {result}\n")


def handle_trust_block(address: str, reason: str = ""):
    """Block an address."""
    result = block(address, reason)
    console.print(f"\n[red]✓[/red] {result}\n")


def handle_trust_unblock(address: str):
    """Unblock an address."""
    result = unblock(address)
    console.print(f"\n[green]✓[/green] {result}\n")


def handle_admin_add(address: str):
    """Add an admin."""
    result = add_admin(address)
    console.print(f"\n[green]✓[/green] {result}\n")


def handle_admin_remove(address: str):
    """Remove an admin."""
    result = remove_admin(address)
    console.print(f"\n[yellow]✓[/yellow] {result}\n")
