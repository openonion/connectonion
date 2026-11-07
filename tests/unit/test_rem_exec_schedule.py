"""Unattended turns use the same prompt and clock as the desktop path."""
import os
import pytest
import plistlib
from pathlib import Path
from subprocess import CompletedProcess

from connectonion.rem import codex_schedule, schedule
from connectonion.rem.config import default_config
from connectonion.rem.files import read_json, state_path

pytestmark = pytest.mark.usefixtures("rem_clock")


@pytest.fixture(autouse=True)
def codex_cli(tmp_path, monkeypatch):
    binary = tmp_path / "fictional-codex"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o700)
    monkeypatch.setenv("CODEX_CMD", str(binary))
    return binary


def test_exec_plist_shares_prompt_fire_times_and_user_path(tmp_path, monkeypatch):
    monkeypatch.setenv('PATH', '/fictional/local/bin:/usr/bin:/bin')
    config = default_config()
    config['schedule'].update(runner='codex-exec', timezone='UTC', times=['03:00', '17:00'])
    monkeypatch.setattr(codex_schedule, 'desktop_timezone', lambda: 'UTC')
    monkeypatch.setattr('shutil.which', lambda name: '/fictional/local/bin/codex')
    config['effort'] = 'high'
    job = plistlib.loads(schedule.CodexExec().render(tmp_path, config).encode())
    assert job['StartCalendarInterval'] == [dict(zip(('Hour', 'Minute'), map(int, t.split(':'))))
                                           for t in codex_schedule.fire_times(config)]
    assert '/fictional/local/bin' in job['EnvironmentVariables']['PATH']
    assert 'connectonion.rem.codex_exec' in job['ProgramArguments']
    from connectonion.rem.codex_exec import exec_command
    command = exec_command(tmp_path, config, last_message=tmp_path / 'last.md')
    assert command[1] == 'exec'
    assert command[command.index('-m') + 1] == config['model']
    assert 'model_reasoning_effort=high' in command
    assert command[command.index('-s') + 1] == 'workspace-write'
    assert ('-c', 'sandbox_workspace_write.network_access=true') in list(zip(command, command[1:]))
    assert command[-1] == codex_schedule.automation_prompt(tmp_path)


def test_exec_turn_lock_blocks_overlapping_fire(tmp_path, monkeypatch):
    from connectonion.rem import codex_exec
    from connectonion.rem.files import atomic_write
    atomic_write(tmp_path / 'config.yaml', 'unused')
    config = default_config()
    monkeypatch.setattr(codex_exec, 'read_config', lambda root: config)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs['stdin'] is not None
        assert len(kwargs['pass_fds']) == 1
        assert codex_exec.run_turn(tmp_path, run=run) == 'busy'
        return CompletedProcess(command, 0)

    assert codex_exec.run_turn(tmp_path, run=run) == 'completed'
    assert len(calls) == 1
    result = read_json(state_path(tmp_path, 'last-turn.json'), {})
    assert result['result'] == 'completed' and result['exit_code'] == 0
    assert result['killed_descendants'] == 0
    assert Path(result['log']).is_file()


def test_exec_status_reports_mode_and_last_turn(tmp_path, monkeypatch):
    from connectonion.rem.files import write_json
    write_json(state_path(tmp_path, 'last-turn.json'), {'result': 'failed', 'exit_code': 7})
    scheduler = schedule.CodexExec(run=lambda *a, **kw: CompletedProcess(a, 1, '', ''))
    assert scheduler.describe(tmp_path)['runner'] == 'codex-exec'
    assert scheduler.describe(tmp_path)['last_turn']['exit_code'] == 7


