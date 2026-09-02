"""
Purpose: CLI surface for the user's Synology NAS — log in, browse, search, download, upload, and share File Station files from the terminal
LLM-Note:
  Dependencies: imports from [json, os, pathlib, typer, questionary, dotenv, rich.console, rich.table, ...useful_tools.synology] | imported by [cli/main.py via handle_syno_*()] | hits the NAS through the Synology tool
  Data flow: _syno() loads SYNOLOGY_* from .env / ~/.co/keys.env → Synology() instance | ls/search: list_files()/search_files() → numbered Rich table (tab-separated with full paths when piped) → saves {#: path} to ~/.co/syno_last_list.json | get/share: resolve short numbers via that cache → download()/share()
  State/Effects: login writes SYNOLOGY_URL/ACCOUNT/PASSWORD/SID to ~/.co/keys.env | writes ~/.co/syno_last_list.json (last listing's # → path map) | get downloads local files | put uploads to the NAS
  Integration: exposes handle_syno_login(), handle_syno_list(), handle_syno_search(), handle_syno_get(), handle_syno_put(), handle_syno_share() for cli/main.py | presentation mirrors gdrive_commands.py | NAS logic lives in useful_tools/synology.py
  Errors: guarded failures print a hint and exit 1 (typer.Exit) — not logged in, unresolvable file #, missing upload path | ValueError from the Synology tool carries decoded DSM error text
"""

import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()

LIST_CACHE = Path.home() / ".co" / "syno_last_list.json"


def _syno():
    """Load SYNOLOGY_* credentials from .env files and return a Synology instance. Exits 1 with a hint if not connected."""
    from dotenv import load_dotenv
    from ...project import project_root

    for env_path in [project_root() / ".env", Path.home() / ".co" / "keys.env"]:
        if env_path.is_file():
            load_dotenv(env_path)

    if not os.getenv("SYNOLOGY_URL"):
        console.print("\n❌ [bold red]Synology NAS not connected[/bold red]")
        console.print("\n[cyan]Connect your NAS first:[/cyan]")
        console.print("  [bold]co syno login[/bold]     Log in with your QuickConnect ID\n")
        raise typer.Exit(1)

    from ...useful_tools.synology import Synology
    return Synology()


def _size(count: int) -> str:
    """Render a byte count as B/KB/MB/GB; '-' for folders."""
    if not count:
        return "-"
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024


def _when(timestamp: int) -> str:
    """Render a File Station mtime (unix seconds) as 'Jul 26 14:30' in local time."""
    from datetime import datetime

    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%b %d %H:%M")


def _print_listing(files: list, title: str):
    """Render files as a numbered table (or tab-separated rows with full paths when piped) and cache the numbering."""
    LIST_CACHE.parent.mkdir(parents=True, exist_ok=True)
    LIST_CACHE.write_text(json.dumps({str(i): f["path"] for i, f in enumerate(files, 1)}), encoding="utf-8")

    if not console.is_terminal:
        # Scripts and agents get full paths, never a truncated column. Plain
        # print, not console.print: Rich expands \t into spaces, which silently
        # turns tab-separated output into something cut -f can't read.
        for item in files:
            print(f"{item['name']}\t{item['type']}\t{item['size']}\t{item['path']}")
        return

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("Name", overflow="ellipsis", no_wrap=True)
    table.add_column("Kind", max_width=6, no_wrap=True)
    table.add_column("Size", justify="right")
    table.add_column("Modified")

    for i, item in enumerate(files, 1):
        table.add_row(str(i), item["name"], item["type"], _size(item["size"]), _when(item["modified"]))

    console.print()
    console.print(table)
    console.print("\n[dim]Download one with:[/dim] [bold]co syno get <#>[/bold]\n")


