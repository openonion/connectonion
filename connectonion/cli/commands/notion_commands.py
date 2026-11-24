"""
Purpose: `co notion` — list, search and read Notion pages and databases (read-only)
LLM-Note:
  Dependencies: imports from [typer, cli/style.py, cli/typer_groups.py, command_tips.py, notion_api.py] | imported by [cli/main.py] | tested by [tests/unit/test_notion_commands.py]
  Data flow: argv → typer leaf → notion_api reads → numbered rows (or --json) → one Next line | pages, search and db save the shown ids as one short-lived listing; page, db and columns take a row number from the last list (or --listing), a link or an id
  State/Effects: reads only; nothing in Notion changes | writes the shown rows' ids (no titles or content) under ~/.co/notion-listings for 15 minutes; --json saves none
  Integration: notion_app is added to the root app in main.py; each "co notion <verb>" is HANDLER in command_tips.NEXT because every handler names its own next command | databases are read through their data source (Notion 2025-09-03) | row numbers use gmail_listings, the same store the Asana and OneNote commands use
  Errors: NotionError → `✗ <cause>` and `Next: <command>` on stderr, exit 1; a wrong argument or a stale row number → exit 2 naming the command to run
"""

import hashlib
import json
import os
import re
import shlex
import tempfile
from functools import wraps
from pathlib import Path
from typing import List, Optional

import typer
from rich.markup import escape

from ...environment import global_config_dir
from .. import style
from ..typer_groups import _OneSuggestion
from . import notion_api as api
from . import notion_markdown
from .command_tips import mark_next_step_named, print_tip, selected_tip
from .gmail_listings import ListingError, resolve_reference, save_listing

notion_app = typer.Typer(
    cls=_OneSuggestion,
    invoke_without_command=True,
    help="Notion pages and databases from the terminal: list what is shared, search titles, read a page, query a "
         "database. Read-only: nothing in Notion changes. It reads what NOTION_API_KEY can read: an internal "
         "connection only the pages given to it, a personal access token everything your account can. Lists are "
         "numbered: page, db and columns take a row number from the last list, a link or an id.",
    epilog="Example:  co notion pages  |  co notion page 1  |  co notion db 2  |  "
           "Setup:  co env set NOTION_API_KEY ntn_... --secret  →  co notion check",
)

ROW = re.compile(r"#?[0-9]{1,4}")          # a row number, as co asana reads one; a Notion id is 32 hex
PAGE_HELP = "Row number from the last list, a page link or an id"
DB_HELP = "Row number from the last list, a database link or an id"
SOURCE_HELP = "Which data source, by id or name, when the database has more than one"
LISTING_HELP = "Listing ID printed under a list; keeps row numbers pointing at that list after you list another"
IDS_HELP = "Also show each row's Notion id"
JSON_HELP = "Print the same fields as JSON (ids included); no row numbers are saved"
LIST_LIMIT = 100                          # one Notion request: most lists are whole without a cursor
CURSOR_HELP = "Continue a list from the --cursor its last line printed; only for that same command"


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


# -- row numbers -----------------------------------------------------------
# One family, "items": the last list shown, whether pages, search or a database's rows,
# so `co notion page 3` opens the third row of whichever list is on screen.

def _listings() -> Path:
    return global_config_dir() / "notion-listings"


def _account() -> str:
    """Row numbers belong to the identity behind the key (its bot or user id), as Asana's belong to an account."""
    return f"notion:{api.whoami().get('id', '')}"


def _usage(message: str, next_step: str) -> None:
    out = style.console(stderr=True)
    out.print(f"{style.error('✗')} {escape(message)}")
    out.print(style.next_line(selected_tip(next_step)))
    mark_next_step_named()
    raise typer.Exit(2)


def _store_rows(account: str, ids: list[str]) -> Optional[str]:
    """Save the shown rows' ids and point last-items at them; returns the listing token.

    An empty list saves nothing and removes last-items, so an old row number is
    refused as "no recent list" instead of reaching rows that are no longer shown.
    """
    try:
        if not ids:
            (_listings() / "last-items").unlink(missing_ok=True)
            return None
        token = save_listing(_listings(), account, "items", ids, provider="notion")
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=_listings(),
                                         prefix=".last-items-", delete=False) as stream:
            stream.write(token)
        os.replace(stream.name, _listings() / "last-items")
    except OSError:
        raise api.NotionError("Could not save the row numbers under ~/.co/notion-listings. Check write access "
                              "there, or use the ids from --ids or --json", "co notion pages --ids") from None
    return token


