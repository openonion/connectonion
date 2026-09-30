"""Experimental co rem inspection. No collection or provider startup on import."""

import json
import re
import shlex
from pathlib import Path
from typing import List, Optional

import typer

from . import rem_look
from .rem_help import show, verbatim
from .rem_output import render


def _next(ctx, arguments):
    """The next command, spelled the way the user invoked this one.

    A thin wrapper (`remi status`) that forwards to `co rem` is only a product
    if the tips agree with it; a user told `co rem --root /long/path logs` has
    been handed the wiring. The wrapper names itself in CO_REM_PROGRAM and every
    Next line follows. The root is spelled out only when it is not the default,
    which is also what makes a tip short enough to copy.
    """
    from ...rem.migrate import program
    program = shlex.split(program())
    root = ctx.obj["root"]
    default = (Path.home() / ".co/rem").expanduser().resolve()
    location = [] if root == default else ["--root", str(root)]
    return shlex.join([*program, *location, *arguments])


def _carry_over(ctx):
    """Bring a co wiki notebook, its schedule and wrapper variable over to co rem (#1932)."""
    from ...rem import migrate
    from ...rem.files import RemError
    root = ctx.obj["root"]
    lines = [migrate.old_program_notice()]
    try:
        if ctx.obj["default_root"]:
            lines.append(migrate.move_notebook(root))
        old = migrate.old_root() if ctx.obj["default_root"] else root
        if root.is_dir():
            lines.append(migrate.replace_schedule(root, old))
    except (RemError, OSError) as error:
        _emit(ctx, str(error), ["status"], failed=True)
    for line in filter(None, lines):
        rem_look.line(line, err=True)


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
                             f"Restore it with co rem subscribe {kind}")
        elif chosen_by_hand:
            reasons[kind] = "connected, left out of this run by --mail; not searched"
        else:
            reasons[kind] = "connected but not read this run; not searched"
    return reasons


def _emit(ctx, value, arguments, *, failed=False, draw=None):
    """Print a result and its Next line: styled in a terminal, the same words anywhere else.

    `draw` turns a result into markup of its own (status's dashboard); any
    other result is `render`'s text with commands, counts and errors marked.
    """
    from ..style import next_line
    command = _next(ctx, arguments)
    if ctx.obj["json"]:
        typer.echo(json.dumps({"ok": not failed, "data": value, "next": command}, ensure_ascii=False))
    elif draw and not failed:
        from .rem_output import printable
        rem_look.say(printable(draw(value)))
        rem_look.say(next_line(command))
    else:
        path, parent = [ctx.info_name or "status"], ctx.parent
        while parent is not None and parent.info_name not in (None, "rem") and parent.parent is not None:
            path.insert(0, parent.info_name)
            parent = parent.parent
        text = render(value, " ".join(path), failed=failed)
        rem_look.say(rem_look.result(text, titled=not isinstance(value, str)), err=failed, plain=text)
        rem_look.say(next_line(command), err=failed)
    if failed:
        raise typer.Exit(1)


# The pages this process wrote, in order: what a Ctrl-C summary names (#2008).
# `_logged` adds to it; each command starts it empty.
_WRITTEN: list = []


def _stopped() -> str:
    """One line for a run stopped with Ctrl-C: what it wrote before the stop (#2008).

    1.9.0a5 stopped with no summary and no Next line; what was written is kept,
    and naming the pages makes that visible.
    """
    written = list(dict.fromkeys(_WRITTEN))
    if not written:
        return "Stopped: nothing was written before the stop."
    return (f"Stopped: {len(written)} page{'s' if len(written) != 1 else ''} written before the stop "
            f"({', '.join(written)}), and kept.")


def _interrupted(ctx, resume, data=None):
    """Say what a stopped run wrote and what continues it, then exit 130 (#2008)."""
    value = ({**(data or {}), "stopped": True, "written": list(dict.fromkeys(_WRITTEN))}
             if ctx.obj["json"] else _stopped())
    _emit(ctx, value, resume)
    raise typer.Exit(130)


def _handle(ctx, operation, recovery, *, retry=None, draw=None, resume=None):
    """Run a command's operation and print its result; `resume` is the Next line after Ctrl-C."""
    from ...rem.files import RemError

    _WRITTEN.clear()
    try:
        response = operation(ctx.obj["root"])
        value, arguments = response[:2]
        failed = response[2] if len(response) > 2 else False
    except KeyboardInterrupt:
        _interrupted(ctx, resume or retry or recovery)
    except (RemError, OSError, UnicodeError) as error:
        message = str(error) if isinstance(error, RemError) else "Cannot read or write the selected co rem files"
        # An error that says what to run is the Next line too. `sync` before
        # `start` said "run co rem start" and then printed "Next: co rem logs".
        named = re.search(r"`co rem ([^`<>]+)`", message)
        next_step = (shlex.split(named.group(1)) if named else
                     retry if retry and getattr(error, "_rem_retry_page", False) else recovery)
        _emit(ctx, message, next_step, failed=True)
        return
    _emit(ctx, value, arguments, failed=failed, draw=draw)


def _dashboard(ctx, verbose=False):
    """How status draws its result: a small dashboard, internals only with --verbose (#1996)."""
    from .rem_status import dashboard
    return lambda value: dashboard(ctx.obj["root"], value, lambda arguments: _next(ctx, arguments), verbose=verbose)


def _moved(ctx, old: str, new: list):
    """An old name still works, and says what it is called now (#1656)."""
    rem_look.line(f"`co rem {old}` is now `{_next(ctx, new)}`; the old name works until 1.9.0.", err=True)


UNITS = {"people": "mails", "projects": "sessions", "orgs": "people"}
UNITS_ONE = {"mails": ("mail",), "sessions": ("session",), "people": ("person", "people"), "": ("", "")}


def _logged(root, record, phase, call):
    """Run one investigation and keep a run record of it, whatever happens.

    Investigations are co rem's most expensive calls and `co rem logs` did
    not list a single one: on a notebook with a dozen investigated pages it
    said "No runs recorded". A manual run is not charged to the background
    daily cap (runner_attempts stays 0), but its usage counts in logs --usage.
    """
    import uuid
    from ...rem.config import read_config
    from ...rem.files import state_path, write_json
    from ...rem.runner import RunFailed
    from ...rem.service import now
    from ...rem import quota
    from ...rem.investigate import NothingFound, NothingNew
    from ...rem.service import abandon_stale_runs, running_marker
    config = read_config(root)
    abandon_stale_runs(root)
    # Manual investigation counts toward the weekly budget like the round (#1842).
    run = {"id": "run_" + uuid.uuid4().hex, "started_at": now().isoformat(), "phase": phase,
           "record": record, "model": config["model"], "outcome": "running",
           "runner_attempts": 0, "usage": None, "changed": [], "sources": [], "items": 0,
           "quota": {"before": quota.read(config)}, **running_marker()}
    path = state_path(root, f"runs/{run['id']}.json")
    write_json(path, run)
    from .rem_output import Turn
    turn = Turn({"investigate me": "Writing your page…", "projects write": f"Writing {record}…"}
                .get(phase, f"Investigating {record}…"))

    def update(stage, processed=None, total=None, usage=None):
        run["stage"] = stage
        run["stage_updated_at"] = now().isoformat()
        if processed is not None:
            run["stage_processed"] = processed
        else:
            run.pop("stage_processed", None)
        if total is not None:
            run["stage_total"] = total
        else:
            run.pop("stage_total", None)
        if usage is not None:
            run["usage"] = usage
        write_json(path, run)
        detail = f" ({processed}/{total})" if processed is not None and total is not None else ""
        turn.stage(f"{stage}{detail}")

    try:
        with turn:
            result = call(update)
        run.update(outcome="completed", usage=result.get("usage"), usage_by_stage=result.get("usage_by_stage") or {},
                   changed=result.get("changed") or [], items=result.get("items", 0),
                   chars_in=result.get("chars_gathered") or 0, coverage=result.get("coverage") or [],
                   instructions_chars=result.get("instructions_chars") or {})
        _WRITTEN.append(record)
        return result
    except BaseException as error:
        run.update(outcome=("refused" if isinstance(error, RunFailed) and "rejected" in str(error) else
                            "nothing_new" if isinstance(error, NothingNew) else
                            "nothing_found" if isinstance(error, NothingFound) else
                            "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"),
                   error=str(error)[:1000], usage=getattr(error, "usage", None) or run.get("usage"))
        if isinstance(error, KeyboardInterrupt):
            raise
        from ...rem.files import RemError
        if isinstance(error, RemError):
            error._rem_retry_page = True
            raise
        failure = RemError(f"Investigation could not finish ({type(error).__name__}); "
                            "check co rem logs and retry this page")
        failure._rem_retry_page = True
        raise failure from error
    finally:
        run["finished_at"] = now().isoformat()
        run["quota"]["after"] = quota.read(config)
        from datetime import datetime
        run["seconds"] = round((datetime.fromisoformat(run["finished_at"])
                                - datetime.fromisoformat(run["started_at"])).total_seconds(), 1)
        write_json(path, run)


