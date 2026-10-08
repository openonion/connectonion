"""Experimental co rem inspection. No collection or provider startup on import."""

import json
import re
import shlex
from pathlib import Path
from typing import List, Optional

import typer

from ...rem.files import MAP_DAYS
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
    elif draw and not isinstance(value, str) and (drawn := draw(value)) is not None:
        # A drawing may decline a result of another shape (sync's dry run) by
        # returning None; a failed result it draws ends on its Next line too.
        from .rem_output import printable
        rem_look.say(printable(drawn), hanging=True)
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


def _logged(root, record, phase, call, quiet=False):
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
                .get(phase, f"Investigating {record}…"), quiet=quiet)

    # Where the time went, stage by stage: a one-day investigation took 8
    # minutes and the record could not say whether it was gathering, the
    # model or validation (#2002, #2016).
    open_stage = {"name": None, "at": None}

    def close_stage(at):
        if open_stage["name"]:
            seconds = run.setdefault("stage_seconds", {})
            seconds[open_stage["name"]] = round(seconds.get(open_stage["name"], 0)
                                                + (at - open_stage["at"]).total_seconds(), 1)

    def update(stage, processed=None, total=None, usage=None):
        moment = now()
        # "gathering codex sessions: 40 scanned" is one stage at a count, not a
        # stage of its own: keyed on the full text, a record had 47–51 (#2030).
        name = re.sub(r":\s*[\d,]+\b.*$", "", stage)
        if name != open_stage["name"]:
            close_stage(moment)
            open_stage.update(name=name, at=moment)
        run["stage"] = stage
        run["stage_updated_at"] = moment.isoformat()
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
                   instructions_chars=result.get("instructions_chars") or {},
                   evidence=result.get("evidence") or [], report=result.get("report") or "")
        _WRITTEN.append(record)
        # Said, not left to the record: an accepted page had no outcome line (#2044).
        if not quiet:
            rem_look.step(f"Updated {record}: accepted, {len(run['changed'])} page"
                          f"{'' if len(run['changed']) == 1 else 's'} changed")
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
        close_stage(now())
        open_stage["name"] = None
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


def _investigate_me(root, *, days, quick, handle=(), quiet=False):
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
        sent_only=True, stage_progress=update, quick=quick), quiet=quiet)
    return result, record


def _first_page_skipped(ctx, root, result, *, want, problem, fix, retry, init) -> str:
    """Why init does not go on to write the owner's page, in one line, or ''.

    The owner decided (#1943) that investigating "me" starts by itself, so a
    first run needs no second command to discover. It does not start when it
    cannot succeed (no runner, no address of yours), when it would pay twice (the
    page is already written), or when --no-investigate was explicitly requested.
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

    The same rules for the owner's page and the rest of the first run: an
    explicit map-only request, or a runner that cannot run.
    """
    if want is False:
        return "--no-investigate was given."
    if problem:
        return f"{problem}; fix it with {fix}."
    return ""


def _investigate_page(root, notebook, record, *, handle=(), days=None, eval_dir=(), progress=None,
                      quiet=False, retry_refused=False):
    """One page of `co rem investigate PAGE|CATEGORY`, and of the first run's organisations."""
    from ...rem import investigate as rem_investigate
    from ...rem.files import RemError, split_handles
    from ...rem.service import subscriptions
    if record.startswith("skills/"):
        if retry_refused:
            raise RemError("--retry-refused applies to people, projects and orgs pages")
        from ...rem.skill_runs import investigate_skill_page
        return _logged(root, record, "investigate", lambda update: investigate_skill_page(
            root, record, eval_dir or [Path.home() / ".co/evals"]), quiet=quiet)
    if eval_dir:
        raise RemError("--eval-dir applies only to skills pages")
    text = notebook.read(record)
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), record)
    known = []
    if record.startswith("people/"):
        person = next((p for p in notebook.people() if p["path"] == record), {})
        known += person.get("emails", []) + person.get("aliases", [])
    for line in text.splitlines():
        low = line.strip().lstrip("-").strip().casefold()
        if low.startswith(("also known as:", "email:", "handles:")) and ":" in line:
            known += split_handles(line.split(":", 1)[1])
    handles = list(dict.fromkeys([*handle, *known, title.split(" (")[0]]))
    clients = _mail_clients(root)
    if record.startswith("projects/"):
        # A project is read from where it lives: the sessions run in its
        # folders. Matching mail on its name pulled in every notification
        # and signature that mentioned it -- 3,500 mails scanned for one
        # project on a real mailbox, then a turn that timed out. Mail about
        # a project comes in through --handle, named on purpose.
        handles = list(dict.fromkeys([*handle, *rem_investigate.project_paths(text), title]))
        clients = {kind: client for kind, client in clients.items() if handle}
    skipped = "" if clients or not record.startswith("projects/") else \
        "not read for a project page; name its mail with --handle"
    return _logged(root, record, "investigate", lambda update: rem_investigate.investigate(
        root, record, title, handles, days=days or rem_investigate.window_since(text), clients=clients,
        subscriptions=subscriptions(root), progress=progress, mail_skipped=skipped,
        stage_progress=update, retry_refused=retry_refused), quiet=quiet)


# The first run investigates the owner and every eligible mapped page. The
# configured weekly budget is an advisory target here; explicit --first-*
# flags cap a kind for a trial.
FIRST_RUN_WORKERS = 16  # pages in parallel; mail fetches share MAIL_FETCH_SLOTS per mailbox


