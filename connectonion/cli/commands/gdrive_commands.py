"""
Purpose: CLI surface for the user's Google Drive — list, search, download, upload, and trash files from the terminal
LLM-Note:
  Dependencies: imports from [json, os, pathlib, typer, dotenv, rich.console, rich.table, ...useful_tools.gdrive.GDrive] | imported by [cli/main.py via handle_gdrive_*()] | hits the Drive API through the GDrive tool
  Data flow: _gdrive() loads GOOGLE_* from .env / ~/.co/keys.env and checks the drive scope → GDrive() instance | list/search: list_files()/search_files() → numbered Rich table (tab-separated with full ids when piped) → saves {#: file_id} to ~/.co/gdrive_last_list.json | get/rm: resolve short numbers via that cache → download()/delete()
  State/Effects: writes ~/.co/gdrive_last_list.json (last listing's # → file id map; "numbers mean your last listing") | downloads write local files | put uploads to Drive | rm trashes (recoverable) rather than deleting
  Integration: exposes handle_gdrive_list(), handle_gdrive_search(), handle_gdrive_get(), handle_gdrive_put(), handle_gdrive_rm() for cli/main.py | presentation mirrors gmail_commands.py / outlook_commands.py | Drive logic lives in useful_tools/gdrive.py | requires prior 'co auth google'
  Errors: guarded failures print a hint and exit 1 (typer.Exit) — missing auth/drive scope, unresolvable file #, missing upload path | Drive API errors propagate from the GDrive tool
"""

import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()

LIST_CACHE = Path.home() / ".co" / "gdrive_last_list.json"


def _gdrive():
    """Load GOOGLE_* credentials from .env files and return a GDrive instance. Exits 1 with a hint if not connected."""
    from dotenv import load_dotenv

    for env_path in [Path(".env"), Path.home() / ".co" / "keys.env"]:
        if env_path.exists():
            load_dotenv(env_path)

    if not os.getenv("GOOGLE_ACCESS_TOKEN"):
        console.print("\n❌ [bold red]Google account not connected[/bold red]")
        console.print("\n[cyan]Connect Google Drive first:[/cyan]")
        console.print("  [bold]co auth google[/bold]     Authorize Drive access\n")
        raise typer.Exit(1)

    if "drive" not in os.getenv("GOOGLE_SCOPES", ""):
        # Drive was added to the OAuth scopes after Gmail and Calendar — a token
        # from before that grants everything else but not this.
        console.print("\n❌ [bold red]Google Drive permission missing[/bold red]")
        console.print("\n[cyan]Reconnect Google to grant it:[/cyan]")
        console.print("  [bold]co auth google[/bold]     Re-authorize with Drive access\n")
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


def _print_listing(files: list, title: str):
    """Render files as a numbered table (or tab-separated rows with full ids when piped) and cache the numbering."""
    LIST_CACHE.parent.mkdir(parents=True, exist_ok=True)
    LIST_CACHE.write_text(json.dumps({str(i): f["id"] for i, f in enumerate(files, 1)}), encoding="utf-8")

    if not console.is_terminal:
        # Scripts and agents get full file ids, never a truncated column.
        # Plain print, not console.print: Rich expands \t into spaces, which
        # silently turns tab-separated output into something cut -f can't read.
        for item in files:
            print(f"{item['name']}\t{item['type']}\t{item['size']}\t{item['id']}")
        # Same next-step tip as the terminal table: piped callers are exactly
        # the AI audience the tip exists for.
        print("Download one with: co gdrive get <#>")
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
    console.print("\n[dim]Download one with:[/dim] [bold]co gdrive get <#>[/bold]\n")


def handle_gdrive_list(last: int = 20):
    """List recently modified Drive files as a numbered table."""
    drive = _gdrive()
    files = drive.list_files(last=last)
    if not files:
        console.print("\n[cyan]Google Drive:[/cyan] no files\n")
        return
    _print_listing(files, f"📁 Drive — {os.getenv('GOOGLE_EMAIL', '')}")


def handle_gdrive_search(query: str, last: int = 20):
    """Search Drive by file name, numbered like the listing."""
    drive = _gdrive()
    files = drive.search_files(query, last=last)
    if not files:
        console.print(f"\n[cyan]Drive search:[/cyan] no files matching [bold]{query}[/bold]")
        console.print("[dim]Drive matches word prefixes, not any substring.[/dim]\n")
        return
    _print_listing(files, f"🔎 Drive — {query}")


def _resolve_file_id(file_id: str) -> str:
    """Turn a listing number into a Drive file id; full ids pass through."""
    cached = json.loads(LIST_CACHE.read_text(encoding="utf-8")) if LIST_CACHE.exists() else {}
    if file_id in cached:
        return cached[file_id]

    if file_id.isascii() and file_id.isdigit() and len(file_id) < 5:
        # A short number means "row N of what you just showed me" — refetching a
        # differently ordered listing would silently act on the wrong file.
        return ""
    return file_id


def handle_gdrive_get(file_id: str, dest: str = "."):
    """Download a Drive file. Accepts the listing # or a full file id."""
    drive = _gdrive()
    resolved = _resolve_file_id(file_id)
    if not resolved:
        console.print(f"\n[yellow]No file #{file_id} in your last listing — run co gdrive, then co gdrive get <#>.[/yellow]\n")
        raise typer.Exit(1)

    console.print(drive.download(resolved, dest=dest).replace("Downloaded to", "\n[green]✓ Downloaded[/green]"))
    console.print()


def handle_gdrive_put(path: str, name: str = None):
    """Upload a local file to Drive."""
    if not Path(path).expanduser().is_file():
        console.print(f"\n❌ [bold red]File not found:[/bold red] {path}\n")
        raise typer.Exit(1)

    drive = _gdrive()
    uploaded = drive.upload(path, name=name)
    console.print(f"\n[green]✓ Uploaded[/green] [bold]{uploaded['name']}[/bold]")
    if uploaded["link"]:
        console.print(f"  {uploaded['link']}")
    console.print()


def handle_gdrive_rm(file_id: str):
    """Move a Drive file to the trash. Accepts the listing # or a full file id."""
    drive = _gdrive()
    resolved = _resolve_file_id(file_id)
    if not resolved:
        console.print(f"\n[yellow]No file #{file_id} in your last listing — run co gdrive, then co gdrive rm <#>.[/yellow]\n")
        raise typer.Exit(1)

    drive.delete(resolved)
    console.print("\n[green]✓ Moved to trash[/green] — restore it from drive.google.com if that was wrong\n")
