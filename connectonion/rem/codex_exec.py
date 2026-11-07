"""One launchd fire, one locked Codex work session, with durable turn receipts."""
import argparse
import fcntl
import os
import shlex
import shutil
import signal
import subprocess
import time
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from ..codex_cli import resolve_codex
from .files import RemError, state_path, write_json

# Leave room for overloaded machines; this bounds hangs, not normal startup.
STARTUP_TIMEOUT_S = 300
TURN_SECONDS = 3 * 3600


def read_config(root):
    # Import configuration only after the turn has a receipt and a deadline.
    from .config import read_config as read
    return read(root)


def _codex_command() -> list[str]:
    """Resolve the CLI without importing the interactive tools or app-server."""
    override = os.environ.get('CODEX_CMD', '')
    expanded = os.path.expanduser(override)
    command = ([expanded] if os.path.isfile(expanded) else shlex.split(override)) if override else ['codex']
    launchers = {'caffeinate', 'env', 'sh', 'bash', 'zsh', 'python', 'python3', 'node'}
    if (not command or any('connectonion.rem.codex_exec' in arg or 'codex_exec.py' in arg for arg in command)
            or Path(command[0]).name in launchers or Path(command[0]).name.startswith('python')):
        raise RemError('CODEX_CMD must name the Codex CLI, never the REM launcher or an interpreter')
    binary = shutil.which(os.path.expanduser(command[0])) if override else resolve_codex()
    if not binary:
        raise RemError('Codex CLI not found; install Codex, fix CODEX_CMD and run co rem start')
    if Path(binary).resolve().name.startswith('python') or Path(binary).resolve().name in launchers:
        raise RemError('CODEX_CMD must name the Codex CLI, never the REM launcher or an interpreter')
    return [os.path.abspath(binary), *command[1:]]


def exec_command(root: Path, config: dict, *, last_message: Path) -> list[str]:
    from ..environment import selected_env_file
    from .codex_schedule import automation_prompt
    # Mailbox refresh locks and atomically replaces keys.env beside the file.
    command = [*_codex_command(), 'exec', '-c', f'model_reasoning_effort={config["effort"]}',
               '-C', str(root), '-s', 'workspace-write', '-c', 'sandbox_workspace_write.network_access=true',
               '--add-dir', str(selected_env_file().parent), '--skip-git-repo-check',
               '--color', 'never', '--json', '--ephemeral', '-o', str(last_message)]
    if config['model'] != 'default':
        command += ['-m', config['model']]
    return [*command, automation_prompt(root)]


def _startup_timeout(signum, frame):
    raise TimeoutError(f'Codex turn could not start within {STARTUP_TIMEOUT_S:g} seconds; '
                       'check configuration and run co rem start')


def _start_command(root, last):
    from ..environment import load_environment
    previous = signal.signal(signal.SIGALRM, _startup_timeout)
    started = time.monotonic()
    delay, interval = signal.setitimer(signal.ITIMER_REAL, STARTUP_TIMEOUT_S)
    try:
        load_environment()
        return exec_command(root, read_config(root), last_message=last)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if delay:
            signal.setitimer(signal.ITIMER_REAL, max(0.001, delay - (time.monotonic() - started)), interval)


def _terminate_descendants(pid):
    """Kill deepest children first, including tools that created new sessions."""
    table = subprocess.run(['ps', '-Ao', 'pid=,ppid='], check=True, capture_output=True, text=True)
    children = {}
    for row in table.stdout.splitlines():
        child, parent = map(int, row.split())
        children.setdefault(parent, []).append(child)
    descendants, parents = [], [pid]
    while parents:
        parents = [child for parent in parents for child in children.get(parent, [])]
        descendants.extend(parents)
    descendants.reverse()
    terminated = set()
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for child in descendants:
            # Exiting between enumeration and signalling is normal; other errors propagate.
            with suppress(ProcessLookupError):
                os.kill(child, sig)
                terminated.add(child)
        if sig == signal.SIGTERM and descendants:
            time.sleep(0.2)
    return len(terminated)


def _execute(command, *, timeout=TURN_SECONDS, **kwargs):
    """A deadline kills detached descendants before the launcher's process group."""
    with subprocess.Popen(command, start_new_session=True, **kwargs) as process:
        try:
            return subprocess.CompletedProcess(command, process.wait(timeout=timeout))
        except subprocess.TimeoutExpired:
            try:
                killed = _terminate_descendants(process.pid)
            finally:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            result = subprocess.CompletedProcess(command, 124)
            result.killed_descendants = killed
            return result


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
    result, skipped = None, False
    try:
        from .codex_schedule import CodexNative
        if CodexNative().recent_desktop_fire(root):
            skipped = True
            receipt['reason'] = 'desktop automation fired in the last 10 minutes'
            return 'skipped'
        with log.open('w') as output:
            startup = time.monotonic()
            command = _start_command(root, last)
            receipt['started_codex_after_s'] = round(time.monotonic() - startup, 3)
            write_json(state_path(root, 'last-turn.json'), receipt)
            # Inherit the lock so killing the launcher cannot overlap a still
            # running Codex session with the next fire.
            result = run(command, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                         cwd=root, pass_fds=(lock_fd,))
    except Exception as error:
        # Persist the failure for unattended users, then preserve the traceback.
        receipt['reason'] = str(error) or type(error).__name__
        raise
    finally:
        code = result.returncode if result is not None else None
        outcome = 'skipped' if skipped else 'completed' if code == 0 else 'timed-out' if code == 124 else 'failed'
        if code == 124:
            receipt['reason'] = 'Turn exceeded 3 hours; the next fire continues the round'
        receipt.update(result=outcome, exit_code=code, killed_descendants=getattr(result, 'killed_descendants', 0),
                       finished_at=datetime.now(timezone.utc).isoformat())
        write_json(directory / f'{name}.json', receipt)
        write_json(state_path(root, 'last-turn.json'), receipt)

    return outcome


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(1 if run_turn(args.root) in ('failed', 'timed-out') else 0)