def _capped(rows: list, cap) -> list:
    return rows if cap is None else rows[:cap]


def _first_people_rows(root, cap, recent_days: int) -> list[dict]:
    """Eligible people in queue order, recent first; automated and own addresses excluded."""
    from ...rem.people_pages import queue
    return _capped(queue(root, recent_days=recent_days), cap)


def _first_project_rows(root, cap) -> list[dict]:
    """Unwritten messages, then mapped projects with readable local evidence."""
    from ...rem.files import Notebook
    from ...rem.investigate import project_file_inventory
    from ...rem.project_material import extract
    from ...rem.project_pages import queue
    from ...rem.queue import order
    from ...rem.service import subscriptions
    # The map summary was already shown. Keep missed session folders as
    # candidates instead of creating project pages during init.
    # A wider map can add older folders after the extraction cursor advanced.
    # Rebind the retained window to all mapped pages; message ids deduplicate it.
    extract(root, subscriptions(root), create_pages=False, full=True)
    rows = queue(root)
    selected = {row['record'] for row in rows}
    notebook = Notebook(root)
    for row in order(root, 'projects'):
        record = row['path']
        if record in selected or row['last_investigated']:
            continue
        page = notebook.read(record)
        if project_file_inventory(page):
            rows.append({'record': record, 'mode': 'full', 'recent': False,
                         'new_messages': 0, 'chars': len(page), 'left_out': 0})
    return _capped(rows, cap)


def _first_org_rows(root, cap) -> list[dict]:
    """Every pending mapped organization, most relevant first."""
    from ...rem.queue import order
    rows = [row for row in order(root, "orgs") if not row["recent"]]
    return _capped(rows, cap)


def _in_parallel(jobs, *, workers, gate, done):
    """Run `jobs` with up to `workers` at once; `gate()` says why not to start the next, or ''.

    A refused or failed page does not stop the others. `done(job, outcome)` is
    called in this thread as each one finishes. Returns (outcomes, stopped).
    """
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    from ...rem.files import RemError
    pending, running, outcomes, stopped = list(jobs), {}, [], ""
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        while pending or running:
            while pending and len(running) < workers and not stopped:
                stopped = gate()
                if not stopped:
                    job = pending.pop(0)
                    running[pool.submit(job["run"])] = job
            if not running:
                break
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                job, error = running.pop(future), future.exception()
                if error is not None and not isinstance(error, RemError):
                    raise error
                if error is not None:
                    from ...rem.runner import model_denial
                    if model_denial(error):
                        stopped = "The selected model denied access; sign in or choose an available model"
                outcome = {"page": job["record"], "mode": job["mode"], "outcome": "accepted"} if error is None else {
                    "page": job["record"], "mode": job["mode"], "why": str(error)[:300],
                    "outcome": "refused" if "rejected" in str(error) else "failed"}
                outcomes.append((job, outcome))
                done(job, outcome)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return outcomes, stopped


def _people_jobs(root, rows) -> list[dict]:
    from ...rem import people_pages
    from ...rem.service import subscriptions

    def job(row):
        investigate = lambda update: people_pages.investigate_person(  # noqa: E731
            root, row, clients=_mail_clients(root), subscriptions=subscriptions(root), stage_progress=update)
        return {"kind": "people", "record": row["record"], "mode": row["mode"], "row": row,
                "run": lambda: _logged(root, row["record"], "investigate", investigate, quiet=True)}
    return [job(row) for row in rows]


def _project_jobs(root, config, rows) -> list[dict]:
    from ...rem.files import Notebook
    from ...rem import project_pages

    def job(row):
        if row['mode'] == 'full':
            return {'kind': 'projects', 'record': row['record'], 'mode': 'full', 'row': row,
                    'run': lambda: _investigate_page(root, Notebook(root), row['record'], quiet=True)}
        write = lambda update: project_pages.write_page(root, row["record"], config=config)  # noqa: E731
        return {"kind": "projects", "record": row["record"], "mode": row["mode"], "row": row,
                "run": lambda: _logged(root, row["record"], "projects write", write, quiet=True)}
    return [job(row) for row in rows]


def _org_jobs(root, rows) -> list[dict]:
    from ...rem.files import Notebook

    def job(row):
        return {"kind": "orgs", "record": row["path"], "mode": "full", "row": row,
                "run": lambda: _investigate_page(root, Notebook(root), row["path"], quiet=True)}
    return [job(row) for row in rows]


def _owner_full_job(root, days) -> dict:
    """Your whole page, from everything you sent, after the quick pass wrote the first one."""
    from ...rem.files import read_json, state_path
    record = read_json(state_path(root, "map.json"), {})["owner"]["record"]
    return {"kind": "me", "record": record, "mode": "full",
            "run": lambda: _investigate_me(root, days=days, quick=False, quiet=True)}


KEYS = {"me": "owner_full", "people": "people_pages", "projects": "project_pages", "orgs": "org_pages",
        "skills": "skill_pages"}
LABELS = {"me": "Your full", "people": "People", "projects": "Project", "orgs": "Organisation", "skills": "Skill"}


