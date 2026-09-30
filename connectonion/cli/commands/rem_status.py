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
from .rem_look import highlight

CATEGORIES = (("people", "People"), ("projects", "Projects"), ("orgs", "Organizations"), ("skills", "Skills"))


def dashboard(root, value: dict, spell, *, verbose: bool = False) -> str:
    """The status result as markup (the plain text is the same markup read without its styles).

    `spell` turns arguments into the command as this user types it (`_next`).
    """
    from ...rem.migrate import program
    counts = notebook(root)
    lines = [_header(value, program()), "", *_notebook(root, value, counts, spell), "",
             *_today(root, value), "", *_mailboxes(root), ""]
    budget = value.get("investigation_quota")
    if budget:
        lines.append(f"{style.heading('Budget')}     {_number(budget['spent_points'])} of "
                     f"{_number(budget['budget_points'])} investigation points this week · "
                     f"Codex week {highlight(value.get('codex_week', 'unknown'))}")
    lines.append(f"{style.heading('Last run')}   {_last_run(value.get('last_run'))}")
    if verbose:
        from .rem_output import _lines
        lines += ["", style.heading("Details"), *(highlight(line) for line in _lines(value, indent=2))]
    return "\n".join(lines)


def notebook(root) -> dict:
    """Pages per category: mapped (every page) and written (filled by a model or by hand since the map)."""
    from ...rem.files import Notebook
    from ...rem.merge import mapped_only
    book, counts = Notebook(root), {}
    for category, _ in CATEGORIES:
        records = [record for record in book.list(category) if category != "skills"
                   or record.startswith("skills/catalog/") and record != "skills/catalog/index.md"]
        counts[category] = {"mapped": len(records),
                            "written": sum(not mapped_only(book.read(record)) for record in records)}
    return counts


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
        left = counts[category]["mapped"] - counts[category]["written"]
        if left:
            return f"{left:,} {label.lower()} page{'s' if left != 1 else ''} not written", ["investigate", category]
    return "", []


def _number(value) -> str:
    return style.count(f"{value:,}")


def _plural(number: int, word: str) -> str:
    return f"{_number(number)} {word}{'s' if number != 1 else ''}"


def _header(value: dict, program: str) -> str:
    state = value["state"].replace("`", "")
    state = state[:1].lower() + state[1:]
    tail = "" if value.get("next_run") else " · no run scheduled"
    return style.heading(f"{program} status") + " · " + highlight(state + tail)


def _notebook(root, value: dict, counts: dict, spell) -> list[str]:
    where = str(value["root"]).replace(str(Path.home()), "~", 1)
    built = "" if value.get("configured") else " (not built yet)"
    lines = [f"{style.heading('Notebook')}  {style.path(where)}{built}"]
    for category, label in CATEGORIES:
        row = counts[category]
        lines.append(f"  {label:<14} {_number(row['written'])} written of {_number(row['mapped'])} mapped")
    what, arguments = next_to_write(root, counts)
    if what:
        lines.append(f"  {'To write next':<14} {what}: {style.command(spell(arguments))}")
    return lines


def _today(root, value: dict) -> list[str]:
    from ...rem.config import read_config
    from ...rem.service import notebook_zone, run_logs, runs_today
    _, recent = runs_today(run_logs(root), notebook_zone(read_config(root)))
    changed = len({page for record in recent for page in record.get("changed") or []})
    usage = value.get("usage_today") or {}
    spent = ("tokens unknown" if usage.get("input_tokens") is None else
             f"{_number(usage['input_tokens'])} tokens in, {_number(usage.get('output_tokens') or 0)} out")
    return [f"{style.heading('Today')}  {value.get('date', '')}",
            f"  {_plural(value.get('batches_today', 0), 'run')} · {_plural(changed, 'page')} changed · {spent}"]


def _mailboxes(root) -> list[str]:
    from ...rem.service import MAIL_KINDS, mailbox_state, subscriptions
    sources, lines = subscriptions(root), [style.heading("Mailboxes")]
    for kind in MAIL_KINDS:
        state, fix = mailbox_state(kind, sources.get(kind, {}))
        mark = style.ok("✓") if state == "read by the daily round" else style.warn("✗")
        lines.append(f"  {mark} {kind.title():<8} {highlight(state)}" + (f" — {style.command(fix)}" if fix else ""))
    return lines


def _last_run(run) -> str:
    if not run:
        return "none yet"
    what = " ".join(filter(None, [run.get("phase") or "sync", run.get("record")]))
    parts = [highlight(part) for part in (run["started_at"][:16].replace("T", " "), what,
                                          str(run.get("outcome", "unknown")).replace("_", " "))]
    parts.append(_plural(len(run.get("changed") or []), "page") + " changed")
    tokens = (run.get("usage") or {}).get("input_tokens")
    if tokens is not None:
        parts.append(f"{_number(tokens)} tokens in")
    return " · ".join(parts)
