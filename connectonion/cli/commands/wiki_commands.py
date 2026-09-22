"""Experimental Wiki inspection. No collection or provider startup on import."""

import json
import shlex
from pathlib import Path
from typing import List, Optional

import typer

from .wiki_output import guide, render


def _next(ctx, arguments):
    """The next command, spelled the way the user invoked this one.

    A thin wrapper (`remi status`) that forwards to `co wiki` is only a product
    if the tips agree with it; a user told `co wiki --root /long/path logs` has
    been handed the wiring. The wrapper names itself in CO_WIKI_PROGRAM and every
    Next line follows. The root is spelled out only when it is not the default,
    which is also what makes a tip short enough to copy.
    """
    import os
    program = shlex.split(os.environ.get("CO_WIKI_PROGRAM") or "co wiki")
    root = ctx.obj["root"]
    default = (Path.home() / ".co/wiki").expanduser().resolve()
    location = [] if root == default else ["--root", str(root)]
    return shlex.join([*program, *location, *arguments])


def _emit(ctx, value, arguments, *, failed=False):
    command = _next(ctx, arguments)
    if ctx.obj["json"]:
        typer.echo(json.dumps({"ok": not failed, "data": value, "next": command}, ensure_ascii=False))
    else:
        text = render(value, ctx.info_name or "status", failed=failed)
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


def _investigation_pages(notebook):
    return [path for path in notebook.list()
            if path.startswith(("people/", "projects/", "orgs/", "skills/catalog/"))
            and path != "skills/catalog/index.md"]


def _resolve_page(notebook, selector):
    from ...wiki.files import WikiError
    pages = _investigation_pages(notebook)
    if selector in notebook.list():
        return selector
    people = {person["path"]: person for person in notebook.people()}
    matches = []
    for path in pages:
        title = next((line[2:].strip() for line in notebook.read(path).splitlines()
                      if line.startswith("# ")), "")
        person = people.get(path, {})
        names = [title, Path(path).stem, *person.get("emails", []), *person.get("aliases", [])]
        if selector.casefold() in [name.casefold() for name in names]:
            matches.append(path)
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise WikiError("More than one page matches. Use an exact path:\n" + "\n".join(matches))
    raise WikiError("No page matches that name, email or path. Run investigate without arguments to see available pages.")