def handle_syno_login(url: str = None):
    """Connect a Synology NAS, by QuickConnect ID or a direct URL, and save the session."""
    import questionary

    from ...useful_tools.synology import Synology, pick_reachable, resolve_quickconnect, save_credentials

    if url:
        base = url.rstrip("/")
    else:
        quickconnect_id = questionary.text("QuickConnect ID (Control Panel → External Access):").ask()
        if not quickconnect_id:
            raise typer.Exit(1)

        console.print("\n[dim]Resolving…[/dim]")
        candidates = resolve_quickconnect(quickconnect_id.strip())
        console.print(f"[dim]Found {len(candidates)} address(es), probing fastest first…[/dim]")
        base = pick_reachable(candidates)

    console.print(f"[green]✓[/green] Reached [bold]{base}[/bold]\n")

    account = questionary.text("DSM username:").ask()
    password = questionary.password("DSM password:").ask()
    if not account or not password:
        raise typer.Exit(1)

    save_credentials(url=base, account=account, password=password)

    # Logging in now both validates the credentials and caches the sid, so the
    # first real command doesn't fail on a typo made minutes earlier.
    Synology(url=base, account=account, password=password)._login()

    console.print(f"\n[green]✓ Connected[/green] as [bold]{account}[/bold]")
    console.print("\n[dim]Try:[/dim] [bold]co syno[/bold]\n")


def handle_syno_list(path: str = None, last: int = 20):
    """List shared folders, or the contents of one folder, as a numbered table."""
    nas = _syno()
    files = nas.list_files(path=path, last=last)
    if not files:
        console.print(f"\n[cyan]Synology:[/cyan] nothing in {path or 'your shared folders'}\n")
        return
    _print_listing(files, f"📁 NAS — {path or 'shared folders'}")


def handle_syno_search(query: str, path: str = "/", last: int = 20):
    """Search the NAS by file name, numbered like the listing."""
    nas = _syno()
    files = nas.search_files(query, path=path, last=last)
    if not files:
        console.print(f"\n[cyan]NAS search:[/cyan] no files matching [bold]{query}[/bold]\n")
        return
    _print_listing(files, f"🔎 NAS — {query}")


def _resolve_path(ref: str) -> str:
    """Turn a listing number into a NAS path; full paths pass through."""
    cached = json.loads(LIST_CACHE.read_text(encoding="utf-8")) if LIST_CACHE.exists() else {}
    if ref in cached:
        return cached[ref]

    if ref.isascii() and ref.isdigit() and len(ref) < 5:
        # A short number means "row N of what you just showed me" — refetching a
        # differently ordered listing would silently act on the wrong file.
        return ""
    return ref


def handle_syno_get(ref: str, dest: str = "."):
    """Download a file from the NAS. Accepts the listing # or a full path."""
    nas = _syno()
    path = _resolve_path(ref)
    if not path:
        console.print(f"\n[yellow]No file #{ref} in your last listing — run co syno to refresh.[/yellow]\n")
        raise typer.Exit(1)

    console.print(f"\n[dim]Downloading {path}…[/dim]")
    console.print(nas.download(path, dest=dest).replace("Downloaded to", "[green]✓ Downloaded[/green]"))
    console.print()


def handle_syno_put(local_path: str, path: str, overwrite: bool = False):
    """Upload a local file to a NAS folder."""
    if not Path(local_path).expanduser().is_file():
        console.print(f"\n❌ [bold red]File not found:[/bold red] {local_path}\n")
        raise typer.Exit(1)

    nas = _syno()
    console.print(f"\n[green]✓ {nas.upload(local_path, path, overwrite=overwrite)}[/green]\n")


def handle_syno_share(ref: str):
    """Create a public sharing link. Accepts the listing # or a full path."""
    nas = _syno()
    path = _resolve_path(ref)
    if not path:
        console.print(f"\n[yellow]No file #{ref} in your last listing — run co syno to refresh.[/yellow]\n")
        raise typer.Exit(1)

    console.print(f"\n[green]✓ Sharing link[/green] for [bold]{path}[/bold]")
    console.print(f"  {nas.share(path)}\n")
