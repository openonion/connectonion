"""Owner thread decisions shared by the reader and both night-run paths."""
import hashlib
import platform
import re
import sqlite3
from contextlib import closing

from .files import Notebook, RemError, maintenance_lock, read_json, state_path, write_json
from .service import now


def done_key(record, text):
    """Match reader.html doneKey, including its display shortening of long IDs."""
    return re.sub(r'\b([0-9a-f]{12})[0-9a-f]{28,}\b', r'\1…', record + '\n' + text, flags=re.I)


def _mail_versions(root, key):
    from .census import CITATION, _thread_sources
    from .reader_model import _cited_row
    record, _, text = key.partition('\n')
    book = Notebook(root)
    if not book.exists(record) or not state_path(root, 'rem.db').is_file():
        return {}
    sources = _thread_sources(book.read(record))
    found = {}
    with closing(sqlite3.connect(state_path(root, 'rem.db'))) as db:
        db.row_factory = sqlite3.Row
        for number in CITATION.findall(text):
            row = _cited_row(db, sources.get(number, ''))
            if row is not None:
                latest = db.execute('select id, time from messages where thread = ? order by time desc, id desc limit 1',
                                    (row['thread'],)).fetchone()
                if latest:
                    found[row['thread']] = dict(latest)
    return found


def observed_versions(root, records):
    """Latest cited versions from one read-only metadata scan, without rereading pages."""
    from .census import _thread_sources
    file = state_path(root, 'rem.db')
    if not file.is_file():
        return {}
    with closing(sqlite3.connect(file.absolute().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute('select id, time, thread, source, body_path from messages')]
    by_id = {row['id']: row for row in rows}
    aliases, latest = {}, {}
    for row in rows:
        thread = row['thread']
        if thread not in latest or (row['time'] is not None, row['time'] or '', row['id']) > (latest[thread]['time'] is not None, latest[thread]['time'] or '', latest[thread]['id']):
            latest[thread] = row
        if row['source'] in ('gmail', 'outlook'):
            digest = hashlib.sha256(row['id'].removeprefix(row['source'] + ':').encode()).hexdigest()[:12]
            body = row['body_path']
            if body is None or body.endswith('.json') and any(body.startswith(f'mail/{folder}/{row["source"]}/{digest}') for folder in ('messages', 'observed')):
                aliases.setdefault(row['source'] + ':' + digest, []).append(row)
    sources = {source for record in records for source in _thread_sources(record['text']).values()}
    resolved = [by_id.get(source) or (aliases[source][0] if len(aliases.get(source, [])) == 1 else None)
                for source in sources]
    return {row['thread']: latest[row['thread']]['id'] for row in resolved if row and row['thread'] is not None}


def listing(root):
    found = read_json(state_path(root, 'threads.json'), {})
    for key, value in found.items():
        if value['state'] == 'skipped':
            latest = _mail_versions(root, key)
            changed = [row['time'] for thread, row in latest.items()
                       if thread in value.get('versions', {}) and row['id'] != value['versions'][thread]]
            if changed:
                value['returned_at'] = max(changed)
    return found


def blocked(root, key, *, states=None):
    value = (listing(root) if states is None else states).get(key, {})
    return value.get('state') in ('done', 'skipped') and not value.get('returned_at')


def set_state(root, key, state, *, device=None, versions=None, keys=None):
    """Open removes the decision and restores its preserved draft, at any time."""
    requested = list(dict.fromkeys([key, *(keys or [])]))
    if (state not in ('done', 'skipped', 'open') or any(
            not isinstance(item, str) or '\n' not in item or len(item) > 32000
            or not Notebook(root).exists(item.partition('\n')[0]) for item in requested)):
        raise RemError('Expected a notebook thread key and state done, skipped or open')
    with maintenance_lock(root):
        keys = list(dict.fromkeys(item for requested_key in requested for item in _matching_keys(root, requested_key)))
        stamp = now().isoformat()
        for item in keys:
            value = _set_state(root, item, state, device=device, versions=versions, at=stamp, keys=keys)
        return {**listing(root).get(key, value), 'keys': keys}


def _matching_keys(root, key):
    from .census import _thread_groups, _thread_items, pages
    book = Notebook(root)
    owner = (read_json(state_path(root, 'map.json'), {}).get('owner') or {}).get('record')
    title = book.read(owner).splitlines()[0].lstrip('# ') if owner and book.exists(owner) else ''
    items = _thread_items(book, pages(root), (title.split() or [''])[0])
    saved = read_json(state_path(root, 'threads.json'), {})
    previous = saved.get(key)
    linked = previous.get('keys', [key]) if previous else [key]
    for group in _thread_groups(items):
        keys = [done_key(record['path'], text) for record, text, sources in group]
        if key in keys:
            return list(dict.fromkeys([*keys, *linked]))
    return linked


def _set_state(root, key, state, *, device=None, versions=None, at=None, keys=None):
    from . import drafts
    found = read_json(state_path(root, 'threads.json'), {})
    found.pop(key, None)
    value = {'state': state, 'at': at or now().isoformat(), 'device': device or platform.node()}
    if state != 'open':
        if keys and len(keys) > 1:
            value['keys'] = keys
        # The page names the mail it showed; a cited thread it could not place is held at the notebook's latest.
        value['versions'] = {**{thread: row['id'] for thread, row in _mail_versions(root, key).items()}, **(versions or {})}
        found[key] = value
    for row in drafts.candidates(root, refresh_index=False):
        if not any(done_key(item['record'], item['text']) == key for item in row['obligations']):
            continue
        saved = read_json(drafts.path(root, row['id']), {})
        if (saved.get('version') != row['version'] or saved.get('status') in ('sent', 'held')
                or state == 'skipped' and versions is not None and row['thread'] in versions and versions[row['thread']] != row['version']):
            continue
        if state != 'open':
            value['draft_id'] = row['id']
            value.setdefault('draft_statuses', {})[row['id']] = {
                'status': saved.get('status_before_skip', saved['status']), 'version': saved['version']}
        if state == 'skipped' and saved['status'] != 'skipped':
            saved['status_before_skip'] = saved['status']
        status = saved['status']
        if state == 'skipped':
            status = 'skipped'
        elif state == 'open' and status in ('skipped', 'discarded'):
            status = saved.pop('status_before_skip', drafts.prepared_status(saved))
        write_json(drafts.path(root, row['id']), {**saved, 'status': status})
    write_json(state_path(root, 'threads.json'), found)
    return value
