"""
Purpose: `co linear` — list, read, search, create, update and comment on Linear issues from the terminal
LLM-Note:
  Dependencies: imports from [typer, cli/style.py, cli/typer_groups.py, command_tips.py, linear_api.py] | imported by [cli/main.py] | tested by [tests/unit/test_linear_commands.py]
  Data flow: argv → typer leaf → linear_api reads/resolves names → print rows (or --json) → one Next line | writes: resolve names → preview → mutation only with --yes
  State/Effects: reads only, except create/update/comment with --yes, which change the Linear workspace as the key's owner
  Integration: linear_app is added to the root app in main.py; each leaf is HANDLER in command_tips.NEXT because every handler names its own next command
  Errors: LinearError → `✗ <cause>` and `Next: <command>` on stderr, exit 1; nothing to update → exit 2 naming the help page
"""

import json
import shlex
import sys
from functools import wraps
from typing import List, Optional

import typer
from rich.markup import escape

from .. import style
from ..typer_groups import _OneSuggestion
from . import linear_api as api
from .command_tips import mark_next_step_named, print_tip, selected_tip

linear_app = typer.Typer(
    cls=_OneSuggestion,
    invoke_without_command=True,
    help="Linear issues from the terminal, with your personal API key: list, read, search, create, update, comment. "
         "Reads are Read-only; create, update and comment only preview until --yes. "
         "Issues are named by their identifier (ENG-123); team, state, label and assignee names are looked up for you.",
    epilog="Example:  co linear issues --mine  |  "
           "Setup:  co env set LINEAR_API_KEY lin_api_... --secret  →  co linear check  |  "
           "Workflow:  co linear issues --mine  →  co linear issue ENG-123  →  "
           "co linear comment ENG-123 \"Fixed in #42\" --yes",
)

TEAM_HELP = "Team key, as co linear teams lists it (ENG)"
YES_HELP = "Do it; without --yes this prints a preview and changes nothing"
JSON_HELP = "Print the same fields as JSON"
ASSIGNEE_HELP = "me, or a member's email from co linear users"
PRIORITY_HELP = "0-4 or a word: 0 none, 1 urgent, 2 high, 3 medium, 4 low"


@linear_app.callback()
def _linear(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())


