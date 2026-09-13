"""Experimental Wiki inspection. No collection or provider startup on import."""

import json
import shlex
from pathlib import Path
from typing import List, Optional

import typer


def _next(ctx, arguments):
    root = ctx.obj["root"]
    return shlex.join(["co", "wiki", "--root", str(root), *arguments])


def _emit(ctx, value, arguments, *, failed=False):
    command = _next(ctx, arguments)
    if ctx.obj["json"]:
        typer.echo(json.dumps({"ok": not failed, "data": value, "next": command}, ensure_ascii=False))
    else:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        text = "".join(char for char in text if char in "\n\t" or (ord(char) >= 32 and not 127 <= ord(char) <= 159))
        typer.echo(text, err=failed)
        typer.echo(f"Next: {command}", err=failed)
    if failed:
        raise typer.Exit(1)


def _handle(ctx, operation, recovery):
    from ...wiki.files import WikiError

    try:
        value, arguments = operation(ctx.obj["root"])
    except (WikiError, OSError, UnicodeError) as error:
        message = str(error) if isinstance(error, WikiError) else "Cannot read or write the selected Wiki files"
        _emit(ctx, message, recovery, failed=True)
        return
    _emit(ctx, value, arguments)


def make_wiki_app(factory):
    wiki = factory(help="A notebook your AI maintains from your Codex sessions: start, inspect, open, stop.",
                   no_args_is_help=False)

    @wiki.callback(invoke_without_command=True)
    def overview(ctx: typer.Context,
                 root: Optional[Path] = typer.Option(None, "--root", help="Notebook root (default ~/.co/wiki)"),
                 json_out: bool = typer.Option(False, "--json", help="Machine-readable output with next command")):
        ctx.obj = {"root": (root or Path.home() / ".co/wiki").expanduser().resolve(), "json": json_out}
        if ctx.invoked_subcommand is None:
            inspect_status(ctx)

    @wiki.command("status")
    def inspect_status(ctx: typer.Context):
        """Show local run counts, known usage, and background readiness."""
        from ...wiki.service import status
        _handle(ctx, lambda root: (status(root), ["logs"]), ["config"])

    @wiki.command("subscriptions")
    def inspect_subscriptions(ctx: typer.Context):
        """Show saved source choices or unsaved defaults; no body reads."""
        from ...wiki.service import subscriptions
        _handle(ctx, lambda root: (subscriptions(root), ["status"]), ["config"])

    @wiki.command("scan")
    def scan_sources(ctx: typer.Context,
                     what: str = typer.Argument("people", help="people or projects"),
                     days: int = typer.Option(150, "--days", help="How far back to look"),
                     min_mails: int = typer.Option(3, "--min-mails", help="people: fewer than this is not listed"),
                     mine: List[str] = typer.Option([], "--mine", help="An address that is yours (repeatable)")):
        """Enumerate correspondents or projects from the sources, with counts and dates. No model."""
        from ...wiki.scan import scan_people, scan_projects
        from ...wiki.service import mail_client, subscriptions

        def run(root):
            if what == "projects":
                return scan_projects(subscriptions(root), days), ["stub", "project", "<name>", "--path", "<cwd>"]
            if what != "people":
                raise WikiError("scan takes people or projects")
            clients = {k: mail_client(k) for k in ("outlook", "gmail")}
            rows = [p for p in scan_people(clients, days, set(mine)) if p["mails"] >= min_mails]
            return rows, ["stub", "person", "<name>", "--handle", "<address>"]
        from ...wiki.files import WikiError
        _handle(ctx, run, ["status"])

    @wiki.command("stub")
    def stub_page(ctx: typer.Context,
                  kind: str = typer.Argument(..., help="person or project"),
                  name: str = typer.Argument(..., help="The page title"),
                  handle: List[str] = typer.Option([], "--handle", help="A spelling, address or alias (repeatable)"),
                  path: List[str] = typer.Option([], "--path", help="project: a directory it lives at (repeatable)"),
                  email: str = typer.Option("", "--email", help="person: the address it was found by")):
        """Create a page with its structure already in place; every unknown section says so. No model."""
        import re
        from ...wiki.files import Notebook, WikiError

        def run(root):
            slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", name.lower()).strip("-") or "page"
            notebook = Notebook(root)
            if kind == "person":
                record = f"people/{slug}.md"
                made = notebook.stub_person(record, name, handle, email=email)
            elif kind == "project":
                record = f"projects/{slug}.md"
                made = notebook.stub_project(record, name, path)
            else:
                raise WikiError("stub takes person or project")
            return {"record": record, "created": made}, ["investigate", record, *sum((["--handle", h] for h in handle), [])]
        _handle(ctx, run, ["unfinished"])

    @wiki.command("unfinished")
    def list_unfinished(ctx: typer.Context, category: str = typer.Argument("", help="people, projects, or all")):
        """Pages still carrying an Unknown section, least-investigated first. The notebook's own work list."""
        from ...wiki.files import Notebook
        _handle(ctx, lambda root: (Notebook(root).unfinished(category), ["investigate", "<path>"]), ["status"])

    @wiki.command("investigate")
    def investigate_page(ctx: typer.Context,
                         record: str = typer.Argument(..., help="The page, e.g. people/emma.md"),
                         handle: List[str] = typer.Option([], "--handle", help="Every spelling, address or alias (repeatable)"),
                         days: int = typer.Option(150, "--days", help="How far back to search")):
        """Fill one page from everything every source holds about its subject. One model turn."""
        from ...wiki.files import Notebook
        from ...wiki.investigate import investigate
        from ...wiki.service import mail_client, subscriptions

        def run(root):
            notebook = Notebook(root)
            text = notebook.read(record)
            title = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), record)
            known = []
            for line in text.splitlines():
                low = line.strip().lstrip("-").strip().casefold()
                if low.startswith(("also known as:", "email:", "handles:")) and ":" in line:
                    known += [h.strip() for h in line.split(":", 1)[1].replace("、", ",").split(",") if h.strip() and h.strip() != "Unknown"]
            handles = list(dict.fromkeys([*handle, *known, title.split(" (")[0]]))
            clients = {k: mail_client(k) for k in ("outlook", "gmail")}
            result = investigate(root, record, title, handles, days=days, clients=clients,
                                 subscriptions=subscriptions(root),
                                 progress=lambda k, stop, n: typer.echo(f"  {k}: to {stop:%Y-%m-%d}, {n} mails", err=True))
            return result, ["show", record]
        _handle(ctx, run, ["unfinished"])

    config_app = factory(help="Inspect or explicitly change Wiki configuration.", no_args_is_help=False)
    wiki.add_typer(config_app, name="config")

    @config_app.callback(invoke_without_command=True)
    def inspect_config(ctx: typer.Context):
        from ...wiki.config import read_config
        if ctx.invoked_subcommand is None:
            _handle(ctx, lambda root: ({"path": str(root / "config.yaml"),
                                       "saved": (root / "config.yaml").exists(),
                                       "config": read_config(root, validated=False)}, ["status"]), ["doctor"])

    @config_app.command("set")
    def change_config(ctx: typer.Context, values: List[str] = typer.Argument(..., help="KEY VALUE pairs")):
        """Validate all supplied settings before saving; never starts collection."""
        from ...wiki.config import set_config
        _handle(ctx, lambda root: (set_config(root, values), ["config"]), ["config"])

    @wiki.command("list")
    def list_records(ctx: typer.Context, category: str = typer.Argument("", help="Category, e.g. people or notes")):
        """List current Markdown paths without inference."""
        from ...wiki.files import Notebook
        def operation(root):
            records = Notebook(root).list(category)
            return records, ["show", records[0]] if records else ["status"]
        _handle(ctx, operation, ["list"])

    @wiki.command("show")
    def show_record(ctx: typer.Context, record: str = typer.Argument(..., help="Path returned by list/search")):
        """Read one Markdown record; does not edit it."""
        from ...wiki.files import CATEGORIES, Notebook
        category = record.split("/")[0]
        recovery = ["list", category] if category in CATEGORIES else ["list"]
        _handle(ctx, lambda root: (Notebook(root).read(record), recovery), recovery)

    @wiki.command("search")
    def search_records(ctx: typer.Context, query: str = typer.Argument(...),
                       category: str = typer.Option("", "--type", help="Restrict to one category")):
        """Literal case-insensitive search; no embeddings or model call."""
        from ...wiki.files import Notebook
        def operation(root):
            found = Notebook(root).search(query, category)
            return found, ["show", found[0]["record"]] if found else ["list"]
        _handle(ctx, operation, ["list"])

    @wiki.command("logs")
    def inspect_logs(ctx: typer.Context, run_id: str = typer.Option("", "--run", help="ID from the run listing")):
        """Show local run outcomes and known/unknown usage."""
        from ...wiki.service import run_logs
        def operation(root):
            records = run_logs(root, run_id)[:20]
            next_args = ["logs", "--run", records[0]["id"]] if records and not run_id else ["status"]
            return records, next_args
        _handle(ctx, operation, ["logs"])

    @wiki.command("start")
    def start_wiki(ctx: typer.Context,
                   yes: bool = typer.Option(False, "--yes", help="Consent without a prompt (after reading the summary)")):
        """Confirm source access once, install the background schedule, run the first batch."""
        import sys

        from ...wiki import schedule as wiki_schedule
        from ...wiki.files import WikiError
        from ...wiki.service import start

        def confirm(summary):
            text = json.dumps(summary, ensure_ascii=False, indent=2)
            if yes:
                return True
            if not sys.stdin.isatty():
                typer.echo(text, err=True)
                typer.echo("Noninteractive first start cannot consent silently; read the summary above "
                           "and run with --yes, or run `co wiki start` in a terminal.", err=True)
                return False
            typer.echo(text)
            return typer.confirm("Read these sources with this model and schedule?", default=False)

        def operation(root):
            result = start(root, confirm=confirm, scheduler=wiki_schedule.default_scheduler())
            if not result["started"]:
                raise WikiError("Start was not confirmed; nothing was read or installed")
            return result, ["status"]

        _handle(ctx, operation, ["start", "--yes"] if not yes else ["doctor"])

    @wiki.command("stop")
    def stop_wiki(ctx: typer.Context):
        """Turn background maintenance off; notes, consent and manual sync remain."""
        from ...wiki import schedule as wiki_schedule
        from ...wiki.service import stop
        _handle(ctx, lambda root: (stop(root, scheduler=wiki_schedule.default_scheduler()), ["start"]), ["status"])

    @wiki.command("sync")
    def sync_wiki(ctx: typer.Context,
                  source: str = typer.Option("", "--source", help="Only this subscription"),
                  with_person: str = typer.Option("", "--with", help="Mail only: just this correspondent, named by "
                                                                     "address or part of one. Everyone else keeps "
                                                                     "their place in the queue"),
                  dry_run: bool = typer.Option(False, "--dry-run", help="Pending file metadata only; no body reads"),
                  scheduled: bool = typer.Option(False, "--scheduled",
                                                 help="Only if a saved time has come due since the last scheduled "
                                                      "batch (what the background job passes); otherwise exit at once"),
                  all_pending: bool = typer.Option(False, "--all",
                                                   help="Backfill: batch after batch, oldest first, until nothing is "
                                                        "pending; not limited by the daily attempt cap")):
        """Run one bounded incremental batch now (does not enable the background schedule)."""
        from ...wiki.files import WikiError
        from ...wiki.service import run_sync

        def operation(root):
            record = run_sync(root, source=source, with_person=with_person, dry_run=dry_run,
                              scheduled=scheduled, all_pending=all_pending)
            if scheduled and record is None:
                return {"due": False, "ran": False}, ["status"]
            if all_pending:
                if record["outcome"] not in ("caught_up",):
                    raise WikiError(f"Backfill stopped after {record['batches']} batches: {record['outcome']}")
                return record, ["status"]
            if dry_run:
                return record, ["sync"]
            if record["outcome"] == "failed":
                # A failed batch must not exit 0: an agent chaining `sync && ...` would walk past it.
                raise WikiError(f"Batch {record['id']} failed: {record.get('error')}")
            return record, ["logs", "--run", record["id"]]
        _handle(ctx, operation, ["logs"])

    @wiki.command("subscribe")
    def subscribe(ctx: typer.Context, name: str = typer.Argument(..., help="codex, claude-code, gmail, outlook"),
                  project: str = typer.Option("", "--project",
                                              help="Coding sources: a scope of its own for sessions run in this "
                                                   "directory"),
                  about: str = typer.Option("", "--about",
                                            help="Coding sources: a scope of its own for sessions that mention this, "
                                                 "whole sessions, whichever directory they ran in"),
                  since: str = typer.Option("", "--since",
                                            help="Read back at least this far: 3d, 2w, 6m, 1y. A window already "
                                                 "wider than this is left alone"),
                  only: bool = typer.Option(False, "--only",
                                            help="With --since: read *only* that far back, narrowing the window"),
                  force: bool = typer.Option(False, "--force", help="Accept dropping unread material when narrowing")):
        """Enable or restore a source; bodies are read only after `start` has been confirmed."""
        from ...wiki.service import set_window, toggle_source

        def operation(root):
            subscription = toggle_source(root, name, True, project=project, about=about,
                                         since=since or "60d")
            result = {"subscription": subscription, "enabled": True}
            if since and not (project or about):
                result.update(set_window(root, subscription, since, narrow=only, force=force))
            return result, ["subscriptions"]
        _handle(ctx, operation, ["subscriptions"])

    @wiki.command("unsubscribe")
    def unsubscribe(ctx: typer.Context, name: str = typer.Argument(..., help="Name from `co wiki subscriptions`")):
        """Stop future reads from this source for good; existing notes stay."""
        from ...wiki.service import toggle_source
        _handle(ctx, lambda root: ({"subscription": toggle_source(root, name, False), "enabled": False},
                                   ["subscriptions"]), ["subscriptions"])

    @wiki.command("usage")
    def usage(ctx: typer.Context, days: int = typer.Option(0, "--days", help="Only runs from the last N days")):
        """Where the tokens went: totals, by stage, by model, by source, from the raw run records."""
        from ...wiki.service import usage_report
        _handle(ctx, lambda root: (usage_report(root, days or None), ["logs"]), ["logs"])

    @wiki.command("open")
    def open_page(ctx: typer.Context,
                  launch: bool = typer.Option(True, "--launch/--no-launch",
                                              help="Open the rendered page in the default browser")):
        """Render the notebook to a disposable local HTML page; no edits, no model."""
        from ...wiki.reader import open_reader

        def operation(root):
            page = open_reader(root, launch=launch)
            return {"page": str(page), "launched": launch,
                    "note": "a snapshot; run this command again after the next maintenance pass"}, ["status"]
        _handle(ctx, operation, ["doctor"])

    @wiki.command("doctor")
    def doctor(ctx: typer.Context):
        """Inspect local prerequisites; no native process, login, or repair."""
        import shutil

        from ...wiki.config import read_config, validate
        def operation(root):
            validate(read_config(root))
            return {"codex_binary_found": bool(shutil.which("codex")),
                    "native_isolation": "not verified by this read-only check",
                    "collection_cli": "not shipped", "background": "not shipped"}, ["status"]
        _handle(ctx, operation, ["config"])

    return wiki
