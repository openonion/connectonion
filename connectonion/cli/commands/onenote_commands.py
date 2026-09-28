"""
Purpose: `co onenote` — list, read and create OneNote pages from the terminal (#1887)
LLM-Note:
  Dependencies: imports from [sys, rich, useful_tools/onenote.OneNote, gmail_listings, command_tips.print_tip] | imported by [cli/main.py] | tested by [tests/unit/test_onenote.py]
  Data flow: ls and pages save short-lived account-bound section/page ID lists → pages/read resolve displayed row numbers, while names and IDs still work → each handler builds OneNote(), prints the result and names the next command
  State/Effects: list commands save ID-only row maps under ~/.co; create writes one new page, confirming a bare number's target; other verbs only read OneNote
  Errors: ValueError, credential and HTTP transport errors print a short recovery hint, exit 1; a failed create never suggests blind retry because the page may already exist
"""

import os
import re
import shlex
import sys
import tempfile
from typing import Optional

import httpx
import typer
from rich.console import Console

from .command_tips import print_tip
from .gmail_listings import resolve_reference, save_listing
from ...environment import global_config_dir

errors = Console(stderr=True)
LISTINGS = global_config_dir() / "onenote-listings"


def _account(note) -> str:
    """Bind row numbers to the selected Microsoft account, as mail listings are."""
    email = note._graph._credentials.get("EMAIL") or ""
    if email:
        return email
    identity = note._json("/me?$select=id").get("id")
    if not identity:
        raise ValueError("Cannot identify this Microsoft account. Run: co auth microsoft")
    return f"microsoft:{identity}"


def _store_rows(note, family: str, ids: list[str]) -> str:
    token = save_listing(LISTINGS, _account(note), family, ids, provider="onenote")
    pointer = LISTINGS / f"last-{family}"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=LISTINGS,
                                         prefix=f".last-{family}-", delete=False) as stream:
            temporary = stream.name
            stream.write(token)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, pointer)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return token


def _resolve_row(note, value: str, family: str, listing: str | None) -> str:
    if not re.fullmatch(r"#?[0-9]{1,4}", value):
        return value
    if listing is None:
        try:
            with open(LISTINGS / f"last-{family}", "rb") as stream:
                listing = stream.read(65).decode("ascii")
        except (OSError, UnicodeError):
            raise ValueError(f"No recent OneNote {family} list. Run: co onenote "
                             f"{'ls' if family == 'sections' else 'pages'}") from None
    return resolve_reference(LISTINGS, value, _account(note), family,
                             listing, provider="onenote")


def _line(value: str) -> str:
    return " ".join(str(value).split())


def _listing_note(token: str) -> str:
    return f"Listing: {token} (15 min; optional --listing ID pins these rows)"


def _listed_notebooks(note, show_ids: bool = False) -> tuple[str, str]:
    notebooks = note.notebook_items()
    ids, lines = [], []
    for notebook in notebooks:
        lines.append(_line(notebook.get("displayName") or "(untitled notebook)"))
        for section in notebook.get("sections") or []:
            ids.append(section["id"])
            line = f"  {len(ids)}. {_line(section.get('displayName') or '(untitled section)')}"
            if show_ids:
                line += f"  (section {section['id']})"
            lines.append(line)
    token = _store_rows(note, "sections", ids)
    lines.append(_listing_note(token))
    if not notebooks:
        return "No OneNote notebooks found.\n" + _listing_note(token), "Next: co onenote pages"
    return "\n".join(lines), "Next: co onenote pages 1" if ids else "Next: co onenote pages"


def _listed_pages(note, section: str | None, limit: int,
                  listing: str | None, show_ids: bool = False) -> tuple[str, str]:
    selected = _resolve_row(note, section, "sections", listing) if section else None
    pages = note.page_items(selected, max_results=limit)
    ids = [page["id"] for page in pages]
    token = _store_rows(note, "pages", ids)
    lines = []
    for i, page in enumerate(pages, 1):
        date = (page.get("lastModifiedDateTime") or "")[:10]
        line = f"{i}. {_line(page.get('title') or '(untitled)')}"
        if date:
            line += f"  ({date})"
        if show_ids:
            line += f"  (page {page['id']})"
        lines.append(line)
    lines.append(_listing_note(token))
    if not pages:
        return "No OneNote pages found.\n" + _listing_note(token), "Next: co onenote ls"
    return "\n".join(lines), "Next: co onenote read 1"