def _ref(value: str, listing: Optional[str]) -> str:
    """The id behind a row number (from --listing, else the last list); a link or an id is returned as given."""
    if not ROW.fullmatch(value.strip()):
        return value
    if listing is None:
        try:
            listing = (_listings() / "last-items").read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            _usage(f"No recent Notion list to take row {value} from", "co notion pages")
    try:
        return resolve_reference(_listings(), value.strip(), _account(), "items", listing, provider="notion")
    except ListingError as error:
        _usage(str(error), "co notion pages")


# -- cursors ---------------------------------------------------------------
# Notion's cursor plus a check of the query it came from, as co gmail binds its mailbox
# cursors to their query: reused with other words, --type, columns or -n, it is refused
# instead of continuing a different list.

def _query_check(*query) -> str:
    return hashlib.sha256(json.dumps(query, ensure_ascii=False).encode()).hexdigest()[:8]


def _bind(after: str, *query) -> str:
    return f"{after}.{_query_check(*query)}" if after else ""


def _unbind(cursor: str, again: str, *query) -> str:
    if not cursor:
        return ""
    after, _, check = cursor.strip().rpartition(".")
    if not after or check != _query_check(*query):
        _usage("This --cursor belongs to another list (other words, --type, columns or -n); "
               "run the original command again", again)
    return after


def _listing_note(token: Optional[str]) -> list[str]:
    return [f"Listing: {token} (15 min; optional --listing ID pins these rows)"] if token else []


def _numbered(lines: list[tuple[str, str, str]], ids: list[str], show_ids: bool) -> None:
    """Print '<n>. <kind/date>  <title>' rows with the columns lined up; ids only under --ids."""
    out = style.console()
    width = len(f"{len(lines)}.")
    meta_width = max((len(meta) for _, meta, _ in lines), default=0)
    for i, (label, meta, extra) in enumerate(lines, 1):
        number = f"{i}.".rjust(width)
        ident = f"  {style.muted(ids[i - 1])}" if show_ids else ""
        out.print(f"{style.count(number)}  {style.muted(meta.ljust(meta_width))}  {escape(label)}{ident}"
                  + (f"  {style.muted(escape(extra))}" if extra else ""))


def _print_rows(rows: list, show_ids: bool = False) -> None:
    _numbered([(r["title"] or "(untitled)", f"{r['type']:<8}  {r['edited'][:10]}",
                "(in trash)" if r.get("in_trash") else "") for r in rows],
              [r["id"] for r in rows], show_ids)


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

@notion_app.command("check", epilog="Example:  co notion check  |  "
                                     "co notion check --target https://www.notion.so/Roadmap-1f2e3d4c5b6a79881726354433221100")
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


