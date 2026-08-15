"""
Purpose: CLI surface for peer-to-peer credit transfers — send credits to another agent address and list transfer history
LLM-Note:
  Dependencies: imports from [requests, typer, rich.console, rich.table, ...backend.backend_url, .project_cmd_lib.load_api_key, .email_commands._err/_print_no_auth] | imported by [cli/main.py via handle_transfer_send()/handle_transfer_list()] | backend endpoints [POST/GET /api/v1/transfers, GET /api/v1/tokens/balance]
  Data flow: handle_transfer_send(address, amount) → print what will happen → typer.confirm unless --yes → POST /api/v1/transfers {to, amount, memo} → print sent amount + remaining balance (GET /api/v1/tokens/balance) + next-step tip | handle_transfer_list() → GET /api/v1/transfers?type=… → table (terminal) or tab-separated rows (piped), tip in both
  State/Effects: no local state | POST moves real money server-side — guarded by explicit confirmation | declined confirm exits 1 before anything is sent
  Integration: registered in cli/main.py as `co transfer <address> <amount>` and `co transfer list [--sent|--received]` | requires prior 'co auth'
  Errors: exit 1 with the server's message on any API failure | exit 1 on declined confirmation | exit 2 on missing/invalid amount | 'run co auth' hint when no API key
"""

import requests
import typer
from rich.console import Console
from rich.table import Table

from ...backend import backend_url
from .email_commands import _err, _print_no_auth
from .project_cmd_lib import load_api_key

console = Console()


def _require_token() -> str:
    token = load_api_key()
    if not token:
        _print_no_auth()
        raise typer.Exit(1)
    return token


def _balance(token: str):
    """Remaining balance in USD, or None when the balance endpoint is unavailable."""
    r = requests.get(
        f"{backend_url()}/api/v1/tokens/balance",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if not r.ok:
        return None
    data = r.json()
    return data.get("credits_usd", 0.0) - data.get("total_spent_usd", 0.0)


def handle_transfer_send(address: str, amount: float, memo: str = None, yes: bool = False):
    """Send credits to another agent address. Irreversible — confirms before posting."""
    if amount is None:
        console.print("\n[red]✗ Amount missing.[/red] Usage: [bold]co transfer <address> <amount>[/bold]\n")
        raise typer.Exit(2)
    if amount <= 0:
        console.print("\n[red]✗ Amount must be positive.[/red] Usage: [bold]co transfer <address> <amount>[/bold]\n")
        raise typer.Exit(2)

    token = _require_token()

    console.print(f"\nTransfer [bold]${amount:.2f}[/bold] of your credits to [cyan]{address}[/cyan].")
    console.print("[yellow]This cannot be undone.[/yellow]\n")
    if not yes and not typer.confirm(f"Send ${amount:.2f}?"):
        console.print("\nCancelled — nothing was sent.\n")
        raise typer.Exit(1)

    payload = {"to": address, "amount": amount}
    if memo:
        payload["memo"] = memo
    r = requests.post(
        f"{backend_url()}/api/v1/transfers",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if not r.ok:
        console.print(f"\n[red]✗ Transfer failed: {_err(r)}[/red]")
        console.print("[dim]Check your balance with:[/dim] [bold]co status[/bold]\n")
        raise typer.Exit(1)

    data = r.json()
    console.print(f"\n[green]✓ Sent[/green] [bold]${data['amount']:.2f}[/bold] to [cyan]{data['to_address']}[/cyan]  (transfer #{data['id']})")
    balance = _balance(token)
    if balance is not None:
        console.print(f"  Balance: [bold]${balance:.2f}[/bold]")
    console.print("\n[dim]See it in your history:[/dim] [bold]co transfer list[/bold]\n")


def handle_transfer_list(sent: bool = False, received: bool = False, last: int = 50):
    """List transfers this account sent and/or received."""
    if sent and received:
        console.print("\n[red]✗ Choose one of --sent or --received[/red] (neither shows both).\n")
        raise typer.Exit(2)

    token = _require_token()
    transfer_type = "sent" if sent else "received" if received else "all"
    r = requests.get(
        f"{backend_url()}/api/v1/transfers",
        params={"type": transfer_type, "limit": last},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if not r.ok:
        console.print(f"\n[red]✗ Could not load transfers: {_err(r)}[/red]")
        console.print("[dim]Check your account with:[/dim] [bold]co status[/bold]\n")
        raise typer.Exit(1)

    transfers = r.json()
    if not transfers:
        scope = {"sent": "sent ", "received": "received ", "all": ""}[transfer_type]
        console.print(f"\n[cyan]Transfers:[/cyan] no {scope}transfers yet")
        console.print("\n[dim]Send credits with:[/dim] [bold]co transfer <address> <amount>[/bold]\n")
        return

    if not console.is_terminal:
        # Scripts and agents get full addresses in tab-separated rows.
        # Plain print, not console.print: Rich expands \t into spaces.
        for t in transfers:
            print(f"{t['id']}\t{t['from_address']}\t{t['to_address']}\t{t['amount']}\t{t.get('memo') or ''}\t{t['created_at']}")
        print("Send credits with: co transfer <address> <amount>")
        return

    table = Table(title=f"💸 Transfers — {transfer_type}", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("From", max_width=16, no_wrap=True)
    table.add_column("To", max_width=16, no_wrap=True)
    table.add_column("Amount", justify="right")
    table.add_column("Memo", overflow="ellipsis", no_wrap=True)
    table.add_column("When")

    for t in transfers:
        table.add_row(
            str(t["id"]),
            str(t["from_address"]),
            str(t["to_address"]),
            f"${t['amount']:.2f}",
            t.get("memo") or "",
            str(t.get("created_at") or "")[:19],
        )

    console.print()
    console.print(table)
    console.print("\n[dim]Send credits with:[/dim] [bold]co transfer <address> <amount>[/bold]\n")
