"""One owner-owed obligation, one Codex process, one durable deliverable receipt."""

import argparse
import fcntl
import hashlib
import os
import re
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


def reserve(root, outcome):
    """Queue without a model call. Host and night share this idempotent claim."""
    task_id = identity(outcome.get('key') or outcome['keys'][0])
    folder = directory(root, task_id)
    with _lock(folder):
        if saved := read_json(folder / 'receipt.json', {}):
            return saved
        receipt = {'id': task_id, 'result': 'queued', 'queued_at': now().isoformat(),
                   'key': outcome.get('key') or outcome['keys'][0], 'keys': outcome['keys'],
                   'record': outcome.get('record', ''), 'title': outcome['title'], 'text': outcome['text'],
                   'prompt': outcome.get('task', {}).get('prompt') or f"Prepare the work owed: {outcome['text']}",
                   'receipt': str(folder / 'receipt.json'), 'deliverable': str(folder / 'result.md'),
                   'last_message': str(folder / 'last.md'), 'log': str(folder / 'codex.jsonl')}
        write_json(folder / 'receipt.json', receipt)
        return receipt


def project_workdir(root, receipt, folder):
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
    existing = [path.resolve() for path in paths if path.is_absolute() and path.is_dir()]
    if len(set(existing)) == 1:
        return existing[0]
    work = folder / 'work'
    work.mkdir(exist_ok=True, mode=0o700)
    return work


def _prompt(receipt):
    return (receipt['prompt'] + '\n\n'
            f"Done means: produce reviewable work satisfying this obligation: {receipt['text']} "
            'Include evidence and validation. If inputs are missing, explain them and do not claim completion.\n'
            f"Deliverable: {receipt['deliverable']} — write the result here, including any changed files and checks.\n"
            'End with a one-line summary of the work. '
            'do not send anything to anyone; write the result and stop')


def _prepared(root, task_id):
    from .night import listing
    return next((row for row in listing(root) if row['kind'] == 'task' and identity(row['key']) == task_id), None)


def start(root, task_id):
    """Detach a worker, never a second worker for the same obligation."""
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
        command = [sys.executable, '-m', 'connectonion.rem.tasks', '--root', str(root), '--id', task_id]
        with (folder / 'worker.log').open('ab') as output:
            process = subprocess.Popen(command, cwd=root, env=child_env(), stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        receipt.update(result='starting', pid=process.pid, command=' '.join(command[1:]))
        write_json(folder / 'receipt.json', receipt)
        return _project(receipt)


def _interrupted(signum, frame):
    raise InterruptedError('Task stopped by the owner')


def _run(command, log, timeout, receipt):
    with log.open('w') as output, subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output,
                                                  stderr=subprocess.STDOUT, start_new_session=True) as process:
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
        work = project_workdir(root, receipt, folder)
        receipt['cwd'] = str(work)
        command = codex_exec.exec_command(work, config, last_message=Path(receipt['last_message']),
                                          prompt=_prompt(receipt), add_dirs=(folder,))
        write_json(folder / 'receipt.json', receipt)
        code = _run(command, Path(receipt['log']), timeout or config['limits']['timeout_seconds'], receipt)
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
        receipt.update(result=result, exit_code=code, finished_at=now().isoformat())
        write_json(folder / 'receipt.json', receipt)
    return _project(receipt)


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
    if not config.get('tasks', {}).get('auto', False):
        return []
    from .night import listing
    return [start(root, reserve(root, row)['id']) for row in listing(root) if row['kind'] == 'task']


def host_dispatch(root, item):
    """The Host runs the public deterministic CLI, never an extra agent turn."""
    from .runner import child_env
    command = [sys.executable, '-m', 'connectonion.cli.main', 'rem', '--root', str(root),
               '--json', 'task', 'run', item['receipt_id']]
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
