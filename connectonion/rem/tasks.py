"""One owner-owed obligation, one Codex process, one durable deliverable receipt."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager, suppress
from pathlib import Path

from . import codex_exec
from .config import read_config
from .files import RemError, read_json, state_path, write_json
from .service import now


ACTIVE = ('starting', 'running')
# Who does the work: the owner's 交给 Codex / 交给 Claude. One runner, the agent as data.
AGENTS = ('codex', 'claude')


def identity(key):
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def directory(root, task_id):
    task_id = task_id.removeprefix('task:').removeprefix('do-')
    if not re.fullmatch(r'[a-f0-9]{32}', task_id):
        raise RemError('Use a task ID from co rem task status')
    return state_path(Path(root), f'tasks/do-{task_id}')


@contextmanager
def _lock(folder, name='control.lock'):
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (folder / name).open('a') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        yield


def _agent(agent):
    if agent not in AGENTS:
        raise RemError('agent must be codex or claude')
    return agent


def reserve(root, outcome, by='owner', agent='codex'):
    """Queue without a model call. Host and night share this idempotent claim."""
    _agent(agent)
    task_id = identity(outcome.get('key') or outcome['keys'][0])
    folder = directory(root, task_id)
    with _lock(folder):
        if saved := read_json(folder / 'receipt.json', {}):
            return saved
        receipt = {'id': task_id, 'result': 'queued', 'queued_at': now().isoformat(), 'by': by, 'agent': agent,
                   'key': outcome.get('key') or outcome['keys'][0], 'keys': outcome['keys'],
                   'record': outcome.get('record', ''), 'title': outcome['title'], 'text': outcome['text'],
                   'prompt': outcome.get('task', {}).get('prompt') or f"Prepare the work owed: {outcome['text']}",
                   'receipt': str(folder / 'receipt.json'), 'deliverable': str(folder / 'result.md'),
                   'last_message': str(folder / 'last.md'), 'log': str(folder / 'codex.jsonl')}
        write_json(folder / 'receipt.json', receipt)
        return receipt


def _project_dir(root, receipt):
    """The one project directory the obligation's page links to, or None."""
    from .files import Notebook
    from .investigate import project_paths
    record = receipt['record']
    book = Notebook(root)
    pages = [record] if record.startswith('projects/') else []
    if record and not pages:
        # Follow only the obligation page's explicit project links.
        text = book.read(record)
        for link in re.findall(r'\]\(([^)#]+)', text):
            target = (Path(root) / record).parent / link
            resolved = target.resolve()
            if resolved.parent == Path(root).resolve() / 'projects' and resolved.suffix == '.md':
                pages.append(resolved.relative_to(Path(root).resolve()).as_posix())
    paths = [Path(path).expanduser() for page in pages for path in project_paths(book.read(page))]
    existing = {path.resolve() for path in paths if path.is_absolute() and path.is_dir()}
    return existing.pop() if len(existing) == 1 else None


def _git(*args):
    process = subprocess.run(['git', *args], capture_output=True, text=True)
    if process.returncode:
        raise RemError(f"git {args[2]} failed: {process.stderr.strip()}")
    return process.stdout.strip()