def _first_pages(ctx, root, config, say, gate, *, people, projects, orgs, skills=(), me_days=None, owner_full=False) -> dict:
    """After your own page: your whole page, people, projects and organisations, FIRST_RUN_WORKERS at a time.

    One line per page as it finishes. Returns owner_full, people_pages,
    project_pages and org_pages, each in the shape its own command reports.
    """
    # The first pass reads only the mapped window, already on disk, so no page
    # waits on the provider; the rest of each person's two years is fetched
    # alongside, and people it found older mail for are deepened at the end.
    from ...rem.files import MAP_DAYS
    deep = [row for row in people if row.get("mode") == "full" and (row.get("days") or 0) > MAP_DAYS]
    # Attachments too: a fresh notebook asked the provider once per archived mail.
    first = [{**row, "days": MAP_DAYS, "attachments": False} if row in deep else row for row in people]
    backfill = _start_backfill(root, deep)
    if deep:
        say(f"Fetching up to two years of mail for {len(deep)} people in the background…")
    kinds = {"me": [_owner_full_job(root, me_days)] if owner_full else [],
             "people": _people_jobs(root, first), "projects": _project_jobs(root, config, projects),
             "orgs": _org_jobs(root, orgs), "skills": _skill_jobs(root, skills)}

    from itertools import zip_longest
    from .rem_output import FirstRunProgress
    jobs = [*kinds["me"], *(job for group in zip_longest(kinds["people"], kinds["projects"],
                                                        kinds["orgs"], kinds["skills"]) for job in group if job)]
    progress = FirstRunProgress({kind: len(rows) for kind, rows in kinds.items()}, quiet=ctx.obj["json"])
    if jobs:
        say(f"Investigating 0/{len(jobs)} pages with up to {FIRST_RUN_WORKERS} workers…")

    def done(job, outcome):
        why = f" ({outcome['why'][:120]})" if outcome["outcome"] != "accepted" else ""
        say(f"  {progress.finish(job['kind'])} {job['record']}: "
            f"{'written' if not why else 'not written' + why}")

    try:
        outcomes, stopped = _in_parallel(jobs, workers=FIRST_RUN_WORKERS, gate=gate, done=done)
    finally:
        progress.close()
    if stopped:
        if "model denied access" in stopped:
            fix = {"claude-code": "claude auth login", "codex": "codex login"}.get(config["runner"], "co auth status")
            say(f"Stopped before the rest: {stopped}. Run {fix}, then retry {_next(ctx, ['init'])}; "
                "completed pages are retained.")
        else:
            say(f"Stopped before the rest: {stopped}. Write them later with "
                f"{_next(ctx, ['investigate', 'all'])} and {_next(ctx, ['projects', 'write'])}.")
    result = {KEYS[kind]: _kind_result(kind, jobs, outcomes, stopped) for kind, jobs in kinds.items()}
    written = {outcome["page"] for job, outcome in outcomes if job["kind"] == "people" and outcome["outcome"] == "accepted"}
    result["people_deepened"] = _deepen(root, say, gate, deep, backfill, written, stopped)
    return result


def _start_backfill(root, rows) -> dict:
    """Each person's older mail, fetched into the archive in the background, four people at a time."""
    from concurrent.futures import ThreadPoolExecutor
    from ...rem.people_pages import backfill_person
    from ...rem.service import subscriptions
    if not rows:
        return {}
    pool = ThreadPoolExecutor(max_workers=4)
    futures = {row["record"]: pool.submit(backfill_person, root, row, clients=_mail_clients(root),
                                          subscriptions=subscriptions(root)) for row in rows}
    pool.shutdown(wait=False)
    return futures


def _deepen(root, say, gate, rows, backfill, written, stopped) -> dict:
    """A second pass on the people whose backfill found mail before the mapped window."""
    if not rows or stopped:
        return {"started": False}
    say("Waiting for the older mail to finish arriving…")
    older = {record: future.result() if future.exception() is None else 0 for record, future in backfill.items()}
    ready = [row for row in rows if row["record"] in written and older.get(row["record"])]
    if not ready:
        return {"started": False, "backfilled": sum(older.values())}
    say(f"Deepening {len(ready)} people with {sum(older[row['record']] for row in ready):,} older messages and attachments…")
    outcomes, halted = _in_parallel(_people_jobs(root, ready), workers=FIRST_RUN_WORKERS, gate=gate,
                                    done=lambda job, outcome: say(f"  deepened {job['record']}: {outcome['outcome']}"))
    return {"started": True, "backfilled": sum(older.values()), "pages": [outcome for _, outcome in outcomes],
            **({"stopped": halted} if halted else {})}


def _skill_jobs(root, rows) -> list[dict]:
    from ...rem.files import Notebook

    def job(row):
        return {"kind": "skills", "record": row["path"], "mode": "full", "row": row,
                "run": lambda: _investigate_page(root, Notebook(root), row["path"], quiet=True)}
    return [job(row) for row in rows]


def _first_abstract(root, config, say, result) -> dict:
    """Decisions, then principles, from the pages the first run just wrote.

    The owner (2026-10-08): the first run should also leave the settled
    questions and standing rules, not only people and projects. `co rem
    abstract` reads pages, never sources; one failure leaves the pages intact.
    """
    written = sum(page.get("outcome") == "accepted" for key in ("people_pages", "project_pages", "org_pages")
                  for page in (result.get(key) or {}).get("pages") or [])
    if not written:
        return {"started": False}
    from ...rem.files import Notebook
    from ...rem.runner import RunFailed, run_stage
    say("Drawing decisions and principles from the pages just written…")
    try:
        out = run_stage(Notebook(root), [], config, stage="abstract")
    except RunFailed as error:
        say(f"Decisions and principles were not written ({str(error)[:160]}); retry with co rem abstract.")
        return {"started": True, "outcome": "failed", "why": str(error), "usage": error.usage}
    pages = [page for page in out.get("changed", []) if page.startswith(("decisions/", "principles/"))]
    say(f"Decisions and principles: {len(pages)} page{'s' if len(pages) != 1 else ''} written.")
    return {"started": True, "outcome": "completed", "pages": pages, "usage": out.get("usage")}


