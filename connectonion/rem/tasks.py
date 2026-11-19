"""One owner-owed obligation, one Codex or Claude Code run, one durable deliverable receipt."""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager, suppress
from pathlib import Path

from . import codex_exec
from .config import read_config
from .files import RemError, read_json, state_path, write_json
from .service import now


ACTIVE = ('starting', 'running')
FAILED = ('failed', 'stopped', 'timed-out')
# Who does the work: the owner's 交给 Codex / 交给 Claude. One runner, the agent as data:
# each is co's own native integration, reached through co ai's harness by its harness name.
HARNESSES = {'codex': 'codex', 'claude': 'claude-code'}
AGENTS = tuple(HARNESSES)
# D-100: full access, in each agent's own words -- Codex's sandbox, Claude Code's permission
# mode. Pushing, merging and sending stay the owner's click, by the prompt.
FULL_ACCESS = {'sandbox': 'danger-full-access', 'permission_mode': 'bypassPermissions'}
# Set by the owner's Stop (SIGTERM). The providers turn an exception inside their run into an
# error result after ending their process, so the worker reads the stop from here, not from it.
_STOPPED = threading.Event()


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
    import fcntl  # POSIX-only, imported here: the reader reads receipts through this module on Windows
    with (folder / name).open('a', encoding='utf-8') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        yield


def _agent(agent):
    if agent not in AGENTS:
        raise RemError('agent must be codex or claude')
    return agent


