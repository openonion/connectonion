"""The morning's prepared outcomes and durable, owner-approved outbox."""

import hashlib
from datetime import datetime, timedelta

from requests import RequestException
from httpx import HTTPError
from googleapiclient.errors import HttpError

from . import drafts, threads, today, service
from .files import RemError, maintenance_lock, read_json, state_path, write_json


def _id(kind, key):
    return kind + ':' + hashlib.sha256(key.encode()).hexdigest()[:32]


def outcomes(root, *, rows=None, prepared=None):
    rows = today.queue(root) if rows is None else rows
    prepared = drafts.listing(root) if prepared is None else prepared
    result, covered = [], set()
    for draft in prepared:
        if draft.get('status') not in ('prepared', 'no_reply'):
            continue
        members = [row for row in rows if row.get('reply', {}).get('thread') == draft.get('thread')
                   and row.get('reply', {}).get('provider') == draft.get('provider')]
        keys = [key for row in members for key in row['keys']]
        if members and all(row['closed'] for row in members):
            continue
        kind = 'handled' if draft.get('status') == 'no_reply' else 'reply'
        if kind == 'handled' and not keys:
            continue
        covered.update(keys)
        result.append({**{key: draft.get(key, '') for key in ('to', 'subject', 'body', 'provider')},
                       'id': _id(kind, draft['id'] + draft['version']), 'kind': kind,
                       'draft_id': draft['id'], 'version': draft['version'], 'keys': keys, 'private': draft.get('private', False),
                       'title': members[0]['title'] if members else draft.get('to', ''),
                       'text': draft.get('gist') or draft.get('why') or '',
                       'blocked': kind == 'reply' and drafts.has_slots(draft.get('body', ''))})
    for row in rows:
        kind = {'replied': 'handled', 'task': 'task'}.get(row.get('reply', {}).get('state'))
        if not kind or row['closed'] or row['quiet'] or row['dir'] != 'mine' or covered.intersection(row['keys']):
            continue
        from .tasks import receipt_for
        if kind == 'task' and receipt_for(root, row['key']):
            continue
        from .night import _task as prepared_task
        task = prepared_task(root, {**row, 'record': row.get('record') or row['key'].split('\n')[0]}) if kind == 'task' else {}
        result.append({**task, 'id': _id(kind, row['key']), 'kind': kind, 'keys': row['keys'],
                       'title': row['title'], 'text': row.get('reply', {}).get('promise') or row['text'], 'blocked': False})
    queued = read_json(state_path(root, 'approvals.json'), {})
    return [item for item in result if queued.get(item['id'], {}).get('status') not in
            ('held', 'queued', 'dispatching', 'dispatched', 'done', 'sent', 'sending', 'scheduling', 'error')]


def pending(root):
    return [value for value in read_json(state_path(root, 'approvals.json'), {}).values()
            if value['status'] in ('held', 'queued', 'error', 'sending', 'scheduling', 'dispatching')]


def _save(root, queue, item):
    queue[item['id']] = item
    write_json(state_path(root, 'approvals.json'), queue)
    return item


def _reply(root, item, body, release_at):
    saved = drafts._current(root, item['draft_id'])
    if saved['version'] != item['version'] or saved.get('status') != 'prepared':
        raise RemError('This reply is no longer prepared; reload Today')
    text = saved['body'] if body is None else body
    if not text.strip() or drafts.has_slots(text):
        raise RemError('Fill the marked part first / 先填好标出的部分')
    claim = {**item, 'body': text, 'status': 'scheduling', 'release_at': release_at}
    _save(root, read_json(state_path(root, 'approvals.json'), {}), claim)
    write_json(drafts.path(root, saved['id']), {**saved, 'body': text, 'status': 'held'})
    receipt = None
    if saved['provider'] == 'outlook' and saved.get('channel', 'mail') == 'mail':
        receipt = drafts.mail_client('outlook').reply(saved['in_reply_to'], text, cc=saved.get('cc') or None,
                                                     send_at=release_at, return_receipt=True)
        if not isinstance(receipt, dict) or not receipt.get('id'):
            raise RemError('Outlook did not return a scheduled message id')
    return {**item, 'body': text, 'blocked': False, 'status': 'held', 'release_at': release_at, 'receipt': receipt}


