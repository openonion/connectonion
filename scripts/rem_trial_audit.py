#!/usr/bin/env python3
"""Audit a co rem run from what it left behind: run records, Codex traces, pages.

Usage: python scripts/rem_trial_audit.py NOTEBOOK [--sessions ~/.codex/sessions] [--home ~] [--json]

Exit 1 when anything severe is found. Run after every trial init: each check
is something reading 1.9.2b3's logs by hand found (2026-10-10), and none of
them showed up in the run's own summary.

- read outside the material: an investigation turn's command touched a file
  under HOME outside the notebook (another notebook, ~/.claude/projects
  transcripts, ~/.codex/sessions, notes).
- cites REM's own session: a page cites a coding session that ran in a
  notebook's .state/tasks, i.e. REM's own turn, as the user's words.
- refusal missing from ledger: a page's last run was refused, and
  .state/refused-investigations.json does not record it.
- background never started: launchd loaded the job and never ran it.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

PATH = r"(?:~|{home})(/[^\s'\"`;|&)(<>,\]]*)"
PRIVATE_SOURCE = re.compile(r"\.claude/projects|\.codex/sessions")
DOMAIN_TITLE = re.compile(r"^# ([a-z0-9-]+\.)+[a-z]{2,}\s*$", re.M)
SEARCH_400 = re.compile(r"refused this search \(HTTP 400\)")


def load_runs(root: Path) -> list[dict]:
    return [json.loads(path.read_text()) for path in sorted((root / ".state" / "runs").glob("*.json"))]


def run_summary(runs: list[dict]) -> dict:
    by_phase = Counter((run.get("phase") or "?", run.get("outcome") or "?") for run in runs)
    errors = Counter(re.sub(r"\d+", "N", (run.get("error") or "")[:70]) for run in runs if run.get("error"))
    unfinished = [run["id"] for run in runs if not run.get("finished_at") and run.get("outcome") != "running"]
    return {"runs": len(runs), "by_phase": {f"{p} {o}": n for (p, o), n in sorted(by_phase.items())},
            "errors": dict(errors.most_common(12)), "unfinished": unfinished}


def missing_refusals(root: Path, runs: list[dict]) -> list[str]:
    last = {}
    for run in sorted(runs, key=lambda run: run.get("started_at") or ""):
        if run.get("record"):
            last[run["record"]] = run.get("outcome")
    ledger = root / ".state" / "refused-investigations.json"
    recorded = json.loads(ledger.read_text()) if ledger.is_file() else {}
    return sorted(record for record, outcome in last.items() if outcome == "refused" and record not in recorded)


def session_files(sessions: Path) -> dict[str, Path]:
    """Every rollout by its session id (the filename's tail), without opening them."""
    found = {}
    for path in sessions.rglob("rollout-*.jsonl") if sessions.is_dir() else ():
        found[path.stem.split("-", 6)[-1]] = path
    return found


def meta(path: Path) -> dict:
    with path.open() as rollout:
        return json.loads(rollout.readline()).get("payload") or {}


def rem_task(cwd: str) -> bool:
    parts = Path(cwd or "").parts
    return any(parts[i:i + 2] == (".state", "tasks") for i in range(len(parts) - 1))


def rem_rollouts(root: Path, files: dict[str, Path]) -> list[Path]:
    tasks = str(root.resolve() / ".state" / "tasks")
    return [path for path in files.values() if str(meta(path).get("cwd", "")).startswith(tasks)]


def prompt(path: Path) -> str:
    """The task the turn was given: every user message that carries <co_rem_task>."""
    found = []
    for line in path.open():
        payload = json.loads(line).get("payload") or {}
        if payload.get("type") == "message" and payload.get("role") == "user":
            text = " ".join(part.get("text", "") for part in payload.get("content") or [] if isinstance(part, dict))
            if "<co_rem_task>" in text:
                found.append(text)
    return "\n".join(found)


def named(text: str, home: Path) -> list[Path]:
    """Paths under HOME a text names: what a turn was told it may read."""
    return [Path(os.path.normpath(home / match.lstrip("/")))
            for match in re.findall(PATH.format(home=re.escape(str(home))), text)]


def calls(path: Path) -> list[str]:
    found = []
    for line in path.open():
        row = json.loads(line)
        payload = row.get("payload") or {}
        if row.get("type") == "response_item" and payload.get("type") in ("function_call", "custom_tool_call"):
            found.append(str(payload.get("arguments") or payload.get("input") or ""))
    return found


def outside(command: str, root: Path, home: Path, allowed: list[Path]) -> list[str]:
    # normpath, not resolve: a symlink under HOME is still a read under HOME.
    paths = named(command, home)
    keep = [root, root.resolve(), *allowed]
    return [str(path) for path in paths if not any(path == base or base in path.parents for base in keep)]


def trace_checks(root: Path, rollouts: list[Path], home: Path, allowed: list[Path]) -> dict:
    wandered, tools, turns = [], Counter(), Counter()
    for path in rollouts:
        # The project's repository or the skill's source, named in the task, is that turn's material.
        given = [*allowed, *named(prompt(path), home)]
        for command in calls(path):
            wandered += outside(command, root, home, given)
            for name in ("mcp__", "web__run", "spawn_agent"):
                tools[name] += name in command
        text = path.read_text()
        turns["with a refused Outlook search"] += bool(SEARCH_400.search(text))
        turns["with a missing file"] += "No such file or directory" in text
    where = Counter("/".join(Path(path).relative_to(home).parts[:2]) for path in wandered)
    return {"rollouts": len(rollouts), "outside": wandered, "outside_by_place": dict(where.most_common(10)),
            "tools": dict(tools), **turns}


def self_citations(root: Path, files: dict[str, Path]) -> list[str]:
    found = []
    for page in pages(root):
        for session in set(re.findall(r"(?:codex|claude-code):([0-9a-f-]{8,})", page.read_text())):
            path = files.get(session)
            if path and rem_task(meta(path).get("cwd", "")):
                found.append(f"{page.relative_to(root)} cites {session}")
    return found


def background_never_started(root: Path) -> str:
    worker = root / ".state" / "worker.json"
    state = json.loads(worker.read_text()) if worker.is_file() else {}
    if not (state.get("enabled") and state.get("scheduler") == "launchd" and sys.platform == "darwin"):
        return ""
    from connectonion.rem.schedule import Launchd
    installed = state.get("installed_at")
    late = installed and datetime.now(timezone.utc) - datetime.fromisoformat(installed) > timedelta(minutes=15)
    return f"loaded since {installed[:10]}, launchd runs = 0" if late and Launchd().describe(root).get("runs") == 0 else ""


def section(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(name)}\n(.*?)(?=^## |\Z)", text)
    return match[1] if match else ""


def page_problems(record: str, text: str) -> list[str]:
    body, _, sources = text.partition("\n## Sources\n")
    listed = [int(n) for n in re.findall(r"(?m)^- \[(\d+)\]", sources)]
    cited = {int(n) for n in re.findall(r"\[(\d+)\](?!\()", body)}
    problems = []
    if cited - set(listed):
        problems.append("citation with no source")
    if listed and sorted(set(listed)) != list(range(1, len(set(listed)) + 1)):
        problems.append("sources numbered with gaps")
    if len(re.findall(r"(?m)^- ", section(text, "Uncertainties"))) > 5:
        problems.append("more than five uncertainties")
    if "not investigated yet" in text.rpartition("Investigation:")[2]:
        problems.append("not investigated")
    aka = re.search(r"(?m)^- Also known as: (.+)$", text)
    if aka and all("@" in part for part in re.split(r"[;,]", aka[1]) if part.strip()):
        problems.append("also known as is only addresses")
    if PRIVATE_SOURCE.search(sources):
        problems.append("private path cited")
    if record.startswith("orgs/") and DOMAIN_TITLE.search(text.split("\n", 1)[0] + "\n"):
        problems.append("organisation titled by its domain")
    return problems


def pages(root: Path) -> list[Path]:
    """The notebook's pages; a candidate under .state is a turn's draft, not a page."""
    return [page for page in sorted(root.glob("*/**/*.md")) if not page.relative_to(root).parts[0].startswith(".")]


def page_checks(root: Path) -> list[dict]:
    return [{"check": problem, "page": str(page.relative_to(root))}
            for page in pages(root)
            for problem in page_problems(str(page.relative_to(root)), page.read_text(encoding="utf-8"))]


def audit(root: Path, sessions: Path, home: Path, allowed: list[Path] = ()) -> dict:
    root, home = Path(root), Path(home)
    # An installed skill's source is a skill page's material.
    allowed = [*allowed, *(home / place for place in (".co/skills", ".codex/skills", ".agents/skills", ".claude/skills",
                                                      ".codex/plugins", ".claude/plugins"))]
    runs, files = load_runs(root) if (root / ".state" / "runs").is_dir() else [], session_files(Path(sessions))
    traces = trace_checks(root, rem_rollouts(root, files), home, allowed)
    severe = []
    if traces["outside"]:
        severe.append({"check": "read outside the material", "count": len(traces["outside"]),
                       "example": f"{traces['outside'][0]}; by place {traces['outside_by_place']}"})
    for finding in self_citations(root, files):
        severe.append({"check": "cites REM's own session", "count": 1, "example": finding})
    for record in missing_refusals(root, runs):
        severe.append({"check": "refusal missing from ledger", "count": 1, "example": record})
    if never := background_never_started(root):
        severe.append({"check": "background never started", "count": 1, "example": never})
    return {"runs": run_summary(runs), "traces": {k: v for k, v in traces.items() if k != "outside"},
            "severe": severe, "pages": page_checks(root)}


def show(report: dict) -> str:
    lines = [f"Runs: {report['runs']['runs']}", *(f"  {k}: {v}" for k, v in report["runs"]["by_phase"].items())]
    lines += ["Errors:", *(f"  {n:3d}  {e}" for e, n in report["runs"]["errors"].items())]
    lines += [f"Traces: {json.dumps(report['traces'])}", "Severe:"]
    lines += [f"  {f['check']} ×{f['count']}: {f['example']}" for f in report["severe"]] or ["  none"]
    tally = Counter(f["check"] for f in report["pages"])
    lines += ["Pages:", *(f"  {n:4d}  {check}" for check, n in tally.most_common())]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("notebook")
    parser.add_argument("--sessions", default=str(Path.home() / ".codex" / "sessions"))
    parser.add_argument("--home", default=str(Path.home()))
    parser.add_argument("--allow", action="append", default=[], help="a path turns may read besides the notebook")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit(Path(args.notebook), Path(args.sessions), Path(args.home), [Path(p) for p in args.allow])
    print(json.dumps(report, indent=1, ensure_ascii=False) if args.json else show(report))
    return 1 if report["severe"] else 0


if __name__ == "__main__":
    sys.exit(main())
