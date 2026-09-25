"""
Purpose: Keep every benchmark run as an immutable report, reopen it, and compare it with the run before
LLM-Note:
  Dependencies: imports from [json, os, secrets, time, pathlib, typing] | imported by [cli/commands/benchmark_commands.py] | tested by [tests/unit/test_benchmark_report.py]
  Data flow: report dict → save() → .co/eval-runs/<name>/<run-id>/report.json (+ traces/<case>-<n>.json) | runs()/load() read them back | compare(current, previous) → deltas | render() → the table a person reads
  State/Effects: save() creates a new directory per run and never overwrites one; nothing here edits the authored benchmark
  Integration: `co eval run` saves and renders; `co eval report` loads, compares and renders
  Errors: a run id that does not exist is a LookupError the CLI turns into exit 2

The old `co eval` wrote results back into the YAML a person authored, so the
standard and the score lived in one file and every run edited the standard.
Here the authored suite is never written to, and a run is a directory that is
never written twice: comparing two runs means comparing two files that cannot
have changed since.
"""

import json
import os
import secrets
import time
from pathlib import Path
from typing import List, Optional


def runs_dir(name: str, root: Optional[Path] = None) -> Path:
    return (root or Path.cwd()) / ".co" / "eval-runs" / name


def save(report: dict, root: Optional[Path] = None) -> Path:
    """Write the run under a fresh id. The traces go beside it, not inside it,
    so report.json stays readable."""
    # Sorted by name is sorted by time only if the time is finer than a run: two
    # runs inside one second used to order by their random suffix, so "the run
    # before" could be the run after. Microseconds first; the suffix only
    # breaks a tie nobody will hit.
    now = time.time()
    run_id = (time.strftime("%Y%m%dT%H%M%S", time.gmtime(now)) + f"{int(now % 1 * 1_000_000):06d}Z-"
              + secrets.token_hex(2))
    directory = runs_dir(report["benchmark"], root) / run_id
    directory.mkdir(parents=True, exist_ok=False)
    traces = directory / "traces"
    traces.mkdir()
    stored = dict(report, run_id=run_id)
    stored["cases"] = []
    for case in report["cases"]:
        attempts = []
        for attempt in case["attempts"]:
            trace_file = traces / f"{_safe(case['id'])}-{attempt['n']}.json"
            trace_file.write_text(json.dumps(attempt["trace"], ensure_ascii=False, indent=1, default=str),
                                  encoding="utf-8")
            attempts.append({k: v for k, v in attempt.items() if k != "trace"} | {"trace_file": str(trace_file)})
        stored["cases"].append(dict(case, attempts=attempts))
    path = directory / "report.json"
    path.write_text(json.dumps(stored, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(path, 0o444)  # a saved run is evidence; editing it by hand should take a deliberate step
    return path


def run_ids(name: str, root: Optional[Path] = None) -> List[str]:
    directory = runs_dir(name, root)
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if (p / "report.json").exists())


def load(name: str, run_id: Optional[str] = None, root: Optional[Path] = None) -> dict:
    ids = run_ids(name, root)
    if not ids:
        raise LookupError(f"no saved runs for {name} under {runs_dir(name, root)}. "
                          f"Next: co eval run {name} --agent agent.py")
    chosen = run_id or ids[-1]
    if chosen not in ids:
        raise LookupError(f"no run {chosen} for {name}; saved runs: {', '.join(ids[-5:])}")
    data = json.loads((runs_dir(name, root) / chosen / "report.json").read_text(encoding="utf-8"))
    data["report_path"] = str(runs_dir(name, root) / chosen / "report.json")
    return data


def previous(name: str, run_id: str, root: Optional[Path] = None) -> Optional[dict]:
    ids = run_ids(name, root)
    if run_id not in ids or ids.index(run_id) == 0:
        return None
    return load(name, ids[ids.index(run_id) - 1], root)


def compare(current: dict, before: Optional[dict]) -> Optional[dict]:
    """What changed since the run before: score, cases that flipped, forbidden outcomes it did not have."""
    if before is None:
        return None
    score = _score(current)
    earlier = _score(before)
    now_pass = {c["id"] for c in current["cases"] if _case_passed(c)}
    then_pass = {c["id"] for c in before["cases"] if _case_passed(c)}
    both = {c["id"] for c in current["cases"]} & {c["id"] for c in before["cases"]}
    forbidden_then = {(c["id"], i["text"]) for c in before["cases"] for a in c["attempts"]
                      for i in a["indicators"] if i["kind"] == "must_not" and i["verdict"] == "FAIL"}
    forbidden_now = {(c["id"], i["text"]) for c in current["cases"] for a in c["attempts"]
                     for i in a["indicators"] if i["kind"] == "must_not" and i["verdict"] == "FAIL"}
    return {
        "previous_run": before["run_id"],
        "score": score,
        "previous_score": earlier,
        "delta": round(score - earlier, 4),
        "newly_passing": sorted((now_pass - then_pass) & both),
        "newly_failing": sorted((then_pass - now_pass) & both),
        "forbidden_regressions": sorted(f"{case}: {text}" for case, text in forbidden_now - forbidden_then
                                        if case in both),
        "same_benchmark": current.get("benchmark_sha256") == before.get("benchmark_sha256"),
        "setup_changed": _setup_changes(current, before),
        "skill_changed": (current.get("skill") or {}).get("sha256") != (before.get("skill") or {}).get("sha256"),
    }


def _score(report: dict) -> float:
    """Passed checks over checks: expectations plus "did the skill run". A
    report written before checks existed falls back to expectations only."""
    summary = report["summary"]
    total = summary.get("checks", summary["indicators"])
    passed = summary.get("passed_checks", summary["passed_indicators"])
    return round(passed / total, 4) if total else 0.0


def _setup_changes(current: dict, before: dict) -> List[str]:
    """What else differs between two runs, so a changed setup is not read as a changed skill."""
    pairs = [("invoke", before.get("invoke"), current.get("invoke")),
             ("model", (before.get("agent") or {}).get("model"), (current.get("agent") or {}).get("model")),
             ("agent", (before.get("agent") or {}).get("path"), (current.get("agent") or {}).get("path")),
             ("runs", before.get("runs"), current.get("runs"))]
    return [f"{label} {then} → {now}" for label, then, now in pairs if then != now]


def _case_passed(case: dict) -> bool:
    return bool(case["attempts"]) and case["passed_attempts"] == len(case["attempts"])


def _safe(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text) or "case"


# ---- what a person reads ------------------------------------------------------------------


def render(report: dict, comparison: Optional[dict] = None) -> str:
    lines = []
    skill = report.get("skill")
    target = f"skill {skill['name']} ({skill['sha256'][:12]}, invoke={report['invoke']})" if skill else "no skill named"
    lines.append(f"{report['benchmark']}  ·  agent {report['agent']['path']} ({report['agent']['model'] or 'model ?'})"
                 f"  ·  {target}  ·  runs={report['runs']}{'  ·  LIVE' if report.get('live') else ''}")
    lines.append("")
    for case in report["cases"]:
        mark = "PASS" if _case_passed(case) else "FAIL"
        lines.append(f"{mark}  {case['id']}  [{case['kind']}]  stable {case['stability']}")
        for attempt in case["attempts"]:
            prefix = f"  #{attempt['n']} " if len(case["attempts"]) > 1 else "  "
            if attempt["error"]:
                lines.append(f"{prefix}ERROR  {attempt['error']}")
                continue
            if attempt.get("stopped"):  # .get: reports saved before the step ceiling have no such key
                lines.append(f"{prefix}STOPPED  {attempt['stopped']}")
            if attempt.get("invalid"):  # .get: reports saved before 1.8.8b12 have no such key
                lines.append(f"{prefix}INVALID  {attempt['invalid']}")
            if attempt["activation"]:
                lines.append(f"{prefix}{attempt['activation']['status']:<10} skill: {attempt['activation']['evidence']}")
            for indicator in attempt["indicators"]:
                label = "must    " if indicator["kind"] == "must" else "must_not"
                lines.append(f"{prefix}{indicator['verdict']:<10} {label} {indicator['text']}")
                if indicator["verdict"] != "PASS":
                    lines.append(f"{prefix}{'':<10}          ↳ {indicator['reason']}")
    s = report["summary"]
    lines.append("")
    lines.append(f"cases {s['cases_passing']}/{s['cases']} · attempts {s['passed_attempts']}/{s['attempts']} · "
                 f"expectations {s['passed_indicators']}/{s['indicators']} · failed {s['failed']} · "
                 f"unverified {s['unverified']} · forbidden {s['forbidden_failures']} · "
                 f"not activated {s['not_activated']} · stopped {s.get('stopped', 0)} · "
                 f"invalid {s.get('invalid', 0)} · "
                 f"runner errors {s['runner_errors']}")
    if s.get("agent_cost") is not None:
        ceiling = f", at most {report['max_iterations']} steps an attempt" if report.get("max_iterations") else ""
        lines.append(f"agent model cost ${s['agent_cost']:.3f} (judge not included{ceiling})")
    if comparison:
        lines.append(f"vs {comparison['previous_run']}: score {comparison['previous_score']:.0%} → "
                     f"{comparison['score']:.0%} ({comparison['delta']:+.0%})"
                     + ("" if comparison["same_benchmark"] else "  ⚠ the benchmark file changed between runs"))
        if comparison.get("setup_changed"):
            lines.append(f"  ⚠ not the same setup: {', '.join(comparison['setup_changed'])} — "
                         "a score change here is not the skill's alone")
        for label, key in (("newly passing", "newly_passing"), ("newly failing", "newly_failing"),
                           # Not "again": this set is, by construction, what the
                           # previous run did NOT do, and 1.8.8b7's "forbidden
                           # again" named a case that had just passed.
                           ("newly forbidden", "forbidden_regressions")):
            if comparison[key]:
                lines.append(f"  {label}: {', '.join(comparison[key])}")
    if report.get("report_path"):
        lines.append(f"report: {report['report_path']}")
    return "\n".join(lines)
