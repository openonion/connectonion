#!/usr/bin/env python3
"""Audit a co rem run from what it left behind: run records, Codex traces, pages.

Usage: python scripts/rem_trial_audit.py NOTEBOOK [--sessions ~/.codex/sessions] [--home ~] [--json]

Exit 1 when anything severe is found. Run after every trial init: each check
is something reading 1.9.2b3's logs by hand found (2026-10-10), and none of
them showed up in the run's own summary.

- read outside the material (reported; severe only with --strict-reads): a
  turn's command touched a file under HOME outside the notebook and outside
  what its task named. Investigations run with full disk access on purpose
  ("context over control", owner's decision 2026-10-11), so this is measured
  to see where they look, not treated as a failure.
- cites REM's own session: a page cites a coding session that ran in a
  notebook's .state/tasks, i.e. REM's own turn, as the user's words.
- refusal missing from ledger: a page's last turn was refused -- in an
  investigation, a sync's one-page maintenance, or a daily row -- and
  .state/refused-investigations.json does not record it.
- page shrank: one maintenance turn left less than 60% of a page's
  characters (connectonion 14,356 -> 4,132 on 2026-10-13).
- background never started: launchd loaded the job and never ran it.

Reported, not severe (2026-10-15 audit): refused rounds inside accepted
investigations, and churn -- a page worked more than three times in three
days, with how many of those turns changed nothing.
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


def page_turns(runs: list[dict]) -> list[dict]:
    """Every page turn the runs record, oldest first: {at, page, outcome, chars, refused_rounds}.

    An investigation names its page; a sync names its one-page turns in
    page_chars and refusals; a daily run names them in its page rows."""
    turns = []
    for run in sorted(runs, key=lambda run: run.get("started_at") or ""):
        at = run.get("started_at") or ""
        if run.get("record") and not run.get("pages"):
            turns.append({"at": at, "page": run["record"], "outcome": run.get("outcome"),
                          "refused_rounds": run.get("refused_rounds") or []})
        for page, chars in (run.get("page_chars") or {}).items():
            outcome = "completed" if page in (run.get("changed") or []) else "no_change"
            turns.append({"at": at, "page": page, "outcome": outcome, "chars": chars})
        for row in run.get("refusals") or []:
            turns.append({"at": at, "page": row["record"], "outcome": "refused"})
        for row in run.get("pages") or []:
            turns.append({"at": at, "page": row["page"], "outcome": row.get("outcome"),
                          "refused_rounds": row.get("refused_rounds") or []})
    return turns


def missing_refusals(root: Path, runs: list[dict]) -> list[str]:
    """Pages refused and not accepted since, which the ledger does not hold.

    A later nothing_found or NO CHANGE settles nothing: job-followup and x-reply
    were refused at init and came back nothing_found every day after."""
    refused = set()
    for turn in page_turns(runs):
        if turn["outcome"] == "refused":
            refused.add(turn["page"])
        elif turn["outcome"] in ("completed", "accepted"):
            refused.discard(turn["page"])
    ledger = root / ".state" / "refused-investigations.json"
    recorded = json.loads(ledger.read_text()) if ledger.is_file() else {}
    return sorted(refused - set(recorded))


def refused_turns(root: Path, runs: list[dict]) -> dict:
    """Refused turns the task folders kept, against those the run records name.

    Two refusals on the 2026-10-10 notebook were in task folders only (Corin
    Marsh's and Briar's rounds): swallowed by an accepted investigation."""
    tasks = sum(1 for review in (root / ".state" / "tasks").glob("*/review.json")
                if json.loads(review.read_text()).get("accepted") is False)
    turns = page_turns(runs)
    recorded = sum(turn["outcome"] == "refused" for turn in turns) + sum(len(turn.get("refused_rounds") or [])
                                                                       for turn in turns)
    return {"tasks": tasks, "recorded": recorded, "swallowed": max(0, tasks - recorded)}


def refused_rounds(runs: list[dict]) -> list[str]:
    """Pages accepted with a refused round inside: material no later round read."""
    return sorted({turn["page"] for turn in page_turns(runs) if turn.get("refused_rounds")})


def shrinks(runs: list[dict], keep: float = 0.6, floor: int = 1000) -> list[str]:
    return [f"{turn['page']} {turn['chars'][0]:,} -> {turn['chars'][1]:,} at {turn['at'][:16]}"
            for turn in page_turns(runs) if turn.get("chars")
            and turn["chars"][0] >= floor and turn["chars"][1] < turn["chars"][0] * keep]


def churn(runs: list[dict], most: int = 3, days: int = 3) -> list[dict]:
    """Pages worked more than `most` times within `days` days, and how many of those turns changed nothing."""
    by_page = {}
    for turn in page_turns(runs):
        by_page.setdefault(turn["page"], []).append(turn)
    found = []
    for page, turns in sorted(by_page.items()):
        stamps = [datetime.fromisoformat(turn["at"]) for turn in turns]
        window = max(sum(1 for other in stamps if timedelta(0) <= other - stamp <= timedelta(days=days))
                     for stamp in stamps)
        if window > most:
            found.append({"page": page, "turns": len(turns), "in_window": window,
                          "no_change": sum(1 for turn in turns if turn["outcome"] == "no_change")})
    return found


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
                found.append(f"{page.relative_to(root)} cites {session} (the next sync's tidy removes it)")
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


def audit(root: Path, sessions: Path, home: Path, allowed: list[Path] = (), strict_reads: bool = False) -> dict:
    root, home = Path(root), Path(home)
    # An installed skill's source is a skill page's material.
    allowed = [*allowed, *(home / place for place in (".co/skills", ".codex/skills", ".agents/skills", ".claude/skills",
                                                      ".codex/plugins", ".claude/plugins"))]
    runs, files = load_runs(root) if (root / ".state" / "runs").is_dir() else [], session_files(Path(sessions))
    traces = trace_checks(root, rem_rollouts(root, files), home, allowed)
    severe = []
    if traces["outside"] and strict_reads:
        severe.append({"check": "read outside the material", "count": len(traces["outside"]),
                       "example": f"{traces['outside'][0]}; by place {traces['outside_by_place']}"})
    for finding in self_citations(root, files):
        severe.append({"check": "cites REM's own session", "count": 1, "example": finding})
    for record in missing_refusals(root, runs):
        severe.append({"check": "refusal missing from ledger", "count": 1, "example": record})
    for shrink in shrinks(runs):
        severe.append({"check": "page shrank", "count": 1, "example": shrink})
    if never := background_never_started(root):
        severe.append({"check": "background never started", "count": 1, "example": never})
    traces["outside_reads"] = len(traces["outside"])
    return {"runs": {**run_summary(runs), "refused_rounds": refused_rounds(runs),
                     "refused_turns": refused_turns(root, runs), "churn": churn(runs)},
            "traces": {k: v for k, v in traces.items() if k != "outside"},
            "severe": severe, "pages": page_checks(root)}


def show(report: dict) -> str:
    lines = [f"Runs: {report['runs']['runs']}", *(f"  {k}: {v}" for k, v in report["runs"]["by_phase"].items())]
    lines += ["Errors:", *(f"  {n:3d}  {e}" for e, n in report["runs"]["errors"].items())]
    turns = report["runs"]["refused_turns"]
    lines += [f"Refused turns: {turns['tasks']} in task folders, {turns['recorded']} in run records, "
              f"{turns['swallowed']} swallowed"]
    lines += ["Refused rounds inside accepted pages:", *(f"  {page}" for page in report["runs"]["refused_rounds"])]
    lines += ["Churn (turns, most in 3 days, NO CHANGE):",
              *(f"  {c['page']}: {c['turns']}, {c['in_window']}, {c['no_change']}" for c in report["runs"]["churn"])]
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
    parser.add_argument("--strict-reads", action="store_true", help="a read outside the material is severe")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit(Path(args.notebook), Path(args.sessions), Path(args.home), [Path(p) for p in args.allow],
                   strict_reads=args.strict_reads)
    print(json.dumps(report, indent=1, ensure_ascii=False) if args.json else show(report))
    return 1 if report["severe"] else 0


if __name__ == "__main__":
    sys.exit(main())
