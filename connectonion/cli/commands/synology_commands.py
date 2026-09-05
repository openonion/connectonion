"""
Purpose: CLI surface for the user's Synology NAS — log in, browse, search, download, upload, and share File Station files from the terminal
LLM-Note:
  Dependencies: imports from [json, os, pathlib, typer, questionary, dotenv, rich.console, rich.table, ...useful_tools.synology] | imported by [cli/main.py via handle_syno_*()] | hits the NAS through the Synology tool
  Data flow: _syno() loads SYNOLOGY_* from .env / ~/.co/keys.env → Synology() instance | ls/search: list_files()/search_files() → numbered Rich table (tab-separated with full paths when piped) → saves {#: path} to ~/.co/syno_last_list.json | get/share: resolve short numbers via that cache → download()/share()
  State/Effects: login writes SYNOLOGY_URL/ACCOUNT/PASSWORD/SID to ~/.co/keys.env | writes ~/.co/syno_last_list.json (last listing's # → path map) | get downloads local files | put uploads to the NAS
  Integration: exposes handle_syno_login(), handle_syno_status(), handle_syno_list(), handle_syno_search(), handle_syno_get(), handle_syno_put(), handle_syno_share(), handle_syno_shares() for cli/main.py | presentation mirrors gdrive_commands.py | NAS logic lives in useful_tools/synology.py
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


def _syno(quiet: bool = False):
    """Load SYNOLOGY_* credentials from .env files and return a Synology instance. Exits 1 with a hint if not connected."""
    from dotenv import load_dotenv

    from ...project import project_root

    for env_path in [project_root() / ".env", Path.home() / ".co" / "keys.env"]:
        if env_path.is_file():
            load_dotenv(env_path)

    if not os.getenv("SYNOLOGY_URL"):
        if quiet:
            from ...useful_tools.synology import SynologyError
            raise SynologyError("Synology NAS not configured", code="not_configured")
        console.print("\n❌ [bold red]Synology NAS not connected[/bold red]")
        console.print("\n[cyan]Connect your NAS first:[/cyan]")
        console.print("  [bold]co syno login[/bold]     Log in with your QuickConnect ID")
        raise typer.Exit(1)

    from ...useful_tools.synology import Synology
    return Synology()


def _emit_json(command: str, data, next_command: str):
    """Write one stable JSON document for scripts and agents."""
    print(json.dumps({
        "schema_version": 1,
        "ok": True,
        "command": command,
        "data": data,
        "next_command": next_command,
    }, separators=(",", ":")))


def _fail_json(command: str, error: Exception, next_command: str):
    """Write a stable guarded-failure envelope, then exit 1."""
    code = getattr(error, "code", "network_error" if error.__class__.__module__.startswith("httpx") else "synology_error")
    print(json.dumps({
        "schema_version": 1,
        "ok": False,
        "command": command,
        "error": {"code": code, "message": str(error)},
        "next_command": next_command,
    }, separators=(",", ":")))
    raise typer.Exit(1)


def _fail_human(label: str, error: Exception, next_command: str):
    """Print one cause and one literal recovery command, then exit 1."""
    console.print(f"\n❌ [bold red]{label}:[/bold red] {error}")
    console.print(f"\n[dim]Next:[/dim] [bold]{next_command}[/bold]\n")
    raise typer.Exit(1)


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
        print("Download the first result with: co syno get 1")
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
    console.print("\n[dim]Download the first result:[/dim] [bold]co syno get 1[/bold]\n")


def _print_shares(links: list):
    """Render sharing links without changing NAS state."""
    if not console.is_terminal:
        for item in links:
            print(
                f"{item['id']}\t{item['path']}\t{item['expires']}\t"
                f"{item['status']}\t{item['url']}"
            )
        print("See all Synology commands: co syno --help")
        return

    table = Table(title="🔗 NAS — sharing links", show_header=True, header_style="bold cyan")
    table.add_column("Path", overflow="ellipsis")
    table.add_column("Expires")
    table.add_column("Status")
    table.add_column("URL", overflow="ellipsis")
    for item in links:
        table.add_row(item["path"], item["expires"] or "never", item["status"], item["url"])
    console.print()
    console.print(table)
    console.print("\n[dim]See all Synology commands:[/dim] [bold]co syno --help[/bold]\n")


def handle_syno_login(url: str = None):
    """Connect a Synology NAS, by QuickConnect ID or a direct URL, and save the session."""
    import questionary

    from ...useful_tools.synology import Synology, pick_reachable, resolve_quickconnect, save_credentials

    if url:
        base = url.rstrip("/")
    else:
        quickconnect_id = questionary.text("QuickConnect ID (Control Panel → External Access):").ask()
        if not quickconnect_id:
            console.print("\n[yellow]Login cancelled.[/yellow]")
            console.print("\n[dim]Start again:[/dim] [bold]co syno login[/bold]\n")
            raise typer.Exit(1)

        console.print("\n[dim]Resolving…[/dim]")
        try:
            candidates = resolve_quickconnect(quickconnect_id.strip())
            console.print(f"[dim]Found {len(candidates)} address(es), probing fastest first…[/dim]")
            base = pick_reachable(candidates)
        except Exception as error:
            _fail_human("Could not reach Synology NAS", error, "co syno login --url <https-url>")

    console.print(f"[green]✓[/green] Reached [bold]{base}[/bold]\n")

    account = questionary.text("DSM username:").ask()
    password = questionary.password("DSM password:").ask()
    if not account or not password:
        console.print("\n[yellow]Login cancelled.[/yellow]")
        console.print("\n[dim]Start again:[/dim] [bold]co syno login[/bold]\n")
        raise typer.Exit(1)

    # Logging in now both validates the credentials and caches the sid, so the
    # first real command doesn't fail on a typo made minutes earlier.
    try:
        nas = Synology(url=base, account=account, password=password)
        nas._login()
    except Exception as error:
        _fail_human("Synology login failed", error, "co syno login")
    save_credentials(url=base, account=account, password=password, sid=nas.sid)

    console.print(f"\n[green]✓ Connected[/green] as [bold]{account}[/bold]")
    console.print("\n[dim]Verify the connection:[/dim] [bold]co syno status[/bold]\n")


def handle_syno_status(json_output: bool = False):
    """Verify authenticated File Station access without changing NAS state."""
    command = "co syno status"
    try:
        status = _syno(quiet=json_output).status()
    except typer.Exit:
        raise
    except Exception as error:
        if json_output:
            _fail_json(command, error, "co syno login")
        console.print(f"\n❌ [bold red]Synology status failed:[/bold red] {error}")
        console.print("\n[dim]Reconnect with:[/dim] [bold]co syno login[/bold]\n")
        raise typer.Exit(1)

    if json_output:
        _emit_json(command, status, "co syno ls --json")
        return

    console.print(f"\n[green]✓ Connected[/green] as [bold]{status['account']}[/bold]")
    console.print(f"  {status['url']}")
    if not status["tls_verification"]:
        console.print("  [yellow]TLS certificate verification is disabled for this connection.[/yellow]")
    console.print("\n[dim]List files:[/dim] [bold]co syno ls[/bold]\n")


def handle_syno_list(path: str = None, last: int = 20, json_output: bool = False):
    """List shared folders, or the contents of one folder, as a numbered table."""
    command = "co syno ls"
    try:
        files = _syno(quiet=json_output).list_files(path=path, last=last)
    except typer.Exit:
        raise
    except Exception as error:
        if json_output:
            _fail_json(command, error, "co syno login")
        _fail_human("Could not list Synology files", error, "co syno status")
    if json_output:
        LIST_CACHE.parent.mkdir(parents=True, exist_ok=True)
        LIST_CACHE.write_text(json.dumps({str(i): f["path"] for i, f in enumerate(files, 1)}), encoding="utf-8")
        _emit_json(command, files, "co syno get 1" if files else "co syno ls <nas-folder>")
        return
    if not files:
        console.print(f"\n[cyan]Synology:[/cyan] nothing in {path or 'your shared folders'}\n")
        console.print("[dim]Choose another folder:[/dim] [bold]co syno ls <nas-folder>[/bold]\n")
        return
    _print_listing(files, f"📁 NAS — {path or 'shared folders'}")


def handle_syno_search(query: str, path: str = "/", last: int = 20, json_output: bool = False):
    """Search the NAS by file name, numbered like the listing."""
    command = "co syno search"
    try:
        files = _syno(quiet=json_output).search_files(query, path=path, last=last)
    except typer.Exit:
        raise
    except Exception as error:
        if json_output:
            _fail_json(command, error, "co syno login")
        _fail_human("Synology search failed", error, "co syno status")
    if json_output:
        LIST_CACHE.parent.mkdir(parents=True, exist_ok=True)
        LIST_CACHE.write_text(json.dumps({str(i): f["path"] for i, f in enumerate(files, 1)}), encoding="utf-8")
        _emit_json(command, files, "co syno get 1" if files else "co syno search <query>")
        return
    if not files:
        console.print(f"\n[cyan]NAS search:[/cyan] no files matching [bold]{query}[/bold]\n")
        console.print("[dim]Try another search:[/dim] [bold]co syno search <query>[/bold]\n")
        return
    _print_listing(files, f"🔎 NAS — {query}")


def _resolve_path(ref: str) -> str:
    """Turn a listing number into a NAS path; full paths pass through."""
    try:
        cached = json.loads(LIST_CACHE.read_text(encoding="utf-8")) if LIST_CACHE.exists() else {}
    except (OSError, ValueError):
        cached = {}
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
        console.print(f"\n[yellow]No file #{ref} in your last listing.[/yellow]")
        console.print("\n[dim]Refresh the listing:[/dim] [bold]co syno ls[/bold]\n")
        raise typer.Exit(1)

    console.print(f"\n[dim]Downloading {path}…[/dim]")
    try:
        result = nas.download(path, dest=dest)
    except Exception as error:
        _fail_human("Synology download failed", error, f"co syno get {ref} --to {dest}")
    console.print(result.replace("Downloaded to", "[green]✓ Downloaded[/green]"))
    console.print("\n[dim]List files again:[/dim] [bold]co syno ls[/bold]\n")


def handle_syno_put(local_path: str, path: str, overwrite: bool = False):
    """Upload a local file to a NAS folder."""
    if not Path(local_path).expanduser().is_file():
        console.print(f"\n❌ [bold red]File not found:[/bold red] {local_path}")
        console.print("\n[dim]Choose a local file:[/dim] [bold]co syno put <local-path> <nas-folder>[/bold]\n")
        raise typer.Exit(1)

    nas = _syno()
    try:
        result = nas.upload(local_path, path, overwrite=overwrite)
    except Exception as error:
        suffix = " --overwrite" if overwrite else ""
        _fail_human("Synology upload failed", error, f"co syno put {local_path} {path}{suffix}")
    console.print(f"\n[green]✓ {result}[/green]")
    console.print(f"\n[dim]Verify the upload:[/dim] [bold]co syno ls {path}[/bold]\n")


def handle_syno_share(ref: str):
    """Create a public sharing link. Accepts the listing # or a full path."""
    nas = _syno()
    path = _resolve_path(ref)
    if not path:
        console.print(f"\n[yellow]No file #{ref} in your last listing.[/yellow]")
        console.print("\n[dim]Refresh the listing:[/dim] [bold]co syno ls[/bold]\n")
        raise typer.Exit(1)

    try:
        url = nas.share(path)
    except Exception as error:
        _fail_human("Could not create Synology sharing link", error, "co syno shares")
    console.print(f"\n[green]✓ Sharing link[/green] for [bold]{path}[/bold]")
    console.print(f"  {url}")
    console.print("\n[dim]Review sharing links:[/dim] [bold]co syno shares[/bold]\n")


def handle_syno_shares(last: int = 20, json_output: bool = False):
    """List existing sharing links without creating or changing them."""
    command = "co syno shares"
    try:
        links = _syno(quiet=json_output).list_sharing_links(last=last)
    except typer.Exit:
        raise
    except Exception as error:
        if json_output:
            _fail_json(command, error, "co syno login")
        console.print(f"\n❌ [bold red]Could not list Synology sharing links:[/bold red] {error}")
        console.print("\n[dim]Reconnect with:[/dim] [bold]co syno login[/bold]\n")
        raise typer.Exit(1)

    if json_output:
        _emit_json(command, links, "co syno --help")
        return
    if not links:
        console.print("\n[cyan]Synology:[/cyan] no sharing links\n")
        console.print("[dim]See all Synology commands:[/dim] [bold]co syno --help[/bold]\n")
        return
    _print_shares(links)