def make_wiki_app(factory):
    wiki = factory(help=guide(lambda args: shlex.join(["co", "wiki", *args])),
                   no_args_is_help=False)

    @wiki.callback(invoke_without_command=True)
    def overview(ctx: typer.Context,
                 root: Optional[Path] = typer.Option(None, "--root", help="Notebook root (default ~/.co/wiki)"),
                 json_out: bool = typer.Option(False, "--json", help="Machine-readable output with next command")):
        ctx.obj = {"root": (root or Path.home() / ".co/wiki").expanduser().resolve(), "json": json_out}
        if ctx.invoked_subcommand is None:
            if ctx.obj["json"]:
                inspect_status(ctx)
            else:
                from ...wiki.service import status
                typer.echo(guide(lambda args: _next(ctx, args)))
                def operation(root):
                    result = status(root)
                    return result, ["unfinished"] if result["configured"] else ["init"]
                _handle(ctx, operation, ["config"])

    @wiki.command("daily", rich_help_panel="3. Update and review")
    def daily_round(ctx: typer.Context, days: int = typer.Option(30, "--days", min=1)):
        """Maintain current material, then investigate at most one unfinished page."""
        from ...wiki.daily import run_daily
        def operation(root):
            result = run_daily(root, days=days)
            if result["outcome"] == "partial":
                _emit(ctx, result, ["logs"], failed=True)
            return result, ["logs"]
        _handle(ctx, operation, ["status"])

    @wiki.command("capture", rich_help_panel="3. Update and review")
    def capture_session(ctx: typer.Context, transcript: Path,
                        source: str = typer.Option(..., "--source")):
        """Capture local user messages into a durable queue; no model or sync."""
        from ...wiki.capture import capture
        _handle(ctx, lambda root: (capture(root, transcript.expanduser().resolve(), source), ["sync"]), ["status"])

    @wiki.command("reflect", rich_help_panel="3. Update and review")
    def reflect(ctx: typer.Context, subject: str, statement: str,
                author: str = typer.Option(..., "--author"),
                basis: str = typer.Option(..., "--basis"),
                previous: str = typer.Option("", "--previous"),
                applies: str = typer.Option("", "--applies"),
                kind: str = typer.Option("reflection", "--kind"),
                source: List[str] = typer.Option([], "--source"),
                supersedes: List[str] = typer.Option([], "--supersedes")):
        """Retain an attributed reflection, correction or real-world change."""
        from ...wiki.reflections import add
        _handle(ctx, lambda root: (add(root, subject, statement, author=author, basis=basis,
                 previous=previous, applies=applies, kind=kind, sources=source, supersedes=supersedes),
                 ["reflections", subject]), ["list"])

    @wiki.command("reflections", rich_help_panel="3. Update and review")
    def reflection_records(ctx: typer.Context, subject: str = typer.Argument(""),
                           compact: bool = typer.Option(False, "--compact")):
        """Read retained reflections or write a lossless compact view; no deletion."""
        from ...wiki.reflections import records, compress
        _handle(ctx, lambda root: (compress(root, subject) if compact else records(root, subject),
                                  ["list"]), ["list"])

    @wiki.command("propose", rich_help_panel="3. Update and review")
    def propose_review(ctx: typer.Context, kind: str, subject: str, question: str,
                       basis: str = typer.Option(..., "--basis"),
                       related: str = typer.Option("", "--related")):
        """Save an evidence-linked question or candidate connection for review."""
        from ...wiki.reviews import propose
        _handle(ctx, lambda root: (propose(root, kind, [subject, related] if related else [subject],
                                         question, basis), ["review"]), ["list"])

    @wiki.command("review", rich_help_panel="3. Update and review")
    def review_candidates(ctx: typer.Context, review_id: str = typer.Argument(""),
                          verdict: str = typer.Option("", "--verdict"),
                          author: str = typer.Option("", "--author"),
                          response: str = typer.Option("", "--response"),
                          audio: Optional[Path] = typer.Option(None, "--audio"),
                          local_model: Optional[Path] = typer.Option(None, "--local-model")):
        """List questions/links, or explicitly answer/accept/reject a candidate."""
        from ...wiki.reviews import listing, decide
        def operation(root):
            from ...wiki.files import WikiError
            text = response
            if audio:
                if not review_id or not local_model or response:
                    raise WikiError("Audio response needs a review ID and --local-model; do not also pass --response")
                from ...wiki.voice import transcribe
                text = transcribe(audio, local_model)
            return (decide(root, review_id, verdict, author=author, response=text)
                    if review_id else listing(root)), ["review"]
        _handle(ctx, operation, ["review"])

    @wiki.command("route", rich_help_panel="5. Settings and diagnostics")
    def route_stage(ctx: typer.Context, stage: str = typer.Argument(""),
                    runner: str = typer.Option("", "--runner"),
                    model: str = typer.Option("", "--model"),
                    clear: bool = typer.Option(False, "--clear")):
        """Inspect or explicitly choose a stage model; enables planned investigation."""
        from ...wiki.inquiry import routing, set_route, clear_route
        def operation(root):
            from ...wiki.files import WikiError
            if clear and (runner or model):
                raise WikiError("Do not combine --clear with --runner or --model")
            value = clear_route(root, stage) if clear else set_route(root, stage, runner, model) if stage else routing(root)
            return value, ["route"]
        _handle(ctx, operation, ["route"])

    @wiki.command("status", rich_help_panel="2. Browse pages")
    def inspect_status(ctx: typer.Context):
        """Show local run counts, known usage, and background readiness."""
        from ...wiki.service import status
        _handle(ctx, lambda root: (status(root), ["logs"]), ["config"])

    @wiki.command("init", rich_help_panel="Commands — 1. Map and investigate")
    def init_wiki(ctx: typer.Context,
                  days: int = typer.Option(150, "--days", min=1),
                  skills_dir: List[Path] = typer.Option([], "--skills-dir"),
                  mine: List[str] = typer.Option([], "--mine"),
                  mail: List[str] = typer.Option([], "--mail", help="Only map these mailboxes: gmail or outlook (repeatable); default: connected mailboxes")):
        """Build people, organization, project and skill maps; no model or investigation.

        When to use: Run co wiki init for a new notebook or to refresh its map.
        Existing authored pages are preserved. This reads available source metadata
        and installed Skill text; it does not run a model or enable a schedule.

        Expected result: Source coverage, created pages and an explicit not-started
        investigation state. Then run co wiki investigate to choose a real page.
        Mapped does not mean researched or verified.

        If sources are missing: Read the coverage and setup tips. Run co auth status
        to inspect mailbox access, then retry init after connecting the missing source.
        --skills-dir replaces default Skill roots; repeat it to include multiple roots.
        """
        from ...wiki.config import prepare
        from ...wiki.map import build_map
        from ...wiki.service import mail_available, mail_client, subscriptions

        def run(root):
            prepare(root)
            sources = subscriptions(root)
            from ...wiki.files import WikiError
            selected = set(mail)
            if selected - {"gmail", "outlook"}:
                raise WikiError("--mail must be gmail or outlook")
            available = {kind for kind in ("gmail", "outlook") if mail_available(kind)}
            if not mail:
                selected.update(available)
                selected.update(sub["kind"] for sub in sources.values()
                                if sub.get("kind") in ("gmail", "outlook") and sub.get("enabled"))
            clients, errors = {}, []
            for kind in sorted(selected):
                try:
                    clients[kind] = mail_client(kind)
                except Exception as error:
                    errors.append({"source": kind, "stage": "client", "error": type(error).__name__})
            result = build_map(root, sources, clients, days=days,
                               skill_directories=skills_dir or None, mine=mine, source_errors=errors)
            tips = []
            for kind, provider in (("gmail", "google"), ("outlook", "microsoft")):
                if kind not in available:
                    tips.append(f"Connect {provider.title()} for People: co auth {provider}; then run "
                                + _next(ctx, ["init"]) + ".")
            if tips:
                result["tips"] = tips
            if not selected:
                result["people_setup"] = "No connected mail source. Local maps are ready; connect mail to add People."
            if result.get("errors"):
                result["recovery"] = "Check mailbox access with co auth status; retry init with --mail after resolving access. Completed maps are preserved."
                _emit(ctx, result, ["init", "--mail", sorted(selected)[0]], failed=True)
                raise typer.Exit(1)
            return result, ["unfinished"]
        _handle(ctx, run, ["subscriptions"])

    @wiki.command("map-skills", rich_help_panel="Commands — 1. Map and investigate")
    def map_skill_pages(ctx: typer.Context,
                        skills_dir: List[Path] = typer.Option([], "--skills-dir", help="Explicit skill roots instead of defaults (repeatable)")):
        """Build the installed-Skill map and missing page skeletons; no model, no execution."""
        from ...wiki.files import Notebook
        from ...wiki.skill_map import map_skills
        _handle(ctx, lambda root: (map_skills(Notebook(root), skills_dir or None),
                                  ["show", "skills/catalog/index.md"]), ["status"])

    @wiki.command("people", rich_help_panel="2. Browse pages")
    def list_people(ctx: typer.Context):
        """List known identities, aliases and contact addresses; no source reads."""
        from ...wiki.files import Notebook
        _handle(ctx, lambda root: (Notebook(root).people(), ["list", "people"]), ["list", "people"])

    @wiki.command("abstract", rich_help_panel="3. Update and review")
    def abstract_pages(ctx: typer.Context):
        """Run the abstraction Skill on existing pages and their evidence."""
        from ...wiki.config import read_config
        from ...wiki.files import Notebook
        from ...wiki.runner import run_stage
        _handle(ctx, lambda root: (
            run_stage(Notebook(root), [], read_config(root), stage="abstract"), ["list"]), ["status"])

    @wiki.command("subscriptions", rich_help_panel="4. Sources and background")
    def inspect_subscriptions(ctx: typer.Context):
        """Show saved source choices or unsaved defaults; no body reads."""
        from ...wiki.service import subscriptions
        _handle(ctx, lambda root: (subscriptions(root), ["status"]), ["config"])

    @wiki.command("scan", rich_help_panel="Commands — 1. Map and investigate")
    def scan_sources(ctx: typer.Context,
                     what: str = typer.Argument("people", help="people, orgs or projects"),
                     days: int = typer.Option(150, "--days", min=1, help="How far back to look"),
                     min_mails: int = typer.Option(3, "--min-mails", help="people: fewer than this is not listed"),
                     min_people: int = typer.Option(2, "--min-people",
                                                    help="orgs: a work domain fewer people write from stays a "
                                                         "Company field on their own page"),
                     mine: List[str] = typer.Option([], "--mine", help="An address that is yours (repeatable)")):
        """Enumerate correspondents, organisations or projects from the sources. No model."""
        from ...wiki.scan import scan_orgs, scan_people, scan_projects
        from ...wiki.service import mail_client, subscriptions

        def run(root):
            if what == "projects":
                rows = scan_projects(subscriptions(root), days)
                return rows, (["stub", "project", rows[0]["name"], "--path", rows[0]["path"]]
                              if rows else ["subscriptions"])
            if what not in ("people", "orgs"):
                raise WikiError("scan takes people, orgs or projects")
            clients = {k: mail_client(k) for k in ("outlook", "gmail")}
            rows = [p for p in scan_people(clients, days, set(mine)) if p["mails"] >= min_mails]
            if what == "orgs":
                own = set(mine) | {a for c in clients.values() for a in c.my_addresses()}
                orgs = scan_orgs(rows, min_people=min_people, own_addresses=own)
                return orgs, (["stub", "org", orgs[0]["domain"], "--domain", orgs[0]["domain"]]
                              if orgs else ["subscriptions"])
            return rows, (["stub", "person", rows[0]["name"] or rows[0]["address"],
                           "--email", rows[0]["address"], "--handle", rows[0]["address"]]
                          if rows else ["subscriptions"])
        from ...wiki.files import WikiError
        _handle(ctx, run, ["status"])

    @wiki.command("stub", rich_help_panel="Commands — 1. Map and investigate")
    def stub_page(ctx: typer.Context,
                  kind: str = typer.Argument(..., help="person, org or project"),
                  name: str = typer.Argument(..., help="The page title"),
                  handle: List[str] = typer.Option([], "--handle", help="A spelling, address or alias (repeatable)"),
                  path: List[str] = typer.Option([], "--path", help="project: a directory it lives at (repeatable)"),
                  domain: List[str] = typer.Option([], "--domain", help="org: a mail domain it owns (repeatable)"),
                  person: List[str] = typer.Option([], "--person",
                                                   help="org: a person page that belongs to it (repeatable)"),
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
            elif kind == "org":
                record = f"orgs/{slug}.md"
                made = notebook.stub_org(record, name, domain, people=person)
            else:
                raise WikiError("stub takes person, org or project")
            return {"record": record, "created": made}, ["investigate", record, *sum((["--handle", h] for h in handle), [])]
        _handle(ctx, run, ["unfinished"])

    @wiki.command("unfinished", rich_help_panel="Commands — 1. Map and investigate")
    def list_unfinished(ctx: typer.Context, category: str = typer.Argument("", help="people, projects, or all")):
        """Pages still carrying an Unknown section, least-investigated first. The notebook's own work list."""
        from ...wiki.files import Notebook
        def operation(root):
            pages = Notebook(root).unfinished(category)
            return pages, ["investigate", pages[0]["path"]] if pages else ["list"]
        _handle(ctx, operation, ["status"])

    @wiki.command("investigate", rich_help_panel="Commands — 1. Map and investigate")
    def investigate_page(ctx: typer.Context,
                         record: str = typer.Argument("", help="Exact page path, unique title or email. Omit to list your pages; no model runs."),
                         handle: List[str] = typer.Option([], "--handle", help="Every spelling, address or alias (repeatable)"),
                         days: int = typer.Option(150, "--days", min=1, help="How far back to search"),
                         eval_dir: List[Path] = typer.Option([], "--eval-dir", help="Skill run summary directory (repeatable; skills only)")):
        """Investigate one existing page; omit the argument to discover available pages.

        When to use: Fill an existing page from its available evidence.

        Choose the input: Run co wiki investigate without arguments. It lists real
        pages without running a model. Copy the printed Next command, or supply
        one exact title or email from your notebook. Do not copy fictional paths
        from examples. With no pages, run co wiki init first.

        More than one match: Use an exact path from the reported choices. A missing
        or ambiguous selection does not start a model. --handle adds known aliases;
        --days limits the search window. Skill pages use retained run evidence;
        --eval-dir selects that evidence directory, not the original Skill directory.

        Check the result: Follow the printed show command and review sources,
        Unknown sections and coverage. A completed command is not a factual-quality
        verdict; incomplete evidence remains incomplete. Use co wiki unfinished
        to find remaining gaps.

        Use --help only to read options; it never runs an investigation.
        """
        from ...wiki.files import Notebook
        from ...wiki.investigate import investigate
        from ...wiki.service import mail_client, subscriptions

        def run(root):
            notebook = Notebook(root)
            if not record:
                pages = _investigation_pages(notebook)
                return pages, ["investigate", pages[0]] if pages else ["init"]
            selected = _resolve_page(notebook, record)
            return investigate_selected(root, notebook, selected)

        def investigate_selected(root, notebook, record):
            if record.startswith("skills/"):
                from ...wiki.skill_runs import investigate_skill_runs
                result = investigate_skill_runs(root, record, eval_dir or [Path.home() / ".co/evals"])
                return result, ["show", result["report"]]
            if eval_dir:
                raise typer.BadParameter("--eval-dir applies only to skills/catalog pages")
            text = notebook.read(record)
            title = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), record)
            known = []
            if record.startswith("people/"):
                person = next((p for p in notebook.people() if p["path"] == record), {})
                known += person.get("emails", []) + person.get("aliases", [])
            for line in text.splitlines():
                low = line.strip().lstrip("-").strip().casefold()
                if low.startswith(("also known as:", "email:", "handles:")) and ":" in line:
                    known += [h.strip() for h in line.split(":", 1)[1].replace("、", ",").split(",") if h.strip() and h.strip() != "Unknown"]
            handles = list(dict.fromkeys([*handle, *known, title.split(" (")[0]]))
            sources = subscriptions(root)
            clients = {sub["kind"]: mail_client(sub["kind"], attachments=True) for sub in sources.values()
                       if sub.get("kind") in ("outlook", "gmail") and sub.get("enabled")}
            result = investigate(root, record, title, handles, days=days, clients=clients,
                                 subscriptions=subscriptions(root),
                                 progress=lambda k, stop, n: typer.echo(f"  {k}: to {stop:%Y-%m-%d}, {n} mails", err=True))
            return result, ["show", record]
        _handle(ctx, run, ["investigate"])

    config_app = factory(help="Inspect or explicitly change Wiki configuration.", no_args_is_help=False)
    wiki.add_typer(config_app, name="config", rich_help_panel="5. Settings and diagnostics")

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

    @wiki.command("list", rich_help_panel="2. Browse pages")
    def list_records(ctx: typer.Context, category: str = typer.Argument("", help="Category, e.g. people or notes")):
        """List current Markdown paths without inference."""
        from ...wiki.files import Notebook
        def operation(root):
            records = Notebook(root).list(category)
            return records, ["show", records[0]] if records else ["status"]
        _handle(ctx, operation, ["list"])

    @wiki.command("show", rich_help_panel="2. Browse pages")
    def show_record(ctx: typer.Context, record: str = typer.Argument(..., help="Path returned by list/search")):
        """Read one Markdown record; does not edit it."""
        from ...wiki.files import CATEGORIES, Notebook
        category = record.split("/")[0]
        recovery = ["list", category] if category in CATEGORIES else ["list"]
        _handle(ctx, lambda root: (Notebook(root).read(record), recovery), recovery)

    @wiki.command("search", rich_help_panel="2. Browse pages")
    def search_records(ctx: typer.Context, query: str = typer.Argument(...),
                       category: str = typer.Option("", "--type", help="Restrict to one category")):
        """Literal case-insensitive search; no embeddings or model call."""
        from ...wiki.files import Notebook
        def operation(root):
            found = Notebook(root).search(query, category)
            return found, ["show", found[0]["record"]] if found else ["list"]
        _handle(ctx, operation, ["list"])

    @wiki.command("logs", rich_help_panel="5. Settings and diagnostics")
    def inspect_logs(ctx: typer.Context, run_id: str = typer.Option("", "--run", help="ID from the run listing")):
        """Show local run outcomes and known/unknown usage."""
        from ...wiki.service import run_logs
        def operation(root):
            records = run_logs(root, run_id)[:20]
            next_args = ["logs", "--run", records[0]["id"]] if records and not run_id else ["status"]
            return records, next_args
        _handle(ctx, operation, ["logs"])

    @wiki.command("start", rich_help_panel="4. Sources and background")
    def start_wiki(ctx: typer.Context,
                   yes: bool = typer.Option(False, "--yes", help="Consent without a prompt (after reading the summary)")):
        """Confirm source access once, install the background schedule, run the first batch."""
        import sys

        from ...wiki import schedule as wiki_schedule
        from ...wiki.files import WikiError
        from ...wiki.service import start

        def confirm(summary):
            text = render(summary, "start — source access and schedule")
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

    @wiki.command("stop", rich_help_panel="4. Sources and background")
    def stop_wiki(ctx: typer.Context):
        """Turn background maintenance off; notes, consent and manual sync remain."""
        from ...wiki import schedule as wiki_schedule
        from ...wiki.service import stop
        _handle(ctx, lambda root: (stop(root, scheduler=wiki_schedule.default_scheduler()), ["start"]), ["status"])

    @wiki.command("sync", rich_help_panel="3. Update and review")
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
        """Run one bounded incremental batch now (does not enable the background schedule).

        Before running: Use co wiki sync --dry-run to inspect pending metadata
        without reading bodies or calling a model. Use co wiki subscriptions
        to check which sources are enabled.

        Source access must already be authorized. co wiki start reviews and confirms
        access AND installs a background schedule; it is not required for map building
        or page discovery. Do not run it just to dismiss an error without reviewing
        the source/model/schedule summary.

        Then run co wiki sync for one bounded batch. --all explicitly backfills all
        pending batches and bypasses the daily attempt cap. --source selects a saved
        subscription; --with limits mail to a correspondent.

        Check co wiki logs, or the printed run-specific Next command, for changes,
        failures and usage. A dry run or no_change result does not mean the Wiki
        has been researched. Do not repeatedly retry a failed model run without
        inspecting the failure.
        """
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

    @wiki.command("subscribe", rich_help_panel="4. Sources and background")
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

    @wiki.command("unsubscribe", rich_help_panel="4. Sources and background")
    def unsubscribe(ctx: typer.Context, name: str = typer.Argument(..., help="Name from `co wiki subscriptions`")):
        """Stop future reads from this source for good; existing notes stay."""
        from ...wiki.service import toggle_source
        _handle(ctx, lambda root: ({"subscription": toggle_source(root, name, False), "enabled": False},
                                   ["subscriptions"]), ["subscriptions"])

    @wiki.command("usage", rich_help_panel="5. Settings and diagnostics")
    def usage(ctx: typer.Context, days: int = typer.Option(0, "--days", help="Only runs from the last N days")):
        """Where the tokens went: totals, by stage, by model, by source, from the raw run records."""
        from ...wiki.service import usage_report
        _handle(ctx, lambda root: (usage_report(root, days or None), ["logs"]), ["logs"])

    @wiki.command("open", rich_help_panel="2. Browse pages")
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

    @wiki.command("doctor", rich_help_panel="5. Settings and diagnostics")
    def doctor(ctx: typer.Context):
        """Inspect local prerequisites; no native process, login, or repair."""
        import shutil

        from ...wiki.config import read_config, validate
        def operation(root):
            validate(read_config(root))
            return {"codex_binary_found": bool(shutil.which("codex")),
                    "native_isolation": "not verified by this read-only check",
                    "collection_cli": "available: co wiki sync",
                    "background": "available on macOS via co wiki start"}, ["status"]
        _handle(ctx, operation, ["config"])

    order = ("init investigate unfinished map-skills scan stub "
             "open list show search people status "
             "sync daily capture reflect reflections propose review abstract "
             "subscriptions subscribe unsubscribe start stop route logs usage doctor").split()
    wiki.registered_commands.sort(key=lambda command: order.index(command.name))
    return wiki
