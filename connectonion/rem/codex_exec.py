"""One launchd fire, one locked Codex work session, with durable turn receipts."""
import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
import traceback
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
    # One session does every task of the round, so it runs the native level.
    from .config import read_config as read
    from .inquiry import stage_config
    return stage_config(root, read(root), "native")


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
    """The scheduled maintenance turn. Owed-work tasks run through co's own Codex
    integration instead (tasks.py)."""
    from ..environment import selected_env_file
    from .codex_schedule import automation_prompt
    # Mailbox refresh locks and atomically replaces keys.env beside the file.
    codex = _codex_command()
    command = [*codex, 'exec', '-c', f'model_reasoning_effort={config["effort"]}',
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
    import fcntl  # POSIX-only; rem.tasks imports this module and the reader imports rem.tasks
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
    import fcntl
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
    result, skipped, failed = None, False, False
    before = read_json(state_path(root, 'round.json'), {})
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
        cursor = read_json(state_path(root, 'round.json'), {})
        if cursor and cursor != before:
            from .schedule import calendar_round
            receipt['calendar'] = calendar_round(root, native=True)
        if result.returncode == 0 and cursor.get('done') and cursor != before:
            from .schedule import finish_exec
            receipt['depth'] = finish_exec(root, {'outcome': 'done', 'reason': 'round done'}).get('depth')
    except BaseException as error:
        # Persist failed or interrupted deepening even after Codex itself exited zero.
        failed = True
        receipt['reason'] = str(error) or type(error).__name__
        with log.open('a') as output:
            output.write(json.dumps({'type': 'rem.turn_failed', 'error': receipt['reason'],
                                     'traceback': traceback.format_exc()}) + '\n')
        raise
    finally:
        code = result.returncode if result is not None else None
        outcome = 'skipped' if skipped else 'completed' if code == 0 and not failed else 'timed-out' if code == 124 else 'failed'
        events = _turn_events(root, receipt)
        preparation_error = events[-1].get('error', '') if events else ''
        if preparation_error and not skipped:
            outcome = 'failed'
            receipt['reason'] = preparation_error
        nothing = _produced_nothing(events) if outcome == 'completed' else ''
        if nothing:
            # Exit 0 says Codex ended cleanly, not that the turn did anything (11-16:
            # three deadlines, nothing served, nothing submitted, "completed").
            outcome = 'failed'
            receipt.update(reason=nothing, produced_nothing=True)
        elif outcome == 'completed' and not events:
            # Still completed: said, not counted, because nothing here proves the turn was empty.
            receipt['reason'] = 'No co rem next was recorded in this turn'
        if code == 124 and not preparation_error:
            receipt['reason'] = 'Turn exceeded 3 hours; the next fire continues the round'
        # Only the protocol's terminal busy line is a blocker, never a recovered narrative.
        message = last.read_text().strip() if last.is_file() else ''
        busy = bool(re.fullmatch(
            r'MAINTENANCE_BUSY: waited 10 minutes total; maintenance lock holder pid (?:\d+|unknown): '
            r'[^\n]+\. Report this message and end the turn without retrying\.', message))
        receipt['blocked'] = busy or bool(preparation_error) or (result is None and not skipped)
        if busy and not preparation_error:
            receipt['reason'] = message
        receipt.update(result=outcome, exit_code=code, killed_descendants=getattr(result, 'killed_descendants', 0),
                       finished_at=datetime.now(timezone.utc).isoformat())
        write_json(directory / f'{name}.json', receipt)
        write_json(state_path(root, 'last-turn.json'), receipt)

    return outcome


def _record(root, event):
    """A next or submit reports to its own launcher, independently of Codex's exit code."""
    turn_id = os.environ.get('CO_REM_TURN_ID')
    if not turn_id:
        return
    turn = read_json(state_path(root, 'last-turn.json'), {})
    if turn.get('turn_id') != turn_id or turn.get('result') != 'running':
        return
    # A separate append stream avoids racing Codex's stdout offset. The launcher
    # copies these events into the turn log after the subprocess has exited.
    with state_path(root, f"turns/{turn['turn_id']}.preparation.jsonl").open('a') as output:
        output.write(json.dumps({**event, 'at': datetime.now(timezone.utc).isoformat()}) + '\n')


def record_preparation(root, error=None, result=None):
    """What one `co rem next` came to: an error, or its outcome (task, done and why)."""
    if error:
        _record(root, {'type': 'rem.preparation_failed', 'error': str(error) or type(error).__name__,
                       'traceback': ''.join(traceback.format_exception(error))})
        return
    said = {key: result[key] for key in ('outcome', 'reason') if result and result.get(key)}
    _record(root, {'type': 'rem.prepared', **said})


def record_submission(root, result):
    _record(root, {'type': 'rem.submitted', 'outcome': result.get('outcome')})


def record_stall(root, step, timings):
    """A `co rem next` that passed its deadline: what it was waiting on and the seconds each step took."""
    _record(root, {'type': 'rem.preparation_stalled', 'step': step, 'timings': timings})


def _turn_events(root, receipt):
    """What this turn's next and submit calls reported, copied into the turn log."""
    path = state_path(root, f"turns/{receipt['turn_id']}.preparation.jsonl")
    if not path.is_file():
        return []
    text = path.read_text()
    with Path(receipt['log']).open('a') as output:
        output.write(text)
    return [json.loads(line) for line in text.splitlines()]


def _produced_nothing(events):
    """Why a turn that exited 0 is not completed, in words; '' when it did work or had none to do.

    Completed means a task was served, a submission was accepted, or the last
    `co rem next` answered without a task (not due, round done, a cap or the
    floor): that last one is how an idle turn is told from an empty one."""
    served = any(event['type'] == 'rem.prepared' and event.get('outcome') == 'task' for event in events)
    accepted = any(event['type'] == 'rem.submitted' and event.get('outcome') == 'accepted' for event in events)
    if served or accepted:
        return ''
    calls = [event for event in events if event['type'] != 'rem.submitted']
    # No call recorded is not evidence of an empty turn: the record may not have reached us.
    if not calls or calls[-1]['type'] != 'rem.preparation_stalled':
        return ''
    stalls = [event for event in calls if event['type'] == 'rem.preparation_stalled']
    times = '1 time' if len(stalls) == 1 else f'{len(stalls)} times'
    return (f"The turn produced nothing: co rem next passed its deadline {times}, last while {stalls[-1]['step']}; "
            'no task was served and nothing was submitted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(1 if run_turn(args.root) in ('failed', 'timed-out') else 0)
