"""help-gate's model review is advisory, but a crash must not read as a pass (#2259).

The step script from .github/workflows/help-gate.yml runs here against a fake
review process: one that prints a verdict, and one that dies the way an exhausted
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
    for name, body in (("python", fake_co),):
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


def test_help_gate_fork_without_a_credential_is_reported_without_model_execution(tmp_path):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    (bin_dir / 'python').write_text('#!/bin/sh\necho model-must-not-run >&2\nexit 99\n')
    (bin_dir / 'python').chmod(0o755)
    summary = tmp_path / 'summary.md'
    env = {**os.environ, 'PATH': f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           'OPENONION_API_KEY': '', 'RUNNER_TEMP': str(tmp_path), 'GITHUB_STEP_SUMMARY': str(summary)}
    result = subprocess.run(['bash', '-e', '-c', STEP['run']], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    assert 'review skipped' in summary.read_text()
    assert 'model-must-not-run' not in result.stderr


def test_help_gate_collects_both_sides_in_parallel_and_caches_only_the_exact_base():
    jobs = WORKFLOW['jobs']
    assert 'needs' not in jobs['base']
    assert 'needs' not in jobs['pages']
    assert set(jobs['review']['needs']) == {'base', 'pages'}
    restore = next(s for s in jobs['base']['steps'] if s.get('id') == 'fingerprint')
    key = restore['with']['key']
    assert 'github.event.pull_request.base.sha' in key
    assert "hashFiles('connectonion/**', 'pyproject.toml', 'uv.lock')" in key
    assert 'restore-keys' not in restore['with']
    trigger = WORKFLOW.get('on', WORKFLOW.get(True))  # PyYAML's YAML 1.1 "on" spelling
    assert trigger['push']['branches'] == ['main']
    assert 'github.sha' in key  # main warms a cache readable by later PRs
    assert jobs['pages']['if'] == "github.event_name == 'pull_request'"
    assert jobs['review']['if'] == "github.event_name == 'pull_request'"
    fingerprint = next(s for s in jobs['base']['steps'] if s.get('name') == "Fingerprint the base's help pages")
    assert fingerprint['if'] == "steps.fingerprint.outputs.cache-hit != 'true'"
    assert "audit.inventory(audit.pages(['co']))" in fingerprint['run']
    assert "echo '{}'" in fingerprint['run']  # pre-audit base compatibility
    assert 'audit.audit(' not in STEP['run']  # consume head pages; never walk them again
    assert 'secrets.OPENONION_API_KEY' not in str(jobs['base']) + str(jobs['pages'])


def test_help_gate_only_reviews_changed_pages_that_passed_the_hard_rules(tmp_path, monkeypatch, capsys):
    import json
    from connectonion.cli import audit

    before = {'co unchanged': 'same', 'co changed': 'old', 'co broken': 'old'}
    head = {'hashes': {'co unchanged': 'same', 'co changed': 'new', 'co broken': 'new', 'co added': 'new'},
            'pages': {'co unchanged': 'untouched', 'co changed': 'updated',
                      'co broken': 'no example', 'co added': 'new page'},
            'findings': [{'path': 'co broken', 'check': 'example', 'detail': 'missing'},
                         {'path': 'co unchanged', 'check': 'example', 'detail': 'old finding'}]}
    (tmp_path / 'base.json').write_text(json.dumps(before))
    (tmp_path / 'pages.json').write_text(json.dumps(head))
    monkeypatch.setenv('RUNNER_TEMP', str(tmp_path))
    reviewed = []

    def review(path, text, model):
        reviewed.append((path, text))
        assert model  # same default as co audit --review, explicitly passed
        return None

    # Execute the actual Python block with a deterministic model substitute.
    monkeypatch.setattr(audit, 'review', review)
    block = STEP['run'].split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]
    exec(block, {})
    assert sorted(reviewed) == [('co added', 'new page'), ('co changed', 'updated')]
    output = capsys.readouterr().out
    assert '3 changed pages' in output
    assert 'co broken' in output
    assert 'co unchanged' not in output
    assert 'not yet fit for an agent harness' in output
