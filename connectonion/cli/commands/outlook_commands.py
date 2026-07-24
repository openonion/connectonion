"""
Purpose: CLI surface for Outlook email and contacts — send/read/search mail and add/list/search contacts from the terminal
LLM-Note:
  Dependencies: imports from [os, sys, json, pathlib, datetime, typer, dotenv, rich.console, rich.panel, rich.table, ...useful_tools.outlook.Outlook] | imported by [cli/main.py via handle_outlook_*()] | hits Microsoft Graph API through the Outlook tool
  Data flow: _outlook() loads MICROSOFT_* from .env / ~/.co/keys.env and checks the operation scope → Outlook() instance | mail commands use list/read/send methods and the numbered inbox cache | contact commands use add_contact()/list_contacts()/search_contacts() and render Rich tables or tab-separated plain output
  State/Effects: writes ~/.co/outlook_last_inbox.json for mail numbering | mutates Outlook mail/contact data through the library | Outlook auto-refreshes expired tokens via oo-api and rewrites ~/.co/keys.env
  Integration: exposes handle_outlook_* functions for cli/main.py, including handle_outlook_contact_add/list/search | presentation mirrors existing mail tables | Graph logic lives in useful_tools/outlook.py | requires prior 'co auth microsoft'
  Errors: guarded failures print a hint and exit 1 (typer.Exit) — missing auth/Mail/Contacts.ReadWrite scopes, invalid files/times/ids | Graph API errors propagate from Outlook
"""

import json
import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

INBOX_CACHE = Path.home() / ".co" / "outlook_last_inbox.json"

ATTACHMENT_LIMIT = 3_000_000  # Graph sendMail rejects larger payloads


def _outlook(required_scope: str = "Mail"):
    """Load Microsoft credentials and require Mail or an exact Graph scope."""
    from dotenv import load_dotenv

    for env_path in [Path(".env"), Path.home() / ".co" / "keys.env"]:
        if env_path.exists():
            load_dotenv(env_path)

    scopes = set(os.getenv("MICROSOFT_SCOPES", "").replace(",", " ").split())
    has_scope = (
        any(scope.startswith("Mail.") for scope in scopes)
        if required_scope == "Mail"
        else required_scope in scopes
    )
    if not os.getenv("MICROSOFT_ACCESS_TOKEN") or not has_scope:
        if os.getenv("MICROSOFT_ACCESS_TOKEN") and required_scope != "Mail":
            console.print(
                f"\n❌ [bold red]Microsoft {required_scope} permission missing[/bold red]"
            )
            console.print("\n[cyan]Reconnect Microsoft to grant it:[/cyan]")
            console.print("  [bold]co auth microsoft[/bold]\n")
            raise typer.Exit(1)
        console.print("\n❌ [bold red]Microsoft account not connected[/bold red]")
        console.print("\n[cyan]Connect Outlook first:[/cyan]")
        console.print("  [bold]co auth microsoft[/bold]     Authorize Outlook access\n")
        raise typer.Exit(1)

    from ...useful_tools.outlook import Outlook
    return Outlook()


def _when(iso: str) -> str:
    """Render a Graph UTC timestamp as short local time, e.g. 'Jul 06 15:23'."""
    import re
    from datetime import datetime

    # Graph sometimes returns 7-digit fractional seconds, which
    # fromisoformat() rejects on Python 3.10 — display is minute-granular.
    iso = re.sub(r"\.\d+", "", str(iso))
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%b %d %H:%M")


def _print_listing(outlook, emails: list, title: str):
    """Render emails as a numbered table (or plain ID-bearing text when piped) and cache the numbering for read/reply."""
    INBOX_CACHE.parent.mkdir(exist_ok=True)
    INBOX_CACHE.write_text(json.dumps({str(i): e["id"] for i, e in enumerate(emails, 1)}), encoding="utf-8")

    if not console.is_terminal:
        # Scripts and agents get the untruncated format with full message ids.
        console.print(outlook._format_dicts(emails), markup=False, highlight=False)
        return

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("From", max_width=28, no_wrap=True)
    table.add_column("Subject", overflow="ellipsis", no_wrap=True)
    table.add_column("Received")

    for i, email in enumerate(emails, 1):
        unread_mark = "[bold green]●[/bold green] " if email["unread"] else ""
        sender = email.get("from_name") or email["from"]
        table.add_row(str(i), sender, f"{unread_mark}{email['subject']}", _when(email["date"]))

    console.print()
    console.print(table)
    console.print("\n[dim]Read one with:[/dim] [bold]co outlook read <#>[/bold]\n")