def _kind_result(kind, jobs, outcomes, stopped) -> dict:
    """One kind's share of the first run, in the shape its own command reports."""
    pages = [outcome for job, outcome in outcomes if job["kind"] == kind]
    if not jobs:
        return {"started": False, "reason": ""}
    if not pages:
        return {"started": False, "reason": f"{LABELS[kind]} pages were not written: {stopped}."}
    return {"started": True, "category": kind, "pages": pages,
            "left": len(jobs) - sum(page["outcome"] == "accepted" for page in pages),
            **({"stopped": stopped} if stopped else {})}


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
    orgs = sum(page.get("outcome") == "accepted" for page in (result.get("org_pages") or {}).get("pages") or [])
    written += [f"{orgs} organisation page{'s' if orgs != 1 else ''}"] if orgs else []
    reviewed = sum(page.get("outcome") == "accepted" for page in (result.get("skill_pages") or {}).get("pages") or [])
    written += [f"{reviewed} skill page{'s' if reviewed != 1 else ''}"] if reviewed else []
    owner = (result.get("owner_page") or {}).get("path") or ""
    return "\n".join([
        "",
        f"Your notebook: {', '.join(counts)} and {names} skill{'s' if names != 1 else ''}.",
        "Written this run: " + (", ".join(written[:-1]) + " and " + written[-1] if len(written) > 1
                                else written[0] if written else "nothing yet") + ".",
        *([f"Your page: {owner}"] if owner else [])])


def _start_consent(ctx, summary, *, yes: bool) -> bool:
    """Use the same visible source and schedule approval in init and start."""
    import sys

    if ctx.obj["json"]:
        return yes
    message = render(summary, "start — source access and schedule")
    if yes:
        rem_look.say(rem_look.result(message), err=True, plain=message)
        return True
    if not sys.stdin.isatty():
        rem_look.say(rem_look.result(message), err=True, plain=message)
        rem_look.line("A noninteractive run cannot consent silently. Run with --yes after reading "
                      "the source and schedule summary, or use a terminal.", err=True)
        return False
    rem_look.say(rem_look.result(message), plain=message)
    return typer.confirm("Read these sources with this model and schedule?", default=False)


