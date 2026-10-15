"""`co rem status` as a small dashboard (#1996).

Status printed every field it had: the schedule times twice, the launchd
plist, "Known attempts / Total attempts" three times, a whole run record --
and never the notebook itself. The owner has 154 skill pages; status did not
say so. Now it answers what someone opening it wants to know, one line each:
is it running, what is in the notebook and how much is written, what ran
today, which mailboxes are read (and the command that fixes one that is not),
what ran last. Everything else is behind --verbose. `--json` is untouched:
this module only draws the same result.
"""

from pathlib import Path

from .. import style
from . import rem_look
from .rem_look import highlight

CATEGORIES = (("people", "People"), ("projects", "Projects"), ("orgs", "Organisations"), ("skills", "Skills"),
              ("sessions", "AI sessions"))


def dashboard(root, value: dict, spell, *, verbose: bool = False) -> str:
    """The status result as markup (the plain text is the same markup read without its styles).

    `spell` turns arguments into the command as this user types it (`_next`).
    A notebook consolidates overnight, so after the title it says what happened
    today before what it holds (1.9.0a9); every value starts at one column.
    """
    from ...rem.census import pages
    from ...rem.migrate import program
    found = pages(Path(root))
    counts = notebook(root, found)
    lines = [*_header(value, program()), "", *_waiting(root, found), *_today(root, value), "",
             *_notebook(root, value, counts, spell), "",
             *_mailboxes(root), *_archive(value, spell), ""]
    lines += [*_budget(value, verbose), *_last_runs(root)]
    if verbose:
        from .rem_output import _lines
        lines += ["", style.label("Details"), *(highlight(line) for line in _lines(value, indent=2))]
    return "\n".join([*lines, ""])


def _waiting(root, found: dict) -> list[str]:
    """What needs the owner, first: the open threads waiting on them, counted as the reader's home counts them."""
    from ...rem.census import open_threads
    found = open_threads(Path(root), found)
    return [rem_look.section("Waiting on you", f"{_number(found['mine'])} of {_plural(found['open'], 'open thread')}"),
            ""]


def _budget(value: dict, verbose: bool) -> list[str]:
    """The week's investigation points and the Codex week, two lines; what a point is only with --verbose.

    "0 of 10 points" beside 3.0M tokens today read as a contradiction (#2008):
    points are percent of the Codex week, moved only by investigations. Codex
    reports whole percents, so a run under one is counted from its tokens
    (#1990). Five lines of it buried the last run (UI audit, 2026-10-15).
    """
    budget = value.get("investigation_quota")
    if not budget:
        return []
    from ...rem.quota import TOKENS_PER_POINT
    # "0% used on pro; resets Thu 22 Oct 17:24" is one line; a longer note goes under --verbose.
    parts = f"Codex week {value.get('codex_week') or 'unknown'}".split("; ")
    week = [" · ".join(parts)] if len(" · ".join(parts)) <= 80 - rem_look.COLUMN else parts
    lines = [rem_look.section("Budget", f"{_number(budget['spent_points'])} of {_number(budget['budget_points'])} "
                              "investigation points this week  "
                              + rem_look.meter(budget["spent_points"], budget["budget_points"])),
             rem_look.follow(highlight(week[0]), glyph="")]
    if verbose:
        lines += [*(rem_look.follow(highlight(part), glyph="") for part in week[1:]),
                  rem_look.follow(style.muted("a point is 1% of your Codex week, spent by investigations only"),
                                  glyph=""),
                  rem_look.follow(style.muted(f"a run under 1% counts fresh tokens, {TOKENS_PER_POINT:,} "
                                              "tokens a point"), glyph="")]
    return [*lines, ""]


def _last_runs(root) -> list[str]:
    """The last run that finished and how it ended; a run going now on one line under it.

    "Last run sync · running · 0 pages changed" read as a sync that changed
    nothing, while the one before it had finished and changed a page.
    """
    from ...rem.service import run_logs, seen_outcome
    zone, logs = _zone(root), run_logs(root)
    done = next((run for run in logs if seen_outcome(run) != "running"), None)
    lines = [rem_look.section("Last run", _last_run(done and {**done, "outcome": seen_outcome(done)}, zone))]
    running = [run for run in logs if seen_outcome(run) == "running"]
    if running:
        lines.append(rem_look.follow(style.muted(_running(running[0], zone)), glyph=""))
    return lines


def _running(run: dict, zone) -> str:
    from datetime import datetime
    what = " ".join(filter(None, [run.get("phase") or "sync", run.get("record")]))
    started = datetime.fromisoformat(run["started_at"]).astimezone(zone).strftime("%H:%M")
    return f"{what} running since {started}"


