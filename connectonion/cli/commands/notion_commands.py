"""
Purpose: `co notion` — list, search and read Notion pages and databases (read-only)
LLM-Note:
  Dependencies: imports from [typer, cli/style.py, cli/typer_groups.py, command_tips.py, notion_api.py] | imported by [cli/main.py] | tested by [tests/unit/test_notion_commands.py]
  Data flow: argv → typer leaf → notion_api reads → print rows (or --json) → one Next line | changes and show --json are what REM reads (#3249): pages edited since a time, and one page as it is now
  State/Effects: reads only; nothing in Notion or on disk changes
  Integration: notion_app is added to the root app in main.py; each "co notion <verb>" is HANDLER in command_tips.NEXT because every handler names its own next command | databases are read through their data source (Notion 2025-09-03)
  Errors: NotionError → `✗ <cause>` and `Next: <command>` on stderr, exit 1; a wrong argument → exit 2 naming the help page
"""

import json
import shlex
from datetime import datetime, timezone
from functools import wraps
from typing import List

import typer
from rich.markup import escape

from .. import style
from ..typer_groups import _OneSuggestion
from . import notion_api as api
from .command_tips import mark_next_step_named, print_tip, selected_tip

notion_app = typer.Typer(
    cls=_OneSuggestion,
    invoke_without_command=True,
    help="Notion pages and databases from the terminal: list what is shared, search titles, read a page, query a "
         "database. Read-only: nothing in Notion changes. It reads what NOTION_API_KEY can read: an internal "
         "connection only the pages given to it, a personal access token everything your account can. A page is "
         "named by its link or id.",
    epilog="Example:  co notion pages  |  "
           "Setup:  co env set NOTION_API_KEY ntn_... --secret  →  co notion check  →  co notion pages  |  "
           "Workflow:  co notion search \"tasks\" --type database  →  co notion columns <id>  →  "
           "co notion db <id> --where \"Status=In progress\"  →  co notion page <row id>",
)

PAGE_HELP = "Page link or id, as co notion search lists it"
DB_HELP = "Database link or id, as co notion search --type database lists it"
SOURCE_HELP = "Which data source, by id or name, when the database has more than one"
JSON_HELP = "Print the same fields as JSON"


@notion_app.callback()
def _notion(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())


