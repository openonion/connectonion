"""
Purpose: `co audit <command>` — is this CLI, ours or any other, fit for an agent harness? (#1735)
LLM-Note:
  Dependencies: imports from [cli/audit.py, rich, shutil] | imported by [cli/main.py]
  Data flow: the command as typed (co gmail, yt-dlp) → audit.audit() walks and checks printed pages → score table, findings, verdict | --review → audit.review() on pages that passed | --inventory / --since → fingerprints to audit only what changed
  State/Effects: read-only; runs `<command> --help` in empty temporary directories; --review calls a model
  Errors: exit 1 when any rule or review fails, each finding with its fix; exit 1 when the program is not on PATH
"""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import typer
from rich.console import Console

from .. import audit

console = Console(soft_wrap=True)


def handle_audit(words: list, review: bool, since: Path, inventory: bool, as_json: bool, model: str) -> None:
    target = list(words)
    if not shutil.which(target[0]) and target[0] != "co":
        console.print(f"[red]✗[/red] No program {target[0]!r} on PATH. Audit the command as you would type it.")
        console.print("Next: co audit co")
        raise typer.Exit(1)
    findings, checked = audit.audit(target)
    if inventory:
        print(json.dumps(audit.inventory(checked), indent=1, sort_keys=True))
        return
    if not checked:
        console.print(f"[red]✗[/red] No page reachable from {target[0]} --help is {' '.join(target)!r}.")
        console.print(f"Next: co audit {target[0]}")
        raise typer.Exit(1)
    if since is not None:
        before = json.loads(since.read_text())
        changed = {path for path, digest in audit.inventory(checked).items() if before.get(path) != digest}
        checked = {path: page for path, page in checked.items() if path in changed}
        findings = [f for f in findings if f.path in changed]
    if review:
        failing = {f.path for f in findings}
        passing = [(path, page.text) for path, page in checked.items() if path not in failing]
        # Model calls wait on the network, not the CPU: eight at once turned a
        # 24-minute review of every co page into a few minutes.
        with ThreadPoolExecutor(max_workers=8) as pool:
            verdicts = pool.map(lambda item: audit.review(item[0], item[1], model), passing)
        findings += [f for f in verdicts if f]
    table = audit.score(findings, checked)
    if as_json:
        print(json.dumps({"target": " ".join(target), "checked": sorted(checked),
                          "score": [{"rule": r, "passing": p, "pages": n} for r, p, n in table],
                          "findings": [{"command": f.path, "check": f.check, "fix": f.fix} for f in findings]},
                         indent=1))
    else:
        for f in findings:
            console.print(f"[red]✗[/red] {f.path}  [bold]{f.check}[/bold]: {f.fix}")
        console.print(f"\n{' '.join(target)}: {len(checked)} pages")
        for rule, passing, pages in table:
            console.print(f"  {rule:<13} {passing:>4}/{pages}")
        ready = not findings
        console.print(("[green]✓ fit for an agent harness[/green]" if ready
                       else f"[red]✗ not yet fit for an agent harness: {len(findings)} problems[/red]"))
        again = " ".join(["co audit", *words])
        console.print(f"Next: fix the pages above, then {again}" if findings
                      else "" if review else f"Next: {again} --review")
    if findings:
        raise typer.Exit(1)
