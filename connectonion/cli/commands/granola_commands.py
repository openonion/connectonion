"""
Purpose: `co granola` — read personal Granola meeting summaries and serve the REM CLI JSON contract (#3249)
LLM-Note:
  Dependencies: imports from [datetime, functools, json, typer, rich.markup, cli/style.py, cli/typer_groups.py, command_tips.py, useful_tools/granola.py] | imported by [cli/main.py] | tested by [tests/unit/test_granola_commands.py]
  Data flow: argv -> typer leaf -> GranolaClient reads live from Granola API v1 -> human rows/Markdown or --json -> one Next: command
  State/Effects: strictly read-only; zero local state or REM subscriptions.json coupling
  Integration: granola_app is registered on root app in cli/main.py; each subcommand is HANDLER in command_tips.NEXT
  Errors: invalid CLI flags/IDs -> exit 2 on stderr; GranolaError (auth/scope/network/rate-limit) -> exit 1 on stderr with Next: recovery command
"""

from datetime import datetime, timezone
from functools import wraps
import json
from typing import Optional

import typer
from rich.markup import escape

from .. import style
from ..typer_groups import _OneSuggestion
from ...useful_tools import granola as api
from .command_tips import mark_next_step_named, print_tip, selected_tip

granola_app = typer.Typer(
    cls=_OneSuggestion,
    invoke_without_command=True,
    help="Personal Granola meeting summaries from the terminal: check the connection, list personal folders, "
         "browse notes, and read changes or one note live as Markdown or JSON. Read-only: nothing in Granola "
         "or on disk changes. Shared-space folders, private scratchpads, transcripts and attendee emails are "
         "never read or returned.",
    epilog="Example:  co granola folders  |  "
           "Setup:  co env set GRANOLA_API_KEY grn_... --secret  ***  co granola check  |  "
           "REM source:  co granola changes --since 2026-11-20T00:00:00Z --folder <id> --json",
)

FOLDER_HELP = "Personal folder ID from co granola folders"
CHILDREN_HELP = "Also include personal child folders under this folder"
JSON_HELP = "Print structured JSON on stdout and send Next: to stderr"


@granola_app.callback()
def _granola(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())


def _tip(command: str, as_json: bool = False) -> None:
    if not as_json:
        print_tip(f"Next: {command}")
        return
    style.console(stderr=True).print(style.next_line(selected_tip(command)))
    mark_next_step_named()