def test_start_exec_pauses_desktop_registration_and_removes_wake(tmp_path, monkeypatch):
    from connectonion.rem import service
    from connectonion.rem.config import prepare, set_config
    from connectonion.rem.files import write_json
    monkeypatch.setattr(codex_schedule, 'desktop_timezone', lambda: 'UTC')
    monkeypatch.setattr('connectonion.rem.runner.ready', lambda config: ('', ''))
    monkeypatch.setattr('connectonion.rem.codex_history.archive_history', lambda *a, **kw: {})
    root = tmp_path / 'notebook'
    prepare(root)
    set_config(root, ['schedule.runner', 'codex-exec', 'schedule.timezone', 'UTC'])
    write_json(state_path(root, 'consent.json'), service.consent_summary(root))
    scheduler = schedule.CodexExec(agents_dir=tmp_path / 'agents', run=lambda *a, **kw: CompletedProcess(a, 0, '', ''))
    home = tmp_path / 'codex'
    monkeypatch.setenv('CODEX_HOME', str(home))
    native = codex_schedule.CodexNative(home, launcher=scheduler)
    native._write(root, {'id': codex_schedule.automation_id(root), 'cwds': [str(root)], 'status': 'PAUSED'})
    scheduler._write_plist(scheduler.wake_path(root), plistlib.dumps({'Label': 'fictional-wake'}).decode())
    result = service.start(root, confirm=lambda summary: True, scheduler=scheduler, run_first_batch=False)
    assert result['runner'] == 'codex-exec'
    assert scheduler.plist_path(root).is_file()
    assert not scheduler.wake_path(root).exists()
    assert native.definition(root)['status'] == 'PAUSED'


def test_app_install_removes_exec_job_and_installs_wake(tmp_path, monkeypatch):
    config = default_config()
    config['schedule'].update(runner='codex-app', timezone='UTC')
    monkeypatch.setattr(codex_schedule, 'desktop_timezone', lambda: 'UTC')
    root = tmp_path / 'notebook'
    scheduler = schedule.CodexExec(agents_dir=tmp_path / 'agents', run=lambda *a, **kw: CompletedProcess(a, 1, '', ''))
    scheduler._write_plist(scheduler.plist_path(root), scheduler.render(root, config))
    native = codex_schedule.CodexNative(tmp_path / 'codex', launcher=scheduler)
    monkeypatch.setattr(native, '_app_running', lambda: True)
    monkeypatch.setattr(native, '_open_desktop', lambda: None)
    monkeypatch.setattr(native, '_wait_for_definition', lambda *args: True)
    monkeypatch.setattr(codex_schedule, 'desktop_app', lambda: Path('/Applications/Codex.app'))
    monkeypatch.setattr(scheduler, '_load', lambda path: None)
    result = native.install(root, config)
    assert result['runner'] == 'codex-app'
    assert native.definition(root)['status'] == 'ACTIVE'
    assert not scheduler.plist_path(root).exists()
    assert scheduler.wake_path(root).is_file()


def test_default_runner_prefers_ready_exec_and_effort_is_saved(tmp_path, monkeypatch):
    from connectonion.rem.config import prepare, read_config, set_config
    monkeypatch.setattr('sys.platform', 'darwin')
    monkeypatch.setattr('connectonion.rem.runner.ready', lambda config: ('', ''))
    monkeypatch.setattr(codex_schedule, 'app_installed', lambda: True)
    prepare(tmp_path)
    assert isinstance(schedule.default_scheduler(tmp_path, for_start=True), schedule.CodexExec)
    set_config(tmp_path, ['effort', 'high', 'schedule.runner', 'codex-app'])
    assert read_config(tmp_path)['effort'] == 'high'
    monkeypatch.setattr(codex_schedule, 'desktop_timezone', lambda: 'UTC')
    assert isinstance(schedule.default_scheduler(tmp_path, for_start=True), codex_schedule.CodexNative)


