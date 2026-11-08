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
    # tasks.auto is off by default until the inverted read boundary ships; these tests run it on.
    set_config(root, ["runner", "codex", "model", default_config()["model"], "tasks.auto", "true"])
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
(last.parent / 'env.json').write_text(json.dumps(sorted(os.environ)))
last.write_text('Reviewed the Mara pilot.')
os.chdir(args[args.index('-C') + 1])
pathlib.Path('codex-was-here.md').write_text('Mara pilot notes')
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
    assert 'default_permissions="rem_task"' in argv and '--add-dir' in argv
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


def _writable(argv):
    return [argv[index + 1] for index, arg in enumerate(argv) if arg == '--add-dir']


def test_task_works_sealed_in_its_own_worktree_and_leaves_the_project_alone(task_notebook, fake_codex, tmp_path, monkeypatch):
    import re
    from connectonion.rem import tasks
    # connectonion's import loads keys.env into os.environ; none of it may reach the task.
    monkeypatch.setenv('CANARY_API_KEY', 'fern-canary')
    monkeypatch.setenv('FERNHILL_TOKEN', 'fern-canary')
    monkeypatch.setenv('MARA_PASSWORD', 'fern-canary')
    repo = _repository(tmp_path / 'pilot-repository')
    _link_project(task_notebook, repo)
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tasks.execute(task_notebook, receipt['id'])
    saved = tasks.status(task_notebook, receipt['id'])
    folder = Path(saved['receipt']).parent
    argv = read_json(folder / 'argv.json', [])
    work = folder / 'work'
    # Codex writes only in a worktree on its own branch, plus its task folder.
    assert argv[argv.index('-C') + 1] == str(work) == saved['cwd'] and _writable(argv) == [str(folder)]
    assert _git(work, 'branch', '--show-current') == saved['branch'] == f"rem/task-{receipt['id']}"
    assert (work / 'codex-was-here.md').is_file() and saved['project'] == str(repo)
    # The owner's checkout keeps its branch and has no new files.
    assert _git(repo, 'branch', '--show-current') == 'main' and _git(repo, 'status', '--porcelain') == ''
    # No network for its commands: nothing can be pushed, mailed or posted.
    assert not any('network_access=true' in arg for arg in argv)
    # A -s flag overrides the permission profile: measured with codex 0.167, a run with
    # -s workspace-write read the canary credentials and reached the network.
    assert '-s' not in argv and '--sandbox' not in argv
    # Codex's own web search could carry what it read to a live URL; it is off too.
    assert 'web_search="disabled"' in argv
    # MCP servers, plugins and app connectors run outside the sandbox with network
    # (a GitHub connector can open an issue): the owner's Codex config is not loaded.
    assert '--ignore-user-config' in argv
    assert {'features.apps=false', 'features.plugins=false', 'features.browser_use=false',
            'features.computer_use=false'} <= set(argv)
    assert not any(arg.startswith('mcp_servers.') and 'enabled=true' in arg for arg in argv)
    # Codex's seatbelt reads the disk except the owner's credentials; the task folder stays
    # writable inside a denied ~/.co.
    from connectonion.rem.sandbox_profile import CREDENTIAL_DIRS, CREDENTIAL_FILES
    assert 'default_permissions="rem_task"' in argv and 'permissions.rem_task.network.enabled=false' in argv
    # The shell tool gets only Codex's core variables, and Codex itself gets no secrets.
    assert 'shell_environment_policy.inherit="core"' in argv
    names = read_json(folder / 'env.json', [])
    assert 'PATH' in names and 'HOME' in names
    assert not [name for name in names if re.search('KEY|TOKEN|SECRET|PASSWORD|API', name, re.I)], names
    table = next(arg for arg in argv if arg.startswith('permissions.rem_task.filesystem='))
    home = os.path.realpath(Path.home())
    for name in ('.co', '.ssh', '.config/gh', '.aws', '.gnupg', '.netrc', '.git-credentials'):
        assert name in (*CREDENTIAL_DIRS, *CREDENTIAL_FILES) and f'"{home}/{name}"="none"' in table
    assert f'"{os.path.realpath(folder)}"="write"' in table and f'"{os.path.realpath(work)}"="write"' in table
    assert str(repo) in argv[-1] and 'Never push' in argv[-1]
    assert saved['result'] == 'completed'


def test_task_without_a_repository_reads_the_project_and_writes_in_its_folder(task_notebook, fake_codex, tmp_path):
    from connectonion.rem import tasks
    project = tmp_path / 'pilot-notes'
    project.mkdir()
    _link_project(task_notebook, project)
    receipt = tasks.reserve(task_notebook, night.listing(task_notebook)[0])
    tasks.execute(task_notebook, receipt['id'])
    saved = tasks.status(task_notebook, receipt['id'])
    folder = Path(saved['receipt']).parent
    argv = read_json(folder / 'argv.json', [])
    assert argv[argv.index('-C') + 1] == str(folder / 'work') and _writable(argv) == [str(folder)]
    assert not (project / 'codex-was-here.md').exists() and 'branch' not in saved
    assert str(project) in argv[-1]


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


