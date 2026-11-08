"""Real CLI and worker processes, a fictional notebook and a fake Codex binary."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from connectonion.rem import tasks as rem_tasks
from tests.unit.test_rem_tasks import task_notebook, fake_codex  # noqa: F401

HELD = rem_tasks.HOLD  # read before task_notebook lifts it in this process; the CLI child keeps it


def test_task_run_says_this_version_holds_the_task(task_notebook):
    command = [sys.executable, '-m', 'connectonion.cli.main', 'rem', '--root', str(task_notebook), '--json', 'task']
    from connectonion.rem.runner import child_env
    task_id = json.loads(subprocess.run([*command, 'status'], capture_output=True, text=True, env=child_env(), timeout=20).stdout)['data'][0]['id']
    run = subprocess.run([*command, 'run', task_id], capture_output=True, text=True, env=child_env(), timeout=20)
    if not HELD:
        pytest.skip('this version runs tasks; test_task_run_status_stop_cli covers it')
    assert run.returncode == 1 and 'this version does not run it' in json.loads(run.stdout)['data']


@pytest.mark.skipif(HELD, reason='this version holds every task (tasks.HOLD); a CLI subprocess cannot lift it')
def test_task_run_status_stop_cli(task_notebook, fake_codex, monkeypatch):
    monkeypatch.setenv('TASK_FAKE_SLEEP', '30')
    from connectonion.rem import tasks
    from connectonion.rem.runner import child_env
    command = [sys.executable, '-m', 'connectonion.cli.main', 'rem', '--root', str(task_notebook), '--json', 'task']

    def cli(*args):
        run = subprocess.run([*command, *args], capture_output=True, text=True, env=child_env(), timeout=20)
        assert run.returncode == 0, run.stdout + run.stderr
        return json.loads(run.stdout)['data']

    task_id = cli('status')[0]['id']
    try:
        first = cli('run', task_id)
        second = cli('run', task_id)
        assert first['id'] == second['id'] and first['pid'] == second['pid']
        deadline = time.monotonic() + 15
        receipt = cli('status', task_id)
        while receipt['result'] == 'starting' and time.monotonic() < deadline:
            time.sleep(.1)
            receipt = cli('status', task_id)
        assert receipt['result'] == 'running', receipt
        assert receipt['started_at'] and Path(receipt['receipt']).is_file()
        stopped = cli('stop', task_id)
        assert stopped['result'] == 'stopped' and stopped['exit_code'] == 130
        assert cli('status', task_id)['finished_at'] == stopped['finished_at']
        assert cli('stop', task_id)['result'] == 'stopped'
    finally:
        tasks.stop(task_notebook, task_id)