def _investigation_pages(notebook):
    return [path for path in notebook.list()
            if path.startswith(("people/", "projects/", "orgs/", "skills/catalog/"))
            and path != "skills/catalog/index.md"]


def _resolve_page(notebook, selector):
    from ...rem.files import RemError
    from ...rem.merge import aliases, resolve
    pages = _investigation_pages(notebook)
    # A page merged into another (#1974) answers to its old record and stem.
    table = aliases(notebook.root)
    selector = next((old for old in table if Path(old).stem == selector), selector)
    selector = resolve(notebook.root, selector)
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
        raise RemError("More than one page matches. Use an exact path:\n" + "\n".join(matches))
    raise RemError("No page matches that name, email or path. Run investigate without arguments to see available pages.")


def _interactive() -> bool:
    """Someone at a terminal, who can read what is about to be spent and press Ctrl-C."""
    import sys
    return sys.stdin.isatty() and sys.stdout.isatty()


def _mail_clients(root):
    """Investigating is an explicit request, so any mailbox this machine can
    already read is read, whether or not background sync is subscribed to it --
    `init` read the same mailboxes to build the map. Only a mailbox the user
    explicitly unsubscribed is left alone."""
    from ...rem.service import mail_available, mail_client, subscriptions
    sources = subscriptions(root)
    return {kind: mail_client(kind, attachments=True) for kind in ("outlook", "gmail")
            if mail_available(kind) and not sources.get(kind, {}).get("unsubscribed")}


def _mail_progress(kind, stop, count):
    rem_look.line(f"  {kind}: to {stop:%Y-%m-%d}, {count} mails", err=True)


def _investigate_me(root, *, days, quick, handle=()):
    """The owner's page from what they sent: `investigate me`, and init's last step (#1943)."""
    from ...rem.files import Notebook, RemError, read_json, state_path
    from ...rem.investigate import investigate
    from ...rem.service import subscriptions
    owner = read_json(state_path(root, "map.json"), {}).get("owner") or {}
    if not owner.get("record"):
        raise RemError("No page for you yet: init makes it from a connected mailbox or from your "
                        "name. Run `co rem init --name \"Your Name\"`")
    record = owner["record"]
    if not owner.get("addresses") and not handle:
        # A page made from --name alone has no address to find your own
        # mail by, and investigating it would run a model on nothing.
        raise RemError(f"Your page {record} has no mail address yet, and investigate me reads what "
                        "you sent. Connect a mailbox with co auth google or co auth microsoft, then "
                        "run `co rem init`")
    title = next((line[2:].strip() for line in Notebook(root).read(record).splitlines()
                  if line.startswith("# ")),
                 "Account owner")
    result = _logged(root, record, "investigate me", lambda update: investigate(
        root, record, title, [*owner.get("addresses", []), *handle], days=days or 30,
        clients=_mail_clients(root), subscriptions=subscriptions(root), progress=_mail_progress,
        sent_only=True, stage_progress=update, quick=quick))
    return result, record


def _first_page_skipped(ctx, root, result, *, want, problem, fix, retry, init) -> str:
    """Why init does not go on to write the owner's page, in one line, or ''.

    The owner decided (#1943) that investigating "me" starts by itself, so a
    first run needs no second command to discover. It does not start when it
    cannot succeed (no runner, no address of yours), when it would pay twice (the
    page is already written), or when nobody is watching to read what it will
    spend and stop it: a script or --json runs no model unless --investigate asks.
    """
    from ...rem.files import Notebook
    manual = _next(ctx, retry)
    if want is False or problem:
        return f"Your page was not written: {_spending_skipped(ctx, want=want, problem=problem, fix=fix)} " \
               f"Write it with {manual}."
    owner = result.get("owner") or {}
    if not owner.get("record") or not owner.get("addresses"):
        return ("Your page was not written: no mailbox gave an address of yours, and it is written from "
                "what you sent. Connect one with co auth google or co auth microsoft, then run "
                + _next(ctx, init) + ".")
    page = Notebook(root).path(owner["record"])
    status = next((line for line in page.read_text(encoding="utf-8").splitlines()
                   if line.startswith("Investigation:")), "") if page.is_file() else ""
    if status and "not investigated" not in status:
        return f"Your page was already written; nothing spent. Refresh it with {manual}."
    shared = _spending_skipped(ctx, want=want, problem=problem, fix=fix)
    return f"Your page was not written: {shared} Write it with {manual}." if shared else ""


def _spending_skipped(ctx, *, want, problem, fix) -> str:
    """Why init spends nothing on a model after the map, or ''.

    The same rules for the owner's page and for recent project pages: asked
    not to, a runner that cannot run, or nobody watching to read the cost and
    press Ctrl-C (a script, or --json, runs no model unless --investigate asks).
    """
    if want is False:
        return "--no-investigate was given."
    if problem:
        return f"{problem}; fix it with {fix}."
    if want is None and ctx.obj["json"]:
        return "--json runs no model unless --investigate asks."
    if want is None and not _interactive():
        return "not a terminal, so nobody could stop it; rerun init with --investigate to allow it."
    return ""


# The first run's spending (owner, 2026-09-30; capped in #2008): your page from
# everything you sent, the few people you write to most, then your few most
# recent projects -- enough that the first minutes show something true about you
# and the people around you, never more than half of the notebook's weekly
# investigation budget, and one total said before the first page.
FIRST_RUN_POINTS = 5


def _first_run_gate(root, config):
    """Before each first-run page: why not to start it, or ''.

    The weekly floor and budget as for any investigation (#1843), and this
    run's own FIRST_RUN_POINTS of the Codex week. Without a meter (another
    runner, or Codex not reporting) the page counts are the only bound.
    """
    from ...rem import quota
    from ...rem.service import run_logs
    start = quota.read(config)

    def gate():
        meter = quota.read(config)
        stop = quota.blocks(meter, quota.points_spent(run_logs(root), meter), config["limits"])
        if stop or "unknown" in meter or "unknown" in start:
            return stop
        used = meter["used_percent"] - start["used_percent"]
        return (f"the first run has used {used} of its {FIRST_RUN_POINTS} points of the Codex week"
                if used >= FIRST_RUN_POINTS else "")
    return gate


def _first_people_rows(root, cap: int, recent_days: int) -> list[dict]:
    """The people the first run will write: the `investigate people` queue's first `cap`."""
    from ...rem.people_pages import queue
    return queue(root, recent_days=recent_days)[:cap]


def _first_project_rows(root, cap: int) -> list[dict]:
    """The projects the first run will write: the `cap` most recently active (no model)."""
    from ...rem.project_material import extract
    from ...rem.project_pages import queue
    from ...rem.service import subscriptions
    extract(root, subscriptions(root))
    return [row for row in queue(root) if row["recent"]][:cap]


def _first_people(ctx, root, gate, *, cap: int, days: int, recent_days: int = 14) -> dict:
    """The people you wrote to most recently, after your own page (owner, 2026-09-30).

    The same queue, one-turn investigation and lines as `co rem investigate
    people`, cut to `cap` and to the first run's budget, and reading the run's
    own `--days` window rather than the 150 days a full investigation reads
    (#2008). The daily round works through the rest.
    """
    from ...rem.service import subscriptions
    from .rem_people import run_people
    if cap <= 0:
        return {"started": False, "reason": ""}
    stopped = gate()
    if stopped:
        return {"started": False, "reason": f"People pages were not written: {stopped}."}
    result, _, _ = run_people(ctx, root, limit=cap, recent_days=recent_days, days=days, list_only=False,
                              gate=gate, clients_for=_mail_clients, subscriptions=subscriptions, logged=_logged,
                              announce=False)
    return result if isinstance(result, dict) else {"started": False, "reason": result}


