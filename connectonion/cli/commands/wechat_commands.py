"""
Purpose: `co wechat` — read the owner's own WeChat for Mac history locally, read-only (#3146)
LLM-Note:
  Dependencies: imports from [os, re, platform, pathlib, typer, rich.console, ...useful_tools.wechat] | imported by [cli/main.py via wechat_app] | decryption engine (SQLCipher 4, cryptography — no new package) in useful_tools/wechat.py
  Data flow: doctor → inspects the WeChat container path + whether WECHAT_DB_KEY is set → report | key set → validates x'<hex>' → writes WECHAT_DB_KEY to ~/.co/keys.env (0600) | key (no args) → prints the consented manual procedure | chats → decrypt each db in memory, list tables+counts | decrypt → write plaintext .db copies | export → one table → JSON/Markdown
  State/Effects: read-only except `key set` (upserts one line in ~/.co/keys.env) and `decrypt` (writes plaintext SQLite copies to --out) | the container probe runs in a timed daemon thread so a TCC prompt cannot hang a non-interactive run | never writes to WeChat's files or network
  Integration: exposes wechat_app for cli/main.py (`app.add_typer(wechat_app, name="wechat")`) | design + staged plan in docs/wechat-read.md | relates to #1215 (live read/send); REM admission of the export is the next step
  Errors: macOS-only — exit 2 off macOS | exit 2 when a read command lacks container access or the key, each with the exact next step | WrongKeyError per database is reported and skipped | `key set` exit 2 on a malformed key
"""

import os
import re
import platform
from pathlib import Path

import typer
from rich.console import Console

console = Console()

# WeChat 4.x for Mac. db_storage holds the SQLCipher databases. See docs/wechat-read.md.
WECHAT_CONTAINER = (
    Path.home()
    / "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
)
KEYS_ENV = Path.home() / ".co" / "keys.env"
KEY_NAME = "WECHAT_DB_KEY"
# SQLCipher 4 raw key: x'<64 hex chars>' (a 32-byte AES-256 key).
RAW_KEY_RE = re.compile(r"^x'[0-9a-fA-F]{64}'$")

DOCS = "docs/wechat-read.md"

wechat_app = typer.Typer(
    help="Read your own WeChat for Mac history locally (read-only). macOS only. See " + DOCS + ".",
    no_args_is_help=True,
    epilog="Example:  co wechat doctor  |  co wechat key set x'0f1e...'  |  co wechat chats  |  co wechat export --db message_0.db --table Msg",
)


def _require_macos() -> None:
    """`co wechat` reads WeChat for Mac's local databases; it is macOS-only."""
    if platform.system() != "Darwin":
        console.print("[bold red]co wechat is macOS-only[/bold red] — it reads WeChat for Mac's local databases.")
        raise typer.Exit(2)


def _read_key() -> str | None:
    """Return the saved WECHAT_DB_KEY from the environment or ~/.co/keys.env, or None."""
    value = os.getenv(KEY_NAME)
    if value:
        return value.strip() or None
    if KEYS_ENV.exists():
        for line in KEYS_ENV.read_text().splitlines():
            name, sep, rest = line.partition("=")
            if sep and name.strip() == KEY_NAME:
                value = rest.strip()
                # Strip one pair of surrounding double-quotes only; the single
                # quotes in x'<hex>' are part of the SQLCipher key literal.
                if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                    value = value[1:-1]
                return value or None
    return None


def _write_key(value: str) -> None:
    """Upsert WECHAT_DB_KEY in ~/.co/keys.env, replacing any existing line, at mode 0600."""
    KEYS_ENV.parent.mkdir(parents=True, exist_ok=True)
    lines = KEYS_ENV.read_text().splitlines() if KEYS_ENV.exists() else []
    kept = [ln for ln in lines if ln.partition("=")[0].strip() != KEY_NAME]
    kept.append(f"{KEY_NAME}={value}")
    KEYS_ENV.write_text("\n".join(kept) + "\n")
    os.chmod(KEYS_ENV, 0o600)


def _probe_container() -> tuple[str, Path | None]:
    """Look for a db_storage under the WeChat container. May block on a TCC prompt."""
    try:
        if not WECHAT_CONTAINER.exists():
            return "missing", None
        for account in sorted(WECHAT_CONTAINER.iterdir()):
            if (account / "db_storage").is_dir():
                return "ok", account
        return "missing", None
    except PermissionError:
        return "blocked", None


