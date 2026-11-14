"""
Purpose: `co asana` — check the Asana personal access token, list projects and tasks, read one task with its comments, and change a task's due day or completion or comment on it, from the terminal
LLM-Note:
  Dependencies: imports from [typer, rich.markup, cli/style.py, cli/typer_groups.py, command_tips.py, gmail_listings.py, environment.global_config_dir, useful_tools/asana.py] | imported by [cli/main.py] | tested by [tests/unit/test_asana_commands.py]
  Data flow: argv → typer leaf → Asana() reads ASANA_ACCESS_TOKEN → get_user("me") (the account and its workspaces) → check prints them; projects lists a workspace's projects; tasks resolves <project> (row number, gid or exact name) and lists its tasks → newest first, -n rows → numbered rows (or --json) → one Next line; task and stories take a row number from the last tasks list (or a task gid) → get_task + list_stories → the task and its comments, or every story → one Next line; update (--due-on, --done or --open) and comment take a task gid (or a row number with its --listing) → get_task → a preview of the change, or with --yes update_task/add_comment → the result → one Next line
  State/Effects: reads ASANA_ACCESS_TOKEN | projects and tasks save the shown rows' gids under ~/.co/asana-listings (15 min, bound to the Asana account, ids only) unless --json | only update --yes and comment --yes change Asana (as the token's owner); without --yes they preview and change nothing
  Integration: asana_app is added to the root app in main.py; every handler names its own next command, so the tip sweep in tests/unit/test_cli_tips_name_real_commands.py checks each one
  Errors: exit codes are documented in every --help page: 0 ok/preview/empty · 1 failure · 2 usage | AsanaError → `✗ <cause>` and `Next: <command>` on stderr, exit 1, a list that stops leading with `Read N <items>, incomplete` (N may be 0); Next follows a success on stdout, or on stderr under --json; a ValueError from an argument (bad date, unknown name, stale row number) → the same, exit 2 | a change whose result is unknown (sent, then no readable answer) exits 1 and names the read command that shows whether it was saved; it is never re-sent
"""

import json
import os
import re
import shlex
import sys
import tempfile
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Optional

import typer
from rich.markup import escape

from .. import style
from ..typer_groups import _OneSuggestion
from ...environment import global_config_dir, selected_command
from .command_tips import mark_next_step_named, print_tip, selected_tip
from .gmail_listings import ListingError, resolve_reference, save_listing

ROW = re.compile(r"#?[0-9]{1,4}")          # a row number, as OneNote reads one; longer digits are a gid
STATUSES = {"open": False, "done": True, "all": None}
JSON_HELP = "Print Asana's own records as JSON (IDs included); no row numbers are saved"
LAST_HELP = "At most this many, most recently modified first"
WORKSPACE_HELP = ('Workspace name or ID from co asana check, a name with spaces in quotes ("My Team"); '
                  "needed only when the account has several")


def _api():
    """The Asana tool module, imported on first use so `co` starts without loading every tool."""
    from ...useful_tools import asana
    return asana


class UsageError(ValueError):
    """A wrong argument, with the command that shows the right one; exit 2."""

    def __init__(self, message: str, next_step: str):
        super().__init__(message)
        self.next_step = next_step

asana_app = typer.Typer(
    cls=_OneSuggestion,
    invoke_without_command=True,
    help="Asana from the terminal with a personal access token. Bare 'co asana' runs check: who it acts as and "
         "their workspaces (Read-only). Reads are Read-only; update and comment only preview until --yes.\n\n"
         "Exit 0 on success (a preview or an empty list too), 1 on a failure from Asana, the token or the "
         "network, 2 on a wrong argument. Results go to stdout and errors to stderr; with --json the suggested "
         "next command also goes to stderr. A list that stops part way prints nothing and says "
         "Read N items, incomplete.",
    epilog="Example:  co asana check  |  co asana tasks 1  |  co asana task 1  |  "
           "Setup:  co auth asana  (or co env set ASANA_ACCESS_TOKEN <pat> --secret)  →  co asana check",
)


@asana_app.callback()
def _asana(ctx: typer.Context):
    # Bare `co asana` shows content, as bare `co gmail` shows the inbox: here the account
    # and its workspaces, the same as `co asana check`, with its Next line. --help keeps the help.
    if ctx.invoked_subcommand is None:
        check()