def test_the_night_runs_one_task_at_a_time_and_queues_the_next_for_later(task_notebook, fake_codex, monkeypatch):
    from connectonion.rem import tasks
    monkeypatch.setenv('TASK_FAKE_SLEEP', '30')
    _second_task(task_notebook)
    config = read_config(task_notebook)
    first = tasks.auto_dispatch(task_notebook, config)
    try:
        assert len(first) == 1
        [waiting] = _waiting(task_notebook).values()
        assert waiting['wait'] == 'later' and 'running' in waiting['reason']
        assert tasks.auto_dispatch(task_notebook, config) == []  # still running: nothing new
    finally:
        tasks.stop(task_notebook, first[0]['id'])
    second = tasks.auto_dispatch(task_notebook, config)
    try:
        assert len(second) == 1 and second[0]['id'] != first[0]['id'] and _waiting(task_notebook) == {}
    finally:
        tasks.stop(task_notebook, second[0]['id'])


def test_tasks_per_night_counts_rem_starts_from_noon_to_noon(task_notebook, fake_codex, monkeypatch):
    from connectonion.rem import tasks
    assert default_config()['limits']['tasks_per_night'] == 3
    _second_task(task_notebook)
    set_config(task_notebook, ['limits.tasks_per_night', '1'])
    config = read_config(task_notebook)
    _clock(monkeypatch, '2026-09-07T23:00:00+00:00')
    _finished(task_notebook, tasks.auto_dispatch(task_notebook, config)[0]['id'])
    _clock(monkeypatch, '2026-09-08T01:00:00+00:00')  # after midnight, still the same night
    assert tasks.auto_dispatch(task_notebook, config) == []
    [waiting] = _waiting(task_notebook).values()
    assert waiting['wait'] == 'budget' and 'tasks_per_night' in waiting['reason']
    _clock(monkeypatch, '2026-09-08T22:00:00+00:00')
    assert len(tasks.auto_dispatch(task_notebook, config)) == 1


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


def test_an_approved_task_waits_for_the_running_one_and_its_card_says_so(task_notebook, fake_codex, monkeypatch):
    from connectonion.rem import approvals, tasks
    monkeypatch.setenv('TASK_FAKE_SLEEP', '30')
    _second_task(task_notebook)
    first = tasks.auto_dispatch(task_notebook, read_config(task_notebook))[0]
    try:
        offered = approvals.outcomes(task_notebook)[0]
        approvals.approve(task_notebook, [offered['id']])
        calls = []
        assert approvals.release(task_notebook, dispatch=lambda item: calls.append(item) or {}) == []
        assert not calls and approvals.pending(task_notebook)[0]['status'] == 'queued'
        [waiting] = _waiting(task_notebook).values()
        assert waiting['wait'] == 'later' and waiting['by'] == 'owner'
    finally:
        tasks.stop(task_notebook, first['id'])
    released = approvals.release(task_notebook, dispatch=lambda item: {'id': item['receipt_id']})
    assert released[0]['status'] == 'dispatched' and released[0]['dispatched_at']


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
    monkeypatch.setenv('TASK_FAKE_SLEEP', '30')
    started = tasks.auto_dispatch(task_notebook, read_config(task_notebook))[0]
    deadline = time.monotonic() + 10
    while not read_json(Path(started['receipt']), {}).get('codex_pid') and time.monotonic() < deadline:
        time.sleep(.05)
    pid = read_json(Path(started['receipt']), {})['codex_pid']
    assert tasks.undo(task_notebook, started['id'])['status'] == 'cancelled'
    assert not Path(started['receipt']).parent.exists()
    import subprocess
    process = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
    assert not process.stdout.strip() or process.stdout.strip().startswith('Z'), 'Codex survived undo'


def test_auto_is_off_by_default_and_the_owner_can_turn_it_on(task_notebook, monkeypatch):
    from connectonion.rem import tasks, service
    launched = []
    monkeypatch.setattr(tasks, 'start', lambda root, identity: launched.append(identity) or {'id': identity})
    set_config(task_notebook, ['tasks.auto', 'false'])
    assert tasks.auto_dispatch(task_notebook, read_config(task_notebook)) == []
    assert not launched and service.status(task_notebook)['tasks']['auto'] is False
    (task_notebook / 'config.yaml').write_text((task_notebook / 'config.yaml').read_text().replace(
        'tasks:\n  auto: false\n', ''))
    assert default_config()['tasks']['auto'] is False
    assert read_config(task_notebook)['tasks']['auto'] is False  # an older notebook without the key
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
