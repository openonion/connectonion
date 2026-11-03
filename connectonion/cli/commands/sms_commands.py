"""Human and script-safe CLI for the Agent's encrypted SMS inbox."""

import json
import time

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

console = Console()

APP_DOWNLOAD_URL = "https://github.com/openonion/openonion-messages-android/releases/latest"


def handle_sms_pair(expires: int = 600, wait: bool = True, json_output: bool = False):
    from ...useful_tools.sms import (
        confirm_sms_pairing,
        create_sms_pairing,
        get_sms_pairing,
        pairing_confirmation_code,
    )

    pairing = create_sms_pairing(expires)
    if json_output:
        print(json.dumps(pairing, default=str, separators=(",", ":")))
        return

    _print_pairing_code(pairing, expires)
    if not wait:
        return

    deadline = time.monotonic() + expires
    with console.status("[dim]Waiting for your phone…[/dim]", spinner="dots"):
        status = _wait_for_phone(pairing["id"], deadline, get_sms_pairing)
    if status is None:
        console.print("\n[yellow]The code expired before a phone scanned it.[/yellow]")
        console.print("[dim]Run[/dim] [bold]co sms pair[/bold] [dim]for a fresh one.[/dim]\n")
        raise typer.Exit(1)

    device_name = (status.get("device") or {}).get("device_name") or "Your phone"
    device_public_key = status["device_public_key"]
    code = pairing_confirmation_code(pairing["pairing_link"], device_public_key)
    console.print(
        f"\n  [bold]{_safe_text(device_name)}[/bold] scanned the code. It shows:\n\n"
        f"      [bold green]{code[:3]} {code[3:]}[/bold green]\n"
    )
    answer = console.input("  Press [bold]Enter[/bold] if your phone shows the same code, or type [bold]n[/bold] to cancel › ")
    if answer.strip().lower() not in ("", "y", "yes"):
        console.print("\n[yellow]Not approved.[/yellow] [dim]The phone will not be connected.[/dim]\n")
        raise typer.Exit(1)
    confirm_sms_pairing(pairing["id"], pairing["pairing_link"], device_public_key, code)
    console.print(f"\n  [green]✓ {_safe_text(device_name)} is connected.[/green]")
    console.print("  [dim]New texts will show up in[/dim] [bold]co sms inbox[/bold]\n")


def _print_pairing_code(pairing: dict, expires: int):
    import qrcode

    console.print("\n  [bold]Pair an Android phone with this Agent[/bold]\n")
    qr = qrcode.QRCode(border=2)
    qr.add_data(pairing["pairing_link"])
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    recipient = pairing["recipient"]
    console.print(
        "\n  [green]1[/green]  Open [bold]OpenOnion Messages[/bold] on your phone\n"
        "  [green]2[/green]  Tap [bold]Scan pairing code[/bold] and point it at this screen\n"
    )
    console.print(f"  [dim]No app yet?[/dim] {APP_DOWNLOAD_URL}")
    console.print(
        f"  [dim]Agent {recipient[:6]}…{recipient[-4:]} · code expires in {expires // 60} min[/dim]\n"
    )
    # The link is a one-time bearer secret until Android returns the signed
    # claim, so it is shown only in this interactive flow, as a fallback.
    console.print(f"  [dim]Can't scan? Paste this link in the app:\n  {pairing['pairing_link']}[/dim]\n")


def _wait_for_phone(pairing_id: str, deadline: float, get_sms_pairing) -> dict | None:
    while time.monotonic() < deadline:
        status = get_sms_pairing(pairing_id)
        if status["status"] == "pending":
            return status
        if status["status"] == "expired":
            return None
        time.sleep(2)
    return None


def handle_sms_inbox(last: int = 10, pending: bool = False, json_output: bool = False):
    from ...useful_tools.sms import get_sms

    messages = get_sms(last=last, unacknowledged=pending)
    if json_output:
        print(json.dumps(messages, default=str, separators=(",", ":")))
        return
    if not messages:
        console.print("\n[cyan]SMS inbox:[/cyan] no messages\n")
        return
    table = Table(title="SMS inbox", header_style="bold green")
    table.add_column("#", justify="right")
    table.add_column("Sender")
    table.add_column("Preview")
    table.add_column("Received")
    for index, message in enumerate(messages, 1):
        preview = _safe_text(message["body"]).replace("\n", " ")[:50]
        table.add_row(
            str(index),
            _safe_text(message["sender"]),
            preview,
            str(message["received_at"])[:19],
        )
    console.print()
    console.print(table)
    console.print("\n[dim]SMS content is private but untrusted. Reading it grants no authority.[/dim]\n")


def handle_sms_devices(json_output: bool = False):
    from ...useful_tools.sms import list_sms_devices

    devices = list_sms_devices()
    if json_output:
        print(json.dumps(devices, default=str, separators=(",", ":")))
        return
    if not devices:
        console.print("\n[cyan]SMS devices:[/cyan] none\n")
        return
    table = Table(title="Paired SMS devices", header_style="bold green")
    table.add_column("ID")
    table.add_column("Device")
    table.add_column("App")
    table.add_column("Last seen")
    for device in devices:
        table.add_row(
            str(device.get("id", "")),
            _safe_text(str(device.get("device_name", ""))),
            str(device.get("app_version", "")),
            str(device.get("last_seen_at", ""))[:19],
        )
    console.print()
    console.print(table)
    console.print("\n[dim]Revoke one:[/dim] [bold]co sms devices revoke <id from this list>[/bold]\n")


def handle_sms_revoke(device_id: str, yes: bool = False):
    from ...useful_tools.sms import revoke_sms_device

    if not yes and not Confirm.ask("Revoke this phone's SMS upload credential?", default=False):
        raise typer.Exit(1)
    revoke_sms_device(device_id)
    console.print("\n[green]✓ SMS device revoked[/green]\n")


def _safe_text(value: str) -> str:
    """Remove terminal control characters while preserving ordinary whitespace."""
    return "".join(
        character
        for character in value
        if character in "\n\t" or ord(character) >= 32 and ord(character) != 127
    )