@notion_app.command("pages", epilog="Example:  co notion pages  |  co notion pages --type database -n 50")
@_reported
def pages(kind: str = typer.Option("", "--type", help="page or database; without it, both"),
          last: int = typer.Option(LIST_LIMIT, "--last", "-n", min=1, max=100, help="At most this many, most recently edited first"),
          cursor: str = typer.Option("", "--cursor", help=CURSOR_HELP),
          ids: bool = typer.Option(False, "--ids", help=IDS_HELP),
          as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List every page and database this key can read, newest edit first. Read-only.

    With an internal connection that is the pages given to it (and the pages
    under them); with a personal access token, what your account can read.
    It is not a list of the whole workspace. Rows are numbered for co notion
    page, db and columns; the numbers stay valid for 15 minutes. When there
    are more than -n (100 by default, one request to Notion), the first line
    says so and the last line names the --cursor command for the next page.
    To find one by its title, use co notion search.
    """
    _listing("", kind, last, cursor, ids, as_json)


@notion_app.command("search", epilog='Example:  co notion search "roadmap"  |  co notion search "meeting" --type page')
@_reported
def search(text: str = typer.Argument(..., help='Words in page or database titles (required; co notion pages lists everything)'),
           kind: str = typer.Option("", "--type", help="page or database; without it, both"),
           last: int = typer.Option(LIST_LIMIT, "--last", "-n", min=1, max=100, help="At most this many, most recently edited first"),
           cursor: str = typer.Option("", "--cursor", help=CURSOR_HELP),
           ids: bool = typer.Option(False, "--ids", help=IDS_HELP),
           as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """Search titles of pages and databases this key can read, newest edit first. Read-only.

    It is not a search of the whole workspace: an empty result means nothing
    this key can read matched, not that the page does not exist. Results are
    numbered like co notion pages. When there are more results the last line
    names the --cursor command for the next page.
    Words are required: co notion pages lists everything this key can read.
    """
    if not text.strip():
        # One command per job: listing everything is co notion pages, not an empty search.
        print_tip("search needs words from a title; to list everything shared use co notion pages. "
                  "Next: co notion pages")
        raise typer.Exit(2)
    _listing(text, kind, last, cursor, ids, as_json)


def _listing(text: str, kind: str, last: int, cursor: str, ids: bool, as_json: bool) -> None:
    """pages (text "") and search share one request: Notion's search, newest edit first."""
    if kind not in ("", "page", "database"):
        command = "search" if text else "pages"
        print_tip(f"--type takes page or database. Next: co notion {command} --help")
        raise typer.Exit(2)
    again = f"co notion search {shlex.quote(text)}" if text else "co notion pages"
    query = ("search" if text else "pages", text, kind, last)
    after_given = _unbind(cursor, again, *query)
    account = None if as_json else _account()
    found, after = api.search(text, kind or None, last, after_given)
    bound = _bind(after, *query)
    rows = [api.row(obj) for obj in found]
    for r in rows:
        if r["type"] == "data_source":
            r["type"] = "database"
    if as_json:
        _dump({"results": rows, "next_cursor": bound or None, "complete": not after, "note": api.SEARCH_NOTE})
    else:
        token = _store_rows(account, [r["id"] for r in rows])
        noun = "result" if len(rows) == 1 else "results"
        if not text:
            noun = "shared " + ("database" if kind == "database" else "page" if kind == "page" else "item") \
                + ("" if len(rows) == 1 else "s")
        style.console().print(f"{style.count(len(rows))} {noun}" + (f" matching {escape(repr(text))}" if text else "")
                              + (" (more available)" if after else ""))
        _print_rows(rows, ids)
        for line in _listing_note(token):
            style.console().print(style.muted(line))
        style.console().print(style.muted(api.SEARCH_NOTE + "."))
    if after:
        return _tip(again + (f" --type {kind}" if kind else "") + (f" -n {last}" if last != LIST_LIMIT else "")
                    + f" --cursor {bound}", as_json)
    if not rows:
        # Nothing listed at all means nothing is shared; nothing matching a title may just be unshared.
        return _tip("co notion check --target <the page's link>", as_json)
    first = rows[0]
    _tip(f"co notion {'columns' if first['type'] == 'database' else 'page'} {first['id'] if as_json else 1}", as_json)


@notion_app.command("page", epilog="Example:  co notion page 1  |  co notion page 1 --md > roadmap.md")
@_reported
def page(target: str = typer.Argument(..., help=PAGE_HELP),
         max_blocks: int = typer.Option(api.DEFAULT_BLOCK_LIMIT, "--max-blocks", min=1, max=20000,
                                        help="Stop after reading this many blocks"),
         depth: int = typer.Option(api.DEFAULT_DEPTH, "--depth", min=1, max=30, help="How deep nested blocks are read"),
         listing: Optional[str] = typer.Option(None, "--listing", help=LISTING_HELP),
         as_md: bool = typer.Option(False, "--md", help="Print the page as a Markdown document (front matter, "
                                                          "title, content) to save as a .md file"),
         as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """Show one page: title, link, every property, and its content with nesting, files and coverage. Read-only.

    The last lines say whether the whole page was read. If a limit stopped it,
    the content is partial and says so; child pages and databases are listed
    with the command that opens each. Under --json every property keeps its
    type, ids and empty values (0, false, null). --md prints the page as a
    Markdown document (properties in front matter) to redirect to a .md file;
    a partial read says so at its top.
    """
    if as_md and as_json:
        print_tip("--md and --json are two outputs; pick one. Next: co notion page --help")
        raise typer.Exit(2)
    detail = api.read_page(_ref(target, listing), max_blocks=max_blocks, max_depth=depth)
    if as_md:
        # Raw text, never through Rich: the document is the output, and the Next line goes to stderr.
        print(notion_markdown.document(detail, _value_text), end="")
        return _tip("co notion pages", True)
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


@notion_app.command("db", epilog='Example:  co notion db 2  |  co notion db 2 --where "Status=In progress" --sort -Due')
@_reported
def db(target: str = typer.Argument(..., help=DB_HELP),
       source: str = typer.Option("", "--source", help=SOURCE_HELP),
       where: List[str] = typer.Option([], "--where", help="Column=value, != ~ > < >= <=; repeat to require all; "
                                                           "edited>2026-10-01 filters by last edit"),
       sort: List[str] = typer.Option([], "--sort", help="Column to sort by, -Column for descending; edited, created"),
       last: int = typer.Option(20, "--last", "-n", min=1, max=100, help="At most this many rows"),
       cursor: str = typer.Option("", "--cursor", help=CURSOR_HELP),
       listing: Optional[str] = typer.Option(None, "--listing", help=LISTING_HELP),
       ids: bool = typer.Option(False, "--ids", help=IDS_HELP),
       as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List a database's rows, numbered: title and every property, filtered and sorted by its real columns. Read-only.

    Column names and options are checked against the data source's schema
    before the query runs. Rows are numbered for co notion page. When there
    are more rows the last line names the --cursor command for the next page;
    under --json, next_cursor and complete.
    Notion stops any one query at 10,000 results; past that it says so and no
    cursor continues, so narrow the query with --where (edited>… works).
    """
    ds = api.data_source(_ref(target, listing), source)
    query = ("db", ds["id"], list(where), list(sort), last)
    after_given = _unbind(cursor, f"co notion db {ds['id']}", *query)
    account = None if as_json else _account()
    found, after, capped = api.query(ds["id"], filter=api.build_filter(ds, where), sorts=api.build_sorts(ds, sort),
                                     first=last, cursor=after_given)
    bound = _bind(after, *query)
    rows = [{**api.row(obj), "properties": api.full_properties(obj)} for obj in found]
    info = _source_row(ds)
    if as_json:
        _dump({"data_source": info, "rows": rows, "next_cursor": bound or None,
               "complete": not after and not capped, "capped": capped})
    else:
        out = style.console()
        out.print(f"{style.count(len(rows))} {'row' if len(rows) == 1 else 'rows'} in {escape(info['title'])}"
                  + (" (more available)" if after else "")
                  + (f" (Notion stopped this query at {api.QUERY_RESULT_LIMIT:,} results: more rows match than any "
                     "cursor reaches)" if capped else ""))
        token = _store_rows(account, [r["id"] for r in rows])
        _numbered([(r["title"] or "(untitled)", r["edited"][:10],
                    "  ".join(f"{k}: {_value_text(v)}" for k, v in r["properties"].items()
                              if v["type"] != "title" and _value_text(v))) for r in rows],
                  [r["id"] for r in rows], ids)
        for line in _listing_note(token):
            out.print(style.muted(line))
    if after:
        words = ["db", ds["id"], *[w for c in where for w in ("--where", c)], *[w for s in sort for w in ("--sort", s)],
                 "-n", str(last), "--cursor", bound]
        return _tip("co notion " + " ".join(shlex.quote(w) for w in words), as_json)
    if capped:
        return _tip(f'co notion db {ds["id"]} --where "edited>{(rows[-1]["edited"] if rows else "2026-01-01")[:10]}"'
                    " --sort edited", as_json)
    _tip(f"co notion page {rows[0]['id'] if as_json else 1}" if rows else f"co notion columns {ds['id']}", as_json)


@notion_app.command("columns", epilog="Example:  co notion columns 2  |  co notion columns 2 --source Archive")
@_reported
def columns(target: str = typer.Argument(..., help=DB_HELP),
            source: str = typer.Option("", "--source", help=SOURCE_HELP),
            listing: Optional[str] = typer.Option(None, "--listing", help=LISTING_HELP),
            as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List a database's columns: name, id, type, and the options a select, status or multi_select takes. Read-only.

    These are the names and values co notion db --where and --sort take. A
    database with several data sources exits 1 listing them; pick one with
    --source.
    """
    ds = api.data_source(_ref(target, listing), source)
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