def _people_table(ctx, root, category, *, company, open_only, sort):
    """`co rem list people --table`: rows from the index (#2067), most recent contact first."""
    from ...rem.files import RemError
    from ...rem.store import db_path, people_table
    if category != "people":
        raise RemError("--table goes with people")
    if not db_path(root).is_file():
        return ("No people table yet: it is built at the end of a map or a sync. Run "
                + _next(ctx, ["sync"]) + " to build it."), ["sync"]
    rows = people_table(root, company=company, open_only=open_only, sort=sort,
                        descending=sort in ("last_contact", "first_contact", "mails", "open_threads"))
    return rows, (["show", rows[0]["record"]] if rows else ["list", "people"])


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
                  days: int = typer.Option(MAP_DAYS, "--days", min=1),
                  skills_dir: List[Path] = typer.Option([], "--skills-dir"),
                  mine: List[str] = typer.Option([], "--mine"),
                  mail: List[str] = typer.Option([], "--mail"),
                  name: str = typer.Option("", "--name"),
                  archive_mail: bool = typer.Option(True, "--archive-mail/--no-mail-archive"),
                  write_mine: Optional[bool] = typer.Option(None, "--investigate/--no-investigate"),
                  all_history: bool = typer.Option(False, "--all-history", help="Map every available mail year; archive only recent bodies"),
                  investigate_all: bool = typer.Option(False, "--investigate-all", help="Select every mapped person and project"),
                  estimate_only: bool = typer.Option(False, "--estimate-only", help="Map and estimate the selected work without model turns or body archive"),
                  start_background: bool = typer.Option(True, "--start/--no-start", help="Install nightly upkeep after the first run"),
                  yes: bool = typer.Option(False, "--yes", help="Approve the shown source access and background schedule"),
                  first_people: Optional[int] = typer.Option(None, "--first-people", min=0),
                  first_projects: Optional[int] = typer.Option(None, "--first-projects", min=0),
                  first_orgs: Optional[int] = typer.Option(None, "--first-orgs", min=0),
                  first_skills: Optional[int] = typer.Option(None, "--first-skills", min=0)):
        from ...rem.config import prepare, read_config
        from ...rem.files import Notebook, state_path
        from ...rem.map import build_map, owner_summary
        from ...rem import runner as rem_runner
        from ...rem.service import mail_available, mail_client, subscribe_read_mail, subscriptions
        from .rem_output import StageProgress
        all_history = all_history or investigate_all
        # One run confirms several addresses: `--mine a,b,c` as well as repeating it.
        owned = [part.strip() for value in mine for part in value.split(",") if part.strip()]
        run_state = {}

        def run(root):
            prepare(root)
            # Before the ten-minute map, not after it: a missing or signed-out
            # runner used to surface only when the first model turn failed.
            config = read_config(root)
            problem, fix = rem_runner.ready(config)
            window = [] if days == MAP_DAYS else ["--days", str(days)]
            init_window = [*window, *(["--all-history"] if all_history else [])]
            map_days = 36500 if all_history else days
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
            progress = StageProgress(log=state_path(root, "init-progress.log"), quiet=ctx.obj["json"], days=map_days)
            try:
                result = build_map(root, sources, clients, days=map_days, all_history=all_history,
                                   skill_directories=skills_dir or None, mine=owned, source_errors=errors,
                                   absent=_absent_mail(selected, available, failed, sources, bool(mail)), name=name,
                                   capture_sources=True, progress=progress)
                run_state["result"] = result
                if archive_mail and not estimate_only and result.get("source_inventory"):
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
                        body_report = archive_init(root, result, clients, progress=progress,
                                                   archive_days=MAP_DAYS if all_history else None)
                    result["mail_archive"] = body_report
                    write_json(state_path(root, "map.json"), result)
            finally:
                progress.close()
            unread = {row.get("source") for row in result.get("errors") or []}
            subscribe_read_mail(root, [kind for kind in clients if kind not in unread])
            tips = []
            unsaved = (result.get("mail_archive") or {}).get("failed")
            if unsaved:
                # A cache miss, not a mailbox problem: a real first run lost every
                # page to one body that timed out of 1,880 (2026-10-01).
                tips.append(f"{unsaved} mail bod{'y' if unsaved == 1 else 'ies'} could not be saved; the "
                            "rest of the first run goes on, and the next init retries "
                            f"{'it' if unsaved == 1 else 'them'}.")
            for kind, provider in (("gmail", "google"), ("outlook", "microsoft")):
                if kind not in available:
                    tips.append(f"Connect {provider.title()} for People: co auth {provider}; then run "
                                + _next(ctx, ["init", *init_window]) + ".")
            if result.get("needs_review"):
                tips.append(f"Held for review, not investigated or listed (no name, never replied): "
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
                    + _next(ctx, ["init", *init_window, "--mine", ",".join(row["address"] for row in shown)])
                    + " (leave out an assistant's or a relative's; nothing is merged without --mine)."]
            summary = owner_summary(Notebook(root), result) if result.get("owner") else None
            if summary:
                result["owner_page"] = summary
            if not selected:
                result["people_setup"] = "No connected mail source. Local maps are ready; connect mail to add People."
            if result.get("errors"):
                retry = ["init", *init_window]
                if mail:
                    retry += [part for kind in mail for part in ("--mail", kind)]
                result["recovery"] = ("Check mailbox access with co auth status; retry init after resolving access. "
                                      "Completed maps and saved mail bodies are reused.")
                if not estimate_only:
                    _emit(ctx, result, retry, failed=True)
                    raise typer.Exit(1)
            result["runner"] = {"runner": config["runner"], "model": config["model"], "ready": not problem,
                                **({"problem": problem, "fix": fix} if problem else {})}
            retry_me = ["investigate", "me", *window]
            reason = ("" if estimate_only else _first_page_skipped(
                ctx, root, result, want=write_mine, problem=problem, fix=fix,
                retry=retry_me, init=["init", *init_window]))
            if not ctx.obj["json"]:
                # The map's summary and your page's facts first: value before any spending.
                text = render(result, "init")
                typer.echo(err=True)   # the stage lines above are stderr; a gap, then the map
                rem_look.say(rem_look.result(text), plain=text, hanging=True)
                typer.echo()
            say = ((lambda text: None) if ctx.obj["json"] else
                   lambda text: rem_look.say(rem_look.highlight(text, counts=True), plain=text))
            plan = rem_runner.PLAN.get(config["runner"], "on the configured runner")
            from ...rem.files import RemError
            skipped = _spending_skipped(ctx, want=write_mine, problem=problem, fix=fix)
            if reason:
                result["investigate_me"] = {"started": False, "reason": reason}
                say(reason)
            if skipped and not estimate_only:
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
            people_rows = _first_people_rows(root, first_people, days)
            project_rows = _first_project_rows(root, first_projects) if first_projects != 0 else []
            org_rows = _first_org_rows(root, first_orgs)
            from ...rem.queue import order
            skill_rows = _capped([row for row in order(root, "skills") if not row["recent"]], first_skills)
            total = first_run.plan(run_logs(root), owner=not reason, people=len(people_rows),
                                   projects=len(project_rows), orgs=len(org_rows), skills=len(skill_rows),
                                   workers=FIRST_RUN_WORKERS)
            result["first_run"] = {**total, "people": [row["record"] for row in people_rows],
                                   "projects": [row["record"] for row in project_rows],
                                   "orgs": [row["path"] for row in org_rows],
                                   "skills": [row["path"] for row in skill_rows],
                                   "source_coverage": "incomplete" if result.get("errors") else "complete"}
            me_days = days if window else 30  # what `investigate me` reads without --days
            steps = ([f"your page (quick first, then full; {me_days} days of your mail and sessions)"]
                     if not reason else [])
            steps += ([f"{counted(len(people_rows), 'person', 'people')} "
                       + ("(every mapped person; current source window per page)" if investigate_all else
                          "(recent first; up to two years of evidence each)")]
                      if people_rows else [])
            steps += ([f"{counted(len(project_rows), 'project')}" +
                       (" (every mapped project)" if investigate_all else " (recent first)")]
                      if project_rows else [])
            steps += ([f"{counted(len(org_rows), 'related organisation')}"] if org_rows else [])
            steps += ([f"{counted(len(skill_rows), 'installed skill')} (source and retained run evidence)"] if skill_rows else [])
            if not steps:
                return (result if ctx.obj["json"] else _init_done(ctx, result)), ["open"]
            cost = (f"First run with {config['runner']} ({config['model']}): "
                    + ", ".join(steps) + f"; up to {FIRST_RUN_WORKERS} at a time.\n"
                    + "Estimate: " + first_run.announce(total, plan) + "\n"
                    + "Input estimate includes cached tokens; it is not weekly quota points.\n"
                    + "No REM page or weekly quota cap stops this first run; the selected queue "
                    "continues through failures. The model provider may still enforce its own limit.\n"
                    "Controls: --first-people, --first-projects, --first-orgs and --first-skills cap a kind; Ctrl-C "
                    "keeps the map and completed pages; --no-investigate skips model work.")
            rem_look.say(rem_look.highlight(cost, counts=True), err=ctx.obj["json"], plain=cost)
            if estimate_only:
                result["estimate_only"] = True
                state = ("Partial estimate: one or more sources failed; counts are a lower bound. "
                         if result.get("errors") else "Estimate only: ")
                say(state + "No model turn or mail body archive was started. The map and coverage are saved.")
                return ((result if ctx.obj["json"] else _init_done(ctx, result)),
                        ["init", *init_window], bool(result.get("errors")))
            if not problem:
                say("Checking access to the selected model before the page queue…")
                access_problem, access_fix = rem_runner.model_access(root, config)
                if access_problem:
                    from datetime import datetime, timezone
                    from uuid import uuid4
                    from ...rem.files import write_json
                    stamp = datetime.now(timezone.utc).isoformat()
                    write_json(state_path(root, f"runs/run_{uuid4().hex}.json"), {
                        "started_at": stamp, "finished_at": stamp, "phase": "model access",
                        "outcome": "failed", "error": access_problem[:300], "changed": [], "items": 0,
                        "model": config["model"], "sources": []})
                    result["model_access"] = {"ready": False, "problem": access_problem, "fix": access_fix}
                    say(f"Model access failed: {access_problem}. Run {access_fix}, then retry init; "
                        "the map and saved mail are retained.")
                    return (result if ctx.obj["json"] else _init_done(ctx, result)), ["init", *init_window], True
            gate = lambda: ""
            if not reason:
                try:
                    # Quick first, so your page is there in minutes; the whole page runs
                    # with the others (2026-10-01: the full pass alone was refused in two
                    # of seven real first runs and nearly empty in a third).
                    _investigate_me(root, days=days if window else None, quick=True)
                except KeyboardInterrupt:
                    result.update(investigation="interrupted",
                                  investigate_me={"started": True, "outcome": "interrupted"})
                    _interrupted(ctx, retry_me, result)
                except (RemError, rem_runner.RunFailed) as error:
                    # One page among the first run's: the others still go on (2026-10-01).
                    result.update(investigation="failed",
                                  investigate_me={"started": True, "outcome": "failed", "why": str(error)})
                    say(f"Your page was not written: {error} The rest of the first run goes on; "
                        f"retry your page with {_next(ctx, retry_me)}.")
                else:
                    record = summary["record"] if summary else result["owner"]["record"]
                    result.update(investigation="completed",
                                  investigate_me={"started": True, "outcome": "completed", "page": record})
                    say("Your page is written: " + str(Notebook(root).path(record)))
            try:
                result.update(_first_pages(ctx, root, config, say, gate, people=people_rows,
                                           projects=project_rows, orgs=org_rows, skills=skill_rows,
                                           me_days=days if window else None,
                                           owner_full=result.get("investigation") == "completed"))
            except KeyboardInterrupt:
                result.update({key: {"started": True, "outcome": "interrupted"} for key in KEYS.values()})
                _interrupted(ctx, ["investigate", "all"], result)
            for key in KEYS.values():
                if result[key].get("reason"):
                    say(result[key]["reason"])
            result["abstract"] = _first_abstract(root, config, say, result)
            if result.get("investigation") == "failed":
                return (result if ctx.obj["json"] else _init_done(ctx, result)), retry_me, True
            return (result if ctx.obj["json"] else _init_done(ctx, result)), ["open"]
        def run_and_start(root):
            response = run(root)
            value, next_step = response[:2]
            result = run_state.get("result", {})
            incomplete = any((result.get(key) or {}).get("left", 0) for key in KEYS.values())
            failed = bool(response[2]) if len(response) > 2 else False
            if incomplete and next_step == ["open"]:
                failed_page = next((page for key in KEYS.values()
                                    for page in (result.get(key) or {}).get("pages", [])
                                    if page.get("outcome") != "accepted"), None)
                next_step = (["investigate", failed_page["page"],
                              *(["--retry-refused"] if failed_page["outcome"] == "refused" else [])]
                             if failed_page else ["init"])
            if estimate_only:
                background = {"started": False, "reason": "Estimate only; no consent or schedule installed."}
            elif not start_background:
                background = {"started": False, "reason": "Background upkeep left off by --no-start."}
            elif failed or (write_mine is not False and
                            (incomplete or (result.get("runner") or {}).get("problem"))):
                background = {"started": False, "reason": "First run needs attention; finish its pages before enabling nightly upkeep."}
            else:
                from ...rem import schedule as rem_schedule
                from ...rem.files import RemError
                from ...rem.service import start
                try:
                    background = start(root, confirm=lambda summary: _start_consent(ctx, summary, yes=yes),
                                       scheduler=rem_schedule.default_scheduler(), run_first_batch=False)
                    if not background["started"]:
                        background["reason"] = ("Background upkeep needs approval. Run "
                                                + _next(ctx, ["start", "--yes"]) + " after reviewing its summary.")
                except RemError as error:
                    background = {"started": False, "reason": f"Background upkeep could not start: {error}"}
            if isinstance(value, dict):
                value["background"] = background
            else:
                detail = ("Background upkeep: scheduled." if background["started"] else
                          "Background upkeep: " + background["reason"])
                value += "\n" + detail
            return (value, next_step, failed or incomplete)

        _handle(ctx, run_and_start, ["sources"])

    @rem.command("investigate", cls=V("co rem investigate"))
    def investigate_page(ctx: typer.Context,
                         target: str = typer.Argument(""),
                         handle: List[str] = typer.Option([], "--handle"),
                         days: Optional[int] = typer.Option(None, "--days", min=1),
                         quick: bool = typer.Option(False, "--quick", help="Bounded first pass for your own page"),
                         limit: Optional[int] = typer.Option(None, "--limit", min=0),
                         workers: Optional[int] = typer.Option(None, "--workers", "-w", min=1, max=32,
                                                               help="Number of concurrent investigation workers (default: 10 for full runs, 1 with limit/budget)"),
                         budget: Optional[int] = typer.Option(None, "--budget", min=1, max=100),
                         list_only: bool = typer.Option(False, "--list"),
                         recent_days: Optional[int] = typer.Option(None, "--recent-days", min=1),
                         eval_dir: List[Path] = typer.Option([], "--eval-dir"),
                         retry_refused: bool = typer.Option(False, "--retry-refused")):
        from ...rem.files import Notebook, RemError, read_json, state_path
        from ...rem import queue as rem_queue
        from ...rem.queue import CATEGORIES, order
        pages_limit = limit if limit is not None else 0
        runnable = (*CATEGORIES, "all")
        from ...rem.runner import RunFailed
        from ...rem.service import subscriptions
        clients_for, progress = _mail_clients, _mail_progress
        effective_workers = workers if workers is not None else (1 if (limit or budget) else 10)

        def one(root, notebook, record):
            return _investigate_page(root, notebook, record, handle=handle, days=days, eval_dir=eval_dir,
                                     progress=progress, retry_refused=retry_refused)

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
            from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
            notebook, done, stopped = Notebook(root), [], ""
            gate = budget_gate(root)
            if chosen:
                rem_look.line(f"Investigating {len(chosen)} of {len(queue)} pending {category} pages "
                              f"with up to {min(effective_workers, len(chosen))} workers.", err=True)

            def investigate_one(record):
                try:
                    one(root, notebook, record)
                    return {"page": record, "outcome": "accepted"}
                except RunFailed as error:
                    return {"page": record, "outcome": "refused", "why": str(error)}
                except RemError as error:
                    from ...rem.investigate import NothingNew
                    outcome = "nothing_new" if isinstance(error, NothingNew) else "failed"
                    return {"page": record, "outcome": outcome, "why": str(error)}

            pending, running = iter(chosen), {}
            with ThreadPoolExecutor(max_workers=effective_workers) as pool:
                while True:
                    while len(running) < effective_workers and not stopped:
                        row = next(pending, None)
                        if row is None:
                            break
                        stopped = gate()
                        if not stopped:
                            running[pool.submit(investigate_one, row["path"])] = row
                    if not running:
                        break
                    finished, _ = wait(running, return_when=FIRST_COMPLETED)
                    for future in finished:
                        running.pop(future)
                        outcome = future.result()
                        done.append(outcome)
                        rem_look.line(f"[{len(done)}/{len(chosen)}] {outcome['page']}: {outcome['outcome']}", err=True)
            if stopped:
                rem_look.line(f"Stopped: {stopped}", err=True)
            skipped = [row["path"] for row in ranked() if row["recent"]]
            accepted = [row["page"] for row in done if row["outcome"] == "accepted"]
            failed = any(row["outcome"] not in ("accepted", "nothing_new") for row in done)
            return ({"category": category, "pages": done, "left": max(len(queue) - len(accepted), 0),
                     **({"show_accepted": _next(ctx, ["show", accepted[0]])} if accepted else {}),
                     **({"skipped_recent": skipped} if skipped else {}),
                     **({"stopped": stopped} if stopped else {})},
                    ["logs"] if failed else ["show", accepted[0]] if accepted else ["list", category], failed)

        def budget_gate(root):
            """Before each page: the weekly safety floor or an explicit --budget."""
            from ...rem import quota
            from ...rem.config import read_config
            from ...rem.service import now, run_logs
            config = read_config(root)
            start, began = quota.read(config), now().isoformat()

            def gate():
                meter, logs = quota.read(config), run_logs(root)
                stop = quota.blocks(meter, quota.points_spent(logs, meter), config["limits"])
                if stop or not budget or "unknown" in meter or "unknown" in start:
                    return stop
                used = quota.run_spent(start, meter, logs, began)
                return f"this run has used {used} of its {budget}-point budget" if used >= budget else ""
            return gate

        def me(root):
            result, record = _investigate_me(root, days=days, quick=quick, handle=handle)
            return result, ["show", record]

        def run(root):
            if quick and target != "me":
                raise RemError("--quick is for `co rem investigate me` only")
            if retry_refused and (not target or target in runnable or target == "me"):
                raise RemError("--retry-refused needs one page: co rem investigate PAGE --retry-refused")
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
                                  clients_for=clients_for, subscriptions=subscriptions, logged=_logged,
                                  workers=effective_workers)
            if target == "me":
                return me(root)
            if target in runnable:
                return by_category(root, target)
            notebook = Notebook(root)
            record = _resolve_page(notebook, target)
            from ...rem.investigate import NothingNew
            try:
                result = one(root, notebook, record)
            except NothingNew as quiet:
                # Nothing new is a finished run, not a failure: it read every
                # source and made no model call. It printed "Error:", exited 1
                # and told the user to run the same command again (#2034).
                return str(quiet), ["show", record]
            return result, ["show", result["report"] if record.startswith("skills/") else record]
        retry = ["investigate", *([target] if target else []),
                 *(["--days", str(days)] if days is not None else []),
                 *(["--quick"] if quick else []),
                 *(["--retry-refused"] if retry_refused else [])]
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
                     review: bool = typer.Option(False, "--review"),
                     table: bool = typer.Option(False, "--table", help="People as a table: company, role, email, "
                                                "phone, last contact, mails, what is open"),
                     company: str = typer.Option("", "--company", help="With --table: only this company"),
                     open_only: bool = typer.Option(False, "--open", help="With --table: only people with "
                                                    "something open"),
                     sort: str = typer.Option("last_contact", "--sort", help="With --table: name, company, role, "
                                              "last_contact, mails or open_threads")):
        from ...rem.files import CATEGORIES, Notebook, RemError
        from ...rem.map import needs_review

        def operation(root):
            if table:
                return _people_table(ctx, root, category, company=company, open_only=open_only, sort=sort)
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
        from .rem_table import draw
        order = "most recent contact first" if sort == "last_contact" else "by " + sort.replace("_", " ")
        _handle(ctx, operation, ["list"], draw=lambda rows: draw(rows, order) if table else None)

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

    @rem.command("merge", cls=V("co rem merge"))
    def merge_pages(ctx: typer.Context, kept: str, old: str,
                    reason: str = typer.Option("manual merge", "--reason", "-r")):
        from ...rem.files import Notebook, RemError, maintenance_lock
        from ...rem.merge import merge_into, resolve

        def operation(root):
            with maintenance_lock(root):
                notebook = Notebook(root)
                target_kept, target_old = resolve(root, kept), resolve(root, old)
                if target_kept == target_old:
                    raise RemError("Choose two different pages to merge")
                for page in (target_kept, target_old):
                    if not notebook.exists(page):
                        raise RemError(f"Record not found: {page}; list the notebook for current record paths")
                result = merge_into(notebook, target_kept, target_old, reason)
                return {**result, "archived": f".state/archived/{target_old}"}, ["show", target_kept]

        _handle(ctx, operation, ["list"])

    # -------------------------------------------------------- Keep it current

    @rem.command("start", cls=V("co rem start"))
    def start_rem(ctx: typer.Context, yes: bool = typer.Option(False, "--yes")):
        from ...rem import schedule as rem_schedule
        from ...rem.files import RemError
        from ...rem.service import start

        def confirm(summary):
            return _start_consent(ctx, summary, yes=yes)

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
                                      scheduled=scheduled, all_pending=all_pending, on_batch=progress,
                                      say=lambda text: rem_look.step(text))
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
            result = run_daily(root, days=days, scheduled=scheduled,
                               say=lambda text: rem_look.step(text))
            if result is None:
                return {"due": False, "ran": False}, ["status"]
            if result["outcome"] == "partial":
                _emit(ctx, result, ["logs"], failed=True, draw=draw)
            return result, ["logs"]
        from .rem_output import sync_summary

        def draw(value):
            # The page lines above are stderr; a gap, then the summary.
            typer.echo(err=True)
            return sync_summary(value, lambda arguments: _next(ctx, arguments))
        _handle(ctx, operation, ["logs"], draw=draw)

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
            from ...rem.mail_archive import archive_state
            from ...rem.service import now as service_now
            archive = archive_state(root, now=service_now())
            if archive:
                # A stalled archive sent every investigation to the mail servers for a day (#2035).
                check("init mail archive", not archive["stalled"], archive["summary"], rem_fix=["sync"])
            for name, sub in subscriptions(root).items():
                if sub.get("kind") in ("codex", "claude-code") and sub.get("enabled", True):
                    check(f"sessions {name}", Path(sub.get("root", "")).is_dir(), sub.get("root", ""),
                          rem_fix=["sources", "remove", name])
            if (root / "config.yaml").exists():
                schedule = status(root)
                slot = schedule.get("next_run")
                attention = str(schedule["state"]).startswith("Background needs attention")
                check("schedule", slot is not None and not attention,
                      schedule["state"] if attention else f"next run {slot}" if slot else "not installed",
                      rem_fix=["logs"] if attention and slot else ["start"])
            return checks, (rem_fixes[0] if rem_fixes else ["status"])
        from .rem_output import doctor_board
        _handle(ctx, operation, ["config"], draw=doctor_board)

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
             "advanced scan map-skills stub merge reflect reflections propose review abstract capture "
             "unfinished people daily subscriptions subscribe unsubscribe route usage").split()
    rem.registered_commands.sort(key=lambda command: order.index(command.name))
    return rem
