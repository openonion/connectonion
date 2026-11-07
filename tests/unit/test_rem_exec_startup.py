"""launchd's sparse environment must produce Codex argv without interactive imports."""
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

from connectonion.rem import codex_exec, codex_schedule, schedule
from connectonion.rem.config import default_config
from connectonion.rem.files import RemError, read_json, state_path


@pytest.mark.parametrize('custom_config', [False, True])
def test_exec_allows_only_the_account_directory_for_credential_refresh(tmp_path, monkeypatch, custom_config):
    monkeypatch.delenv('AGENT_CONFIG_PATH', raising=False)
    account = tmp_path / 'account config' if custom_config else Path.home() / '.co'
    if custom_config:
        monkeypatch.setenv('AGENT_CONFIG_PATH', str(account))
    monkeypatch.setattr(codex_exec, '_codex_command', lambda: ['codex'])
    monkeypatch.setattr(codex_schedule, 'automation_prompt', lambda root: 'prompt')
    command = codex_exec.exec_command(tmp_path / 'notebook', default_config(), last_message=tmp_path / 'last.md')
    assert [value for flag, value in zip(command, command[1:]) if flag == '--add-dir'] == [str(account)]


def test_exec_slow_start_still_runs_and_records_startup_time(tmp_path, monkeypatch):
    import signal
    import time
    setitimer = signal.setitimer

    def scaled_timer(which, seconds, interval=0):
        # Scale the startup bound only; preserve any caller's restored alarm.
        monkeypatch.setattr(signal, 'setitimer', setitimer)
        return setitimer(which, seconds / 100, interval)

    def slow_config(root):
        time.sleep(0.4)  # Longer than the old scaled 0.3s bound.
        return default_config()

    def run(command, **kwargs):
        receipt = read_json(state_path(tmp_path, 'last-turn.json'), {})
        assert receipt['result'] == 'running'
        assert receipt['started_codex_after_s'] >= 0.4
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(signal, 'setitimer', scaled_timer)
    monkeypatch.setattr(codex_exec, 'read_config', slow_config)
    monkeypatch.setattr(codex_exec, 'exec_command', lambda *a, **kw: ['codex', 'exec'])
    assert codex_exec.run_turn(tmp_path, run=run) == 'completed'
    receipt = read_json(state_path(tmp_path, 'last-turn.json'), {})
    assert receipt['started_codex_after_s'] >= 0.4
    assert read_json(next(state_path(tmp_path, 'turns').glob('*.json')), {}) == receipt


