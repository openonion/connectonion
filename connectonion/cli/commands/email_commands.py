"""
Purpose: CLI surface for the agent mailbox — send, list (inbox), and read emails from the terminal
LLM-Note:
  Dependencies: imports from [rich.console, rich.table, rich.panel, .project_cmd_lib.load_api_key, ...useful_tools.send_email.send_email, ...useful_tools.get_emails.get_emails/mark_read] | imported by [cli/main.py via handle_email_*()] | hits the configured backend through the engine tools at [/api/v1/email/*]
  Data flow: load_api_key() ensures OPENONION_API_KEY + AGENT_EMAIL are in env → handle_email_send() → send_email(to, subject, message) → prints message_id | handle_email_inbox() → get_emails(last, unread, offset) → Rich table | handle_email_read() → get_emails() → find by id → print body → optionally mark_read(id)
  State/Effects: no local state | network calls happen inside the engine tools | only read --mark-read flips server-side read status | writes to stdout via rich.Console
  Integration: exposes handle_email_send(), handle_email_inbox(), handle_email_read(), handle_email_addresses() for cli/main.py | thin presentation layer — all email logic lives in useful_tools/{send_email,get_emails}.py | requires prior 'co auth'
  Errors: prints a 'run co auth' hint when no API key found | send_email returns {success, error} dicts (printed as-is); get_emails/mark_read let API errors crash
"""

import os
import shlex

import requests
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...backend import backend_url
from .project_cmd_lib import load_api_key

console = Console()

def _print_no_auth():
    console.print("\n❌ [bold red]No API key found[/bold red]")
    console.print("\n[cyan]Authenticate first:[/cyan]")
    console.print("  [bold]co auth[/bold]     Authenticate with OpenOnion\n")


def _require_auth() -> bool:
    """Ensure OPENONION_API_KEY (and the .env it lives next to) are loaded. Exits 1 if missing."""
    if load_api_key():
        return True
    _print_no_auth()
    raise typer.Exit(1)


def _err(response) -> str:
    """Pull a human-readable message out of an error response (JSON detail or raw text)."""
    if response.headers.get("content-type", "").startswith("application/json"):
        body = response.json()
        detail = body.get("detail", body)
        return detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
    return response.text.strip() or f"HTTP {response.status_code}"


def handle_email_send(
    to: str, subject: str, message: str,
    idempotency_key: str = None, from_address: str = None,
):
    """Send an email from the agent's address."""
    if not _require_auth():
        return

    from ...useful_tools.send_email import send_email
    result = send_email(
        to, subject, message,
        idempotency_key=idempotency_key, from_address=from_address,
    )

    if result.get("success"):
        console.print(f"\n[green]✓ Sent[/green] to [cyan]{to}[/cyan]")
        console.print(f"  From:       {result.get('from', '')}")
        console.print(f"  Message ID: {result.get('message_id', '')}")
        console.print("\n[dim]See it in your sent mail:[/dim] [bold]co email sent[/bold]\n")
    else:
        error = result.get("error", "Unknown error")
        console.print(f"\n❌ [bold red]Failed:[/bold red] {error}")
        if result.get("request_id"):
            console.print(f"  Request ID: {result['request_id']}")
        if result.get("retryable") and result.get("idempotency_key"):
            # The full command, restated — "the same command" is not in the
            # output, so an agent reading only this output could not retry.
            retry = ["co", "email", "send", shlex.quote(to), shlex.quote(subject), shlex.quote(message)]
            if from_address:
                retry += ["--from", shlex.quote(from_address)]
            retry += ["--idempotency-key", shlex.quote(result["idempotency_key"])]
            # Plain print, not console.print: Rich wraps at the console width,
            # and a line-broken command is no longer copy-pasteable.
            print("  Retry safely with: " + " ".join(retry))
        if "not one of this account's email addresses" in error:
            console.print("  See your addresses: [bold]co email addresses[/bold]")
        console.print()
        raise typer.Exit(1)


