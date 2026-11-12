"""Decide whether the tagged commit's Tests run already proves it.

The release used to re-run the whole Tests workflow (about 37 jobs) on a
commit whose main-push run had just tested exactly that code; queued behind
the org's concurrent-job limit, that re-run was 16 of a release's 20 minutes.

Only a ``push`` run counts. A ``pull_request`` run tests GitHub's synthetic
merge ref, not the commit its ``head_sha`` names, so it is no evidence for a
squash-merged tag. A run counts as green only when it concluded ``success``
and every job of its latest attempt did too, ``tests-passed`` included: a
cancelled or skipped shard is not a pass.

Verdicts:
  tested    a green run exists; the release skips the matrix.
  untested  no push run exists for this commit (an untagged branch, a moved
            tag); the release runs the full tests.yml itself.
  wait      a run is still going (a tag cut right after the merge); poll it.
  blocked   every finished run on this commit is red. Publication stops; we
            do not re-run the matrix until a flake goes green. Re-run the red
            Tests run, then retry the release with workflow_dispatch.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable

TESTED, UNTESTED, WAIT, BLOCKED = "tested", "untested", "wait", "blocked"
AGGREGATE_JOB = "tests-passed"


@dataclass
class Decision:
    verdict: str
    reason: str


def _red_jobs(jobs: dict) -> list[str]:
    listed = jobs.get("jobs", [])
    red = [f"{job['name']}: {job.get('conclusion') or job.get('status')}"
           for job in listed if job.get("conclusion") != "success"]
    if not any(job["name"] == AGGREGATE_JOB for job in listed):
        red.append(f"{AGGREGATE_JOB}: missing")
    return red


def decide(sha: str, runs: dict, jobs_for: Callable[[int], dict]) -> Decision:
    """Pure decision over the API's runs listing and each run's jobs."""
    ours = [run for run in runs.get("workflow_runs", [])
            if run["head_sha"] == sha and run["event"] == "push"]
    if not ours:
        return Decision(UNTESTED, f"no push Tests run exists for {sha}")
    red = []
    for run in ours:
        if run["status"] != "completed":
            continue
        problems = _red_jobs(jobs_for(run["id"]))
        if run["conclusion"] == "success" and not problems:
            return Decision(TESTED, f"Tests run {run['html_url']} passed every job on {sha}")
        red.append(f"{run['html_url']} ({run['conclusion']}): " + "; ".join(problems))
    if any(run["status"] != "completed" for run in ours):
        return Decision(WAIT, f"a Tests run for {sha} is still running")
    return Decision(BLOCKED, "every Tests run on this commit is red: " + " | ".join(red))


def _gh(path: str) -> dict:
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--wait-minutes", type=float, default=25)
    parser.add_argument("--poll-seconds", type=float, default=20)
    args = parser.parse_args()

    runs_path = (f"repos/{args.repo}/actions/workflows/tests.yml/runs"
                 f"?head_sha={args.sha}&event=push&per_page=100")
    deadline = time.monotonic() + args.wait_minutes * 60
    while True:
        decision = decide(args.sha, _gh(runs_path), lambda run_id: _gh(
            f"repos/{args.repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100"))
        print(f"{decision.verdict}: {decision.reason}", flush=True)
        if decision.verdict != WAIT:
            break
        if time.monotonic() > deadline:
            print(f"Tests did not finish within {args.wait_minutes:g} minutes; "
                  "retry the release with workflow_dispatch once it does.", file=sys.stderr)
            return 1
        time.sleep(args.poll_seconds)

    if decision.verdict == BLOCKED:
        print("Re-run the red Tests run; once it is green, retry the release "
              "with workflow_dispatch.", file=sys.stderr)
        return 1
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"tested={'true' if decision.verdict == TESTED else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
