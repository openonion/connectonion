"""Experimental Wiki inspection. No collection or provider startup on import."""

import json
import re
import shlex
from pathlib import Path
from typing import List, Optional

import typer

from .wiki_help import page, verbatim
from .wiki_output import render


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


def _absent_mail(selected, available, failed, sources, chosen_by_hand) -> dict:
    """Why each mailbox is not in this map, in the words of the fix it needs.

    Four states the init contract requires to stay apart, because each sends the
    user somewhere different: never connected (co auth), connected but switched
    off (subscribe), connected and asked for but it would not open (co auth
    status), and deliberately left out of this run by --mail. From inside the
    map they are one thing -- an absent client -- so the answer is assembled
    here, where the command already knows all four (#1616).
    """
    reasons = {}
    for kind, provider in (("gmail", "google"), ("outlook", "microsoft")):
        if kind in selected and kind not in failed:
            continue
        if kind in failed:
            reasons[kind] = (f"authorized but could not be opened ({failed[kind]}); not searched. "
                             f"Check access with co auth status")
        elif kind not in available:
            reasons[kind] = f"not connected; not searched. Connect it with co auth {provider}"
        elif sources.get(kind, {}).get("unsubscribed"):
            reasons[kind] = (f"unsubscribed by the user; not searched. "
                             f"Restore it with co wiki subscribe {kind}")
        elif chosen_by_hand:
            reasons[kind] = "connected, left out of this run by --mail; not searched"
        else:
            reasons[kind] = "connected but not read this run; not searched"
    return reasons


def _emit(ctx, value, arguments, *, failed=False):
    command = _next(ctx, arguments)
    if ctx.obj["json"]:
        typer.echo(json.dumps({"ok": not failed, "data": value, "next": command}, ensure_ascii=False))
    else:
        path, parent = [ctx.info_name or "status"], ctx.parent
        while parent is not None and parent.info_name not in (None, "wiki") and parent.parent is not None:
            path.insert(0, parent.info_name)
            parent = parent.parent
        text = render(value, " ".join(path), failed=failed)
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
        # An error that says what to run is the Next line too. `sync` before
        # `start` said "run co wiki start" and then printed "Next: co wiki logs".
        named = re.search(r"`co wiki ([^`<>]+)`", message)
        _emit(ctx, message, shlex.split(named.group(1)) if named else recovery, failed=True)
        return
    _emit(ctx, value, arguments)


def _moved(ctx, old: str, new: list):
    """An old name still works, and says what it is called now (#1656)."""
    typer.echo(f"`co wiki {old}` is now `{_next(ctx, new)}`; the old name works until 1.9.", err=True)


def _logged(root, record, phase, call):
    """Run one investigation and keep a run record of it, whatever happens.

    Investigations are the Wiki's most expensive calls and `co wiki logs` did
    not list a single one: on a notebook with a dozen investigated pages it
    said "No runs recorded". A manual run is not charged to the background
    daily cap (runner_attempts stays 0), but its usage counts in logs --usage.
    """
    import uuid
    from ...wiki.config import read_config
    from ...wiki.files import state_path, write_json
    from ...wiki.runner import RunFailed
    from ...wiki.service import now
    run = {"id": "run_" + uuid.uuid4().hex, "started_at": now().isoformat(), "phase": phase,
           "record": record, "model": read_config(root)["model"], "outcome": "running",
           "runner_attempts": 0, "usage": None, "changed": [], "sources": [], "items": 0}
    path = state_path(root, f"runs/{run['id']}.json")
    write_json(path, run)
    try:
        result = call()
        run.update(outcome="completed", usage=result.get("usage"), usage_by_stage=result.get("usage_by_stage") or {},
                   changed=result.get("changed") or [], items=result.get("items", 0),
                   chars_in=result.get("chars_gathered") or 0, coverage=result.get("coverage") or [])
        return result
    except BaseException as error:
        run.update(outcome=("refused" if isinstance(error, RunFailed) and "rejected" in str(error) else
                            "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"),
                   error=str(error)[:1000], usage=getattr(error, "usage", None))
        raise
    finally:
        run["finished_at"] = now().isoformat()
        from datetime import datetime
        run["seconds"] = round((datetime.fromisoformat(run["finished_at"])
                                - datetime.fromisoformat(run["started_at"])).total_seconds(), 1)
        write_json(path, run)


def _investigation_pages(notebook):
    return [path for path in notebook.list()
            if path.startswith(("people/", "projects/", "orgs/", "skills/catalog/"))
            and path != "skills/catalog/index.md"]


