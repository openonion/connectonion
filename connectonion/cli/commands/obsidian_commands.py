"""
Purpose: Discover Obsidian vaults, list or read selected notes, and search them from the terminal
LLM-Note:
  Dependencies: imports from [json, typer, rich.markup, cli/style.py, command_tips.py, gmail_listings.py, environment.global_config_dir, useful_tools/obsidian.py] | imported lazily by [cli/main.py]
  Data flow: explicit vault and folders → tool records → displayed rows or JSON; a row reference → context-bound path → original Markdown
  State/Effects: vaults remain read-only; human lists cache displayed relative paths under ~/.co/obsidian-listings for 15 minutes; JSON never saves rows
  Errors: ObsidianError → cause and Next on stderr, exit 1; ValueError → same format, exit 2
"""

import json
import os
import re
import shlex
import stat
import sys
import tempfile
from functools import wraps
from hashlib import sha256
from pathlib import Path
from typing import Sequence

import typer
from rich.markup import escape

from .. import style
from ...environment import global_config_dir
from ...useful_tools import obsidian as api
from .command_tips import mark_next_step_named, print_tip, selected_tip
from .gmail_listings import ListingError, resolve_reference, save_listing

ROW = re.compile(r"#?[0-9]{1,4}")


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
    if not as_json:
        print_tip(f"Next: {command}")
        return
    style.console(stderr=True).print(style.next_line(selected_tip(command)))
    mark_next_step_named()


def _render_vaults(vaults: list[dict]) -> None:
    lines = [f"{style.count(len(vaults))} registered Obsidian vaults"]
    for vault in vaults:
        available = style.ok("available") if vault["available"] else style.warn("unavailable")
        opened = "open" if vault["open"] else "not open"
        lines.append(f"{escape(vault['name'])}  {style.path(vault['path'])}  {available}  {opened}")
    out = style.console()
    for line in lines:
        out.print(line)


@_reported
def handle_obsidian_vaults(*, json_output: bool = False) -> None:
    """List registered vaults without importing them or reading any notes."""
    vaults = api.discover_vaults()
    if json_output:
        _emit_json(vaults)
    else:
        _render_vaults(vaults)
    _tip('co obsidian notes --vault "<path>" --folder "."', json_output)


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
            raise UsageError("Vaults use names or paths, not row numbers.", "co obsidian vaults")
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


def _listings() -> Path:
    return global_config_dir() / "obsidian-listings"


def _store_note_rows(*, context: str, note_paths: Sequence[str]) -> str | None:
    """Store only displayed paths; an empty result invalidates the last-notes pointer."""
    temporary = None
    try:
        if not note_paths:
            (_listings() / "last-notes").unlink(missing_ok=True)
            return None
        token = save_listing(_listings(), context, "notes", list(note_paths), provider="obsidian")
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=_listings(),
                                         prefix=".last-notes-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(token)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, _listings() / "last-notes")
        temporary = None
    except (OSError, ListingError):
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                raise api.ObsidianError("Could not remove an incomplete note listing. Check ~/.co/obsidian-listings.",
                                        "co obsidian notes --help") from None
        raise api.ObsidianError("Could not save note row numbers under ~/.co/obsidian-listings. "
                                "Check write access there, or use paths from --json.", "co obsidian notes --help") from None
    return token


