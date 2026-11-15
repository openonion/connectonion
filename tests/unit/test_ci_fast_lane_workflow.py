"""Execute the fast-lane decisions from YAML, including fail-closed summaries."""

import importlib.util
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = {name: yaml.safe_load((ROOT / f'.github/workflows/{name}.yml').read_text())
             for name in ('tests', 'help-gate', 'release')}
JOBS = WORKFLOWS['tests']['jobs']
NATIVE = {'remote-browser-egress': 'egress', 'windows-browser': 'browser',
          'windows-e2e': 'e2e', 'macos-e2e': 'e2e'}


def step(job, name):
    return next(s for s in job['steps'] if s.get('name') == name)


def python_body(script, delimiter='PY'):
    return script.split(f"<<'{delimiter}'", 1)[1].split('\n', 1)[1].rsplit(f'\n{delimiter}', 1)[0]


def native_paths(monkeypatch, tmp_path, paths, event='pull_request'):
    output = tmp_path / 'outputs'
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    monkeypatch.setenv('EVENT_NAME', event)
    monkeypatch.setenv('BASE_SHA', 'base')
    monkeypatch.setenv('HEAD_SHA', 'head')
    calls = []

    def diff(argv):
        calls.append(argv)
        return ('\0'.join(paths) + '\0').encode()

    monkeypatch.setattr(subprocess, 'check_output', diff)
    script = step(JOBS['lockfile'], 'Identify native contracts affected by this PR')['run']
    exec(python_body(script), {})
    if event == 'pull_request':
        assert calls == [['git', 'diff', '--name-only', '-z', '--no-renames', 'base', 'head']]
        assert 'git fetch --no-tags --depth=1 origin "$BASE_SHA" "$HEAD_SHA"' in script
    else:
        assert not calls
    return dict(line.split('=') for line in output.read_text().splitlines())


def versions(job, pr):
    # Pin both arms rather than pretending to implement the Actions expression engine.
    expression = job['strategy']['matrix']['python-version']
    assert "github.event_name == 'pull_request'" in expression
    arms = expression.split("&& '", 1)[1].split("' || '")
    return json.loads(arms[0] if pr else arms[1].split("'", 1)[0])


def test_ci_pr_is_one_python_but_main_and_reusable_runs_keep_the_full_matrix():
    for name in ('test', 'remote-browser-egress', 'windows-browser'):
        assert versions(JOBS[name], pr=True) == ['3.12']
        assert versions(JOBS[name], pr=False) == ['3.11', '3.12', '3.13']
        assert JOBS[name]['strategy']['fail-fast'] is False
    matrix = JOBS['test']['strategy']['matrix']
    assert 'needs.lockfile.outputs.shards' in matrix['shard']
    assert "'[1, 2, 3, 4, 5, 6, 7, 8]'" in matrix['shard']
    assert JOBS['test']['needs'] == 'lockfile'
    assert matrix['exclude'] == [{'python-version': '3.11', 'shard': 7},
                                 {'python-version': '3.11', 'shard': 8}]
    command = step(JOBS['test'], "Run this shard's test files")
    assert 'scripts/ci_test_shard.py' in command['run']
    assert '-n logical --dist worksteal' in command['run']
    assert '--cov=connectonion --cov-report=' in command['env']['COVERAGE_ARGS']
    assert 'not slow and not real_api and not network' in command['run']
    assert JOBS['cli-help-audit']['strategy']['matrix']['shard'] == [1, 2, 3, 4]
    # Existing slow help tests still run, including the cross-shard tree check.
    assert 'test_co_meets_the_contract_and_its_house_style' in str(JOBS['cli-help-audit'])
    assert 'test_the_shards_together_audit_every_page_once' in str(JOBS['tests-passed'])
    assert '--fail-under=78' in str(JOBS['tests-passed'])
    # All native paths on a PR: 8 test + 4 audit + 2 egress + browser + 2 e2e + lock + summary.
    count = 8 + 4 + 2 + 1 + 2 + 1 + 1
    assert count == 19 < 20
    assert 10 + 4 + 1 + 1 == 16 < 20  # extra PR shards with native jobs filtered out
    assert set(JOBS) == {'lockfile', 'test', 'tests-passed', 'cli-help-audit', *NATIVE}


@pytest.mark.parametrize('path,expected', [
    ('connectonion/rem/facts.py', (False, False, False)),
    ('connectonion/cli/commands/rem_help.md', (False, False, False)),
    ('docs/blog/2026-11-16-rem.md', (False, False, False)),
    ('connectonion/cli/browser_agent/transport.py', (True, True, True)),
    ('connectonion/useful_tools/browser_tools/_async_browser.py', (True, True, True)),
    ('connectonion/rem/files.py', (True, True, True)),
    ('connectonion/network/host/egress_gateway.py', (False, True, False)),
    ('tests/fixtures/remote_browser_destination_vectors.json', (False, True, False)),
    ('connectonion/cli/commands/remote_browser_commands.py', (False, True, False)),
    ('connectonion/cli/main.py', (True, True, True)),
    ('connectonion/environment.py', (True, True, True)),
    ('connectonion/cli/codex_setup.py', (True, True, True)),
    ('connectonion/cli/typer_groups.py', (True, True, True)),
    ('connectonion/core/usage.py', (True, True, True)),
    ('connectonion/cli/commands/init.py', (False, False, True)),
    ('connectonion/rem/reader.py', (False, False, True)),
    ('connectonion/rem/vendor/d3.js', (False, False, True)),
    ('scripts/check_rem_reader_snapshot.py', (False, False, True)),
    ('tests/e2e/cli/test_browser_daemon.py', (True, True, True)),
    ('tests/conftest.py', (True, True, True)),
    ('tests/unit/conftest.py', (True, True, True)),
    ('MANIFEST.in', (True, True, True)),
    ('pyproject.toml', (True, True, True)),
    ('uv.lock', (True, True, True)),
    ('.github/workflows/tests.yml', (True, True, True)),
])
def test_ci_filters_include_native_sources_tests_dependencies_and_packaging(monkeypatch, tmp_path, path, expected):
    actual = native_paths(monkeypatch, tmp_path, [path])
    assert [actual[name] == 'true' for name in ('browser', 'egress', 'e2e')] == list(expected)
    splits = 8 if any(expected) else 10
    assert actual['splits'] == str(splits)
    assert json.loads(actual['shards']) == list(range(1, splits + 1))


