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


NATIVE = Path(__file__).parents[1] / 'fixtures' / 'native_runners'


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    """`codex app-server` answering from a recorded real turn; each request lands in requests.jsonl."""
    record = tmp_path / 'codex-requests.jsonl'
    monkeypatch.setenv('CODEX_CMD', str(NATIVE / 'fake_codex_app_server.py'))
    monkeypatch.setenv('FAKE_CODEX_RECORD', str(record))
    return record


def _codex_requests(record):
    """The last request of each method the task's Codex app-server received."""
    return {row['method']: row['params'] for row in map(json.loads, record.read_text().splitlines())}


def _turn_prompt(record):
    return _codex_requests(record)['turn/start']['input'][0]['text']


@pytest.fixture
def fake_claude(monkeypatch):
    """`claude -p --output-format stream-json` replaying a recorded real run."""
    monkeypatch.setenv('CLAUDE_CODE_CMD', str(NATIVE / 'fake_claude.py'))


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


@pytest.mark.parametrize('status,exit_code,missing,expected', [
    ('', 0, False, 'completed'), ('failed', 1, False, 'failed'), ('', 0, True, 'failed')])
def test_one_codex_session_receipts_and_honest_completion(task_notebook, fake_codex, monkeypatch, status, exit_code,
                                                          missing, expected):
    # Codex runs through co's own app-server integration (useful_tools/codex.py), not `codex exec`.
    from connectonion.rem import tasks
    root = task_notebook
    if status:
        monkeypatch.setenv('FAKE_CODEX_STATUS', status)
    if missing:
        monkeypatch.setenv('FAKE_CODEX_MISSING', '1')
    outcome = night.listing(root)[0]
    receipt = tasks.reserve(root, outcome)
    tasks.execute(root, receipt['id'])
    saved = tasks.status(root, receipt['id'])
    assert saved['result'] == expected and saved['exit_code'] == exit_code
    assert saved['started_at'] and saved['finished_at'] and Path(saved['last_message']).is_file()
    assert Path(saved['last_message']).read_text() == 'Hello!'  # the final answer, not the commentary before it
    thread = _codex_requests(fake_codex)['thread/start']
    assert thread['model'] == default_config()['models']['level4'] and thread['config']['model_reasoning_effort'] == 'medium'
    assert thread['sandbox'] == 'danger-full-access' and thread['approvalPolicy'] == 'never'
    prompt = _turn_prompt(fake_codex)
    assert 'Done means:' in prompt and 'Deliverable:' in prompt
    assert 'do not send anything to anyone; write the result and stop' in prompt
    assert saved['deliverable'] in prompt
    assert saved['session_id'] == '01a1bda7-ca66-7640-88ca-79eb9b66e649'
    assert saved.get('prepared_reply', '').startswith('REM 已经做完：') == (expected == 'completed')
    assert tasks.start(root, receipt['id'])['finished_at'] == saved['finished_at']


def test_timeout_kills_work_and_keeps_receipt(task_notebook, fake_codex, monkeypatch):
    from connectonion.rem import tasks
    monkeypatch.setenv('FAKE_CODEX_SLEEP', '120')
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tasks.execute(task_notebook, receipt['id'], timeout=2)
    saved = tasks.status(task_notebook, receipt['id'])
    assert saved['result'] == 'timed-out' and saved['exit_code'] == 124
    assert not saved.get('prepared_reply') and saved['finished_at']


def _git(directory, *args):
    import subprocess
    return subprocess.run(['git', '-C', str(directory), '-c', 'user.name=Mara', '-c', 'user.email=mara@example.com',
                           *args], check=True, capture_output=True, text=True).stdout.strip()


def _link_project(root, path):
    book = Notebook(root)
    book.write('projects/pilot.md', book.read('projects/pilot.md').replace('## Paths\n', f'## Paths\n- {path}\n'))


def _repository(path):
    path.mkdir()
    _git(path, 'init', '-q', '-b', 'main')
    (path / 'README.md').write_text('Fernhill Labs pilot\n')
    _git(path, 'add', 'README.md')
    _git(path, 'commit', '-q', '-m', 'Start the pilot')
    return path


def _writable(record):
    return _codex_requests(record)['thread/start']['config']['sandbox_workspace_write']['writable_roots']


