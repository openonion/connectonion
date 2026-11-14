"""
Purpose: Manage trust lists (contacts, whitelist, blocklist, admins) with full address display for easy copying
LLM-Note:
  Dependencies: imports from [pathlib, rich.console, rich.table, network.trust.tools] | imported by [cli/main.py via trust subcommands] | tested by [tests/e2e/cli/test_cli_trust.py]
  Data flow: receives address and optional flags → calls trust.tools functions (get_level, promote_to_contact, promote_to_whitelist, demote_to_stranger, block, unblock, add_admin, remove_admin, load_admins, get_self_address) → reads/writes the selected agent directory/{contacts,whitelist,blocklist,admins}.txt → displays results with Rich console color coding (stranger=dim, contact=cyan, whitelist=green, blocked=red) → outputs full addresses (not truncated) for easy copy-paste to other commands
  State/Effects: modifies trust list files in the selected agent directory (contacts.txt, whitelist.txt, blocklist.txt, admins.txt) | reads from these files to display current state | writes to stdout via rich.Console | no network calls
  Integration: exposes handle_trust_* functions for CLI subcommands | relies on network.trust.tools for verification logic and file operations | uses Rich for formatted terminal output | integrates with trust verification system used by network.host() | admins can manage trust lists via CLI commands | self address shown with "(self)" label in admin list
  Performance: file I/O for reading/writing trust lists (<50ms) | Rich table rendering is fast | no network calls | linear scan of trust list files (typically small <100 entries)
  Errors: trust.tools functions return descriptive error messages on failure (e.g., "Address not found", "Already in list") | gracefully handles missing trust list files (treats as empty) | invalid addresses rejected by trust.tools validation | admin operations require super admin privileges (enforced by trust.tools)

CLI commands for managing trust lists (contacts, whitelist, blocklist, admins).

Addresses are shown in full (not truncated) so users can easily copy them
for use in other commands or configuration files.

Usage:
    co trust list                    # List all trust lists
    co trust list --global           # The global identity's (co ai, co handoff)
    co trust level <address>         # Check trust level of address
    co trust add <address>           # Add to contacts (default)
    co trust add <address> -w        # Add to whitelist
    co trust remove <address>        # Remove from all lists
    co trust block <address>         # Block an address
    co trust unblock <address>       # Unblock an address
    co trust admin add <address>     # Add admin (super admin only)
    co trust admin remove <address>  # Remove admin (super admin only)
"""

import re
import shlex
from pathlib import Path

import typer
from rich.console import Console

from ...network.trust.tools import (
    add_admin,
    block,
    demote_to_stranger,
    get_level,
    get_self_address,
    is_admin,
    list_file,
    load_admins,
    promote_to_contact,
    promote_to_whitelist,
    remove_admin,
    unblock,
)
from ...project import project_co_dir

console = Console()

# An agent address is an Ed25519 public key: 0x and 64 hex digits.
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{64}$")


def trust_target(co_dir=None, global_: bool = False):
    """Select one trust directory for all CLI reads and mutations."""
    if global_ and co_dir is not None:
        raise typer.BadParameter("Use either --co-dir or --global, not both.")
    if global_:
        from ...environment import global_config_dir
        return global_config_dir()
    return Path(co_dir).expanduser().resolve() if co_dir is not None else None


def _require_address(address: str) -> None:
    """Refuse anything that cannot be an address, with exit code 2 (a usage error).

    `co trust add not-an-address` printed "✓ not-an-address promoted to
    contact" and stored it: a typo, or a name pasted where the key belonged,
    looked like success and admitted nobody. Removing (`remove`, `unblock`,
    `admin remove`) is not checked, so an entry an older version stored can
    still be taken out.
    """
    if ADDRESS.match(address or ""):
        return
    console.print(f"\n[red]✗ {address!r} is not an agent address.[/red] "
                  "An address is 0x followed by 64 hex digits.\n")
    raise typer.Exit(2)


def _read_list(list_name: str, co_dir=None) -> list[str]:
    """Read entries from a list file."""
    list_path = list_file(list_name, co_dir)
    if not list_path.exists():
        return []
    content = list_path.read_text(encoding='utf-8')
    return [line.strip() for line in content.splitlines()
            if line.strip() and not line.startswith('#')]


def _print_targeted_tip(tip: str, co_dir=None):
    from .command_tips import print_tip, tips_enabled

    if not tips_enabled():
        return

    target = f" --co-dir {shlex.quote(str(Path(co_dir).expanduser().resolve()))}" if co_dir is not None else ""
    print_tip(f"Next: {tip}{target}")