def _onenote():
    from ...useful_tools.onenote import OneNote
    return OneNote()


def _run(call, next_command: str, retry_command: str, *, write: bool = False,
         lookup_command: str = "co onenote ls") -> None:
    from ...provider_credentials import ProviderCredentialError
    try:
        output = call(_onenote())
        if isinstance(output, tuple):
            output, next_command = output
        print(output)
    except httpx.TimeoutException:
        if write:
            errors.print("OneNote timed out after the create request. The page may exist; check its section before creating it again.",
                         style="red", markup=False)
        else:
            errors.print(f"Microsoft OneNote took too long to respond. Try again: {retry_command}",
                         style="red", markup=False)
        sys.exit(1)
    except httpx.RequestError:
        if write:
            errors.print("Could not confirm whether OneNote created the page. Check its section before creating it again.",
                         style="red", markup=False)
        else:
            errors.print(f"Could not reach Microsoft OneNote. Check your connection, then retry: {retry_command}",
                         style="red", markup=False)
        sys.exit(1)
    except OSError:
        errors.print(f"Could not save or read the OneNote row list. Check ~/.co permissions. Next: {lookup_command}",
                     style="red", markup=False)
        sys.exit(1)
    except (ValueError, ProviderCredentialError) as exc:
        text = str(exc).strip()
        errors.print(text if "co " in text else f"{text} Next: {lookup_command}", style="red", markup=False)
        sys.exit(1)
    print_tip(next_command)


def handle_onenote_ls(*, show_ids: bool = False) -> None:
    _run(lambda n: _listed_notebooks(n, show_ids), "Next: co onenote pages", "co onenote ls")


def handle_onenote_pages(section: Optional[str] = None, limit: int = 20,
                         *, listing: str | None = None, show_ids: bool = False) -> None:
    retry = "co onenote pages" + (f" {shlex.quote(section)}" if section else "")
    if listing:
        retry += f" --listing {shlex.quote(listing)}"
    _run(lambda n: _listed_pages(n, section, limit, listing, show_ids),
         "Next: co onenote read 1", retry)


def handle_onenote_read(page: Optional[str] = None, *, listing: str | None = None) -> None:
    if page is None:
        handle_onenote_pages()
    else:
        retry = f"co onenote read {shlex.quote(page)}"
        if listing:
            retry += f" --listing {shlex.quote(listing)}"
        if re.fullmatch(r"#?[0-9]{1,4}", page):
            call = lambda n: n.read_page(_resolve_row(n, page, "pages", listing))
        elif re.match(r"^\d+-[^\s]+!", page):
            call = lambda n: n.read_page(page)
        else:
            call = lambda n: n.read_page_by_title(page)
        _run(call, "Next: co onenote pages", retry, lookup_command="co onenote pages")


def _can_confirm() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def handle_onenote_create(section: str, title: str, text: Optional[str] = None,
                          *, listing: str | None = None) -> None:
    body = text if text is not None else ("" if sys.stdin.isatty() else sys.stdin.read())

    def create(note):
        selected = _resolve_row(note, section, "sections", listing)
        if selected != section and listing is None:
            if not _can_confirm():
                raise ValueError("A numbered create needs an interactive terminal or --listing from co onenote ls.")
            found = note._section(selected)
            target = f"{found['notebook']} / {found['displayName']}"
            errors.print(f"Create '{title}' in {target}?", markup=False)
            try:
                confirmed = typer.confirm("Create this OneNote page?", default=False)
            except (typer.Abort, KeyboardInterrupt, EOFError):
                confirmed = False
            if not confirmed:
                errors.print("Not created. Next: co onenote ls", markup=False)
                raise typer.Exit(1)
        return note.create_page(selected, title, body), \
            f"Next: co onenote pages {shlex.quote(selected)}"

    _run(create, "Next: co onenote ls", f"co onenote pages {shlex.quote(section)}", write=True)