def _reported(handler):
    """A NotionError becomes its cause and the one command to run next, on stderr; exit 1."""
    @wraps(handler)
    def run(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except api.NotionError as error:
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


def _print_rows(rows: list) -> None:
    out = style.console()
    for r in rows:
        trash = "  (in trash)" if r.get("in_trash") else ""
        out.print(f"{style.command(r['id'])}  {style.muted(r['type'] + '  ' + r['edited'][:10])}  "
                  f"{escape(r['title'])}{trash}")


def _source_row(ds: dict) -> dict:
    database = ds.get("database") or {}
    return {"id": ds["id"], "title": api.title_of(ds), "database_id": database.get("id", ""),
            "database_title": api.title_of(database) if database else "", "url": database.get("url", "")}


def _coverage_lines(coverage: dict) -> list:
    lines = [f"Read {coverage['blocks']} blocks; " + ("complete" if coverage["complete"] else
                                                      "INCOMPLETE: " + "; ".join(coverage["stopped"]))]
    if coverage["unsupported"]:
        lines.append("Not rendered (shown as [unsupported block]): "
                     + ", ".join(f"{k} ×{v}" for k, v in coverage["unsupported"].items()))
    for item in coverage["media"]:
        where = ("hosted by Notion" + (f", link expires {item['expires']}" if item["expires"] else "")
                 if item["hosted"] else f"external {item['url']}")
        lines.append(f"File: {item['name']} ({item['kind']}; {where})")
    for child in coverage["child_pages"]:
        lines.append(f"Child page: {child['title']} — co notion page {child['id']}")
    for child in coverage["child_databases"]:
        lines.append(f"Child database: {child['title']} — co notion db {child['id']}")
    return lines


# -- reads -----------------------------------------------------------------

@notion_app.command("check", epilog="Example:  co notion check  |  co notion check --target <page or database link>")
@_reported
def check(target: str = typer.Option("", "--target", help="Also check that this key can read this page or "
                                                          "database")):
    """Check the Notion connection: which credential acts, its workspace, and optionally one target's access. Read-only.

    A NOTION_API_KEY exported in the shell acts first, then the one saved with
    co env set (the env file, then the encrypted store). A working connection
    and a readable page are separate facts: an internal connection reads only
    the pages given to it. Not connected, it exits 1 naming how to save the key.
    """
    bot = api.whoami()
    space = api.workspace(bot)
    using = api.credential()
    out = style.console()
    out.print(f"{style.ok('✓')} Connected with {escape(using.label)}: "
              f"{escape(space['bot_name'] or space['bot_id'])} in "
              f"workspace {escape(space['name'] or '(unnamed)')}" + (f" ({space['id']})" if space["id"] else ""))
    out.print(f"  API version {api.version()}. Which pages it reads depends on the key: "
              f"{escape(api.KEY_SCOPE)}.")
    if not target:
        return _tip("co notion pages")
    parsed = api.parse_target(target)
    try:
        found = api.call("GET", f"pages/{parsed.id}")
        kind = "page"
    except api.NotionError as error:
        if error.kind != "not_found":
            raise
        found = api.data_source(target)
        kind = "data source"
    out.print(f"{style.ok('✓')} Target shared: {kind} {escape(api.title_of(found))} ({found['id']})")
    _tip(f"co notion {'page' if kind == 'page' else 'columns'} {found['id']}")


@notion_app.command("pages", epilog="Example:  co notion pages  |  co notion pages --type database -n 50 --json")
@_reported
def pages(kind: str = typer.Option("", "--type", help="page or database; without it, both"),
          last: int = typer.Option(20, "--last", "-n", min=1, max=100, help="At most this many, most recently edited first"),
          cursor: str = typer.Option("", "--cursor", help="Continue a previous listing from its next_cursor"),
          as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List every page and database this key can read, newest edit first. Read-only.

    With an internal connection that is the pages given to it (and the pages
    under them); with a personal access token, what your account can read.
    It is not a list of the whole workspace. When there are more, the last
    line names the --cursor command for the next page. To find one by its
    title, use co notion search.
    """
    _listing("", kind, last, cursor, as_json)


@notion_app.command("search", epilog='Example:  co notion search "roadmap"  |  '
                                      'co notion search "meeting" --type page -n 50 --json')
@_reported
def search(text: str = typer.Argument(..., help='Words in page or database titles (required; co notion pages lists everything)'),
           kind: str = typer.Option("", "--type", help="page or database; without it, both"),
           last: int = typer.Option(20, "--last", "-n", min=1, max=100, help="At most this many, most recently edited first"),
           cursor: str = typer.Option("", "--cursor", help="Continue a previous search from its next_cursor"),
           as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """Search titles of pages and databases this key can read, newest edit first. Read-only.

    It is not a search of the whole workspace: an empty result means nothing
    this key can read matched, not that the page does not exist. When there are more
    results the last line names the --cursor command for the next page.
    Words are required: co notion pages lists everything this key can read.
    """
    if not text.strip():
        # One command per job: listing everything is co notion pages, not an empty search.
        print_tip("search needs words from a title; to list everything shared use co notion pages. "
                  "Next: co notion pages")
        raise typer.Exit(2)
    _listing(text, kind, last, cursor, as_json)


def _listing(text: str, kind: str, last: int, cursor: str, as_json: bool) -> None:
    """pages (text "") and search share one request: Notion's search, newest edit first."""
    if kind not in ("", "page", "database"):
        command = "search" if text else "pages"
        print_tip(f"--type takes page or database. Next: co notion {command} --help")
        raise typer.Exit(2)
    found, after = api.search(text, kind or None, last, cursor)
    rows = [api.row(obj) for obj in found]
    for r in rows:
        if r["type"] == "data_source":
            r["type"] = "database"
    if as_json:
        _dump({"results": rows, "next_cursor": after or None, "complete": not after, "note": api.SEARCH_NOTE})
    else:
        noun = "result" if len(rows) == 1 else "results"
        if not text:
            noun = "shared " + ("database" if kind == "database" else "page" if kind == "page" else "item") \
                + ("" if len(rows) == 1 else "s")
        style.console().print(f"{style.count(len(rows))} {noun}" + (f" matching {escape(repr(text))}" if text else "")
                              + (" (more available)" if after else ""))
        _print_rows(rows)
        style.console().print(style.muted(api.SEARCH_NOTE + "."))
    again = f"co notion search {shlex.quote(text)}" if text else "co notion pages"
    if after:
        return _tip(again + (f" --type {kind}" if kind else "") + f" -n {last} --cursor {after}", as_json)
    if not rows:
        # Nothing listed at all means nothing is shared; nothing matching a title may just be unshared.
        return _tip("co notion check --target <the page's link>", as_json)
    first = rows[0]
    _tip(f"co notion {'columns' if first['type'] == 'database' else 'page'} {first['id']}", as_json)


@notion_app.command("page", epilog="Example:  co notion page 1f2e3d4c5b6a79881726354433221100  |  "
                                    "co notion page https://www.notion.so/Roadmap-1f2e3d4c5b6a79881726354433221100 --json")
@_reported
def page(target: str = typer.Argument(..., help=PAGE_HELP),
         max_blocks: int = typer.Option(api.DEFAULT_BLOCK_LIMIT, "--max-blocks", min=1, max=20000,
                                        help="Stop after reading this many blocks"),
         depth: int = typer.Option(api.DEFAULT_DEPTH, "--depth", min=1, max=30, help="How deep nested blocks are read"),
         as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """Show one page: title, link, every property, and its content with nesting, files and coverage. Read-only.

    The last lines say whether the whole page was read. If a limit stopped it,
    the content is partial and says so; child pages and databases are listed
    with the command that opens each. Under --json every property keeps its
    type, ids and empty values (0, false, null).
    """
    detail = api.read_page(target, max_blocks=max_blocks, max_depth=depth)
    out_detail = {key: value for key, value in detail.items() if key not in ("raw", "blocks")}
    if as_json:
        _dump(out_detail)
    else:
        out = style.console()
        out.print(f"{style.heading(detail['title'])}  {style.muted(detail['edited'][:16].replace('T', ' '))}")
        out.print(style.path(detail["url"]))
        if detail["in_trash"]:
            out.print(style.warn("This page is in Notion's trash."))
        if detail["anchor"]:
            out.print(style.muted(f"The link points at block {detail['anchor']} on this page; the whole page is shown."))
        for name, prop in detail["properties"].items():
            if prop["type"] == "title":
                continue
            text = _value_text(prop)
            if text:
                out.print(escape(f"{name}: {text}"))
        out.print()
        out.print(escape(detail["content"] or "(no content)"))
        out.print()
        for line in _coverage_lines(detail["coverage"]):
            out.print(style.muted(escape(line)))
    children = detail["coverage"]["child_pages"]
    if detail["parent"] == "data_source":
        _tip(f'co notion db {detail["parent_id"]}', as_json)       # the other rows of its database
    elif children:
        _tip(f'co notion page {children[0]["id"]}', as_json)
    else:
        _tip("co notion pages", as_json)


def _value_text(prop: dict) -> str:
    """Display text for one full_properties() entry."""
    value, kind = prop["value"], prop["type"]
    if value is None or value == "" or value == []:
        return ""
    if kind == "checkbox":
        return "yes" if value else "no"
    if kind == "date":
        return value["start"] + (f" → {value['end']}" if value.get("end") else "")
    if kind in ("people",):
        return ", ".join(p.get("name") or p.get("id", "") for p in value)
    if kind in ("created_by", "last_edited_by"):
        return value.get("name") or value.get("id", "")
    if kind == "relation":
        return f"{len(value)} linked: " + ", ".join(value[:5]) + (" …" if len(value) > 5 else "")
    if kind == "files":
        return ", ".join(f.get("name") or "file" for f in value)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


@notion_app.command("db", epilog='Example:  co notion db <db-id> --where "Status=In progress" --sort -Due  |  '
                                  "co notion db <db-id> -n 100 --json")
@_reported
def db(target: str = typer.Argument(..., help=DB_HELP),
       source: str = typer.Option("", "--source", help=SOURCE_HELP),
       where: List[str] = typer.Option([], "--where", help="Column=value, != ~ > < >= <=; repeat to require all; "
                                                           "edited>2026-10-01 filters by last edit"),
       sort: List[str] = typer.Option([], "--sort", help="Column to sort by, -Column for descending; edited, created"),
       last: int = typer.Option(20, "--last", "-n", min=1, max=100, help="At most this many rows"),
       cursor: str = typer.Option("", "--cursor", help="Continue from a previous listing's next_cursor"),
       as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List a database's rows: id, title and every property, filtered and sorted by its real columns. Read-only.

    Column names and options are checked against the data source's schema
    before the query runs. When there are more rows the last line names the
    --cursor command for the next page; under --json, next_cursor and complete.
    Notion stops any one query at 10,000 results; past that it says so and no
    cursor continues, so narrow the query with --where (edited>… works).
    """
    ds = api.data_source(target, source)
    found, after, capped = api.query(ds["id"], filter=api.build_filter(ds, where), sorts=api.build_sorts(ds, sort),
                                     first=last, cursor=cursor)
    rows = [{**api.row(obj), "properties": api.full_properties(obj)} for obj in found]
    info = _source_row(ds)
    if as_json:
        _dump({"data_source": info, "rows": rows, "next_cursor": after or None,
               "complete": not after and not capped, "capped": capped})
    else:
        out = style.console()
        out.print(f"{style.count(len(rows))} {'row' if len(rows) == 1 else 'rows'} in {escape(info['title'])}"
                  + (" (more available)" if after else "")
                  + (f" (Notion stopped this query at {api.QUERY_RESULT_LIMIT:,} results: more rows match than any "
                     "cursor reaches)" if capped else ""))
        for r in rows:
            shown = "  ".join(f"{k}: {_value_text(v)}" for k, v in r["properties"].items()
                              if v["type"] != "title" and _value_text(v))
            out.print(f"{style.command(r['id'])}  {escape(r['title'])}  {style.muted(escape(shown))}")
    if after:
        words = ["db", ds["id"], *[w for c in where for w in ("--where", c)], *[w for s in sort for w in ("--sort", s)],
                 "-n", str(last), "--cursor", after]
        return _tip("co notion " + " ".join(shlex.quote(w) for w in words), as_json)
    if capped:
        return _tip(f'co notion db {ds["id"]} --where "edited>{(rows[-1]["edited"] if rows else "2026-01-01")[:10]}"'
                    " --sort edited", as_json)
    _tip(f"co notion page {rows[0]['id']}" if rows else f"co notion columns {ds['id']}", as_json)


@notion_app.command("columns", epilog="Example:  co notion columns 1f2e3d4c5b6a79881726354433221100  |  "
                                       "co notion columns <id> --source Archive --json")
@_reported
def columns(target: str = typer.Argument(..., help=DB_HELP),
            source: str = typer.Option("", "--source", help=SOURCE_HELP),
            as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List a database's columns: name, id, type, and the options a select, status or multi_select takes. Read-only.

    These are the names and values co notion db --where and --sort take. A
    database with several data sources exits 1 listing them; pick one with
    --source.
    """
    ds = api.data_source(target, source)
    rows = api.columns(ds)
    info = _source_row(ds)
    if as_json:
        _dump({"data_source": info, "columns": rows})
    else:
        out = style.console()
        out.print(f"{style.count(len(rows))} columns in {escape(info['title'])}  {style.muted('data source ' + ds['id'])}")
        for c in rows:
            kind = c["type"]
            options = f"  {', '.join(c['options'])}" if c["options"] else ""
            out.print(f"{style.command(c['name'])}  {style.muted(kind)}{escape(options)}")
    choice = next((c for c in rows if c["options"]), None)
    where = f' --where "{choice["name"]}={choice["options"][0]}"' if choice else ""
    _tip(f'co notion db {ds["id"]}{where}', as_json)


# -- what REM reads: changes since a time, and one page now (#3249) ----------------
# A REM source is its command plus `changes --since <time> --json` and `show <id> --json`,
# the shape co asana gives. REM keeps nothing: a citation notion:<id> opens live through show.

CHANGES_PAGE_LIMIT = 50          # requests of 100: past 5,000 pages edited since a time, say so instead
CHANGES_JSON_HELP = 'Print {"since", "until", "items": [{"id", "time", "title", "parent", "link"}]}'
SHOW_JSON_HELP = ('Print {"id", "title", "text", "author", "author_id", "time", "created", "link", '
                  '"properties", "parent", "in_trash", "complete"}')


def _since(value: str, now: datetime) -> datetime:
    """--since: a time with its zone, not after now, as co asana changes takes it."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        moment = None
    if moment is None or moment.tzinfo is None:
        print_tip(f"--since takes a time with its zone, like 2026-11-01T09:00+11:00, not {value!r}. "
                  "Next: co notion changes --help")
        raise typer.Exit(2)
    if moment > now:
        print_tip(f"--since {value} is later than now ({now.isoformat()}); nothing can have changed after it. "
                  "Next: co notion changes --help")
        raise typer.Exit(2)
    return moment


def _edited(obj: dict) -> datetime | None:
    stamp = obj.get("last_edited_time") or ""
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _changed_pages(since: datetime) -> list[dict]:
    """Pages this key can read edited at or after `since`'s minute, newest first, every page of the search.

    Notion keeps last_edited_time to the minute, so a page edited at 10:05:30
    reads 10:05:00: the minute `since` falls in is included, and a reader keeps
    one item per id and time. The search is newest first, so it stops at the
    first older page. Past CHANGES_PAGE_LIMIT requests it stops and says so.
    """
    floor = since.replace(second=0, microsecond=0)
    found, cursor = [], ""
    for _ in range(CHANGES_PAGE_LIMIT):
        batch, cursor = api.search("", "page", 100, cursor)
        for obj in batch:
            edited = _edited(obj)
            if edited is not None and edited < floor:
                return found
            found.append(obj)
        if not cursor:
            return found
    raise api.NotionError(f"Read {len(found)} pages edited since {since.isoformat()}, incomplete: more than "
                          f"{CHANGES_PAGE_LIMIT * 100:,}; nothing was listed. Use a later --since",
                          "co notion changes --help", "incomplete")


def _change_item(obj: dict) -> dict:
    row = api.row(obj)
    return {"id": row["id"], "time": row["edited"] or None, "title": row["title"],
            "parent": {"type": row["parent"], "id": row["parent_id"]}, "link": row["url"] or None}


@notion_app.command("changes", epilog="Example:  co notion changes --since 2026-11-01T00:00Z  |  "
                                      "co notion changes --since 2026-11-01T00:00Z --json")
@_reported
def changes(since: str = typer.Option(..., "--since", help="Only pages edited after this time, with its zone "
                                                           "(2026-11-01T09:00+11:00)"),
            as_json: bool = typer.Option(False, "--json", help=CHANGES_JSON_HELP)):
    """List the pages this key can read that were edited since a time, oldest edit first. Read-only.

    Database rows are pages, so an edited row is listed. Notion keeps edit
    times to the minute: the minute --since falls in is included, so a page
    can appear in two consecutive lists; keep one per id and time. "until"
    in --json is when reading began: pass it as the next --since and nothing
    in between is missed. Pages in the trash and pages this key cannot read
    are not listed. REM reads this list; it changes nothing in Notion.
    """
    now = datetime.now(timezone.utc)
    until = now.replace(microsecond=0)
    start = _since(since, now)
    items = [_change_item(obj) for obj in reversed(_changed_pages(start))]
    if as_json:
        _dump({"since": start.isoformat(), "until": until.isoformat(), "items": items})
        return _tip(f"co notion show {items[0]['id']} --json" if items else "co notion check", True)
    out = style.console()
    out.print(f"{style.count(len(items))} {'page' if len(items) == 1 else 'pages'} edited since "
              f"{escape(start.isoformat())}")
    for item in items:
        out.print(f"  {style.muted((item['time'] or '-')[:16].replace('T', ' '))}  {style.muted(item['id'])}  "
                  f"{escape(item['title'])}")
    _tip(f"co notion show {items[0]['id']}" if items else "co notion pages", False)


def _author(user_id: str) -> str | None:
    """A person's name, when Notion lets this key read users; None otherwise, never a guess."""
    if not user_id:
        return None
    try:
        return api.call("GET", f"users/{user_id}").get("name")
    except api.NotionError:
        return None


def _show_item(detail: dict) -> dict:
    """One page now, in the shape REM reads from every source: id, title, text, author, time, link."""
    coverage = detail["coverage"]
    text = detail["content"] or "(no content)"
    if not coverage["complete"]:
        text += "\n\n[INCOMPLETE: " + "; ".join(coverage["stopped"]) + ". The rest of the page was not read.]"
    author_id = detail.get("created_by") or ""
    return {"id": detail["id"], "title": detail["title"], "text": text, "author": _author(author_id),
            "author_id": author_id or None, "time": detail["edited"] or None, "created": detail.get("created") or None,
            "link": detail["url"] or None,
            "properties": {name: _value_text(prop) for name, prop in detail["properties"].items()
                           if prop["type"] != "title" and _value_text(prop)},
            "parent": {"type": detail["parent"], "id": detail["parent_id"]}, "in_trash": detail["in_trash"],
            "complete": coverage["complete"]}


@notion_app.command("show", epilog="Example:  co notion show 1f2e3d4c5b6a79881726354433221100  |  "
                                   "co notion show 1f2e3d4c5b6a79881726354433221100 --json")
@_reported
def show(target: str = typer.Argument(..., help=PAGE_HELP),
         as_json: bool = typer.Option(False, "--json", help=SHOW_JSON_HELP)):
    """Show one page as it is now, as co notion page does; --json gives the shape REM reads. Read-only.

    "text" is the page's content; when a limit stopped the read it ends with
    an [INCOMPLETE: …] line and "complete" is false. "author" is the person
    who created the page, or null when this key cannot read users; "time" is
    its last edit, so a reader can tell it changed since it was cited. A page
    deleted or no longer shared exits 1. Changes nothing in Notion.
    """
    detail = api.read_page(target)
    if as_json:
        _dump(_show_item(detail))
        return _tip(f"co notion page {detail['id']}", True)
    item = _show_item(detail)
    out = style.console()
    out.print(f"{style.heading(item['title'])}  {style.muted(item['id'])}")
    out.print(escape(f"Edited: {(item['time'] or '-')[:16].replace('T', ' ')}   Created by: {item['author'] or item['author_id'] or '-'}"))
    if item["link"]:
        out.print(style.path(item["link"]))
    for name, value in item["properties"].items():
        out.print(escape(f"{name}: {value}"))
    out.print()
    out.print(escape(item["text"]))
    _tip(f"co notion page {detail['id']}", False)
