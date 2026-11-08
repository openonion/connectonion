"""Obligation work leaves evidence, never messages or a narrative-only completion."""
import json
import os
import time
from pathlib import Path

import pytest

from connectonion.rem import night, runner
from connectonion.rem.config import default_config, prepare, read_config, set_config
from connectonion.rem.files import RemError, Notebook, read_json, state_path, write_json


@pytest.fixture
def task_notebook(tmp_path, monkeypatch, rem_clock):
    root = tmp_path / 'rem'
    prepare(root)
    set_config(root, ["runner", "codex", "model", default_config()["model"]])
    book = Notebook(root)
    book.stub_project('projects/pilot.md', 'Mara pilot', [])
    book.write('projects/pilot.md', book.read('projects/pilot.md').replace(
        '## Open threads\n', '## Open threads\n- You owe Mara a pilot review.\n'))
    night.prepare(root, read_config(root))
    assert night.listing(root)[0]['kind'] == 'task'
    return root


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    path = tmp_path / 'codex-fake'
    path.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
last = pathlib.Path(args[args.index('-o') + 1])
(last.parent / 'argv.json').write_text(json.dumps(args))
last.write_text('Reviewed the Mara pilot.')
if os.environ.get('TASK_FAKE_SLEEP'):
    time.sleep(float(os.environ['TASK_FAKE_SLEEP']))
if not os.environ.get('TASK_FAKE_MISSING'):
    (last.parent / 'result.md').write_text('# Mara pilot review\\nReady for owner review.\\n')
