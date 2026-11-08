"""Real CLI and worker processes, a fictional notebook and a fake Codex binary."""
import json
import subprocess
import sys
import time
from pathlib import Path

from tests.unit.test_rem_tasks import task_notebook, fake_codex  # noqa: F401


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