def test_task_runs_with_full_access_in_its_own_worktree_and_leaves_the_project_alone(task_notebook, fake_codex, tmp_path, monkeypatch):
    # D-100: owed work runs as the owner's own Codex runs do, with full access. It needs the
    # web and his accounts (gh, co) to do the job, so nothing is sealed and no variable is stripped.
    from connectonion.rem import tasks
    monkeypatch.setenv('FERNHILL_TOKEN', 'fern-token')
    repo = _repository(tmp_path / 'pilot-repository')
    _link_project(task_notebook, repo)
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tasks.execute(task_notebook, receipt['id'])
    saved = tasks.status(task_notebook, receipt['id'])
    folder = Path(saved['receipt']).parent
    requests = _codex_requests(fake_codex)
    work = folder / 'work'
    assert requests['turn/start']['cwd'] == str(work) == saved['cwd'] and _writable(fake_codex) == [str(folder)]
    assert requests['thread/start']['sandbox'] == 'danger-full-access'
    assert set(requests['thread/start']['config']) == {'model_reasoning_effort', 'sandbox_workspace_write'}
    assert 'FERNHILL_TOKEN' in read_json(folder / 'env.json', [])
    assert (folder / 'tmpdir.txt').read_text() == str(folder / 'tmp')
    # Its own branch: the owner's checkout keeps its branch and has no new files.
    assert _git(work, 'branch', '--show-current') == saved['branch'] == f"rem/task-{receipt['id']}"
    assert (work / 'codex-was-here.md').is_file() and saved['project'] == str(repo)
    assert _git(repo, 'branch', '--show-current') == 'main' and _git(repo, 'status', '--porcelain') == ''
    # Pushing, merging and sending stay the owner's one irreversible click.
    prompt = _turn_prompt(fake_codex)
    assert str(repo) in prompt and 'Never push' in prompt
    assert 'no network' not in prompt and 'cannot read credentials' not in prompt
    assert saved['result'] == 'completed'


def test_a_worktree_the_model_wrote_gets_its_git_pointer_back(task_notebook, fake_codex, tmp_path, monkeypatch):
    import subprocess
    from connectonion.rem import tasks
    repo = _repository(tmp_path / 'pilot-repository')
    _link_project(task_notebook, repo)
    monkeypatch.setenv('FAKE_CODEX_PLANT', '1')  # the model swaps work/.git for a repo with core.fsmonitor
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tasks.execute(task_notebook, receipt['id'])
    work = Path(receipt['receipt']).parent / 'work'
    assert (work / '.git').is_file() and (work / '.git').read_text() == tasks.status(task_notebook, receipt['id'])['gitdir']
    assert _git(work, 'branch', '--show-current') == f"rem/task-{receipt['id']}"
    monitor = subprocess.run(['git', '-C', str(work), 'config', '--get', 'core.fsmonitor'], capture_output=True, text=True)
    assert monitor.returncode == 1 and not monitor.stdout


def test_task_without_a_repository_reads_the_project_and_writes_in_its_folder(task_notebook, fake_codex, tmp_path):
    from connectonion.rem import tasks
    project = tmp_path / 'pilot-notes'
    project.mkdir()
    _link_project(task_notebook, project)
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tasks.execute(task_notebook, receipt['id'])
    saved = tasks.status(task_notebook, receipt['id'])
    folder = Path(saved['receipt']).parent
    assert _codex_requests(fake_codex)['turn/start']['cwd'] == str(folder / 'work')
    assert _writable(fake_codex) == [str(folder)]
    assert not (project / 'codex-was-here.md').exists() and 'branch' not in saved
    assert str(project) in _turn_prompt(fake_codex)


def _finished(root, task_id):
    from connectonion.rem import tasks
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        saved = tasks.status(root, task_id)
        if saved['result'] not in ('queued', 'starting', 'running'):
            return saved
        time.sleep(.05)
    raise AssertionError(saved)


def _approvals(root):
    return list(read_json(state_path(root, 'approvals.json'), {}).values())


def test_night_dispatches_when_on_and_records_rem_as_the_one_who_started(task_notebook, fake_codex):
    from connectonion.rem import approvals, reader, tasks
    config = read_config(task_notebook)
    started = tasks.auto_dispatch(task_notebook, config)
    assert len(started) == 1 and started[0]['by'] == 'rem'
    saved = _finished(task_notebook, started[0]['id'])
    assert saved['result'] == 'completed'
    [record] = _approvals(task_notebook)
    assert record['by'] == 'rem' and record['kind'] == 'task' and record['status'] == 'dispatched'
    assert record['receipt_id'] == saved['id'] and record['keys'] == night.listing(task_notebook)[0]['keys']
    task = reader.snapshot(task_notebook, local=True, today=True)['today_queue'][0]['outcome']['task']
    assert task['by'] == 'rem' and task['prepared_reply'].startswith('REM 已经做完：')
    # The next round finds the receipt: no second session, no second record.
    assert tasks.auto_dispatch(task_notebook, config) == []
    assert tasks.status(task_notebook, saved['id'])['finished_at'] == saved['finished_at']
    assert len(_approvals(task_notebook)) == 1 and approvals.outcomes(task_notebook) == []


