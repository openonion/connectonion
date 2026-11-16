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


def test_exec_passes_own_turn_id_to_maintenance_children(tmp_path, monkeypatch):
    from connectonion.rem import codex_exec
    from connectonion.rem.files import maintenance_lock
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])

    def run(command, **kwargs):
        turn_id = kwargs['env']['CO_REM_TURN_ID']
        assert turn_id == read_json(state_path(tmp_path, 'last-turn.json'), {})['turn_id']
        monkeypatch.setenv('CO_REM_TURN_ID', turn_id)
        for operation in ('next', 'submit'):
            with maintenance_lock(tmp_path, operation=operation):
                owner = read_json(state_path(tmp_path, 'maintenance-owner.json'), {})
                assert owner['turn_id'] == turn_id
                assert owner['pid'] == os.getpid()
        return CompletedProcess(command, 0)

    assert codex_exec.run_turn(tmp_path, run=run) == 'completed'


@pytest.mark.parametrize('recovery', [None, 'not due', 'round done', 'task'])
def test_exec_records_preparation_error_even_when_codex_exits_zero(tmp_path, monkeypatch, recovery):
    import json
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.rem import codex_exec, native
    from connectonion.rem.config import prepare
    prepare(tmp_path)
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_schedule.CodexNative, 'recent_desktop_fire', lambda *a: False)

    def fail(root, **kwargs):
        raise PermissionError(13, 'Permission denied', '/outside/protected/.git')

    def run(command, **kwargs):
        monkeypatch.setenv('CO_REM_TURN_ID', kwargs['env']['CO_REM_TURN_ID'])
        monkeypatch.setattr(native, 'next_task', fail)
        failed = CliRunner().invoke(app, ['rem', '--root', str(tmp_path), 'next', '--scheduled', '--json'])
        assert failed.exit_code == 1
        assert 'Cannot read or write the selected co rem files' not in failed.output
        if recovery:
            value = {'outcome': 'task', 'id': 'fixture'} if recovery == 'task' else {'outcome': 'done', 'reason': recovery}
            monkeypatch.setattr(native, 'next_task', lambda *a, **kw: value)
            assert CliRunner().invoke(app, ['rem', '--root', str(tmp_path), 'next', '--json']).exit_code == 0
        return CompletedProcess(command, 0)

    expected = 'completed' if recovery else 'failed'
    assert codex_exec.run_turn(tmp_path, run=run) == expected
    receipt = read_json(state_path(tmp_path, 'last-turn.json'), {})
    assert receipt['result'] == expected and receipt['exit_code'] == 0
    assert read_json(state_path(tmp_path, f"turns/{receipt['turn_id']}.json"), {}) == receipt
    if not recovery:
        assert '/outside/protected/.git' in receipt['reason']
    events = [json.loads(line) for line in Path(receipt['log']).read_text().splitlines()]
    failure = next(event for event in events if event.get('type') == 'rem.preparation_failed')
    assert 'Traceback (most recent call last)' in failure['traceback']
    assert 'PermissionError' in failure['traceback'] and 'fail' in failure['traceback']


@pytest.mark.parametrize('reason', ['not due', 'round done', 'nothing to do'])
def test_exec_idle_preparation_is_completed(tmp_path, monkeypatch, reason):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.rem import codex_exec, native
    from connectonion.rem.config import prepare
    prepare(tmp_path)
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_schedule.CodexNative, 'recent_desktop_fire', lambda *a: False)
    monkeypatch.setattr(native, 'next_task', lambda *a, **kw: {'outcome': 'done', 'reason': reason})

    def run(command, **kwargs):
        monkeypatch.setenv('CO_REM_TURN_ID', kwargs['env']['CO_REM_TURN_ID'])
        result = CliRunner().invoke(app, ['rem', '--root', str(tmp_path), 'next', '--scheduled', '--json'])
        assert result.exit_code == 0
        return CompletedProcess(command, 0)

    assert codex_exec.run_turn(tmp_path, run=run) == 'completed'


def _turn_of(tmp_path, monkeypatch, commands):
    """One scheduled turn whose Codex session runs `commands` and exits 0."""
    from connectonion.rem import codex_exec
    from connectonion.rem.config import prepare
    prepare(tmp_path)
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_schedule.CodexNative, 'recent_desktop_fire', lambda *a: False)

    def run(command, **kwargs):
        monkeypatch.setenv('CO_REM_TURN_ID', kwargs['env']['CO_REM_TURN_ID'])
        for step in commands:
            step()
        return CompletedProcess(command, 0)

    outcome = codex_exec.run_turn(tmp_path, run=run)
    receipt = read_json(state_path(tmp_path, 'last-turn.json'), {})
    assert receipt['result'] == outcome and receipt['exit_code'] == 0
    return receipt


