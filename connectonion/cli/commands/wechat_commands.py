"""
Purpose: `co wechat` — read the owner's own WeChat for Mac history locally, read-only (#3146)
LLM-Note:
  Dependencies: imports from [os, re, platform, pathlib, typer, rich.console, ...useful_tools.wechat] | imported by [cli/main.py via wechat_app] | decryption engine (SQLCipher 4, cryptography — no new package) in useful_tools/wechat.py
  Data flow: co wechat (bare) → first run sets up what is missing (Full Disk Access, keys via `key capture`) → numbered recent chats | read N|name → one chat's messages | search WORDS | key capture → one consent, a re-signed copy under lldb captures each database's key by salt → ~/.co/wechat/keys.json (0600) | tables → each db's tables + counts | decrypt / export → raw copies
  State/Effects: read-only except `key set` (upserts one line in ~/.co/keys.env) and `decrypt` (writes plaintext SQLite copies to --out) | the container probe runs in a timed daemon thread so a TCC prompt cannot hang a non-interactive run | never writes to WeChat's files or network
  Integration: cli/main.py registers wechat_app under the name "wechat" | design + staged plan in docs/wechat-read.md | relates to #1215 (live read/send); REM admission of the export is the next step
  Errors: macOS-only — exit 2 off macOS | exit 2 when a read command lacks container access or the key, each with the exact next step | WrongKeyError per database is reported and skipped | `key set` exit 2 on a malformed key
"""

import os
import re
import platform
from pathlib import Path

import typer
from rich.console import Console

from ..typer_groups import _OneSuggestion

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
    cls=_OneSuggestion,
    help="Read your own WeChat for Mac chats on this Mac (read-only). Run co wechat on its own: the first time it "
         "sets up what is missing, then it lists your recent chats. macOS only. Nothing is sent.",
    no_args_is_help=False,
    invoke_without_command=True,
    epilog="Example:  co wechat  |  co wechat read 1  |  co wechat search 合同",
)
KEY_DIR = Path.home() / ".co" / "wechat"
KEY_MAP = KEY_DIR / "keys.json"        # {database salt hex: raw key hex}; WeChat 4.1 has one key per database
LISTING = KEY_DIR / "last-list.json"   # the numbers of the last chat list, for `co wechat read 2`
LISTING_MINUTES = 15
WECHAT_APP = Path("/Applications/WeChat.app")
DEBUG_COPY = KEY_DIR / "WeChat-debug.app"
FDA_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"


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
        # Several accounts can live here; the one in use is the one whose chat list WeChat wrote last.
        accounts = [a for a in WECHAT_CONTAINER.iterdir() if (a / "db_storage").is_dir()]
        if not accounts:
            return "missing", None
        latest = lambda a: max((p.stat().st_mtime for p in (a / "db_storage" / "session").glob("session.db*")), default=0)
        return "ok", max(accounts, key=latest)
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
    """Check whether WeChat chats can be read: macOS, access to the WeChat data folder, and saved keys. Read-only; exits 2 if something is missing."""
    _require_macos()
    console.print("[bold]co wechat doctor[/bold]\n")

    status, account = _container_status()
    if status == "ok":
        console.print(f"[green]OK[/green]  WeChat data found: {account}")
    elif status == "blocked":
        console.print("[yellow]BLOCKED[/yellow]  macOS denied access to WeChat's container.")
        console.print(f"        Turn on Full Disk Access for {_terminal_app()}:")
        console.print("        System Settings -> Privacy & Security -> Full Disk Access (co wechat opens it for you).")
    else:
        console.print(f"[yellow]MISSING[/yellow]  No WeChat data under {WECHAT_CONTAINER}")
        console.print("        Open WeChat for Mac and sign in, then migrate the history you want from your phone")
        console.print("        (WeChat on phone -> Settings -> General -> Chat Log Migration & Backup -> Migrate to a computer).")

    keys = len(_key_map())
    key = keys or _read_key()
    console.print(f"\n{'[green]OK[/green]' if key else '[yellow]MISSING[/yellow]'}  database keys: "
                  + (f"{keys} saved" if keys else ("one key saved with key set" if key else "none yet")) + ".")
    if not key:
        console.print("        Get them after one question:  co wechat key capture")

    if status == "ok" and key:
        console.print("\nReady. Next:  co wechat")
    else:
        console.print("\nNext: co wechat  (it sets up what is missing)")
    raise typer.Exit(0 if (status == "ok" and key) else 2)


