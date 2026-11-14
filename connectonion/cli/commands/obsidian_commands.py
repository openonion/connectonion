"""
Purpose: Discover, read and search Obsidian notes; preview or explicitly create/append one note
LLM-Note:
  Dependencies: imports from [json, typer, rich.markup, cli/style.py, command_tips.py, gmail_listings.py, environment.global_config_dir, useful_tools/obsidian.py] | imported lazily by [cli/main.py]
  Data flow: vault and folder listings → cached row references; selected folders → displayed notes or JSON; note row → context-bound path → original Markdown
  State/Effects: reads do not change notes; create/append write only with --yes; human lists cache paths under ~/.co/obsidian-listings for 15 minutes; JSON never saves rows
  Errors: ObsidianError → cause and Next on stderr, exit 1; ValueError → same format, exit 2
"""

import json
import os
import re
import shlex
import stat
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from functools import wraps
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Sequence

import typer
from rich.markup import escape
from rich.table import Column, Table
from rich.text import Text

from .. import style
from ...environment import global_config_dir, selected_command
from ...useful_tools import obsidian as api
from .command_tips import mark_next_step_named, selected_tip
from .gmail_listings import LIFETIME_SECONDS, MAX_FILE_BYTES, ListingError, resolve_reference, save_listing

ROW = re.compile(r"#?[0-9]{1,4}")
LISTING_ID = re.compile(r"[a-f0-9]{32}")
MAX_NAVIGATION_ROWS = 500
OBSIDIAN_LISTING_FAMILY = "notes"
VAULTS_CONTEXT = "obsidian:vaults"


class UsageError(ValueError):
    """A wrong reference and the command that helps choose a new one."""

    def __init__(self, message: str, next_step: str):
        super().__init__(message)
        self.next_step = next_step


