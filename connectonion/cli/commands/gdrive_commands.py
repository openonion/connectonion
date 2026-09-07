"""Drive CLI with frozen account-bound listings and read-only inspection."""

import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from .google_errors import google_errors
from .command_tips import print_tip

from ...provider_credentials import resolve_provider_credentials

console = Console()

from ...environment import global_config_dir
from .gmail_listings import save_listing, resolve_reference

LIST_CACHE = global_config_dir() / "gdrive_last_list.json"  # legacy location; only its parent is used


def _gdrive():
    """Load GOOGLE_* credentials from .env files and return a GDrive instance. Exits 1 with a hint if not connected."""
    from ...environment import load_environment
    load_environment()
    from ...provider_credentials import resolve_provider_credentials
    record = resolve_provider_credentials("google")
    auth_tip = record.auth_command

    if not (record.get("ACCESS_TOKEN") or record.get("REFRESH_TOKEN")):
        console.print("\n❌ [bold red]Google account not connected[/bold red]")
        console.print("\n[cyan]Connect Google Drive first:[/cyan]")
        print(f"Next: {auth_tip}")
        raise typer.Exit(1)

    from ...useful_tools.google_scopes import granted_scopes
    scopes = granted_scopes()
    if scopes and not scopes.intersection({"drive", "drive.readonly"}):
        # Drive was added to the OAuth scopes after Gmail and Calendar — a token
        # from before that grants everything else but not this.
        console.print("\n❌ [bold red]Google Drive permission missing[/bold red]")
        console.print("\n[cyan]Reconnect Google to grant it:[/cyan]")
        print(f"Next: {auth_tip}")
        raise typer.Exit(1)

    from ...useful_tools.gdrive import GDrive
    return GDrive()


def _size(count: int) -> str:
    """Render a byte count as B/KB/MB/GB; '-' for the sizeless (folders, native docs)."""
    if not count:
        return "-"
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024


def _kind(mime: str) -> str:
    """Render a mimeType as a short human label."""
    from ...useful_tools.gdrive import NATIVE_PREFIX

    if mime.startswith(NATIVE_PREFIX):
        return mime[len(NATIVE_PREFIX):]
    return mime.rsplit("/", 1)[-1]


def _when(timestamp: str) -> str:
    """Render Drive's RFC 3339 modifiedTime as 'Jul 26 14:30' in local time."""
    from datetime import datetime

    if not timestamp:
        return ""
    # Drive sends fractional seconds ('2026-07-26T14:30:00.123Z'), which
    # fromisoformat() rejects on Python 3.10 — display is minute-granular.
    cleaned = timestamp.replace("Z", "+00:00").split(".")[0]
    if "+" in timestamp and "." in timestamp:
        cleaned = f"{cleaned}+00:00"
    return datetime.fromisoformat(cleaned).astimezone().strftime("%b %d %H:%M")


def _print_listing(drive, files: list, title: str):
    """Render files as a numbered table (or tab-separated rows with full ids when piped) and cache the numbering."""
    token = save_listing(LIST_CACHE.parent / "gdrive-listings", drive.get_account_email(),
                         "files", [item["id"] for item in files], provider="gdrive")
    if not console.is_terminal:
        # Scripts and agents get full file ids, never a truncated column.
        # Plain print, not console.print: Rich expands \t into spaces, which
        # silently turns tab-separated output into something cut -f can't read.
        for i, item in enumerate(files, 1):
            print(f"{item['name']}\t{item['type']}\t{item['size']}\t{item['id']}\t{i}")
        # Same next-step tip as the terminal table: piped callers are exactly
        # the AI audience the tip exists for.
        print(f"Listing: {token} (15 minutes; use --listing {token} with a row)")
        if files:
            print_tip(f"Download one with: co gdrive get {files[0]['id']}")
        return

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("Name", overflow="ellipsis", no_wrap=True)
    table.add_column("Kind", max_width=14, no_wrap=True)
    table.add_column("Size", justify="right")
    table.add_column("Modified")

    for i, item in enumerate(files, 1):
        table.add_row(str(i), item["name"], _kind(item["type"]), _size(item["size"]), _when(item["modified"]))

    console.print()
    console.print(table)
    print(f"Listing: {token} (15 minutes; use --listing {token} with a row)")
    if files:
        print_tip(f"Download one with: co gdrive get {files[0]['id']}")


@google_errors("co gdrive list")
def handle_gdrive_list(last: int = 20):
    """List recently modified Drive files as a numbered table."""
    drive = _gdrive()
    files = drive.list_files(last=last)
    if not files:
        _print_listing(drive, [], "Drive")
        console.print("\n[cyan]Google Drive:[/cyan] no files\n")
        print_tip("Search by name: co gdrive search <name prefix>")
        return
    _print_listing(drive, files, f"📁 Drive — {resolve_provider_credentials('google').get('EMAIL') or ''}")