def _first_projects(ctx, root, config, plan, say, gate=None, *, cap: int = 3) -> dict:
    """The pages of your `cap` most recently active projects, after your own page (#1943, #2008).

    The owner decided the first run should also leave the projects you are
    working on now written, from the messages you typed in their Codex and
    Claude Code sessions (#1947's `co rem projects write`). The cost was said
    once, before the first page; stopped by the weekly budget and floor like any
    investigation, one line per page. The rest wait for `co rem projects write`.
    """
    from ...rem import quota
    from ...rem.files import RemError
    from ...rem.project_pages import RECENT_DAYS, write_page, write_pages
    from ...rem.service import run_logs
    recent = _first_project_rows(root, cap) if cap > 0 else []
    if not recent:
        return {"started": False, "reason": "" if cap <= 0 else
                f"No project active in the last {RECENT_DAYS} days has messages to write from."}

    def weekly():
        reading = quota.read(config)
        return quota.blocks(reading, quota.points_spent(run_logs(root), reading), config["limits"])
    gate = gate or weekly
    stopped = gate()
    if stopped:
        return {"started": False, "reason": f"Project pages were not written: {stopped}."}

    def one(record):
        try:
            _logged(root, record, "projects write", lambda update: write_page(root, record, config=config))
        except RemError as error:
            say(f"  {record}: not written ({str(error)[:120]})")
            raise
        say(f"  {record}: written")

    done = write_pages(root, limit=len(recent), write=one, gate=gate)
    if done.get("stopped"):
        say(f"Stopped before the rest: {done['stopped']}. Write them later with {_next(ctx, ['projects', 'write'])}.")
    return {"started": True, **done}


def _init_done(ctx, result) -> str:
    """init's last word (#1996): what is in the notebook, skills included, what was written, what is next.

    The map's summary is printed before anything is spent; by the end it has
    scrolled away under the model turns, so the counts are said once more.
    """
    skills = result.get("skills") or {}
    names = len({str(row.get("name", "")).casefold() for row in skills.get("skills") or []})
    counts = [f"{len(result.get(kind) or [])} {label}" for kind, label in
              (("people", "people"), ("orgs", "organizations"), ("projects", "projects"))]
    written = (["your page"] if (result.get("investigate_me") or {}).get("outcome") == "completed" else [])
    people = sum(page.get("outcome") == "accepted" for page in (result.get("people_pages") or {}).get("pages") or [])
    written += [f"{people} {'person' if people == 1 else 'people'}"] if people else []
    projects = sum(page.get("outcome") == "accepted" for page in (result.get("project_pages") or {}).get("pages") or [])
    written += [f"{projects} project page{'s' if projects != 1 else ''}"] if projects else []
    owner = (result.get("owner_page") or {}).get("path") or ""
    return "\n".join([
        "",
        f"Your notebook: {', '.join(counts)} and {names} skill{'s' if names != 1 else ''}.",
        "Written this run: " + (", ".join(written[:-1]) + " and " + written[-1] if len(written) > 1
                                else written[0] if written else "nothing yet") + ".",
        *([f"Your page: {owner}"] if owner else []),
        "Then keep it current: " + _next(ctx, ["start"]) + " (it asks before anything is read in the background)."])