key_app = typer.Typer(
    cls=_OneSuggestion,
    help="WeChat database keys. Read-only unless you run capture or set: capture gets them after one question; set saves one you already have.",
    no_args_is_help=False,
    invoke_without_command=True,
    epilog="Example:  co wechat key capture  |  co wechat key",
)


@key_app.callback(invoke_without_command=True)
def key_help(ctx: typer.Context):
    """With no subcommand, say how keys are obtained. Read-only. `co wechat key capture` gets them for you."""
    if ctx.invoked_subcommand is not None:
        return
    _require_macos()
    count = len(_key_map())
    console.print(
        "\n".join([
            f"[bold]WeChat database keys[/bold]: {count} saved in {KEY_MAP}" if count else "[bold]WeChat database keys[/bold]: none saved yet.",
            "",
            "WeChat 4.1 encrypts each database with its own key, which exists only while WeChat opens it.",
            "co wechat key capture gets them for you, after one question: it quits WeChat, opens a re-signed copy",
            "under Apple's debugger (lldb) while the copy opens your chats, saves each key by its database's salt,",
            "and reopens the real WeChat, which is never changed. Only macOS tools are used; nothing is installed.",
            "",
            "Next: co wechat key capture   (or just: co wechat, which asks the first time)",
        ])
    )


@key_app.command("capture", epilog="Example:  co wechat key capture  |  co wechat key capture --yes")
def key_capture(yes: bool = typer.Option(False, "--yes", help="Skip the question; for a script you started yourself")):
    """Writes the key of every WeChat database on this Mac to ~/.co/wechat/keys.json (0600), after one question. Quits and reopens WeChat."""
    _require_macos()
    status, account = _container_status()
    if status == "blocked":
        account = _wait_for_access()
    if account is None:
        console.print("[yellow]WeChat data is not accessible.[/yellow] Run:  co wechat doctor")
        raise typer.Exit(2)
    if not yes and not typer.confirm("This quits WeChat, opens a re-signed copy under Apple's debugger while it opens your chats, "
                                     "saves the keys on this Mac, then reopens WeChat. Continue?", default=True):
        raise typer.Exit(1)
    from ...useful_tools import wechat as engine
    total = len(engine.message_dbs(account / "db_storage"))
    done = capture_keys(account / "db_storage")
    console.print(f"[green]Saved keys for {done} of {total} databases[/green] in {KEY_MAP}.")
    # The copy took WeChat's one Mac session, so the real app asks to log in once more; reading never does.
    console.print("WeChat has reopened: log in one last time. After this, co wechat only reads files on this Mac.")
    console.print("Next: co wechat")
    raise typer.Exit(0 if done else 1)


@key_app.command("set", epilog="Example:  co wechat key set \"x'0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0'\"")
def key_set(
    key: str = typer.Argument(..., help="The SQLCipher raw key as x'<64 hex chars>', obtained per co wechat key --help"),
):
    """Writes one database key you already have into ~/.co/keys.env (owner-only). Most people want: co wechat key capture."""
    _require_macos()
    if not RAW_KEY_RE.match(key.strip()):
        console.print("[bold red]Not a valid key.[/bold red] Expected a SQLCipher raw key: x'<64 hex characters>'.")
        console.print("See how to obtain it:  co wechat key --help")
        raise typer.Exit(2)
    _write_key(key.strip())
    console.print(f"[green]Saved[/green] {KEY_NAME} to {KEYS_ENV} (0600). Check readiness:  co wechat doctor")


wechat_app.add_typer(key_app, name="key")


def _key_map() -> dict:
    """{database salt hex: raw key hex}, from `co wechat key capture`."""
    import json
    return json.loads(KEY_MAP.read_text()) if KEY_MAP.is_file() else {}


def _save_key_map(keys: dict) -> None:
    import json
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(KEY_DIR, 0o700)
    KEY_MAP.write_text(json.dumps(keys, indent=1))
    os.chmod(KEY_MAP, 0o600)


def _key_for(path: Path) -> str | None:
    """The key for one database: its own, found by salt, else the single key saved with `key set`."""
    from ...useful_tools import wechat as engine
    return _key_map().get(engine.db_salt(path)) or _read_key()