def reserve(root, outcome, by='owner', agent='codex'):
    """Queue without a model call. Host and night share this idempotent claim."""
    from .languages import owner_language
    _agent(agent)
    task_id = identity(outcome.get('key') or outcome['keys'][0])
    folder = directory(root, task_id)
    with _lock(folder):
        if saved := read_json(folder / 'receipt.json', {}):
            return saved
        receipt = {'id': task_id, 'result': 'queued', 'queued_at': now().isoformat(), 'by': by, 'agent': agent,
                   'key': outcome.get('key') or outcome['keys'][0], 'keys': outcome['keys'],
                   'record': outcome.get('record', ''), 'title': outcome['title'], 'text': outcome['text'],
                   'language': owner_language(root) or read_config(root)['language'],
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
    process = subprocess.run(['git', *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if process.returncode:
        raise RemError(f"git {args[2]} failed: {process.stderr.strip()}")
    return process.stdout.strip()


def workspace(root, receipt, folder):
    """Codex writes only here: a worktree of the project on its own branch, else work/."""
    work = folder / 'work'
    project = _project_dir(root, receipt)
    if project:
        receipt['project'] = str(project)
        top = subprocess.run(['git', '-C', str(project), 'rev-parse', '--show-toplevel'], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if top.returncode == 0:
            branch = f"rem/task-{receipt['id']}" + (f"-{receipt['attempt']}" if receipt.get("attempt") else "")
            _git('-C', top.stdout.strip(), 'worktree', 'add', '-q', '-b', branch, str(work), 'HEAD')
            receipt.update(repository=top.stdout.strip(), branch=branch, gitdir=(work / '.git').read_text(encoding="utf-8"))
    work.mkdir(exist_ok=True, mode=0o700)
    return work


def _prompt(receipt):
    from .languages import native_name
    language = receipt.get('language', 'en')
    tab = 'rem-' + receipt['id']
    place = f"Project, to read only: {receipt['project']}\n" if receipt.get('project') else ''
    if receipt.get('branch'):
        place += (f"Your copy is the worktree {receipt['cwd']} on branch {receipt['branch']}: "
                  'change files there and leave them uncommitted for review.\n')
    return (receipt['prompt'] + '\n\n' + place +
            f"Done means: produce reviewable work satisfying this obligation: {receipt['text']} "
            'Include evidence and validation. If inputs are missing, explain them and do not claim completion.\n'
            f"Deliverable: {receipt['deliverable']} — write the result here, including any changed files and checks.\n"
            f"Write the report in the notebook owner's language: {native_name(language)} ({language}). "
            'Start with a one-line summary, then the full report. '
            'Put any proposed reply in a fenced block marked reply (```reply\n...\n```). '
            f'For browser work, first run co browser tab open {tab}; use -t {tab} on every browser command. '
            f'At the end, close your tab with co browser tab close {tab}. Never use the default shared tab. '
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
        pid, session = _in_tmux(root, folder, task_id, command, child_env())
        if pid is None:
            with (folder / 'worker.log').open('ab') as output:
                pid = subprocess.Popen(command, cwd=root, env=child_env(), stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, start_new_session=True).pid
        receipt.update(result='starting', pid=pid, command=' '.join(command[1:]), **({'tmux': session} if session else {}))
        write_json(folder / 'receipt.json', receipt)
        return _project(receipt)


# #3138 (owner, 2026-11-19: «能不能在终端里直接用 tmux 之类的启动一个后台 session，这样我就可以接着做，或者能看到它
# 的进度？»): with tmux on this computer the worker runs in a named session the owner can attach to and watch.
# Without it, a plain detached process, as before. `env -i` hands the worker REM's own environment and then
# execs it, so the pane's pid is the worker's and `_alive` recognises it as before.
def _tmux():
    return shutil.which('tmux')


def tmux_name(task_id):
    return 'rem-' + task_id[:12]


def _in_tmux(root, folder, task_id, command, env):
    """(worker pid, session name) when tmux started it, else (None, None)."""
    tmux = _tmux()
    if not tmux:
        return None, None
    attempt = read_json(folder / "receipt.json", {}).get("attempt")
    name = tmux_name(task_id) + (f"-{attempt}" if attempt else "")
    started = subprocess.run([tmux, 'new-session', '-d', '-s', name, '-x', '160', '-y', '48', '-c', str(root), '-P', '-F', '#{pane_pid}',
                              'env', '-i', *[f'{key}={value}' for key, value in env.items()], *command],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, stdin=subprocess.DEVNULL)
    pid = started.stdout.strip()
    if started.returncode != 0 or not pid.isdigit():
        return None, None
    # The pane is also the worker's log, as the detached process's stdout was.
    subprocess.run([tmux, 'pipe-pane', '-o', '-t', name, f"cat >> '{folder / 'worker.log'}'"],
                   capture_output=True, timeout=10, stdin=subprocess.DEVNULL)
    return int(pid), name


def _interrupted(signum, frame):
    # Only record it: an exception raised here lands wherever the worker is, and inside
    # the Codex client's lock waits it hung the worker. The run polls _STOPPED instead.
    _STOPPED.set()


@contextmanager
def _tmpdir(path):
    """The agent's scratch files go in the task's own tmp/, removed with the task."""
    previous = os.environ.get('TMPDIR')
    os.environ['TMPDIR'] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('TMPDIR')
        else:
            os.environ['TMPDIR'] = previous


def _delegate(receipt, folder, config, timeout):
    """The agent's own run through co's native integration, in the task's workspace.
    Returns the exit code the receipt keeps: 0 done, 124 out of time, 1 anything else."""
    from ..cli.co_ai import harness
    agent = receipt.get('agent', 'codex')
    # REM's model names a Codex model; Claude Code keeps its own, and the owner's own
    # Claude setup loads (context over control): user_setup.
    model = config['model'] if agent == 'codex' and config['model'] != 'default' else ''
    if _STOPPED.is_set():
        raise InterruptedError('Task stopped by the owner')
    with _tmpdir(folder / 'tmp'):
        answer = harness.run(HARNESSES[agent], _prompt(receipt), model, cwd=receipt['cwd'],
                             timeout=math.ceil(timeout), effort=config['effort'], add_dirs=(str(folder),),
                             user_setup=True, cancelled=_STOPPED.is_set, on_activity=_step_writer(folder), **FULL_ACCESS)
    if _STOPPED.is_set():
        raise InterruptedError('Task stopped by the owner')
    Path(receipt['log']).write_text(json.dumps(answer, ensure_ascii=False) + '\n', encoding='utf-8')
    if answer['result']:
        Path(receipt['last_message']).write_text(answer['result'], encoding='utf-8')
    receipt['session_id'] = answer.get('session_id')  # resumable in the agent's own app
    if answer['error']:
        receipt['reason'] = answer['error']
    return {'natural': 0, 'timeout': 124}.get(answer['outcome'], 1)


# What the agent is doing, while it does it (#3138): each step co ai's Work Room would show (an OIP
# provider_activity: a fixed phrase such as "Running the requested tests", never the command), one line of
# events.jsonl. The status a page polls reads the last one; the worker's own output, the tmux pane, says it too.
STEP_FIELDS = ('kind', 'status', 'title', 'summary', 'files')


def _step_writer(folder):
    path = folder / 'events.jsonl'

    def write(activity):
        step = {'at': now().isoformat(), **{key: activity[key] for key in STEP_FIELDS if key in activity}}
        with path.open('a', encoding='utf-8') as out:
            out.write(json.dumps(step, ensure_ascii=False) + '\n')
        print(f"{step['at'][11:19]}  {step.get('summary', '')}", flush=True)
    return write


def _last_step(folder):
    """(the latest step, how many) from events.jsonl; a half-written last line is skipped."""
    path = folder / 'events.jsonl'
    if not path.is_file():
        return None, 0
    lines = path.read_text(encoding='utf-8').splitlines()
    for line in reversed(lines):
        with suppress(ValueError):
            return json.loads(line), len(lines)
    return None, len(lines)


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
        from .inquiry import stage_config
        config = stage_config(root, read_config(root), 'task')
        work = workspace(root, receipt, folder)
        receipt['cwd'] = str(work)
        (folder / 'tmp').mkdir(exist_ok=True, mode=0o700)
        write_json(folder / 'receipt.json', receipt)
        code = _delegate(receipt, folder, config, timeout or config['limits']['timeout_seconds'])
        deliverable = Path(receipt['deliverable'])
        present = deliverable.is_file() and not deliverable.is_symlink() and bool(deliverable.read_text(encoding="utf-8").strip())
        result = 'completed' if code == 0 and present else 'timed-out' if code == 124 else 'failed'
        if code == 0 and not present:
            receipt['reason'] = f"{receipt.get('agent', 'codex').capitalize()} finished without a nonempty deliverable"
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


def _neuter(work, gitdir):
    """The model wrote this worktree. Before the owner runs git in it, its .git is REM's pointer
    again and no per-worktree config (core.fsmonitor, hooksPath) remains to run on `git status`."""
    marker = work / '.git'
    if marker.is_dir() and not marker.is_symlink():
        shutil.rmtree(marker)
    elif marker.exists() or marker.is_symlink():
        marker.unlink()
    marker.write_text(gitdir, encoding='utf-8')
    (Path(gitdir.split(':', 1)[1].strip()) / 'config.worktree').unlink(missing_ok=True)


def _report(receipt):
    for name in ('deliverable', 'last_message'):
        path = Path(receipt[name])
        if path.is_file() and not path.is_symlink() and (text := path.read_text(encoding="utf-8").strip()):
            return text
    return ''


def _failure(receipt):
    agent = 'Claude' if receipt.get('agent') == 'claude' else 'Codex'
    reason = receipt.get('reason', '')
    if 'Operation not permitted' in reason and agent == 'Codex':
        return 'Codex 当时无法启动（已修复），可以重试'
    if receipt['result'] == 'timed-out':
        return f'{agent} 超时了，可以重试'
    if receipt['result'] == 'stopped':
        return f'{agent} 已停止，可以重试'
    if 'without a nonempty deliverable' in reason:
        return f'{agent} 没有留下报告，可以重试'
    if 'not found' in reason or 'No such file' in reason:
        return f'{agent} 无法启动，请检查安装后重试'
    return f'{agent} 这次未能完成，可以重试'


def _project(receipt):
    value = {**receipt}
    value.pop('prepared_reply', None)
    if value.get('last_message'):
        step, count = _last_step(Path(value['last_message']).parent)
        if step:
            value.update(step=step, steps=count)
    text = _report(value) if value['result'] not in (*ACTIVE, 'queued') else ''
    value['has_output'] = bool(text)
    if value['result'] == 'completed':
        value['summary'] = re.sub(r'^#+\s*', '', text.splitlines()[0])[:240] if text else value['text']
        reply = re.search(r'^```reply[^\S\n]*\n(.*?)^```[ \t]*$', text, re.M | re.S)
        value['reply'] = reply[1].strip() if reply else ''
    elif value['result'] in FAILED:
        value['failure'] = _failure(value)
    return value


def result(root, task_id):
    """The owner's See result: what the agent wrote, from the deliverable or else its last message."""
    receipt = status(root, task_id)
    if receipt['result'] in (*ACTIVE, 'queued', 'ready'):
        raise RemError('The agent is still working; its result shows when it finishes')
    text = _report(receipt)
    return {'id': receipt['id'], 'result': receipt['result'], 'agent': receipt.get('agent', 'codex'),
            'reason': receipt.get('reason', ''), 'text': text}


def receipt_for(root, key):
    receipt = read_json(directory(root, identity(key)) / 'receipt.json', {})
    return _project(receipt) if receipt and not receipt.get('dismissed') else None


def _reap_codex(receipt):
    pid, command = receipt.get('codex_pid'), receipt.get('codex_command')
    if not pid or not command:
        return
    process = subprocess.run(['ps', '-ww', '-p', str(pid), '-o', 'uid=', '-o', 'command='],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2)
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
        if not saved.get('dismissed'):
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


# Pick it up yourself (#3138): a running task's tmux session, or the finished session in its own agent, opened in
# Terminal on this computer. Buttons only (D-60): the command lives in a script REM writes, never on the page.
def _open_in_terminal(script):
    """Open a .command script in Terminal (macOS); tests replace this."""
    if sys.platform != 'darwin':
        raise RemError('Opening a terminal from the page works on macOS; on this computer use the agent directly')
    subprocess.run(['open', '-a', 'Terminal', str(script)], check=True, capture_output=True, timeout=10)


def _terminal_script(folder, name, lines):
    script = folder / f'{name}.command'
    script.write_text('#!/bin/sh\n' + '\n'.join(lines) + '\n', encoding='utf-8')
    script.chmod(0o700)
    return script


def watch(root, task_id):
    """Open Terminal attached to the running task's tmux session."""
    folder = directory(root, task_id)
    receipt = read_json(folder / 'receipt.json', {})
    tmux = _tmux()
    if not receipt.get('tmux') or not tmux:
        raise RemError('This run is not in a terminal session; its progress shows on the page')
    if subprocess.run([tmux, 'has-session', '-t', receipt['tmux']], capture_output=True, timeout=10).returncode != 0:
        raise RemError('The run has ended, so there is no live session to watch')
    _open_in_terminal(_terminal_script(folder, 'watch', [f"exec '{tmux}' attach -t '{receipt['tmux']}'"]))
    return _project(receipt)


RESUME = {'codex': ('codex', 'resume'), 'claude': ('claude', '--resume')}


def resume(root, task_id):
    """Open Terminal in the task's folder with its agent resuming its session, to carry on by hand."""
    folder = directory(root, task_id)
    receipt = read_json(folder / 'receipt.json', {})
    agent, session = receipt.get('agent', 'codex'), receipt.get('session_id')
    if receipt.get('result') in ACTIVE:
        raise RemError('The agent is still working; watch it, or carry on once it finishes')
    if not session or not re.fullmatch(r'[A-Za-z0-9-]{8,80}', session):
        raise RemError('This run kept no session to continue')
    program, flag = RESUME[agent]
    cwd = receipt.get('cwd') or str(folder)
    if "'" in cwd:
        raise RemError('The task folder has a quote in its path; open it in the agent directly')
    _open_in_terminal(_terminal_script(folder, 'resume', [f"cd '{cwd}' || exit 1", f"exec {program} {flag} {session}"]))
    return _project(receipt)


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
                or (directory(root, identity(row['key'])) / 'receipt.json').is_file()
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


class UnknownItem(RemError):
    """The key names no unfinished row: the page is older than the notebook."""


# Who the open item waits on, in the words the agent's prompt gives it.
WAITS_ON = {'mine': 'The owner owes this.',
            'theirs': 'Someone else owes the owner this: prepare what moves it forward, such as a follow-up the owner can send.',
            'plain': 'An open item in the owner\'s notebook.'}


def unfinished(root, key):
    """The unfinished row the reader shows for `key` (any of its copies), as reserve takes it.
    The night's own outcome when it prepared one; otherwise built here from the row itself."""
    from .night import listing
    from .today import queue
    row = next((row for row in queue(root) if key in row['keys'] and not row['closed']), None)
    if row is None:
        raise UnknownItem('This item is no longer open in your notebook. Reload the page to see what is.')
    prepared = next(iter(listing(root, rows=[row])), {})
    if prepared.get('task', {}).get('prompt'):
        return prepared
    prompt = (f"Prepare the work for this open item.\nNotebook page: {row['record']}\n"
              f"Item: {row['text']}\n{WAITS_ON[row['dir']]}\n"
              f"Source: {row['reply'].get('source') or 'the notebook item'}\n"
              'Produce a reviewable result with evidence. State any missing inputs; do not invent completion.')
    return {**{field: row[field] for field in ('key', 'keys', 'record', 'title', 'text')}, 'task': {'prompt': prompt}}


def investigation(root, record):
    """让 Codex 查 (#2909): the owner's request to investigate one private project page, as reserve takes it.
    Automatic investigations skip a private project, so this request is the only way one starts."""
    from .files import Notebook
    from .project_pages import private
    book = Notebook(root)
    if record not in book.list('projects') or not private(record, book.read(record)):
        raise UnknownItem('This private project is no longer in your notebook. Reload the page to see what is.')
    title = book.read(record).split('\n', 1)[0].lstrip('# ').strip()
    prompt = (f"The owner asked you to investigate this private project.\nNotebook page: {record}\n"
              'Read the project itself and say what it is, where the work stands and what is still open, '
              'each with its evidence (files, commits, sessions). Do not edit the notebook page.')
    return {'key': record, 'keys': [record], 'record': record, 'title': title,
            'text': f'Investigate {title}', 'task': {'prompt': prompt}}


def dispatch(root, key, agent='codex'):
    """The owner's 交给 Codex / 交给 Claude on any unfinished row, or 让 Codex 查 on a private project page
    (a row key always holds a newline; a page path never does): reserve its work and start it now."""
    _agent(agent)
    work = unfinished(root, key) if '\n' in key else investigation(root, key)
    saved = read_json(directory(root, identity(work['key'])) / 'receipt.json', {})
    if saved.get('result') in FAILED:
        return retry(root, saved['id'], agent)
    return start(root, reserve(root, work, agent=agent)['id'], agent)


def retry(root, task_id, agent=None):
    """Keep the failed attempt for inspection; a fresh workspace and session for this item."""
    folder = directory(root, task_id)
    with _lock(folder.parent, folder.name + '.retry.lock'):
        saved = read_json(folder / 'receipt.json', {})
        if saved.get('result') not in FAILED:
            raise RemError('Only a failed or stopped task can be retried')
        work = unfinished(root, saved['key']) if '\n' in saved['key'] else investigation(root, saved['key'])
        history = folder.parent / 'history'
        history.mkdir(exist_ok=True, mode=0o700)
        archived = history / f"{folder.name}-{time.time_ns()}"
        folder.rename(archived)
        _archive_receipt(saved, folder, archived)
        receipt = reserve(root, work, by='owner', agent=agent or saved.get('agent', 'codex'))
        receipt['attempt'] = saved.get('attempt', 0) + 1
        write_json(Path(receipt['receipt']), receipt)
        return start(root, receipt['id'], agent)


def _archive_receipt(saved, folder, archived):
    for field in ('receipt', 'deliverable', 'last_message', 'log', 'cwd'):
        if saved.get(field):
            saved[field] = str(archived / Path(saved[field]).relative_to(folder))
    if saved.get('repository'):
        _git('-C', saved['repository'], 'worktree', 'repair', str(archived / 'work'))
        saved['gitdir'] = (archived / 'work' / '.git').read_text(encoding="utf-8")
    write_json(archived / 'receipt.json', saved)


def clear_failed(root):
    """Hide old failures together without deleting their evidence or stopping live work."""
    cleared = []
    for path in state_path(Path(root), 'tasks').glob('do-*/receipt.json'):
        with _lock(path.parent):
            saved = read_json(path, {})
            if saved.get('result') in FAILED and not saved.get('dismissed'):
                write_json(path, {**saved, 'dismissed': True})
                cleared.append(saved['id'])
    return {'cleared': cleared}


def prepare_reply(root, task_id):
    """Promote the report's reply to the existing local draft store. Never send or open mail."""
    from . import drafts
    receipt = status(root, task_id)
    folder = directory(root, task_id)
    with _lock(folder):
        saved = read_json(folder / 'receipt.json', {})
        if draft_id := saved.get('draft_id'):
            return drafts._current(root, draft_id, refresh_index=False)
        draft = _prepare_reply(root, receipt)
        write_json(folder / 'receipt.json', {**saved, 'draft_id': draft['id']})
        return draft


def _prepare_reply(root, receipt):
    from . import drafts, threads
    if receipt['result'] != 'completed' or not receipt.get('reply'):
        raise RemError('This task has no reply draft')
    rows = [row for row in drafts.candidates(root, refresh_index=False)
            if any(threads.done_key(item['record'], item['text']) in receipt['keys'] for item in row['obligations'])]
    if len(rows) != 1:
        raise RemError('This item must match one current mail thread before preparing its reply')
    row = rows[0]
    drafts._not_held(read_json(drafts.path(root, row['id']), {}))
    plan = {key: val for key, val in row.items() if key not in ('material', 'obligations')}
    drafts.promote(root, {**plan, 'body': receipt['reply'], 'sources': [item['source'] for item in row['material']],
                          'verdict': 'reply', 'send': 'owner', 'needs_owner': [], 'channel': 'mail',
                          'gist': receipt['summary'], 'why': receipt['summary']})
    return read_json(drafts.path(root, row['id']), {})


def task_file(root, task_id, name):
    """Resolve only a file inside this task's work folder, including through symlinks."""
    folder = directory(root, task_id)
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts or folder.is_symlink() or not (folder / 'receipt.json').is_file():
        raise RemError('No such task file')
    if relative.parts[:1] == ('work',):
        relative = Path(*relative.parts[1:])
    work = (folder / 'work').resolve()
    # A work directory symlink must not turn another directory into this task's work.
    if work != folder.resolve() / 'work':
        raise RemError('No such task file')
    path = (work / relative).resolve()
    if not path.is_relative_to(work) or not path.is_file():
        raise RemError('No such task file')
    return path


def host_dispatch(root, item, agent='codex'):
    """The Host runs the public deterministic CLI, never an extra agent turn."""
    from .runner import child_env
    command = [sys.executable, '-m', 'connectonion.cli.main', 'rem', '--root', str(root),
               '--json', 'task', 'run', item['receipt_id'], '--agent', _agent(item.get('agent', agent))]
    try:
        result = subprocess.run(command, env=child_env(), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
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
    execute(args.root, args.id)