def status_next(value: dict) -> list:
    """What status ends on: the step its first line names, or the log once it runs by itself.

    It ended on `co rem logs` whatever it said, so a notebook that was never
    started read "run co rem start" and then "Next: co rem logs".
    """
    if not value.get("configured"):
        return ["init"]
    if str(value.get("state", "")).startswith("Background needs attention"):
        return ["logs"] if value.get("next_run") else ["start"]
    # The first thing under "To write next", when there is one (#2008): the
    # dashboard said `investigate me` there and then "Next: co rem logs".
    if value.get("root"):
        _, arguments = next_to_write(Path(value["root"]), notebook(value["root"]))
        if arguments:
            return arguments
    return ["logs"] if str(value.get("state", "")).startswith("Running") else ["start"]


def notebook(root, found: dict | None = None) -> dict:
    """Pages per category, mapped and written, counted the way the reader counts them (`rem.census`)."""
    from ...rem.census import counts
    return counts(Path(root), found)


def _zone(root):
    from ...rem.config import read_config
    from ...rem.service import notebook_zone
    return notebook_zone(read_config(root))


def _private_unwritten(root) -> int:
    """Mapped private projects require a named-page request, not a category write (#2079)."""
    from ...rem.files import Notebook
    from ...rem.merge import mapped_only
    from ...rem.project_pages import private
    book = Notebook(root)
    return sum(mapped_only(text := book.read(record)) and private(record, text)
               for record in book.list("projects"))


def next_to_write(root, counts: dict) -> tuple:
    """(what to write next, the arguments of the command that writes it), or ('', [])."""
    from ...rem.files import Notebook, read_json, state_path
    from ...rem.merge import mapped_only
    owner = (read_json(state_path(root, "map.json"), {}).get("owner") or {}).get("record")
    book = Notebook(root)
    if owner and book.path(owner).is_file() and mapped_only(book.read(owner)):
        return "your own page", ["investigate", "me"]
    if not any(row["mapped"] for row in counts.values()):
        return "nothing mapped yet", ["init"]
    for category, label in CATEGORIES:
        left = counts[category]["mapped"] > counts[category]["written"] and queued_unwritten(root, category)
        if left:
            return f"{left:,} {label.lower()} page{'s' if left != 1 else ''} not written", ["investigate", category]
    return "", []


def queued_unwritten(root, category: str) -> int:
    """Unwritten pages `co rem investigate CATEGORY` would write: its own queue's, so never one it leaves out.

    The census's mapped minus written said "1 organisations page not written
    → co rem investigate orgs" for the owner's own company, which that command
    never investigates and so did nothing; a private project is the same (#2079).
    """
    from ...rem.census import written
    from ...rem.files import Notebook
    from ...rem.queue import order
    book = Notebook(root)
    return sum(not written(book.read(row["path"])) for row in order(Path(root), category))


def _number(value) -> str:
    return style.count(f"{value:,}")


def _plural(number: int, word: str) -> str:
    return f"{_number(number)} {word}{'s' if number != 1 else ''}"


def _header(value: dict, program: str) -> list[str]:
    """The title and the state's short name on one line; what the state asks for under it, muted.

    "not scheduled here — the saved schedule belongs to another notebook or
    was removed; co rem start schedules this one · no run scheduled" was one
    line of 130 characters, wrapped in two by an 80-column terminal.
    """
    state = value["state"].replace("`", "")
    head, _, rest = state.partition(" — ")
    if not rest:
        head, _, rest = state.partition("; ")
    head = head[:1].lower() + head[1:]
    # A state that is not running already says nothing is scheduled.
    tail = " · no run scheduled" if not value.get("next_run") and head.startswith("running") else ""
    lines = [style.heading(f"{program} status") + " · " + highlight(head + tail)]
    return lines + ["  " + highlight(part.strip()) for part in rest.split("; ") if part.strip()]


def _notebook(root, value: dict, counts: dict, spell) -> list[str]:
    """Each category's pages, written of mapped, as a meter and two right-aligned counts."""
    where = str(value["root"]).replace(str(Path.home()), "~", 1)
    built = "  (not built yet)" if not value.get("configured") else ""
    lines = [rem_look.section("Notebook", style.path(where) + built)]
    rows = [(label, counts[category]) for category, label in CATEGORIES]
    wide = max(len(f"{row['mapped']:,}") for _, row in rows)
    for label, row in rows:
        done, total = row["written"], row["mapped"]
        share = f"{round(100 * done / total)}%" if total else "—"
        lines.append(rem_look.row(label, rem_look.meter(done, total) + "  "
                                  + _number(done).rjust(len(_number(done)) + wide - len(f"{done:,}"))
                                  + style.muted(" of ") + _number(total)
                                  + " " * (wide - len(f"{total:,}")) + "  " + style.muted(share.rjust(4))))
    lines.append(rem_look.follow(style.muted(f"{rem_look.WRITTEN} written  {rem_look.MAPPED} mapped, not written yet"),
                                 glyph=""))
    if private := _private_unwritten(root):
        lines.append(rem_look.row("Private projects", f"{private:,} unwritten; write only when you name the page"))
    what, arguments = next_to_write(root, counts)
    if what:
        lines.append(rem_look.row("To write next", what))
        lines.append(rem_look.follow(style.command(spell(arguments))))
    return lines


