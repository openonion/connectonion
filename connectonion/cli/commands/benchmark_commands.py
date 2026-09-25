"""
Purpose: The verbs of skill benchmarks — `co benchmark list|check` (read-only) and `co eval run|report` (runs the real Agent)
LLM-Note:
  Dependencies: imports from [json, sys, pathlib, benchmark/] and lazily from [benchmark/runner.py, benchmark/report.py, core/usage.DEFAULT_MODEL] | imported by [cli/main.py] | tested by [tests/unit/test_benchmark_commands.py]
  Data flow: handle_benchmark_list/check → suite.load → printed table or JSON | handle_eval_run → suite.load → runner.load_agent/resolve_skill → runner.run → report.save → render | handle_eval_report → report.load → compare with the run before → render
  State/Effects: benchmark verbs read only; eval run writes one new directory under .co/eval-runs/<name>/
  Integration: every verb prints its own `Next:` line (HANDLER in command_tips) because the right next step depends on what it found
  Errors: exit 0 ok · 1 a run with a failed or unverified expectation · 2 bad name, suite or option · 3 the runner or the Agent itself broke (never a pass)
"""

import json
import sys
from typing import Optional

from ...benchmark import EXAMPLE, list_suites, load


def _next(text: str) -> None:
    """The next step, on stderr so --json stdout stays parseable; off with --no-tips / CO_TIPS=off."""
    from .command_tips import tips_enabled

    if tips_enabled():
        print(f"Next: {text}", file=sys.stderr)


def handle_benchmark_list(as_json: bool = False) -> int:
    rows = list_suites()
    if as_json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("No benchmarks yet. A benchmark is .co/benchmarks/<name>.yaml; this is the smallest valid one:\n")
        print(EXAMPLE)
        _next("write .co/benchmarks/<name>.yaml, then co benchmark check <name>")
        return 0
    for row in rows:
        state = f"{row['cases']} cases, valid" if row["valid"] else f"{row['problems']} problem(s)"
        print(f"{row['name']}\t{state}\t{row['path']}")
    first_bad = next((r for r in rows if not r["valid"]), None)
    _next(f"co benchmark check {(first_bad or rows[0])['name']}")
    return 0


def handle_benchmark_check(name: str, as_json: bool = False) -> int:
    suite, problems = load(name)
    if as_json:
        print(json.dumps({
            "name": name, "valid": suite is not None,
            "cases": len(suite.cases) if suite else None,
            "counts": suite.counts() if suite else None,
            "problems": [p.as_dict() for p in problems],
        }, indent=2))
        return 0 if suite else 2
    if suite is None:
        print(f"Invalid: {name} ({len(problems)} problem(s))")
        for problem in problems:
            print(f"  {problem.line()}")
        if any(p.field in ("", "cases") for p in problems):
            print("\nThe smallest valid benchmark:\n")
            print(EXAMPLE)
        _next(f"fix the file, then co benchmark check {name}")
        return 2
    counts = suite.counts()
    print(f"Valid: {len(suite.cases)} cases ({counts['normal']} normal, {counts['counterexample']} counterexample)"
          f" — {suite.path}")
    print("Structure is checked; whether the cases are really different decisions is for a person to read.")
    _next(f"write or edit .co/skills/<skill>/SKILL.md, then co eval run {name} --agent agent.py "
          f"--skill <skill> --runs 1")
    return 0


def handle_eval_run(name: str, agent_path: str, skill_name: Optional[str] = None, invoke: str = "auto",
                    runs: int = 1, as_json: bool = False, live: bool = False,
                    judge_model: Optional[str] = None, max_iterations: Optional[int] = None) -> int:
    from ...benchmark import report as reports
    from ...benchmark import runner
    from ...core.usage import DEFAULT_MODEL

    suite, problems = load(name)
    if suite is None:
        print(f"{name} is not a runnable benchmark:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem.line()}", file=sys.stderr)
        _next(f"co benchmark check {name}")
        return 2
    ceiling = max_iterations or runner.DEFAULT_MAX_ITERATIONS
    _say_what_it_will_spend(name, len(suite.cases), runs, ceiling)
    try:
        skill = runner.resolve_skill(skill_name) if skill_name else None
        agent = runner.load_agent(agent_path)
        result = runner.run(suite, agent, agent_path=agent_path, skill=skill, invoke=invoke, runs=runs,
                            live=live, judge_model=judge_model or DEFAULT_MODEL, max_iterations=ceiling)
    except runner.RunnerError as error:
        print(str(error), file=sys.stderr)
        return error.code
    path = reports.save(result)
    stored = reports.load(name, path.parent.name)
    comparison = reports.compare(stored, reports.previous(name, stored["run_id"]))
    if as_json:
        print(json.dumps({"report_path": str(path), "summary": stored["summary"], "comparison": comparison},
                         indent=2))
    else:
        print(reports.render(stored, comparison))
        if skill is None:
            print("No --skill was named: this scored the Agent as a whole, not any one skill.")
    _next(f"co eval report {name} --latest")
    return stored["summary"]["exit_code"]


def _say_what_it_will_spend(name: str, cases: int, runs: int, ceiling: int) -> None:
    """Before the first model call, how many Agent runs this is and how far each
    may go, on stderr. Every attempt is paid for from the user's own balance; a
    new user's first run on 1.8.8b9 cost $1 of $5 without a word beforehand."""
    from ...benchmark import report as reports

    print(f"{cases} cases × {runs} run(s) = {cases * runs} Agent runs, each stopped after {ceiling} steps "
          f"(--max-iterations N to raise), plus one judge call each. Paid from your balance.", file=sys.stderr)
    if runs > 1 and not reports.run_ids(name):
        print(f"No run of {name} is saved yet: --runs 1 first costs 1/{runs} of this and shows whether the "
              f"cases work; add runs to measure stability once they do.", file=sys.stderr)


def handle_eval_report(name: str, run_id: Optional[str] = None, as_json: bool = False) -> int:
    from ...benchmark import report as reports

    try:
        stored = reports.load(name, run_id)
    except LookupError as error:
        print(str(error), file=sys.stderr)
        return 2
    comparison = reports.compare(stored, reports.previous(name, stored["run_id"]))
    if as_json:
        print(json.dumps(dict(stored, comparison=comparison), indent=2, ensure_ascii=False))
    else:
        print(reports.render(stored, comparison))
    failing = [c["id"] for c in stored["cases"] if c["passed_attempts"] < len(c["attempts"])]
    if failing:
        _next(f"edit only the skill for {failing[0]}, then rerun the same benchmark: co eval run {name} "
              f"--agent {stored['agent']['path']}"
              + (f" --skill {stored['skill']['name']}" if stored.get("skill") else ""))
    else:
        _next(f"every case passed; add a harder case to .co/benchmarks/{name}.yaml, then co benchmark check {name}")
    return 0
