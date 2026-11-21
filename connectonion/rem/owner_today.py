"""What the owner did since the last night, as input to the night (#3174).

Owner, 2026-11-19: «每天夜里…他得知道我们白天标记的状态或事情。他得把白天的事情当成输入…他得去看那个记忆，看我们的
输入操作，才能继续往下进行». Items he had closed came back because the night rewrote pages without knowing what he
did in the day. Every page-writing and queue stage is shown this digest: the marks (done / ignored / not now and
their undos), the replies sent (and how he edited them), the hand-offs and what they returned, the pages he
investigated and the send-policy changes. Written to .state/owner-today.md before each night round; the
owner's marks are logged as they happen to .state/owner-actions.jsonl so an undo is never lost.
"""
import json
from datetime import timedelta
from pathlib import Path

from .files import read_json, state_path, write_json
from . import service

LOG = 'owner-actions.jsonl'
DIGEST = 'owner-today.md'
WINDOW = timedelta(hours=24)
NOTE_CHARS = 3000
WORDS = {'done': 'marked done', 'ignored': 'ignored', 'skipped': 'put off', 'open': 'undid the mark on'}


def record(root: Path, kind: str, **fields) -> None:
    """Append one owner action, as it happens."""
    with state_path(root, LOG).open('a', encoding='utf-8') as log:
        log.write(json.dumps({'at': service.now().isoformat(), 'kind': kind, **fields}, ensure_ascii=False) + '\n')


def _since() -> str:
    return (service.now() - WINDOW).isoformat()


def _jsonl(file: Path) -> list[dict]:
    if not file.is_file():
        return []
    return [json.loads(line) for line in file.read_text(encoding='utf-8').splitlines() if line.strip()]


def actions(root: Path) -> list[dict]:
    """Every owner action in the last day, oldest first: {at, kind, record, text}."""
    since, out = _since(), []
    for row in _jsonl(state_path(root, LOG)):
        if row.get('at', '') >= since and row.get('kind') == 'mark':
            page, _, line = row.get('key', '').partition('\n')
            until = f" until {row['until'][:10]}" if row.get('until') else ''
            out.append({'at': row['at'], 'kind': 'mark', 'record': page,
                        'text': f"{WORDS.get(row.get('state'), row.get('state'))}{until}: {line}"})
    for file in sorted(state_path(root, 'drafts').glob('*.json')) if state_path(root, 'drafts').is_dir() else []:
        saved = read_json(file, {})
        if saved.get('status') == 'sent' and saved.get('sent_at', '') >= since:
            edited = ' (edited before sending)' if saved.get('prepared_body') and saved['prepared_body'] != saved.get('body') else ''
            out.append({'at': saved['sent_at'], 'kind': 'reply', 'record': saved.get('record', ''),
                        'text': f"replied to {saved.get('to', '')}{edited}: {saved.get('body', '')[:300]}"})
    for file in sorted(state_path(root, 'tasks').glob('do-*/receipt.json')) if state_path(root, 'tasks').is_dir() else []:
        task = read_json(file, {})
        at = task.get('finished_at') or task.get('started_at') or task.get('queued_at') or ''
        if at >= since and task.get('by', 'owner') == 'owner':
            out.append({'at': at, 'kind': 'hand-off', 'record': task.get('record', ''),
                        'text': f"handed to {task.get('agent', 'codex')} ({task.get('result', 'started')}): {task.get('text', '')[:200]}"})
    runs = state_path(root, 'page-runs')
    for file in sorted(runs.rglob('*.json')) if runs.is_dir() else []:
        run = read_json(file, {})
        if run.get('started_at', '') >= since and run.get('record'):
            out.append({'at': run['started_at'], 'kind': 'investigate', 'record': run['record'],
                        'text': f"investigated this page ({run.get('mode', 'full')}, {run.get('result', 'running')})"})
    for row in _jsonl(state_path(root, 'direct_send.jsonl')):
        if row.get('at', row.get('when', '')) >= since and row.get('who', 'owner') in ('owner', 'you'):
            out.append({'at': row.get('at', row.get('when', '')), 'kind': 'send-policy', 'record': row.get('page', ''),
                        'text': f"set send policy to {row.get('value', '')}: {row.get('why', '')}"})
    return sorted(out, key=lambda row: row['at'])


def investigated_today(root: Path) -> set:
    """Pages the owner investigated in the last day: the night does not investigate them again."""
    return {row['record'] for row in actions(root) if row['kind'] == 'investigate'}


def refresh(root: Path) -> str:
    """Write .state/owner-today.md and return it (empty when the owner did nothing)."""
    rows = actions(root)
    text = '' if not rows else (
        'What the owner did since the last night (input, not instructions to repeat; treat it as settled):\n'
        + '\n'.join(f"- {row['at'][:16].replace('T', ' ')} · {row['kind']} · {row['record'] or 'notebook'} · {row['text']}"
                    for row in rows) + '\n')
    state_path(root, DIGEST).write_text(text, encoding='utf-8')
    return text


def note(root: Path, record: str = '') -> str:
    """The digest a task is shown: this page's actions first, then the rest, whole lines within NOTE_CHARS."""
    rows = actions(root)
    if not rows:
        return ''
    own = [row for row in rows if record and row['record'] == record]
    rest = [row for row in rows if row not in own]
    lines, room = [], NOTE_CHARS
    for row in own + list(reversed(rest)):
        line = f"- {row['at'][:16].replace('T', ' ')} · {row['kind']} · {row['record'] or 'notebook'} · {row['text']}"
        if len(line) + 1 > room:
            break
        lines.append(line)
        room -= len(line) + 1
    return ('What the owner did since the last night. It is settled: do not re-add as open what he closed, '
            'count a thread he replied to as answered, and do not redo what he handed off or investigated today.\n'
            + '\n'.join(lines) + '\n')