def _handled(root, item, body, release_at):
    for key in item['keys']:
        threads._set_state(root, key, 'done', keys=item['keys'])
    return {**item, 'status': 'done'}


def _task(root, item, body, release_at):
    from .tasks import reserve
    receipt = reserve(root, item)
    return {**item, 'status': 'queued', 'receipt_id': receipt['id']}


def started(root, item, receipt):
    """A task REM started itself, recorded like an approval so Today names who started it.
    The night caller already holds the notebook lock."""
    queue = read_json(state_path(root, 'approvals.json'), {})
    key = _id('task', item['key'])
    if key in queue:
        return queue[key]
    return _save(root, queue, {'id': key, 'kind': 'task', 'keys': item['keys'], 'title': item['title'],
                               'text': item['text'], 'status': 'dispatched', 'by': 'rem',
                               'receipt_id': receipt['id'], 'dispatched_at': service.now().isoformat(),
                               'result': {'id': receipt['id'], 'receipt': receipt['receipt']}})


def withdrawn(root, key):
    return read_json(state_path(root, 'approvals.json'), {}).get(_id('task', key), {}).get('status') == 'cancelled'


def withdraw(root, receipt):
    """The owner undid a task: the night never starts it again; morning approval still can."""
    with maintenance_lock(root):
        queue = read_json(state_path(root, 'approvals.json'), {})
        key = _id('task', receipt['key'])
        record = queue.get(key) or {'id': key, 'kind': 'task', 'keys': receipt['keys'],
                                    'title': receipt['title'], 'text': receipt['text']}
        return _save(root, queue, {**record, 'status': 'cancelled', 'cancelled_at': service.now().isoformat()})


# A new prepared outcome kind adds one handler here; the reader renders the common fields.
ACTIONS = {'reply': _reply, 'handled': _handled, 'task': _task}


def approve(root, ids, *, bodies=None):
    with maintenance_lock(root):
        return _approve(root, ids, bodies=bodies)


def send_direct(root, draft_id):
    """A reply the writer marked send=now, for someone the owner trusts REM with,
    goes out through the same 10-minute hold and Undo, recorded as REM's decision."""
    saved = read_json(drafts.path(root, draft_id), {})
    if saved.get('send') != 'now' or saved.get('status') != 'prepared' or drafts.has_slots(saved.get('body', '')):
        return None
    item = next((item for item in outcomes(root) if item.get('draft_id') == draft_id and item['kind'] == 'reply'), None)
    return _approve(root, [item['id']], by='rem') if item else None


def _approve(root, ids, *, bodies=None, by='owner'):
    release_at = (service.now() + timedelta(minutes=10)).isoformat()
    available = {item['id']: item for item in outcomes(root)}
    queue = read_json(state_path(root, 'approvals.json'), {})
    results = []
    for key in dict.fromkeys(ids):
        previous = queue.get(key)
        if previous and previous['status'] != 'cancelled':
            results.append(previous)
            continue
        item = available.get(key)
        # Invalid selections and provider rejections are expected per-item failures.
        try:
            if item is None:
                raise RemError('This outcome is no longer current; reload Today')
            value = ACTIONS[item['kind']](root, item, (bodies or {}).get(key), release_at)
            results.append(_save(root, queue, {**value, 'by': by}))
        except (RemError, ValueError, RequestException, HTTPError, HttpError) as error:
            claim = read_json(state_path(root, 'approvals.json'), {}).get(key)
            failure = {'id': key, 'status': 'error', 'error': str(error)}
            results.append(_save(root, queue, {**claim, **failure}) if claim else failure)
    return {'release_at': release_at, 'results': results}