sys.exit(int(os.environ.get('TASK_FAKE_EXIT', '0')))
''')
    path.chmod(0o700)
    monkeypatch.setenv('CODEX_CMD', str(path))
    return path


def test_native_cleanup_keeps_obligation_work_even_when_old(tmp_path):
    directory = tmp_path / 'do-mara'
    directory.mkdir()
    deliverable = directory / 'result.md'
    deliverable.write_text('Mara pilot review')
    write_json(directory / 'receipt.json', {'result': 'completed'})
    os.utime(directory, (1, 1))
    runner.scrub_finished_tasks(tmp_path)
    runner.scrub_task(directory)
    assert deliverable.read_text() == 'Mara pilot review'
    assert (directory / 'receipt.json').is_file()


@pytest.mark.parametrize('exit_code,missing,expected', [(0, False, 'completed'), (1, False, 'failed'), (0, True, 'failed')])
def test_one_codex_session_receipts_and_honest_completion(task_notebook, fake_codex, monkeypatch, exit_code, missing, expected):
    from connectonion.rem import tasks
    root = task_notebook
    monkeypatch.setenv('TASK_FAKE_EXIT', str(exit_code))
    if missing:
        monkeypatch.setenv('TASK_FAKE_MISSING', '1')
    outcome = night.listing(root)[0]
    receipt = tasks.reserve(root, outcome)
    tasks.execute(root, receipt['id'])
    saved = tasks.status(root, receipt['id'])
    assert saved['result'] == expected and saved['exit_code'] == exit_code
    assert saved['started_at'] and saved['finished_at'] and Path(saved['last_message']).is_file()
    argv = read_json(Path(saved['receipt']).parent / 'argv.json', [])
    assert argv[0] == 'exec' and argv[argv.index('-m') + 1] == default_config()['model']
    assert argv[argv.index('-s') + 1] == 'workspace-write'
    assert 'sandbox_workspace_write.network_access=true' in argv and '--add-dir' in argv
    assert 'Done means:' in argv[-1] and 'Deliverable:' in argv[-1]
    assert 'do not send anything to anyone; write the result and stop' in argv[-1]
    assert saved['deliverable'] in argv[-1]
    assert saved.get('prepared_reply', '').startswith('REM 已经做完：') == (expected == 'completed')
    assert tasks.start(root, receipt['id'])['finished_at'] == saved['finished_at']


def test_timeout_kills_work_and_keeps_receipt(task_notebook, fake_codex, monkeypatch):
    from connectonion.rem import tasks
    monkeypatch.setenv('TASK_FAKE_SLEEP', '30')
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tasks.execute(task_notebook, receipt['id'], timeout=0.1)
    saved = tasks.status(task_notebook, receipt['id'])
    assert saved['result'] == 'timed-out' and saved['exit_code'] == 124
    assert not saved.get('prepared_reply') and saved['finished_at']


def test_project_repository_is_working_directory(task_notebook, fake_codex, tmp_path):
    from connectonion.rem import tasks
    repo = tmp_path / 'pilot-repository'
    repo.mkdir()
    book = Notebook(task_notebook)
    book.write('projects/pilot.md', book.read('projects/pilot.md').replace('## Paths\n', f'## Paths\n- {repo}\n'))
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tasks.execute(task_notebook, receipt['id'])
    argv = read_json(Path(receipt['receipt']).parent / 'argv.json', [])
    assert argv[argv.index('-C') + 1] == str(repo)
    assert str(Path(receipt['receipt']).parent) in argv


def test_auto_is_opt_in_and_status_explains_it(task_notebook, monkeypatch):
    from connectonion.rem import tasks, service
    launched = []
    monkeypatch.setattr(tasks, 'start', lambda root, identity: launched.append(identity) or {'id': identity})
    assert not read_config(task_notebook)['tasks']['auto']
    assert tasks.auto_dispatch(task_notebook, read_config(task_notebook)) == []
    assert not launched
    set_config(task_notebook, ['tasks.auto', 'true'])
    tasks.auto_dispatch(task_notebook, read_config(task_notebook))
    assert launched
    assert service.status(task_notebook)['tasks']['auto'] is True
    with pytest.raises(RemError, match='tasks.auto'):
        set_config(task_notebook, ['tasks.auto', 'yes'])


def test_approval_queues_receipt_for_host_without_starting_codex(task_notebook, monkeypatch):
    from connectonion.rem import approvals, tasks
    monkeypatch.setattr(tasks, 'start', lambda *a: pytest.fail('approval must dispatch through Host'))
    outcome = approvals.outcomes(task_notebook)[0]
    result = approvals.approve(task_notebook, [outcome['id']])['results'][0]
    assert result['receipt_id'] and result['status'] == 'queued'
    receipt = tasks.status(task_notebook, result['receipt_id'])
    assert receipt['result'] == 'queued'
    calls = []
    approvals.release(task_notebook, dispatch=lambda item: calls.append(item) or {'id': item['receipt_id']})
    assert calls[0]['receipt_id'] == receipt['id']


def test_reader_uses_receipt_and_does_not_trust_last_message(task_notebook, fake_codex):
    from connectonion.rem import tasks, reader
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tasks.execute(task_notebook, receipt['id'])
    data = reader.snapshot(task_notebook, local=True, today=True)
    task = data['today_queue'][0]['outcome']['task']
    assert task['result'] == 'completed' and Path(task['deliverable']).is_file()
    assert task['prepared_reply'].startswith('REM 已经做完：')
    saved = read_json(Path(receipt['receipt']), {})
    write_json(Path(receipt['receipt']), {**saved, 'result': 'failed', 'exit_code': 1})
    task = reader.snapshot(task_notebook, local=True, today=True)['today_queue'][0]['outcome']['task']
    assert task['result'] == 'failed' and not task.get('prepared_reply')
    assert reader.snapshot(task_notebook)['night_outcomes'] == []


def test_status_reconciles_a_worker_that_died_before_writing_its_receipt(task_notebook):
    from connectonion.rem import tasks
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    write_json(Path(receipt['receipt']), {**receipt, 'result': 'starting', 'pid': 999999999,
                                         'command': '-m connectonion.rem.tasks --root fictional'})
    saved = tasks.status(task_notebook, receipt['id'])
    assert saved['result'] == 'failed' and saved['finished_at']
    assert read_json(Path(receipt['receipt']), {})['result'] == 'failed'


def test_stop_handles_a_worker_without_a_signal_handler(task_notebook, tmp_path):
    import subprocess
    from connectonion.rem import tasks
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    script = tmp_path / 'starting-worker'
    script.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n')
    script.chmod(0o700)
    command = [str(script), '--root', str(task_notebook)]
    process = subprocess.Popen(command, start_new_session=True)
    try:
        write_json(Path(receipt['receipt']), {**receipt, 'result': 'starting', 'pid': process.pid,
                                             'command': ' '.join(command[1:])})
        saved = tasks.stop(task_notebook, receipt['id'])
        assert saved['result'] == 'stopped' and saved['finished_at']
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()


def test_host_timeout_is_a_durable_approval_error(task_notebook, monkeypatch):
    import subprocess
    from connectonion.rem import approvals, tasks
    item = approvals.outcomes(task_notebook)[0]
    approvals.approve(task_notebook, [item['id']])
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 30)
    monkeypatch.setattr(tasks.subprocess, 'run', timeout)
    result = approvals.release(task_notebook, dispatch=lambda item: tasks.host_dispatch(task_notebook, item))[0]
    assert result['status'] == 'error' and 'launch' in result['error'].lower()


def test_completed_task_is_not_offered_for_approval_again(task_notebook, fake_codex):
    from connectonion.rem import approvals, tasks
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tasks.execute(task_notebook, receipt['id'])
    assert approvals.outcomes(task_notebook) == []


def test_stop_reaps_codex_after_worker_crash(task_notebook, fake_codex, monkeypatch):
    import signal
    import subprocess
    from contextlib import suppress
    from connectonion.rem import tasks
    from connectonion.rem.live_host import _alive
    monkeypatch.setenv('TASK_FAKE_SLEEP', '30')
    task_id = tasks.status(task_notebook)[0]['id']
    receipt = tasks.start(task_notebook, task_id)
    child = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            saved = read_json(Path(receipt['receipt']), {})
            if saved.get('codex_pid') and (Path(receipt['receipt']).parent / 'argv.json').exists():
                child = saved['codex_pid']
                break
            time.sleep(.05)
        assert child is not None, saved
        os.kill(receipt['pid'], signal.SIGKILL)
        while _alive(receipt) and time.monotonic() < deadline:
            time.sleep(.05)
        assert tasks.stop(task_notebook, task_id)['result'] == 'stopped'
        process = subprocess.run(['ps', '-p', str(child), '-o', 'stat='], capture_output=True, text=True)
        assert not process.stdout.strip() or process.stdout.strip().startswith('Z'), 'Codex survived confirmed stop'
    finally:
        for pid in [receipt['pid'], child]:
            if pid:
                with suppress(ProcessLookupError):
                    os.killpg(pid, signal.SIGKILL)


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('automatic', [False, True])
def test_both_rounds_dispatch_after_drafts_only_when_opted_in(task_notebook, monkeypatch, native, automatic):
    from connectonion.rem import daily, native_round, tasks
    config = read_config(task_notebook)
    config['tasks']['auto'] = automatic
    events = []
    monkeypatch.setattr(night, 'prepare', lambda *a, **kw: events.append('drafts') or [])
    monkeypatch.setattr(tasks, 'start', lambda root, task_id: events.append('task') or {'id': task_id})
    if native:
        monkeypatch.setattr(native_round, 'finish', lambda *a: None)
        cursor = {'phase': 'daily-update', 'batch': {'done': True}, 'current': None,
                  'jobs': [], 'job_index': 0, 'summaries': [], 'same_new_left': 0,
                  'same_left': 0, 'slot': None, 'changed': [], 'translations': []}
        native_round.prepare_task(task_notebook, cursor, config, task_notebook / 'native-work')
    else:
        monkeypatch.setattr(runner, 'ready', lambda config: (None, None))
        daily._draft_replies(task_notebook, config, {})
    assert events == (['drafts', 'task'] if automatic else ['drafts'])


def test_host_dispatch_runs_public_cli_with_receipt_id(task_notebook, fake_codex, monkeypatch):
    import subprocess
    from connectonion.rem import approvals, tasks
    item = approvals.approve(task_notebook, [approvals.outcomes(task_notebook)[0]['id']])['results'][0]
    calls = []
    def launch(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, '{}', '')
    monkeypatch.setattr(tasks.subprocess, 'run', launch)
    result = tasks.host_dispatch(task_notebook, item)
    assert calls[0][-3:] == ['task', 'run', item['receipt_id']]
    assert '--root' in calls[0] and str(task_notebook) in calls[0]
    assert result['id'] == item['receipt_id']