def workspace(root, receipt, folder):
    """Codex writes only here: a worktree of the project on its own branch, else work/."""
    work = folder / 'work'
    project = _project_dir(root, receipt)
    if project:
        receipt['project'] = str(project)
        top = subprocess.run(['git', '-C', str(project), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        if top.returncode == 0:
            branch = f"rem/task-{receipt['id']}"
            _git('-C', top.stdout.strip(), 'worktree', 'add', '-q', '-b', branch, str(work), 'HEAD')
            receipt.update(repository=top.stdout.strip(), branch=branch, gitdir=(work / '.git').read_text())
    work.mkdir(exist_ok=True, mode=0o700)
    return work


def _prompt(receipt):
    place = f"Project, to read only: {receipt['project']}\n" if receipt.get('project') else ''
    if receipt.get('branch'):
        place += (f"Your copy is the worktree {receipt['cwd']} on branch {receipt['branch']}: "
                  'change files there and leave them uncommitted for review.\n')
    return (receipt['prompt'] + '\n\n' + place +
            f"Done means: produce reviewable work satisfying this obligation: {receipt['text']} "
            'Include evidence and validation. If inputs are missing, explain them and do not claim completion.\n'
            f"Deliverable: {receipt['deliverable']} — write the result here, including any changed files and checks.\n"
            'End with a one-line summary of the work. '
            'Never push, merge, send mail or post: those stay the owner\'s click. '
            'do not send anything to anyone; write the result and stop')


def _prepared(root, task_id):
    from .night import listing
    return next((row for row in listing(root) if row['kind'] == 'task' and identity(row['key']) == task_id), None)


def start(root, task_id, agent=None):
    """Detach a worker, never a second worker for the same obligation. `agent` changes who
    runs a task that has not started yet; None keeps the receipt's."""
    from .runner import child_env
    root = Path(root).resolve()
    folder = directory(root, task_id)
    task_id = folder.name[3:]
    if not (folder / 'receipt.json').exists():
        outcome = _prepared(root, task_id)
        if not outcome:
            raise RemError('No current prepared task matches this ID; run co rem task status')
        reserve(root, outcome)
    with _lock(folder):
        receipt = read_json(folder / 'receipt.json', {})
        if receipt['result'] != 'queued':
            return _project(receipt)
        receipt['agent'] = _agent(agent or receipt.get('agent', 'codex'))
        command = [sys.executable, '-m', 'connectonion.rem.tasks', '--root', str(root), '--id', task_id]
        with (folder / 'worker.log').open('ab') as output:
            process = subprocess.Popen(command, cwd=root, env=child_env(), stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        receipt.update(result='starting', pid=process.pid, command=' '.join(command[1:]))
        write_json(folder / 'receipt.json', receipt)
        return _project(receipt)


def _interrupted(signum, frame):
    raise InterruptedError('Task stopped by the owner')


def _run(command, log, timeout, receipt, cwd):
    with log.open('w') as output, subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=output,
                                                  stderr=subprocess.STDOUT, start_new_session=True,
                                                  env={**os.environ,
                                                       'TMPDIR': str(Path(receipt['receipt']).parent / 'tmp')}) as process:
        receipt.update(codex_pid=process.pid, codex_command=' '.join(command[:-1]))
        write_json(Path(receipt['receipt']), receipt)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124
        finally:
            if process.poll() is None:
                try:
                    codex_exec._terminate_descendants(process.pid)
                finally:
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


def execute(root, task_id, *, timeout=None):
    """Worker owns the execution lock until Codex and its tools have exited."""
    folder = directory(root, task_id)
    with _lock(folder, 'execute.lock'):
        with _lock(folder):
            receipt = read_json(folder / 'receipt.json', {})
            if receipt.get('result') not in ('queued', 'starting'):
                return _project(receipt)
            receipt.update(result='running', started_at=now().isoformat())
            write_json(folder / 'receipt.json', receipt)
        return _execute(root, folder, receipt, timeout)


def _execute(root, folder, receipt, timeout):
    code, result = None, 'failed'
    try:
        config = read_config(root)
        work = workspace(root, receipt, folder)
        receipt['cwd'] = str(work)
        (folder / 'tmp').mkdir(exist_ok=True, mode=0o700)
        command = _command(receipt.get('agent', 'codex'), work, folder, config, receipt)
        write_json(folder / 'receipt.json', receipt)
        code = _run(command, Path(receipt['log']), timeout or config['limits']['timeout_seconds'], receipt, work)
        if receipt.get('agent') == 'claude':
            _claude_last_message(Path(receipt['log']), Path(receipt['last_message']))
        deliverable = Path(receipt['deliverable'])
        present = deliverable.is_file() and not deliverable.is_symlink() and bool(deliverable.read_text().strip())
        result = 'completed' if code == 0 and present else 'timed-out' if code == 124 else 'failed'
        if code == 0 and not present:
            receipt['reason'] = 'Codex exited successfully without a nonempty deliverable'
    except InterruptedError:
        code, result = 130, 'stopped'
    except (OSError, RemError) as error:
        # Missing executables, inaccessible projects and invalid configs are expected launch failures.
        receipt['reason'] = str(error)
    finally:
        if receipt.get('gitdir'):
            _neuter(folder / 'work', receipt['gitdir'])
        receipt.update(result=result, exit_code=code, finished_at=now().isoformat())
        write_json(folder / 'receipt.json', receipt)
    return _project(receipt)


def _command(agent, work, folder, config, receipt):
    """The agent's own non-interactive run, with full access (D-100), in the task's workspace."""
    if agent == 'codex':
        return codex_exec.exec_command(work, config, last_message=Path(receipt['last_message']),
                                       prompt=_prompt(receipt), add_dirs=(folder,), full_access=True)
    claude = shlex.split(os.environ.get('CLAUDE_CMD', '')) or [shutil.which('claude')]
    if not claude[0]:
        raise RemError('Claude Code CLI not found; install it or set CLAUDE_CMD')
    return [*claude, '-p', _prompt(receipt), '--dangerously-skip-permissions', '--output-format', 'json',
            '--add-dir', str(folder)]


def _claude_last_message(log, last):
    """claude -p --output-format json prints one result object; its text is the run's last message."""
    results = [json.loads(line) for line in log.read_text().splitlines() if line.startswith('{"type": "result"')
               or line.startswith('{"type":"result"')]
    if results and isinstance(results[-1].get('result'), str):
        last.write_text(results[-1]['result'])


def _neuter(work, gitdir):
    """The model wrote this worktree. Before the owner runs git in it, its .git is REM's pointer
    again and no per-worktree config (core.fsmonitor, hooksPath) remains to run on `git status`."""
    marker = work / '.git'
    if marker.is_dir() and not marker.is_symlink():
        shutil.rmtree(marker)
    elif marker.exists() or marker.is_symlink():
        marker.unlink()
    marker.write_text(gitdir)
    (Path(gitdir.split(':', 1)[1].strip()) / 'config.worktree').unlink(missing_ok=True)


def _project(receipt):
    value = {**receipt}
    value.pop('prepared_reply', None)
    deliverable = Path(value['deliverable'])
    if value['result'] == 'completed' and deliverable.is_file() and not deliverable.is_symlink():
        last = Path(value['last_message'])
        summary = last.read_text().strip().splitlines()[0][:240] if last.is_file() and last.read_text().strip() else value['text']
        value['prepared_reply'] = f"REM 已经做完：{summary} · 附：{deliverable}"
    return value


def receipt_for(root, key):
    receipt = read_json(directory(root, identity(key)) / 'receipt.json', {})
    return _project(receipt) if receipt else None


def _reap_codex(receipt):
    pid, command = receipt.get('codex_pid'), receipt.get('codex_command')
    if not pid or not command:
        return
    process = subprocess.run(['ps', '-ww', '-p', str(pid), '-o', 'uid=', '-o', 'command='],
                             capture_output=True, text=True, timeout=2)
    fields = process.stdout.strip().split(maxsplit=1)
    if len(fields) == 2 and fields[0] == str(os.getuid()) and (' ' + command + ' ') in (' ' + fields[1]):
        codex_exec._terminate_descendants(pid)
        with suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)


def _reconcile(folder, *, stopped=False):
    from .live_host import _alive
    with _lock(folder):
        receipt = read_json(folder / 'receipt.json', {})
        if receipt.get('result') in ACTIVE and not _alive(receipt):
            _reap_codex(receipt)
            receipt.update(result='stopped' if stopped else 'failed', exit_code=130 if stopped else None,
                           finished_at=now().isoformat(), reason='Worker exited without a terminal receipt')
            write_json(folder / 'receipt.json', receipt)
        return receipt


def status(root, task_id=None):
    if task_id:
        folder = directory(root, task_id)
        saved = _reconcile(folder) if (folder / 'receipt.json').is_file() else {}
        if saved:
            return _project(saved)
        task_id = directory(root, task_id).name[3:]
        if row := _prepared(root, task_id):
            return {'id': task_id, 'result': 'ready', 'title': row['title'], 'text': row['text']}
        raise RemError('Unknown task ID; run co rem task status')
    from .night import listing
    ready = {identity(row['key']): {'id': identity(row['key']), 'result': 'ready',
                                   'title': row['title'], 'text': row['text']}
             for row in listing(root) if row['kind'] == 'task'}
    for path in state_path(Path(root), 'tasks').glob('do-*/receipt.json'):
        saved = _reconcile(path.parent)
        ready[saved['id']] = _project(saved)
    return list(ready.values())


def stop(root, task_id):
    from .live_host import _alive
    folder = directory(root, task_id)
    with _lock(folder):
        receipt = read_json(folder / 'receipt.json', {})
        if not receipt:
            raise RemError('No receipt for this task; run co rem task status')
        if receipt['result'] not in (*ACTIVE, 'queued'):
            return _project(receipt)
        if receipt['result'] in ACTIVE and _alive(receipt):
            with suppress(ProcessLookupError):
                os.kill(receipt['pid'], signal.SIGTERM)
        else:
            _reap_codex(receipt)
            receipt.update(result='stopped', exit_code=130, finished_at=now().isoformat())
            write_json(folder / 'receipt.json', receipt)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = _project(_reconcile(folder, stopped=True))
        if current['result'] not in ACTIVE:
            return current
        time.sleep(0.05)
    raise RemError('Task has not confirmed stop yet; inspect co rem task status')


def auto_dispatch(root, config):
    """After the night's drafts, start the next owed task REM may start; the rest wait with a reason."""
    if not config['tasks']['auto']:
        _forget_unstarted(root)
        return []
    from .approvals import started, withdrawn
    from .night import listing
    launched = []
    for row in listing(root):
        if (row['kind'] != 'task' or withdrawn(root, row['key']) or receipt_for(root, row['key'])
                or gate(root, config, row['key'])):
            continue
        receipt = reserve(root, row, by='rem')
        started(root, row, receipt)
        launched.append(start(root, receipt['id']))
    return launched


def _forget_unstarted(root):
    """With tasks.auto off nothing will start an unapproved task, so it no longer shows as queued."""
    path = state_path(Path(root), 'tasks/waiting.json')
    waiting = read_json(path, {})
    kept = {key: hold for key, hold in waiting.items() if receipt_for(root, key)}
    if kept != waiting:
        write_json(path, kept)


def gate(root, config, key):
    """None when the task owed for `key` may start now; otherwise why not, kept for its Today card.
    REM's own starts and the owner's approved ones pass the same gate."""
    path = state_path(Path(root), 'tasks/waiting.json')
    waiting = read_json(path, {})
    hold = _hold(root, config)
    if hold != waiting.pop(key, None):
        write_json(path, {**waiting, key: hold} if hold else waiting)
    return hold


def _hold(root, config):
    """Why REM starts no task now, or None. Only the Codex week's floor stops one (D-104): tasks
    run side by side and a night has no count cap."""
    from . import quota
    if floor := quota.floor_block(quota.meter(root, config), config['limits']):
        return {'wait': 'budget', 'reason': floor[0].upper() + floor[1:] + '.'}
    return None


def undo(root, task_id):
    """The owner's Undo: never started again by the night; stop it and remove its work."""
    from .approvals import withdraw
    folder = directory(root, task_id)
    receipt = read_json(folder / 'receipt.json', {})
    if not receipt:
        raise RemError('No receipt for this task; run co rem task status')
    record = withdraw(root, receipt)
    if receipt['result'] in (*ACTIVE, 'queued'):
        stop(root, task_id)
    receipt = read_json(folder / 'receipt.json', {})
    if receipt.get('branch'):
        _git('-C', receipt['repository'], 'worktree', 'remove', '--force', str(folder / 'work'))
        _git('-C', receipt['repository'], 'branch', '-D', receipt['branch'])
    shutil.rmtree(folder)
    return record


def dispatch(root, key, agent='codex'):
    """The owner's 交给 Codex / 交给 Claude on any pending item: reserve its work and start it now."""
    from .night import listing
    _agent(agent)
    row = next((row for row in listing(root) if key in row['keys']), None)
    if row is None:
        raise RemError('No pending item has this key; reload Today')
    return start(root, reserve(root, row, agent=agent)['id'], agent)


def host_dispatch(root, item, agent='codex'):
    """The Host runs the public deterministic CLI, never an extra agent turn."""
    from .runner import child_env
    command = [sys.executable, '-m', 'connectonion.cli.main', 'rem', '--root', str(root),
               '--json', 'task', 'run', item['receipt_id'], '--agent', _agent(item.get('agent', agent))]
    try:
        result = subprocess.run(command, env=child_env(), capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError) as error:
        raise RemError('Task launch not confirmed; inspect co rem task status before retrying') from error
    if result.returncode:
        raise RemError('Task launch failed; inspect co rem task status and the worker log')
    return {'id': item['receipt_id'], 'receipt': str(directory(root, item['receipt_id']) / 'receipt.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--id', required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _interrupted)
    try:
        execute(args.root, args.id)
    except InterruptedError:
        # A stop may arrive while this worker is still acquiring its launch lock.
        folder = directory(args.root, args.id)
        with _lock(folder):
            saved = read_json(folder / 'receipt.json', {})
            saved.update(result='stopped', exit_code=130, finished_at=now().isoformat())
            write_json(folder / 'receipt.json', saved)