def undo(root, ids):
    with maintenance_lock(root):
        queue = read_json(state_path(root, 'approvals.json'), {})
        results = []
        for key in dict.fromkeys(ids):
            item = queue.get(key)
            try:
                if not item or item['status'] != 'held' or service.now() >= datetime.fromisoformat(item['release_at']):
                    raise RemError('This send is no longer held')
                if item.get('receipt'):
                    drafts.mail_client('outlook').cancel_scheduled(item['receipt']['id'])
                saved = read_json(drafts.path(root, item['draft_id']), {})
                if saved.get('version') == item['version'] and saved.get('status') == 'held':
                    write_json(drafts.path(root, item['draft_id']), {**saved, 'status': 'prepared'})
                results.append(_save(root, queue, {**item, 'status': 'cancelled'}))
            except (RemError, ValueError, RequestException, HTTPError, HttpError) as error:
                results.append({'id': key, 'status': 'error', 'error': str(error)})
        return {'results': results}


def release(root, *, at=None, dispatch=None):
    """Host tick; claim before external IO. Ambiguous failures never auto-resend."""
    at = at or service.now()
    with maintenance_lock(root):
        queue = read_json(state_path(root, 'approvals.json'), {})
        ready = [item for item in queue.values() if
                 (item['status'] == 'held' and at >= datetime.fromisoformat(item['release_at']))
                 or (item['status'] == 'queued' and dispatch is not None)]
    # Release due replies before starting potentially long task turns.
    ready.sort(key=lambda item: item['kind'] == 'task')
    return [value for item in ready if (value := _release_one(root, item['id'], at, dispatch))]


def _waits(root, key):
    """An approved task passes the same gate as REM's own: one at a time, the nightly cap, the floor."""
    from . import tasks
    from .config import read_config
    item = read_json(state_path(root, 'approvals.json'), {})[key]
    if item['kind'] != 'task' or item['status'] != 'queued':
        return None
    return tasks.gate(root, read_config(root), item['key'])


def _release_one(root, key, at, dispatch):
    if dispatch is not None and _waits(root, key):
        return None
    with maintenance_lock(root):
        queue = read_json(state_path(root, 'approvals.json'), {})
        item = queue[key]
        task = item['status'] == 'queued' and dispatch is not None
        held = item['status'] == 'held' and at >= datetime.fromisoformat(item['release_at'])
        if not task and not held:
            return None
        _save(root, queue, {**item, 'status': 'dispatching' if task else 'sending'})
    # In particular, an agent turn must never own the notebook maintenance lock.
    try:
        if task:
            receipt = dispatch(item)
        else:
            with maintenance_lock(root):
                receipt = _deliver(root, item, at)
        value = {**item, 'status': 'dispatched' if task else 'sent', 'result': receipt,
                 **({'dispatched_at': service.now().isoformat()} if task else {})}
    except (RemError, ValueError, RequestException, HTTPError, HttpError) as error:
        value = {**item, 'status': 'error', 'error': str(error)}
    with maintenance_lock(root):
        return _save(root, read_json(state_path(root, 'approvals.json'), {}), value)


def _deliver(root, item, at):
    if not item.get('receipt'):
        saved = drafts._current(root, item['draft_id'])
        if saved.get('version') != item['version'] or saved.get('status') != 'held':
            raise RemError('This held reply changed; delivery stopped. Check the latest draft.')
        return drafts._send_locked(root, item['draft_id'], item['body'], held=True)
    saved = read_json(drafts.path(root, item['draft_id']), {})
    if saved.get('version') == item['version'] and saved.get('status') == 'held':
        write_json(drafts.path(root, item['draft_id']), {**saved, 'status': 'sent', 'sent_at': at.isoformat(),
                                                      'sent_receipt': item['receipt']})
    return item['receipt']