def _open(path: Path):
    """An in-memory read-only connection to one database; None when no key opens it."""
    import sqlite3
    from ...useful_tools import wechat as engine
    key = _key_for(path)
    if not key:
        return None
    try:
        return engine.open_readonly(engine.decrypt_db(path, key))
    except (engine.WrongKeyError, sqlite3.DatabaseError):
        return None


def _ready() -> Path:
    """db_storage once macOS and container access are in place; else exit 2 with the next step."""
    _require_macos()
    status, account = _container_status()
    if status != "ok":
        console.print("[yellow]WeChat data is not accessible yet.[/yellow] Run:  co wechat")
        raise typer.Exit(2)
    return account / "db_storage"


def _terminal_app() -> str:
    """The app macOS asks Full Disk Access for: the terminal this command runs in (tmux included)."""
    import subprocess
    names, pid = [], os.getpid()
    for _ in range(12):
        line = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        if not line:
            break
        ppid, _, comm = line.partition(" ")
        names.append(comm.strip())
        pid = int(ppid)
        if pid <= 1:
            break
    for app in ("Ghostty", "iTerm", "Terminal", "WezTerm", "Warp", "kitty", "Alacritty", "Code", "Cursor"):
        if any(app.lower() in name.lower() for name in names):
            extra = " and /opt/homebrew/bin/tmux" if os.environ.get("TMUX") else ""
            return app + extra
    return "your terminal app" + (" and /opt/homebrew/bin/tmux" if os.environ.get("TMUX") else "")