def test_exec_failed_spawn_records_failure_and_releases_lock(tmp_path, monkeypatch):
    from connectonion.rem import codex_exec
    monkeypatch.setattr(codex_exec, 'read_config', lambda root: default_config())
    monkeypatch.setattr(codex_exec, 'exec_command', lambda *a, **kw: ['missing-codex'])

    def missing(*args, **kwargs):
        raise FileNotFoundError('fictional missing executable')

    with pytest.raises(FileNotFoundError):
        codex_exec.run_turn(tmp_path, run=missing)
    assert read_json(state_path(tmp_path, 'last-turn.json'), {})['result'] == 'failed'
    assert codex_exec.run_turn(tmp_path, run=lambda *a, **kw: CompletedProcess(a, 0)) == 'completed'


def test_child_retains_lock_when_launch_wrapper_exits(tmp_path):
    """A detached child must own the same lock even after its launcher closes it."""
    import fcntl
    import subprocess
    import sys
    from connectonion.rem.codex_exec import run_turn
    lock = state_path(tmp_path, 'exec-turn.lock')
    lock.parent.mkdir(exist_ok=True)
    with lock.open('a') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        child = subprocess.Popen([sys.executable, '-c',
            'import sys; sys.stdin.read()'],
            stdin=subprocess.PIPE, pass_fds=(held.fileno(),))
    try:
        assert run_turn(tmp_path) == 'busy'
    finally:
        child.communicate(b'finish', timeout=5)


def test_legacy_runner_uses_default_without_ready_cli(tmp_path, monkeypatch):
    import yaml
    from connectonion.rem.config import read_config, set_config
    monkeypatch.setattr(codex_schedule, 'app_installed', lambda: True)
    monkeypatch.setattr('connectonion.rem.runner.ready', lambda config: ('Codex is not signed in', 'codex login'))
    config = default_config()
    config['schedule'].pop('runner')
    (tmp_path / 'config.yaml').write_text(yaml.safe_dump(config))
    assert read_config(tmp_path)['schedule']['runner'] == default_config()['schedule']['runner'] == 'codex-exec'
    set_config(tmp_path, ['schedule.runner', 'codex-app'])
    assert read_config(tmp_path)['schedule']['runner'] == 'codex-app'


@pytest.mark.parametrize('code, outcome, reason', [
    (7, 'failed', None),
    (124, 'timed-out', 'Turn exceeded 3 hours; the next fire continues the round'),
])
def test_exec_nonzero_turn_result_is_durable(tmp_path, monkeypatch, code, outcome, reason):
    from connectonion.rem import codex_exec
    monkeypatch.setattr(codex_exec, 'read_config', lambda root: default_config())
    monkeypatch.setattr(codex_exec, 'exec_command', lambda *a, **kw: ['fictional-codex', 'exec'])
    result = CompletedProcess(['fictional-codex', 'exec'], code)
    result.killed_descendants = 2 if code == 124 else 0
    assert codex_exec.run_turn(tmp_path, run=lambda *a, **kw: result) == outcome
    receipt = read_json(state_path(tmp_path, 'last-turn.json'), {})
    assert receipt['result'] == outcome and receipt['exit_code'] == code
    assert receipt.get('reason') == reason
    assert receipt['killed_descendants'] == result.killed_descendants
    receipts = list(state_path(tmp_path, 'turns').glob('*.json'))
    assert len(receipts) == 1
    assert read_json(receipts[0], {}) == receipt


def test_exec_deadline_is_three_hours_and_kills_the_process_group(monkeypatch):
    import signal
    import subprocess
    from unittest.mock import MagicMock, call
    from connectonion.rem import codex_exec
    command = ['fictional-codex', 'exec']
    process = MagicMock(pid=123)
    process.wait.side_effect = [subprocess.TimeoutExpired(command, 3 * 3600), -signal.SIGKILL]
    popen = MagicMock()
    popen.return_value.__enter__.return_value = process
    killpg = MagicMock()
    monkeypatch.setattr(codex_exec.subprocess, 'Popen', popen)
    monkeypatch.setattr(codex_exec.os, 'killpg', killpg)
    monkeypatch.setattr(codex_exec, '_terminate_descendants', lambda pid: 0)

    assert codex_exec._execute(command).returncode == 124
    popen.assert_called_once_with(command, start_new_session=True)
    assert process.wait.call_args_list == [call(timeout=3 * 3600), call()]
    killpg.assert_called_once_with(process.pid, signal.SIGKILL)


