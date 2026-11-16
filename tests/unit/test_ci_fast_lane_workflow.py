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
PR_SHARDS = 10
NATIVE = {'remote-browser-egress': 'egress', 'windows-browser': 'browser',
          'windows-e2e': 'e2e', 'windows-first-run': 'e2e', 'windows-rem-reader': 'reader',
          'macos-e2e': 'e2e'}


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
    pr, full = matrix['shard'].split("&& '", 1)[1].split("' || '")
    assert json.loads(pr) == list(range(1, PR_SHARDS + 1))
    assert json.loads(full.split("'", 1)[0]) == [1, 2, 3, 4, 5, 6, 7, 8]
    count = f"github.event_name == 'pull_request' && {PR_SHARDS} || matrix.python-version == '3.11' && 6 || 8"
    assert count in JOBS['test']['name']
    assert count in step(JOBS['test'], "Run this shard's test files")['env']['SHARD_COUNT']
    # No shard waits for another job: the lock check gates the summary, not the start.
    assert 'needs' not in JOBS['test'] and 'needs' not in JOBS['cli-help-audit']
    assert 'lockfile' in JOBS['tests-passed']['needs']
    assert matrix['exclude'] == [{'python-version': '3.11', 'shard': 7},
                                 {'python-version': '3.11', 'shard': 8}]
    command = step(JOBS['test'], "Run this shard's test files")
    # Four processes a job, each a shard of its own: no xdist worker collects another's files.
    assert 'scripts/ci_test_shard.py $(( (SHARD - 1) * 4 + part )) $(( SHARD_COUNT * 4 ))' in command['run']
    assert 'for part in 1 2 3 4' in command['run'] and '--dist' not in command['run']
    # A background command without job control ignores SIGINT, and so does every test's child.
    assert command['run'].index('set -m') < command['run'].index('pytest $(')
    assert 'wait "${pids[part - 1]}" || failed=1' in command['run'] and command['run'].rstrip().endswith('exit "$failed"')
    assert 'COVERAGE_FILE="$COVERAGE_DATA-$part"' in command['run']
    assert step(JOBS['test'], "Upload this shard's coverage data")['with']['path'] == '.coverage.shard-${{ matrix.shard }}-*'
    assert '--cov=connectonion --cov-report=' in command['env']['COVERAGE_ARGS']
    assert 'not slow and not real_api and not network' in command['run']
    assert JOBS['cli-help-audit']['strategy']['matrix']['shard'] == [1, 2, 3, 4]
    # Existing slow help tests still run, including the cross-shard tree check.
    assert 'test_co_meets_the_contract_and_its_house_style' in str(JOBS['cli-help-audit'])
    assert 'test_the_shards_together_audit_every_page_once' in str(JOBS['tests-passed'])
    assert '--fail-under=78' in str(JOBS['tests-passed'])
    # A PR with every native path filtered out stays under the 20 jobs the plan
    # runs at once, with room for CodeQL, blog-gate and triage beside it:
    # 10 test + 4 audit + lock, then the summary. Native jobs start after lockfile.
    assert PR_SHARDS + 4 + 1 == 15 < 20
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
    ('connectonion/rem/reader.py', (False, False, False)),
    ('connectonion/rem/service.py', (False, False, False)),
    ('connectonion/rem/vendor/d3.js', (False, False, False)),
    ('scripts/check_rem_reader_snapshot.py', (False, False, False)),
    ('docs/.package-ignore', (False, False, True)),
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
    assert set(actual) == {'browser', 'egress', 'e2e', 'reader'}
    # The reader's Windows snapshot runs for its own files and wherever the wheel jobs run.
    own = path.startswith(('connectonion/rem/reader', 'connectonion/rem/service.py',
                           'connectonion/rem/vendor/', 'scripts/check_rem_reader_snapshot.py'))
    assert (actual['reader'] == 'true') == (expected[2] or own)


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


