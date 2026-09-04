"""Human and script-safe CLI for the Agent's encrypted SMS inbox."""

import json
import time

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

console = Console()


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

    console.print("\n[bold green]Scan with OpenOnion Messages[/bold green]\n")
    try:
        import qrcode

        qr = qrcode.QRCode(border=2)
        qr.add_data(pairing["pairing_link"])
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        console.print("[yellow]QR renderer unavailable; use the private link below.[/yellow]")
    # The link is intentionally visible only in an interactive human flow. It
    # is a one-time bearer secret until Android returns the signed claim.
    console.print(f"\n[dim]Private one-time link:[/dim]\n{pairing['pairing_link']}")
    console.print(f"\n[dim]Agent inbox:[/dim] {pairing['recipient']}")
    console.print(f"[dim]Expires:[/dim] {pairing['expires_at']}\n")
    if not wait:
        return

    deadline = time.monotonic() + expires
    while time.monotonic() < deadline:
        status = get_sms_pairing(pairing["id"])
        if status["status"] == "pending":
            device = status.get("device") or {}
            device_public_key = status["device_public_key"]
            code = pairing_confirmation_code(pairing["pairing_link"], device_public_key)
            console.print(
                "\n[bold]Confirm this phone[/bold]\n"
                f"  Device: {device.get('device_name', 'Android device')}\n"
                f"  Code:   [bold green]{code[:3]} {code[3:]}[/bold green]\n"
            )
            if not Confirm.ask("Does the same code appear on the phone?", default=False):
                console.print("[yellow]Not confirmed. The pairing will expire automatically.[/yellow]")
                raise typer.Exit(1)
            confirm_sms_pairing(
                pairing["id"],
                pairing["pairing_link"],
                device_public_key,
                code,
            )
            console.print("\n[green]✓ Phone approved[/green]")
            console.print("[dim]The phone can now activate its upload-only credential.[/dim]\n")
            return
        if status["status"] == "expired":
            break
        time.sleep(2)
    console.print("\n[yellow]Pairing expired before a phone was confirmed.[/yellow]\n")
    raise typer.Exit(1)


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
    console.print()


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