def _container_status(timeout: float = 3.0) -> tuple[str, Path | None]:
    """Report access to the WeChat container without hanging on a TCC prompt.

    Returns (status, account_dir). status is one of: "missing" (WeChat not
    installed / no data here), "blocked" (macOS has not granted access, or the
    probe did not return in time — grant Full Disk Access), "ok" (a db_storage
    was found). The filesystem probe runs in a daemon thread so that a pending
    macOS privacy prompt cannot hang a non-interactive run.
    """
    import threading

    result: list[tuple[str, Path | None]] = []
    worker = threading.Thread(target=lambda: result.append(_probe_container()), daemon=True)
    worker.start()
    worker.join(timeout)
    return result[0] if result else ("blocked", None)


@wechat_app.command("doctor", epilog="Example:  co wechat doctor")
def doctor():
    """Check the prerequisites for reading WeChat history: macOS, the container, and whether a key is saved. Read-only; exits 2 if anything blocks a read."""
    _require_macos()
    console.print("[bold]co wechat doctor[/bold]\n")

    status, account = _container_status()
    if status == "ok":
        console.print(f"[green]OK[/green]  WeChat data found: {account}")
    elif status == "blocked":
        console.print("[yellow]BLOCKED[/yellow]  macOS denied access to WeChat's container.")
        console.print("        Grant your terminal Full Disk Access:")
        console.print("        System Settings -> Privacy & Security -> Full Disk Access -> add your terminal, then reopen it.")
    else:
        console.print(f"[yellow]MISSING[/yellow]  No WeChat data under {WECHAT_CONTAINER}")
        console.print("        Open WeChat for Mac and sign in, then migrate the history you want from your phone")
        console.print("        (WeChat on phone -> Settings -> General -> Chat Log Migration & Backup -> Migrate to a computer).")

    key = _read_key()
    console.print(f"\n{'[green]OK[/green]' if key else '[yellow]MISSING[/yellow]'}  database key ({KEY_NAME}) {'is saved' if key else 'is not set'}.")
    if not key:
        console.print(f"        Obtain it as a consented local step, then save it:  co wechat key --help")

    if status == "ok" and key:
        console.print("\nReady. Next:  co wechat chats  (then  co wechat decrypt  or  co wechat export)")
    else:
        console.print(f"\nOnce both are green:  co wechat chats. Design and plan: {DOCS}")
    raise typer.Exit(0 if (status == "ok" and key) else 2)


key_app = typer.Typer(
    help="The WeChat database key: how to obtain it (a consented local step), and how to save one you have.",
    no_args_is_help=False,
    invoke_without_command=True,
)


@key_app.callback(invoke_without_command=True)
def key_help(ctx: typer.Context):
    """With no subcommand, explain how to obtain the key. `co wechat key set x'<hex>'` saves one."""
    if ctx.invoked_subcommand is not None:
        return
    _require_macos()
    console.print(
        "\n".join([
            "[bold]Obtaining the WeChat database key[/bold] — a consented, local, one-time step.",
            "",
            "The key is not on disk; it lives only in the running WeChat process. On WeChat 4.1.x it",
            "no longer sits in memory, so it is captured the moment a database is opened, using Apple's",
            "own debugger against a RE-SIGNED COPY of WeChat (never the real /Applications/WeChat.app).",
            "This uses only OS tools (codesign, lldb, python3) — no package is installed.",
            "",
            "co wechat does not do this for you. Follow one of the open-source references in the design",
            f"doc ({DOCS}), on your own account, then save the key you get:",
            "",
            "    co wechat key set x'<64 hex characters>'",
            "",
            "SIP does not need to be disabled. Reading the container needs Full Disk Access (see: co wechat doctor).",
        ])
    )


@key_app.command("set", epilog="Example:  co wechat key set x'0f1e2d3c...'  (64 hex chars)")
def key_set(
    key: str = typer.Argument(..., help="The SQLCipher raw key as x'<64 hex chars>', obtained per co wechat key --help"),
):
    """Save a WeChat database key you obtained into ~/.co/keys.env (owner-only). Validates the x'<hex>' form."""
    _require_macos()
    if not RAW_KEY_RE.match(key.strip()):
        console.print("[bold red]Not a valid key.[/bold red] Expected a SQLCipher raw key: x'<64 hex characters>'.")
        console.print("See how to obtain it:  co wechat key --help")
        raise typer.Exit(2)
    _write_key(key.strip())
    console.print(f"[green]Saved[/green] {KEY_NAME} to {KEYS_ENV} (0600). Check readiness:  co wechat doctor")