def _parse_send_at(at: str) -> str:
    """Turn '+30m' / '+2h' into a UTC ISO timestamp; validate ISO strings. Exits 1 on bad input."""
    from datetime import datetime, timedelta, timezone

    def bad():
        console.print(f"\n❌ [bold red]Invalid --at value:[/bold red] {at}")
        console.print("   Use [bold]+30m[/bold], [bold]+2h[/bold], or UTC ISO like [bold]2026-07-06T15:30:00Z[/bold]\n")
        raise typer.Exit(1)

    if at.startswith("+"):
        n, unit = at[1:-1], at[-1]
        if unit not in ("m", "h") or not (n.isascii() and n.isdigit()):
            bad()
        delta = timedelta(**{{"m": "minutes", "h": "hours"}[unit]: int(n)})
        return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        parsed = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        bad()
    if parsed.tzinfo is None:
        # Exchange reads the deferred-send time as UTC; a naive local time
        # would silently go out hours off target.
        bad()
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_attachments(attachments: list):
    """Precheck attachment paths before base64-encoding megabytes. Exits 1 on bad input."""
    paths = [Path(p).expanduser() for p in attachments]
    for given, path in zip(attachments, paths):
        if not path.is_file():
            console.print(f"\n❌ [bold red]Attachment not found:[/bold red] {given}\n")
            raise typer.Exit(1)
    if sum(p.stat().st_size for p in paths) > ATTACHMENT_LIMIT:
        console.print("\n❌ [bold red]Attachments exceed Outlook's 3MB send limit.[/bold red]\n")
        raise typer.Exit(1)


def handle_outlook_send(to: str, subject: str, message: str, cc: str = None, bcc: str = None,
                        attachments: list = None, at: str = None):
    """Send an email from the connected Outlook account. A message of '-' reads the body from stdin."""
    if message == "-":
        message = sys.stdin.read()
    send_at = _parse_send_at(at) if at else None
    if attachments:
        _check_attachments(attachments)

    outlook = _outlook()
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
    emails = outlook.list_inbox(last=last, unread=unread)
    if not emails:
        scope = "unread " if unread else ""
        console.print(f"\n[cyan]Outlook inbox:[/cyan] no {scope}emails\n")
        return
    _print_listing(outlook, emails, f"📬 Outlook — {os.getenv('MICROSOFT_EMAIL', '')}")


def _resolve_email_id(outlook, email_id: str) -> str:
    """Turn a listing number into a Graph message id; full ids pass through. Numbers mean the last listing shown."""
    cached = json.loads(INBOX_CACHE.read_text(encoding="utf-8")) if INBOX_CACHE.exists() else {}
    if email_id in cached:
        return cached[email_id]

    if not (email_id.isascii() and email_id.isdigit() and len(email_id) < 5):
        return email_id  # full Graph message id

    if cached or int(email_id) < 1:
        # The user is pointing at their last listing and that number wasn't in
        # it — fetching a fresh (differently numbered) list would silently open
        # the wrong email.
        return ""

    emails = outlook.list_inbox(last=int(email_id))
    if len(emails) < int(email_id):
        return ""
    return emails[int(email_id) - 1]["id"]


def handle_outlook_read(email_id: str):
    """Show one Outlook email's full body and mark it read. Accepts the listing # or a full message id."""
    outlook = _outlook()
    resolved = _resolve_email_id(outlook, email_id)
    if not resolved:
        console.print(f"\n[yellow]No email #{email_id} in your last listing — run co outlook to refresh.[/yellow]\n")
        raise typer.Exit(1)

    body = outlook.get_email_body(resolved)
    header, _, content = body.partition("\n--- Email Body ---\n")
    console.print()
    console.print(Panel.fit(header.replace("From:", "[cyan]From:[/cyan]")
                            .replace("To:", "[cyan]To:[/cyan]", 1)
                            .replace("Subject:", "[cyan]Subject:[/cyan]")
                            .replace("Date:", "[cyan]Date:[/cyan]"),
                            title=f"✉️  Email {email_id}", border_style="cyan"))
    console.print()
    console.print(content.strip() or "[dim](empty body)[/dim]", markup=False, highlight=False)

    marked = ""
    if "Mail.ReadWrite" in os.getenv("MICROSOFT_SCOPES", ""):
        # Marking read is a mailbox write — Graph rejects it with 403 on
        # tokens that only carry Mail.Read + Mail.Send.
        outlook.mark_read(resolved)
        marked = "Marked read. "
    console.print(f"\n[dim]{marked}Reply with:[/dim] [bold]co outlook reply <#> <message>[/bold]\n")


def handle_outlook_reply(email_id: str, message: str, at: str = None):
    """Reply to an email from the last listing (threaded via Graph). A message of '-' reads stdin."""
    if message == "-":
        message = sys.stdin.read()
    send_at = _parse_send_at(at) if at else None

    outlook = _outlook()
    resolved = _resolve_email_id(outlook, email_id)
    if not resolved:
        console.print(f"\n[yellow]No email #{email_id} in your last listing — run co outlook to refresh.[/yellow]\n")
        raise typer.Exit(1)

    outlook.reply(resolved, message, send_at=send_at)
    if send_at:
        console.print(f"\n[green]✓ Reply scheduled[/green] for [bold]{send_at}[/bold] to email {email_id}\n")
    else:
        console.print(f"\n[green]✓ Replied[/green] to email {email_id}\n")


