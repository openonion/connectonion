"""
Purpose: CLI surface for the agent mailbox — send, list (inbox), and read emails from the terminal
LLM-Note:
  Dependencies: imports from [rich.console, rich.table, rich.panel, .project_cmd_lib.load_api_key, ...useful_tools.send_email.send_email, ...useful_tools.get_emails.get_emails/mark_read] | imported by [cli/main.py via handle_email_*()] | hits backend through the engine tools at [oo.openonion.ai/api/v1/email/*]
  Data flow: load_api_key() ensures OPENONION_API_KEY + AGENT_EMAIL are in env → handle_email_send() → send_email(to, subject, message) → prints message_id | handle_email_inbox() → get_emails(last, unread) → Rich table | handle_email_read() → get_emails() → find by id → print body → mark_read(id)
  State/Effects: no local state | network calls happen inside the engine tools | mark_read() flips server-side read status | writes to stdout via rich.Console
  Integration: exposes handle_email_send(), handle_email_inbox(), handle_email_read() for cli/main.py | thin presentation layer — all email logic lives in useful_tools/{send_email,get_emails}.py | requires prior 'co auth'
  Errors: prints a 'run co auth' hint when no API key found | send_email returns {success, error} dicts (printed as-is); get_emails/mark_read let API errors crash
"""

import os

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .project_cmd_lib import load_api_key

console = Console()

BACKEND = os.getenv("CONNECTONION_BACKEND_URL", "https://oo.openonion.ai")


def _print_no_auth():
    console.print("\n❌ [bold red]No API key found[/bold red]")
    console.print("\n[cyan]Authenticate first:[/cyan]")
    console.print("  [bold]co auth[/bold]     Authenticate with OpenOnion\n")


def _require_auth() -> bool:
    """Ensure OPENONION_API_KEY (and the .env it lives next to) are loaded. Returns False if missing."""
    if load_api_key():
        return True
    _print_no_auth()
    return False


def _err(response) -> str:
    """Pull a human-readable message out of an error response (JSON detail or raw text)."""
    if response.headers.get("content-type", "").startswith("application/json"):
        body = response.json()
        detail = body.get("detail", body)
        return detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
    return response.text.strip() or f"HTTP {response.status_code}"


def handle_email_send(to: str, subject: str, message: str):
    """Send an email from the agent's address."""
    if not _require_auth():
        return

    from ...useful_tools.send_email import send_email
    result = send_email(to, subject, message)

    if result.get("success"):
        console.print(f"\n[green]✓ Sent[/green] to [cyan]{to}[/cyan]")
        console.print(f"  From:       {result.get('from', '')}")
        console.print(f"  Message ID: {result.get('message_id', '')}\n")
    else:
        console.print(f"\n❌ [bold red]Failed:[/bold red] {result.get('error', 'Unknown error')}\n")


def handle_email_inbox(last: int = 10, unread: bool = False):
    """List recent emails received at the agent's address."""
    if not _require_auth():
        return

    from ...useful_tools.get_emails import get_emails
    emails = get_emails(last=last)
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
    console.print("\n[dim]Read one with:[/dim] [bold]co email read <#>[/bold]\n")


def handle_email_read(email_id: str):
    """Show a single email's body and mark it read."""
    if not _require_auth():
        return

    from ...useful_tools.get_emails import get_emails, mark_read
    emails = get_emails(last=100)
    match = next((e for e in emails if str(e.get("id")) == str(email_id)), None)

    if not match:
        console.print(f"\n[yellow]No email with id {email_id} in your recent inbox.[/yellow]\n")
        return

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

    mark_read(str(email_id))


def handle_email_name(name: str, buy: bool = False):
    """Check whether a custom email name is available, or claim it (deducts credits)."""
    token = load_api_key()
    if not token:
        _print_no_auth()
        return

    headers = {"Authorization": f"Bearer {token}"}

    if not buy:
        r = requests.get(f"{BACKEND}/api/v1/email/check-name", params={"name": name}, headers=headers, timeout=10)
        if not r.ok:
            console.print(f"\n[red]✗ {_err(r)}[/red]\n")
            return
        data = r.json()
        if data.get("available"):
            console.print(f"\n[green]✓ {data['email']} is available[/green] — [bold]${data['price']:.2f}[/bold] one-time, from credits")
            console.print(f"[dim]Claim it:[/dim] [bold]co email name {name} --buy[/bold]\n")
        else:
            console.print(f"\n[yellow]✗ {data['email']} — {data.get('reason', 'unavailable')}[/yellow]\n")
        return

    r = requests.post(f"{BACKEND}/api/v1/email/purchase-name", json={"name": name}, headers=headers, timeout=15)
    if not r.ok:
        console.print(f"\n[red]✗ {_err(r)}[/red]\n")
        return
    data = r.json()
    console.print(f"\n[green]✓ {data['message']}[/green]")
    console.print(f"  Your address: [cyan]{data['email']}[/cyan]\n")


def handle_email_upgrade(tier: str, domain: str = None, alias: str = None):
    """Upgrade email tier (plus/pro), deducting the monthly price from credits."""
    token = load_api_key()
    if not token:
        _print_no_auth()
        return

    headers = {"Authorization": f"Bearer {token}"}
    payload = {"tier": tier}
    if domain:
        payload["domain"] = domain
    if alias:
        payload["alias"] = alias

    r = requests.post(f"{BACKEND}/api/v1/email/upgrade", json=payload, headers=headers, timeout=15)
    if not r.ok:
        console.print(f"\n[red]✗ {_err(r)}[/red]\n")
        return
    data = r.json()
    console.print(f"\n[green]✓ {data['message']}[/green]")
    console.print(f"  Address: [cyan]{data['email_address']}[/cyan]")
    console.print(f"  Quota:   {data['emails_per_month']:,}/month")
    if data.get("balance") is not None:
        console.print(f"  Balance: ${data['balance']:.2f}")
    console.print()
