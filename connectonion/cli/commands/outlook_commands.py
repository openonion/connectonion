"""
Purpose: CLI surface for Outlook email and contacts — send/read/search mail and add/list/search contacts from the terminal
LLM-Note:
  Dependencies: imports from [os, sys, json, pathlib, datetime, typer, dotenv, rich.console, rich.panel, rich.table, ...useful_tools.outlook.Outlook] | imported by [cli/main.py via handle_outlook_*()] | hits Microsoft Graph API through the Outlook tool
  Data flow: _microsoft_record() loads MICROSOFT_* from the global default or explicit --env-file and checks the operation scope (shared with outlook_calendar_commands) → _outlook() wraps it in an Outlook() instance | mail commands use list/read/send/reply methods and the numbered inbox cache | send and reply share _check_attachments() to reject missing or oversize --attach files before megabytes are base64-encoded | handle_outlook_reply(email_id, message, at, *, attachments, cc, bcc) keeps `at` third positional for pre-attachment callers, so attachments/cc/bcc are keyword-only | every handler ends with one print_tip() next command that survives piping; a scheduled send or reply names the cancel path (#1314) | contact commands use add_contact()/list_contacts()/search_contacts() and render Rich tables or tab-separated plain output
  State/Effects: writes ~/.co/outlook_last_inbox.json for mail numbering | read changes mailbox state only with --mark-read; send/reply/contact commands mutate their named data | Outlook auto-refreshes expired tokens via oo-api and saves the selected credential record
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
from .mail_window import print_json_listing, window_listing
from .microsoft_errors import microsoft_errors
from .command_tips import print_tip

from ...provider_credentials import resolve_provider_credentials

console = Console()

INBOX_CACHE = Path.home() / ".co" / "outlook_last_inbox.json"

def _microsoft_record(required_scope: str = "Mail"):
    """Load the selected Microsoft record and require the Graph scope this command needs.

    Shared by mail, contacts and calendar so all three answer "not connected"
    and "permission missing" with the same words and the same next command.
    """
    from ...environment import load_environment
    load_environment()
    from ...provider_credentials import resolve_provider_credentials
    record = resolve_provider_credentials("microsoft")
    auth_tip = record.auth_command

    if not (record.get("ACCESS_TOKEN") or record.get("REFRESH_TOKEN")):
        console.print("\n❌ [bold red]Microsoft account not connected[/bold red]")
        console.print("\n[cyan]Connect Outlook first:[/cyan]")
        print(f"Next: {auth_tip}")
        raise typer.Exit(1)

    # "Mail" matches any Mail.* grant; "Contacts.ReadWrite" matches only itself.
    scopes = record.scopes
    if scopes and not any(s == required_scope or s.startswith(f"{required_scope}.") for s in scopes):
        console.print(f"\n❌ [bold red]Microsoft {required_scope} permission missing[/bold red]")
        console.print("\n[cyan]Reconnect Microsoft to grant it:[/cyan]")
        print(f"Next: {auth_tip}")
        raise typer.Exit(1)
    return record


def _outlook(required_scope: str = "Mail"):
    """Load Microsoft credentials and require the Graph scope this command needs."""
    _microsoft_record(required_scope)
    from ...useful_tools.outlook import Outlook
    return Outlook(allow_external_attachments=True)


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
        # Scripts and agents get the untruncated format with full message ids —
        # and the same next-step tip: piped callers are exactly the AI audience
        # the tip exists for.
        console.print(outlook._format_dicts(emails), markup=False, highlight=False)
        print_tip("Read one with: co outlook read <#>")
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
    print_tip("\n[dim]Read one with:[/dim] [bold]co outlook read <#>[/bold]\n")


def _parse_send_at(at: str) -> str:
    """Turn '+30m' / '+2h' into a UTC ISO timestamp; validate ISO strings. Exits 1 on bad input."""
    from datetime import datetime, timedelta, timezone

    def bad():
        console.print(f"\n❌ [bold red]Invalid --at value:[/bold red] {at}")
        console.print("   Use [bold]+30m[/bold], [bold]+2h[/bold], or UTC ISO like [bold]2026-07-06T15:30:00Z[/bold]\n")
        print_tip("Next: co outlook send --help")
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
    from ...useful_tools.outlook import OUTLOOK_ATTACHMENT_LIMIT

    paths = [Path(p).expanduser() for p in attachments]
    for given, path in zip(attachments, paths):
        if not path.is_file():
            console.print(f"\n❌ [bold red]Attachment not found:[/bold red] {given}\n")
            raise typer.Exit(1)
    if sum(p.stat().st_size for p in paths) > OUTLOOK_ATTACHMENT_LIMIT:
        console.print("\n❌ [bold red]Attachments exceed Outlook's 3MB send limit.[/bold red]\n")
        raise typer.Exit(1)


@microsoft_errors("co outlook sent")
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
    console.print(f"  From: {resolve_provider_credentials('microsoft').get('EMAIL') or ''}")
    if cc:
        console.print(f"  Cc: {cc}")
    if bcc:
        console.print(f"  Bcc: {bcc}")
    if attachments:
        names = ", ".join(Path(p).name for p in attachments)
        console.print(f"  Attached: {names}")
    _after_send(send_at)


def _after_send(send_at: str | None) -> None:
    """The send most likely to be taken back is the one that says how (#1314).

    Four emails queued for the next morning, wording that then had to change,
    and the cancel path found by reading useful_tools/outlook.py rather than
    any CLI output. So the confirmation names it, and the same tip survives
    piping — the agent that scheduled the mail is the one that needs it.
    """
    if send_at:
        console.print("  Cancel before it goes out: co outlook scheduled, then co outlook cancel <#>",
                      markup=False, highlight=False)
        print_tip("Next: co outlook scheduled")
    else:
        print_tip("Next: co outlook sent")


@microsoft_errors("co outlook inbox")
def handle_outlook_inbox(last: int = 10, unread: bool = False,
                        since: str = None, until: str = None, json_output: bool = False):
    """List recent Outlook inbox emails as a numbered table, and remember the numbering for 'read'."""
    outlook = _outlook()
    if since:
        try:
            emails = window_listing(outlook, since, until, last)
        except ValueError as error:
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(2) from None
    else:
        emails = outlook.list_inbox(last=last, unread=unread)
    if json_output:
        print_json_listing(emails)
        return
    if not emails:
        scope = "unread " if unread else ""
        console.print(f"\n[cyan]Outlook inbox:[/cyan] no {scope}emails\n")
        print_tip("Next: co outlook inbox -n 25" if unread else "Next: co outlook search <words>")
        return
    _print_listing(outlook, emails, f"📬 Outlook — {resolve_provider_credentials('microsoft').get('EMAIL') or ''}")


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


@microsoft_errors("co outlook inbox")
def handle_outlook_read(email_id: str, mark_read: bool = False):
    """Show one Outlook message; mark it read only with explicit opt-in."""
    outlook = _outlook()
    resolved = _resolve_email_id(outlook, email_id)
    if not resolved:
        print_tip(f"\n[yellow]No email #{email_id} in your last listing — run co outlook, then co outlook read <#>.[/yellow]\n")
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

    marked = "Unread state unchanged. "
    # The scope comes from the same selected record as the token — a per-field
    # os.getenv read could answer for a different account than the one that
    # is about to be written to.
    if mark_read and "Mail.ReadWrite" in outlook._credentials.scopes:
        # Marking read is a mailbox write — Graph rejects it with 403 on
        # tokens that only carry Mail.Read + Mail.Send.
        outlook.mark_read(resolved)
        marked = "Marked read. "
    elif mark_read:
        marked = "Not marked read: run co auth microsoft to grant Mail.ReadWrite. "
    print_tip(f"\n[dim]{marked}Reply with:[/dim] [bold]co outlook reply <#> <message>[/bold]\n")


@microsoft_errors("co outlook inbox")
def handle_outlook_download(email_id: str, out_dir: str = ".", include_inline: bool = False):
    """Save an email's attachments to disk. Accepts the listing # or a full message id."""
    outlook = _outlook()
    resolved = _resolve_email_id(outlook, email_id)
    if not resolved:
        print_tip(f"\n[yellow]No email #{email_id} in your last listing — run co outlook, then co outlook download <#>.[/yellow]\n")
        raise typer.Exit(1)

    saved = outlook.download_attachments(resolved, out_dir, include_inline=include_inline)
    if not saved:
        console.print("\n[yellow]No file attachments on that email.[/yellow]")
        console.print("[dim]Embedded signature images are skipped — --include-inline saves them too.[/dim]\n")
        print_tip(f"Next: co outlook download {email_id} --include-inline")
        return

    console.print()
    for path in saved:
        console.print(f"[green]✓[/green] {path}")
    print_tip(f"Next: co outlook read {email_id}")


@microsoft_errors("co outlook sent")
def handle_outlook_reply(email_id: str, message: str, at: str = None, *, attachments: list = None,
                         cc: str = None, bcc: str = None):
    """Reply to an email from the last listing (threaded via Graph). A message of '-' reads stdin.

    `at` keeps its third-positional slot from before attachments existed;
    attachments, cc and bcc are keyword-only so no caller can pass a schedule
    as a file or an address.
    """
    if message == "-":
        message = sys.stdin.read()
    send_at = _parse_send_at(at) if at else None
    if attachments:
        _check_attachments(attachments)

    outlook = _outlook()
    resolved = _resolve_email_id(outlook, email_id)
    if not resolved:
        print_tip(f"\n[yellow]No email #{email_id} in your last listing — run co outlook, then co outlook reply <#> <message>.[/yellow]\n")
        raise typer.Exit(1)

    outlook.reply(resolved, message, attachments=attachments, send_at=send_at, cc=cc, bcc=bcc)
    if send_at:
        console.print(f"\n[green]✓ Reply scheduled[/green] for [bold]{send_at}[/bold] to email {email_id}")
    else:
        console.print(f"\n[green]✓ Replied[/green] to email {email_id}")
    if cc:
        console.print(f"  Cc: {cc}")
    if bcc:
        console.print(f"  Bcc: {bcc}")
    if attachments:
        names = ", ".join(Path(p).name for p in attachments)
        console.print(f"  Attached: {names}")
    _after_send(send_at)


@microsoft_errors("co outlook inbox")
def handle_outlook_sent(last: int = 10):
    """List recently sent Outlook emails."""
    outlook = _outlook()
    console.print(f"\n📤 [bold cyan]Outlook sent[/bold cyan] [dim]({resolve_provider_credentials('microsoft').get('EMAIL') or ''})[/dim]\n")
    console.print(outlook.get_sent_emails(max_results=last), markup=False, highlight=False)
    print_tip("Next: co outlook inbox")


@microsoft_errors("co outlook inbox")
def handle_outlook_search(query: str, last: int = 10):
    """Search Outlook emails and list matches with the same numbering contract as the inbox."""
    outlook = _outlook()
    emails = outlook.list_search(query, max_results=last)
    if not emails:
        console.print(f"\n[cyan]Search:[/cyan] no emails matching [bold]{query}[/bold]\n")
        print_tip("Next: co outlook inbox -n 25")
        return
    _print_listing(outlook, emails, f"🔎 Outlook — {query}")


def _print_contacts(contacts: list, title: str):
    """Render contacts as a table, or stable tab-separated rows when piped."""
    if not console.is_terminal:
        # Plain print, not console.print: Rich expands \t into spaces, which
        # silently turns tab-separated output into something cut -f can't read.
        for contact in contacts:
            print(f"{contact['name']}\t{contact['email']}\t{contact['id']}")
        print_tip('Next: co outlook send <email from this listing> "<subject>" "<message>"')
        return

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("Name", max_width=36, no_wrap=True)
    table.add_column("Email", max_width=48, no_wrap=True)
    for index, contact in enumerate(contacts, 1):
        table.add_row(str(index), contact["name"], contact["email"])
    console.print()
    console.print(table)
    print_tip('Next: co outlook send <email from this listing> "<subject>" "<message>"')


@microsoft_errors("co outlook inbox")
def handle_outlook_contact_add(name: str, email: str):
    """Create a contact in the connected Outlook account."""
    outlook = _outlook(required_scope="Contacts.ReadWrite")
    contact = outlook.add_contact(name, email)
    console.print(
        f"\n[green]✓ Saved contact[/green] "
        f"[bold]{contact['name']}[/bold] <[cyan]{contact['email']}[/cyan]>\n"
    )
    print_tip("Next: co outlook contact list")


@microsoft_errors("co outlook inbox")
def handle_outlook_contact_list(last: int = 25):
    """List contacts from the connected Outlook account."""
    outlook = _outlook(required_scope="Contacts.ReadWrite")
    contacts = outlook.list_contacts(max_results=last)
    if not contacts:
        console.print("\n[cyan]Outlook contacts:[/cyan] none saved\n")
        print_tip('Next: co outlook contact add "<name>" <email>')
        return
    _print_contacts(contacts, "👥 Outlook contacts")


@microsoft_errors("co outlook inbox")
def handle_outlook_contact_search(query: str, last: int = 25):
    """Search Outlook contacts by name or email."""
    outlook = _outlook(required_scope="Contacts.ReadWrite")
    contacts = outlook.search_contacts(query, max_results=last)
    if not contacts:
        console.print(
            f"\n[cyan]Contact search:[/cyan] no contacts matching "
            f"[bold]{query}[/bold]"
        )
        print_tip("Next: co outlook contact list -n 100")
        return
    _print_contacts(contacts, f"🔎 Outlook contacts — {query}")


@microsoft_errors("co outlook inbox")
def handle_outlook_scheduled():
    """List emails waiting for scheduled delivery, numbered for cancel."""
    outlook = _outlook()
    scheduled = outlook.get_scheduled()
    if not scheduled:
        console.print("\n[cyan]No scheduled emails.[/cyan]\n")
        print_tip('Next: co outlook send <to> "<subject>" "<message>" --at +2h')
        return

    INBOX_CACHE.parent.mkdir(exist_ok=True)
    INBOX_CACHE.write_text(json.dumps({str(i): e["id"] for i, e in enumerate(scheduled, 1)}), encoding="utf-8")

    if not console.is_terminal:
        # Scripts and agents get one plain line per email with the full id —
        # and the same next-step tip as the terminal table.
        for email in scheduled:
            console.print(f"{email['send_at']}  {email['to']}  {email['subject']}  {email['id']}",
                          markup=False, highlight=False)
        print_tip("Cancel one with: co outlook cancel <#>")
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
    print_tip("\n[dim]Cancel one with:[/dim] [bold]co outlook cancel <#>[/bold]\n")


@microsoft_errors("co outlook inbox")
def handle_outlook_cancel(email_id: str):
    """Cancel a scheduled email before Exchange sends it."""
    outlook = _outlook()
    resolved = _resolve_email_id(outlook, email_id)
    if not resolved:
        print_tip(f"\n[yellow]No email #{email_id} in your last listing — run co outlook scheduled, then co outlook cancel <#>.[/yellow]\n")
        raise typer.Exit(1)

    outlook.cancel_scheduled(resolved)
    console.print(f"\n[green]✓ Canceled[/green] scheduled email {email_id}")
    print_tip("Next: co outlook scheduled")