def _today(root, value: dict) -> list[str]:
    """What the notebook did today, first: pages changed and material read, then what it cost."""
    from ...rem.config import read_config
    from ...rem.service import notebook_zone, run_logs, runs_today
    _, recent = runs_today(run_logs(root), notebook_zone(read_config(root)))
    changed = len({page for record in recent for page in record.get("changed") or []})
    items = sum(record.get("items") or 0 for record in recent if isinstance(record.get("items"), int))
    runs = value.get("batches_today", 0)
    if not runs:
        return [rem_look.section("Today", style.muted(f"nothing ran yet ({value.get('date', '')})"))]
    usage = value.get("usage_today") or {}
    spent = ("tokens unknown" if usage.get("input_tokens") is None else
             f"{_compact(usage['input_tokens'])} tokens in · {_compact(usage.get('output_tokens') or 0)} out")
    missing = usage.get("runs_without_usage") or 0
    if missing and usage.get("input_tokens") is not None:
        spent += f" ({_plural(missing, 'run')} without usage)"
    return [rem_look.section("Today", f"{_plural(changed, 'page')} changed · {_plural(items, 'item')} read · "
                             f"{_plural(runs, 'run')}"),
            rem_look.follow(spent, glyph="")]


def _mailboxes(root) -> list[str]:
    """One line a mailbox: ✓ read, ✗ not, and the command that fixes it on the line under."""
    from ...rem.service import MAIL_KINDS, mailbox_state, subscriptions
    sources, lines = subscriptions(root), [style.label("Mailboxes")]
    for kind in MAIL_KINDS:
        state, fix = mailbox_state(kind, sources.get(kind, {}))
        mark = style.ok(rem_look.FINE) if state == "read by the daily round" else style.warn(rem_look.BROKEN)
        lines.append(rem_look.row(kind.title(), highlight(state), mark))
        if fix:
            lines.append(rem_look.follow(style.command(fix)))
    return lines


def _archive(value: dict, spell=lambda arguments: "co rem " + " ".join(arguments)) -> list[str]:
    """An unfinished init mail archive (#2035): ↻ and how far it got; nothing once it is complete."""
    archive = value.get("mail_archive")
    if not archive:
        return []
    if "on_disk" not in archive:   # a result from before the archive said its counts
        return [rem_look.row("Archive", highlight(archive["summary"]), style.muted(rem_look.RESUMES))]
    saved = f"{_number(archive['on_disk'])} of {_number(archive['target'])} mail bodies saved"
    if not archive.get("stalled"):
        return [rem_look.row("Archive", saved + style.muted(" · saving"), style.muted(rem_look.RESUMES))]
    since = str(archive.get("updated", ""))[:16].replace("T", " ")
    return [rem_look.row("Archive", saved + " · " + style.warn(f"stalled since {since}"), style.warn(rem_look.RESUMES)),
            rem_look.follow(style.muted("investigations ask the mail servers until it is done"), glyph=""),
            rem_look.follow(style.command(spell(["sync"])) + style.muted(" resumes it from the saved bodies"))]


def _last_run(run, zone) -> str:
    """What ran and how it ended, then when and what it changed on the line under (#2008: the notebook's zone)."""
    from datetime import datetime
    if not run:
        return style.muted("none yet")
    what = " ".join(filter(None, [run.get("phase") or "sync", run.get("record")]))
    outcome = str(run.get("outcome", "unknown")).replace("_", " ")
    started = datetime.fromisoformat(run["started_at"]).astimezone(zone).strftime("%Y-%m-%d %H:%M")
    detail = [highlight(started), _plural(len(run.get("changed") or []), "page") + " changed"]
    tokens = (run.get("usage") or {}).get("input_tokens")
    if tokens is not None:
        detail.append(f"{_compact(tokens)} tokens in")
    return highlight(what) + " · " + highlight(outcome) + "\n" + rem_look.follow(" · ".join(detail), glyph="")


def _compact(tokens) -> str:
    return style.count(rem_look.compact(tokens))