def _wait_for_access(wait_seconds: int = 300) -> Path | None:
    """Open the Full Disk Access pane, name the app to add, and continue by itself once access is granted."""
    import subprocess
    import time
    console.print(f"macOS needs Full Disk Access for [bold]{_terminal_app()}[/bold] so co wechat can read WeChat's files.")
    console.print("Opening System Settings → Privacy & Security → Full Disk Access. Turn it on there; this waits and continues by itself.")
    subprocess.run(["open", FDA_PANE], check=False)
    for _ in range(wait_seconds // 3):
        time.sleep(3)
        status, account = _container_status()
        if status == "ok":
            console.print("[green]Access granted.[/green]")
            return account
    return None


HOOK = r"""
import os, lldb
OUT = os.environ.get("CO_WECHAT_CAPTURE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "captured.txt")

def _read(proc, ptr, length):
    err = lldb.SBError()
    data = proc.ReadMemory(ptr, length, err) if ptr and 0 < length <= 64 else None
    return data.hex() if data and err.Success() else None

def pbkdf_bp(frame, bp_loc, internal_dict):
    # CCKeyDerivationPBKDF(alg, password, passwordLen, salt, saltLen, prf, rounds, derivedKey, derivedKeyLen).
    # With rounds == 2, SQLCipher derives the HMAC key from the database's raw key and salt ^ 0x3a.
    reg = lambda n: frame.FindRegister(n).GetValueAsUnsigned()
    proc = frame.GetThread().GetProcess()
    if reg("x6") == 2 and reg("x2") == 32 and reg("x4") == 16:
        key, salt = _read(proc, reg("x1"), 32), _read(proc, reg("x3"), 16)
        if key and salt:
            fd = os.open(OUT, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as handle:
                handle.write(salt + " " + key + "\n")
    return False
"""

ENTITLEMENTS = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>com.apple.security.get-task-allow</key><true/></dict></plist>
"""


def _app_version(app: Path) -> str:
    import plistlib
    return plistlib.loads((app / "Contents" / "Info.plist").read_bytes()).get("CFBundleVersion", "")


def _debug_copy(work: Path) -> Path:
    """A re-signed copy of WeChat that Apple's debugger may attach to. The real app is never touched."""
    import shutil
    import subprocess
    if DEBUG_COPY.is_dir() and _app_version(DEBUG_COPY) == _app_version(WECHAT_APP):
        return DEBUG_COPY
    console.print("Making a re-signed copy of WeChat (about 1.4 GB, once per WeChat version)…")
    if DEBUG_COPY.exists():
        shutil.rmtree(DEBUG_COPY)
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-R", str(WECHAT_APP), str(DEBUG_COPY)], check=True)
    entitlements = work / "debug.entitlements"
    entitlements.write_text(ENTITLEMENTS)
    subprocess.run(["codesign", "--force", "--sign", "-", "--entitlements", str(entitlements), str(DEBUG_COPY)],
                   check=True, capture_output=True)
    return DEBUG_COPY


def _quit_wechat() -> None:
    import subprocess
    import time
    subprocess.run(["osascript", "-e", 'quit app "WeChat"'], check=False, capture_output=True)
    time.sleep(3)
    subprocess.run(["pkill", "-x", "WeChat"], check=False)
    time.sleep(1)


def capture_keys(db_storage: Path, wait_seconds: int = 600) -> int:
    """Quit WeChat, open the re-signed copy under lldb, record each database's key by salt, restore WeChat.

    Returns how many of this account's databases now have a key. Only OS tools: codesign, lldb, python3.
    """
    import subprocess
    import tempfile
    import time
    from ...useful_tools import wechat as engine
    salts = {engine.db_salt(p) for p in engine.message_dbs(db_storage)}
    work = Path(tempfile.mkdtemp(prefix="co-wechat-"))
    os.chmod(work, 0o700)
    capture = work / "captured.txt"
    (work / "hook.py").write_text(HOOK)
    (work / "lldb.cmds").write_text(
        f"command script import {work / 'hook.py'}\nbreak set -n CCKeyDerivationPBKDF\n"
        "break command add -F hook.pbkdf_bp\ncontinue\n")
    app = _debug_copy(work)
    _quit_wechat()
    # The debugger's own output (never the keys) goes to capture.log, so a run that finds nothing can say why.
    log = open(KEY_DIR / "capture.log", "w")
    lldb = subprocess.Popen(["lldb", "-b", "-o", "process attach --name WeChat --waitfor", "-s", str(work / "lldb.cmds")],
                            stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "CO_WECHAT_CAPTURE": str(capture)})
    keys = _key_map()
    try:
        time.sleep(3)
        subprocess.run(["open", str(app)], check=True)
        console.print("[bold]Log in on the WeChat window that just opened[/bold] (scan the code, or confirm on your phone): "
                      "each database's key appears the moment it opens your chats. If macOS asks whether "
                      "\"WeChat-debug\" may access data from other apps, allow it.")
        found = set()
        for _ in range(wait_seconds // 3):
            time.sleep(3)
            for line in capture.read_text().splitlines() if capture.is_file() else []:
                salt, _, key = line.partition(" ")
                db = bytes(b ^ 0x3A for b in bytes.fromhex(salt)).hex()
                if db in salts:
                    keys[db] = "x'" + key + "'"
                    found.add(db)
            console.print(f"\r  {len(found)} of {len(salts)} databases", end="")
            if found >= salts:
                break
        console.print()
    finally:
        lldb.terminate()
        lldb.wait(timeout=10)
        log.close()
        subprocess.run(["pkill", "-f", str(app / "Contents" / "MacOS" / "WeChat")], check=False)
        time.sleep(2)
        subprocess.run(["open", str(WECHAT_APP)], check=False)
        for leftover in work.iterdir():
            leftover.unlink()
        work.rmdir()
    _save_key_map(keys)
    if not found:
        console.print("[yellow]No keys appeared.[/yellow] The copy has to log in for WeChat to open its databases. "
                      "Run co wechat key capture again and log in on the window it opens.")
    return len(salts & set(keys))


def _setup(interactive: bool) -> Path:
    """Fix what is missing before reading: access, then keys. Returns db_storage."""
    _require_macos()
    status, account = _container_status()
    if status == "missing":
        console.print(f"[yellow]No WeChat data on this Mac.[/yellow] Open WeChat for Mac and sign in, then run co wechat again.")
        raise typer.Exit(2)
    if status == "blocked":
        account = _wait_for_access() if interactive else None
        if account is None:
            console.print(f"[yellow]Full Disk Access is still off for {_terminal_app()}.[/yellow] Turn it on, then: co wechat")
            raise typer.Exit(2)
    db_storage = account / "db_storage"
    session_db = db_storage / "session" / "session.db"
    if session_db.is_file() and not _open(session_db):
        if not interactive:
            console.print("[yellow]No key for your chats yet.[/yellow] Run:  co wechat key capture")
            raise typer.Exit(2)
        console.print("WeChat keeps a separate key for each database. To read them, co wechat will quit WeChat, open a "
                      "re-signed copy under Apple's debugger while it opens your chats, and save the keys on this Mac (0600). "
                      "The real WeChat app is not changed, and it reopens at the end.")
        if not typer.confirm("Continue?", default=True):
            raise typer.Exit(1)
        done = capture_keys(db_storage)
        console.print(f"[green]Saved keys for {done} databases.[/green] WeChat has reopened: log in one last time.")
    return db_storage


def _clock(seconds) -> str:
    from datetime import datetime
    if not seconds:
        return ""
    moment = datetime.fromtimestamp(int(seconds))
    return moment.strftime("%H:%M") if moment.date() == datetime.now().date() else moment.strftime("%m-%d")


def _contacts(db_storage: Path) -> dict:
    from ...useful_tools import wechat as engine
    conn = _open(db_storage / "contact" / "contact.db")
    return engine.names(conn) if conn else {}


@wechat_app.callback(invoke_without_command=True)
def recent(ctx: typer.Context, limit: int = typer.Option(20, "--limit", help="How many chats to list")):
    """Your recent WeChat chats, numbered, newest first. The first run sets up access and keys. Read-only."""
    if ctx.invoked_subcommand is not None:
        return
    import json
    import sys
    import time
    from ...useful_tools import wechat as engine
    db_storage = _setup(interactive=sys.stdin.isatty())
    conn = _open(db_storage / "session" / "session.db")
    if conn is None:
        console.print("[yellow]Your chat list could not be opened.[/yellow] Run:  co wechat key capture")
        raise typer.Exit(2)
    rows = engine.sessions(conn, _contacts(db_storage), limit)
    for number, row in enumerate(rows, 1):
        unread = f"  [red]{row['unread']} new[/red]" if row["unread"] else ""
        summary = " ".join(row["summary"].split())[:46]
        console.print(f"{number:>3}  [bold]{row['name'][:22]:<22}[/bold] {_clock(row['time']):>5}  {summary}{unread}")
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    LISTING.write_text(json.dumps({"at": time.time(), "chats": [r["username"] for r in rows]}))
    os.chmod(LISTING, 0o600)
    console.print("\nNext: co wechat read 1  (a number above, or a name)")


def _who(db_storage: Path, who: str, known: dict) -> str | None:
    """A number from the last list (for 15 minutes) or a name, to a WeChat username."""
    import json
    import time
    if who.isdigit() and LISTING.is_file():
        saved = json.loads(LISTING.read_text())
        if time.time() - saved["at"] < LISTING_MINUTES * 60 and 0 < int(who) <= len(saved["chats"]):
            return saved["chats"][int(who) - 1]
    lowered = who.lower()
    exact = [u for u, name in known.items() if name.lower() == lowered or u.lower() == lowered]
    partial = [u for u, name in known.items() if lowered in name.lower()]
    return (exact or partial or [None])[0]


def _message_dbs(db_storage: Path) -> list:
    return [c for c in (_open(p) for p in sorted((db_storage / "message").glob("*message_[0-9]*.db"))) if c]


@wechat_app.command("read", epilog="Example:  co wechat read 1  |  co wechat read 妈妈 --limit 50")
def read(who: str = typer.Argument(..., help="A number from co wechat, or a name"),
         limit: int = typer.Option(30, "--limit", help="How many recent messages")):
    """Show one chat's recent messages, oldest first. Read-only."""
    from ...useful_tools import wechat as engine
    db_storage = _setup(interactive=False)
    known = _contacts(db_storage)
    username = _who(db_storage, who, known)
    if not username:
        console.print(f"[yellow]No chat matches {who}.[/yellow] List them:  co wechat")
        raise typer.Exit(2)
    table = engine.message_table(username)
    for conn in _message_dbs(db_storage):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (table,)).fetchone():
            console.print(f"[bold]{known.get(username, username)}[/bold]\n")
            for m in engine.messages(conn, username, known, limit):
                console.print(f"{_clock(m['time']):>5}  [cyan]{m['sender'][:16]}[/cyan]  {m['text']}")
            return
    console.print(f"[yellow]No messages from {known.get(username, username)} on this Mac.[/yellow] "
                  "Older history may still be on your phone (Settings → General → Chat Log Migration).")
    raise typer.Exit(1)


