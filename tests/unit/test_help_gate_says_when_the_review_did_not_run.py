"""help-gate's model review is advisory, but a crash must not read as a pass (#2259).

The step script from .github/workflows/help-gate.yml runs here against a fake
`co`: one that prints a verdict, and one that dies the way an exhausted
credit balance did on PR #2238.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/help-gate.yml").read_text())
STEP = next(s for s in WORKFLOW["jobs"]["review"]["steps"] if s.get("name") == "Review the pages this PR added or changed")

CRASH = """#!/bin/sh
echo 'Traceback (most recent call last):' >&2
echo 'connectonion.core.exceptions.InsufficientCreditsError: need $0.0054, have $0.0006' >&2
exit 1
"""
VERDICT = """#!/bin/sh
echo 'co: 2 pages'
echo '✓ fit for an agent harness'
"""
FINDINGS = """#!/bin/sh
echo '✗ co x  review: clear; say what it writes'
echo '✗ not yet fit for an agent harness: 1 problems'
exit 1
"""


def run_step(tmp_path, fake_co):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("co", fake_co), ("pip", "#!/bin/sh\nexit 0\n")):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    summary = tmp_path / "summary.md"
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "OPENONION_API_KEY": "set", "RUNNER_TEMP": str(tmp_path), "GITHUB_STEP_SUMMARY": str(summary)}
    result = subprocess.run(["bash", "-e", "-c", STEP["run"]], env=env, capture_output=True, text=True)
    return result, summary.read_text()


pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="the workflow step is a bash script")


def test_a_crashed_review_is_reported_as_unavailable_not_as_a_pass(tmp_path):
    result, summary = run_step(tmp_path, CRASH)

    assert result.returncode == 0  # advisory: it never blocks the merge
    assert "review unavailable" in summary
    assert "InsufficientCreditsError" in summary
    assert "::warning" in result.stdout


def test_a_completed_review_shows_its_verdict_without_a_warning(tmp_path):
    result, summary = run_step(tmp_path, VERDICT)

    assert result.returncode == 0
    assert "fit for an agent harness" in summary
    assert "unavailable" not in summary
    assert "::warning" not in result.stdout


def test_a_review_with_findings_still_does_not_block(tmp_path):
    result, summary = run_step(tmp_path, FINDINGS)

    assert result.returncode == 0
    assert "not yet fit for an agent harness" in summary
    assert "unavailable" not in summary
