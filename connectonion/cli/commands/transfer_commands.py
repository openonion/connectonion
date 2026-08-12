"""
Purpose: Transfer OpenOnion credits from this account to another address
LLM-Note:
  Dependencies: imports from [requests, rich.console, backend.backend_url, project_cmd_lib.load_api_key] | imported by [cli/main.py via handle_transfer()] | calls the configured backend /api/v1/transfers and /api/v1/auth/me | tested by [tests/e2e/cli/test_cli_transfer.py]
  Data flow: receives address/amount/memo → load_api_key() resolves the account token → GET /api/v1/auth/me for the starting balance → POST /api/v1/transfers → GET /api/v1/auth/me again → prints from/to/amount and the balance before → after
  State/Effects: moves credits between two accounts on the backend — not reversible from the CLI | no local file writes | two or three network calls
  Integration: exposes handle_transfer(address, amount, memo) for CLI | reuses the same token resolution as `co status` so the account charged is the account shown there
  Performance: 2-3 backend round trips, ~1-3s total
  Errors: refuses a non-positive amount and a self-transfer before spending anything | surfaces the backend's own message for insufficient balance or an unknown recipient | a failed balance read never blocks the transfer, it only drops that line from the output
"""

from typing import Optional

import requests
from rich.console import Console

from ...backend import backend_url
from .project_cmd_lib import load_api_key

console = Console()

TIMEOUT = 30


def _balance(api_key: str) -> Optional[float]:
    """Current balance in USD, or None if it cannot be read.

    Only ever used to decorate the output. A transfer that succeeded must not
    look like it failed because this call did.
    """
    try:
        response = requests.get(
            f"{backend_url()}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            return None
        return response.json().get("balance_usd")
    except requests.RequestException:
        return None


def _short(address: str) -> str:
    """0x1234...abcd — long enough to recognise, short enough to read."""
    return f"{address[:6]}...{address[-4:]}" if len(address) > 14 else address


def _error(response: requests.Response) -> str:
    """The backend's own reason, falling back to the status code."""
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    detail = body.get("detail") or body.get("message")
    if isinstance(detail, list) and detail:
        detail = detail[0].get("msg", detail[0])
    return str(detail) if detail else f"HTTP {response.status_code}"


def handle_transfer(address: str, amount: float, memo: Optional[str] = None) -> bool:
    """Transfer credits to another address. Returns True when the money moved."""
    # Checked here rather than only server-side so an obvious mistake costs a
    # round trip and not a transfer.
    if amount <= 0:
        console.print("[red]Amount must be greater than zero.[/red]")
        return False

    api_key = load_api_key()
    if not api_key:
        console.print("[red]Not authenticated.[/red] Run [cyan]co auth[/cyan] first.")
        return False

    before = _balance(api_key)
    if before is not None and amount > before:
        console.print(
            f"[red]Balance is ${before:.2f} — not enough for ${amount:.2f}.[/red]\n"
            "Add credits at https://o.openonion.ai/purchase"
        )
        return False

    payload = {"to": address, "amount": amount}
    if memo:
        payload["memo"] = memo

    console.print(f"\nTransferring [cyan]${amount:.2f}[/cyan] to [cyan]{_short(address)}[/cyan]")

    try:
        response = requests.post(
            f"{backend_url()}/api/v1/transfers",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        # The request may or may not have reached the backend. Say so instead of
        # implying nothing happened.
        console.print(f"[red]Transfer failed:[/red] {exc}")
        console.print("[yellow]Check [cyan]co transfer --list[/cyan] before retrying.[/yellow]")
        return False

    if response.status_code != 200:
        console.print(f"[red]Transfer failed:[/red] {_error(response)}")
        return False

    result = response.json()
    after = _balance(api_key)

    console.print("\n[green]✓ Transfer complete[/green]")
    console.print(f"  From:    {_short(result.get('from_address', ''))}")
    console.print(f"  To:      {_short(result.get('to_address', address))}")
    console.print(f"  Amount:  ${float(result.get('amount', amount)):.2f}")
    if memo:
        console.print(f"  Memo:    {memo}")
    if before is not None and after is not None:
        console.print(f"  Balance: ${before:.2f} → ${after:.2f}")
    return True


def handle_transfer_list(direction: str = "all", limit: int = 20) -> bool:
    """Print recent transfers. `direction` is sent, received, or all."""
    api_key = load_api_key()
    if not api_key:
        console.print("[red]Not authenticated.[/red] Run [cyan]co auth[/cyan] first.")
        return False

    try:
        response = requests.get(
            f"{backend_url()}/api/v1/transfers",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"type": direction, "limit": limit},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        console.print(f"[red]Could not load transfers:[/red] {exc}")
        return False

    if response.status_code != 200:
        console.print(f"[red]Could not load transfers:[/red] {_error(response)}")
        return False

    transfers = response.json()
    if not transfers:
        console.print(f"\n[cyan]Transfers ({direction}):[/cyan] none\n")
        return True

    console.print(f"\n[cyan]Transfers ({direction}):[/cyan]")
    for item in transfers:
        created = str(item.get("created_at", ""))[:19].replace("T", " ")
        line = (
            f"  {created}  ${float(item.get('amount', 0)):>8.2f}  "
            f"{_short(item.get('from_address', ''))} → {_short(item.get('to_address', ''))}"
        )
        if item.get("memo"):
            line += f"  ({item['memo']})"
        console.print(line)
    console.print()
    return True