@google_errors("co gdrive list")
def handle_gdrive_search(query: str, last: int = 20):
    """Search Drive by file name, numbered like the listing."""
    drive = _gdrive()
    files = drive.search_files(query, last=last)
    if not files:
        _print_listing(drive, [], "Drive")
        console.print(f"\n[cyan]Drive search:[/cyan] no files matching [bold]{query}[/bold]")
        console.print("[dim]Drive matches word prefixes, not any substring.[/dim]\n")
        print_tip("Show recent files: co gdrive list")
        return
    _print_listing(drive, files, f"🔎 Drive — {query}")


def _resolve_file_id(file_id: str, drive=None, listing: str | None = None) -> str:
    """Resolve a number only within its frozen provider-confirmed listing."""
    number = file_id.removeprefix('#')
    if not (number.isascii() and number.isdigit() and len(number) < 5):
        return file_id
    account = drive.get_account_email() if drive is not None else ''
    return resolve_reference(LIST_CACHE.parent / "gdrive-listings", file_id, account,
                             "files", listing, provider="gdrive")


@google_errors("co gdrive list")
def handle_gdrive_get(file_id: str, dest: str = ".", *, listing: str | None = None):
    """Download a Drive file. Accepts the listing # or a full file id."""
    drive = _gdrive()
    resolved = _resolve_file_id(file_id, drive, listing)
    if not resolved:
        console.print(f"\nNo file #{file_id} in your last listing.", markup=False)
        print_tip("Refresh the listing: co gdrive list")
        raise typer.Exit(1)

    console.print(drive.download(resolved, dest=dest).replace("Downloaded to", "\n[green]✓ Downloaded[/green]"))
    print_tip("Show more files: co gdrive list")


@google_errors("co gdrive list")
def handle_gdrive_put(path: str, name: str = None):
    """Upload a local file to Drive."""
    if not Path(path).expanduser().is_file():
        console.print(f"\n❌ [bold red]File not found:[/bold red] {path}\n")
        print_tip("Retry with: co gdrive put <path to an existing file>")
        raise typer.Exit(1)

    drive = _gdrive()
    uploaded = drive.upload(path, name=name)
    console.print(f"\n[green]✓ Uploaded[/green] [bold]{uploaded['name']}[/bold]")
    if uploaded["link"]:
        console.print(f"  {uploaded['link']}")
    print_tip("Check uploaded files: co gdrive list")


@google_errors("co gdrive list")
def handle_gdrive_rm(file_id: str, *, listing: str | None = None):
    """Move a Drive file to the trash. Accepts the listing # or a full file id."""
    drive = _gdrive()
    resolved = _resolve_file_id(file_id, drive, listing)
    if not resolved:
        console.print(f"\nNo file #{file_id} in your last listing.", markup=False)
        print_tip("Refresh the listing: co gdrive list")
        raise typer.Exit(1)

    drive.delete(resolved)
    console.print("\n[green]✓ Moved to trash[/green] — restore it from drive.google.com if that was wrong\n")
    print_tip("Show remaining files: co gdrive list")


@google_errors("co gdrive list")
def _inspect_file(file_id: str, listing: str | None = None) -> tuple[str, dict]:
    drive = _gdrive()
    return drive.get_account_email(), drive.get_info(_resolve_file_id(file_id, drive, listing))


def handle_gdrive_info(file_id: str, *, listing: str | None = None, json_output: bool = False) -> None:
    """Inspect a full Drive file ID with a single machine-readable result."""
    from contextlib import redirect_stdout, redirect_stderr
    import io
    import shlex
    from ...environment import selected_command
    result = {"schema_version":1, "provider":"gdrive", "operation":"info", "account":None,
              "status":"error", "complete":False, "data":None, "error":None}
    output = io.StringIO()
    next_command = 'co gdrive list'
    try:
        with redirect_stdout(output), redirect_stderr(output):
            account, data = _inspect_file(file_id, listing)
        result.update(account=account, data=data, status="success", complete=True)
        next_command = f'co gdrive get {shlex.quote(data["id"])}'
    except typer.Exit:
        result['error'] = {"code":"inspection_failed", "message":output.getvalue().strip()}
        if 'co auth google' in output.getvalue():
            next_command = 'co auth google'
    result['next_command'] = selected_command(next_command)
    if json_output:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result['data'] or result['error'], ensure_ascii=False, indent=2))
        print_tip(f'Next: {result["next_command"]}')
    if not result['complete']:
        raise typer.Exit(1)
