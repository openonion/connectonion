"""
Purpose: CLI surface for the user's Gmail mailbox — send, list (inbox/sent), read, reply, and search from the terminal
LLM-Note:
  Dependencies: imports from [os, sys, json, pathlib, typer, dotenv, rich.console, rich.panel, rich.table, ...useful_tools.gmail.Gmail] | imported by [cli/main.py via handle_gmail_*()] | hits the Gmail API through the Gmail tool
  Data flow: _gmail() loads GOOGLE_* from .env / ~/.co/keys.env → Gmail() instance | inbox/search: list_inbox()/list_search() → numbered Rich table (plain ID-bearing text when piped) → saves {#: message_id} to ~/.co/gmail_last_inbox.json | draft list → ~/.co/gmail_last_drafts.json | draft edits parse and replace Gmail's raw MIME message | Drive attachment reads reuse GDrive without writing local files
  State/Effects: writes Gmail inbox/draft numbering caches under ~/.co | draft commands create/update Gmail drafts, but only draft send can deliver and it always asks for confirmation | read changes mailbox state only with --mark-read | Gmail refreshes expired tokens via oo-api and rewrites ~/.co/keys.env
  Integration: exposes inbox/read/reply/send/sent/search plus draft list/create/attach/remove/replace/preview/send handlers for cli/main.py | presentation mirrors outlook_commands.py | Gmail/Drive API logic lives in useful_tools | requires prior 'co auth google'
  Errors: every guarded draft failure prints a provider-safe hint and exits 1 (typer.Exit) so scripts can detect it — missing auth/scopes, unresolvable email/draft/file #, missing or oversized attachments | older direct Gmail commands retain their existing API-error behavior
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
DRAFT_CACHE = Path.home() / ".co" / "gmail_last_drafts.json"


def _gmail(require_draft_write: bool = False):
    """Load GOOGLE_* credentials from .env files and return a Gmail instance. Exits 1 with a hint if not connected."""
    from dotenv import load_dotenv
    from ...project import project_root

    for env_path in [project_root() / ".env", Path.home() / ".co" / "keys.env"]:
        if env_path.is_file():
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

    if require_draft_write and not any(
        scope in scopes for scope in ("gmail.modify", "gmail.compose", "mail.google.com")
    ):
        console.print("\n❌ [bold red]Gmail draft permission missing[/bold red]")
        console.print("\n[cyan]Reconnect Google to grant it:[/cyan]")
        console.print("  [bold]co auth google[/bold]     Re-authorize with Gmail draft access\n")
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


def handle_gmail_read(email_id: str, mark_read: bool = False):
    """Show one Gmail message; mark it read only with explicit opt-in."""
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

    marked = "Unread state unchanged. "
    if mark_read and "gmail.modify" in os.getenv("GOOGLE_SCOPES", ""):
        # Marking read is a mailbox write — the API rejects it on tokens that
        # only carry gmail.readonly + gmail.send.
        gmail.mark_read(resolved)
        marked = "Marked read. "
    elif mark_read:
        marked = "Not marked read: run co auth google to grant gmail.modify. "
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


# === Draft attachment workflow ===

def _resolve_draft_id(draft_id: str) -> str:
    """Turn a draft-list number into an immutable Gmail draft id."""
    cached = json.loads(DRAFT_CACHE.read_text(encoding="utf-8")) if DRAFT_CACHE.exists() else {}
    if draft_id in cached:
        return cached[draft_id]
    if draft_id.isascii() and draft_id.isdigit() and len(draft_id) < 5:
        return ""
    return draft_id


def _draft_call(action, retry_command: str):
    """Run one draft API operation and turn provider failures into fix-it output."""
    from googleapiclient.errors import HttpError

    try:
        return action()
    except HttpError as exc:
        status = getattr(exc.resp, "status", None)
        if status in (401, 403):
            cause = "Google rejected the Gmail/Drive permission."
            retry_command = "co auth google"
        elif status == 404:
            cause = "Gmail draft or Drive file was not found."
            retry_command = "co gmail draft list"
        else:
            suffix = f" (HTTP {status})" if status else ""
            cause = f"Google could not complete the draft request{suffix}."
        console.print(f"\n❌ {cause}", markup=False, highlight=False)
        console.print(f"Retry with: {retry_command}\n", markup=False, highlight=False)
        raise typer.Exit(1) from None
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        # These messages are generated locally by the bounded attachment and
        # OAuth checks. Provider response bodies (which can carry secrets) are
        # never printed.
        console.print(f"\n❌ {exc}", markup=False, highlight=False)
        console.print(f"Retry with: {retry_command}\n", markup=False, highlight=False)
        raise typer.Exit(1) from None


def _print_draft_list(drafts: list) -> None:
    DRAFT_CACHE.parent.mkdir(exist_ok=True)
    DRAFT_CACHE.write_text(
        json.dumps({str(i): draft["id"] for i, draft in enumerate(drafts, 1)}),
        encoding="utf-8",
    )
    if not console.is_terminal:
        for i, draft in enumerate(drafts, 1):
            print(
                f"{i}.\t{draft['to']}\t{draft['subject']}\t"
                f"{draft['attachments']}\t{draft['id']}"
            )
        print("Preview one with: co gmail draft preview <# from this listing>")
        return

    table = Table(title=f"📝 Gmail drafts — {os.getenv('GOOGLE_EMAIL', '')}")
    table.add_column("#", justify="right")
    table.add_column("To", max_width=30, no_wrap=True)
    table.add_column("Subject", overflow="ellipsis", no_wrap=True)
    table.add_column("Files", justify="right")
    for i, draft in enumerate(drafts, 1):
        table.add_row(str(i), draft["to"] or "-", draft["subject"] or "(no subject)",
                      str(draft["attachments"]))
    console.print()
    console.print(table)
    console.print("\nPreview one with: [bold]co gmail draft preview <# from this listing>[/bold]\n")


def _print_draft_preview(draft: dict, tip: bool = True) -> None:
    console.print()
    console.print(f"Draft: {draft['id']}", markup=False, highlight=False)
    console.print(f"To: {draft['to'] or '-'}", markup=False, highlight=False)
    if draft.get("cc"):
        console.print(f"Cc: {draft['cc']}", markup=False, highlight=False)
    if draft.get("bcc"):
        console.print(f"Bcc: {draft['bcc']}", markup=False, highlight=False)
    console.print(f"Subject: {draft['subject'] or '(no subject)'}", markup=False, highlight=False)
    console.print("\n--- Body ---", markup=False)
    console.print(draft["body"] or "(empty body)", markup=False, highlight=False)
    console.print("\n--- Attachments ---", markup=False)
    if draft["attachments"]:
        for i, item in enumerate(draft["attachments"], 1):
            console.print(
                f"{i}. {item['name']} ({item['type']}, {item['size']} bytes)",
                markup=False,
                highlight=False,
            )
        console.print(f"Total: {draft['attachment_size']} bytes", markup=False)
    else:
        console.print("(none)", markup=False)
    if tip:
        console.print(f"\nSend with confirmation: [bold]co gmail draft send {draft['id']}[/bold]\n")


def _draft_id_or_exit(draft_id: str) -> str:
    resolved = _resolve_draft_id(draft_id)
    if not resolved:
        console.print(f"\n❌ [bold red]No draft #{draft_id} in your last listing.[/bold red]")
        console.print("List drafts: [bold]co gmail draft list[/bold]\n")
        raise typer.Exit(1)
    return resolved


def handle_gmail_draft_list(last: int = 20):
    gmail = _gmail()
    drafts = _draft_call(lambda: gmail.list_drafts(last=last), "co gmail draft list")
    if not drafts:
        DRAFT_CACHE.parent.mkdir(exist_ok=True)
        DRAFT_CACHE.write_text("{}", encoding="utf-8")
        console.print("\nGmail drafts: none")
        console.print("Create one with: [bold]co gmail draft create <to> <subject> <message>[/bold]\n")
        return
    _print_draft_list(drafts)


def handle_gmail_draft_create(to: str, subject: str, message: str, cc: str = None,
                              bcc: str = None):
    if message == "-":
        message = sys.stdin.read()
    gmail = _gmail(require_draft_write=True)
    draft = _draft_call(
        lambda: gmail.create_draft(to, subject, message, cc=cc, bcc=bcc),
        "co gmail draft create <to> <subject> <message>",
    )
    console.print(f"\n[green]✓ Draft created[/green] {draft['id']}")
    console.print(f"Attach a local file: [bold]co gmail draft attach {draft['id']} <path>[/bold]\n")


def handle_gmail_draft_attach(draft_id: str, source: str, drive: bool = False,
                              link: bool = False):
    if link and not drive:
        console.print("\n❌ [bold red]--link requires --drive.[/bold red]")
        console.print(
            f"Retry with: [bold]co gmail draft attach {draft_id} <Drive file # or id> --drive --link[/bold]\n"
        )
        raise typer.Exit(1)

    gmail = _gmail(require_draft_write=True)
    resolved = _draft_id_or_exit(draft_id)
    if drive:
        from .gdrive_commands import _gdrive, _resolve_file_id
        from ...useful_tools.gmail import GMAIL_ATTACHMENT_LIMIT

        file_id = _resolve_file_id(source)
        if not file_id:
            console.print(f"\n❌ [bold red]No Drive file #{source} in your last listing.[/bold red]")
            console.print("List Drive files: [bold]co gdrive[/bold]\n")
            raise typer.Exit(1)
        drive_client = _gdrive()
        if link:
            item = _draft_call(lambda: drive_client._get_file(file_id), "co gdrive")
            if not item["link"]:
                console.print("\n❌ [bold red]Drive returned no web link for this file.[/bold red]")
                console.print(f"Attach its bytes: [bold]co gmail draft attach {draft_id} {source} --drive[/bold]\n")
                raise typer.Exit(1)
            updated = _draft_call(
                lambda: gmail.add_draft_link(resolved, item["name"], item["link"]),
                f"co gmail draft attach {draft_id} {source} --drive --link",
            )
        else:
            item = _draft_call(
                lambda: drive_client._read_file(file_id, max_bytes=GMAIL_ATTACHMENT_LIMIT),
                f"co gmail draft attach {draft_id} {source} --drive",
            )
            updated = _draft_call(
                lambda: gmail._add_draft_attachment(
                    resolved, item["name"], item["type"], item["data"]
                ),
                f"co gmail draft attach {draft_id} {source} --drive",
            )
    else:
        updated = _draft_call(
            lambda: gmail.add_draft_attachment(resolved, source),
            f"co gmail draft attach {draft_id} <path that exists>",
        )

    action = "Drive link added" if link else "Attachment staged"
    console.print(f"\n[green]✓ {action}[/green]")
    console.print(f"Preview it: [bold]co gmail draft preview {updated['id']}[/bold]\n")


def handle_gmail_draft_remove(draft_id: str, attachment: int):
    gmail = _gmail(require_draft_write=True)
    resolved = _draft_id_or_exit(draft_id)
    updated = _draft_call(
        lambda: gmail.remove_draft_attachment(resolved, attachment),
        f"co gmail draft preview {resolved}",
    )
    console.print(f"\n[green]✓ Attachment removed[/green]")
    console.print(f"Preview it: [bold]co gmail draft preview {updated['id']}[/bold]\n")


def handle_gmail_draft_replace(draft_id: str, attachment: int, source: str,
                               drive: bool = False):
    gmail = _gmail(require_draft_write=True)
    resolved = _draft_id_or_exit(draft_id)
    if drive:
        from .gdrive_commands import _gdrive, _resolve_file_id
        from ...useful_tools.gmail import GMAIL_ATTACHMENT_LIMIT

        file_id = _resolve_file_id(source)
        if not file_id:
            console.print(f"\n❌ [bold red]No Drive file #{source} in your last listing.[/bold red]")
            console.print("List Drive files: [bold]co gdrive[/bold]\n")
            raise typer.Exit(1)
        item = _draft_call(
            lambda: _gdrive()._read_file(file_id, max_bytes=GMAIL_ATTACHMENT_LIMIT),
            f"co gmail draft replace {draft_id} {attachment} {source} --drive",
        )
        updated = _draft_call(
            lambda: gmail._replace_draft_attachment(
                resolved, attachment, item["name"], item["type"], item["data"]
            ),
            f"co gmail draft preview {resolved}",
        )
    else:
        updated = _draft_call(
            lambda: gmail.replace_draft_attachment(resolved, attachment, source),
            f"co gmail draft replace {draft_id} {attachment} <path that exists>",
        )
    console.print("\n[green]✓ Attachment replaced[/green]")
    console.print(f"Preview it: [bold]co gmail draft preview {updated['id']}[/bold]\n")


def handle_gmail_draft_preview(draft_id: str):
    gmail = _gmail()
    resolved = _draft_id_or_exit(draft_id)
    draft = _draft_call(lambda: gmail.get_draft(resolved), "co gmail draft list")
    _print_draft_preview(draft)


def handle_gmail_draft_send(draft_id: str):
    gmail = _gmail(require_draft_write=True)
    resolved = _draft_id_or_exit(draft_id)
    draft = _draft_call(lambda: gmail.get_draft(resolved), "co gmail draft list")
    _print_draft_preview(draft, tip=False)
    try:
        confirmed = typer.confirm("\nSend this Gmail draft now?", default=False)
    except (typer.Abort, KeyboardInterrupt, EOFError):
        confirmed = False
    if not confirmed:
        console.print("\n[yellow]Not sent; the Gmail draft was kept.[/yellow]")
        console.print(f"Preview again: [bold]co gmail draft preview {resolved}[/bold]\n")
        raise typer.Exit(1)
    sent = _draft_call(lambda: gmail._send_draft(resolved), f"co gmail draft send {resolved}")
    console.print(f"\n[green]✓ Sent[/green] Gmail message {sent.get('id', '')}")
    console.print("List sent mail: [bold]co gmail sent[/bold]\n")