def handle_trust_list(co_dir=None):
    """List all trust lists: this directory's agent, or `co_dir` (the global identity for --global)."""
    # These lists belong to one agent, so being in the wrong directory shows
    # four empty sections — which reads as "my whitelist was wiped" rather than
    # "you are not standing in an agent". Say which it is.
    agent_dir = list_file("whitelist", co_dir).parent
    if not agent_dir.is_dir():
        console.print()
        console.print(f"[yellow]No agent here[/yellow] — {agent_dir} does not exist.")
        console.print("[dim]Trust lists belong to one agent. Run this from its "
                      "directory, or 'co init ./' to make one.[/dim]")
        console.print("[dim]Contacts made by co ai and co handoff belong to your global identity:[/dim]")
        console.print("  co trust list --global")
        console.print()
        _print_targeted_tip("Check one address: co trust level <address>", co_dir)
        return

    contacts = _read_list("contacts", co_dir)
    whitelist = _read_list("whitelist", co_dir)
    blocklist = _read_list("blocklist", co_dir)
    admins = load_admins(co_dir)
    self_addr = get_self_address(co_dir)

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

    # Handoffs only: senders whose handoff this agent accepted (Aaron, 2026-10-13)
    handoffs = [a for a in _read_list("handoffs", co_dir) if a not in contacts]
    if handoffs:
        console.print("[bold]Handoffs only[/bold] [dim](the other side of a handoff: they can send you handoff "
                      "messages, not run tools here; either side of a handoff lands here)[/dim]")
        for addr in handoffs:
            console.print(f"  {addr}")
        console.print()

    # Contacts
    console.print("[bold]Contacts[/bold] [dim](invite, payment, or added by you)[/dim]")
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

    console.print(f"[dim]Lists stored in: {agent_dir}[/dim]")
    _print_targeted_tip("Check one address: co trust level <address>", co_dir)


def _print_trust_files(co_dir):
    console.print("Trust files:", markup=False)
    for name in ("blocklist", "whitelist", "contacts", "handoffs", "admins"):
        console.print(str(list_file(name, co_dir)), markup=False, soft_wrap=True)


def _resolved(co_dir):
    return Path(co_dir or project_co_dir()).expanduser().resolve()


def _print_updated(co_dir, *names):
    """Name each list an edit wrote, so a wrong target is visible at once (#2819)."""
    for name in names:
        console.print(f"Updated: {list_file(name, co_dir)}", markup=False, soft_wrap=True)


def handle_trust_level(address: str, co_dir=None):
    """Check trust level of an address."""
    _require_address(address)
    explicit_directory = co_dir is not None
    co_dir = _resolved(co_dir)
    target = f" --co-dir {shlex.quote(str(co_dir))}" if explicit_directory else ""
    level = get_level(address, co_dir)
    if level != "blocked" and is_admin(address, co_dir):
        # This reported the agent's own address as a stranger and suggested
        # making it a contact. Admins -- this agent's own key always among
        # them -- pass every trust check; none of the lists apply to them.
        own = " (this agent's own address)" if address == get_self_address(co_dir) else ""
        console.print(f"\n{address}: [bold magenta]admin[/bold magenta]{own}\n")
        _print_trust_files(co_dir)
        from .command_tips import print_tip
        print_tip(f"Admins pass every trust check. Next: co trust list{target}")
        return

    level_colors = {
        "stranger": "dim",
        "contact": "cyan",
        "whitelist": "green",
        "blocked": "red",
    }
    color = level_colors.get(level, "white")

    console.print(f"\n{address}: [{color}]{level}[/{color}]\n")
    _print_trust_files(co_dir)
    # One static tip said "Make it a contact" to every address, including the
    # contact that had just been made one. What comes next depends on where it is.
    from .command_tips import print_tip
    tip = {
        "stranger": f"Next: co trust add {address}{target}   (make it a contact)",
        "contact": f"Next: co trust add -w {address}{target}   (whitelist it), or co trust remove {address}{target}",
        "whitelist": f"Next: co trust remove {address}{target}   (back to stranger)",
        "blocked": f"Next: co trust unblock {address}{target}",
    }.get(level, f"Next: co trust list{target}")
    print_tip(tip)


def handle_trust_add(address: str, whitelist: bool = False, co_dir=None):
    """Add address to contacts or whitelist."""
    _require_address(address)
    resolved = _resolved(co_dir)
    promote = promote_to_whitelist if whitelist else promote_to_contact
    console.print(f"\n[green]✓[/green] {promote(address, resolved)}\n")
    _print_updated(resolved, "whitelist" if whitelist else "contacts")

    _print_targeted_tip("See every list: co trust list", co_dir)


def handle_trust_remove(address: str, co_dir=None):
    """Remove address from all lists (demote to stranger)."""
    resolved = _resolved(co_dir)
    console.print(f"\n[yellow]✓[/yellow] {demote_to_stranger(address, resolved)}\n")
    _print_updated(resolved, "contacts", "whitelist")

    _print_targeted_tip("See every list: co trust list", co_dir)


def handle_trust_block(address: str, reason: str = "", co_dir=None):
    """Block an address."""
    _require_address(address)
    resolved = _resolved(co_dir)
    console.print(f"\n[red]✓[/red] {block(address, reason, resolved)}\n")
    _print_updated(resolved, "blocklist")

    _print_targeted_tip("See every list: co trust list", co_dir)


def handle_trust_unblock(address: str, co_dir=None):
    """Unblock an address."""
    resolved = _resolved(co_dir)
    console.print(f"\n[green]✓[/green] {unblock(address, resolved)}\n")
    _print_updated(resolved, "blocklist")

    _print_targeted_tip("See every list: co trust list", co_dir)


def handle_admin_add(address: str, co_dir=None):
    """Add an admin."""
    _require_address(address)
    resolved = _resolved(co_dir)
    console.print(f"\n[green]✓[/green] {add_admin(address, resolved)}\n")
    _print_updated(resolved, "admins")

    _print_targeted_tip("See every list: co trust list", co_dir)


def handle_admin_remove(address: str, co_dir=None):
    """Remove an admin."""
    resolved = _resolved(co_dir)
    console.print(f"\n[yellow]✓[/yellow] {remove_admin(address, resolved)}\n")
    _print_updated(resolved, "admins")
    _print_targeted_tip("See every list: co trust list", co_dir)