def make_rem_app(factory):
    rem = factory(help="co rem", no_args_is_help=False)
    base = verbatim("co rem", rem.info.cls)

    class RemGroup(base):
        def invoke(self, ctx):
            # The callback below runs before Click prints a subcommand's help,
            # and by then the subcommand's arguments are gone from ctx; here
            # they are still visible. `co rem projects --help` moved the
            # owner's real notebook and replaced their schedule: reading a help
            # page writes nothing.
            rest = [*getattr(ctx, "_protected_args", []), *ctx.args]
            ctx.meta["rem_asks_help"] = "--help" in rest
            return super().invoke(ctx)

    rem.info.cls = RemGroup

    @rem.callback(invoke_without_command=True)
    def overview(ctx: typer.Context,
                 root: Optional[Path] = typer.Option(None, "--root", help="Notebook root (default ~/.co/rem)"),
                 json_out: bool = typer.Option(False, "--json", help="Machine-readable output with next command")):
        ctx.obj = {"root": (root or Path.home() / ".co/rem").expanduser().resolve(),
                   "default_root": root is None, "json": json_out}
        if not ctx.resilient_parsing and not ctx.meta.get("rem_asks_help"):
            _carry_over(ctx)
        if ctx.invoked_subcommand is None:
            if ctx.obj["json"]:
                inspect_status(ctx, verbose=False)
            else:
                from ...rem.service import status
                show("co rem")
                typer.echo()
                def operation(root):
                    result = status(root)
                    return result, ["investigate"] if result["configured"] else ["init"]
                _handle(ctx, operation, ["config"], draw=_dashboard(ctx))

    V = verbatim

    # ------------------------------------------------------------------ Build

    @rem.command("init", cls=V("co rem init"))
    def init_rem(ctx: typer.Context,
                  days: int = typer.Option(90, "--days", min=1),
                  skills_dir: List[Path] = typer.Option([], "--skills-dir"),
                  mine: List[str] = typer.Option([], "--mine"),
                  mail: List[str] = typer.Option([], "--mail"),
                  name: str = typer.Option("", "--name"),
                  archive_mail: bool = typer.Option(True, "--archive-mail/--no-mail-archive"),
                  write_mine: Optional[bool] = typer.Option(None, "--investigate/--no-investigate"),
                  first_people: int = typer.Option(3, "--first-people", min=0),
                  first_projects: int = typer.Option(3, "--first-projects", min=0)):
        from ...rem.config import prepare, read_config
        from ...rem.files import Notebook, state_path
        from ...rem.map import build_map, owner_summary
        from ...rem import runner as rem_runner
        from ...rem.service import mail_available, mail_client, subscribe_read_mail, subscriptions
        from .rem_output import StageProgress
        # One run confirms several addresses: `--mine a,b,c` as well as repeating it.
        owned = [part.strip() for value in mine for part in value.split(",") if part.strip()]

        def run(root):
            prepare(root)
            # Before the ten-minute map, not after it: a missing or signed-out
            # runner used to surface only when the first model turn failed.
            config = read_config(root)
            problem, fix = rem_runner.ready(config)
            window = [] if days == 90 else ["--days", str(days)]
            sources = subscriptions(root)
            from ...rem.files import RemError
            selected = set(mail)
            if selected - {"gmail", "outlook"}:
                raise RemError("--mail must be gmail or outlook")
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
            # One line per stage on the terminal; every step in the log (#1943).
            progress = StageProgress(log=state_path(root, "init-progress.log"), quiet=ctx.obj["json"], days=days)
            try:
                result = build_map(root, sources, clients, days=days,
                                   skill_directories=skills_dir or None, mine=owned, source_errors=errors,
                                   absent=_absent_mail(selected, available, failed, sources, bool(mail)), name=name,
                                   capture_sources=True, progress=progress)
                if archive_mail and result.get("source_inventory"):
                    from ...rem.files import read_json, write_json
                    from ...rem.mail_archive import archive_init
                    previous = read_json(state_path(root, "mail/archive.json"), {})
                    incomplete_scan = any(row.get("source") in ("gmail", "outlook")
                                          for row in result.get("errors", []))
                    if previous and (not clients or incomplete_scan):
                        body_report = {"phase": "previous_preserved", "started": previous.get("started"),
                                       "target": previous.get("target", 0),
                                       "reason": "Current mail enumeration unavailable; previous private archive retained"}
                    else:
                        body_report = archive_init(root, result, clients, progress=progress)
                    result["mail_archive"] = body_report
                    if body_report.get("failed"):
                        result["errors"].append({"source": "mail-archive", "stage": "body",
                                                 "error": f"{body_report['failed']} message{'' if body_report['failed'] == 1 else 's'} unavailable"})
                        result["phase"] = "partial"
                    write_json(state_path(root, "map.json"), result)
            finally:
                progress.close()
            unread = {row.get("source") for row in result.get("errors") or []}
            subscribe_read_mail(root, [kind for kind in clients if kind not in unread])
            tips = []
            for kind, provider in (("gmail", "google"), ("outlook", "microsoft")):
                if kind not in available:
                    tips.append(f"Connect {provider.title()} for People: co auth {provider}; then run "
                                + _next(ctx, ["init", *window]) + ".")
            if result.get("needs_review"):
                tips.append(f"Held for review, not investigated or listed (no name, never written to): "
                            f"{len(result['needs_review'])}. See " + _next(ctx, ["list", "people", "--review"]))
            if tips:
                result["tips"] = tips
            candidates = result.get("possible_own_addresses") or []
            if candidates:
                # The owner is the only one who can answer this, so the question
                # arrives with the command that answers it, spelled for the root
                # they actually used. Asked once, in one place: the owner's first
                # run ended with twelve questions and a command for each (#1943).
                shown = candidates[:6]
                more = len(candidates) - len(shown)
                result["confirm_own_addresses"] = [
                    "Possibly yours too (you wrote, they never replied): "
                    + ", ".join(f"{row['address']} ({row['sent']} sent, none received)" for row in shown)
                    + (f", and {more} more in .state/map.json" if more else "")
                    + ".\nConfirm the ones that are yours in one run: "
                    + _next(ctx, ["init", *window, "--mine", ",".join(row["address"] for row in shown)])
                    + " (leave out an assistant's or a relative's; nothing is merged without --mine)."]
            summary = owner_summary(Notebook(root), result) if result.get("owner") else None
            if summary:
                result["owner_page"] = summary
            if not selected:
                result["people_setup"] = "No connected mail source. Local maps are ready; connect mail to add People."
            if result.get("errors"):
                retry = ["init", *window]
                if mail:
                    retry += [part for kind in mail for part in ("--mail", kind)]
                result["recovery"] = ("Check mailbox access with co auth status; retry init after resolving access. "
                                      "Completed maps and saved mail bodies are reused.")
                _emit(ctx, result, retry, failed=True)
                raise typer.Exit(1)
            result["runner"] = {"runner": config["runner"], "model": config["model"], "ready": not problem,
                                **({"problem": problem, "fix": fix} if problem else {})}
            retry_me = ["investigate", "me", *window]
            reason = _first_page_skipped(ctx, root, result, want=write_mine, problem=problem, fix=fix,
                                         retry=retry_me, init=["init", *window])
            if not ctx.obj["json"]:
                # The map's summary and your page's facts first: value before any spending.
                text = render(result, "init")
                rem_look.say(rem_look.result(text), plain=text)
                typer.echo()
            say = ((lambda text: None) if ctx.obj["json"] else
                   lambda text: rem_look.say(rem_look.highlight(text, counts=True), plain=text))
            plan = rem_runner.PLAN.get(config["runner"], "on the configured runner")
            from ...rem.files import RemError
            skipped = _spending_skipped(ctx, want=write_mine, problem=problem, fix=fix)
            if reason:
                result["investigate_me"] = {"started": False, "reason": reason}
                say(reason)
            if skipped:
                result["people_pages"] = {"started": False, "reason": "People pages were not written: " + skipped}
                result["project_pages"] = {"started": False, "reason": "Project pages were not written: " + skipped}
                if skipped not in (reason or ""):  # said once: the owner-page line may already say why
                    say(result["project_pages"]["reason"])
                return (result if ctx.obj["json"] else _init_done(ctx, result)), ["open"]
            # One total before the first page (#2008): 1.9.0a5 said "~90k per
            # project page, about a minute" and spent 614k-922k and 4-5 minutes
            # each, on every project active in the window, with no total at all.
            from ...rem import first_run
            from .rem_people import counted
            from ...rem.service import run_logs
            recent = min(14, days)
            people_rows = _first_people_rows(root, first_people, recent)
            project_rows = _first_project_rows(root, first_projects) if first_projects > 0 else []
            total = first_run.plan(run_logs(root), owner=not reason, people=len(people_rows),
                                   projects=len(project_rows))
            result["first_run"] = {**total, "people": [row["record"] for row in people_rows],
                                   "projects": [row["record"] for row in project_rows]}
            me_days = days if window else 30  # what `investigate me` reads without --days
            steps = ([f"your own page from everything you sent and your coding sessions of the last {me_days} days"]
                     if not reason else [])
            steps += ([f"the {counted(len(people_rows), 'person', 'people')} you wrote to most in the last {recent} days, from the "
                       f"last {days} days of their mail"] if people_rows else [])
            steps += ([f"the {counted(len(project_rows), 'project')} you worked on most recently"] if project_rows else [])
            if not steps:
                return (result if ctx.obj["json"] else _init_done(ctx, result)), ["open"]
            cost = (f"First run with {config['runner']} ({config['model']}): " + ", then ".join(steps) + ". "
                    + first_run.announce(total, plan) + f" It stops at {FIRST_RUN_POINTS} points of the Codex "
                    "week; --first-people and --first-projects change the counts. Ctrl-C stops it and keeps the "
                    "map and every page written. (--no-investigate skips this.)")
            rem_look.say(rem_look.highlight(cost, counts=True), err=ctx.obj["json"], plain=cost)
            gate = _first_run_gate(root, config)
            if not reason:
                try:
                    _investigate_me(root, days=days if window else None, quick=False)
                except KeyboardInterrupt:
                    result.update(investigation="interrupted",
                                  investigate_me={"started": True, "outcome": "interrupted"})
                    _interrupted(ctx, retry_me, result)
                except (RemError, rem_runner.RunFailed) as error:
                    result.update(investigation="failed",
                                  investigate_me={"started": True, "outcome": "failed", "why": str(error)})
                    return (result if ctx.obj["json"] else
                            f"Your page was not written: {error} The map is kept."), retry_me, True
                record = summary["record"] if summary else result["owner"]["record"]
                result.update(investigation="completed",
                              investigate_me={"started": True, "outcome": "completed", "page": record})
                say("Your page is written: " + str(Notebook(root).path(record)))
            # Then the people you write to most, and the projects you worked on,
            # by the same rules and one budget (#1943).
            try:
                result["people_pages"] = _first_people(ctx, root, gate, cap=len(people_rows), days=days,
                                                       recent_days=recent)
            except KeyboardInterrupt:
                result["people_pages"] = {"started": True, "outcome": "interrupted"}
                _interrupted(ctx, ["investigate", "people"], result)
            if result["people_pages"].get("reason"):
                say(result["people_pages"]["reason"])
            try:
                result["project_pages"] = _first_projects(ctx, root, config, plan, say, gate,
                                                          cap=len(project_rows))
            except KeyboardInterrupt:
                result["project_pages"] = {"started": True, "outcome": "interrupted"}
                _interrupted(ctx, ["projects", "write"], result)
            if result["project_pages"].get("reason"):
                say(result["project_pages"]["reason"])
            return (result if ctx.obj["json"] else _init_done(ctx, result)), ["open"]
        _handle(ctx, run, ["sources"])

    @rem.command("investigate", cls=V("co rem investigate"))
    def investigate_page(ctx: typer.Context,
                         target: str = typer.Argument(""),
                         handle: List[str] = typer.Option([], "--handle"),
                         days: Optional[int] = typer.Option(None, "--days", min=1),
                         quick: bool = typer.Option(False, "--quick", help="Bounded first pass for your own page"),
                         limit: Optional[int] = typer.Option(None, "--limit", min=0),
                         budget: Optional[int] = typer.Option(None, "--budget", min=1, max=100),
                         list_only: bool = typer.Option(False, "--list"),
                         recent_days: Optional[int] = typer.Option(None, "--recent-days", min=1),
                         eval_dir: List[Path] = typer.Option([], "--eval-dir")):
        from ...rem.files import Notebook, RemError, read_json, state_path
        from ...rem.investigate import investigate
        from ...rem import queue as rem_queue
        from ...rem.queue import CATEGORIES, order
        # With a budget the budget is the bound; otherwise five pages, as before.
        pages_limit = limit if limit is not None else (0 if budget else 5)
        runnable = (*CATEGORIES, "all")
        from ...rem.runner import RunFailed
        from ...rem.service import subscriptions
        clients_for, progress = _mail_clients, _mail_progress

        def one(root, notebook, record):
            if record.startswith("skills/"):
                from ...rem.skill_runs import investigate_skill_runs
                return investigate_skill_runs(root, record, eval_dir or [Path.home() / ".co/evals"])
            if eval_dir:
                raise RemError("--eval-dir applies only to skills pages")
            text = notebook.read(record)
            title = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), record)
            known = []
            if record.startswith("people/"):
                person = next((p for p in notebook.people() if p["path"] == record), {})
                known += person.get("emails", []) + person.get("aliases", [])
            for line in text.splitlines():
                low = line.strip().lstrip("-").strip().casefold()
                if low.startswith(("also known as:", "email:", "handles:")) and ":" in line:
                    from ...rem.files import split_handles
                    known += split_handles(line.split(":", 1)[1])
            handles = list(dict.fromkeys([*handle, *known, title.split(" (")[0]]))
            clients = clients_for(root)
            if record.startswith("projects/"):
                # A project is read from where it lives: the sessions run in its
                # folders. Matching mail on its name pulled in every notification
                # and signature that mentioned it -- 3,500 mails scanned for one
                # project on a real mailbox, then a turn that timed out. Mail about
                # a project comes in through --handle, named on purpose.
                from ...rem.investigate import project_paths
                handles = list(dict.fromkeys([*handle, *project_paths(text), title]))
                clients = {kind: client for kind, client in clients.items() if handle}
            skipped = "" if clients or not record.startswith("projects/") else \
                "not read for a project page; name its mail with --handle"
            from ...rem.investigate import window_since
            return _logged(root, record, "investigate", lambda update: investigate(
                root, record, title, handles, days=days or window_since(text), clients=clients,
                subscriptions=subscriptions(root), progress=progress, mail_skipped=skipped,
                stage_progress=update))

        def overview(root):
            from ...rem.people_pages import queue as people_queue
            from .rem_people import owner_first
            state = read_json(state_path(root, "map.json"), {})
            owner = (state.get("owner") or {}).get("record")
            if not owner and not Notebook(root).list():
                return "No pages available to investigate: the map has not been built yet.", ["init"]
            rows = {}
            # Your own page first while it has never been investigated (#1943,
            # #1974); "has an Unknown" kept the Next line on it forever.
            first_lines = owner_first(ctx, root)
            pending = bool(owner) and any(line.startswith("First, your own page") for line in first_lines)
            if owner:
                rows["me"] = {"page": owner, "investigated": not pending}
            if first_lines:
                rows["first"] = first_lines
            for category in CATEGORIES:
                if category == "people":
                    # The same queue `investigate people --list` prints and runs (#1974).
                    queue = people_queue(root)
                    rows[category] = {"unfinished": len(queue), "next": [row["record"] for row in queue][:3]}
                    continue
                queue = order(root, category)
                rows[category] = {"unfinished": len(queue),
                                  "next": [row["path"] for row in queue if not row["recent"]][:3]}
            first = next((c for c in CATEGORIES if rows[c]["next"]), None)
            return rows, (["investigate", "me"] if pending
                          else ["investigate", first] if first else ["list"])

        def by_category(root, category):
            ranked = (lambda: rem_queue.order_all(root)) if category == "all" else (lambda: order(root, category))
            queue = [row for row in ranked() if not row["recent"]]
            chosen = queue if pages_limit == 0 else queue[:pages_limit]
            if list_only:
                rows = ranked()
                if not ctx.obj["json"]:
                    from .rem_people import counted
                    unit = UNITS.get(category)
                    rows = [f"{row['path']}  ("
                            + (f"{counted(row['weight'], *UNITS_ONE[unit or UNITS.get(row['path'].split('/')[0], '')])}, "
                               if unit or category == "all" else "")
                            + (f"investigated {row['last_investigated']}" if row["last_investigated"]
                               else "not investigated") + (", skipped: this week" if row["recent"] else "") + ")"
                            for row in rows]
                return {"category": category, "order": rows}, ["investigate", category]
            notebook, done, stopped = Notebook(root), [], ""
            gate = budget_gate(root)
            for number, row in enumerate(chosen, 1):
                stopped = gate()
                if stopped:
                    rem_look.line(f"Stopped: {stopped}", err=True)
                    break
                rem_look.line(f"[{number}/{len(chosen)}] {row['path']}", err=True)
                try:
                    one(root, notebook, row["path"])
                    done.append({"page": row["path"], "outcome": "accepted"})
                except RunFailed as error:
                    done.append({"page": row["path"], "outcome": "refused", "why": str(error)})
                except RemError as error:
                    done.append({"page": row["path"], "outcome": "failed", "why": str(error)})
            skipped = [row["path"] for row in ranked() if row["recent"]]
            accepted = [row["page"] for row in done if row["outcome"] == "accepted"]
            return ({"category": category, "pages": done, "skipped_recent": skipped,
                     "left": max(len(queue) - len(done), 0), **({"stopped": stopped} if stopped else {})},
                    ["show", accepted[0]] if accepted else ["logs"],
                    any(row["outcome"] != "accepted" for row in done))

        def budget_gate(root):
            """Before each page: why not to start it, or ''. Reads the Codex week
            (#1843): the weekly budget, this run's --budget, and the floor."""
            from ...rem import quota
            from ...rem.config import read_config
            from ...rem.service import run_logs
            config = read_config(root)
            start = quota.read(config)

            def gate():
                meter = quota.read(config)
                stop = quota.blocks(meter, quota.points_spent(run_logs(root), meter), config["limits"])
                if stop or not budget or "unknown" in meter or "unknown" in start:
                    return stop
                used = meter["used_percent"] - start["used_percent"]
                return f"this run has used {used} of its {budget}-point budget" if used >= budget else ""
            return gate

        def me(root):
            result, record = _investigate_me(root, days=days, quick=quick, handle=handle)
            return result, ["show", record]

        def run(root):
            if quick and target != "me":
                raise RemError("--quick is for `co rem investigate me` only")
            if budget and target not in runnable:
                raise RemError("--budget goes with a category: co rem investigate all --budget 10")
            if list_only and target not in runnable:
                raise RemError("--list goes with a category: co rem investigate people --list "
                                "(or projects, orgs, skills)")
            if recent_days is not None and target != "people":
                raise RemError("--recent-days goes with people: co rem investigate people --recent-days 14")
            if not target:
                return overview(root)
            if target == "people":
                # An agent searching each person's prepared evidence (#1943, #1850).
                from .rem_people import run_people
                return run_people(ctx, root, limit=pages_limit, recent_days=recent_days or 14, days=days,
                                  list_only=list_only, gate=None if list_only else budget_gate(root),
                                  clients_for=clients_for, subscriptions=subscriptions, logged=_logged)
            if target == "me":
                return me(root)
            if target in runnable:
                return by_category(root, target)
            notebook = Notebook(root)
            record = _resolve_page(notebook, target)
            result = one(root, notebook, record)
            return result, ["show", result["report"] if record.startswith("skills/") else record]
        retry = ["investigate", *([target] if target else []),
                 *(["--days", str(days)] if days is not None else []),
                 *(["--quick"] if quick else [])]
        _handle(ctx, run, ["investigate"], retry=retry, resume=retry)

    # ------------------------------------------------------------------- Read

    @rem.command("open", cls=V("co rem open"))
    def open_page(ctx: typer.Context,
                  launch: bool = typer.Option(True, "--launch/--no-launch"),
                  live: bool = typer.Option(False, "--live"),
                  local: bool = typer.Option(False, "--local")):
        from ...rem import reader

        def operation(root):
            from connectonion.project import selected_identity_dir
            from connectonion import address

            # The live view reads the default notebook through the co ai identity
            # (#1637); a custom --root is never assumed to belong to it.
            identity = (address.load(selected_identity_dir())
                        if ctx.obj["default_root"] and root.is_dir() else None)
            # The snapshot is the default (#1828); the live view is asked for.
            wanted = not local and (live or reader.LIVE_IS_DEFAULT)
            result = reader.live_or_snapshot(root, identity and identity["address"],
                                             live=wanted, launch=launch)
            return result, ["status"] if launch else ["open"]   # --no-launch: open is what shows it (#2008)
        _handle(ctx, operation, ["doctor"])

    @rem.command("list", cls=V("co rem list"))
    def list_records(ctx: typer.Context, category: str = typer.Argument(""),
                     aliases: bool = typer.Option(False, "--aliases"),
                     review: bool = typer.Option(False, "--review")):
        from ...rem.files import CATEGORIES, Notebook, RemError
        from ...rem.map import needs_review

        def operation(root):
            notebook = Notebook(root)
            if aliases:
                if category not in ("", "people"):
                    raise RemError("--aliases goes with people")
                people = notebook.people()
                return people, (["show", people[0]["path"]] if people else ["init"])
            held = needs_review(root)
            if review:
                if category not in ("", "people"):
                    raise RemError("--review goes with people")
                return sorted(held), (["show", min(held)] if held else ["list", "people"])
            if not category:
                counts = {name: count for name in CATEGORIES if (count := len(set(notebook.list(name)) - held))}
                return (counts, ["list", next(iter(counts))]) if counts else ([], ["init"])
            from ...rem.queue import by_weight
            records = [record for record in by_weight(root, notebook.list(category)) if record not in held]
            if not records and category == "people" and not ctx.obj["json"]:
                from ...rem.files import state_path
                from ...rem.service import mail_available
                # Right after init this said "Run init to build the map", to
                # someone who just had. People come only from a mailbox.
                if state_path(root, "map.json").is_file() and not any(
                        mail_available(kind) for kind in ("gmail", "outlook")):
                    return ("No people yet: people pages come from a connected mailbox, and none is "
                            "connected. Connect one with co auth google or co auth microsoft, then run "
                            + _next(ctx, ["init"]) + "."), ["sources"]
            return records, (["show", records[0]] if records else ["list"])
        _handle(ctx, operation, ["list"])

    @rem.command("show", cls=V("co rem show"))
    def show_record(ctx: typer.Context, record: str = typer.Argument(...)):
        from ...rem.files import CATEGORIES, Notebook, RemError, read_json, state_path
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
                    raise RemError("No page for you yet: init makes it from a connected mailbox or from your "
                                    "name. Run `co rem init --name \"Your Name\"`")
                category = page.split("/")[0]
            from ...rem.merge import resolve
            text = Notebook(root).read(resolve(root, page))
            return text, (["investigate", record] if "Unknown" in text else ["list", category])
        _handle(ctx, operation, recovery)

    @rem.command("search", cls=V("co rem search"))
    def search_records(ctx: typer.Context, query: str = typer.Argument(...),
                       within: str = typer.Option("", "--in"),
                       old_type: str = typer.Option("", "--type")):
        from ...rem.files import Notebook
        def operation(root):
            found = Notebook(root).search(query, within or old_type)
            return found, ["show", found[0]["record"]] if found else ["list"]
        _handle(ctx, operation, ["list"])

    # -------------------------------------------------------- Keep it current

    @rem.command("start", cls=V("co rem start"))
    def start_rem(ctx: typer.Context, yes: bool = typer.Option(False, "--yes")):
        import sys

        from ...rem import schedule as rem_schedule
        from ...rem.files import RemError
        from ...rem.service import start

        def confirm(summary):
            text = render(summary, "start — source access and schedule")
            if yes:
                if any("if you approve" in str(source.get("state")) for source in summary["sources"].values()):
                    # --yes approves what was shown before; a mailbox offered for
                    # the first time is shown now, on stderr (#1974).
                    rem_look.say(rem_look.result(text), err=True, plain=text)
                return True
            if not sys.stdin.isatty():
                rem_look.say(rem_look.result(text), err=True, plain=text)
                rem_look.line("A noninteractive start cannot consent silently; read the summary above "
                           "and run with --yes, or run `co rem start` in a terminal.", err=True)
                return False
            rem_look.say(rem_look.result(text), plain=text)
            return typer.confirm("Read these sources with this model and schedule?", default=False)

        def operation(root):
            result = start(root, confirm=confirm, scheduler=rem_schedule.default_scheduler())
            if not result["started"]:
                raise RemError("Start was not confirmed; nothing was read or installed")
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

    @rem.command("stop", cls=V("co rem stop"))
    def stop_rem(ctx: typer.Context):
        from ...rem import schedule as rem_schedule
        from ...rem.service import stop
        _handle(ctx, lambda root: (stop(root, scheduler=rem_schedule.default_scheduler()), ["status"]), ["status"])

    @rem.command("status", cls=V("co rem status"))
    def inspect_status(ctx: typer.Context, verbose: bool = typer.Option(False, "--verbose")):
        from ...rem.service import status
        from .rem_status import status_next

        def operation(root):
            value = status(root, live_quota=True)
            return value, status_next(value)
        _handle(ctx, operation, ["config"],
                draw=_dashboard(ctx, verbose))

    def _sync(ctx, source, with_person, dry_run, scheduled, all_pending, days):
        from ...rem.files import RemError
        from ...rem.service import run_sync

        finished = []

        def progress(number, record):
            # A backfill ran 37 minutes over five batches with no output at all
            # (#1957). One line per batch, on stderr so --json stays one document.
            finished.append(record)
            rem_look.line(f"Batch {number}: {record['items']} items, {len(record.get('changed') or [])} pages "
                       f"changed, {record.get('runner_attempts', 0)} model calls, {record.get('seconds')}s "
                       f"({record['outcome']})", err=True)

        def operation(root):
            if dry_run or source or with_person or all_pending:
                try:
                    record = run_sync(root, source=source, with_person=with_person, dry_run=dry_run,
                                      scheduled=scheduled, all_pending=all_pending, on_batch=progress)
                except KeyboardInterrupt:
                    # Ctrl-C exited 130 with nothing said; the finished batches are
                    # kept, and the interrupted one reads again next time.
                    pages = len({page for record in finished for page in record.get("changed") or []})
                    rem_look.line(f"Stopped: {len(finished)} batch{'es' if len(finished) != 1 else ''} finished "
                               f"({sum(r['items'] for r in finished)} items, {pages} pages changed); the "
                               f"interrupted batch reads again next time. See {_next(ctx, ['logs'])}.", err=True)
                    raise typer.Exit(130)
                if scheduled and record is None:
                    return {"due": False, "ran": False}, ["status"]
                if all_pending:
                    if record["outcome"] not in ("caught_up",):
                        why = record.get("reason") or record["outcome"]
                        raise RemError(f"Backfill stopped after {record['batches']} batches "
                                       f"({record['items']} items): {why}")
                    return record, ["status"]
                if dry_run:
                    return record, ["sync"]
                if record["outcome"] == "failed":
                    # A failed batch must not exit 0: an agent chaining `sync && ...` would walk past it.
                    raise RemError(f"Batch {record['id']} failed: {record.get('error')}")
                return record, ["logs", record["id"]]
            # The whole update: new material first, then at most one unfinished page.
            from ...rem.daily import run_daily
            result = run_daily(root, days=days, scheduled=scheduled)
            if result is None:
                return {"due": False, "ran": False}, ["status"]
            if result["outcome"] == "partial":
                _emit(ctx, result, ["logs"], failed=True)
            return result, ["logs"]
        _handle(ctx, operation, ["logs"])

    @rem.command("sync", cls=V("co rem sync"))
    def sync_rem(ctx: typer.Context,
                  source: str = typer.Option("", "--source"),
                  with_person: str = typer.Option("", "--with"),
                  dry_run: bool = typer.Option(False, "--dry-run"),
                  scheduled: bool = typer.Option(False, "--scheduled"),
                  all_pending: bool = typer.Option(False, "--all"),
                  days: int = typer.Option(30, "--days", min=1)):
        _sync(ctx, source, with_person, dry_run, scheduled, all_pending, days)

    # --------------------------------------------------------------- Settings

    sources_app = factory(help="co rem sources", no_args_is_help=False)
    sources_app.info.cls = verbatim("co rem sources", sources_app.info.cls)
    rem.add_typer(sources_app, name="sources")

    @sources_app.callback(invoke_without_command=True)
    def inspect_sources(ctx: typer.Context):
        from ...rem.service import subscriptions
        if ctx.invoked_subcommand is None:
            _handle(ctx, lambda root: (subscriptions(root), ["sync", "--dry-run"]), ["config"])

    def _add_source(ctx, name, chat, project, about, since, only, force):
        from ...rem.service import set_window, toggle_source

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
        from ...rem.service import subscriptions, toggle_source

        def operation(root):
            toggle_source(root, name, False, chats=chat)
            source = subscriptions(root)[name]
            return {"subscription": name, "enabled": bool(source.get("enabled")),
                    **({"chats": source.get("chats") or []} if chat else {})}, ["sources"]
        _handle(ctx, operation, ["sources"])

    @sources_app.command("add", cls=V("co rem sources add"))
    def add_source(ctx: typer.Context, name: str = typer.Argument(...),
                   chat: List[str] = typer.Option([], "--chat"),
                   project: str = typer.Option("", "--project"),
                   about: str = typer.Option("", "--about"),
                   since: str = typer.Option("", "--since"),
                   only: bool = typer.Option(False, "--only"),
                   force: bool = typer.Option(False, "--force")):
        _add_source(ctx, name, chat, project, about, since, only, force)

    @sources_app.command("remove", cls=V("co rem sources remove"))
    def remove_source(ctx: typer.Context, name: str = typer.Argument(...),
                      chat: List[str] = typer.Option([], "--chat")):
        _remove_source(ctx, name, chat)

    config_app = factory(help="co rem config", no_args_is_help=False)
    config_app.info.cls = verbatim("co rem config", config_app.info.cls)
    rem.add_typer(config_app, name="config")

    @config_app.callback(invoke_without_command=True)
    def inspect_config(ctx: typer.Context):
        from ...rem.config import read_config
        from ...rem.inquiry import routing
        from ...rem.tier import describe

        def operation(root):
            config = read_config(root, validated=False)
            tier = describe(root, config)
            # Unchecked runs as the agent tier, said so, with the command that measures it (#1847).
            if not tier["checked"]:
                # In the note, not the Next line: "Next: co rem config set model
                # gpt-6-luna" read as "you have not set the model yet" (#1974).
                tier["note"] += (f"; to check it, set the same model again: "
                                 + _next(ctx, ["config", "set", "model", str(config.get("model"))])
                                 + " (one or two model calls)")
            return ({"path": str(root / "config.yaml"), "saved": (root / "config.yaml").exists(),
                     "config": config, "tier": tier, "routes": routing(root)}, ["status"])
        if ctx.invoked_subcommand is None:
            _handle(ctx, operation, ["doctor"])

    @config_app.command("set", cls=V("co rem config set"))
    def change_config(ctx: typer.Context, values: List[str] = typer.Argument(...),
                      no_check: bool = typer.Option(False, "--no-check")):
        from ...rem.config import read_config, set_config
        from ...rem.files import RemError
        from ...rem.inquiry import STAGES, clear_route, routing, set_route
        from ...rem.tier import check_and_record

        def operation(root):
            if len(values) % 2:
                raise RemError("config set needs KEY VALUE pairs")
            pairs = list(zip(values[::2], values[1::2]))
            routes = [(key.split(".", 1)[1], value) for key, value in pairs if key.startswith("route.")]
            rest = [part for key, value in pairs if not key.startswith("route.") for part in (key, value)]
            for stage, _ in routes:
                if stage not in STAGES:
                    raise RemError(f"route.{stage}: the stages are {', '.join(STAGES)}")
            config = set_config(root, rest) if rest else read_config(root)
            for stage, model in routes:
                if model == "default":
                    clear_route(root, stage)
                else:
                    set_route(root, stage, config["runner"], model)
            value = {"config": config, "routes": routing(root)}
            # The tier is measured when the model changes, never read off its name (#1847).
            if {"model", "runner"} & set(values[::2]) and not no_check:
                if not ctx.obj["json"]:
                    rem_look.line(f"Checking {config['model']} on a fixture page (one or two model calls)...",
                               err=True)
                value["check"] = check_and_record(root, config)
            return value, ["config"]
        _handle(ctx, operation, ["config"])

    @rem.command("logs", cls=V("co rem logs"))
    def inspect_logs(ctx: typer.Context, run_id: str = typer.Argument(""),
                     usage: bool = typer.Option(False, "--usage"),
                     days: int = typer.Option(0, "--days", min=0),
                     old_run: str = typer.Option("", "--run")):
        from ...rem.service import run_logs, usage_report

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

    @rem.command("doctor", cls=V("co rem doctor"))
    def doctor(ctx: typer.Context):
        import shutil

        from ..._version import __version__
        from ...rem.config import read_config, validate
        from ...rem.files import RemError
        from ...rem.runner import co_command
        from ...rem.service import status, subscriptions

        def operation(root):
            checks, rem_fixes = [], []

            def check(name, ok, detail, fix="", rem_fix=None):
                """`rem_fix` is a co rem command, spelled for this root; `fix` is anything else."""
                if not ok and rem_fix:
                    fix = _next(ctx, rem_fix)
                    rem_fixes.append(rem_fix)
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
            except RemError as error:
                check("configuration", False, str(error), rem_fix=["config"])
            runner = (config or {}).get("runner", "codex")
            binary = {"codex": "codex", "claude-code": "claude"}.get(runner)
            if binary:
                # The same check init makes before its first run (#1943): on PATH, and Codex signed in.
                from ...rem.runner import ready
                problem, fix = ready({"runner": runner})
                check(f"model runner ({runner})", not problem, problem or shutil.which(binary) or binary, fix)
            import importlib.util
            # Optional (the `co rem` extra): without it an XLSX attachment is named,
            # not read, and nothing said so until a page came back without it.
            sheets = importlib.util.find_spec("openpyxl") is not None
            check("spreadsheet support (co rem extra)", sheets,
                  "openpyxl installed; XLSX attachments are read" if sheets
                  else "not installed; XLSX attachments are named, not read",
                  f"python -m pip install 'connectonion[rem]=={__version__}'")
            from ...rem.service import mailbox_state
            sources = subscriptions(root)
            for kind in ("gmail", "outlook"):
                # "connected" while the daily round read nothing from it (#1974):
                # connected, subscribed and approved are three different facts.
                state, fix = mailbox_state(kind, sources.get(kind, {}))
                if fix.startswith("co rem "):
                    check(f"mailbox {kind}", False, state, rem_fix=fix.split()[2:])
                else:
                    check(f"mailbox {kind}", not fix, state, fix)
            for name, sub in subscriptions(root).items():
                if sub.get("kind") in ("codex", "claude-code") and sub.get("enabled", True):
                    check(f"sessions {name}", Path(sub.get("root", "")).is_dir(), sub.get("root", ""),
                          rem_fix=["sources", "remove", name])
            if (root / "config.yaml").exists():
                slot = status(root).get("next_run")
                check("schedule", slot is not None, f"next run {slot}" if slot else "not installed",
                      rem_fix=["start"])
            if not ctx.obj["json"]:
                checks = [f"{'ok ' if row['ok'] else 'NO '} {row['check']}: {row['detail']}"
                          + ("" if row["ok"] else f" -> {row['fix']}") for row in checks]
            return checks, (rem_fixes[0] if rem_fixes else ["status"])
        _handle(ctx, operation, ["config"])

    # --------------------------------------------------------------- Advanced

    @rem.command("advanced", cls=V("co rem advanced"))
    def advanced(ctx: typer.Context):
        show("co rem advanced")

    @rem.command("scan", cls=V("co rem scan"))
    def scan_sources(ctx: typer.Context,
                     what: str = typer.Argument("people"),
                     days: int = typer.Option(150, "--days", min=1),
                     min_mails: int = typer.Option(3, "--min-mails"),
                     min_people: int = typer.Option(2, "--min-people"),
                     mine: List[str] = typer.Option([], "--mine")):
        from ...rem.files import RemError
        from ...rem.scan import scan_orgs, scan_people, scan_projects
        from ...rem.service import mail_client, subscriptions

        def run(root):
            if what == "projects":
                rows = scan_projects(subscriptions(root), days, root)
                return rows, (["stub", "project", rows[0]["name"], "--path", rows[0]["path"]]
                              if rows else ["sources"])
            if what not in ("people", "orgs"):
                raise RemError("scan takes people, orgs or projects")
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

    @rem.command("map-skills", cls=V("co rem map-skills"))
    def map_skill_pages(ctx: typer.Context, skills_dir: List[Path] = typer.Option([], "--skills-dir")):
        from ...rem.files import Notebook
        from ...rem.skill_map import map_skills
        _handle(ctx, lambda root: (map_skills(Notebook(root), skills_dir or None), ["list", "skills"]), ["status"])

    @rem.command("stub", cls=V("co rem stub"))
    def stub_page(ctx: typer.Context,
                  kind: str = typer.Argument(...),
                  name: str = typer.Argument(...),
                  handle: List[str] = typer.Option([], "--handle"),
                  path: List[str] = typer.Option([], "--path"),
                  domain: List[str] = typer.Option([], "--domain"),
                  person: List[str] = typer.Option([], "--person"),
                  email: str = typer.Option("", "--email")):
        import re
        from ...rem.files import Notebook, RemError

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
                raise RemError("stub takes person, org or project")
            return {"record": record, "created": made}, ["investigate", record, *sum((["--handle", h] for h in handle), [])]
        _handle(ctx, run, ["investigate"])

    @rem.command("reflect", cls=V("co rem reflect"))
    def reflect(ctx: typer.Context, subject: str, statement: str,
                author: str = typer.Option(..., "--author"),
                basis: str = typer.Option(..., "--basis"),
                previous: str = typer.Option("", "--previous"),
                applies: str = typer.Option("", "--applies"),
                kind: str = typer.Option("reflection", "--kind"),
                source: List[str] = typer.Option([], "--source"),
                supersedes: List[str] = typer.Option([], "--supersedes")):
        from ...rem.reflections import add
        _handle(ctx, lambda root: (add(root, subject, statement, author=author, basis=basis,
                 previous=previous, applies=applies, kind=kind, sources=source, supersedes=supersedes),
                 ["investigate", subject]), ["list"])

    @rem.command("reflections", cls=V("co rem reflections"))
    def reflection_records(ctx: typer.Context, subject: str = typer.Argument(""),
                           compact: bool = typer.Option(False, "--compact")):
        from ...rem.reflections import compress, records
        _handle(ctx, lambda root: (compress(root, subject) if compact else records(root, subject),
                                  ["list"]), ["list"])

    @rem.command("propose", cls=V("co rem propose"))
    def propose_review(ctx: typer.Context, kind: str, subject: str, question: str,
                       basis: str = typer.Option(..., "--basis"),
                       related: str = typer.Option("", "--related")):
        from ...rem.reviews import propose
        _handle(ctx, lambda root: (propose(root, kind, [subject, related] if related else [subject],
                                         question, basis), ["review"]), ["list"])

    @rem.command("review", cls=V("co rem review"))
    def review_candidates(ctx: typer.Context, review_id: str = typer.Argument(""),
                          verdict: str = typer.Option("", "--verdict"),
                          author: str = typer.Option("", "--author"),
                          response: str = typer.Option("", "--response"),
                          audio: Optional[Path] = typer.Option(None, "--audio"),
                          local_model: Optional[Path] = typer.Option(None, "--local-model")):
        from ...rem.reviews import decide, listing

        def operation(root):
            from ...rem.files import RemError
            text = response
            if audio:
                if not review_id or not local_model or response:
                    raise RemError("Audio response needs a review ID and --local-model; do not also pass --response")
                from ...rem.voice import transcribe
                text = transcribe(audio, local_model)
            return (decide(root, review_id, verdict, author=author, response=text)
                    if review_id else listing(root)), ["review"]
        _handle(ctx, operation, ["review"])

    @rem.command("abstract", cls=V("co rem abstract"))
    def abstract_pages(ctx: typer.Context):
        from ...rem.config import read_config
        from ...rem.files import Notebook
        from ...rem.runner import run_stage
        _handle(ctx, lambda root: (
            run_stage(Notebook(root), [], read_config(root), stage="abstract"), ["list", "decisions"]), ["status"])

    @rem.command("capture", cls=V("co rem capture"))
    def capture_session(ctx: typer.Context, transcript: Path, source: str = typer.Option(..., "--source")):
        from ...rem.capture import capture
        _handle(ctx, lambda root: (capture(root, transcript.expanduser().resolve(), source),
                                  ["sync", "--dry-run"]), ["status"])

    # ------------------- Project pages from the user's own messages (#1943)
    from .rem_projects import add_projects_app
    add_projects_app(rem, factory, _handle, _logged)

    # ------------------------------------------------ Old names (until 1.9.0)

    @rem.command("unfinished", help="Old name for `co rem investigate`; works until 1.9.0.")
    def list_unfinished(ctx: typer.Context, category: str = typer.Argument("")):
        _moved(ctx, "unfinished", ["investigate", *([category] if category and category != "all" else [])])
        from ...rem.files import Notebook
        def operation(root):
            pages = Notebook(root).unfinished("" if category == "all" else category)
            return pages, ["investigate", pages[0]["path"]] if pages else ["list"]
        _handle(ctx, operation, ["status"])

    @rem.command("people", help="Old name for `co rem list people --aliases`; works until 1.9.0.")
    def list_people(ctx: typer.Context):
        _moved(ctx, "people", ["list", "people", "--aliases"])
        from ...rem.files import Notebook
        _handle(ctx, lambda root: (Notebook(root).people(), ["list", "people"]), ["list", "people"])

    @rem.command("daily", help="Old name for `co rem sync`; works until 1.9.0.")
    def daily_round(ctx: typer.Context, days: int = typer.Option(30, "--days", min=1),
                    scheduled: bool = typer.Option(False, "--scheduled")):
        # Installed launchd jobs still call `daily --scheduled`; the notice goes
        # to their log, not to a person, so it is kept to one line.
        _moved(ctx, "daily", ["sync"])
        _sync(ctx, "", "", False, scheduled, False, days)

    @rem.command("subscriptions", help="Old name for `co rem sources`; works until 1.9.0.")
    def inspect_subscriptions(ctx: typer.Context):
        _moved(ctx, "subscriptions", ["sources"])
        from ...rem.service import subscriptions
        _handle(ctx, lambda root: (subscriptions(root), ["sources"]), ["config"])

    @rem.command("subscribe", help="Old name for `co rem sources add`; works until 1.9.0.")
    def subscribe(ctx: typer.Context, name: str = typer.Argument(...),
                  chat: List[str] = typer.Option([], "--chat"),
                  project: str = typer.Option("", "--project"),
                  about: str = typer.Option("", "--about"),
                  since: str = typer.Option("", "--since"),
                  only: bool = typer.Option(False, "--only"),
                  force: bool = typer.Option(False, "--force")):
        _moved(ctx, "subscribe", ["sources", "add", name])
        _add_source(ctx, name, chat, project, about, since, only, force)

    @rem.command("unsubscribe", help="Old name for `co rem sources remove`; works until 1.9.0.")
    def unsubscribe(ctx: typer.Context, name: str = typer.Argument(...),
                    chat: List[str] = typer.Option([], "--chat")):
        _moved(ctx, "unsubscribe", ["sources", "remove", name])
        _remove_source(ctx, name, chat)

    @rem.command("route", help="Old name for `co rem config set route.<stage>`; works until 1.9.0.")
    def route_stage(ctx: typer.Context, stage: str = typer.Argument(""),
                    runner: str = typer.Option("", "--runner"),
                    model: str = typer.Option("", "--model"),
                    clear: bool = typer.Option(False, "--clear")):
        _moved(ctx, "route", ["config", "set", f"route.{stage or '<stage>'}", model or "<model>"])
        from ...rem.inquiry import clear_route, routing, set_route
        def operation(root):
            from ...rem.files import RemError
            if clear and (runner or model):
                raise RemError("Do not combine --clear with --runner or --model")
            value = clear_route(root, stage) if clear else set_route(root, stage, runner, model) if stage else routing(root)
            return value, ["config"]
        _handle(ctx, operation, ["config"])

    @rem.command("usage", help="Old name for `co rem logs --usage`; works until 1.9.0.")
    def usage(ctx: typer.Context, days: int = typer.Option(0, "--days")):
        _moved(ctx, "usage", ["logs", "--usage"])
        from ...rem.service import usage_report
        _handle(ctx, lambda root: (usage_report(root, days or None), ["logs"]), ["logs"])

    order = ("init investigate open list show search start stop status sync sources config logs doctor "
             "advanced scan map-skills stub reflect reflections propose review abstract capture "
             "unfinished people daily subscriptions subscribe unsubscribe route usage").split()
    rem.registered_commands.sort(key=lambda command: order.index(command.name))
    return rem
