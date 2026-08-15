"""
Purpose: CLI surface for the user's Gmail mailbox — send, list (inbox/sent), read, reply, and search from the terminal
LLM-Note:
  Dependencies: imports from [os, sys, json, pathlib, typer, dotenv, rich.console, rich.panel, rich.table, ...useful_tools.gmail.Gmail] | imported by [cli/main.py via handle_gmail_*()] | hits the Gmail API through the Gmail tool
  Data flow: _gmail() loads GOOGLE_* from .env / ~/.co/keys.env → Gmail() instance | inbox/search: list_inbox()/list_search() → numbered Rich table (plain ID-bearing text when piped) → saves {#: message_id} to ~/.co/gmail_last_inbox.json | read/reply: resolve short numbers via that cache → get_email_body()/reply() | send: '-' body reads stdin
  State/Effects: writes ~/.co/gmail_last_inbox.json (last listing's # → message id map; "numbers mean your last listing" — only inbox and search write it) | read marks emails read server-side | Gmail refreshes expired tokens via oo-api and rewrites ~/.co/keys.env
  Integration: exposes handle_gmail_send(), handle_gmail_inbox(), handle_gmail_read(), handle_gmail_reply(), handle_gmail_sent(), handle_gmail_search() for cli/main.py | presentation mirrors outlook_commands.py (table shape, ● unread mark, ✉️ panel, '✓ Sent' wording) | Gmail API logic lives in useful_tools/gmail.py | requires prior 'co auth google'
  Errors: every guarded failure prints a hint and exits 1 (typer.Exit) so scripts can detect it — missing auth/scopes, unresolvable email # | Gmail API errors propagate from the Gmail tool
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

INBOX_CACHE = Path.home() / ".co" / "gmail_last_inbox.json"


def _gmail():
    """Load GOOGLE_* credentials from .env files and return a Gmail instance. Exits 1 with a hint if not connected."""
    from dotenv import load_dotenv

    for env_path in [Path(".env"), Path.home() / ".co" / "keys.env"]:
        if env_path.exists():
            load_dotenv(env_path)

    if not os.getenv("GOOGLE_ACCESS_TOKEN"):
        console.print("\n❌ [bold red]Google account not connected[/bold red]")
        console.print("\n[cyan]Connect Gmail first:[/cyan]")
        console.print("  [bold]co auth google[/bold]     Authorize Gmail access\n")
        raise typer.Exit(1)

    # Gmail() itself requires both scopes — check them here so a partially
    # authorized token gets the hint instead of a raw ValueError traceback.
    scopes = os.getenv("GOOGLE_SCOPES", "")
    if "gmail.readonly" not in scopes or "gmail.send" not in scopes:
        console.print("\n❌ [bold red]Gmail permission missing[/bold red]")
        console.print("\n[cyan]Reconnect Google to grant it:[/cyan]")
        console.print("  [bold]co auth google[/bold]     Re-authorize with Gmail access\n")
        raise typer.Exit(1)

    from ...useful_tools.gmail import Gmail
    # A person invoking the CLI explicitly names every path. Agent tool
    # instances keep Gmail's project-only default instead.
    return Gmail(allow_external_attachments=True)


def _when(date: str) -> str:
    """Render a Gmail RFC 2822 Date header as 'Jul 26 14:30' in local time.

    Messages without a Date header arrive here as 'Unknown', and spam carries
    outright malformed ones; parsedate_to_datetime() raises ValueError on both,
    which would take down the whole listing. Show the raw value instead.
    """
    from email.utils import parsedate_to_datetime

    try:
        parsed = parsedate_to_datetime(date)
    except ValueError:
        return date
    return parsed.astimezone().strftime("%b %d %H:%M")


def _print_listing(gmail, emails: list, title: str):
    """Render emails as a numbered table (or plain ID-bearing text when piped) and cache the numbering for read/reply."""
    INBOX_CACHE.parent.mkdir(exist_ok=True)
    INBOX_CACHE.write_text(json.dumps({str(i): e["id"] for i, e in enumerate(emails, 1)}), encoding="utf-8")

    if not console.is_terminal:
        # Scripts and agents get the untruncated format with full message ids —
        # and the same next-step tip: piped callers are exactly the AI audience
        # the tip exists for.
        console.print(gmail._format_dicts(emails), markup=False, highlight=False)
        print("Read one with: co gmail read <#>")
        return

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("From", max_width=28, no_wrap=True)
    table.add_column("Subject", overflow="ellipsis", no_wrap=True)
    table.add_column("Received")

    for i, email in enumerate(emails, 1):
        unread_mark = "[bold green]●[/bold green] " if email["unread"] else ""
        table.add_row(str(i), email["from"], f"{unread_mark}{email['subject']}", _when(email["date"]))

    console.print()
    console.print(table)
    console.print("\n[dim]Read one with:[/dim] [bold]co gmail read <#>[/bold]\n")


def handle_gmail_inbox(last: int = 10, unread: bool = False):
    """List recent Gmail inbox emails as a numbered table, and remember the numbering for 'read'."""
    gmail = _gmail()
    emails = gmail.list_inbox(last=last, unread=unread)
    if not emails:
        scope = "unread " if unread else ""
        console.print(f"\n[cyan]Gmail inbox:[/cyan] no {scope}emails\n")
        return
    _print_listing(gmail, emails, f"📬 Gmail — {os.getenv('GOOGLE_EMAIL', '')}")


def _resolve_email_id(gmail, email_id: str) -> str:
    """Turn a listing number into a Gmail message id; full ids pass through. Numbers mean the last listing shown."""
    cached = json.loads(INBOX_CACHE.read_text(encoding="utf-8")) if INBOX_CACHE.exists() else {}
    if email_id in cached:
        return cached[email_id]

    if not (email_id.isascii() and email_id.isdigit() and len(email_id) < 5):
        return email_id  # full Gmail message id

    if cached or int(email_id) < 1:
        # The user is pointing at their last listing and that number wasn't in
        # it — fetching a fresh (differently numbered) list would silently open
        # the wrong email.
        return ""

    emails = gmail.list_inbox(last=int(email_id))
    if len(emails) < int(email_id):
        return ""
    return emails[int(email_id) - 1]["id"]


def handle_gmail_read(email_id: str):
    """Show one Gmail email's full body and mark it read. Accepts the listing # or a full message id."""
    gmail = _gmail()
    resolved = _resolve_email_id(gmail, email_id)
    if not resolved:
        console.print(f"\n[yellow]No email #{email_id} in your last listing — run co gmail, then co gmail read <#>.[/yellow]\n")
        raise typer.Exit(1)

    body = gmail.get_email_body(resolved)
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
    if "gmail.modify" in os.getenv("GOOGLE_SCOPES", ""):
        # Marking read is a mailbox write — the API rejects it on tokens that
        # only carry gmail.readonly + gmail.send.
        gmail.mark_read(resolved)
        marked = "Marked read. "
    console.print(f"\n[dim]{marked}Reply with:[/dim] [bold]co gmail reply <#> <message>[/bold]\n")


