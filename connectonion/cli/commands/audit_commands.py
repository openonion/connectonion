"""
Purpose: `co audit` — check that every co command's help is something an agent can act on (#1735)
LLM-Note:
  Dependencies: imports from [cli/audit.py, core/usage.py, rich] | imported by [cli/main.py]
  Data flow: words → a command prefix → audit.audit() hard rules → print findings | --review → audit.review() on pages that passed | --inventory / --since → fingerprints to audit only what changed
  State/Effects: read-only; --review calls a model; --inventory writes JSON to stdout only
  Errors: exit 1 when any rule or review fails, each finding with its fix
"""

import json
from pathlib import Path

import typer
from rich.console import Console

from .. import audit
from ...core.usage import DEFAULT_MODEL

console = Console(soft_wrap=True)


def handle_audit(words: list, review: bool, since: Path, inventory: bool, as_json: bool, model: str) -> None:
    from ..main import app

    if inventory:
        print(json.dumps(audit.inventory(app), indent=1, sort_keys=True))
        return
    prefix = " ".join(["co", *words])
    paths = audit.commands(app, prefix)
    if not paths:
        console.print(f"[red]✗[/red] No command {prefix!r}.")
        console.print("Next: co commands")
        raise typer.Exit(1)
    if since is not None:
        changed = set(audit.changed_since(app, json.loads(since.read_text())))
        paths = [path for path in paths if path in changed]
    findings = [f for path in paths for f in audit.check_page(app, path)]
    if review:
        failing = {f.path for f in findings}
        findings += [f for path in paths if path not in failing
                     for f in [audit.review(app, path, model)] if f]
    if as_json:
        print(json.dumps({"checked": paths, "findings": [
            {"command": f.path, "check": f.check, "fix": f.fix} for f in findings]}, indent=1))
    else:
        for f in findings:
            console.print(f"[red]✗[/red] {f.path}  [bold]{f.check}[/bold]: {f.fix}")
        layers = "hard rules and a model review" if review else "hard rules"
        mark = "[red]✗[/red]" if findings else "[green]✓[/green]"
        console.print(f"{mark} {len(paths)} commands checked against {layers}: {len(findings)} problems.")
        if findings:
            console.print(f"Next: fix the pages above, then co audit {' '.join(words)}".rstrip())
        elif not review:
            console.print(f"Next: co audit {' '.join(words)} --review".replace("  ", " "))
    if findings:
        raise typer.Exit(1)