def _reported(handler):
    """The cause and one recovery command, with no partial stdout or traceback."""
    @wraps(handler)
    def run(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except (api.ObsidianError, ValueError) as error:
            out = style.console(stderr=True)
            out.print(f"{style.error('✗')} {escape(str(error))}")
            out.print(style.next_line(selected_tip(getattr(error, "next_step", api.HELP))))
            mark_next_step_named()
            raise typer.Exit(1 if isinstance(error, api.ObsidianError) else 2) from None
    return run


def _emit_json(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _tip(command: str, as_json: bool) -> None:
    """JSON keeps stdout parseable; its Next line goes to stderr, as Linear's does."""
    style.console(stderr=as_json).print(style.next_line(selected_command(command)), emoji=False)
    mark_next_step_named()


def _render_vaults(vaults: list[dict], numbered: int) -> None:
    out = style.console()
    out.print(f"{style.count(len(vaults))} registered Obsidian vaults")
    if not vaults:
        return
    table = Table(
        Column("#", justify="right", no_wrap=True),
        Column("Vault / path", overflow="fold"),
        Column("Availability", no_wrap=True),
        Column("Open", no_wrap=True),
        box=None,
        pad_edge=False,
        header_style="co.label",
    )
    for index, vault in enumerate(vaults, 1):
        available = style.ok("available") if vault["available"] else style.warn("unavailable")
        opened = "open" if vault["open"] else "not open"
        label = Text.assemble(vault["name"], "\n", (vault["path"], "co.path"))
        table.add_row(style.count(index) if index <= numbered else "", label, available, opened)
    out.print(table, soft_wrap=False)


@_reported
def handle_obsidian_vaults(*, json_output: bool = False) -> None:
    """List registered vaults without importing them or reading any notes."""
    vaults = api.discover_vaults()
    numbered = 0
    if json_output:
        _emit_json(vaults)
    else:
        paths = [Path(vault["path"]) for vault in vaults]
        cache = _listings("vaults").resolve()
        if not any(cache.is_relative_to(path) for path in paths):
            rows = paths[:MAX_NAVIGATION_ROWS]
            _store_rows([_path_key(path) for path in rows], "vaults", VAULTS_CONTEXT, next_step=api.HELP)
            numbered = len(rows)
        _render_vaults(vaults, numbered)
    next_command = 'co obsidian ls --vault "<vault-path>"'
    for index, vault in enumerate(vaults, 1):
        if vault["available"]:
            next_command = _scope_command("ls", str(index) if index <= numbered else vault["path"], ())
            break
    _tip(next_command, json_output)


# -- references -----------------------------------------------------------

def _resolve_vault_reference(reference: str | None) -> Path:
    """Use an explicit path or a unique registered name; auto-select only one available vault."""
    if reference is not None:
        if not reference.strip() or "\x00" in reference:
            raise ValueError("Choose a non-empty vault name or path.")
        path = Path(reference).expanduser()
        if path.is_absolute() or "/" in reference or "\\" in reference or reference.startswith((".", "~")):
            return path
        if ROW.fullmatch(reference):
            raise UsageError("Choose a vault name or path for this command.", "co obsidian vaults")
    vaults = api.discover_vaults()
    if reference is None:
        found = [vault for vault in vaults if vault["available"]]
        if len(found) == 1:
            return Path(found[0]["path"])
        if not found:
            raise api.ObsidianError("No available registered vault. Choose one with --vault <path>.", "co obsidian vaults")
        raise UsageError("Several vaults are available. Choose one with --vault <name or path>.", "co obsidian vaults")
    found = [vault for vault in vaults if vault["name"] == reference]
    if len(found) == 1:
        return Path(found[0]["path"])
    if len(found) > 1:
        raise UsageError(f"Several vaults are named {reference!r}: " + ", ".join(vault["path"] for vault in found)
                         + ". Give the path instead.", "co obsidian vaults")
    if path.is_dir():
        return path
    raise api.ObsidianError(f"No registered vault named {reference!r}. Choose a vault path instead.", "co obsidian vaults")


def _listing_context(vault_path: Path, folders: Sequence[str]) -> str:
    """Hash canonical selections before the shared cache's account case folding."""
    scope = api._validate_scope(vault_path, folders)
    selection = [os.path.normcase(str(scope.vault_path)),
                 sorted(os.path.normcase(str(folder)) for folder in scope.folders)]
    return "obsidian:" + sha256(json.dumps(selection, ensure_ascii=False).encode("utf-8")).hexdigest()


def _listings(family: str = "notes") -> Path:
    directory = global_config_dir() / "obsidian-listings"
    return directory if family == "notes" else directory / family


def _path_key(path: str | Path) -> str:
    return sha256(os.fsencode(os.path.normcase(path))).hexdigest()


def _listing_pointer(family: str, context: str) -> Path:
    name = f"last-folders-{context}" if family == "folders" else f"last-{family}"
    return _listings(family) / name


def _save_note_scope(path: Path, scope: dict, expires_at: float) -> None:
    """Store the selection beside its immutable row list before publishing the token."""
    payload = json.dumps({"scope": scope, "expires_at": expires_at}, ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_FILE_BYTES:
        raise ListingError("Obsidian listing scope is too large. Select fewer folders.")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    # The shared writer evicts old row lists. Discard their companion scopes too.
    for old in path.parent.glob("*.scope"):
        if LISTING_ID.fullmatch(old.stem) and not old.with_suffix(".json").is_file():
            old.unlink(missing_ok=True)


def _store_rows(ids: list[str], family: str, context: str, *, next_step: str, scope: dict | None = None) -> str | None:
    """Publish the displayed rows atomically. Empty lists clear the latest rows."""
    pointer = _listing_pointer(family, context)
    temporary = None
    try:
        if not ids:
            pointer.unlink(missing_ok=True)
            return None
        # The shared API offers one Obsidian family. Each kind has its own directory and context.
        now = time.time()
        token = save_listing(pointer.parent, context, OBSIDIAN_LISTING_FAMILY, ids, now=now, provider="obsidian")
        if scope is not None:
            _save_note_scope(pointer.parent / f"{token}.scope", scope, now + LIFETIME_SECONDS)
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=pointer.parent,
                                         prefix=".last-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(token)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, pointer)
    except (OSError, ListingError):
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                raise api.ObsidianError(f"Could not remove an incomplete listing under {pointer.parent}.", next_step) from None
        raise api.ObsidianError(f"Could not save {family} row numbers under {pointer.parent}. "
                                "Check write access there, or use paths from --json.", next_step) from None
    return token


def _read_cache_file(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Invalid listing cache file")
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Listing cache file is too large")
    return content


def _latest_listing(family: str, context: str, next_step: str) -> str:
    try:
        return _read_cache_file(_listing_pointer(family, context), 64).decode("ascii").strip()
    except (OSError, UnicodeError, ValueError):
        raise UsageError(f"No recent {family} list. List again or use a path.", next_step) from None


def _resolve_row(reference: str, family: str, context: str, *,
                 next_step: str, listing: str | None = None) -> str:
    if not ROW.fullmatch(reference):
        return reference
    if listing is None:
        listing = _latest_listing(family, context, next_step)
    try:
        return resolve_reference(_listings(family), reference, context, OBSIDIAN_LISTING_FAMILY, listing,
                                 provider="obsidian")
    except ListingError as error:
        raise UsageError(str(error), next_step) from None


def _unique_vault_name(path: Path, vaults: list[dict] | None = None) -> str | None:
    """Use a short name in a tip only when it resolves to the selected vault."""
    name = path.name
    if not name.strip() or ROW.fullmatch(name) or name.startswith(("-", ".", "~")) or "\\" in name:
        return None
    if vaults is None:
        try:
            vaults = api.discover_vaults()
        except api.ObsidianError:
            return None
    matches = [vault["path"] for vault in vaults if vault["name"] == name]
    return name if matches == [str(path)] else None


def _resolve_list_vault(reference: str | None) -> tuple[Path, str | None]:
    """Resolve an ls/notes vault and retain a unique name for its next command."""
    if reference is None or not ROW.fullmatch(reference):
        path = _resolve_vault_reference(reference)
        return path, reference if path.is_absolute() and reference == path.name else None

    relist = "co obsidian vaults"
    key = _resolve_row(reference, "vaults", VAULTS_CONTEXT, next_step=relist)
    vaults = api.discover_vaults()
    vault = next((vault for vault in vaults if _path_key(vault["path"]) == key), None)
    if vault is None or not vault["available"]:
        raise api.ObsidianError(f"Vault row {reference} is no longer available. List vaults again.", relist)
    path = Path(vault["path"])
    return path, _unique_vault_name(path, vaults)


def _resolve_list_folders(vault: Path, folders: Sequence[str]) -> tuple[Path, Sequence[str]]:
    if not any(ROW.fullmatch(folder) for folder in folders):
        return vault, folders
    root = api.list_vault_root(vault)
    vault = Path(root["vault"])
    relist = _scope_command("ls", vault, ())
    context = _path_key(vault)
    listing = _latest_listing("folders", context, relist)
    current = {_path_key(folder): folder for folder in root["folders"]}
    selected = []
    for folder in folders:
        if ROW.fullmatch(folder):
            key = _resolve_row(folder, "folders", context, next_step=relist, listing=listing)
            if key not in current:
                raise UsageError(f"Folder row {folder} is no longer available. List folders again.", relist)
            folder = current[key]
        selected.append(folder)
    return vault, selected


def _selection(vault: Path, folders: Sequence[str]) -> tuple[Path, tuple[str, ...]]:
    scope = api._validate_scope(vault, folders)
    return scope.vault_path, tuple(folder.relative_to(scope.vault_path).as_posix() for folder in scope.folders)


def _scope_command(command: str, vault: str | Path, folders: Sequence[str]) -> str:
    return f"co obsidian {command} --vault {shlex.quote(str(vault))}" + "".join(
        f" --folder {shlex.quote(folder)}" for folder in folders)


def _limit(last: int) -> None:
    if not 1 <= last <= 250:
        raise ValueError("Choose --last between 1 and 250.")


def _save_rows(vault: Path, folders: Sequence[str], rows: list[dict]) -> str | None:
    if _listings().resolve().is_relative_to(vault):
        raise api.ObsidianError("The row cache would be inside this vault. Use --json and read by path instead.",
                                "co obsidian notes --help")
    return _store_rows([row["path"] for row in rows], "notes", _listing_context(vault, folders),
                       next_step="co obsidian notes --help", scope={"vault": str(vault), "folders": folders})


def _read_note_scope(listing: str) -> tuple[Path, list[str]] | None:
    if not LISTING_ID.fullmatch(listing):
        raise ValueError("Invalid listing ID")
    directory = _listings()
    try:
        content = _read_cache_file(directory / f"{listing}.scope", MAX_FILE_BYTES)
    except FileNotFoundError:
        # Listings written before scopes had their own file can still be read.
        content = _read_cache_file(directory / f"{listing}.json", MAX_FILE_BYTES)
    data = json.loads(content)
    if not time.time() < data["expires_at"]:
        raise ValueError("Expired listing")
    scope = data.get("scope")
    if scope is None:
        return None
    vault, folders = scope["vault"], scope["folders"]
    if (isinstance(vault, str) and Path(vault).is_absolute() and isinstance(folders, list)
            and folders and all(isinstance(folder, str) for folder in folders)):
        return Path(vault), folders
    raise ValueError("Invalid Obsidian note listing scope")


def _listed_note_scope(listing: str | None) -> tuple[Path, list[str], str]:
    next_step = "co obsidian notes --help"
    if listing is None:
        listing = _latest_listing("notes", "", next_step)
    try:
        scope = _read_note_scope(listing)
    except (OSError, ValueError, KeyError, TypeError):
        raise UsageError("Note listing unavailable or expired. List notes again.", next_step) from None
    if scope is None:
        raise UsageError("Use the original --vault and --folder for this listing, or list notes again.", next_step)
    return scope[0], scope[1], listing


def _select_note(reference: str, *, vault: str | None, folders: Sequence[str], listing: str | None,
                 help_command: str) -> tuple[Path, tuple[str, ...], str]:
    numbered = ROW.fullmatch(reference) is not None
    if numbered and vault is None and not folders:
        vault_path, folders, listing = _listed_note_scope(listing)
    elif folders:
        vault_path = _resolve_vault_reference(vault)
    else:
        raise UsageError("Choose --folder to set the scope, or use a note row from a listing.", help_command)
    path, selected = _selection(vault_path, folders)
    if numbered:
        reference = _resolve_row(reference, "notes", _listing_context(path, selected), listing=listing,
                                 next_step="co obsidian notes --help")
    return path, selected, reference


# -- output ---------------------------------------------------------------

def _listing_note(token: str | None) -> None:
    if token:
        style.console().print(f"Listing: {token} (15 min)")


def _read_tip(rows: list[dict], token: str | None, vault: Path, folders: Sequence[str], as_json: bool) -> None:
    if token:
        return _tip(f"co obsidian read 1 --listing {token}", as_json)
    ref = shlex.quote(rows[0]["path"]) if rows else '"<note.md>"'
    _tip(_scope_command(f"read {ref}", vault, folders), as_json)


def _duplicate_note_folders(paths: list[PurePosixPath]) -> dict[PurePosixPath, str]:
    """Show the shortest parent suffix that distinguishes repeated filenames."""
    filenames = Counter(path.name for path in paths)
    duplicates = [path for path in paths if filenames[path.name] > 1]
    suffix_counts = Counter(
        path.parts[-size:] for path in duplicates for size in range(2, len(path.parts) + 1)
    )
    folders = {}
    for path in duplicates:
        folder = path.parent.as_posix()
        for size in range(2, len(path.parts)):
            if suffix_counts[path.parts[-size:]] == 1:
                folder = "…/" + "/".join(path.parts[-size:-1])
                break
        folders[path] = folder + "/"
    return folders


def _render_notes(notes: list[dict], *, listing_token: str | None, ids: bool = False) -> None:
    out = style.console()
    out.print(f"{style.count(len(notes))} Obsidian notes")
    if ids:
        for note in notes:
            path = style.path(note["path"])
            out.print(f"{path}  {escape(note['title'])}  {path}  {style.muted(note['modified_at'])}")
    else:
        paths = [PurePosixPath(note["path"]) for note in notes]
        folders = _duplicate_note_folders(paths)
        for index, path in enumerate(paths, 1):
            label = escape(path.name)
            if path in folders:
                label += f"  {style.path(folders[path])}"
            out.print(f"{style.count(index)}  {label}")
    _listing_note(listing_token)


def _render_search(hits: list[dict], *, ids: bool = False) -> None:
    out = style.console()
    out.print(f"{style.count(len(hits))} Obsidian matches")
    if not hits:
        return

    results = Table.grid(padding=(0, 2))
    if not ids:
        results.add_column(justify="right", no_wrap=True, style="co.count")
    results.add_column(overflow="fold")
    for index, hit in enumerate(hits, 1):
        title = (hit["title"], "co.label")
        path = (hit["path"], "co.path")
        first, second = (path, title) if ids else (title, path)
        modified = datetime.fromisoformat(hit["modified_at"]).strftime("%Y-%m-%d %H:%M %Z")
        fields = ", ".join(hit["matched_fields"])
        details = Text.assemble(first, "\n", second, "\n", (f"{modified} · Matched {fields}", "co.muted"))
        excerpt = " ".join(hit["excerpt"].split())
        if excerpt:
            details.append("\n" + excerpt)
        if index > 1:
            results.add_row()
        if ids:
            results.add_row(details)
        else:
            results.add_row(str(index), details)
    out.print()
    out.print(results, soft_wrap=False)
    out.print()


def _render_note(note: dict) -> None:
    """Show the note's title, path, properties and Markdown in a terminal."""
    from rich.markdown import CodeBlock, Markdown

    content, offset = note["content"], note["body_offset"]
    out = style.console()
    out.print(Text(note["title"], style="co.label"), Text(note["path"], style="co.path"), sep="\n", soft_wrap=False)
    out.print()
    properties = "\n".join(content[:offset].splitlines()[1:-1])
    if properties:
        out.print(style.label("Properties"), Text(properties), sep="\n", soft_wrap=False)
        out.print()
    body = content[offset:]
    if not body.strip():
        out.print(style.muted("No body text."))
    else:
        try:
            markdown = Markdown(body, hyperlinks=False)
            # Rich would otherwise skip the content of embedded HTML blocks.
            markdown.elements = {**markdown.elements, "html_block": CodeBlock}
            out.print(markdown, soft_wrap=False)
        except IndexError:
            # Rich can fail to render an unmatched inline HTML tag.
            out.print(Text(body), soft_wrap=False)
    out.print()


def _print_raw_note(content: str) -> None:
    """Preserve the source bytes on stdout and separate the stderr hint."""
    # A binary stream also preserves CRLF when stdout is a Windows pipe.
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(content.encode("utf-8"))
        sys.stdout.buffer.flush()
    else:
        print(content, end="", flush=True)
    if content and not content.endswith("\n"):
        print(file=sys.stderr)


def _browse_vault(vault: Path, name: str | None, json_output: bool) -> None:
    root = api.list_vault_root(vault)
    path, folders, notes = Path(root["vault"]), root["folders"], root["notes"]
    numbered = 0
    help_command = "co obsidian ls --help"
    if json_output:
        _emit_json(root)
    else:
        if not _listings("folders").resolve().is_relative_to(path):
            rows = folders[:MAX_NAVIGATION_ROWS]
            _store_rows([_path_key(folder) for folder in rows], "folders", _path_key(path), next_step=help_command)
            numbered = len(rows)
        out = style.console()
        out.print(f"{style.count(len(folders))} folders · {style.count(len(notes))} Markdown files in {escape(path.name)}")
        for index, folder in enumerate(folders, 1):
            prefix = f"{style.count(index)}  " if index <= numbered else "   "
            out.print(f"{prefix}{style.path(folder + '/')}")
        for note in notes:
            out.print(f"   {style.path(note)}")
    if not folders:
        return _tip(help_command, json_output)
    folder = folders[0]
    literal = f"./{folder}" if ROW.fullmatch(folder) else folder
    command = _scope_command("ls", name or path, ("1" if numbered else literal,))
    if _listings().resolve().is_relative_to(path):
        command += " --json"
    _tip(command, json_output)


@_reported
def handle_obsidian_notes(*, vault: str | None = None, folders: Sequence[str] = (), last: int = 20,
                          ids: bool = False, json_output: bool = False) -> None:
    """Browse the vault root or list notes in the selected folders, newest first."""
    _limit(last)
    path, name = _resolve_list_vault(vault)
    if not folders:
        return _browse_vault(path, name, json_output)
    path, folders = _resolve_list_folders(path, folders)
    path, selected = _selection(path, folders)
    notes = sorted(api.list_notes(path, folders=selected), key=lambda note: (-note["mtime_ns"], note["path"]))[:last]
    if json_output:
        _emit_json(notes)
        token = None
    else:
        token = _save_rows(path, selected, notes)
        _render_notes(notes, listing_token=token, ids=ids)
    if not notes:
        return _tip(_scope_command("ls", name or path, ()), json_output)
    _read_tip(notes, token, path, selected, json_output)


@_reported
def handle_obsidian_read(ref: str, *, vault: str | None = None, folders: Sequence[str] = (),
                         listing: str | None = None, json_output: bool = False, raw: bool = False) -> None:
    """Format a terminal read and keep piped Markdown or JSON on stdout."""
    path, selected, reference = _select_note(ref, vault=vault, folders=folders, listing=listing,
                                             help_command="co obsidian read --help")
    note = api.read_note(path, reference, folders=selected)
    if json_output:
        _emit_json(note)
    elif not raw and sys.stdout.isatty():
        _render_note(note)
    else:
        _print_raw_note(note["content"])
    _tip(_scope_command('search "<query>"', _unique_vault_name(path) or path, selected), True)


@_reported
def handle_obsidian_search(query: str, *, vault: str | None = None, folders: Sequence[str], last: int = 20,
                           ids: bool = False, json_output: bool = False) -> None:
    """Search the same explicit scope; displayed hits become the next notes row list."""
    _limit(last)
    path, selected = _selection(_resolve_vault_reference(vault), folders)
    hits = api.search_notes(path, query, folders=selected)[:last]
    if json_output:
        _emit_json(hits)
        token = None
    else:
        token = _save_rows(path, selected, hits)
        _render_search(hits, ids=ids)
        _listing_note(token)
    _read_tip(hits, token, path, selected, json_output)


# -- explicit writes ------------------------------------------------------

@_reported
def handle_obsidian_write(operation: str, note_path: str, content: str, *, vault: str | None,
                          folders: Sequence[str], yes: bool = False, expect: str | None = None,
                          json_output: bool = False, listing: str | None = None) -> None:
    """Preview or write exactly one path; a copied Next binds the original version and input."""
    help_command = f"co obsidian {operation} --help"
    if operation == "append" and yes and ROW.fullmatch(note_path):
        raise UsageError("Preview the numbered note first. Copy the preview's Next command to write to its path.",
                         help_command)
    piped = content == "-"
    if piped:
        try:
            content = sys.stdin.buffer.read().decode("utf-8") if hasattr(sys.stdin, "buffer") else sys.stdin.read()
        except (OSError, UnicodeError):
            raise UsageError("Cannot read UTF-8 content from standard input.", help_command) from None
    if operation == "append":
        path, selected, note_path = _select_note(note_path, vault=vault, folders=folders, listing=listing,
                                                 help_command=help_command)
        change = api.append_note
    else:
        path, selected = _selection(_resolve_vault_reference(vault), folders)
        change = api.create_note
    result = change(path, note_path, content, folders=selected, yes=yes, expect=expect)
    if json_output:
        _emit_json(result)
    else:
        out = style.console()
        label = "Preview" if result["preview"] else "Created" if operation == "create" else "Appended"
        if not result["changed"]:
            label = "Preview: no change" if result["preview"] else "No change"
        out.print(f"{style.label(label)} {style.path(result['path'])}: "
                  f"{result['bytes_before']} → {result['bytes_after']} bytes", emoji=False)
        if result["preview"]:
            out.print(style.muted("Nothing written. Content to create or append:"))
            out.print(content, markup=False, emoji=False, highlight=False)
    if not result["preview"]:
        return _tip(_scope_command(f"read {shlex.quote(result['path'])}", path, selected), json_output)
    command = _scope_command(f"{operation} {shlex.quote(result['path'])}", path, selected)
    again_stdin = piped or content == "-" or any(ord(char) < 32 or ord(char) == 127 for char in content)
    # The selector is added to the outer command only; content is always one literal argument.
    command += f" --content={shlex.quote('-' if again_stdin else content)} --yes --expect {result['expect']}"
    if json_output:
        command += " --json"
    if again_stdin:
        style.console(stderr=json_output).print(
            style.muted("Pipe the same UTF-8 content into the command below; different input is refused."))
    _tip(command, json_output)