def test_exec_command_under_plist_environment_does_not_import_tools(tmp_path, monkeypatch):
    binary = tmp_path / 'bin with spaces' / 'codex'
    binary.parent.mkdir()
    binary.write_text('#!/bin/sh\nexit 0\n')
    binary.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('PATH', str(binary.parent) + os.pathsep + '/usr/bin:/bin')
    monkeypatch.delenv('CODEX_CMD', raising=False)
    monkeypatch.setattr(codex_schedule, 'desktop_timezone', lambda: 'UTC')
    config = default_config()
    config['schedule']['timezone'] = 'UTC'
    job = plistlib.loads(schedule.CodexExec().render(tmp_path, config).encode())
    assert job['EnvironmentVariables']['CODEX_CMD'] == str(binary)
    script = '''
import importlib.abc, json, sys
from pathlib import Path
class NoInteractiveTools(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'connectonion.useful_tools':
            raise AssertionError('scheduler startup imported the interactive tools package')
sys.meta_path.insert(0, NoInteractiveTools())
from connectonion.rem.codex_exec import exec_command
from connectonion.rem.config import default_config
print(json.dumps(exec_command(Path(sys.argv[1]), default_config(), last_message=Path('last.md'))))
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
                            env=job['EnvironmentVariables'], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    argv = json.loads(result.stdout)
    assert argv[:2] == [str(binary), 'exec']
    assert not {'connectonion.rem.codex_exec', 'caffeinate', 'python'} & set(argv)


@pytest.mark.parametrize('command', [
    '/usr/bin/caffeinate -i python -m connectonion.rem.codex_exec',
    f'{sys.executable} -m connectonion.rem.codex_exec',
    'python3', 'connectonion.rem.codex_exec',
])
def test_exec_rejects_launcher_recursion(tmp_path, monkeypatch, command):
    monkeypatch.setenv('CODEX_CMD', command)
    with pytest.raises(RemError, match='CODEX_CMD.*Codex CLI'):
        codex_exec.exec_command(tmp_path, default_config(), last_message=tmp_path / 'last.md')


def test_exec_cannot_start_records_the_reason_and_status_shows_it(tmp_path, monkeypatch):
    from connectonion.cli.commands import rem_status
    monkeypatch.setattr(codex_exec, 'read_config', lambda root: default_config())
    monkeypatch.setenv('CODEX_CMD', '/missing/codex')
    with pytest.raises(RemError, match='Codex CLI'):
        codex_exec.run_turn(tmp_path)
    receipt = read_json(state_path(tmp_path, 'last-turn.json'), {})
    assert receipt['result'] == 'failed'
    assert 'Codex CLI' in receipt['reason']
    assert receipt['finished_at']
    worker = schedule.CodexExec(run=lambda *a, **kw: subprocess.CompletedProcess(a, 1, '', ''))
    assert worker.describe(tmp_path)['last_turn'] == receipt
    # Render the real status with the unrelated notebook sections empty.
    monkeypatch.setattr('connectonion.rem.census.pages', lambda root: {})
    monkeypatch.setattr(rem_status, 'notebook', lambda *args: {})
    for name in ('_header', '_waiting', '_today', '_notebook', '_mailboxes', '_archive', '_budget', '_last_runs'):
        monkeypatch.setattr(rem_status, name, lambda *args: [])
    rendered = rem_status.dashboard(tmp_path, {'last_turn': receipt}, lambda args: 'co rem')
    from rich.text import Text
    assert receipt['reason'] in Text.from_markup(rendered).plain


def test_exec_failed_spawn_preserves_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_exec, 'read_config', lambda root: default_config())
    monkeypatch.setattr(codex_exec, 'exec_command', lambda *a, **kw: ['missing-codex'])
    def missing(*args, **kwargs):
        raise FileNotFoundError('Codex executable disappeared before spawn')
    with pytest.raises(FileNotFoundError):
        codex_exec.run_turn(tmp_path, run=missing)
    assert read_json(state_path(tmp_path, 'last-turn.json'), {})['reason'] == 'Codex executable disappeared before spawn'


@pytest.mark.parametrize('result, seconds', [
    ('running', 65.4), ('completed', 65.4), ('failed', 65.4), ('completed', 0), ('completed', None),
])
def test_exec_status_shows_startup_time(tmp_path, monkeypatch, result, seconds):
    from connectonion.cli.commands import rem_status
    from rich.text import Text
    receipt = {'result': result, 'started_at': '2026-11-07T00:00:00+00:00'}
    if seconds is not None:
        receipt['started_codex_after_s'] = seconds
    monkeypatch.setattr('connectonion.rem.census.pages', lambda root: {})
    monkeypatch.setattr(rem_status, 'notebook', lambda *args: {})
    for name in ('_header', '_waiting', '_today', '_notebook', '_mailboxes', '_archive', '_budget', '_last_runs'):
        monkeypatch.setattr(rem_status, name, lambda *args: [])
    rendered = Text.from_markup(rem_status.dashboard(tmp_path, {'last_turn': receipt}, lambda args: 'co rem')).plain
    if seconds is None:
        assert 'Codex startup' not in rendered
    else:
        assert f'Codex startup: {seconds:g}s' in rendered


def test_exec_module_records_environment_errors_before_config_import(tmp_path):
    home = tmp_path / 'home'
    (home / '.co').mkdir(parents=True)
    (home / '.co' / 'keys.env').write_text('invalid env line\n')
    env = {'HOME': str(home), 'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(Path.cwd())}
    result = subprocess.run([sys.executable, '-m', 'connectonion.rem.codex_exec', '--root', str(tmp_path)],
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    receipt = read_json(state_path(tmp_path, 'last-turn.json'), {})
    assert receipt['result'] == 'failed'
    assert 'invalid syntax' in receipt['reason']
    assert receipt['finished_at']


def test_exec_stalled_startup_has_a_failed_receipt_and_restores_alarm(tmp_path, monkeypatch):
    import signal
    previous = signal.getsignal(signal.SIGALRM)
    def stalled(root):
        signal.pause()
    monkeypatch.setattr(codex_exec, 'STARTUP_TIMEOUT_S', 0.05)
    monkeypatch.setattr(codex_exec, 'read_config', stalled)
    with pytest.raises(TimeoutError, match='could not start within 0.05 seconds'):
        codex_exec.run_turn(tmp_path)
    receipt = read_json(state_path(tmp_path, 'last-turn.json'), {})
    assert receipt['result'] == 'failed'
    assert 'could not start within 0.05 seconds' in receipt['reason']
    assert 'started_codex_after_s' not in receipt
    assert signal.getsignal(signal.SIGALRM) is previous


def test_exec_rejects_python_disguised_as_codex(tmp_path, monkeypatch):
    binary = tmp_path / 'codex'
    binary.symlink_to(sys.executable)
    monkeypatch.setenv('CODEX_CMD', str(binary))
    with pytest.raises(RemError, match='CODEX_CMD.*Codex CLI'):
        codex_exec.exec_command(tmp_path, default_config(), last_message=tmp_path / 'last.md')


def test_exec_turn_is_ephemeral_and_falls_back_to_the_app_bundled_cli(tmp_path, monkeypatch):
    from connectonion.rem import codex_exec
    bundled = tmp_path / 'codex'
    bundled.write_text('#!/bin/sh\n')
    bundled.chmod(0o755)
    monkeypatch.delenv('CODEX_CMD', raising=False)
    monkeypatch.setattr(codex_exec.shutil, 'which', lambda name: None)
    monkeypatch.setattr('connectonion.codex_cli.BUNDLED_CODEX', (Path('/missing/codex'), bundled))
    monkeypatch.setattr('connectonion.rem.codex_schedule.automation_prompt', lambda root: 'prompt')
    argv = codex_exec.exec_command(tmp_path, {'effort': 'medium', 'model': 'default'}, last_message=tmp_path / 'last.md')
    assert argv[0] == str(bundled)
    assert '--ephemeral' in argv