def _dump(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _reported(handler):
    """Turn GranolaError into a clean stderr diagnostic + Next: line; invalid arguments exit 2, runtime errors exit 1."""
    @wraps(handler)
    def run(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except api.GranolaError as error:
            out = style.console(stderr=True)
            out.print(f"{style.error('✗')} {escape(str(error))}")
            out.print(style.next_line(selected_tip(error.next_step)))
            mark_next_step_named()
            raise typer.Exit(2 if error.kind == "invalid" else 1) from None
    return run


@granola_app.command("check", epilog="Example:  co granola check  |  co granola check --folder fld_example --json")
@_reported
def check(
    folder: Optional[str] = typer.Option(None, "--folder", help="Also verify this personal folder ID"),
    include_children: bool = typer.Option(False, "--include-children", help=CHILDREN_HELP),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
):
    """Check GRANOLA_API_KEY, personal folder count, and optionally one folder's personal scope. Read-only."""
    client = api.GranolaClient()
    status = client.check()
    checked_folder = None
    if folder is not None:
        checked_folder = client.resolve_personal_folder(folder, include_children=include_children)
        status["folder"] = {
            "id": checked_folder["folder_id"],
            "name": checked_folder["name"],
            "include_children": include_children,
            "folder_count": len(checked_folder["allowed_ids"]),
        }

    next_cmd = f"co granola notes {checked_folder['folder_id']}" if checked_folder else "co granola folders"
    if include_children and checked_folder:
        next_cmd += " --include-children"

    if as_json:
        _dump(status)
        return _tip(next_cmd, as_json=True)

    out = style.console()
    count = status["personal_folders"]
    noun = "folder" if count == 1 else "folders"
    shared_note = f" ({status['shared_skipped']} shared skipped)" if status["shared_skipped"] else ""
    out.print(
        f"{style.ok('✓')} Connected with {escape(status['credential_label'])}: "
        f"{count} personal {noun}{escape(shared_note)}"
    )
    if checked_folder:
        out.print(f"{style.ok('✓')} Personal folder ready: {escape(checked_folder['name'])} ({escape(checked_folder['folder_id'])})")
    _tip(next_cmd)


@granola_app.command("folders", epilog="Example:  co granola folders  |  co granola folders --json")
@_reported
def folders(as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List personal Granola folders (shared spaces are skipped). Read-only."""
    client = api.GranolaClient()
    listing = client.list_folders()
    rows = listing["personal"]
    first = rows[0] if rows else None
    next_cmd = (
        f"co granola notes {first['id']}" + (" --include-children" if first["child_count"] else "")
        if first
        else "co granola check"
    )

    if as_json:
        _dump({"folders": rows, "shared_skipped": listing["shared_count"]})
        return _tip(next_cmd, as_json=True)

    out = style.console()
    if not rows:
        out.print("No personal Granola folders found.")
    for r in rows:
        sub = f"  ({r['child_count']} child folders; pass --include-children)" if r["child_count"] else ""
        out.print(f"{style.command(r['id'])}  {escape(r['name'])}{style.muted(sub)}")
    if listing["shared_count"]:
        out.print(style.muted(f"Skipped {listing['shared_count']} shared-space folder(s)."))
    _tip(next_cmd)


@granola_app.command("notes", epilog="Example:  co granola notes fld_example  |  co granola notes fld_example --limit 10 --json")
@_reported
def notes(
    folder: str = typer.Argument(..., help=FOLDER_HELP),
    include_children: bool = typer.Option(False, "--include-children", help=CHILDREN_HELP),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=api.MAX_SELECTED, help="At most this many notes, newest update first"),
    since: Optional[str] = typer.Option(None, "--since", help="Only notes updated after this ISO-8601 timestamp with timezone"),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
):
    """List meeting notes in one personal Granola folder, newest update first. Read-only."""
    iso_since = None
    if since is not None:
        iso_since = api.parse_iso_utc(since, flag_name="--since").isoformat().replace("+00:00", "Z")

    client = api.GranolaClient()
    raw_notes = client.list_notes(folder, include_children=include_children, limit=limit, updated_after=iso_since)
    items = [
        {
            "id": n["id"],
            "time": n.get("updated_at") or n.get("created_at") or "",
            "title": api.redact_text(n.get("title") or "(untitled)"),
            "link": api.clean_link(n.get("web_url")),
        }
        for n in raw_notes
    ]

    scope_flags = f" --folder {folder}" + (" --include-children" if include_children else "")
    next_cmd = f"co granola show {items[0]['id']}{scope_flags}" if items else "co granola folders"

    if as_json:
        _dump({"folder_id": folder, "include_children": include_children, "notes": items})
        return _tip(next_cmd, as_json=True)

    out = style.console()
    if not items:
        out.print(f"No notes found in {escape(folder)}.")
    for item in items:
        day = item["time"][:10] if item["time"] else ""
        out.print(f"{style.command(item['id'])}  {style.muted(day)}  {escape(item['title'])}")
    _tip(next_cmd)


@granola_app.command(
    "changes",
    epilog="Example:  co granola changes --since 2026-11-20T00:00:00Z --folder fld_example --json",
)
@_reported
def changes(
    since: str = typer.Option(..., "--since", help="ISO-8601 timestamp with timezone; list notes updated after this instant"),
    folder: str = typer.Option(..., "--folder", help=FOLDER_HELP),
    include_children: bool = typer.Option(False, "--include-children", help=CHILDREN_HELP),
    as_json: bool = typer.Option(False, "--json", help="Print since, until and items as JSON; send Next: to stderr"),
):
    """List notes updated in a personal folder since --since, oldest update first. Read-only.

    Captures `until` before starting the read so the caller can pass `until` as
    the next `--since` without missing concurrent updates. Deleted notes and
    shared-space folders are excluded.
    """
    since_dt = api.parse_iso_utc(since, flag_name="--since")
    until_dt = datetime.now(timezone.utc)

    client = api.GranolaClient()
    items = client.list_changes(since=since_dt, folder_id=folder, include_children=include_children)

    since_iso = since_dt.isoformat().replace("+00:00", "Z")
    until_iso = until_dt.isoformat().replace("+00:00", "Z")
    scope_flags = f" --folder {folder}" + (" --include-children" if include_children else "")
    next_cmd = (
        f"co granola show {items[0]['id']}{scope_flags}"
        if items
        else f"co granola changes --since {until_iso}{scope_flags}"
    )

    if as_json:
        _dump({"since": since_iso, "until": until_iso, "items": items})
        return _tip(next_cmd, as_json=True)

    out = style.console()
    if not items:
        out.print(f"No changes since {since_iso}.")
    for item in items:
        out.print(f"{style.command(item['id'])}  {style.muted(item['time'][:19])}  {escape(item['title'])}")
    _tip(next_cmd)


@granola_app.command(
    "show",
    epilog="Example:  co granola show not_example --folder fld_example  |  co granola show not_example --folder fld_example --json",
)
@_reported
def show(
    note_id: str = typer.Argument(..., help="Note ID from co granola changes or notes (granola:<id> prefix also accepted)"),
    folder: Optional[str] = typer.Option(None, "--folder", help="Verify the note belongs to this personal folder"),
    include_children: bool = typer.Option(False, "--include-children", help=CHILDREN_HELP),
    as_json: bool = typer.Option(False, "--json", help="Print id, version, time, meeting_time, title, text, author and link as JSON"),
):
    """Read one personal Granola meeting summary live. Read-only."""
    client = api.GranolaClient()
    note = client.get_note(note_id, folder_id=folder, include_children=include_children)

    next_folder = folder or note.get("folder_id")
    next_cmd = f"co granola notes {next_folder}" if next_folder else "co granola folders"
    if include_children and folder:
        next_cmd += " --include-children"

    if as_json:
        _dump(note)
        return _tip(next_cmd, as_json=True)

    out = style.console()
    out.print(f"# {escape(note['title'])}")
    meta = [f"id: {note['id']}"]
    if note.get("meeting_time"):
        meta.append(f"meeting: {note['meeting_time']}")
    if note.get("time"):
        meta.append(f"updated: {note['time']}")
    if note.get("link"):
        meta.append(note["link"])
    out.print(style.muted("  ·  ".join(meta)))
    if note["text"]:
        print()
        print(note["text"])
    _tip(next_cmd)