def handle_email_inbox(last: int = 10, unread: bool = False, offset: int = 0):
    """List recent emails received at the agent's address."""
    if not _require_auth():
        return

    from ...useful_tools.get_emails import get_emails
    emails = get_emails(last=last, offset=offset)
    page_is_full = len(emails) == last
    if unread:
        # The /received endpoint ignores the unread param, so filter here to keep the flag honest.
        emails = [e for e in emails if not e.get("read")]

    if not emails:
        scope = "unread " if unread else ""
        console.print(f"\n[cyan]Inbox:[/cyan] no {scope}emails\n")
        return

    table = Table(title="📬 Inbox", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("From")
    table.add_column("Subject")
    table.add_column("Received")

    for email in emails:
        unread_mark = "" if email.get("read") else "[bold green]●[/bold green] "
        table.add_row(
            str(email.get("id", "")),
            str(email.get("from", "")),
            f"{unread_mark}{email.get('subject', '')}",
            str(email.get("timestamp", ""))[:19],
        )

    console.print()
    console.print(table)
    console.print("\n[dim]Read one with:[/dim] [bold]co email read <#>[/bold]")
    if page_is_full:
        next_offset = offset + last
        console.print(
            "[dim]Next page:[/dim] "
            f"[bold]co email inbox --last {last} --offset {next_offset}[/bold]"
        )
    console.print()


def handle_email_sent(last: int = 10, to: str = None):
    """List emails the agent has sent."""
    if not _require_auth():
        return

    from ...useful_tools.get_emails import get_sent
    try:
        emails = get_sent(last=last, to=to)
    except requests.HTTPError as exc:
        response = exc.response
        if response is not None and response.status_code == 404:
            console.print(
                "\n[yellow]Sent mail is not available on this backend yet.[/yellow] "
                "The oo-api Sent endpoint must be deployed before this command can be used.\n"
            )
        else:
            status = response.status_code if response is not None else "unknown"
            console.print(f"\n[red]✗ Could not load sent mail (HTTP {status}).[/red]\n")
        raise typer.Exit(1)
    except requests.RequestException:
        console.print("\n[red]✗ Could not reach the email service.[/red] Try again later.\n")
        raise typer.Exit(1)

    if not emails:
        scope = f" to {to}" if to else ""
        console.print(f"\n[cyan]Sent:[/cyan] no emails{scope}\n")
        return

    table = Table(title="📤 Sent", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("To")
    table.add_column("Subject")
    table.add_column("Status")
    table.add_column("Sent")

    for email in emails:
        table.add_row(
            str(email.get("id", "")),
            str(email.get("to", "")),
            str(email.get("subject", "")),
            str(email.get("status", "")),
            str(email.get("timestamp", ""))[:19],
        )

    console.print()
    console.print(table)
    console.print("\n[dim]Read one with:[/dim] [bold]co email sent read <#>[/bold]\n")


def handle_email_sent_read(email_id: str):
    """Show a single sent email's body."""
    if not _require_auth():
        return

    from ...useful_tools.get_emails import get_sent
    try:
        emails = get_sent(last=100)
    except requests.HTTPError as exc:
        response = exc.response
        if response is not None and response.status_code == 404:
            console.print(
                "\n[yellow]Sent mail is not available on this backend yet.[/yellow] "
                "The oo-api Sent endpoint must be deployed before this command can be used.\n"
            )
        else:
            status = response.status_code if response is not None else "unknown"
            console.print(f"\n[red]✗ Could not load sent mail (HTTP {status}).[/red]\n")
        raise typer.Exit(1)
    except requests.RequestException:
        console.print("\n[red]✗ Could not reach the email service.[/red] Try again later.\n")
        raise typer.Exit(1)
    match = next((e for e in emails if str(e.get("id")) == str(email_id)), None)

    if not match:
        console.print(f"\n[yellow]No sent email with id {email_id} in your recent sent mail — run co email sent, then co email sent read <#>.[/yellow]\n")
        raise typer.Exit(1)

    header = (
        f"[cyan]To:[/cyan]         {match.get('to', '')}\n"
        f"[cyan]From:[/cyan]       {match.get('from', '')}\n"
        f"[cyan]Subject:[/cyan]    {match.get('subject', '')}\n"
        f"[cyan]Status:[/cyan]     {match.get('status', '')}\n"
        f"[cyan]Message ID:[/cyan] {match.get('message_id', '')}\n"
        f"[cyan]Date:[/cyan]       {match.get('timestamp', '')}"
    )
    console.print()
    console.print(Panel.fit(header, title=f"📤 Sent #{email_id}", border_style="cyan"))
    console.print()
    console.print(match.get("body", "") or "[dim](empty body)[/dim]")
    console.print()


def handle_email_read(email_id: str, mark_read: bool = False):
    """Show a single email's body; mutate its read state only when requested."""
    if not _require_auth():
        return

    from ...useful_tools.get_emails import get_emails
    emails = get_emails(last=1000)
    match = next((e for e in emails if str(e.get("id")) == str(email_id)), None)

    if not match:
        console.print(f"\n[yellow]No email with id {email_id} in your recent inbox — run co email inbox, then co email read <#>.[/yellow]\n")
        raise typer.Exit(1)

    header = (
        f"[cyan]From:[/cyan]    {match.get('from', '')}\n"
        f"[cyan]Subject:[/cyan] {match.get('subject', '')}\n"
        f"[cyan]Date:[/cyan]    {match.get('timestamp', '')}"
    )
    console.print()
    console.print(Panel.fit(header, title=f"✉️  Email #{email_id}", border_style="cyan"))
    console.print()
    console.print(match.get("message", "") or "[dim](empty body)[/dim]")
    console.print()

    if mark_read:
        from ...useful_tools.get_emails import mark_read as mark_email_read
        mark_email_read(str(email_id))
        console.print("[dim]Marked read.[/dim]")
    else:
        console.print("[dim]Unread state unchanged. Use --mark-read to change it.[/dim]")


def handle_email_addresses():
    """List every email address this account owns, marking the default sender."""
    token = load_api_key()
    if not token:
        _print_no_auth()
        raise typer.Exit(1)

    r = requests.get(
        f"{backend_url()}/api/v1/email/addresses",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if not r.ok:
        console.print(f"\n[red]✗ {_err(r)}[/red]\n")
        raise typer.Exit(1)

    addresses = r.json().get("addresses", [])
    if not addresses:
        console.print("\n[cyan]Addresses:[/cyan] none owned yet")
        console.print("\n[dim]Get one with:[/dim] [bold]co email name <name>[/bold]\n")
        return

    if not console.is_terminal:
        # Scripts and agents get tab-separated rows: address, default flag.
        # Plain print, not console.print: Rich expands \t into spaces.
        for a in addresses:
            print(f"{a['address']}\t{'default' if a.get('is_default') else ''}")
        print('Send as one with: co email send <to> "<subject>" "<body>" --from <address>')
        return

    table = Table(title="📧 Your addresses", show_header=True, header_style="bold cyan")
    table.add_column("Address")
    table.add_column("Default")
    table.add_column("Since")

    for a in addresses:
        table.add_row(
            str(a["address"]),
            "[green]✓[/green]" if a.get("is_default") else "",
            str(a.get("created_at") or "")[:10],
        )

    console.print()
    console.print(table)
    console.print('\n[dim]Send as one with:[/dim] [bold]co email send <to> "<subject>" "<body>" --from <address>[/bold]\n')


def handle_email_name(name: str, buy: bool = False):
    """Check whether a custom email name is available, or claim it (deducts credits)."""
    token = load_api_key()
    if not token:
        _print_no_auth()
        raise typer.Exit(1)

    headers = {"Authorization": f"Bearer {token}"}

    if not buy:
        r = requests.get(f"{backend_url()}/api/v1/email/check-name", params={"name": name}, headers=headers, timeout=10)
        if not r.ok:
            console.print(f"\n[red]✗ {_err(r)}[/red]\n")
            raise typer.Exit(1)
        data = r.json()
        if data.get("available"):
            console.print(f"\n[green]✓ {data['email']} is available[/green] — [bold]${data['price']:.2f}[/bold] one-time, from credits")
            console.print(f"[dim]Claim it:[/dim] [bold]co email name {name} --buy[/bold]\n")
        else:
            console.print(f"\n[yellow]✗ {data['email']} — {data.get('reason', 'unavailable')}[/yellow]\n")
        return

    r = requests.post(f"{backend_url()}/api/v1/email/purchase-name", json={"name": name}, headers=headers, timeout=15)
    if not r.ok:
        console.print(f"\n[red]✗ {_err(r)}[/red]\n")
        raise typer.Exit(1)
    data = r.json()
    console.print(f"\n[green]✓ {data['message']}[/green]")
    console.print(f"  Your address: [cyan]{data['email']}[/cyan]\n")


def handle_email_upgrade(
    tier: str,
    domain: str = None,
    alias: str = None,
    keep_address: bool = False,
):
    """Upgrade email tier (plus/pro), deducting the monthly price from credits."""
    token = load_api_key()
    if not token:
        _print_no_auth()
        raise typer.Exit(1)

    headers = {"Authorization": f"Bearer {token}"}
    payload = {"tier": tier}
    if domain:
        payload["domain"] = domain
    if alias:
        payload["alias"] = alias
    if keep_address:
        payload["keep_address"] = True

    r = requests.post(f"{backend_url()}/api/v1/email/upgrade", json=payload, headers=headers, timeout=15)
    if not r.ok:
        console.print(f"\n[red]✗ {_err(r)}[/red]\n")
        raise typer.Exit(1)
    data = r.json()
    console.print(f"\n[green]✓ {data['message']}[/green]")
    console.print(f"  Address: [cyan]{data['email_address']}[/cyan]")
    console.print(f"  Quota:   {data['emails_per_month']:,}/month")
    if data.get("balance") is not None:
        console.print(f"  Balance: ${data['balance']:.2f}")
    console.print()