def _resolve_note_reference(reference: str, *, context: str, listing: str | None = None) -> str:
    """Only row numbers touch the cache; paths and titles pass to the tool unchanged."""
    if not ROW.fullmatch(reference):
        return reference
    if listing is None:
        try:
            descriptor = os.open(_listings() / "last-notes", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                                 | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(descriptor, "r", encoding="ascii") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("Invalid notes pointer")
                listing = stream.read(65).strip()
        except (OSError, UnicodeError, ValueError):
            raise UsageError("No recent notes list. List the selected folders again, or give a note path.",
                             "co obsidian notes --help") from None
    try:
        return resolve_reference(_listings(), reference, context, "notes", listing, provider="obsidian")
    except ListingError as error:
        raise UsageError(str(error), "co obsidian notes --help") from None


def _selection(vault: str | None, folders: Sequence[str]) -> tuple[Path, tuple[str, ...]]:
    scope = api._validate_scope(_resolve_vault_reference(vault), folders)
    return scope.vault_path, tuple(folder.relative_to(scope.vault_path).as_posix() for folder in scope.folders)


def _scope_command(command: str, vault: Path, folders: Sequence[str]) -> str:
    return f"co obsidian {command} --vault {shlex.quote(str(vault))}" + "".join(
        f" --folder {shlex.quote(folder)}" for folder in folders)


def _limit(last: int) -> None:
    if not 1 <= last <= 250:
        raise ValueError("Choose --last between 1 and 250.")


def _save_rows(vault: Path, folders: Sequence[str], rows: list[dict]) -> str | None:
    if _listings().resolve().is_relative_to(vault):
        raise api.ObsidianError("The row cache would be inside this vault. Use --json and read by path instead.",
                                "co obsidian notes --help")
    return _store_note_rows(context=_listing_context(vault, folders), note_paths=[row["path"] for row in rows])


# -- output ---------------------------------------------------------------

def _listing_note(token: str | None) -> None:
    if token:
        style.console().print(f"Listing: {token} (15 min; optional --listing ID pins these rows)")


def _render_notes(notes: list[dict], *, listing_token: str | None, ids: bool = False) -> None:
    out = style.console()
    out.print(f"{style.count(len(notes))} Obsidian notes")
    for index, note in enumerate(notes, 1):
        reference = style.path(note["path"]) if ids else style.count(index)
        out.print(f"{reference}  {escape(note['title'])}  {style.path(note['path'])}  {style.muted(note['modified_at'])}")
    _listing_note(listing_token)


def _render_search(hits: list[dict], *, ids: bool = False) -> None:
    out = style.console()
    out.print(f"{style.count(len(hits))} Obsidian matches")
    for index, hit in enumerate(hits, 1):
        reference = style.path(hit["path"]) if ids else style.count(index)
        out.print(f"{reference}  {escape(hit['title'])}  {style.path(hit['path'])}  {style.muted(hit['modified_at'])}")
        out.print(f"  {style.muted(', '.join(hit['matched_fields']))}  {escape(hit['excerpt'])}")


@_reported
def handle_obsidian_notes(*, vault: str | None = None, folders: Sequence[str], last: int = 20,
                          ids: bool = False, json_output: bool = False) -> None:
    """List selected notes, newest first; JSON includes full records and never saves rows."""
    _limit(last)
    path, selected = _selection(vault, folders)
    notes = sorted(api.list_notes(path, folders=selected), key=lambda note: (-note["mtime_ns"], note["path"]))[:last]
    if json_output:
        _emit_json(notes)
        token = None
    else:
        token = _save_rows(path, selected, notes)
        _render_notes(notes, listing_token=token, ids=ids)
    ref = ("1" if token else shlex.quote(notes[0]["path"])) if notes else '"<note.md>"'
    command = _scope_command(f"read {ref}", path, selected)
    _tip(command + (f" --listing {token}" if token else ""), json_output)


@_reported
def handle_obsidian_read(ref: str, *, vault: str | None = None, folders: Sequence[str],
                         listing: str | None = None, json_output: bool = False) -> None:
    """Raw Markdown alone on stdout; the next command always goes to stderr."""
    path, selected = _selection(vault, folders)
    reference = _resolve_note_reference(ref, context=_listing_context(path, selected), listing=listing)
    note = api.read_note(path, reference, folders=selected)
    if json_output:
        _emit_json(note)
    else:
        # A binary stream also preserves CRLF when stdout is a Windows pipe.
        if hasattr(sys.stdout, "buffer"):
            sys.stdout.buffer.write(note["content"].encode("utf-8"))
            sys.stdout.buffer.flush()
        else:
            sys.stdout.write(note["content"])
    _tip(_scope_command('search "<query>"', path, selected), True)


@_reported
def handle_obsidian_search(query: str, *, vault: str | None = None, folders: Sequence[str], last: int = 20,
                           ids: bool = False, json_output: bool = False) -> None:
    """Search the same explicit scope; displayed hits become the next notes row list."""
    _limit(last)
    path, selected = _selection(vault, folders)
    hits = api.search_notes(path, query, folders=selected)[:last]
    if json_output:
        _emit_json(hits)
        token = None
    else:
        token = _save_rows(path, selected, hits)
        _render_search(hits, ids=ids)
        _listing_note(token)
    ref = ("1" if token else shlex.quote(hits[0]["path"])) if hits else '"<note.md>"'
    command = _scope_command(f"read {ref}", path, selected)
    _tip(command + (f" --listing {token}" if token else ""), json_output)