def handle_gmail_reply(email_id: str, message: str):
    """Reply to an email from the last listing (threaded). A message of '-' reads stdin."""
    if message == "-":
        message = sys.stdin.read()

    gmail = _gmail()
    resolved = _resolve_email_id(gmail, email_id)
    if not resolved:
        console.print(f"\n[yellow]No email #{email_id} in your last listing — run co gmail, then co gmail reply <#> <message>.[/yellow]\n")
        raise typer.Exit(1)

    gmail.reply(resolved, message)
    console.print(f"\n[green]✓ Replied[/green] to email {email_id}\n")


def _check_attachments(attachments: list):
    """Precheck paths before base64-encoding megabytes. Exits 1 on bad input.

    Mirrors the Outlook precheck deliberately, including doing it here rather
    than in the tool: a missing file should cost a message, not a traceback
    after the encode. The limit differs because the services do -- Gmail takes
    25MB where Graph stops at 3MB -- so borrowing Outlook's number would refuse
    mail Gmail would have accepted.
    """
    from ...useful_tools.gmail import GMAIL_ATTACHMENT_LIMIT

    paths = [Path(p).expanduser() for p in attachments]
    for given, path in zip(attachments, paths):
        if not path.is_file():
            console.print(f"\n❌ [bold red]Attachment not found:[/bold red] {given}\n")
            raise typer.Exit(1)
    if sum(p.stat().st_size for p in paths) > GMAIL_ATTACHMENT_LIMIT:
        console.print("\n❌ [bold red]Attachments exceed Gmail's 25MB send limit.[/bold red]\n")
        raise typer.Exit(1)


def handle_gmail_send(to: str, subject: str, message: str, cc: str = None,
                      bcc: str = None, attachments: list = None):
    """Send an email from the connected Gmail account. A message of '-' reads the body from stdin."""
    if message == "-":
        message = sys.stdin.read()

    if attachments:
        _check_attachments(attachments)

    gmail = _gmail()
    gmail.send(to, subject, message, cc=cc, bcc=bcc, attachments=attachments)

    console.print(f"\n[green]✓ Sent[/green] to [cyan]{to}[/cyan]")
    console.print(f"  From: {os.getenv('GOOGLE_EMAIL', '')}")
    console.print()


def handle_gmail_sent(last: int = 10):
    """List recently sent Gmail emails."""
    gmail = _gmail()
    console.print(f"\n📤 [bold cyan]Gmail sent[/bold cyan] [dim]({os.getenv('GOOGLE_EMAIL', '')})[/dim]\n")
    console.print(gmail.get_sent_emails(max_results=last), markup=False, highlight=False)
    console.print()


def handle_gmail_search(query: str, last: int = 10):
    """Search Gmail and list matches with the same numbering contract as the inbox."""
    gmail = _gmail()
    emails = gmail.list_search(query, max_results=last)
    if not emails:
        console.print(f"\n[cyan]Search:[/cyan] no emails matching [bold]{query}[/bold]\n")
        return
    _print_listing(gmail, emails, f"🔎 Gmail — {query}")
