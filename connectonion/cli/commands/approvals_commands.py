"""
Purpose: `co approvals` — read the record of what this agent did or declined, for whom
LLM-Note:
  Dependencies: imports from [json, rich.console, approvals.py, project.py] | imported by [cli/main.py] | tested by [tests/unit/test_the_record.py]
  Data flow: handle_approvals(who, klass, last, json_output) → approvals.read(project .co/) → one line per entry, or JSON
  State/Effects: read-only
"""

import json

from rich.console import Console
from rich.markup import escape

from ... import approvals
from ...environment import global_config_dir
from ...project import project_co_dir

console = Console()


def record_dir():
    """This project's record, or co ai's in ~/.co when the project keeps none."""
    project = project_co_dir()
    if (project / approvals.RECORD).exists():
        return project
    home = global_config_dir()
    return home if (home / approvals.RECORD).exists() else project


def handle_approvals(who: str = None, klass: str = None, last: int = 50, json_output: bool = False) -> None:
    co_dir = record_dir()
    entries = approvals.read(co_dir, who=who, klass=klass, last=last)
    if json_output:
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return
    if not entries:
        where = co_dir / approvals.RECORD
        console.print(f"[dim]Nothing recorded{' for ' + who if who else ''} in {where}.[/dim]")
        return
    console.print(f"[dim]{co_dir / approvals.RECORD}[/dim]")
    for entry in entries:
        console.print(_line(entry))


def _line(entry: dict) -> str:
    mark = "[green]✓[/green]" if entry.get("decision") == "done" else "[red]✗[/red]"
    what = escape(f"{entry.get('tool') or ''} {entry.get('args') or ''}".strip())
    klass = f" [yellow]{entry['class']}[/yellow]" if entry.get("class") else ""
    reason = f"  [dim]{escape(str(entry['reason']))}[/dim]" if entry.get("reason") else ""
    return f"{mark} [dim]{entry.get('ts', '')}[/dim] {entry.get('path', '')} {escape(entry.get('who') or entry.get('subject') or '')}{klass}  {what}{reason}"
