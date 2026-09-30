"""
Purpose: `co audit <command>` — is this CLI, ours or any other, fit for an agent harness? (#1735, #1997)
LLM-Note:
  Dependencies: imports from [cli/audit.py, cli/style.py, shutil] | imported by [cli/main.py]
  Data flow: the command as typed (co gmail, yt-dlp) → audit.audit() walks and checks printed pages → score table, findings, verdict | --style → audit.style_audit() runs each page (and read-only status commands) in a terminal and a pipe → style table and a table by group | --review → audit.review() on pages that passed | --inventory / --since → fingerprints to audit only what changed
  State/Effects: runs `<command> --help` in empty temporary directories; --style also runs commands named status/check/ls/doctor whose help says Read-only; --review calls a model
  Errors: exit 1 when any rule or review fails, each finding with its fix; exit 1 when the program is not on PATH
"""

import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import typer

from .. import audit
from ..style import command, count, error, heading, next_line, ok, plain_output


def handle_audit(words: list, review: bool, since: Path, inventory: bool, as_json: bool, model: str,
                 style: bool = False) -> None:
    target = list(words)
    if as_json or inventory:
        plain_output()
    if not shutil.which(target[0]) and target[0] != "co":
        print(error(f"No program {target[0]!r} on PATH. Audit the command as you would type it."))
        print(next_line("co audit co", sys.stdout))
        raise typer.Exit(1)
    findings, checked = audit.audit(target)
    if inventory:
        print(json.dumps(audit.inventory(checked), indent=1, sort_keys=True))
        return
    if not checked:
        print(error(f"No page reachable from {target[0]} --help is {' '.join(target)!r}."))
        print(next_line(f"co audit {target[0]}", sys.stdout))
        raise typer.Exit(1)
    if since is not None:
        before = json.loads(since.read_text())
        changed = {path for path, digest in audit.inventory(checked).items() if before.get(path) != digest}
        checked = {path: page for path, page in checked.items() if path in changed}
        findings = [f for f in findings if f.path in changed]
    rules = audit.RULES
    if style:
        findings, checked = audit.style_audit(checked)
        rules = audit.STYLE_RULES
    if review and not style:
        failing = {f.path for f in findings}
        passing = [(path, page.text) for path, page in checked.items() if path not in failing]
        # Model calls wait on the network, not the CPU: eight at once turned a
        # 24-minute review of every co page into a few minutes.
        with ThreadPoolExecutor(max_workers=8) as pool:
            verdicts = pool.map(lambda item: audit.review(item[0], item[1], model), passing)
        findings += [f for f in verdicts if f]
    table = audit.score(findings, checked, rules)
    groups = audit.by_group(findings, checked) if style else []
    if as_json:
        print(json.dumps({"target": " ".join(target), "checked": sorted(checked),
                          "score": [{"rule": r, "passing": p, "pages": n} for r, p, n in table],
                          **({"groups": [{"group": g, "passing": p, "outputs": n} for g, p, n in groups]}
                             if style else {}),
                          "findings": [{"command": f.path, "check": f.check, "fix": f.fix} for f in findings]},
                         indent=1))
    else:
        _report(words, findings, checked, table, groups, review, style)
    if findings:
        raise typer.Exit(1)


def _report(words, findings, checked, table, groups, review, style) -> None:
    for f in findings:
        print(error(f"{f.path}  {heading(f.check)}: {f.fix}"))
    kind = "outputs" if style else "pages"
    print(f"\n{heading(' '.join(words))}: {count(len(checked), kind[:-1])}")
    for rule, passing, pages in table:
        print(f"  {rule:<14} {passing:>4}/{pages}")
    failing_groups = [row for row in groups if row[1] < row[2]]
    if failing_groups:
        print(f"\n{heading('By group')} (outputs passing every rule)")
        for group, passing, outputs in failing_groups:
            print(f"  {group:<24} {passing:>4}/{outputs}")
    goal = "the visual standard" if style else "an agent harness"
    print(ok(f"fit for {goal}") if not findings
          else error(f"not yet fit for {goal}: {count(len(findings), 'problem')}"))
    again = " ".join(["co audit", *words, *(["--style"] if style else [])])
    if findings:
        print(f"Next: fix the {kind} above, then {command(again)}")
    elif not review and not style:
        print(next_line(f"{again} --review", sys.stdout))