def _second_task(root):
    book = Notebook(root)
    book.write('projects/pilot.md', book.read('projects/pilot.md').replace(
        '- You owe Mara a pilot review.\n', '- You owe Mara a pilot review.\n- You owe Fern the onboarding notes.\n'))
    night.prepare(root, read_config(root))
    assert [row['kind'] for row in night.listing(root)] == ['task', 'task']


def _waiting(root):
    return {row['text']: row['task'] for row in night.listing(root) if row['task'].get('result') == 'waiting'}


def _clock(monkeypatch, text):
    from datetime import datetime
    from connectonion.rem import service
    monkeypatch.setattr(service, 'now', lambda: datetime.fromisoformat(text))


# D-104: tasks run side by side and a night has no count cap; only the week floor holds one.
def test_the_night_starts_every_owed_task_at_once(task_notebook, fake_codex, monkeypatch):
    from connectonion.rem import tasks
    monkeypatch.setenv('FAKE_CODEX_SLEEP', '120')
    _second_task(task_notebook)
    started = tasks.auto_dispatch(task_notebook, read_config(task_notebook))
    try:
        assert len(started) == 2 and len({row['id'] for row in started}) == 2
        assert [_running(task_notebook, row['id']) for row in started] == ['running', 'running']
        assert read_json(state_path(task_notebook, 'tasks/waiting.json'), {}) == {}
    finally:
        for row in started:
            tasks.stop(task_notebook, row['id'])


def test_an_approved_task_starts_beside_a_running_one(task_notebook, fake_codex, monkeypatch):
    from connectonion.rem import approvals, tasks
    monkeypatch.setenv('FAKE_CODEX_SLEEP', '120')
    _second_task(task_notebook)
    set_config(task_notebook, ['tasks.auto', 'false'])
    first = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tasks.start(task_notebook, first['id'])
    try:
        offered = next(item for item in approvals.outcomes(task_notebook) if item['kind'] == 'task')
        approvals.approve(task_notebook, [offered['id']])
        assert _running(task_notebook, first['id']) == 'running'
        released = approvals.release(task_notebook, dispatch=lambda item: {'id': item['receipt_id']})
        assert [item['status'] for item in released] == ['dispatched']
    finally:
        tasks.stop(task_notebook, first['id'])


def _running(root, task_id):
    import time
    from connectonion.rem import tasks
    deadline = time.monotonic() + 15
    while tasks.status(root, task_id)['result'] in ('queued', 'starting') and time.monotonic() < deadline:
        time.sleep(.05)
    return tasks.status(root, task_id)['result']


def test_the_night_starts_no_task_past_the_weeks_floor(task_notebook, monkeypatch):
    from connectonion.rem import quota, tasks
    monkeypatch.setattr(tasks, 'start', lambda *a: pytest.fail('past the floor nothing starts'))
    monkeypatch.setattr(quota, 'read', lambda config: {'used_percent': 93, 'window_minutes': 10080,
                                                       'resets_at': 0, 'plan': 'pro'})
    assert tasks.auto_dispatch(task_notebook, read_config(task_notebook)) == []
    [waiting] = _waiting(task_notebook).values()
    assert waiting['wait'] == 'budget' and '93%' in waiting['reason']
    set_config(task_notebook, ['tasks.auto', 'false'])
    tasks.auto_dispatch(task_notebook, read_config(task_notebook))
    assert _waiting(task_notebook) == {}  # with auto off nothing will start it, so it is not "queued"


def test_an_approved_task_starts_its_codex_run(task_notebook, fake_codex):
    # rc62 held every task ("this version does not run it"); D-100 lifts the hold.
    from connectonion.rem import approvals, tasks
    offered = approvals.outcomes(task_notebook)[0]
    assert approvals.approve(task_notebook, [offered['id']])['results'][0]['status'] == 'queued'
    released = approvals.release(task_notebook, dispatch=lambda item: tasks.start(task_notebook, item['receipt_id']))
    assert released[0]['status'] == 'dispatched'
    task = night.listing(task_notebook)[0]['task']
    assert task['result'] != 'held'
    assert _finished(task_notebook, task['id'])['result'] == 'completed'
    assert not hasattr(tasks, 'HOLD') and not hasattr(tasks, 'HELD')


