"""
Purpose: CLI surface for the user's Outlook mailbox — send, list (inbox/sent), read, and search email from the terminal
LLM-Note:
  Dependencies: imports from [os, pathlib, dotenv, rich.console, ...useful_tools.outlook.Outlook] | imported by [cli/main.py via handle_outlook_*()] | hits Microsoft Graph API through the Outlook tool
  Data flow: _outlook() loads MICROSOFT_* from .env / ~/.co/keys.env → Outlook() instance → each handler calls one Outlook method → prints the tool's formatted string
  State/Effects: no local state | network calls happen inside the Outlook tool | read marks emails read server-side | Outlook auto-refreshes expired tokens via oo-api and rewrites ~/.co/keys.env
  Integration: exposes handle_outlook_send(), handle_outlook_inbox(), handle_outlook_read(), handle_outlook_sent(), handle_outlook_search() for cli/main.py | thin presentation layer — all Graph logic lives in useful_tools/outlook.py | requires prior 'co auth microsoft'
  Errors: prints a 'run co auth microsoft' hint when MICROSOFT_* credentials are missing | Graph API errors propagate from the Outlook tool
"""

import os
from pathlib import Path

from rich.console import Console

console = Console()


def _outlook():
    """Load MICROSOFT_* credentials from .env files and return an Outlook instance, or None with a hint."""
    from dotenv import load_dotenv

    for env_path in [Path(".env"), Path.home() / ".co" / "keys.env"]:
        if env_path.exists():
            load_dotenv(env_path)

    if not os.getenv("MICROSOFT_ACCESS_TOKEN"):
        console.print("\n❌ [bold red]Microsoft account not connected[/bold red]")
        console.print("\n[cyan]Connect Outlook first:[/cyan]")
        console.print("  [bold]co auth microsoft[/bold]     Authorize Outlook access\n")
        return None

    from ...useful_tools.outlook import Outlook
    return Outlook()


def handle_outlook_send(to: str, subject: str, message: str, cc: str = None, bcc: str = None,
                        attachments: list = None):
    """Send an email from the connected Outlook account."""
    outlook = _outlook()
    if not outlook:
        return
    result = outlook.send(to, subject, message, cc=cc, bcc=bcc, attachments=attachments)
    console.print(f"\n[green]✓[/green] {result}")
    console.print(f"  From: {os.getenv('MICROSOFT_EMAIL', '')}\n")


def handle_outlook_inbox(last: int = 10, unread: bool = False):
    """List recent emails in the Outlook inbox."""
    outlook = _outlook()
    if not outlook:
        return
    console.print(f"\n📬 [bold cyan]Outlook inbox[/bold cyan] [dim]({os.getenv('MICROSOFT_EMAIL', '')})[/dim]\n")
    console.print(outlook.read_inbox(last=last, unread=unread))
    console.print("\n[dim]Read one with:[/dim] [bold]co outlook read <ID>[/bold]\n")


def handle_outlook_read(email_id: str):
    """Show one Outlook email's full body and mark it read."""
    outlook = _outlook()
    if not outlook:
        return
    console.print()
    console.print(outlook.get_email_body(email_id))
    console.print()
    outlook.mark_read(email_id)


def handle_outlook_sent(last: int = 10):
    """List recently sent Outlook emails."""
    outlook = _outlook()
    if not outlook:
        return
    console.print(f"\n📤 [bold cyan]Outlook sent[/bold cyan] [dim]({os.getenv('MICROSOFT_EMAIL', '')})[/dim]\n")
    console.print(outlook.get_sent_emails(max_results=last))
    console.print()


def handle_outlook_search(query: str, last: int = 10):
    """Search Outlook emails by subject and body."""
    outlook = _outlook()
    if not outlook:
        return
    console.print()
    console.print(outlook.search_emails(query, max_results=last))
    console.print()