def _reported(handler):
    """An AsanaError becomes its cause and the one command to run next, on stderr; exit 1 (exit 2 for a bad argument)."""
    @wraps(handler)
    def run(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except (_api().AsanaError, ValueError) as error:
            out = style.console(stderr=True)
            out.print(f"{style.error('✗')} {escape(str(error))}")
            next_step = getattr(error, "next_step", "co asana --help")
            out.print(style.next_line(selected_tip(next_step)))
            mark_next_step_named()
            raise typer.Exit(1 if isinstance(error, _api().AsanaError) else 2) from None
    return run


# -- the token -------------------------------------------------------------

@asana_app.command("check", epilog="Example:  co asana check")
@_reported
def check():
    """Show which Asana account co uses, and that account's workspaces with their IDs. Read-only.

    If Asana is not connected yet, or the saved token stopped working, it
    exits 1 and tells you to run co auth asana.

    Exit 0 on success, 1 on a failure from the token, Asana or the network,
    2 on a wrong argument. Errors go to stderr.
    """
    me = _api().Asana().get_user()
    workspaces = me.get("workspaces") or []
    # Every line is drawn before any is printed, so nothing says ✓ unless all of it can be shown.
    lines = [f"{style.ok('✓')} Asana: acting as {escape(me.get('name') or '(no name)')} "
             f"<{escape(me.get('email') or 'no email')}>"]
    lines += [f"  Workspace: {escape(w.get('name') or '(untitled)')}  {style.muted(w['gid'])}" for w in workspaces]
    if not workspaces:
        lines.append("  No workspaces: this account belongs to none yet. Join one in Asana, then check again.")
    out = style.console()
    for line in lines:
        out.print(line)
    if not workspaces:
        print_tip("Next: co asana check")
    elif len(workspaces) == 1:
        print_tip("Next: co asana projects")
    else:
        # Several workspaces: the reader picks one from the list above; the tip does not pick for them.
        print_tip('Next: co asana projects --workspace "<workspace>"')


# -- row numbers -----------------------------------------------------------

def _listings() -> Path:
    return global_config_dir() / "asana-listings"


def _account(me: dict) -> str:
    """Row numbers belong to one Asana account, as Gmail's and OneNote's do."""
    return f"asana:{me['gid']}"


def _store_rows(me: dict, family: str, gids: list[str]) -> Optional[str]:
    """Save the shown rows' gids and point last-<family> at them; returns the listing token.

    An empty list saves nothing and removes last-<family>, so an old row number
    is refused as "no recent list" instead of reaching rows that are no longer shown.
    """
    try:
        if not gids:
            (_listings() / f"last-{family}").unlink(missing_ok=True)
            return None
        token = save_listing(_listings(), _account(me), family, gids, provider="asana")
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=_listings(),
                                         prefix=f".last-{family}-", delete=False) as stream:
            stream.write(token)
        os.replace(stream.name, _listings() / f"last-{family}")
    except OSError:
        raise _api().AsanaError("Could not save the row numbers under ~/.co/asana-listings. "
                             "Check write access there, or use gids from --json", "co asana check") from None
    return token


def _resolve_row(me: dict, value: str, family: str, listing: Optional[str], relist: str) -> str:
    """The gid behind a row number: from --listing, else from this computer's last <family> list."""
    if listing is None:
        try:
            listing = (_listings() / f"last-{family}").read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            raise UsageError(f"No recent Asana {family} list to take row {value} from", relist) from None
    try:
        return resolve_reference(_listings(), value, _account(me), family, listing, provider="asana")
    except ListingError as error:
        raise UsageError(str(error), relist) from None


def _listing_note(token: Optional[str]) -> list[str]:
    return [f"Listing: {token} (15 min; optional --listing ID pins these rows)"] if token else []


# -- arguments -------------------------------------------------------------

def _same_name(kind: str, given: str, found: list[dict], details=lambda record: []) -> str:
    """A refusal naming every match, one per line, as `co rem` lists the pages a name matched.

    The first line is OneNote's wording; each row is laid out as `co asana check` and
    `projects` show one (name, what tells it apart, gid). No row numbers: they would read
    as listing rows that `tasks 1` could take.
    """
    rows = ["  " + "  ".join([record.get("name") or "(untitled)", *details(record), record["gid"]])
            for record in found]
    return "\n".join([f"Several {kind}s are named {given!r}. Pass the {kind} gid instead:", *rows])


def _workspace(me: Optional[dict], given: Optional[str],
               retry: str = "co asana projects --workspace <workspace-gid>") -> dict:
    """The workspace named or given by gid; the only one when none is named. A gid needs no account read.

    retry is the command a same-named refusal suggests, with the gid in place of the name.
    """
    if me is None:
        return {"gid": given}
    workspaces = me.get("workspaces") or []
    if given is None:
        if len(workspaces) == 1:
            return workspaces[0]
        if not workspaces:
            raise _api().AsanaError("This Asana account belongs to no workspace yet", "co asana check")
        raise UsageError('This account has several workspaces; name one with --workspace "<name>" '
                         "(quotes around a name with spaces)", "co asana check")
    found = [w for w in workspaces if given in (w["gid"], w.get("name"))]
    if len(found) == 1:
        return found[0]
    if not found:
        raise UsageError(f"No workspace {given!r} for this account", "co asana check")
    raise UsageError(_same_name("workspace", given, found), retry)


