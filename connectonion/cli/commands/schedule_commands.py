"""
Purpose: `co schedule` — see, check, run now, pause and resume the recurring work in this project's .co/schedule.yaml
LLM-Note:
  Dependencies: imports from [network/host/schedule.py, project.py, rich] | imported by [cli/main.py]
  Data flow: project_co_dir() → load_entries(report=True) + load_state() → print | run/pause/resume → schedule.set_flag() into .co/schedule-state.json
  State/Effects: list/check read only | run/pause/resume write schedule-state.json, which the running Host reads on its next tick (at most a minute) | never writes schedule.yaml, which is deployed and would be overwritten
  Integration: the Host's scheduler honours `paused` and `run_requested`; the Home page reads the same file, so the CLI and the page cannot disagree
  Errors: every refusal exits 1 and names the next command to run
"""

import json
from datetime import datetime, timezone

import typer
from rich.console import Console

from ...network.host import schedule
from ...project import project_co_dir

# soft_wrap: a path or a command must stay on one line to be copyable.
console = Console(soft_wrap=True)

EXAMPLE = '''  - name: morning report
    at: "Mon 09:00"
    tz: Australia/Sydney
    run: "Summarise yesterday's orders and email the team"'''


def _refuse(message: str, next_step: str) -> None:
    console.print(f"[red]✗[/red] {message}")
    console.print(f"Next: {next_step}")
    raise typer.Exit(1)


def _entries():
    """The entries as the scheduler reads them, or an exit that says how to add one."""
    co_dir = project_co_dir()
    path = co_dir / schedule.SCHEDULE_FILE
    if not path.is_file():
        console.print(f"[red]✗[/red] No schedule: {path} does not exist.")
        console.print(f"Create it with an entry like:\n{EXAMPLE}")
        console.print("Next: co schedule check")
        raise typer.Exit(1)
    entries, problems = schedule.load_entries(co_dir, report=True)
    return co_dir, entries, problems


def _named(name: str):
    co_dir, entries, _ = _entries()
    if name not in {entry.name for entry in entries}:
        known = ", ".join(repr(entry.name) for entry in entries) or "none"
        _refuse(f"No entry named {name!r}. Entries: {known}.", "co schedule list")
    return co_dir


def _when(moment, now) -> str:
    if moment is None:
        return "-"
    if moment <= now:
        return "next tick"
    return moment.astimezone().strftime("%a %d %b %H:%M")


def handle_list(as_json: bool) -> None:
    co_dir, entries, problems = _entries()
    state = schedule.load_state(co_dir)
    now = datetime.now(timezone.utc)
    rows = []
    for entry in entries:
        st = state.get(entry.name) or {}
        rows.append({
            "name": entry.name,
            "does": "exec" if entry.exec else "run",
            "what": entry.exec or entry.run,
            "when": schedule.cadence(entry) + (f" {entry.tz or 'UTC'}" if entry.at else ""),
            "paused": bool(st.get("paused")),
            "next_run": None if (moment := schedule.next_run(entry, state, now)) is None else moment.isoformat(),
            "last_run": st.get("last_run"),
            "status": st.get("status"),
            "reason": st.get("reason"),
            "session_id": st.get("session_id"),
        })
    if as_json:
        print(json.dumps({"entries": rows, "problems": problems}, indent=2))
        return
    if not rows:
        console.print("No valid entries.")
    for row in rows:
        state_word = "paused" if row["paused"] else (row["status"] or "not yet run")
        console.print(f"[bold]{row['name']}[/bold]  {row['when']}  · {state_word}")
        next_moment = datetime.fromisoformat(row["next_run"]) if row["next_run"] else None
        console.print(f"  next: {_when(next_moment, now)}   last: {row['last_run'] or '-'}")
        if row["reason"]:
            console.print(f"  reason: {row['reason']}")
        if row["session_id"]:
            console.print(f"  session: {row['session_id']}")
    for problem in problems:
        console.print(f"[yellow]ignored:[/yellow] {problem}")


def handle_check() -> None:
    co_dir, entries, problems = _entries()
    for problem in problems:
        console.print(f"[red]✗[/red] {problem}")
    if problems:
        console.print(f"{len(entries)} valid, {len(problems)} ignored by the scheduler.")
        console.print(f"Fix {co_dir / schedule.SCHEDULE_FILE}, then run: co schedule check")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] {len(entries)} entries, all valid.")


def handle_run(name: str) -> None:
    co_dir = _named(name)
    schedule.set_flag(co_dir, name, "run_requested", True)
    console.print(f"[green]✓[/green] {name} will run on the agent's next tick (within a minute), "
                  "or when the agent next starts.")


def handle_pause(name: str) -> None:
    co_dir = _named(name)
    schedule.set_flag(co_dir, name, "paused", True)
    console.print(f"[green]✓[/green] {name} is paused. schedule.yaml is unchanged.")
    console.print(f"Next: co schedule resume {name!r}")


def handle_resume(name: str) -> None:
    co_dir = _named(name)
    schedule.set_flag(co_dir, name, "paused", False)
    console.print(f"[green]✓[/green] {name} is back on its schedule.")
