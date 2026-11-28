"""
Purpose: `co onenote changes` and `co onenote show` — the REM CLI JSON source contract (DD-081, #3249) for OneNote
LLM-Note:
  Dependencies: imports from [datetime, functools, json, typer, rich.markup, cli/style.py, command_tips.py, useful_tools/onenote.py (lazily)] | imported by [cli/main.py] | tested by [tests/unit/test_onenote_source_commands.py]
  Data flow: argv -> typer leaf -> OneNote() over Microsoft Graph -> section_changes / page_source -> human rows or --json -> one Next: command
  State/Effects: strictly read-only; scope arrives as --section; never reads REM state such as .state/subscriptions.json
  Integration: add_source_commands(onenote_app) registers both leaves on the existing onenote_app (cli/main.py); each is HANDLER in command_tips.NEXT
  Errors: invalid flags or IDs -> exit 2 on stderr; sign-in, scope, Graph and paging failures -> exit 1 on stderr with Next:; stdout never carries partial JSON
"""

from datetime import datetime, timezone
from functools import wraps
import json
import shlex
from typing import Optional

import typer
from rich.markup import escape

from .. import style
from .command_tips import mark_next_step_named, print_tip, selected_tip

SECTION_HELP = "Section ID from co onenote ls --ids (an exact unique section name also works)"


def _api():
    """Import useful_tools.onenote lazily so starting `co` never loads useful_tools/__init__.py or httpx."""
    from ...useful_tools import onenote
    return onenote


def _tip(command: str, as_json: bool) -> None:
    if not as_json:
        print_tip(f"Next: {command}")
        return
    style.console(stderr=True).print(style.next_line(selected_tip(command)))
    mark_next_step_named()


def _fail(message: str, next_step: str, code: int) -> None:
    out = style.console(stderr=True)
    out.print(f"{style.error('✗')} {escape(message)}")
    out.print(style.next_line(selected_tip(next_step)))
    mark_next_step_named()
    raise typer.Exit(code)


def _reported(handler):
    """Every failure becomes one stderr diagnostic and one Next: line. Invalid input exits 2, the rest 1."""
    @wraps(handler)
    def run(*args, **kwargs):
        import httpx
        from ...provider_credentials import ProviderCredentialError
        api = _api()
        try:
            return handler(*args, **kwargs)
        except api.OneNoteSourceError as error:
            _fail(str(error), error.next_step, 2 if error.kind == "invalid" else 1)
        except ProviderCredentialError as error:
            _fail(str(error).split("\nNext:")[0], error.next_command, 1)
        except httpx.RequestError:
            _fail("Could not reach Microsoft OneNote. Check your connection and try again.", "co onenote ls", 1)
        except ValueError as error:
            message, _, hint = str(error).strip().partition("\n")
            _fail(message, "co auth microsoft" if "co auth microsoft" in hint + message else "co onenote ls", 1)
    return run


def add_source_commands(onenote_app: typer.Typer) -> None:
    """Register changes and show on the co onenote group defined in cli/main.py."""

    @onenote_app.command(
        "changes",
        epilog="Example:  co onenote changes --since 2026-11-20T00:00:00Z --section 1-example --json",
    )
    @_reported
    def changes(
        since: str = typer.Option(..., "--since", help="ISO-8601 time with timezone; list pages modified after it"),
        section: str = typer.Option(..., "--section", help=SECTION_HELP),
        as_json: bool = typer.Option(False, "--json", help="Print since, until and items as JSON; send Next: to stderr"),
    ):
        """List pages in one section modified since --since, oldest first. Metadata only. Read-only.

        `until` is taken before the read starts, so passing it as the next --since
        misses no page edited during the read.
        """
        api = _api()
        since_dt = api.parse_since(since)
        until_dt = datetime.now(timezone.utc)
        items = api.section_changes(api.OneNote(), section, since_dt)

        since_iso, until_iso = (moment.isoformat().replace("+00:00", "Z") for moment in (since_dt, until_dt))
        scope = shlex.quote(section)
        next_cmd = (f"co onenote show {items[0]['id']} --section {scope}" if items
                    else f"co onenote changes --since {until_iso} --section {scope}")
        if as_json:
            print(json.dumps({"since": since_iso, "until": until_iso, "items": items}, indent=2, ensure_ascii=False))
            return _tip(next_cmd, as_json=True)

        out = style.console()
        if not items:
            out.print(f"No pages changed since {since_iso}.")
        for item in items:
            out.print(f"{style.command(item['id'])}  {style.muted(item['time'][:19])}  {escape(item['title'])}")
        _tip(next_cmd, as_json=False)

    @onenote_app.command(
        "show",
        epilog="Example:  co onenote show 0-example --section 1-example --json",
    )
    @_reported
    def show(
        page_id: str = typer.Argument(..., help="Page ID from co onenote changes (onenote:<id> also accepted)"),
        section: Optional[str] = typer.Option(None, "--section", help="Refuse the page unless it is filed in this section"),
        as_json: bool = typer.Option(False, "--json", help="Print id, version, time, title, text, author and link as JSON"),
    ):
        """Read one OneNote page live as text, with its version and link. Read-only."""
        api = _api()
        page = api.page_source(api.OneNote(), page_id, section)
        next_cmd = f"co onenote pages {page['section_id']} --ids" if page.get("section_id") else "co onenote ls"
        if as_json:
            print(json.dumps(page, indent=2, ensure_ascii=False))
            return _tip(next_cmd, as_json=True)

        out = style.console()
        out.print(f"# {escape(page['title'])}")
        meta = [f"id: {page['id']}", f"modified: {page['time']}"] + ([page["link"]] if page.get("link") else [])
        out.print(style.muted("  ·  ".join(meta)))
        if page["text"]:
            print()
            print(page["text"])
        _tip(next_cmd, as_json=False)