def _resolve_page(notebook, selector):
    from ...wiki.files import WikiError
    pages = _investigation_pages(notebook)
    if selector in notebook.list():
        return selector
    candidate = notebook.root / selector
    if selector.endswith(".md") and (candidate.exists() or candidate.is_symlink()):
        # A file that is there but is not a page (a symlink, over 1 MB, not
        # UTF-8, hidden): say why, as show does, not "No page matches".
        notebook.read(selector)
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
    wiki = factory(help="co wiki", no_args_is_help=False)
    wiki.info.cls = verbatim("co wiki", wiki.info.cls)

    @wiki.callback(invoke_without_command=True)
    def overview(ctx: typer.Context,
                 root: Optional[Path] = typer.Option(None, "--root", help="Notebook root (default ~/.co/wiki)"),
                 json_out: bool = typer.Option(False, "--json", help="Machine-readable output with next command")):
        ctx.obj = {"root": (root or Path.home() / ".co/wiki").expanduser().resolve(),
                   "default_root": root is None, "json": json_out}
        if ctx.invoked_subcommand is None:
            if ctx.obj["json"]:
                inspect_status(ctx)
            else:
                from ...wiki.service import status
                typer.echo(page("co wiki"))
                typer.echo()
                def operation(root):
                    result = status(root)
                    return result, ["investigate"] if result["configured"] else ["init"]
                _handle(ctx, operation, ["config"])

    V = verbatim

    # ------------------------------------------------------------------ Build

    @wiki.command("init", cls=V("co wiki init"))
    def init_wiki(ctx: typer.Context,
                  days: int = typer.Option(90, "--days", min=1),
                  skills_dir: List[Path] = typer.Option([], "--skills-dir"),
                  mine: List[str] = typer.Option([], "--mine"),
                  mail: List[str] = typer.Option([], "--mail"),
                  name: str = typer.Option("", "--name"),
                  archive_mail: bool = typer.Option(True, "--archive-mail/--no-mail-archive")):
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
                # A mailbox the user explicitly unsubscribed stays out, the same
                # rule investigate follows; anything else authorized is mapped.
                selected.update(kind for kind in available
                                if not sources.get(kind, {}).get("unsubscribed"))
                selected.update(sub["kind"] for sub in sources.values()
                                if sub.get("kind") in ("gmail", "outlook") and sub.get("enabled"))
            clients, errors = {}, []
            for kind in sorted(selected):
                try:
                    clients[kind] = mail_client(kind)
                except Exception as error:
                    errors.append({"source": kind, "stage": "client", "error": type(error).__name__})
            failed = {row["source"]: row["error"] for row in errors}
            result = build_map(root, sources, clients, days=days,
                               skill_directories=skills_dir or None, mine=mine, source_errors=errors,
                               absent=_absent_mail(selected, available, failed, sources, bool(mail)), name=name,
                               capture_sources=True,
                               progress=(None if ctx.obj["json"] else
                                         lambda message: typer.echo("[wiki init] " + message, err=True)))
            if archive_mail and result.get("source_inventory"):
                from ...wiki.files import read_json, state_path, write_json
                from ...wiki.mail_archive import archive_init
                previous = read_json(state_path(root, "mail/archive.json"), {})
                incomplete_scan = any(row.get("source") in ("gmail", "outlook")
                                      for row in result.get("errors", []))
                if previous and (not clients or incomplete_scan):
                    body_report = {"phase": "previous_preserved", "started": previous.get("started"),
                                   "target": previous.get("target", 0),
                                   "reason": "Current mail enumeration unavailable; previous private archive retained"}
                else:
                    body_report = archive_init(
                        root, result, clients,
                        progress=(None if ctx.obj["json"] else
                                  lambda message: typer.echo("[wiki init] " + message, err=True)))
                result["mail_archive"] = body_report
                if body_report.get("failed"):
                    result["errors"].append({"source": "mail-archive", "stage": "body",
                                             "error": f"{body_report['failed']} messages unavailable"})
                    result["phase"] = "partial"
                write_json(state_path(root, "map.json"), result)
            tips = []
            for kind, provider in (("gmail", "google"), ("outlook", "microsoft")):
                if kind not in available:
                    tips.append(f"Connect {provider.title()} for People: co auth {provider}; then run "
                                + _next(ctx, ["init"]) + ".")
            if tips:
                result["tips"] = tips
            candidates = result.get("possible_own_addresses") or []
            if candidates:
                # The owner is the only one who can answer this, so the question
                # arrives with the command that answers it, spelled for the root
                # they actually used. Five at a time: the rest stay in the report.
                result["confirm_own_addresses"] = [
                    f"{row['address']}: {row['sent']} sent, none received. If it is yours, run "
                    + _next(ctx, ["init", "--mine", row["address"]])
                    + "; if it is an assistant or a relative, leave it as a person."
                    for row in candidates[:5]]
                if len(candidates) > 5:
                    result["confirm_own_addresses"].append(
                        f"{len(candidates) - 5} more in .state/map.json; nothing is merged without --mine.")
            if not selected:
                result["people_setup"] = "No connected mail source. Local maps are ready; connect mail to add People."
            if result.get("errors"):
                result["recovery"] = ("Check mailbox access with co auth status, then rerun init. "
                                      "Saved mail bodies and completed maps are reused.")
                retry = ["init", "--mail", sorted(selected)[0]] if selected else ["init"]
                _emit(ctx, result, retry, failed=True)
                raise typer.Exit(1)
            # A page made from --name alone has no address for investigate me to use.
            return result, (["investigate", "me"] if (result.get("owner") or {}).get("addresses")
                            else ["investigate"])
        _handle(ctx, run, ["sources"])

    @wiki.command("investigate", cls=V("co wiki investigate"))
    def investigate_page(ctx: typer.Context,
                         target: str = typer.Argument(""),
                         handle: List[str] = typer.Option([], "--handle"),
                         days: Optional[int] = typer.Option(None, "--days", min=1),
                         limit: int = typer.Option(5, "--limit", min=0),
                         list_only: bool = typer.Option(False, "--list"),
                         eval_dir: List[Path] = typer.Option([], "--eval-dir")):
        from ...wiki.files import Notebook, WikiError, read_json, state_path
        from ...wiki.investigate import investigate
        from ...wiki.queue import CATEGORIES, order
        from ...wiki.runner import RunFailed
        from ...wiki.service import mail_available, mail_client, subscriptions

        def clients_for(root):
            # Investigating is an explicit request, so any mailbox this machine can
            # already read is read, whether or not background sync is subscribed to
            # it -- `init` read the same mailboxes to build the map. Only a mailbox
            # the user explicitly unsubscribed is left alone.
            sources = subscriptions(root)
            return {kind: mail_client(kind, attachments=True) for kind in ("outlook", "gmail")
                    if mail_available(kind) and not sources.get(kind, {}).get("unsubscribed")}

        def progress(kind, stop, count):
            typer.echo(f"  {kind}: to {stop:%Y-%m-%d}, {count} mails", err=True)

        def one(root, notebook, record):
            if record.startswith("skills/"):
                from ...wiki.skill_runs import investigate_skill_runs
                return investigate_skill_runs(root, record, eval_dir or [Path.home() / ".co/evals"])
            if eval_dir:
                raise WikiError("--eval-dir applies only to skills pages")
            text = notebook.read(record)
            title = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), record)
            known = []
            if record.startswith("people/"):
                person = next((p for p in notebook.people() if p["path"] == record), {})
                known += person.get("emails", []) + person.get("aliases", [])
            for line in text.splitlines():
                low = line.strip().lstrip("-").strip().casefold()
                if low.startswith(("also known as:", "email:", "handles:")) and ":" in line:
                    known += [h.strip() for h in line.split(":", 1)[1].replace("、", ",").split(",")
                              if h.strip() and h.strip() != "Unknown"]
            handles = list(dict.fromkeys([*handle, *known, title.split(" (")[0]]))
            clients = clients_for(root)
            if record.startswith("projects/"):
                # A project is read from where it lives: the sessions run in its
                # folders. Matching mail on its name pulled in every notification
                # and signature that mentioned it -- 3,500 mails scanned for one
                # project on a real mailbox, then a turn that timed out. Mail about
                # a project comes in through --handle, named on purpose.
                section = text.partition("## Paths\n")[2].split("\n## ")[0]
                handles = list(dict.fromkeys([*handle, *(line[2:].strip() for line in section.splitlines()
                                                          if line.startswith("- /")), title]))
                clients = {kind: client for kind, client in clients.items() if handle}
            skipped = "" if clients or not record.startswith("projects/") else \
                "not read for a project page; name its mail with --handle"
            return _logged(root, record, "investigate", lambda: investigate(
                root, record, title, handles, days=days or 150, clients=clients,
                subscriptions=subscriptions(root), progress=progress, mail_skipped=skipped))

        def overview(root):
            state = read_json(state_path(root, "map.json"), {})
            owner = (state.get("owner") or {}).get("record")
            if not owner and not Notebook(root).list():
                return "No pages available to investigate: the map has not been built yet.", ["init"]
            rows = {}
            for category in CATEGORIES:
                queue = order(root, category)
                rows[category] = {"unfinished": len(queue),
                                  "next": [row["path"] for row in queue if not row["recent"]][:3]}
            if owner:
                rows["me"] = {"page": owner, "unfinished": owner in {p["path"] for p in Notebook(root).unfinished("people")}}
            first = next((c for c in CATEGORIES if rows[c]["next"]), None)
            return rows, (["investigate", "me"] if owner and rows["me"]["unfinished"]
                          else ["investigate", first] if first else ["list"])

        def by_category(root, category):
            queue = [row for row in order(root, category) if not row["recent"]]
            chosen = queue if limit == 0 else queue[:limit]
            if list_only:
                rows = order(root, category)
                if not ctx.obj["json"]:
                    unit = {"people": "mails", "projects": "sessions", "orgs": "people"}.get(category)
                    rows = [f"{row['path']}  ("
                            + (f"{row['weight']} {unit}, " if unit else "")
                            + (f"investigated {row['last_investigated']}" if row["last_investigated"]
                               else "not investigated") + (", skipped: this week" if row["recent"] else "") + ")"
                            for row in rows]
                return {"category": category, "order": rows}, ["investigate", category]
            notebook, done = Notebook(root), []
            for number, row in enumerate(chosen, 1):
                typer.echo(f"[{number}/{len(chosen)}] {row['path']}", err=True)
                try:
                    one(root, notebook, row["path"])
                    done.append({"page": row["path"], "outcome": "accepted"})
                except RunFailed as error:
                    done.append({"page": row["path"], "outcome": "refused", "why": str(error)})
                except WikiError as error:
                    done.append({"page": row["path"], "outcome": "failed", "why": str(error)})
            skipped = [row["path"] for row in order(root, category) if row["recent"]]
            accepted = [row["page"] for row in done if row["outcome"] == "accepted"]
            return ({"category": category, "pages": done, "skipped_recent": skipped,
                     "left": max(len(queue) - len(chosen), 0)},
                    ["show", accepted[0]] if accepted else ["logs"])

        def me(root):
            state = read_json(state_path(root, "map.json"), {})
            owner = state.get("owner") or {}
            if not owner.get("record"):
                raise WikiError("No page for you yet: init makes it from a connected mailbox or from your "
                                "name. Run `co wiki init --name \"Your Name\"`")
            record = owner["record"]
            if not owner.get("addresses") and not handle:
                # A page made from --name alone has no address to find your own
                # mail by, and investigating it would run a model on nothing.
                raise WikiError(f"Your page {record} has no mail address yet, and investigate me reads what "
                                "you sent. Connect a mailbox with co auth google or co auth microsoft, then "
                                "run `co wiki init`")
            title = next((l[2:].strip() for l in Notebook(root).read(record).splitlines() if l.startswith("# ")),
                         "Account owner")
            result = _logged(root, record, "investigate me", lambda: investigate(
                root, record, title, [*owner.get("addresses", []), *handle], days=days or 30,
                clients=clients_for(root), subscriptions=subscriptions(root), progress=progress, sent_only=True))
            return result, ["show", record]

        def run(root):
            if list_only and target not in CATEGORIES:
                raise WikiError("--list goes with a category: co wiki investigate people --list "
                                "(or projects, orgs, skills)")
            if not target:
                return overview(root)
            if target == "me":
                return me(root)
            if target in CATEGORIES:
                return by_category(root, target)
            notebook = Notebook(root)
            record = _resolve_page(notebook, target)
            result = one(root, notebook, record)
            return result, ["show", result["report"] if record.startswith("skills/") else record]
        _handle(ctx, run, ["investigate"])

    # ------------------------------------------------------------------- Read

    @wiki.command("open", cls=V("co wiki open"))
    def open_page(ctx: typer.Context,
                  launch: bool = typer.Option(True, "--launch/--no-launch"),
                  local: bool = typer.Option(False, "--local")):
        from ...wiki.reader import open_reader

        def operation(root):
            from connectonion.project import selected_identity_dir
            from connectonion import address

            identity = (address.load(selected_identity_dir())
                        if not local and ctx.obj["default_root"] and root.is_dir() else None)
            if identity:
                import webbrowser

                url = f"https://chat.openonion.ai/{identity['address']}/wiki"
                if launch:
                    webbrowser.open(url)
                return {"page": url, "launched": launch}, ["status"]
            opened = open_reader(root, launch=launch)
            return {"page": str(opened), "launched": launch,
                    "note": "local snapshot; run again after the next maintenance pass"}, ["status"]
        _handle(ctx, operation, ["doctor"])

    @wiki.command("list", cls=V("co wiki list"))
    def list_records(ctx: typer.Context, category: str = typer.Argument(""),
                     aliases: bool = typer.Option(False, "--aliases")):
        from ...wiki.files import CATEGORIES, Notebook, WikiError

        def operation(root):
            notebook = Notebook(root)
            if aliases:
                if category not in ("", "people"):
                    raise WikiError("--aliases goes with people")
                people = notebook.people()
                return people, (["show", people[0]["path"]] if people else ["init"])
            if not category:
                counts = {name: len(notebook.list(name)) for name in CATEGORIES if notebook.list(name)}
                return (counts, ["list", next(iter(counts))]) if counts else ([], ["init"])
            records = notebook.list(category)
            if not records and category == "people" and not ctx.obj["json"]:
                from ...wiki.files import state_path
                from ...wiki.service import mail_available
                # Right after init this said "Run init to build the map", to
                # someone who just had. People come only from a mailbox.
                if state_path(root, "map.json").is_file() and not any(
                        mail_available(kind) for kind in ("gmail", "outlook")):
                    return ("No people yet: people pages come from a connected mailbox, and none is "
                            "connected. Connect one with co auth google or co auth microsoft, then run "
                            + _next(ctx, ["init"]) + "."), ["sources"]
            return records, (["show", records[0]] if records else ["list"])
        _handle(ctx, operation, ["list"])

    @wiki.command("show", cls=V("co wiki show"))
    def show_record(ctx: typer.Context, record: str = typer.Argument(...)):
        from ...wiki.files import CATEGORIES, Notebook, WikiError, read_json, state_path
        category = record.split("/")[0]
        recovery = ["list", category] if category in CATEGORIES else ["list"]
        def operation(root):
            nonlocal category
            page = record
            if record == "me":
                # The same owner `investigate me` uses; `show me` used to be
                # read as a page called "me" and refused.
                page = (read_json(state_path(root, "map.json"), {}).get("owner") or {}).get("record")
                if not page:
                    raise WikiError("No page for you yet: init makes it from a connected mailbox or from your "
                                    "name. Run `co wiki init --name \"Your Name\"`")
                category = page.split("/")[0]
            text = Notebook(root).read(page)
            return text, (["investigate", record] if "Unknown" in text else ["list", category])
        _handle(ctx, operation, recovery)

    @wiki.command("search", cls=V("co wiki search"))
    def search_records(ctx: typer.Context, query: str = typer.Argument(...),
                       within: str = typer.Option("", "--in"),
                       old_type: str = typer.Option("", "--type")):
        from ...wiki.files import Notebook
        def operation(root):
            found = Notebook(root).search(query, within or old_type)
            return found, ["show", found[0]["record"]] if found else ["list"]
        _handle(ctx, operation, ["list"])

    # -------------------------------------------------------- Keep it current

    @wiki.command("start", cls=V("co wiki start"))
    def start_wiki(ctx: typer.Context, yes: bool = typer.Option(False, "--yes")):
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
                typer.echo("A noninteractive start cannot consent silently; read the summary above "
                           "and run with --yes, or run `co wiki start` in a terminal.", err=True)
                return False
            typer.echo(text)
            return typer.confirm("Read these sources with this model and schedule?", default=False)

        def operation(root):
            result = start(root, confirm=confirm, scheduler=wiki_schedule.default_scheduler())
            if not result["started"]:
                raise WikiError("Start was not confirmed; nothing was read or installed")
            first = result.get("first_batch") or {}
            if first.get("outcome") == "failed":
                # The schedule is installed, but the first update did not work; exit 0
                # here let `start && ...` walk past it (seen on a real notebook).
                result["attention"] = (f"The schedule is installed, but the first update failed: "
                                       f"{first.get('error')}")
                _emit(ctx, result, ["logs", first["id"]], failed=True)
            if result.get("first_batch") is None and not ctx.obj["json"]:
                # Only the first start runs a batch; a start after stop resumes
                # the clock. None printed as "Unknown", which read as a fault.
                result["first_batch"] = ("Not run: the first start already ran it. "
                                         f"{_next(ctx, ['sync'])} runs an update now.")
            return result, ["status"]

        _handle(ctx, operation, ["start", "--yes"] if not yes else ["doctor"])

    @wiki.command("stop", cls=V("co wiki stop"))
    def stop_wiki(ctx: typer.Context):
        from ...wiki import schedule as wiki_schedule
        from ...wiki.service import stop
        _handle(ctx, lambda root: (stop(root, scheduler=wiki_schedule.default_scheduler()), ["status"]), ["status"])

    @wiki.command("status", cls=V("co wiki status"))
    def inspect_status(ctx: typer.Context):
        from ...wiki.service import status
        _handle(ctx, lambda root: (status(root), ["logs"]), ["config"])

    def _sync(ctx, source, with_person, dry_run, scheduled, all_pending, days):
        from ...wiki.files import WikiError
        from ...wiki.service import run_sync

        def operation(root):
            if dry_run or source or with_person or all_pending:
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
                return record, ["logs", record["id"]]
            # The whole update: new material first, then at most one unfinished page.
            from ...wiki.daily import run_daily
            result = run_daily(root, days=days, scheduled=scheduled)
            if result is None:
                return {"due": False, "ran": False}, ["status"]
            if result["outcome"] == "partial":
                _emit(ctx, result, ["logs"], failed=True)
            return result, ["logs"]
        _handle(ctx, operation, ["logs"])

    @wiki.command("sync", cls=V("co wiki sync"))
    def sync_wiki(ctx: typer.Context,
                  source: str = typer.Option("", "--source"),
                  with_person: str = typer.Option("", "--with"),
                  dry_run: bool = typer.Option(False, "--dry-run"),
                  scheduled: bool = typer.Option(False, "--scheduled"),
                  all_pending: bool = typer.Option(False, "--all"),
                  days: int = typer.Option(30, "--days", min=1)):
        _sync(ctx, source, with_person, dry_run, scheduled, all_pending, days)

    # --------------------------------------------------------------- Settings

    sources_app = factory(help="co wiki sources", no_args_is_help=False)
    sources_app.info.cls = verbatim("co wiki sources", sources_app.info.cls)
    wiki.add_typer(sources_app, name="sources")

    @sources_app.callback(invoke_without_command=True)
    def inspect_sources(ctx: typer.Context):
        from ...wiki.service import subscriptions
        if ctx.invoked_subcommand is None:
            _handle(ctx, lambda root: (subscriptions(root), ["sync", "--dry-run"]), ["config"])

    def _add_source(ctx, name, chat, project, about, since, only, force):
        from ...wiki.service import set_window, toggle_source

        def operation(root):
            subscription = toggle_source(root, name, True, project=project, about=about,
                                         since=since or "60d", chats=chat)
            result = {"subscription": subscription, "enabled": True}
            if since and not (project or about):
                result.update(set_window(root, subscription, since, narrow=only, force=force))
            if chat:
                # A new chat is not read until `start` has shown it and the user agreed.
                result["chats"] = chat
                return result, ["start"]
            return result, ["sync", "--dry-run"]
        _handle(ctx, operation, ["sources"])

    def _remove_source(ctx, name, chat):
        from ...wiki.service import subscriptions, toggle_source

        def operation(root):
            toggle_source(root, name, False, chats=chat)
            source = subscriptions(root)[name]
            return {"subscription": name, "enabled": bool(source.get("enabled")),
                    **({"chats": source.get("chats") or []} if chat else {})}, ["sources"]
        _handle(ctx, operation, ["sources"])

    @sources_app.command("add", cls=V("co wiki sources add"))
    def add_source(ctx: typer.Context, name: str = typer.Argument(...),
                   chat: List[str] = typer.Option([], "--chat"),
                   project: str = typer.Option("", "--project"),
                   about: str = typer.Option("", "--about"),
                   since: str = typer.Option("", "--since"),
                   only: bool = typer.Option(False, "--only"),
                   force: bool = typer.Option(False, "--force")):
        _add_source(ctx, name, chat, project, about, since, only, force)

    @sources_app.command("remove", cls=V("co wiki sources remove"))
    def remove_source(ctx: typer.Context, name: str = typer.Argument(...),
                      chat: List[str] = typer.Option([], "--chat")):
        _remove_source(ctx, name, chat)

    config_app = factory(help="co wiki config", no_args_is_help=False)
    config_app.info.cls = verbatim("co wiki config", config_app.info.cls)
    wiki.add_typer(config_app, name="config")

    @config_app.callback(invoke_without_command=True)
    def inspect_config(ctx: typer.Context):
        from ...wiki.config import read_config
        from ...wiki.inquiry import routing
        if ctx.invoked_subcommand is None:
            _handle(ctx, lambda root: ({"path": str(root / "config.yaml"),
                                       "saved": (root / "config.yaml").exists(),
                                       "config": read_config(root, validated=False),
                                       "routes": routing(root)}, ["status"]), ["doctor"])

    @config_app.command("set", cls=V("co wiki config set"))
    def change_config(ctx: typer.Context, values: List[str] = typer.Argument(...)):
        from ...wiki.config import read_config, set_config
        from ...wiki.files import WikiError
        from ...wiki.inquiry import STAGES, clear_route, routing, set_route

        def operation(root):
            if len(values) % 2:
                raise WikiError("config set needs KEY VALUE pairs")
            pairs = list(zip(values[::2], values[1::2]))
            routes = [(key.split(".", 1)[1], value) for key, value in pairs if key.startswith("route.")]
            rest = [part for key, value in pairs if not key.startswith("route.") for part in (key, value)]
            for stage, _ in routes:
                if stage not in STAGES:
                    raise WikiError(f"route.{stage}: the stages are {', '.join(STAGES)}")
            config = set_config(root, rest) if rest else read_config(root)
            for stage, model in routes:
                if model == "default":
                    clear_route(root, stage)
                else:
                    set_route(root, stage, config["runner"], model)
            return {"config": config, "routes": routing(root)}, ["config"]
        _handle(ctx, operation, ["config"])

    @wiki.command("logs", cls=V("co wiki logs"))
    def inspect_logs(ctx: typer.Context, run_id: str = typer.Argument(""),
                     usage: bool = typer.Option(False, "--usage"),
                     days: int = typer.Option(0, "--days", min=0),
                     old_run: str = typer.Option("", "--run")):
        from ...wiki.service import run_logs, usage_report

        def operation(root):
            if usage:
                report = usage_report(root, days or None)
                if not report["runs"]:
                    window = f" in the last {days} days" if days else ""
                    return f"No runs with recorded usage{window}.", ["logs"]
                return report, ["logs"]
            chosen = run_id or old_run
            records = run_logs(root, chosen)[:20]
            return records, (["logs", records[0]["id"]] if records and not chosen else ["status"])
        _handle(ctx, operation, ["logs"])

    @wiki.command("doctor", cls=V("co wiki doctor"))
    def doctor(ctx: typer.Context):
        import shutil

        from ..._version import __version__
        from ...wiki.config import read_config, validate
        from ...wiki.files import WikiError
        from ...wiki.runner import co_command
        from ...wiki.service import mail_available, status, subscriptions

        def operation(root):
            checks, wiki_fixes = [], []

            def check(name, ok, detail, fix="", wiki_fix=None):
                """`wiki_fix` is a co wiki command, spelled for this root; `fix` is anything else."""
                if not ok and wiki_fix:
                    fix = _next(ctx, wiki_fix)
                    wiki_fixes.append(wiki_fix)
                checks.append({"check": name, "ok": ok, "detail": detail, **({"fix": fix} if not ok else {})})

            check("co CLI", True, " ".join(co_command()),
                  # This exact version, never `--pre`, which also takes pre-release
                  # dependencies (httpx 1.0.dev6 crashed 1.8.8b7).
                  f"python -m pip install --upgrade 'connectonion=={__version__}'")
            config = None
            try:
                config = read_config(root)
                validate(config)
                check("configuration", True, str(root / "config.yaml"))
            except WikiError as error:
                check("configuration", False, str(error), wiki_fix=["config"])
            runner = (config or {}).get("runner", "codex")
            binary = {"codex": "codex", "claude-code": "claude"}.get(runner)
            if binary:
                check(f"model runner ({runner})", bool(shutil.which(binary)), shutil.which(binary) or "not on PATH",
                      "npm install -g @openai/codex" if binary == "codex" else "npm install -g @anthropic-ai/claude-code")
            import importlib.util
            # Optional (the `wiki` extra): without it an XLSX attachment is named,
            # not read, and nothing said so until a page came back without it.
            sheets = importlib.util.find_spec("openpyxl") is not None
            check("spreadsheet support (wiki extra)", sheets,
                  "openpyxl installed; XLSX attachments are read" if sheets
                  else "not installed; XLSX attachments are named, not read",
                  f"python -m pip install 'connectonion[wiki]=={__version__}'")
            for kind, provider in (("gmail", "google"), ("outlook", "microsoft")):
                there = mail_available(kind)
                check(f"mailbox {kind}", there, "connected" if there else "not connected", f"co auth {provider}")
            for name, sub in subscriptions(root).items():
                if sub.get("kind") in ("codex", "claude-code") and sub.get("enabled", True):
                    check(f"sessions {name}", Path(sub.get("root", "")).is_dir(), sub.get("root", ""),
                          wiki_fix=["sources", "remove", name])
            if (root / "config.yaml").exists():
                slot = status(root).get("next_run")
                check("schedule", slot is not None, f"next run {slot}" if slot else "not installed",
                      wiki_fix=["start"])
            if not ctx.obj["json"]:
                checks = [f"{'ok ' if row['ok'] else 'NO '} {row['check']}: {row['detail']}"
                          + ("" if row["ok"] else f" -> {row['fix']}") for row in checks]
            return checks, (wiki_fixes[0] if wiki_fixes else ["status"])
        _handle(ctx, operation, ["config"])

    # --------------------------------------------------------------- Advanced

    @wiki.command("advanced", cls=V("co wiki advanced"))
    def advanced(ctx: typer.Context):
        typer.echo(page("co wiki advanced"))

    @wiki.command("scan", cls=V("co wiki scan"))
    def scan_sources(ctx: typer.Context,
                     what: str = typer.Argument("people"),
                     days: int = typer.Option(150, "--days", min=1),
                     min_mails: int = typer.Option(3, "--min-mails"),
                     min_people: int = typer.Option(2, "--min-people"),
                     mine: List[str] = typer.Option([], "--mine")):
        from ...wiki.files import WikiError
        from ...wiki.scan import scan_orgs, scan_people, scan_projects
        from ...wiki.service import mail_client, subscriptions

        def run(root):
            if what == "projects":
                rows = scan_projects(subscriptions(root), days, root)
                return rows, (["stub", "project", rows[0]["name"], "--path", rows[0]["path"]]
                              if rows else ["sources"])
            if what not in ("people", "orgs"):
                raise WikiError("scan takes people, orgs or projects")
            clients = {k: mail_client(k) for k in ("outlook", "gmail")}
            rows = [p for p in scan_people(clients, days, set(mine)) if p["mails"] >= min_mails]
            if what == "orgs":
                own = set(mine) | {a for c in clients.values() for a in c.my_addresses()}
                orgs = scan_orgs(rows, min_people=min_people, own_addresses=own)
                return orgs, (["stub", "org", orgs[0]["domain"], "--domain", orgs[0]["domain"]]
                              if orgs else ["sources"])
            return rows, (["stub", "person", rows[0]["name"] or rows[0]["address"],
                           "--email", rows[0]["address"], "--handle", rows[0]["address"]]
                          if rows else ["sources"])
        _handle(ctx, run, ["status"])

    @wiki.command("map-skills", cls=V("co wiki map-skills"))
    def map_skill_pages(ctx: typer.Context, skills_dir: List[Path] = typer.Option([], "--skills-dir")):
        from ...wiki.files import Notebook
        from ...wiki.skill_map import map_skills
        _handle(ctx, lambda root: (map_skills(Notebook(root), skills_dir or None), ["list", "skills"]), ["status"])

    @wiki.command("stub", cls=V("co wiki stub"))
    def stub_page(ctx: typer.Context,
                  kind: str = typer.Argument(...),
                  name: str = typer.Argument(...),
                  handle: List[str] = typer.Option([], "--handle"),
                  path: List[str] = typer.Option([], "--path"),
                  domain: List[str] = typer.Option([], "--domain"),
                  person: List[str] = typer.Option([], "--person"),
                  email: str = typer.Option("", "--email")):
        import re
        from ...wiki.files import Notebook, WikiError

        def run(root):
            slug = re.sub(r"[^a-z0-9一-鿿]+", "-", name.lower()).strip("-") or "page"
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
        _handle(ctx, run, ["investigate"])

    @wiki.command("reflect", cls=V("co wiki reflect"))
    def reflect(ctx: typer.Context, subject: str, statement: str,
                author: str = typer.Option(..., "--author"),
                basis: str = typer.Option(..., "--basis"),
                previous: str = typer.Option("", "--previous"),
                applies: str = typer.Option("", "--applies"),
                kind: str = typer.Option("reflection", "--kind"),
                source: List[str] = typer.Option([], "--source"),
                supersedes: List[str] = typer.Option([], "--supersedes")):
        from ...wiki.reflections import add
        _handle(ctx, lambda root: (add(root, subject, statement, author=author, basis=basis,
                 previous=previous, applies=applies, kind=kind, sources=source, supersedes=supersedes),
                 ["investigate", subject]), ["list"])

    @wiki.command("reflections", cls=V("co wiki reflections"))
    def reflection_records(ctx: typer.Context, subject: str = typer.Argument(""),
                           compact: bool = typer.Option(False, "--compact")):
        from ...wiki.reflections import compress, records
        _handle(ctx, lambda root: (compress(root, subject) if compact else records(root, subject),
                                  ["list"]), ["list"])

    @wiki.command("propose", cls=V("co wiki propose"))
    def propose_review(ctx: typer.Context, kind: str, subject: str, question: str,
                       basis: str = typer.Option(..., "--basis"),
                       related: str = typer.Option("", "--related")):
        from ...wiki.reviews import propose
        _handle(ctx, lambda root: (propose(root, kind, [subject, related] if related else [subject],
                                         question, basis), ["review"]), ["list"])

    @wiki.command("review", cls=V("co wiki review"))
    def review_candidates(ctx: typer.Context, review_id: str = typer.Argument(""),
                          verdict: str = typer.Option("", "--verdict"),
                          author: str = typer.Option("", "--author"),
                          response: str = typer.Option("", "--response"),
                          audio: Optional[Path] = typer.Option(None, "--audio"),
                          local_model: Optional[Path] = typer.Option(None, "--local-model")):
        from ...wiki.reviews import decide, listing

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

    @wiki.command("abstract", cls=V("co wiki abstract"))
    def abstract_pages(ctx: typer.Context):
        from ...wiki.config import read_config
        from ...wiki.files import Notebook
        from ...wiki.runner import run_stage
        _handle(ctx, lambda root: (
            run_stage(Notebook(root), [], read_config(root), stage="abstract"), ["list", "decisions"]), ["status"])

    @wiki.command("capture", cls=V("co wiki capture"))
    def capture_session(ctx: typer.Context, transcript: Path, source: str = typer.Option(..., "--source")):
        from ...wiki.capture import capture
        _handle(ctx, lambda root: (capture(root, transcript.expanduser().resolve(), source),
                                  ["sync", "--dry-run"]), ["status"])

    # ------------------------------------------------ Old names (until 1.9)

    @wiki.command("unfinished", help="Old name for `co wiki investigate`; works until 1.9.")
    def list_unfinished(ctx: typer.Context, category: str = typer.Argument("")):
        _moved(ctx, "unfinished", ["investigate", *([category] if category and category != "all" else [])])
        from ...wiki.files import Notebook
        def operation(root):
            pages = Notebook(root).unfinished("" if category == "all" else category)
            return pages, ["investigate", pages[0]["path"]] if pages else ["list"]
        _handle(ctx, operation, ["status"])

    @wiki.command("people", help="Old name for `co wiki list people --aliases`; works until 1.9.")
    def list_people(ctx: typer.Context):
        _moved(ctx, "people", ["list", "people", "--aliases"])
        from ...wiki.files import Notebook
        _handle(ctx, lambda root: (Notebook(root).people(), ["list", "people"]), ["list", "people"])

    @wiki.command("daily", help="Old name for `co wiki sync`; works until 1.9.")
    def daily_round(ctx: typer.Context, days: int = typer.Option(30, "--days", min=1),
                    scheduled: bool = typer.Option(False, "--scheduled")):
        # Installed launchd jobs still call `daily --scheduled`; the notice goes
        # to their log, not to a person, so it is kept to one line.
        _moved(ctx, "daily", ["sync"])
        _sync(ctx, "", "", False, scheduled, False, days)

    @wiki.command("subscriptions", help="Old name for `co wiki sources`; works until 1.9.")
    def inspect_subscriptions(ctx: typer.Context):
        _moved(ctx, "subscriptions", ["sources"])
        from ...wiki.service import subscriptions
        _handle(ctx, lambda root: (subscriptions(root), ["sources"]), ["config"])

    @wiki.command("subscribe", help="Old name for `co wiki sources add`; works until 1.9.")
    def subscribe(ctx: typer.Context, name: str = typer.Argument(...),
                  chat: List[str] = typer.Option([], "--chat"),
                  project: str = typer.Option("", "--project"),
                  about: str = typer.Option("", "--about"),
                  since: str = typer.Option("", "--since"),
                  only: bool = typer.Option(False, "--only"),
                  force: bool = typer.Option(False, "--force")):
        _moved(ctx, "subscribe", ["sources", "add", name])
        _add_source(ctx, name, chat, project, about, since, only, force)

    @wiki.command("unsubscribe", help="Old name for `co wiki sources remove`; works until 1.9.")
    def unsubscribe(ctx: typer.Context, name: str = typer.Argument(...),
                    chat: List[str] = typer.Option([], "--chat")):
        _moved(ctx, "unsubscribe", ["sources", "remove", name])
        _remove_source(ctx, name, chat)

    @wiki.command("route", help="Old name for `co wiki config set route.<stage>`; works until 1.9.")
    def route_stage(ctx: typer.Context, stage: str = typer.Argument(""),
                    runner: str = typer.Option("", "--runner"),
                    model: str = typer.Option("", "--model"),
                    clear: bool = typer.Option(False, "--clear")):
        _moved(ctx, "route", ["config", "set", f"route.{stage or '<stage>'}", model or "<model>"])
        from ...wiki.inquiry import clear_route, routing, set_route
        def operation(root):
            from ...wiki.files import WikiError
            if clear and (runner or model):
                raise WikiError("Do not combine --clear with --runner or --model")
            value = clear_route(root, stage) if clear else set_route(root, stage, runner, model) if stage else routing(root)
            return value, ["config"]
        _handle(ctx, operation, ["config"])

    @wiki.command("usage", help="Old name for `co wiki logs --usage`; works until 1.9.")
    def usage(ctx: typer.Context, days: int = typer.Option(0, "--days")):
        _moved(ctx, "usage", ["logs", "--usage"])
        from ...wiki.service import usage_report
        _handle(ctx, lambda root: (usage_report(root, days or None), ["logs"]), ["logs"])

    order = ("init investigate open list show search start stop status sync sources config logs doctor "
             "advanced scan map-skills stub reflect reflections propose review abstract capture "
             "unfinished people daily subscriptions subscribe unsubscribe route usage").split()
    wiki.registered_commands.sort(key=lambda command: order.index(command.name))
    return wiki