@wechat_app.command("search", epilog="Example:  co wechat search 合同  |  co wechat search invoice --limit 50")
def search(words: str = typer.Argument(..., help="Text to look for in messages"),
           limit: int = typer.Option(20, "--limit", help="How many results")):
    """Find text messages that contain the words, across your chats, newest first. Read-only."""
    from ...useful_tools import wechat as engine
    db_storage = _setup(interactive=False)
    known = _contacts(db_storage)
    chat_of = {engine.message_table(u): u for u in known}
    hits = []
    for conn in _message_dbs(db_storage):
        # One table per chat, Msg_<32 hex>; indexes and helper tables share the prefix.
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                  if re.fullmatch(r"Msg_[0-9a-f]{32}", r[0])]
        for table in tables:
            for r in conn.execute(f'SELECT create_time, message_content, WCDB_CT_message_content FROM "{table}" '
                                  "WHERE local_type = 1 ORDER BY sort_seq DESC LIMIT 3000"):
                text = engine.text_of(r[1], r[2])
                if words.lower() in text.lower():
                    hits.append((r[0], known.get(chat_of.get(table, ""), "?"), " ".join(text.split())))
    for when, chat, text in sorted(hits, reverse=True)[:limit]:
        console.print(f"{_clock(when):>5}  [bold]{chat[:18]}[/bold]  {text[:90]}")
    if not hits:
        console.print(f"No messages contain {words}.")