def _reported(handler):
    """A LinearError becomes its cause and the one command to run next, on stderr; exit 1."""
    @wraps(handler)
    def run(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except api.LinearError as error:
            out = style.console(stderr=True)
            out.print(f"{style.error('✗')} {escape(str(error))}")
            out.print(style.next_line(selected_tip(error.next_step)))
            mark_next_step_named()
            raise typer.Exit(1) from None
    return run


def _tip(command: str, as_json: bool = False) -> None:
    """The Next line: stdout for people, stderr under --json so stdout stays parseable."""
    if not as_json:
        print_tip(f"Next: {command}")
        return
    style.console(stderr=True).print(style.next_line(selected_tip(command)))
    mark_next_step_named()


def _dump(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _show(rows: list, as_json: bool, line) -> None:
    """Rows as JSON, or one line each drawn by `line(row)`."""
    if as_json:
        return _dump(rows)
    out = style.console()
    for r in rows:
        out.print(line(r))


def _print_rows(rows: list) -> None:
    cells = [[r["id"], r["state"], r["priority"], r["assignee"] or "-", r["updated"][:10]] for r in rows]
    widths = [max((len(c[i]) for c in cells), default=0) for i in range(5)]
    out = style.console()
    for cell, r in zip(cells, rows):
        line = "  ".join(value.ljust(width) for value, width in zip(cell, widths))
        out.print(f"{style.command(cell[0])}{escape(line[len(cell[0]):])}  {escape(r['title'])}")


def _show_list(nodes: list, heading: str, as_json: bool, empty_next: str) -> None:
    rows = [api.row(node) for node in nodes]
    if as_json:
        _dump(rows)
    else:
        style.console().print(f"{style.count(len(rows))} {escape(heading)}")
        _print_rows(rows)
    _tip(f"co linear issue {rows[0]['id']}" if rows else empty_next, as_json)


def _text(value: str) -> str:
    """`-` means standard input, for text too long or too awkward to quote."""
    return sys.stdin.read() if value == "-" else value


def _rerun(*words: str) -> str:
    return "co linear " + " ".join(shlex.quote(w) for w in words) + " --yes"


def _preview(what: str, lines: dict, rerun: str) -> None:
    out = style.console()
    out.print(f"{style.warn('Preview')} — {escape(what)}. Nothing changed in Linear.")
    for label, value in lines.items():
        out.print(f"  {label + ':':<13}{escape(str(value))}")
    _tip(rerun)


# -- reads -----------------------------------------------------------------

@linear_app.command("issues", epilog='Example:  co linear issues --mine  |  '
                                     'co linear issues --team ENG --state "In Progress" -n 50 --json')
@_reported
def issues(mine: bool = typer.Option(False, "--mine", help="Only issues assigned to you"),
           team: Optional[str] = typer.Option(None, "--team", help=TEAM_HELP),
           state: Optional[str] = typer.Option(None, "--state", help="State name from co linear states; "
                                               "without it, completed and canceled issues are left out"),
           project: Optional[str] = typer.Option(None, "--project", help="Project name from co linear projects"),
           last: int = typer.Option(20, "--last", "-n", min=1, max=250, help="At most this many, most recently updated first"),
           as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List issues, most recently updated first: id, state, priority, assignee, updated, title. Read-only.

    Open issues only unless --state names one (--state Done shows finished
    work). Team, state and project names are checked first: an unknown one
    exits 1 listing the valid names.
    """
    found_team = api.team(team) if team else None
    where = {"assignee": {"isMe": {"eq": True}}} if mine else {}
    if found_team:
        where["team"] = {"key": {"eq": found_team["key"]}}
    if state:
        where["state"] = {"name": {"eq": api.state_name(state, found_team)}}
    else:
        where["state"] = {"type": {"nin": ["completed", "canceled"]}}
    if project:
        where["project"] = {"name": {"eq": api.project_name(project)}}
    heading = " ".join(filter(None, ["issues" if state else "open issues", "assigned to you" if mine else "",
                                     f"in {found_team['key']}" if found_team else "", f"in state {state}" if state else "",
                                     f"in project {project}" if project else ""]))
    _show_list(api.issues(where, last), heading, as_json, "co linear search \"<words>\"")


@linear_app.command("issue", epilog="Example:  co linear issue ENG-123  |  co linear issue ENG-123 --json")
@_reported
def issue(identifier: str = typer.Argument(..., help="Issue identifier, as lists show it (ENG-123)"),
          as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """Show one issue: state, priority, assignee, team, project, labels, link, description and comments. Read-only."""
    node = api.issue(identifier)
    comments = sorted(node["comments"]["nodes"], key=lambda c: c["createdAt"])
    detail = {
        **api.row(node),
        "url": node["url"],
        "team": node["team"]["key"],
        "project": (node.get("project") or {}).get("name"),
        "labels": [label["name"] for label in node["labels"]["nodes"]],
        "created": node["createdAt"],
        "description": node.get("description") or "",
        "comments": [{"author": (c.get("user") or {}).get("name"), "created": c["createdAt"], "body": c["body"]}
                     for c in comments],
    }
    if as_json:
        _dump(detail)
    else:
        _print_issue(detail)
    _tip(f'co linear comment {detail["id"]} "<your reply>"', as_json)


def _print_issue(d: dict) -> None:
    out = style.console()
    out.print(f"{style.command(d['id'])}  {style.heading(d['title'])}")
    out.print(escape(f"State: {d['state']}   Priority: {d['priority']}   Assignee: {d['assignee'] or '-'}"))
    out.print(escape(f"Team: {d['team']}   Project: {d['project'] or '-'}   Labels: {', '.join(d['labels']) or '-'}"))
    out.print(escape(f"Updated: {d['updated']}   Created: {d['created']}"))
    out.print(style.path(d["url"]))
    out.print()
    out.print(escape(d["description"] or "(no description)"))
    out.print()
    out.print(f"Comments ({style.count(len(d['comments']))}):")
    for c in d["comments"]:
        out.print(f"  {style.muted(c['created'][:16].replace('T', ' '))} {escape(c['author'] or '(integration)')}: "
                  f"{escape(c['body'])}")


@linear_app.command("search", epilog='Example:  co linear search "login redirect"  |  co linear search "login" -n 5 --json')
@_reported
def search(text: str = typer.Argument(..., help="Words to look for in issue titles and descriptions"),
           last: int = typer.Option(20, "--last", "-n", min=1, max=250, help="At most this many results"),
           as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """Search issues by text, Linear's best match first, open or closed. Read-only."""
    _show_list(api.search(text, last), f"issues matching {text!r}", as_json, "co linear issues")


@linear_app.command("teams", epilog="Example:  co linear teams  |  co linear teams --json")
@_reported
def teams(as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List teams with the key that --team takes (ENG) and that starts each issue id. Read-only."""
    rows = [{"key": t["key"], "name": t["name"]} for t in api.teams()]
    _show(rows, as_json, lambda r: f"{style.command(r['key'])}  {escape(r['name'])}")
    _tip(f"co linear issues --team {rows[0]['key']}" if rows else "co linear check", as_json)


@linear_app.command("projects", epilog="Example:  co linear projects  |  co linear projects --team ENG --json")
@_reported
def projects(team: Optional[str] = typer.Option(None, "--team", help=TEAM_HELP + "; only that team's projects"),
             as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List projects with their status and teams; the names --project takes. Read-only."""
    found_team = api.team(team) if team else None
    rows = [{"name": p["name"], "status": p["status"]["name"], "teams": [t["key"] for t in p["teams"]["nodes"]],
             "updated": p["updatedAt"], "url": p["url"]} for p in api.projects(found_team and found_team["id"])]
    _show(rows, as_json, lambda r: f"{escape(r['name'])}  {style.muted(r['status'] + '  ' + ','.join(r['teams']))}")
    _tip(f'co linear issues --project "{rows[0]["name"]}"' if rows else "co linear teams", as_json)


@linear_app.command("states", epilog="Example:  co linear states --team ENG  |  co linear states --json")
@_reported
def states(team: Optional[str] = typer.Option(None, "--team", help=TEAM_HELP + "; each team has its own states"),
           as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List workflow states per team, in board order; the names --state takes. Read-only."""
    found_team = api.team(team) if team else None
    nodes = sorted(api.states(found_team and found_team["id"]), key=lambda s: (s["team"]["key"], s["position"]))
    rows = [{"team": s["team"]["key"], "name": s["name"], "type": s["type"]} for s in nodes]
    _show(rows, as_json, lambda r: f"{escape(r['team'])}  {style.command(r['name'])}  {style.muted(r['type'])}")
    _tip(f'co linear issues --team {rows[0]["team"]} --state "{rows[0]["name"]}"' if rows else "co linear teams", as_json)


@linear_app.command("labels", epilog="Example:  co linear labels --team ENG  |  co linear labels --json")
@_reported
def labels(team: Optional[str] = typer.Option(None, "--team", help=TEAM_HELP + "; that team's labels plus workspace ones"),
           as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List issue labels, the names create --label takes; a team label shows its team key. Read-only."""
    found_team = api.team(team) if team else None
    rows = [{"name": l["name"], "team": (l["team"] or {}).get("key")} for l in api.labels(found_team and found_team["id"])]
    rows.sort(key=lambda r: (r["team"] or "", r["name"].lower()))
    _show(rows, as_json, lambda r: f"{style.command(r['name'])}  {style.muted(r['team'] or 'workspace')}")
    _tip(f'co linear create "<title>" --team {found_team["key"] if found_team else "<key>"} --label "{rows[0]["name"]}"'
         if rows else "co linear teams", as_json)


@linear_app.command("users", epilog="Example:  co linear users  |  co linear users --json")
@_reported
def users(as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List active workspace members with the email --assignee takes. Read-only."""
    rows = [{"name": u["name"], "email": u["email"]} for u in api.users()]
    _show(rows, as_json, lambda r: f"{escape(r['name'])}  {style.command(r['email'])}")
    _tip(f"co linear update <ENG-123> --assignee {rows[0]['email']}" if rows else "co linear check", as_json)


@linear_app.command("check", epilog="Example:  co linear check")
@_reported
def check():
    """Check LINEAR_API_KEY: the workspace and the person it acts as. Read-only.

    Without a key it exits 1 naming the co env set command and where in Linear
    to create one.
    """
    who = api.whoami()
    out = style.console()
    out.print(f"{style.ok('✓')} Linear workspace {escape(who['organization']['name'])} "
              f"{style.path('linear.app/' + who['organization']['urlKey'])}")
    out.print(f"  Acting as {escape(who['viewer']['name'])} <{escape(who['viewer']['email'])}>")
    _tip("co linear issues --mine")


# -- writes ----------------------------------------------------------------

@linear_app.command("create", epilog='Example:  co linear create "Login redirect loops" --team ENG --label bug --priority 2  |  '
                                     'co linear create "Login redirect loops" --team ENG --description - --assignee me --yes')
@_reported
def create(title: str = typer.Argument(..., help="Issue title"),
           team: str = typer.Option(..., "--team", help=TEAM_HELP),
           description: Optional[str] = typer.Option(None, "--description", help="Markdown body; - reads it from standard input"),
           assignee: Optional[str] = typer.Option(None, "--assignee", help=ASSIGNEE_HELP),
           priority: Optional[str] = typer.Option(None, "--priority", help=PRIORITY_HELP),
           label: List[str] = typer.Option([], "--label", help="Label name from co linear labels; repeat for more"),
           yes: bool = typer.Option(False, "--yes", help=YES_HELP)):
    """Create an issue in a team, in the team's default state. Creates it only with --yes; otherwise previews.

    Every name is looked up before anything is created, so an unknown team,
    label or assignee exits 1 listing the valid ones. Prints the new id.
    """
    found_team = api.team(team)
    fields = {"teamId": found_team["id"], "title": title}
    shown = {"team": f"{found_team['key']} ({found_team['name']})", "title": title}
    if description is not None:
        fields["description"] = _text(description)
        shown["description"] = f"{len(fields['description'])} characters"
    if assignee:
        person = api.user(assignee)
        fields["assigneeId"] = person["id"]
        shown["assignee"] = f"{person['name']} <{person['email']}>"
    if priority is not None:
        fields["priority"] = api.priority(priority, "create")
        shown["priority"] = api.priority_word(fields["priority"])
    if label:
        found_labels = api.label_ids(found_team, label)
        fields["labelIds"] = [l["id"] for l in found_labels]
        shown["labels"] = ", ".join(l["name"] for l in found_labels)
    if not yes:
        words = [title, "--team", found_team["key"]] + _flags(description=description, assignee=assignee,
                                                               priority=priority) + [w for l in label for w in ("--label", l)]
        return _preview(f"would create this issue in {found_team['key']}", shown, _rerun("create", *words))
    created = api.create_issue(fields)
    style.console().print(f"{style.ok('✓')} Created {style.command(created['identifier'])}: {escape(created['title'])}  "
                          f"{style.path(created['url'])}")
    _tip(f"co linear issue {created['identifier']}")


def _flags(**values) -> list:
    return [w for name, value in values.items() if value is not None for w in (f"--{name}", value)]


@linear_app.command("update", epilog='Example:  co linear update ENG-123 --state Done  |  '
                                     "co linear update ENG-123 --assignee me --priority 1 --yes")
@_reported
def update(identifier: str = typer.Argument(..., help="Issue identifier (ENG-123)"),
           state: Optional[str] = typer.Option(None, "--state", help="State name in the issue's team, from co linear states --team <key>"),
           assignee: Optional[str] = typer.Option(None, "--assignee", help=ASSIGNEE_HELP),
           priority: Optional[str] = typer.Option(None, "--priority", help=PRIORITY_HELP),
           yes: bool = typer.Option(False, "--yes", help=YES_HELP)):
    """Change an issue's state, assignee or priority; what you leave out stays. Changes it only with --yes; otherwise previews.

    The preview shows each field as it is now and as it would be. Linear
    notifies the issue's subscribers of the change.
    """
    if state is None and assignee is None and priority is None:
        print_tip("Nothing to change: give --state, --assignee or --priority. Next: co linear update --help")
        raise typer.Exit(2)
    node = api.issue(identifier)
    fields, shown = {}, {}
    if state:
        found = api.state(node["team"], state)
        fields["stateId"] = found["id"]
        shown["state"] = f"{node['state']['name']} → {found['name']}"
    if assignee:
        person = api.user(assignee)
        fields["assigneeId"] = person["id"]
        shown["assignee"] = f"{(node.get('assignee') or {}).get('name') or '-'} → {person['name']}"
    if priority is not None:
        fields["priority"] = api.priority(priority, "update")
        shown["priority"] = f"{node['priorityLabel']} → {api.priority_word(fields['priority'])}"
    if not yes:
        words = [node["identifier"]] + _flags(state=state, assignee=assignee, priority=priority)
        return _preview(f"would change {node['identifier']} {node['title']}", shown, _rerun("update", *words))
    changed = api.update_issue(node["id"], fields)
    style.console().print(f"{style.ok('✓')} Updated {style.command(changed['identifier'])}: "
                          + escape(", ".join(f"{k} {v}" for k, v in shown.items())))
    _tip(f"co linear issue {changed['identifier']}")


@linear_app.command("comment", epilog='Example:  co linear comment ENG-123 "Fixed in #42"  |  '
                                      'co linear comment ENG-123 - --yes')
@_reported
def comment(identifier: str = typer.Argument(..., help="Issue identifier (ENG-123)"),
            text: str = typer.Argument(..., help="Comment in Markdown; - reads it from standard input"),
            yes: bool = typer.Option(False, "--yes", help=YES_HELP)):
    """Write a comment on an issue, posted as you; Linear notifies its subscribers. Sends it only with --yes; otherwise previews."""
    node = api.issue(identifier)
    body = _text(text)
    if not yes:
        shown = {"issue": f"{node['identifier']} {node['title']}", "comment": body}
        return _preview(f"would comment on {node['identifier']}", shown, _rerun("comment", node["identifier"], text))
    posted = api.create_comment(node["id"], body)
    style.console().print(f"{style.ok('✓')} Commented on {style.command(node['identifier'])}  {style.path(posted['url'])}")
    _tip(f"co linear issue {node['identifier']}")