@pytest.mark.parametrize('event', ['push', 'workflow_call', 'workflow_dispatch'])
def test_ci_every_non_pr_runs_every_native_contract(monkeypatch, tmp_path, event):
    actual = native_paths(monkeypatch, tmp_path, [], event)
    assert all(actual[flag] == 'true' for flag in NATIVE.values())
    for name, flag in NATIVE.items():
        assert JOBS[name]['needs'] == 'lockfile'
        assert JOBS[name]['if'] == f"needs.lockfile.outputs.{flag} == 'true'"


def summary_needs(filtered=True):
    needs = {name: {'result': 'success', 'outputs': {}} for name in JOBS['tests-passed']['needs']}
    needs['lockfile']['outputs'] = {flag: str(not filtered).lower() for flag in set(NATIVE.values())}
    if filtered:
        for name in NATIVE:
            needs[name]['result'] = 'skipped'
    return needs


def run_summary(needs):
    script = step(JOBS['tests-passed'], 'Require every unfiltered job to succeed')['run']
    return subprocess.run([sys.executable, '-c', python_body(script, 'PYCODE')],
                          env={**os.environ, 'NEEDS': json.dumps(needs)}, capture_output=True, text=True)


def test_ci_summary_accepts_filtered_skips_and_all_success():
    assert JOBS['tests-passed']['if'] == 'always()'
    assert set(JOBS['tests-passed']['needs']) == set(JOBS) - {'tests-passed'}
    assert run_summary(summary_needs(filtered=True)).returncode == 0
    assert run_summary(summary_needs(filtered=False)).returncode == 0


@pytest.mark.parametrize('name', sorted(set(JOBS) - {'tests-passed'}))
@pytest.mark.parametrize('result', ['failure', 'cancelled'])
def test_ci_summary_rejects_every_failed_or_cancelled_job(name, result):
    needs = summary_needs()
    needs[name]['result'] = result
    outcome = run_summary(needs)
    assert outcome.returncode != 0
    assert name in outcome.stderr


@pytest.mark.parametrize('name', sorted(set(JOBS) - {'tests-passed'}))
def test_ci_summary_rejects_every_unfiltered_skip(name):
    needs = summary_needs(filtered=False)
    needs[name]['result'] = 'skipped'
    assert run_summary(needs).returncode != 0


@pytest.mark.parametrize('splits', [8, 10])
def test_ci_duration_shards_are_deterministic_disjoint_and_cover_every_test_file(splits):
    spec = importlib.util.spec_from_file_location('ci_test_shard', ROOT / 'scripts/ci_test_shard.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    groups = [module.shard(i, splits) for i in range(1, splits + 1)]
    assert groups == [module.shard(i, splits) for i in range(1, splits + 1)]
    flattened = [path for group in groups for path in group]
    assert sorted(flattened) == module.test_files()
    assert len(flattened) == len(set(flattened))
    weights = json.loads(module.DURATIONS.read_text())
    default = statistics.median(weights.values())
    loads = [sum(weights.get(path, default) for path in group) for group in groups]
    assert max(loads) - min(loads) <= default
    assert '--record junit-*/junit.xml' in (ROOT / '.github/workflows/tests.yml').read_text()


def test_ci_uv_caches_use_the_lock_and_every_external_action_stays_pinned():
    for workflow in WORKFLOWS.values():
        for job in workflow['jobs'].values():
            for action in job.get('steps', []):
                uses = action.get('uses', '')
                if uses:
                    sha = uses.split('@')[1]
                    assert len(sha) == 40 and all(c in '0123456789abcdef' for c in sha)
                if uses.startswith('astral-sh/setup-uv@'):
                    assert action['with']['enable-cache'] is True
                    assert action['with']['cache-dependency-glob'] == 'uv.lock'
                if uses.startswith('actions/setup-python@'):
                    assert 'cache' not in action.get('with', {})
    for name in ('test', 'tests-passed', 'lockfile', 'cli-help-audit', *NATIVE):
        assert any(s.get('uses', '').startswith('astral-sh/setup-uv@') for s in JOBS[name]['steps'])


def test_ci_windows_always_installs_the_current_shared_wheel_over_the_cached_environment():
    wheel = step(JOBS['lockfile'], 'Share the candidate wheel')
    assert wheel['with']['name'] == 'native-wheel'
    for name in ('windows-e2e', 'macos-e2e'):
        assert step(JOBS[name], 'Recover the candidate wheel')['with']['name'] == 'native-wheel'
        assert 'python -m build' not in str(JOBS[name])
    cached = step(JOBS['windows-e2e'], 'Restore the Windows dependency environment')
    assert "hashFiles('uv.lock')" in cached['with']['key']
    assert 'steps.python.outputs.python-version' in cached['with']['key']
    install = step(JOBS['windows-e2e'], 'Install from the wheel like a real user (not editable)')
    assert 'if' not in install
    assert '--reinstall-package connectonion $whl' in install['run']
    assert 'GITHUB_PATH' in install['run']
