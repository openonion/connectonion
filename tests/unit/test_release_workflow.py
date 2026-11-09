"""The release path is automated, gated, and separate from announcements."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RELEASE = (ROOT / ".github/workflows/release.yml").read_text()
TESTS = (ROOT / ".github/workflows/tests.yml").read_text()
WHEEL_ACCEPTANCE = (ROOT / "tests/e2e/test_the_wheel_works_when_installed.py").read_text()


def test_release_reuses_full_tests_and_waits_for_them_before_publication():
    assert "workflow_call:" in TESTS
    assert "uses: ./.github/workflows/tests.yml" in RELEASE
    build_job = RELEASE.split("  build:", 1)[1].split("  publish:", 1)[0]
    publish_job = RELEASE.split("  publish:", 1)[1].split("  finalize:", 1)[0]
    assert "needs: tests" not in build_job
    assert "needs: [gate, tests, build]" in publish_job


def test_ci_audits_the_exact_dependency_lock():
    assert "uv==0.6.16" in TESTS
    assert "pip-audit==2.10.1" in TESTS
    assert "uv lock --check" in TESTS
    assert "uv export --quiet --frozen --all-extras --no-dev --no-emit-project" in TESTS
    assert "python -m pip_audit" in TESTS
    assert "--disable-pip --strict --progress-spinner off" in TESTS


def test_remote_browser_egress_has_a_job_timeout():
    workflow = yaml.safe_load(TESTS)
    assert workflow["jobs"]["remote-browser-egress"].get("timeout-minutes") == 20


def test_every_pull_request_runs_the_test_workflow():
    trigger = TESTS.split("on:", 1)[1].split("jobs:", 1)[0]
    pull_request = trigger.split("pull_request:", 1)[1].split("workflow_call:", 1)[0]

    assert "branches:" not in pull_request


def test_pytest_jobs_install_the_declared_dev_extra():
    pytest_jobs = ("test", "cli-help-audit", "cli-help-audit-tree", "remote-browser-egress", "windows-browser")
    lines = TESTS.splitlines()
    for job in pytest_jobs:
        start = lines.index(f"  {job}:")
        job_lines = []
        for line in lines[start + 1 :]:
            if line.startswith("  ") and not line.startswith("    "):
                break
            job_lines.append(line)
        job_body = "\n".join(job_lines)
        assert 'pip install -e ".[dev]"' in job_body

    assert TESTS.count('pip install -e ".[dev]"') == len(pytest_jobs)
    assert "pip install pytest" not in TESTS


def test_tag_and_emergency_manual_release_paths_exist():
    assert 'tags:\n      - "v*"' in RELEASE
    assert "workflow_dispatch:" in RELEASE
    assert "MANUAL_VERSION" in RELEASE
    assert 'git rev-parse --verify --quiet "refs/tags/$tag"' in RELEASE
    assert 'tagged_commit="$(git rev-list -n 1 "$tag")"' in RELEASE
    assert '"$tagged_commit" != "$GITHUB_SHA"' in RELEASE


def test_manual_release_is_only_a_retry_for_an_existing_reviewed_tag():
    assert "Release tag $tag does not exist" in RELEASE
    assert 'git rev-list -n 1 "$tag"' in RELEASE


def test_test_job_does_not_inherit_repository_secrets():
    assert "secrets: inherit" not in RELEASE


def test_release_uses_trusted_publishing_and_verifies_pypi():
    assert "id-token: write" in RELEASE
    assert "pypa/gh-action-pypi-publish@" in RELEASE
    assert "--no-cache-dir \"connectonion==$VERSION\"" in RELEASE
    assert "connectonion.__version__ == '$VERSION'" in RELEASE


def test_build_publish_and_finalize_permissions_are_separated():
    before_jobs = RELEASE.split("jobs:", 1)[0]
    tests_job = RELEASE.split("  tests:", 1)[1].split("  build:", 1)[0]
    build_job = RELEASE.split("  build:", 1)[1].split("  publish:", 1)[0]
    publish_job = RELEASE.split("  publish:", 1)[1].split("  finalize:", 1)[0]
    finalize_job = RELEASE.split("  finalize:", 1)[1]

    assert "contents: read" in before_jobs
    assert "contents: write" not in before_jobs
    assert "id-token: write" not in before_jobs
    assert "contents: read" in tests_job
    assert "contents: read" in build_job
    assert "contents: write" not in build_job
    assert "id-token: write" not in build_job
    assert "id-token: write" in publish_job
    assert "contents: write" not in publish_job
    assert "environment:" in publish_job
    assert "contents: write" in finalize_job
    assert "id-token: write" not in finalize_job


def test_only_the_current_pair_is_built_and_attached():
    assert "rm -rf dist" in RELEASE
    assert 'wheel="dist/connectonion-${VERSION}-py3-none-any.whl"' in RELEASE
    assert 'sdist="dist/connectonion-${VERSION}.tar.gz"' in RELEASE
    assert "verify_published_artifacts.py" in RELEASE
    assert 'wheel="published/connectonion-${VERSION}-py3-none-any.whl"' in RELEASE
    assert 'sdist="published/connectonion-${VERSION}.tar.gz"' in RELEASE
    assert "gh release create" in RELEASE


def test_preview_releases_are_not_advertised_as_latest():
    assert '"$VERSION" =~ [a-zA-Z]' in RELEASE
    assert "--prerelease --latest=false" in RELEASE


def test_artifact_job_installs_what_its_wheel_acceptance_test_needs():
    build_job = RELEASE.split("  build:", 1)[1].split("  publish:", 1)[0]
    install = 'python -m pip install --upgrade pip build twine ".[dev]"'
    acceptance = "pytest tests/e2e/test_the_wheel_works_when_installed.py"

    assert install in build_job
    assert "requirements.txt" not in build_job
    assert build_job.index(install) < build_job.index(acceptance)


def test_wheel_acceptance_reinstalls_over_the_build_environment_copy():
    assert '"--force-reinstall"' in WHEEL_ACCEPTANCE


def test_announcements_cannot_fail_a_package_release():
    assert "Discord/LinkedIn integration" in RELEASE
    assert "discord.com/api/webhooks" not in RELEASE.lower()


def test_external_actions_are_pinned_to_immutable_commits():
    workflows = RELEASE + TESTS
    external_uses = [
        line.strip()
        for line in workflows.splitlines()
        if line.strip().startswith("uses:") and "uses: ./" not in line
    ]

    assert external_uses
    for line in external_uses:
        reference = line.split("@", 1)[1].split()[0]
        assert len(reference) == 40
        assert all(character in "0123456789abcdef" for character in reference)


# The release does not re-run a Tests run that already passed on the tagged
# commit; .github/scripts/release_test_gate.py decides from the API's own
# answers. The fixtures are recorded from the main-push Tests run of
# 69685d5 (v1.9.3rc63's commit), trimmed to the fields the gate reads.

import copy
import importlib.util
import json
import sys

import pytest

_GATE_SPEC = importlib.util.spec_from_file_location(
    "release_test_gate", ROOT / ".github/scripts/release_test_gate.py"
)
GATE = importlib.util.module_from_spec(_GATE_SPEC)
sys.modules[_GATE_SPEC.name] = GATE  # dataclasses resolve their module by name
_GATE_SPEC.loader.exec_module(GATE)

FIXTURES = ROOT / "tests/fixtures/release_gate"
RECORDED_SHA = "69685d5af38697eafdf02f6a8a476771d72bd361"
RECORDED_RUNS = json.loads((FIXTURES / "tests_runs_for_sha.json").read_text())
RECORDED_JOBS = json.loads((FIXTURES / "tests_run_jobs.json").read_text())


def _decide(runs=None, jobs=None, sha=RECORDED_SHA):
    runs = RECORDED_RUNS if runs is None else runs
    jobs = RECORDED_JOBS if jobs is None else jobs
    return GATE.decide(sha, runs, lambda run_id: jobs)


def _with_job(name, **fields):
    jobs = copy.deepcopy(RECORDED_JOBS)
    for job in jobs["jobs"]:
        if job["name"] == name:
            job.update(fields)
    return jobs


def _with_run(**fields):
    runs = copy.deepcopy(RECORDED_RUNS)
    runs["workflow_runs"][0].update(fields)
    return runs


def test_a_green_tests_run_on_the_exact_commit_skips_the_matrix():
    assert _decide().verdict == GATE.TESTED


def test_an_untested_or_moved_tag_runs_the_full_matrix():
    assert _decide(sha="0" * 40).verdict == GATE.UNTESTED
    assert _decide(runs={"total_count": 0, "workflow_runs": []}).verdict == GATE.UNTESTED


def test_a_pull_request_run_is_not_evidence_for_the_merged_commit():
    # A pull_request run tests GitHub's merge ref, not the commit it names.
    assert _decide(runs=_with_run(event="pull_request")).verdict == GATE.UNTESTED


def test_a_run_still_in_progress_is_waited_for():
    runs = _with_run(status="in_progress", conclusion=None)
    assert _decide(runs=runs).verdict == GATE.WAIT


def test_a_failed_run_blocks_publish():
    runs = _with_run(conclusion="failure")
    jobs = {"jobs": [
        dict(job, conclusion="failure") if job["name"] in {"test (3.12) 4/6", "tests-passed"}
        else job for job in RECORDED_JOBS["jobs"]]}
    decision = _decide(runs=runs, jobs=jobs)
    assert decision.verdict == GATE.BLOCKED
    assert "test (3.12) 4/6" in decision.reason


@pytest.mark.parametrize("conclusion", ["cancelled", "skipped"])
def test_a_cancelled_or_skipped_shard_blocks_publish_even_under_a_green_run(conclusion):
    decision = _decide(jobs=_with_job("test (3.11) 2/6", conclusion=conclusion))
    assert decision.verdict == GATE.BLOCKED
    assert "test (3.11) 2/6" in decision.reason


def test_a_run_without_the_tests_passed_aggregate_is_not_green():
    jobs = {"jobs": [job for job in RECORDED_JOBS["jobs"] if job["name"] != "tests-passed"]}
    assert _decide(jobs=jobs).verdict == GATE.BLOCKED


def test_a_green_attempt_beats_an_older_red_run_on_the_same_commit():
    runs = copy.deepcopy(RECORDED_RUNS)
    red = dict(runs["workflow_runs"][0], id=1, conclusion="failure")
    runs["workflow_runs"].append(red)
    decision = GATE.decide(RECORDED_SHA, runs,
                           lambda run_id: RECORDED_JOBS if run_id != 1 else {"jobs": []})
    assert decision.verdict == GATE.TESTED


def _release():
    return yaml.safe_load(RELEASE)


def test_release_gate_reads_actions_and_feeds_publish():
    jobs = _release()["jobs"]
    assert jobs["gate"]["permissions"]["actions"] == "read"
    assert "release_test_gate.py" in RELEASE
    assert set(jobs["publish"]["needs"]) == {"gate", "tests", "build"}
    condition = jobs["publish"]["if"]
    assert "needs.gate.result == 'success'" in condition
    assert "needs.build.result == 'success'" in condition
    assert "needs.tests.result == 'success'" in condition
    assert "needs.gate.outputs.tested == 'true'" in condition


def test_the_full_matrix_runs_only_when_the_gate_found_no_green_run():
    tests_job = _release()["jobs"]["tests"]
    assert tests_job["uses"] == "./.github/workflows/tests.yml"
    assert tests_job["needs"] == "gate"
    assert tests_job["if"] == "needs.gate.outputs.tested != 'true'"


def test_build_starts_without_waiting_for_the_gate_or_tests():
    assert "needs" not in _release()["jobs"]["build"]


def test_the_exact_wheel_is_smoke_tested_offline_before_upload():
    build = _release()["jobs"]["build"]
    names = [step.get("name", "") for step in build["steps"]]
    smoke = next(step for step in build["steps"] if step.get("name", "").startswith("Smoke"))
    assert names.index(smoke["name"]) < names.index("Preserve the reviewed artifacts")
    script = smoke["run"]
    assert 'dist/connectonion-${VERSION}-py3-none-any.whl' in script
    assert '/bin/co" --version' in script
    assert '/bin/co" --help' in script
    assert '/bin/co" init --yes' in script
    assert "HTTPS_PROXY=http://127.0.0.1:9" in script
    assert '"$VERSION"' in script


def test_finalize_runs_when_the_gate_skipped_the_tests():
    """A tested tag skips the tests job; a job with no `if` then inherits success(),
    which is false below a skipped ancestor. v1.9.3rc64 and v1.9.3 reached PyPI
    with no GitHub Release that way."""
    finalize_job = RELEASE.split("  finalize:", 1)[1].split("\n  ", 1)[0] + RELEASE.split("  finalize:", 1)[1][:600]
    assert "if: ${{ !cancelled()" in finalize_job
    assert "needs.publish.result == 'success'" in finalize_job
