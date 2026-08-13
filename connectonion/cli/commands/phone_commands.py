"""
Purpose: `co phone` — set the number your agents reach you on, and send a notification to it
LLM-Note:
  Dependencies: imports from [sys, rich.console, useful_tools.phone] | imported by [cli/main.py via phone_*()] | tested by [tests/unit/test_phone.py]
  Data flow: handle_phone_number(phone) → set/get_owner_phone() | handle_phone_notify(message, urgent) → notify_owner() → prints the outcome
  State/Effects: one HTTP call per command via the tool | no local state
  Integration: same shape as handle_email_send — a thin handler over the tool an agent already has
  Errors: any failure prints the server's own reason and exits 1
"""

import sys

from rich.console import Console

from ...useful_tools.phone import get_owner_phone, notify_owner, set_owner_phone

console = Console()


def handle_phone_number(phone: str = None) -> int:
    """Show the configured number, or set it."""
    result = set_owner_phone(phone) if phone else get_owner_phone()

    if not result["success"]:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)

    if phone:
        console.print(f"[green]Your agents will reach you on {result['phone']}[/green]")
        return 0

    if not result.get("configured"):
        console.print(
            "No number set. [dim]co phone number +61435525634[/dim]\n"
            "Until then your agents can only reach you by email."
        )
        return 0

    console.print(f"Your agents reach you on [cyan]{result['phone']}[/cyan]")
    return 0


def handle_phone_notify(message: str, urgent: bool = False) -> int:
    """Send yourself a notification, the way an agent would."""
    result = notify_owner(message, urgent=urgent)

    if not result["success"]:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)

    console.print(
        f"[green]{'Calling' if urgent else 'Texted'} {result['to']}[/green] "
        f"[dim](${result['cost_usd']:.2f})[/dim]"
    )
    return 0