wechat_app.add_typer(key_app, name="key")


def _ready() -> tuple[Path, str]:
    """Return (db_storage, key) once macOS, container access and the key are all in place; else exit 2."""
    _require_macos()
    status, account = _container_status()
    if status != "ok":
        console.print("[yellow]WeChat data is not accessible yet.[/yellow] Run:  co wechat doctor")
        raise typer.Exit(2)
    key = _read_key()
    if not key:
        console.print(f"[yellow]No database key saved.[/yellow] Obtain it (co wechat key --help), then: co wechat key set x'<hex>'")
        raise typer.Exit(2)
    return account / "db_storage", key


@wechat_app.command("chats", epilog="Example:  co wechat chats")
def chats():
    """Show each local WeChat database and its tables with row counts (schema discovery). Decrypts in memory; nothing is written."""
    from ...useful_tools import wechat as engine

    db_storage, key = _ready()
    dbs = engine.message_dbs(db_storage)
    if not dbs:
        console.print(f"No .db files under {db_storage}")
        raise typer.Exit(2)
    for path in dbs:
        try:
            conn = engine.open_readonly(engine.decrypt_db(path, key))
        except engine.WrongKeyError:
            console.print(f"[yellow]{path.name}[/yellow]: key did not decrypt it (re-check: co wechat key)")
            continue
        listing = ", ".join(f"{name}({rows})" for name, rows in engine.tables(conn)) or "(no tables)"
        console.print(f"[bold]{path.name}[/bold]: {listing}")


@wechat_app.command("decrypt", epilog="Example:  co wechat decrypt --out ~/wechat-plain")
def decrypt(
    out: Path = typer.Option(Path("wechat-plain"), "--out", help="Directory to write plaintext SQLite copies into"),
):
    """Decrypt every local WeChat database to plaintext SQLite files you can open with any sqlite tool. Local only."""
    from ...useful_tools import wechat as engine

    db_storage, key = _ready()
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in engine.message_dbs(db_storage):
        try:
            plaintext = engine.decrypt_db(path, key)
        except engine.WrongKeyError:
            console.print(f"[yellow]skip[/yellow] {path.name}: key did not decrypt it")
            continue
        target = out / path.name
        target.write_bytes(plaintext)
        written += 1
        console.print(f"[green]wrote[/green] {target} ({len(plaintext) // 1024} KB)")
    console.print(f"\n{written} database(s) decrypted to {out}. These are plaintext — keep them local.")
    raise typer.Exit(0 if written else 2)


@wechat_app.command("export", epilog='Example:  co wechat export --db message_0.db --table Msg --format json --out msg.json')
def export(
    db: str = typer.Option(..., "--db", help="A database file name, as shown by: co wechat chats"),
    table: str = typer.Option(..., "--table", help="A table in that database, as shown by: co wechat chats"),
    fmt: str = typer.Option("json", "--format", help="json or md"),
    out: Path = typer.Option(None, "--out", help="Write here instead of stdout"),
):
    """Export one table from a local WeChat database as JSON or Markdown. Schema-agnostic; decrypts in memory."""
    import json
    from ...useful_tools import wechat as engine

    db_storage, key = _ready()
    matches = [p for p in engine.message_dbs(db_storage) if p.name == db]
    if not matches:
        console.print(f"[yellow]No database named {db}.[/yellow] List them:  co wechat chats")
        raise typer.Exit(2)
    try:
        conn = engine.open_readonly(engine.decrypt_db(matches[0], key))
    except engine.WrongKeyError:
        console.print(f"[yellow]{db}[/yellow]: key did not decrypt it (re-check: co wechat key)")
        raise typer.Exit(2)
    try:
        cursor = conn.execute(f'SELECT * FROM "{table}"')
    except Exception:
        console.print(f"[yellow]No table {table} in {db}.[/yellow] List them:  co wechat chats")
        raise typer.Exit(2)
    cols = [c[0] for c in cursor.description]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    if fmt == "md":
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
        lines += ["| " + " | ".join(str(row[c]).replace("|", "\\|") for c in cols) + " |" for row in rows]
        text = "\n".join(lines) + "\n"
    else:
        text = json.dumps(rows, ensure_ascii=False, indent=2)
    if out:
        out.write_text(text)
        console.print(f"[green]wrote[/green] {len(rows)} rows to {out}")
    else:
        console.print(text)
