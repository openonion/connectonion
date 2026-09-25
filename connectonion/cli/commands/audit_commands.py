"""
Purpose: `co audit` — run co, read its help pages, and report what an agent could not act on (#1735)
LLM-Note:
  Dependencies: imports from [cli/audit.py, rich] | imported by [cli/main.py]
  Data flow: words → a command prefix → audit.audit() walks and checks printed pages → print findings | --review → audit.review() on pages that passed | --inventory / --since → fingerprints to audit only what changed
  State/Effects: read-only; runs `co ... --help` in empty temporary directories; --review calls a model
  Errors: exit 1 when any rule or review fails, each finding with its fix
"""

import json
from pathlib import Path

import typer
from rich.console import Console

from .. import audit

console = Console(soft_wrap=True)


def handle_audit(words: list, review: bool, since: Path, inventory: bool, as_json: bool, model: str) -> None:
    prefix = " ".join(["co", *words])
    findings, checked = audit.audit(prefix)
    if inventory:
        print(json.dumps(audit.inventory(checked), indent=1, sort_keys=True))
        return
    if not checked:
        console.print(f"[red]✗[/red] No page reachable from co --help is {prefix!r}.")
        console.print("Next: co commands")
        raise typer.Exit(1)
    if since is not None:
        before = json.loads(since.read_text())
        changed = {path for path, digest in audit.inventory(checked).items() if before.get(path) != digest}
        checked = {path: page for path, page in checked.items() if path in changed}
        findings = [f for f in findings if f.path in changed]
    if review:
        failing = {f.path for f in findings}
        findings += [f for path, (_, text, _) in checked.items() if path not in failing
                     for f in [audit.review(path, text, model)] if f]
    if as_json:
        print(json.dumps({"checked": sorted(checked), "findings": [
            {"command": f.path, "check": f.check, "fix": f.fix} for f in findings]}, indent=1))
    else:
        for f in findings:
            console.print(f"[red]✗[/red] {f.path}  [bold]{f.check}[/bold]: {f.fix}")
        layers = "hard rules and a model review" if review else "hard rules"
        mark = "[red]✗[/red]" if findings else "[green]✓[/green]"
        console.print(f"{mark} {len(checked)} pages checked against {layers}: {len(findings)} problems.")
        again = " ".join(["co audit", *words])
        console.print(f"Next: fix the pages above, then {again}" if findings
                      else "" if review else f"Next: {again} --review")
    if findings:
        raise typer.Exit(1)