def test_undo_discards_rem_work_returns_it_to_approval_and_the_night_leaves_it(task_notebook, fake_codex, tmp_path):
    from connectonion.rem import approvals, tasks
    repo = _repository(tmp_path / 'pilot-repository')
    _link_project(task_notebook, repo)
    config = read_config(task_notebook)
    saved = _finished(task_notebook, tasks.auto_dispatch(task_notebook, config)[0]['id'])
    folder = Path(saved['receipt']).parent
    assert tasks.undo(task_notebook, saved['id'])['status'] == 'cancelled'
    assert not folder.exists() and _git(repo, 'branch', '--list', 'rem/*') == ''
    assert len(_git(repo, 'worktree', 'list').splitlines()) == 1
    assert [record['status'] for record in _approvals(task_notebook)] == ['cancelled']
    [offered] = approvals.outcomes(task_notebook)
    assert offered['kind'] == 'task' and tasks.auto_dispatch(task_notebook, config) == []
    assert approvals.approve(task_notebook, [offered['id']])['results'][0]['status'] == 'queued'


def test_undo_stops_a_running_task_first(task_notebook, fake_codex, monkeypatch):
    from connectonion.rem import tasks
    monkeypatch.setenv('FAKE_CODEX_SLEEP', '120')
    started = tasks.auto_dispatch(task_notebook, read_config(task_notebook))[0]
    pid = _provider_pid(Path(started['receipt']).parent)
    assert tasks.undo(task_notebook, started['id'])['status'] == 'cancelled'
    assert not Path(started['receipt']).parent.exists()
    import subprocess
    process = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
    assert not process.stdout.strip() or process.stdout.strip().startswith('Z'), 'Codex survived undo'


def _provider_pid(folder):
    """The Codex app-server's pid, written once its turn has started."""
    deadline = time.monotonic() + 15
    while not (folder / 'pid.txt').is_file() and time.monotonic() < deadline:
        time.sleep(.05)
    return int((folder / 'pid.txt').read_text())


def _gone(pid):
    import subprocess
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True).stdout.strip()
        if not state or state.startswith('Z'):
            return True
        time.sleep(.05)
    return False


def test_stop_ends_a_running_task_as_stopped_and_its_provider_with_it(task_notebook, fake_codex, monkeypatch):
    # The owner's Stop reaches the worker as SIGTERM. Codex's own error handling must not
    # turn it into an ordinary failed run.
    from connectonion.rem import tasks
    monkeypatch.setenv('FAKE_CODEX_SLEEP', '120')
    started = tasks.start(task_notebook, tasks.status(task_notebook)[0]['id'])
    pid = _provider_pid(Path(started['receipt']).parent)
    assert _running(task_notebook, started['id']) == 'running'
    saved = tasks.stop(task_notebook, started['id'])
    assert saved['result'] == 'stopped' and saved['exit_code'] == 130
    assert _gone(pid), 'Codex survived stop'


def test_auto_is_on_by_default_and_the_owner_can_turn_it_off(task_notebook, monkeypatch):
    from connectonion.rem import tasks, service
    from connectonion.rem.config import EXPLICIT
    launched = []
    monkeypatch.setattr(tasks, 'start', lambda root, identity: launched.append(identity) or {'id': identity})
    assert default_config()['tasks']['auto'] is True
    config_path = task_notebook / 'config.yaml'
    # init wrote the old default, auto: false, into config.yaml; that is not the owner's choice.
    config_path.write_text(config_path.read_text().replace('tasks:\n  auto: true\n', 'tasks:\n  auto: false\n'))
    assert 'auto: false' in config_path.read_text() and read_config(task_notebook)['tasks']['auto'] is True
    config_path.write_text(config_path.read_text().replace('tasks:\n  auto: false\n', ''))
    assert read_config(task_notebook)['tasks']['auto'] is True  # an older notebook without the key
    tasks.auto_dispatch(task_notebook, read_config(task_notebook))
    assert launched and service.status(task_notebook)['tasks']['auto'] is True
    launched.clear()
    set_config(task_notebook, ['tasks.auto', 'false'])  # the owner's own choice wins
    assert 'tasks.auto' in read_json(state_path(task_notebook, EXPLICIT), [])
    assert tasks.auto_dispatch(task_notebook, read_config(task_notebook)) == []
    assert not launched and service.status(task_notebook)['tasks']['auto'] is False
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
    monkeypatch.setenv('FAKE_CODEX_SLEEP', '120')
    task_id = tasks.status(task_notebook)[0]['id']
    receipt = tasks.start(task_notebook, task_id)
    child = None
    try:
        child = _provider_pid(Path(receipt['receipt']).parent)
        os.kill(receipt['pid'], signal.SIGKILL)
        deadline = time.monotonic() + 10
        while _alive(receipt) and time.monotonic() < deadline:
            time.sleep(.05)
        assert tasks.stop(task_notebook, task_id)['result'] == 'stopped'
        # The app-server's stdin closed with its worker; it ends itself, as the real one does.
        assert _gone(child), 'Codex survived confirmed stop'
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
    assert calls[0][-5:] == ['task', 'run', item['receipt_id'], '--agent', 'codex']
    assert '--root' in calls[0] and str(task_notebook) in calls[0]
    assert result['id'] == item['receipt_id']


