"""
Purpose: CLI surface for the user's Outlook mailbox — send, list (inbox/sent), read, and search email from the terminal
LLM-Note:
  Dependencies: imports from [os, sys, json, pathlib, dotenv, rich.console, rich.table, ...useful_tools.outlook.Outlook] | imported by [cli/main.py via handle_outlook_*()] | hits Microsoft Graph API through the Outlook tool
  Data flow: _outlook() loads MICROSOFT_* from .env / ~/.co/keys.env → Outlook() instance | inbox: list_inbox() → Rich table numbered 1..N → saves {#: message_id} to ~/.co/outlook_last_inbox.json | read: resolves short numbers via that cache (falls back to a fresh list_inbox) → get_email_body() → mark_read() | send: '-' body reads stdin → send() → '✓ Sent' confirmation
  State/Effects: writes ~/.co/outlook_last_inbox.json (last listing's # → message id map) | network calls happen inside the Outlook tool | read marks emails read server-side | Outlook auto-refreshes expired tokens via oo-api and rewrites ~/.co/keys.env
  Integration: exposes handle_outlook_send(), handle_outlook_inbox(), handle_outlook_read(), handle_outlook_sent(), handle_outlook_search() for cli/main.py | presentation mirrors email_commands.py (same table shape, ● unread mark, '✓ Sent' wording) | Graph logic lives in useful_tools/outlook.py | requires prior 'co auth microsoft'
  Errors: prints a 'run co auth microsoft' hint when MICROSOFT_* credentials or Mail scopes are missing | Graph API errors propagate from the Outlook tool
"""

import json
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

INBOX_CACHE = Path.home() / ".co" / "outlook_last_inbox.json"


def _outlook():
    """Load MICROSOFT_* credentials from .env files and return an Outlook instance, or None with a hint."""
    from dotenv import load_dotenv

    for env_path in [Path(".env"), Path.home() / ".co" / "keys.env"]:
        if env_path.exists():
            load_dotenv(env_path)

    if not os.getenv("MICROSOFT_ACCESS_TOKEN") or "Mail" not in os.getenv("MICROSOFT_SCOPES", ""):
        console.print("\n❌ [bold red]Microsoft account not connected[/bold red]")
        console.print("\n[cyan]Connect Outlook first:[/cyan]")
        console.print("  [bold]co auth microsoft[/bold]     Authorize Outlook access\n")
        return None

    from ...useful_tools.outlook import Outlook
    return Outlook()


def _parse_send_at(at: str) -> str:
    """Turn '+30m' / '+2h' into a UTC ISO timestamp; ISO strings pass through."""
    if not at.startswith("+"):
        return at

    from datetime import datetime, timedelta, timezone

    unit = at[-1]
    if unit not in ("m", "h") or not at[1:-1].isdigit():
        raise ValueError(f"Invalid --at value: {at} (use +30m, +2h, or a UTC ISO time)")
    delta = timedelta(**{{"m": "minutes", "h": "hours"}[unit]: int(at[1:-1])})
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def handle_outlook_send(to: str, subject: str, message: str, cc: str = None, bcc: str = None,
                        attachments: list = None, at: str = None):
    """Send an email from the connected Outlook account. A message of '-' reads the body from stdin."""
    if message == "-":
        message = sys.stdin.read()
    send_at = _parse_send_at(at) if at else None

    outlook = _outlook()
    if not outlook:
        return
    outlook.send(to, subject, message, cc=cc, bcc=bcc, attachments=attachments, send_at=send_at)

    if send_at:
        console.print(f"\n[green]✓ Scheduled[/green] for [bold]{send_at}[/bold] to [cyan]{to}[/cyan]")
    else:
        console.print(f"\n[green]✓ Sent[/green] to [cyan]{to}[/cyan]")
    console.print(f"  From: {os.getenv('MICROSOFT_EMAIL', '')}")
    if attachments:
        names = ", ".join(Path(p).name for p in attachments)
        console.print(f"  Attached: {names}")
    console.print()


def handle_outlook_inbox(last: int = 10, unread: bool = False):
    """List recent Outlook inbox emails as a numbered table, and remember the numbering for 'read'."""
    outlook = _outlook()
    if not outlook:
        return

    emails = outlook.list_inbox(last=last, unread=unread)
    if not emails:
        scope = "unread " if unread else ""
        console.print(f"\n[cyan]Outlook inbox:[/cyan] no {scope}emails\n")
        return

    table = Table(title=f"📬 Outlook — {os.getenv('MICROSOFT_EMAIL', '')}", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("From")
    table.add_column("Subject")
    table.add_column("Received")

    for i, email in enumerate(emails, 1):
        unread_mark = "[bold green]●[/bold green] " if email["unread"] else ""
        table.add_row(str(i), email["from"], f"{unread_mark}{email['subject']}", str(email["date"])[:19])

    INBOX_CACHE.parent.mkdir(exist_ok=True)
    INBOX_CACHE.write_text(json.dumps({str(i): e["id"] for i, e in enumerate(emails, 1)}))

    console.print()
    console.print(table)
    console.print("\n[dim]Read one with:[/dim] [bold]co outlook read <#>[/bold]\n")


def _resolve_email_id(outlook, email_id: str) -> str:
    """Turn a short inbox number into a Graph message id; full ids pass through."""
    if not (email_id.isdigit() and len(email_id) < 5):
        return email_id

    if INBOX_CACHE.exists():
        cached = json.loads(INBOX_CACHE.read_text()).get(email_id)
        if cached:
            return cached

    emails = outlook.list_inbox(last=int(email_id))
    if len(emails) < int(email_id):
        return ""
    return emails[int(email_id) - 1]["id"]


def handle_outlook_read(email_id: str):
    """Show one Outlook email's full body and mark it read. Accepts the inbox # or a full message id."""
    outlook = _outlook()
    if not outlook:
        return

    resolved = _resolve_email_id(outlook, email_id)
    if not resolved:
        console.print(f"\n[yellow]No email #{email_id} in your inbox.[/yellow]\n")
        return

    console.print()
    console.print(outlook.get_email_body(resolved))
    console.print()
    outlook.mark_read(resolved)


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