def _stalled_next(tmp_path, page='people/fixture.md'):
    """What a `co rem next` that passes its deadline leaves for its launcher before it exits 75."""
    from connectonion.rem import codex_exec
    return lambda: codex_exec.record_stall(tmp_path, f'preparing {page}: gathering codex sessions',
                                           {f'preparing {page}: gathering codex sessions': 598})


def _cli(tmp_path, monkeypatch, command, value):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.rem import native

    def invoke():
        monkeypatch.setattr(native, 'next_task' if command[0] == 'next' else 'submit', lambda *a, **kw: value)
        assert CliRunner().invoke(app, ['rem', '--json', '--root', str(tmp_path), *command]).exit_code in (0, 1)
    return invoke


def test_exec_turn_whose_every_next_passed_its_deadline_is_not_completed(tmp_path, monkeypatch):
    """11-16: three deadlines, nothing served, nothing submitted, and the receipt said completed, exit 0."""
    import json
    receipt = _turn_of(tmp_path, monkeypatch, [_stalled_next(tmp_path)] * 3)
    assert receipt['result'] == 'failed' and receipt['produced_nothing'] is True
    assert receipt['blocked'] is False
    assert receipt['reason'] == ('The turn produced nothing: co rem next passed its deadline 3 times, last while '
                                 'preparing people/fixture.md: gathering codex sessions; '
                                 'no task was served and nothing was submitted')
    stalls = [json.loads(line) for line in Path(receipt['log']).read_text().splitlines()]
    assert [event['type'] for event in stalls] == ['rem.preparation_stalled'] * 3
    assert stalls[0]['timings'] == {'preparing people/fixture.md: gathering codex sessions': 598}


def test_exec_turn_with_no_recorded_next_says_so_and_is_not_counted_as_empty(tmp_path, monkeypatch):
    """No record is not proof of an empty turn; the receipt says what is known."""
    from connectonion.rem import service
    receipt = _turn_of(tmp_path, monkeypatch, [])
    assert receipt['result'] == 'completed' and 'produced_nothing' not in receipt
    assert receipt['reason'] == 'No co rem next was recorded in this turn'
    assert service.schedule_failure(tmp_path) is None


@pytest.mark.parametrize('after', ['served', 'accepted', 'not due'])
def test_exec_turn_that_stalled_once_and_then_worked_or_had_nothing_due_is_completed(tmp_path, monkeypatch, after):
    task_id = 'native-' + '0' * 32
    then = {'served': _cli(tmp_path, monkeypatch, ['next', '--scheduled'], {'outcome': 'task', 'id': task_id}),
            'accepted': _cli(tmp_path, monkeypatch, ['submit', task_id], {'outcome': 'accepted', 'id': task_id}),
            'not due': _cli(tmp_path, monkeypatch, ['next', '--scheduled'], {'outcome': 'done', 'reason': 'not due'})}
    receipt = _turn_of(tmp_path, monkeypatch, [_stalled_next(tmp_path), then[after]])
    assert receipt['result'] == 'completed' and 'produced_nothing' not in receipt


def test_exec_turn_whose_only_submission_was_refused_and_last_next_stalled_is_not_completed(tmp_path, monkeypatch):
    task_id = 'native-' + '0' * 32
    refused = _cli(tmp_path, monkeypatch, ['submit', task_id], {'outcome': 'refused', 'reason': 'fixture'})
    receipt = _turn_of(tmp_path, monkeypatch, [refused, _stalled_next(tmp_path)])
    assert receipt['result'] == 'failed' and 'passed its deadline 1 time,' in receipt['reason']