def _own_username(account: Path) -> str:
    """The account's own WeChat id: its folder is the id plus a short suffix (wxid_xxx_ab12)."""
    name = account.name
    return name.rsplit("_", 1)[0] if name.startswith("wxid_") and name.count("_") >= 2 else name


@wechat_app.command("sync", epilog="Example:  co wechat sync  |  co wechat sync --quiet")
def sync(quiet: bool = typer.Option(False, "--quiet", help="Print only problems")):
    """Writes your WeChat messages as inbox files (received.jsonl, own.jsonl) under ~/.co/inbox/wechat, for co rem. Reads WeChat only."""
    import json
    import re as _re
    from datetime import datetime, timezone
    from ...inbox.store import default_home
    from ...useful_tools import wechat as engine
    db_storage = _setup(interactive=False)
    account = db_storage.parent
    own = _own_username(account)
    known = _contacts(db_storage)
    home = default_home("wechat")
    home.mkdir(parents=True, exist_ok=True)
    os.chmod(home, 0o700)
    received, mine, chats = [], [], {}
    for conn in _message_dbs(db_storage):
        users = [r[0] for r in conn.execute("SELECT user_name FROM Name2Id")]
        by_table = {engine.message_table(u): u for u in users}
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
            chat = by_table.get(table) if _re.fullmatch(r"Msg_[0-9a-f]{32}", table) else None
            if not chat:
                continue
            chats[chat] = known.get(chat, chat)
            sender_of = {r[0]: r[1] for r in conn.execute("SELECT rowid, user_name FROM Name2Id")}
            for r in conn.execute(f'SELECT local_id, local_type, create_time, real_sender_id, message_content, '
                                  f'WCDB_CT_message_content FROM "{table}" ORDER BY sort_seq'):
                kind = r[1] & 0xFFFF
                text = engine.text_of(r[4], r[5]) if kind in (1, 10000) else engine.KINDS.get(kind, "[其他]")
                sender = sender_of.get(r[3], "")
                if chat.endswith("@chatroom") and ":\n" in text[:80]:
                    sender, text = text.split(":\n", 1)
                row = {"id": str(r[0]), "chat": chat, "chat_name": chats[chat],
                       "at": datetime.fromtimestamp(r[2], timezone.utc).isoformat(),
                       "text": text.strip(), "sender": sender, "sender_name": known.get(sender, sender),
                       "kind": "text" if kind == 1 else "system" if kind == 10000 else "media"}
                (mine if sender == own else received).append(row)
    for name, rows in (("received.jsonl", received), ("own.jsonl", mine)):
        target, part = home / name, home / (name + ".part")
        part.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        os.chmod(part, 0o600)
        part.replace(target)
    (home / "chats.json").write_text(json.dumps(chats, ensure_ascii=False, indent=1))
    os.chmod(home / "chats.json", 0o600)
    if not quiet:
        people = sum(1 for c in chats if not c.endswith("@chatroom") and not c.startswith("gh_"))
        console.print(f"[green]Wrote[/green] {len(received) + len(mine)} messages from {len(chats)} chats "
                      f"({people} with one person) to {home}.")
        console.print("Next: co rem sources add wechat  (reads every one-to-one chat; add a group with --chat <id>)")


