"""One launchd fire, one locked Codex work session, with durable turn receipts."""
import argparse
import fcntl
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from ..codex_cli import resolve_codex
from ..environment import subprocess_environment
from .files import RemError, read_json, state_path, write_json

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


def _sealed(writable) -> list[str]:
    """An owed-work task's prompt comes from untrusted mail, so it gets no way to send anything
    and cannot read credentials: Codex's own seatbelt runs a permission profile that reads the
    disk except the owner's credential paths, writes only `writable` and temp, and has no
    network. The owner's Codex config is not loaded, so none of their MCP servers, plugins,
    app connectors or hooks start (those run outside the sandbox); web search is off too."""
    from .sandbox_profile import CREDENTIAL_DIRS, CREDENTIAL_FILES
    home = Path(os.path.realpath(Path.home()))
    # A more specific path wins: the task folder stays writable inside a denied ~/.co.
    access = {'/': 'read', ':tmpdir': 'write', ':slash_tmp': 'write',
              **{str(home / name): 'none' for name in (*CREDENTIAL_DIRS, *CREDENTIAL_FILES)},
              **{os.path.realpath(path): 'write' for path in writable}}
    table = '{' + ','.join(f'{json.dumps(path)}={json.dumps(mode)}' for path, mode in access.items()) + '}'
    return ['--ignore-user-config', '-c', 'web_search="disabled"', '-c', 'features.apps=false',
            '-c', 'features.plugins=false', '-c', 'features.browser_use=false', '-c', 'features.computer_use=false',
            '-c', 'default_permissions="rem_task"', '-c', f'permissions.rem_task.filesystem={table}',
            '-c', 'permissions.rem_task.network.enabled=false',
            # connectonion's import loads keys.env into the environment; `env` must not show it.
            '-c', 'shell_environment_policy.inherit="core"']


SECRET_NAME = re.compile('KEY|TOKEN|SECRET|PASSWORD|API', re.I)


def sealed_environment(environment) -> dict:
    """What a sealed Codex itself starts with: no secrets. It signs in from CODEX_HOME's auth file."""
    return {name: value for name, value in environment.items() if not SECRET_NAME.search(name)}


def exec_command(root: Path, config: dict, *, last_message: Path, prompt=None, add_dirs=(), sealed=False) -> list[str]:
    """sealed: an owed-work task; see `_sealed()`."""
    from ..environment import selected_env_file
    from .codex_schedule import automation_prompt
    # Mailbox refresh locks and atomically replaces keys.env beside the file.
    # A -s flag would override the sealed permission profile (codex 0.167 measured it).
    access = _sealed((root, *add_dirs)) if sealed else [
        '-s', 'workspace-write', '-c', 'sandbox_workspace_write.network_access=true',
        '--add-dir', str(selected_env_file().parent)]
    command = [*_codex_command(), 'exec', '-c', f'model_reasoning_effort={config["effort"]}',
               '-C', str(root), *access, '--skip-git-repo-check',
               '--color', 'never', '--json', '--ephemeral', '-o', str(last_message)]
    if config['model'] != 'default':
        command += ['-m', config['model']]
    for directory in add_dirs:
        command += ['--add-dir', str(directory)]
    return [*command, automation_prompt(root) if prompt is None else prompt]


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


def _reap_orphan_maintenance(root):
    """Only a detached next/submit whose own turn finished can be reaped."""
    owner = read_json(state_path(root, 'maintenance-owner.json'), {})
    turn_id, pid = owner.get('turn_id'), owner.get('pid')
    if not turn_id or not pid or owner.get('operation') not in ('next', 'submit'):
        return []
    turn = read_json(state_path(root, f'turns/{turn_id}.json'), {})
    if not turn.get('finished_at') or turn.get('result') not in ('completed', 'failed', 'timed-out'):
        return []
    with state_path(root, 'maintenance.lock').open('a') as held:
        locked = True
        with suppress(BlockingIOError):
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = False
        if not locked:
            return []
    process = subprocess.run(['ps', '-p', str(pid), '-o', 'ppid=,command='],
                             capture_output=True, text=True).stdout.strip().split(maxsplit=1)
    if len(process) != 2 or process[0] != '1':
        return []
    command = process[1]
    # A stale owner file must not authorize killing an unrelated reused PID.
    words = shlex.split(command)
    if 'rem' not in words or not any(word in words for word in ('next', 'submit')):
        return []
    with suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)
        return [f'Terminated orphan maintenance pid {pid}: {command} (finished turn {turn_id})']
    return []


def _run_locked(root, run, lock_fd):
    started = datetime.now(timezone.utc)
    directory = state_path(root, 'turns')
    directory.mkdir(exist_ok=True, mode=0o700)
    name = started.strftime('%Y%m%dT%H%M%S.%fZ')
    log, last = directory / f'{name}.jsonl', directory / f'{name}.last.md'
    receipt = {'turn_id': name, 'started_at': started.isoformat(), 'result': 'running',
               'log': str(log), 'last_message': str(last)}
    write_json(state_path(root, 'last-turn.json'), receipt)
    result, skipped = None, False
    try:
        receipt['terminated_orphans'] = _reap_orphan_maintenance(root)
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
                         cwd=root, pass_fds=(lock_fd,), env={**subprocess_environment(), 'CO_REM_TURN_ID': name})
    except Exception as error:
        # Persist the failure for unattended users, then preserve the traceback.
        receipt['reason'] = str(error) or type(error).__name__
        raise
    finally:
        code = result.returncode if result is not None else None
        outcome = 'skipped' if skipped else 'completed' if code == 0 else 'timed-out' if code == 124 else 'failed'
        if code == 124:
            receipt['reason'] = 'Turn exceeded 3 hours; the next fire continues the round'
        # Only the protocol's terminal busy line is a blocker, never a recovered narrative.
        message = last.read_text().strip() if last.is_file() else ''
        busy = bool(re.fullmatch(
            r'MAINTENANCE_BUSY: waited 10 minutes total; maintenance lock holder pid (?:\d+|unknown): '
            r'[^\n]+\. Report this message and end the turn without retrying\.', message))
        receipt['blocked'] = busy or (result is None and not skipped)
        if busy:
            receipt['reason'] = message
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