def test_status_counts_turns_that_produced_nothing_and_idle_turns_end_the_count(tmp_path, monkeypatch):
    from rich.text import Text
    from connectonion.cli.commands.rem_status import _today, dashboard
    from connectonion.rem import service
    for _ in range(2):
        _turn_of(tmp_path, monkeypatch, [_stalled_next(tmp_path)])
    warning = service.schedule_failure(tmp_path)
    assert warning['failures'] == 2 and warning['empty'] == 2 and warning['code'] == 'repeated_failure'
    value = service.status(tmp_path)
    today = Text.from_markup('\n'.join(_today(tmp_path, value))).plain
    assert 'Background: the last 2 turns ran but produced nothing, since ' in today
    assert 'Last error: The turn produced nothing: co rem next passed its deadline 1 time, last while preparing' in today
    shown = Text.from_markup(dashboard(tmp_path, value, lambda arguments: 'co rem ' + ' '.join(arguments))).plain
    assert 'failed · exit 0' in shown and 'after fixing the cause' not in shown
    idle = _cli(tmp_path, monkeypatch, ['next', '--scheduled'], {'outcome': 'done', 'reason': 'not due'})
    assert _turn_of(tmp_path, monkeypatch, [idle])['result'] == 'completed'
    assert service.schedule_failure(tmp_path) is None


def test_exec_records_unhandled_preparation_failure(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.rem import codex_exec, native
    from connectonion.rem.config import prepare
    prepare(tmp_path)
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_schedule.CodexNative, 'recent_desktop_fire', lambda *a: False)

    def fail(root, **kwargs):
        raise RuntimeError('Fixture preparation failed unexpectedly')

    def run(command, **kwargs):
        monkeypatch.setenv('CO_REM_TURN_ID', kwargs['env']['CO_REM_TURN_ID'])
        monkeypatch.setattr(native, 'next_task', fail)
        result = CliRunner().invoke(app, ['rem', '--root', str(tmp_path), 'next', '--scheduled', '--json'])
        assert isinstance(result.exception, RuntimeError)
        return CompletedProcess(command, 0)

    assert codex_exec.run_turn(tmp_path, run=run) == 'failed'
    receipt = read_json(state_path(tmp_path, 'last-turn.json'), {})
    assert receipt['reason'] == 'Fixture preparation failed unexpectedly'
    assert 'RuntimeError' in Path(receipt['log']).read_text()


@pytest.mark.parametrize('parent,result,command,terminated', [
    (1, 'timed-out', 'co rem next --scheduled', True),
    (1, 'completed', 'co rem submit task-1', True),
    (123, 'timed-out', 'co rem next --scheduled', False),
    (1, 'running', 'co rem next --scheduled', False),
    (1, 'completed', 'unrelated-command', False),
])
def test_exec_reaps_only_orphan_maintenance_from_a_finished_turn(tmp_path, monkeypatch,
                                                               parent, result, command, terminated):
    import signal
    from unittest.mock import Mock
    from connectonion.rem import codex_exec
    from connectonion.rem.files import write_json
    write_json(state_path(tmp_path, 'maintenance-owner.json'),
               {'pid': 49443, 'operation': 'next', 'turn_id': 'old-turn'})
    write_json(state_path(tmp_path, 'turns/old-turn.json'),
               {'result': result, **({'finished_at': '2026-11-06T03:00:00Z'} if result != 'running' else {})})
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_exec.subprocess, 'run', lambda *a, **kw:
                        CompletedProcess(a, 0, f'{parent} {command}\n', ''))
    kill = Mock()
    monkeypatch.setattr(codex_exec.os, 'kill', kill)
    import fcntl
    with state_path(tmp_path, 'maintenance.lock').open('a') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert codex_exec.run_turn(tmp_path, run=lambda *a, **kw: CompletedProcess(a, 0)) == 'completed'
    receipt = read_json(state_path(tmp_path, 'last-turn.json'), {})
    if terminated:
        kill.assert_called_once_with(49443, signal.SIGKILL)
        assert '49443' in receipt['terminated_orphans'][0]
        assert command in receipt['terminated_orphans'][0]
    else:
        kill.assert_not_called()
        assert not receipt.get('terminated_orphans')


def test_exec_does_not_reap_stale_owner_when_maintenance_lock_is_free(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from connectonion.rem import codex_exec
    from connectonion.rem.files import write_json
    write_json(state_path(tmp_path, 'maintenance-owner.json'),
               {'pid': 49443, 'operation': 'next', 'turn_id': 'old-turn'})
    write_json(state_path(tmp_path, 'turns/old-turn.json'),
               {'result': 'completed', 'finished_at': '2026-11-06T03:00:00Z'})
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_exec.subprocess, 'run', lambda *a, **kw:
                        CompletedProcess(a, 0, '1 co rem next --scheduled\n', ''))
    kill = Mock()
    monkeypatch.setattr(codex_exec.os, 'kill', kill)
    assert codex_exec.run_turn(tmp_path, run=lambda *a, **kw: CompletedProcess(a, 0)) == 'completed'
    kill.assert_not_called()