def handle_outlook_sent(last: int = 10):
    """List recently sent Outlook emails."""
    outlook = _outlook()
    console.print(f"\n📤 [bold cyan]Outlook sent[/bold cyan] [dim]({os.getenv('MICROSOFT_EMAIL', '')})[/dim]\n")
    console.print(outlook.get_sent_emails(max_results=last), markup=False, highlight=False)
    console.print()


def handle_outlook_search(query: str, last: int = 10):
    """Search Outlook emails and list matches with the same numbering contract as the inbox."""
    outlook = _outlook()
    emails = outlook.list_search(query, max_results=last)
    if not emails:
        console.print(f"\n[cyan]Search:[/cyan] no emails matching [bold]{query}[/bold]\n")
        return
    _print_listing(outlook, emails, f"🔎 Outlook — {query}")


def _print_contacts(contacts: list, title: str):
    """Render contacts as a table, or stable tab-separated rows when piped."""
    if not console.is_terminal:
        for contact in contacts:
            console.print(
                f"{contact['name']}\t{contact['email']}\t{contact['id']}",
                markup=False,
                highlight=False,
            )
        return

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("Name", max_width=36, no_wrap=True)
    table.add_column("Email", max_width=48, no_wrap=True)
    for index, contact in enumerate(contacts, 1):
        table.add_row(str(index), contact["name"], contact["email"])
    console.print()
    console.print(table)
    console.print()


def handle_outlook_contact_add(name: str, email: str):
    """Create a contact in the connected Outlook account."""
    outlook = _outlook(required_scope="Contacts.ReadWrite")
    contact = outlook.add_contact(name, email)
    console.print(
        f"\n[green]✓ Saved contact[/green] "
        f"[bold]{contact['name']}[/bold] <[cyan]{contact['email']}[/cyan]>\n"
    )


def handle_outlook_contact_list(last: int = 25):
    """List contacts from the connected Outlook account."""
    outlook = _outlook(required_scope="Contacts.ReadWrite")
    contacts = outlook.list_contacts(max_results=last)
    if not contacts:
        console.print("\n[cyan]Outlook contacts:[/cyan] none saved\n")
        return
    _print_contacts(contacts, "👥 Outlook contacts")


def handle_outlook_contact_search(query: str, last: int = 25):
    """Search Outlook contacts by name or email."""
    outlook = _outlook(required_scope="Contacts.ReadWrite")
    contacts = outlook.search_contacts(query, max_results=last)
    if not contacts:
        console.print(
            f"\n[cyan]Contact search:[/cyan] no contacts matching "
            f"[bold]{query}[/bold]\n"
        )
        return
    _print_contacts(contacts, f"🔎 Outlook contacts — {query}")


def handle_outlook_scheduled():
    """List emails waiting for scheduled delivery, numbered for cancel."""
    outlook = _outlook()
    scheduled = outlook.get_scheduled()
    if not scheduled:
        console.print("\n[cyan]No scheduled emails.[/cyan]\n")
        return

    INBOX_CACHE.parent.mkdir(exist_ok=True)
    INBOX_CACHE.write_text(json.dumps({str(i): e["id"] for i, e in enumerate(scheduled, 1)}), encoding="utf-8")

    if not console.is_terminal:
        # Scripts and agents get one plain line per email with the full id.
        for email in scheduled:
            console.print(f"{email['send_at']}  {email['to']}  {email['subject']}  {email['id']}",
                          markup=False, highlight=False)
        return

    table = Table(title="⏰ Outlook — scheduled sends", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("To", max_width=32, no_wrap=True)
    table.add_column("Subject", overflow="ellipsis", no_wrap=True)
    table.add_column("Sends at")

    for i, email in enumerate(scheduled, 1):
        table.add_row(str(i), email["to"], email["subject"], _when(email["send_at"]))

    console.print()
    console.print(table)
    console.print("\n[dim]Cancel one with:[/dim] [bold]co outlook cancel <#>[/bold]\n")


def handle_outlook_cancel(email_id: str):
    """Cancel a scheduled email before Exchange sends it."""
    outlook = _outlook()
    resolved = _resolve_email_id(outlook, email_id)
    if not resolved:
        console.print(f"\n[yellow]No email #{email_id} in your last listing — run co outlook scheduled first.[/yellow]\n")
        raise typer.Exit(1)

    outlook.cancel_scheduled(resolved)
    console.print(f"\n[green]✓ Canceled[/green] scheduled email {email_id}\n")