def shard_module():
    spec = importlib.util.spec_from_file_location('ci_test_shard', ROOT / 'scripts/ci_test_shard.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('splits', [6 * 4, 8 * 4, PR_SHARDS * 4])
def test_ci_duration_shards_are_deterministic_balanced_and_run_every_test_file_once(splits):
    module = shard_module()
    groups = [module.shard(i, splits) for i in range(1, splits + 1)]
    assert groups == [module.shard(i, splits) for i in range(1, splits + 1)]
    weights = json.loads(module.DURATIONS.read_text())
    default = statistics.median(weights.values())
    cut, loads = {}, []
    for group in groups:
        files = [arg for arg in group if not arg.startswith('--')]
        mine = {}
        for arg in group:
            if arg.startswith('--file-part='):
                name, part = arg.split('=', 1)[1].rsplit(':', 1)
                assert name in files  # a part is useless without its file on the command line
                index, of = map(int, part.split('/'))
                cut.setdefault(name, []).append((index, of))
                mine[name] = mine.get(name, 0) + 1 / of
        loads.append(sum((weights.get(path) or default) * mine.get(path, 1) for path in files))
    # Every file is listed; an uncut file by exactly one shard, a cut one by its parts' shards.
    listed = [path for group in groups for path in group if not path.startswith('--')]
    assert sorted(set(listed)) == module.test_files()
    assert all(listed.count(path) == 1 for path in set(listed) - set(cut))
    for name, parts in cut.items():
        of = parts[0][1]
        assert sorted(parts) == [(index, of) for index in range(1, of + 1)], name
    assert max(loads) - min(loads) <= default
    # No file, whole or in parts, is heavier than half of an even share.
    share = sum(weights.get(path) or default for path in module.test_files()) / splits
    assert all((weights.get(path) or default) / len(cut.get(path, [1])) <= share / 2 + 0.01
               for path in module.test_files())
    assert cut  # today's suite has files this heavy; without them the option goes untested
    assert '--record junit-*/junit-*.xml' in (ROOT / '.github/workflows/tests.yml').read_text()


def test_ci_parts_of_a_cut_file_run_each_of_its_tests_exactly_once(tmp_path):
    # The real hook from tests/conftest.py, in a throwaway project that real pytest collects.
    source = (ROOT / 'tests/conftest.py').read_text()
    hook = source[source.index('def pytest_addoption'):source.index('def pytest_collection_modifyitems')]
    (tmp_path / 'conftest.py').write_text(hook + 'def pytest_collection_modifyitems(config, items):\n'
                                          '    _keep_file_parts(config, items)\n')
    cases = ''.join(f'def test_{letter}(): pass\n' for letter in 'abcdefg')
    (tmp_path / 'test_cut.py').write_text('import pytest\n@pytest.mark.parametrize("n", [1, 2, 3])\n'
                                          'def test_many(n): pass\n' + cases)
    (tmp_path / 'test_whole.py').write_text('def test_kept(): pass\n')

    def collected(*parts):
        done = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider',
                               'test_cut.py', 'test_whole.py',
                               *[f'--file-part=test_cut.py:{part}' for part in parts]],
                              cwd=tmp_path, capture_output=True, text=True)
        assert done.returncode == 0, done.stdout + done.stderr
        return sorted(line for line in done.stdout.splitlines() if '::' in line)

    whole = collected()
    assert len(whole) == 11
    parts = [collected(f'{index}/3') for index in (1, 2, 3)]
    assert sorted(test for part in parts for test in part if 'test_cut' in test) == whole[:10]
    assert all('test_whole.py::test_kept' in part for part in parts)  # other files are untouched
    assert all(3 <= len(part) - 1 <= 4 for part in parts)
    assert collected('1/3', '3/3') == sorted(set(parts[0]) | set(parts[2]))  # two parts in one shard


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
    assert all(step(JOBS['lockfile'], name)['if'] == "steps.paths.outputs.reader == 'true'"
               for name in ('Build the native candidate wheel once', 'Share the candidate wheel'))
    for name in ('windows-e2e', 'windows-first-run', 'windows-rem-reader', 'macos-e2e'):
        assert step(JOBS[name], 'Recover the candidate wheel')['with']['name'] == 'native-wheel'
        assert 'python -m build' not in str(JOBS[name])
    for name in ('windows-e2e', 'windows-first-run', 'windows-rem-reader'):
        cached = step(JOBS[name], 'Restore the Windows dependency environment')
        assert "hashFiles('uv.lock')" in cached['with']['key']
        assert 'steps.python.outputs.python-version' in cached['with']['key']
        install = step(JOBS[name], 'Install from the wheel like a real user (not editable)')
        assert 'if' not in install
        assert '--reinstall-package connectonion $whl' in install['run']
        assert 'GITHUB_PATH' in install['run']


def test_ci_the_windows_jobs_together_keep_every_real_user_step():
    # windows-e2e was one job of 158 s; its steps are split, none dropped.
    names = [s['name'].split(' — ')[0].split(' (')[0]
             for name in ('windows-e2e', 'windows-first-run', 'windows-rem-reader')
             for s in JOBS[name]['steps'] if 'run' in s]
    assert sorted(set(names)) == sorted([
        'Install from the wheel like a real user', 'CLI is discoverable from a plain shell',
        'CLI works from cmd.exe too', 'REM reader opens its private snapshot on Windows',
        'First run OFFLINE is graceful', 'patchright CLI is included and runnable',
        'Package data survives the wheel', 'Real co browser end-to-end', 'Parallel agents',
        'Restart after close', 'Fresh laptop', 'Restore system Chrome',
        'CLI works from Windows PowerShell 5.1', 'Everything works with a CJK + space home directory',
        'Subprocess tools survive the Chinese', 'Stale pid file with a recycled live pid cannot brick the daemon',
        'Corrupt authkey self-heals', 'Show the browser daemon log on failure'])
    # The daemon steps reuse one another's daemon, so they stay in one job and in order.
    daemon = [s['name'].split(' — ')[0] for s in JOBS['windows-e2e']['steps']]
    assert daemon.index('Real co browser end-to-end') < daemon.index('Parallel agents') < daemon.index('Restart after close')