@wechat_app.command("tables", epilog="Example:  co wechat tables")
def tables():
    """List each WeChat database with its tables and row counts, for raw access. Read-only."""
    from ...useful_tools import wechat as engine
    db_storage = _ready()
    opened = 0
    for path in engine.message_dbs(db_storage):
        conn = _open(path)
        if conn is None:
            console.print(f"[yellow]{path.name}[/yellow]: no key opens it yet (run: co wechat key capture)")
            continue
        opened += 1
        listing = ", ".join(f"{name}({rows})" for name, rows in engine.tables(conn)) or "(no tables)"
        console.print(f"[bold]{path.name}[/bold]: {listing}")
    if not opened:
        console.print("[yellow]No key opens any WeChat database yet.[/yellow] Run:  co wechat key capture")
        raise typer.Exit(2)


@wechat_app.command("decrypt", epilog="Example:  co wechat decrypt --out ~/wechat-plain")
def decrypt(
    out: Path = typer.Option(Path("wechat-plain"), "--out", help="Directory to write plaintext SQLite copies into"),
):
    """Writes a plaintext SQLite copy of each WeChat database into --out, openable by any SQLite tool. Local only."""
    from ...useful_tools import wechat as engine

    db_storage = _ready()
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in engine.message_dbs(db_storage):
        key = _key_for(path)
        try:
            plaintext = engine.decrypt_db(path, key) if key else None
        except engine.WrongKeyError:
            plaintext = None
        if plaintext is None:
            console.print(f"[yellow]skip[/yellow] {path.name}: no key opens it yet")
            continue
        target = out / path.name
        target.write_bytes(plaintext)
        written += 1
        console.print(f"[green]wrote[/green] {target} ({len(plaintext) // 1024} KB)")
    console.print(f"\n{written} database(s) decrypted to {out}. These are plaintext — keep them local.")
    raise typer.Exit(0 if written else 2)


@wechat_app.command("export", epilog='Example:  co wechat export --db contact.db --table contact --format json --out contacts.json')
def export(
    db: str = typer.Option(..., "--db", help="A database file name, as shown by: co wechat tables"),
    table: str = typer.Option(..., "--table", help="A table in that database, as shown by: co wechat tables"),
    fmt: str = typer.Option("json", "--format", help="json or md"),
    out: Path = typer.Option(None, "--out", help="Write here instead of printing"),
):
    """Writes one table from a WeChat database as JSON or Markdown to --out, or prints it. Reads WeChat only."""
    import json
    import sqlite3
    from ...useful_tools import wechat as engine

    db_storage = _ready()
    matches = [p for p in engine.message_dbs(db_storage) if p.name == db]
    if not matches:
        console.print(f"[yellow]No database named {db}.[/yellow] List them:  co wechat tables")
        raise typer.Exit(2)
    conn = _open(matches[0])
    if conn is None:
        console.print(f"[yellow]{db}[/yellow]: no key opens it yet (run: co wechat key capture)")
        raise typer.Exit(2)
    try:
        cursor = conn.execute(f'SELECT * FROM "{table}"')
    except sqlite3.OperationalError:
        console.print(f"[yellow]No table {table} in {db}.[/yellow] List them:  co wechat tables")
        raise typer.Exit(2)
    cols = [c[0] for c in cursor.description]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    if fmt == "md":
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
        lines += ["| " + " | ".join(str(row[c]).replace("|", "\\|") for c in cols) + " |" for row in rows]
        text = "\n".join(lines) + "\n"
    else:
        text = json.dumps(rows, ensure_ascii=False, indent=2, default=lambda v: v.hex() if isinstance(v, bytes) else str(v))
    if out:
        out.write_text(text)
        console.print(f"[green]wrote[/green] {len(rows)} rows to {out}")
    else:
        console.print(text)