def test_exec_descendants_are_terminated_deepest_first(monkeypatch):
    import signal
    from unittest.mock import Mock, call
    from connectonion.rem import codex_exec

    table = CompletedProcess(['ps'], 0, '30 20\n10 1\n20 10\n40 1\n')
    monkeypatch.setattr(codex_exec.subprocess, 'run', lambda *a, **kw: table)
    kill = Mock(side_effect=[None, None, ProcessLookupError(), None])
    monkeypatch.setattr(codex_exec.os, 'kill', kill)
    monkeypatch.setattr(codex_exec.time, 'sleep', lambda seconds: None)

    assert codex_exec._terminate_descendants(10) == 2
    assert kill.call_args_list == [call(30, signal.SIGTERM), call(20, signal.SIGTERM),
                                   call(30, signal.SIGKILL), call(20, signal.SIGKILL)]


@pytest.mark.skipif(os.name == 'nt', reason='POSIX sessions and signals')
@pytest.mark.parametrize('ignore_term', [False, True])
def test_exec_deadline_kills_detached_grandchild(tmp_path, ignore_term):
    import subprocess
    import sys
    import time
    from connectonion.rem.codex_exec import _execute

    pid_file = tmp_path / 'grandchild.pid'
    grandchild = (
        'import os, signal, time; from pathlib import Path; '
        f'signal.signal(signal.SIGTERM, {"signal.SIG_IGN" if ignore_term else "signal.SIG_DFL"}); '
        f'Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(60)'
    )
    child = (
        'import subprocess, sys, time; '
        f'process = subprocess.Popen([sys.executable, "-c", {grandchild!r}], start_new_session=True); '
        'process.wait(); time.sleep(60)'
    )
    try:
        result = _execute([sys.executable, '-c', child], timeout=0.5)
        assert result.returncode == 124
        pid = int(pid_file.read_text())
        for _ in range(100):
            status = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='],
                                    capture_output=True, text=True).stdout.strip()
            # A zombie has exited and released its locks, but awaits reaping.
            if not status or status.startswith('Z'):
                break
            time.sleep(0.01)
        assert not status or status.startswith('Z'), f'grandchild {pid} survived: {status}'
        assert result.killed_descendants == 1
    finally:
        if pid_file.exists():
            # The red test must not leave its deliberately detached sleeper behind.
            subprocess.run(['kill', '-KILL', pid_file.read_text()], capture_output=True)


def test_saved_scheduler_choice_does_not_probe_cli_on_read(tmp_path, monkeypatch):
    import yaml
    from connectonion.rem.config import read_config
    config = default_config()
    config['schedule']['runner'] = 'codex-exec'
    (tmp_path / 'config.yaml').write_text(yaml.safe_dump(config))

    def no_probe(config):
        raise AssertionError('A saved configuration must be readable without probing a runner')

    monkeypatch.setattr('connectonion.rem.runner.ready', no_probe)
    assert read_config(tmp_path)['schedule']['runner'] == 'codex-exec'


def test_exec_turn_skips_recent_desktop_fire_with_durable_receipt(tmp_path, monkeypatch):
    from connectonion.rem import codex_exec
    monkeypatch.setattr(codex_schedule.CodexNative, 'recent_desktop_fire', lambda *a: True)
    def no_spawn(*args, **kwargs):
        pytest.fail('Desktop fire must prevent another Codex turn')
    assert codex_exec.run_turn(tmp_path, run=no_spawn) == 'skipped'
    receipt = read_json(state_path(tmp_path, 'last-turn.json'), {})
    assert receipt['result'] == 'skipped'
    assert 'desktop automation' in receipt['reason']