def test_claude_runs_a_task_like_codex_with_full_access_and_the_same_receipt(task_notebook, fake_claude):
    # The owner's 交给 Claude: one code path, the agent as data (D-100: full access).
    from connectonion.rem import tasks
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0], agent='claude')
    assert receipt['agent'] == 'claude'
    tasks.execute(task_notebook, receipt['id'])
    saved = tasks.status(task_notebook, receipt['id'])
    folder = Path(saved['receipt']).parent
    argv = read_json(folder / 'argv.json', [])
    assert saved['result'] == 'completed' and saved['agent'] == 'claude'
    # Through co's own Claude Code integration (useful_tools/claude_code.py), full access as a mode.
    assert argv[argv.index('--permission-mode') + 1] == 'bypassPermissions'
    assert argv[argv.index('--add-dir') + 1] == str(folder) and '--output-format' in argv
    assert '--model' not in argv  # REM's model names a Codex model; Claude keeps its own
    assert (folder / 'cwd.txt').read_text() == str(folder / 'work') == saved['cwd']
    assert 'Done means:' in argv[-1] and 'Never push' in argv[-1]
    assert saved['session_id'] == 'bf1b715f-3272-4573-b78d-359571db650a'
    assert saved['prepared_reply'] == f"REM 已经做完：Added to the end of README.md: · 附：{saved['deliverable']}"


def test_a_claude_task_loads_the_owners_own_claude_setup(task_notebook, fake_claude):
    # Context over control: his user CLAUDE.md, skills and settings load, not --safe-mode.
    from connectonion.rem import tasks
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0], agent='claude')
    tasks.execute(task_notebook, receipt['id'])
    saved = tasks.status(task_notebook, receipt['id'])
    argv = read_json(Path(saved['receipt']).parent / 'argv.json', [])
    assert saved['result'] == 'completed', saved.get('reason')
    assert '--safe-mode' not in argv
    assert argv[argv.index('--setting-sources') + 1] == 'user'
    assert argv[argv.index('--permission-mode') + 1] == 'bypassPermissions'


def test_dispatch_starts_any_pending_item_with_the_chosen_agent(task_notebook, fake_claude):
    from connectonion.rem import tasks
    row = night.listing(task_notebook)[0]
    started = tasks.dispatch(task_notebook, row['keys'][0], agent='claude')
    assert started['agent'] == 'claude' and started['by'] == 'owner'
    assert _finished(task_notebook, started['id'])['result'] == 'completed'
    with pytest.raises(RemError, match='codex or claude'):
        tasks.dispatch(task_notebook, row['keys'][0], agent='gemini')
    with pytest.raises(RemError, match='No pending item'):
        tasks.dispatch(task_notebook, 'people/nobody.md\nNothing.', agent='codex')


def test_a_queued_task_takes_the_agent_the_owner_picks_and_the_host_passes_it(task_notebook, monkeypatch):
    from connectonion.rem import tasks
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    assert receipt['agent'] == 'codex'
    seen = []
    monkeypatch.setattr(tasks.subprocess, 'run', lambda command, **kw: seen.append(command) or
                        type('Done', (), {'returncode': 0})())
    tasks.host_dispatch(task_notebook, {'receipt_id': receipt['id'], 'agent': 'claude'})
    assert seen[0][-3:] == [receipt['id'], '--agent', 'claude']
