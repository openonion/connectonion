"""One launchd fire, one locked Codex work session, with durable turn receipts."""
import argparse
import fcntl
import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .config import read_config
from .files import state_path, write_json


def exec_command(root: Path, config: dict, *, last_message: Path) -> list[str]:
    from ..useful_tools.codex import _base_command
    from .codex_schedule import automation_prompt
    from .files import RemError
    base = _base_command()
    if not base:
        raise RemError('Install the Codex CLI and run codex login before co rem start')
    command = [*base[:-1], 'exec', '-c', f'model_reasoning_effort={config["effort"]}',
               '-C', str(root), '-s', 'workspace-write', '--skip-git-repo-check',
               '--color', 'never', '--json', '-o', str(last_message)]
    if config['model'] != 'default':
        command += ['-m', config['model']]
    return [*command, automation_prompt(root)]


def _execute(command, **kwargs):
    """A deadline kills the process group too, including tools still running."""
    with subprocess.Popen(command, start_new_session=True, **kwargs) as process:
        try:
            return subprocess.CompletedProcess(command, process.wait(timeout=3000))
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            return subprocess.CompletedProcess(command, 124)


def run_turn(root: Path, *, run=_execute) -> str:
    root = Path(root).resolve()
    lock = state_path(root, 'exec-turn.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as held:
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'busy'
        return _run_locked(root, run, held.fileno())


def _run_locked(root, run, lock_fd):
    started = datetime.now(timezone.utc)
    directory = state_path(root, 'turns')
    directory.mkdir(exist_ok=True, mode=0o700)
    name = started.strftime('%Y%m%dT%H%M%S.%fZ')
    log, last = directory / f'{name}.jsonl', directory / f'{name}.last.md'
    receipt = {'started_at': started.isoformat(), 'result': 'running',
               'log': str(log), 'last_message': str(last)}
    write_json(state_path(root, 'last-turn.json'), receipt)
    result = None
    try:
        with log.open('w') as output:
            command = exec_command(root, read_config(root), last_message=last)
            # Inherit the lock so killing the launcher cannot overlap a still
            # running Codex session with the next fire.
            result = run(command, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                         cwd=root, pass_fds=(lock_fd,))
    finally:
        code = result.returncode if result is not None else None
        outcome = 'completed' if code == 0 else 'timed-out' if code == 124 else 'failed'
        receipt.update(result=outcome, exit_code=code, finished_at=datetime.now(timezone.utc).isoformat())
        write_json(directory / f'{name}.json', receipt)
        write_json(state_path(root, 'last-turn.json'), receipt)

    return outcome


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(1 if run_turn(args.root) in ('failed', 'timed-out') else 0)