def _project(client, me: Optional[dict], given: str, workspace: Optional[str], listing: Optional[str]) -> tuple[str, Optional[str]]:
    """(gid, name or None) for a row number, a gid, or an exact project name in the workspace."""
    if ROW.fullmatch(given):
        return _resolve_row(me, given, "projects", listing, "co asana projects"), None
    if given.isdigit():
        return given, None
    space = _workspace(me, workspace, f"co asana tasks {_arg(given)} --workspace <workspace-gid>")
    named = [p for p in client.list_projects(space["gid"]) if p.get("name") == given]
    # An active project wins over an archived one of the same name, as `co asana projects`
    # lists active ones; an archived project is still found by name when it is the only match.
    found = [p for p in named if not p.get("archived")] or named
    if len(found) == 1:
        return found[0]["gid"], found[0]["name"]
    if not found:
        raise UsageError(f"No project named {given!r} in {space.get('name') or space['gid']}", "co asana projects")
    raise UsageError(_same_name("project", given, found, _project_details), "co asana tasks <project-gid>")


def _project_details(project: dict) -> list[str]:
    """What tells same-named projects apart besides the gid, in the order `projects` shows it."""
    return [(project.get("team") or {}).get("name") or "no team", *(["archived"] if project.get("archived") else [])]


def _day(value: Optional[str], flag: str, help_command: str = "co asana tasks --help") -> Optional[date]:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise UsageError(f"{flag} takes a date like 2026-10-16, not {value!r}", help_command) from None


def _moment(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise UsageError(f"--modified-since takes a time with its zone, like 2026-10-01T09:00+11:00, not {value!r}",
                         "co asana tasks --help") from None


def _check_assignee(value: Optional[str]) -> None:
    """--assignee is checked before anything is sent: me, a user gid, or an email address."""
    if value is None or value == "me" or value.isdigit() or _api().is_email(value):
        return
    raise UsageError(f"--assignee takes me, an email address or a user gid, not {value!r}", "co asana tasks --help")


def _assignee(client, me: Optional[dict], value: Optional[str]) -> Optional[str]:
    """The gid --assignee names; an email is looked up in Asana."""
    if value is None or value.isdigit():
        return value
    return me["gid"] if value == "me" else client.get_user(value)["gid"]


def _status(value: str) -> Optional[bool]:
    if value not in STATUSES:
        raise UsageError(f"--status takes open, done or all, not {value!r}", "co asana tasks --help")
    return STATUSES[value]


# -- output ----------------------------------------------------------------

def _newest(records: list[dict], last: int) -> list[dict]:
    return sorted(records, key=lambda r: r.get("modified_at") or "", reverse=True)[:last]


def _tip(command: str, as_json: bool) -> None:
    """The Next line: stdout for people, stderr under --json so stdout stays parseable."""
    # Select the outer command only; quoted comment text is data, not another tip.
    style.console(stderr=as_json).print(style.next_line(selected_command(command)), emoji=False)
    mark_next_step_named()


def _literal_tip(line: str, as_json: bool) -> None:
    """A Next line printed exactly as given, for one that carries the user's own text.

    print_tip drops [red]-style tags and selected_tip rewrites every "co " in the
    line, both of which would change a comment's text. The caller applies
    selected_tip to the command words only; this prints the rest untouched.
    """
    mark_next_step_named()
    out = style.console(stderr=as_json)
    if out.is_terminal:
        out.print(f"[co.next]Next:[/co.next] {style.command(line)}", emoji=False, highlight=False, soft_wrap=True)
    else:
        print(f"Next: {line}", file=out.file, flush=True)


def _print(lines: list[str]) -> None:
    out = style.console()
    for line in lines:
        out.print(line)


def _arg(value: str) -> str:
    """An argument as a Next line can be pasted: a row number without its #, which a shell reads as a
    comment, and a name with spaces or other shell characters quoted."""
    return value.lstrip("#") if ROW.fullmatch(value) else shlex.quote(value)


NAME_CELLS = 16     # widest a person or team column gets; longer ones end in "…"


def _fit(text: str, limit: int = NAME_CELLS) -> str:
    """At most `limit` terminal cells, so one long assignee or team does not push every name off an 80-column line."""
    from rich.cells import cell_len
    if cell_len(text) <= limit:
        return text
    out = ""
    for ch in text:
        if cell_len(out + ch) > limit - 1:
            break
        out += ch
    return out + "…"


def _aligned(cells: list[list[tuple]], names: list[str]) -> list[str]:
    """Rows as `co linear issues` draws them: short fields padded into columns, the name last.

    Each cell is (text, style or None). Widths are terminal cells, not characters,
    so a Chinese assignee or an emoji keeps the next column in line; the name goes
    last because its length varies most. The row number stays at the very start of
    the line (`1.` then padding, never a leading space), as before; it is what a
    reader passes to `co asana task`. Scripts read `--json`, whose shape is unchanged.
    """
    from rich.cells import cell_len
    widths = [max((cell_len(row[i][0]) for row in cells), default=0) for i in range(len(cells[0]))] if cells else []
    lines = []
    for row, name in zip(cells, names):
        parts = []
        for (text, paint), width in zip(row, widths):
            padded = text + " " * (width - cell_len(text))
            parts.append(paint(padded) if paint else escape(padded))   # style.* escapes itself
        lines.append("  ".join(parts) + "  " + escape(name))
    return lines


# -- projects and tasks ----------------------------------------------------

@asana_app.command("projects", epilog="Example:  co asana projects  |  co asana projects --workspace Acme -n 50 --json")
@_reported
def projects(workspace: Optional[str] = typer.Option(None, "--workspace", help=WORKSPACE_HELP),
             archived: bool = typer.Option(False, "--archived", help="Include archived projects"),
             last: int = typer.Option(20, "--last", "-n", min=1, max=250, help=LAST_HELP),
             ids: bool = typer.Option(False, "--ids", help="Also show each project's ID"),
             as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List a workspace's projects, most recently modified first, numbered for co asana tasks. Read-only.

    All of the workspace's projects are fetched before anything is shown,
    so the list is never cut short; archived ones are left out unless
    --archived is passed. Row numbers stay valid for 15 minutes.

    Exit 0 on success (an empty list too), 1 on a failure from Asana, the
    token or the network, 2 on a wrong argument. If reading stops part way,
    nothing is listed and the error says "Read N items, incomplete".
    Errors go to stderr.
    """
    client = _api().Asana()
    # The account is read only when something needs it: row numbers, or a workspace to find or name.
    direct = as_json and workspace is not None and workspace.isdigit()
    me = None if direct else client.get_user()
    space = _workspace(me, workspace)
    found = [p for p in client.list_projects(space["gid"]) if archived or not p.get("archived")]
    rows = _newest(found, last)
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return _tip("co asana tasks <project-gid>" if rows else "co asana check", True)
    token = _store_rows(me, "projects", [p["gid"] for p in rows])
    shown = f" (showing {len(rows)} of {len(found)})" if len(rows) < len(found) else ""
    lines = [f"{style.count(len(found))} {'project' if len(found) == 1 else 'projects'} in "
             f"{escape(space.get('name') or space['gid'])}{shown}"]
    teams = any((p.get("team") or {}).get("name") for p in rows)
    archived_any = any(p.get("archived") for p in rows)
    cells = []
    for i, p in enumerate(rows, 1):
        row = [(f"{i}.", None), ((p.get("modified_at") or "")[:10] or "-", None)]
        if teams:
            row.append((_fit((p.get("team") or {}).get("name") or "-"), None))
        if archived_any:
            row.append(("archived" if p.get("archived") else "", style.muted))
        if ids:
            row.append((p["gid"], style.muted))
        cells.append(row)
    lines += _aligned(cells, [p.get("name") or "(untitled)" for p in rows])
    _print(lines + _listing_note(token))
    _tip("co asana tasks 1" if rows else ("co asana projects --archived" if not archived else "co asana check"), False)


@asana_app.command("tasks", epilog='Example:  co asana tasks 1  |  co asana tasks "Website" --assignee me --due-to 2026-10-16')
@_reported
def tasks(project: str = typer.Argument(..., help="Row number from co asana projects, project ID, or exact project name"),
          workspace: Optional[str] = typer.Option(None, "--workspace", help=WORKSPACE_HELP + "; used to find a project by name"),
          assignee: Optional[str] = typer.Option(None, "--assignee", help="me, an email, or a user ID"),
          status: str = typer.Option("open", "--status", help="open (default), done or all"),
          due_from: Optional[str] = typer.Option(None, "--due-from", help="Due on or after this date, YYYY-MM-DD"),
          due_to: Optional[str] = typer.Option(None, "--due-to", help="Due on or before this date, YYYY-MM-DD"),
          modified_since: Optional[str] = typer.Option(None, "--modified-since", help="Changed since this time, with its zone"),
          last: int = typer.Option(20, "--last", "-n", min=1, max=250, help=LAST_HELP),
          listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID printed by co asana projects; keeps row numbers pointing at that list even after you list something else"),
          ids: bool = typer.Option(False, "--ids", help="Also show each task's ID"),
          as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List a project's tasks, most recently modified first, numbered for task, stories, update and comment. Read-only.

    Each row shows status, due day and assignee in columns, then the name;
    a past-due day is red, today yellow, and your own name bold. Open tasks only
    unless --status says otherwise. All of the project's tasks are fetched
    and filtered before anything is shown; a task with no due day is left
    out when --due-from or --due-to is given.

    Exit 0 on success (an empty list too), 1 on a failure from Asana, the
    token or the network, 2 on a wrong argument. If reading stops part way,
    nothing is listed and the error says "Read N items, incomplete".
    Errors go to stderr.
    """
    completed, start, end, since = _status(status), _day(due_from, "--due-from"), _day(due_to, "--due-to"), _moment(modified_since)
    _check_assignee(assignee)
    client = _api().Asana()
    # A project gid with --json needs no account: no row numbers to bind, no name to find, no "me".
    direct = as_json and project.isdigit() and not ROW.fullmatch(project) and assignee != "me"
    me = None if direct else client.get_user()
    gid, name = _project(client, me, project, workspace, listing)
    found = client.list_tasks(gid, assignee_gid=_assignee(client, me, assignee), completed=completed,
                              due_from=start, due_to=end, modified_since=since)
    rows = _newest(found, last)
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return _tip("co asana task <task-gid>" if rows else "co asana projects", True)
    token = _store_rows(me, "tasks", [t["gid"] for t in rows])
    _print(_task_lines(found, rows, name or _project_name(found, gid), status, ids, (me or {}).get("gid"))
           + _listing_note(token))
    _tip("co asana task 1" if rows else (f"co asana tasks {_arg(project)} --status all" if status != "all" else "co asana projects"), False)


def _project_name(found: list[dict], gid: str) -> str:
    """The project's name as its tasks carry it; its gid when there is no task to read it from."""
    for task in found:
        for p in task.get("projects") or []:
            if isinstance(p, dict) and p.get("gid") == gid and isinstance(p.get("name"), str):
                return p["name"]
    return gid


def _today() -> date:
    """Today on this machine, in the zone due days are read in; tests pin it."""
    return datetime.now(_api()._local_zone()).date()


def _due_paint(day, done: bool, today: date):
    """Red when an open task is past due, yellow when it is due today, dim when done or undated.

    The words stay (`due 2026-11-10`, `due -`), so nothing is lost without colour (NO_COLOR).
    """
    if done or day is None:
        return style.muted
    if day < today:
        return style.error
    if day == today:
        return style.warn
    return None


def _who_paint(assignee: dict, me_gid) -> object:
    """Bold for the token's own user, dim when nobody is assigned."""
    if not assignee.get("gid") and not assignee.get("name"):
        return style.muted
    return style.label if me_gid and assignee.get("gid") == me_gid else None


def _task_lines(found: list[dict], rows: list[dict], project: str, status: str, ids: bool,
                me_gid: str | None = None) -> list[str]:
    kind = "" if status == "all" else f"{status} "
    noun = "task" if len(found) == 1 else "tasks"
    shown = f" (showing {len(rows)} of {len(found)})" if len(rows) < len(found) else ""
    lines = [f"{style.count(len(found))} {kind}{noun} in {escape(project)}{shown}"]
    cells, today = [], _today()
    for i, t in enumerate(rows, 1):
        day = _api().due_day(t)                                   # the same day --due-from/--due-to compare
        done = bool(t.get("completed"))
        assignee = t.get("assignee") or {}
        row = [(f"{i}.", None), ("done" if done else "open", style.muted if done else None),
               (f"due {day.isoformat() if day else '-'}", _due_paint(day, done, today)),
               (_fit(assignee.get("name") or "-"), _who_paint(assignee, me_gid))]
        if ids:
            row.append((t["gid"], style.muted))
        cells.append(row)
    return lines + _aligned(cells, [t.get("name") or "(untitled)" for t in rows])


# -- one task --------------------------------------------------------------

REF_HELP = "Row number from co asana tasks, or a task ID"
RELIST = 'co asana tasks "<project>"'


def _task_ref(client, ref: str, listing: Optional[str]) -> str:
    """The task gid behind a row number from the last tasks list, or the gid given. A gid needs no account read."""
    if ROW.fullmatch(ref):
        return _resolve_row(client.get_user(), ref, "tasks", listing, RELIST)
    if ref.isdigit():
        return ref
    # No task names here: names repeat across projects, and the tasks list already numbers them.
    raise UsageError(f"Give a row number from co asana tasks or a task gid, not {ref!r}", RELIST)


def _ref_command(command: str, ref: str, listing: Optional[str]) -> str:
    """The next command on the same task: a row number keeps its --listing, so it still means the row just read."""
    pinned = f" --listing {listing}" if listing and ROW.fullmatch(ref) else ""
    return f"co asana {command} {_arg(ref)}{pinned}"


def _when(value) -> str:
    """An Asana time in this computer's zone, to the minute; '-' when there is none."""
    moment = _api().local_time(value)
    return moment.strftime("%Y-%m-%d %H:%M") if moment else "-"


def _oldest_first(found: list[dict]) -> list[dict]:
    """A sorted copy for people to read; --json keeps Asana's own order and the list itself is not touched."""
    return sorted(found, key=_api().story_time)


def _names(records) -> str:
    """Names of followers or projects; a gid stands in for a missing name."""
    named = [str(r.get("name") or r.get("gid") or "?") for r in records or [] if isinstance(r, dict)]
    return ", ".join(named) or "-"


def _author(story: dict) -> str:
    return (story.get("created_by") or {}).get("name") or "(Asana)"


def _story_line(story: dict, kind: bool) -> str:
    label = f"  {story.get('resource_subtype') or story['type']}" if kind else ""
    return (f"  {style.muted(_when(story.get('created_at')))} {escape(_author(story))}{escape(label)}: "
            f"{escape(story.get('text') or '(no text)')}")


@asana_app.command("task", epilog="Example:  co asana task 1  |  co asana task 1209876543210987 --json")
@_reported
def task(ref: str = typer.Argument(..., help=REF_HELP),
         listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID printed by co asana tasks; keeps row numbers pointing at that list even after you list something else"),
         as_json: bool = typer.Option(False, "--json", help='Print {"task": ..., "stories": [...]} as Asana returns them')):
    """Show one task: status, assignee, due day, followers, projects, fields, link, description and comments. Read-only.

    Reads the task and its stories from Asana with your token; changes
    nothing in Asana and writes no file. Only comments are shown here;
    co asana stories shows every change Asana recorded as well. --json
    keeps all stories.

    Exit 0 on success, 1 on a failure from Asana, the token or the network,
    2 on a wrong argument. If the stories stop part way, nothing is shown
    and the error says "Read N stories, incomplete". Errors go to stderr.
    """
    client = _api().Asana()
    gid = _task_ref(client, ref, listing)
    found, history = client.get_task(gid), client.list_stories(gid)
    if as_json:
        print(json.dumps({"task": found, "stories": history}, indent=2, ensure_ascii=False))
        return _tip(_ref_command("stories", ref, listing), True)
    _print(_detail_lines(found, [s for s in _oldest_first(history) if _api().is_comment(s)]))
    _tip(_ref_command("stories", ref, listing), False)


def _detail_lines(t: dict, comments: list[dict]) -> list[str]:
    """Every line of co asana task, drawn before any is printed."""
    day = _api().due_day(t)
    fields = "   ".join(f"{f.get('name') or f['gid']}: {f['display_value']}"
                       for f in t.get("custom_fields") or [] if f.get("display_value"))
    lines = [f"{style.heading(escape(t.get('name') or '(untitled)'))}  {style.muted(t['gid'])}",
             escape(f"Status: {'done' if t.get('completed') else 'open'}   "
                    f"Assignee: {(t.get('assignee') or {}).get('name') or '-'}   "
                    f"Due: {day.isoformat() if day else '-'}"),
             escape(f"Followers: {_names(t.get('followers'))}"),
             escape(f"Projects: {_names(t.get('projects'))}   Workspace: {(t.get('workspace') or {}).get('name') or '-'}"),
             escape(f"Fields: {fields or '-'}"),
             escape(f"Created: {_when(t.get('created_at'))}   Modified: {_when(t.get('modified_at'))}"
                    + (f"   Completed: {_when(t.get('completed_at'))}" if t.get("completed") else ""))]
    if t.get("permalink_url"):
        lines.append(style.path(escape(t["permalink_url"])))
    lines += ["", escape(t.get("notes") or "(no description)"), "", f"Comments ({style.count(len(comments))}):"]
    return lines + [_story_line(c, False) for c in comments]


@asana_app.command("stories", epilog="Example:  co asana stories 1  |  co asana stories 1209876543210987 --json")
@_reported
def stories(ref: str = typer.Argument(..., help=REF_HELP),
            listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID printed by co asana tasks; keeps row numbers pointing at that list even after you list something else"),
            as_json: bool = typer.Option(False, "--json", help="Print Asana's own story records as JSON")):
    """Show everything recorded on a task, oldest first: comments and Asana's own activity. Read-only.

    Each line is the time, who did it ((Asana) when no person did), the
    kind of story, and its text.

    Exit 0 on success (an empty list too), 1 on a failure from Asana, the
    token or the network, 2 on a wrong argument. If reading stops part way,
    nothing is listed and the error says "Read N items, incomplete".
    Errors go to stderr.
    """
    client = _api().Asana()
    gid = _task_ref(client, ref, listing)
    found = client.list_stories(gid)
    if as_json:
        print(json.dumps(found, indent=2, ensure_ascii=False))
        return _tip(_ref_command("task", ref, listing), True)
    target = next((s["target"]["name"] for s in found
                   if isinstance(s.get("target"), dict) and isinstance(s["target"].get("name"), str)), gid)
    lines = [f"{style.count(len(found))} {'story' if len(found) == 1 else 'stories'} on {escape(target)}"]
    _print(lines + [_story_line(s, True) for s in _oldest_first(found)])
    _tip(_ref_command("task", ref, listing), False)


# -- changes ------------------------------------------------

YES_HELP = "Do it; without --yes this prints a preview and changes nothing in Asana"
WRITE_REF_HELP = "Task ID, or a row number from co asana tasks with its --listing"


def _write_task_ref(client, ref: str, listing: Optional[str]) -> str:
    """The task a change goes to: a gid, or a row number pinned by --listing; never the implicit last list."""
    if ROW.fullmatch(ref) and listing is None:
        raise UsageError(f"Row {ref} needs the --listing it came from before anything is changed; "
                         "or give the task gid", RELIST)
    return _task_ref(client, ref, listing)


def _rerun(*words: str) -> str:
    """The same change with --yes, aimed at the gid so it cannot drift to another row."""
    return "co asana " + " ".join(shlex.quote(w) for w in words) + " --yes"


def _preview(what: str, task: dict, changes: dict, shown: dict, rerun: str, as_json: bool,
             note: str | None = None, literal: bool = False) -> None:
    """Show what would change and change nothing; --json prints {preview, task_gid, changes}.

    `note` is one extra line before Next (stderr under --json), for when the
    rerun cannot carry everything by itself. `literal` means `rerun` already has
    the selector applied and carries user text, so it is printed untouched.
    """
    tip = _literal_tip if literal else _tip
    if as_json:
        print(json.dumps({"preview": True, "task_gid": task["gid"], "changes": changes}, indent=2, ensure_ascii=False))
        if note:
            style.console(stderr=True).print(style.muted(escape(note)))
        return tip(rerun, True)
    out = style.console()
    out.print(f"{style.warn('Preview')} — {escape(what)}. Nothing changed in Asana.")
    for label, value in shown.items():
        out.print(f"  {label + ':':<13}{escape(str(value))}")
    if note:
        out.print(style.muted(escape(note)))
    tip(rerun, False)


def _unknown_points_to(error, command: str):
    """A change whose result is unknown names the read that shows whether it was saved."""
    if getattr(error, "outcome_unknown", False):
        error.next_step = command
        error.args = (f"{str(error).rstrip('.')}. Check before running it again.",)
    return error


@asana_app.command("update", epilog="Example:  co asana update 1209876543210987 --due-on 2026-10-30  |  "
                                    "co asana update 1209876543210987 --done --yes  |  "
                                    "co asana update 1209876543210987 --open --yes")
@_reported
def update(ref: str = typer.Argument(..., help=WRITE_REF_HELP),
           due_on: Optional[str] = typer.Option(None, "--due-on", help="New due day, YYYY-MM-DD"),
           done: bool = typer.Option(False, "--done", help="Mark the task complete"),
           reopen: bool = typer.Option(False, "--open", help="Mark a completed task open again; not with --done"),
           listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID from co asana tasks; needed with a row number"),
           yes: bool = typer.Option(False, "--yes", help=YES_HELP),
           as_json: bool = typer.Option(False, "--json", help="Print the preview, or the updated task, as JSON")):
    """Change a task's due day and/or mark it complete or open again; what you leave out stays. Changes it only with --yes; otherwise previews.

    The preview shows each field as it is now and as it would be. A task due at
    a time of day is refused: --due-on would drop the time.

    Exit 0 on success or preview, 1 on a failure from Asana, the token or
    the network, 2 on a wrong argument. A change whose result is unknown is
    never sent again. Errors go to stderr.
    """
    if done and reopen:
        raise UsageError("Give --done or --open, not both", "co asana update --help")
    if due_on is None and not done and not reopen:
        raise UsageError("Nothing to change: give --due-on, --done or --open", "co asana update --help")
    completed = True if done else False if reopen else None
    day = _day(due_on, "--due-on", "co asana update --help")
    client = _api().Asana()
    gid = _write_task_ref(client, ref, listing)
    task = client.get_task(gid)
    if day is not None and task.get("due_at"):
        raise UsageError(f"Task {gid} is due at a time ({_when(task['due_at'])}); --due-on would drop the time. "
                         "Change it in Asana", f"co asana task {gid}")
    before_day = _api().due_day(task)
    changes, shown = {}, {"task": f"{task.get('name') or '(untitled)'}  {gid}"}
    if day is not None:
        changes["due_on"] = {"before": task.get("due_on"), "after": day.isoformat()}
        shown["due"] = f"{before_day.isoformat() if before_day else '-'} → {day.isoformat()}"
    if completed is not None:
        changes["completed"] = {"before": task.get("completed"), "after": completed}
        shown["status"] = f"{'done' if task.get('completed') else 'open'} → {'done' if completed else 'open'}"
    if not yes:
        words = (["update", gid] + (["--due-on", day.isoformat()] if day else [])
                 + (["--done"] if done else []) + (["--open"] if reopen else []))
        return _preview(f"would change {task.get('name') or gid}", task, changes, shown,
                        _rerun(*words) + (" --json" if as_json else ""), as_json)
    try:
        updated = client.update_task(gid, due_on=day, completed=completed)
    except _api().AsanaError as error:
        raise _unknown_points_to(error, f"co asana task {gid}") from None
    if as_json:
        print(json.dumps(updated, indent=2, ensure_ascii=False))
        return _tip(f"co asana task {gid}", True)
    after_day = _api().due_day(updated)
    result = [f"due {after_day.isoformat() if after_day else '-'}"] if day is not None else []
    result += [f"{'done' if updated.get('completed') else 'open'}"] if completed is not None else []
    _print([f"{style.ok('✓')} Updated {escape(updated.get('name') or '(untitled)')}  {style.muted(gid)}: "
            f"{escape(', '.join(result))}"])
    _tip(f"co asana task {gid}", False)


@asana_app.command("comment", epilog='Example:  co asana comment 1209876543210987 "Moved to Friday"  |  '
                                     'co asana comment 1209876543210987 "Moved to Friday" --yes  |  '
                                     "co asana comment 1209876543210987 - --yes < note.md")
@_reported
def comment(ref: str = typer.Argument(..., help=WRITE_REF_HELP),
            text: str = typer.Argument(..., help="Comment text; - reads it from standard input"),
            listing: Optional[str] = typer.Option(None, "--listing", help="Listing ID from co asana tasks; needed with a row number"),
            yes: bool = typer.Option(False, "--yes", help=YES_HELP),
            as_json: bool = typer.Option(False, "--json", help="Print the preview, or the new comment, as JSON")):
    """Write a comment on a task, posted as you; Asana notifies its followers. Sends it only with --yes; otherwise previews.

    Run it once without --yes to see the preview, then again with --yes to post.
    The text is sent exactly as written; - reads it from a file or pipe. If
    Asana's answer is lost, the comment is not sent again: run co asana stories
    on the task to see whether it was posted before you retry.

    Exit 0 on success or preview, 1 on a failure from Asana, the token or
    the network, 2 on a wrong argument. A comment whose result is unknown is
    never sent again. Errors go to stderr.
    """
    piped = text == "-"
    body = sys.stdin.read() if piped else text
    if not body.strip():
        raise UsageError("The comment is empty", "co asana comment --help")
    client = _api().Asana()
    gid = _write_task_ref(client, ref, listing)
    task = client.get_task(gid)
    if not yes:
        shown = {"task": f"{task.get('name') or '(untitled)'}  {gid}", "comment": body}
        flags = " --json" if as_json else ""
        # Standard input is used up by now, so Next carries the text itself when it
        # survives as one argument unchanged. Piped text with a line break (a trailing
        # newline included) or exactly "-" (Next would read standard input again) is
        # piped again instead; text starting with "-" goes after "--" so it is not an option.
        # The text is added after selected_tip and printed literally, so neither the
        # --env-file selector nor tag stripping can reach it.
        if piped and ("\n" in body or "\r" in body or body == "-"):
            note = "The comment came from standard input: pipe the same text into the command below."
            return _preview(f"would comment on {task.get('name') or gid}", task, {"comment": body}, shown,
                            _rerun("comment", gid, "-") + flags, as_json, note)
        if body.startswith("-"):
            rerun = selected_tip(_rerun("comment", gid) + flags) + " -- " + shlex.quote(body)
        else:
            rerun = (selected_tip(f"co asana comment {shlex.quote(gid)}") + " " + shlex.quote(body)
                     + " --yes" + flags)
        return _preview(f"would comment on {task.get('name') or gid}", task, {"comment": body}, shown,
                        rerun, as_json, literal=True)
    try:
        story = client.add_comment(gid, body)
    except _api().AsanaError as error:
        raise _unknown_points_to(error, f"co asana stories {gid}") from None
    if as_json:
        print(json.dumps(story, indent=2, ensure_ascii=False))
        return _tip(f"co asana stories {gid}", True)
    _print([f"{style.ok('✓')} Commented on {escape(task.get('name') or '(untitled)')}  {style.muted(gid)}  "
            f"{style.muted(_when(story.get('created_at')))}"])
    _tip(f"co asana stories {gid}", False)
