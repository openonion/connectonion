"""One current, reviewable outcome per owner-owed Today item; never sends or closes it."""

import hashlib
import json

from . import drafts, service, threads, today
from .files import read_json, state_path, write_json


def _owed(rows):
    return [row for row in rows if row['dir'] == 'mine' and not row['closed']]


def _revision(row):
    evidence = [row['text'], row['keys'], row['reply']]
    return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()


def _base(row, kind, **fields):
    return {**{key: row[key] for key in ('key', 'keys', 'record', 'title', 'text')},
            'kind': kind, 'source': row['reply'].get('source', ''), **fields}


def _draft_for(row, candidates):
    keys = set(row['keys'])
    return next((draft for draft in candidates if draft['version'] == row['reply'].get('source')
                 and any(threads.done_key(item['record'], item['text']) in keys
                         for item in draft['obligations'])), None)


def _draft_outcome(root, row, draft):
    if draft.get('status') == 'sent':
        words = today._owner_words(draft['body'])
        if today._future_commitment(words) or today._unanswered(words):
            return _task(root, row, words=words) | {'draft_id': draft['id'], 'prepared_at': draft.get('sent_at')}
        return _base(row, 'already_handled', draft_id=draft['id'], owner_quote=draft['body'],
                     reason='The prepared reply was sent.', prepared_at=draft.get('sent_at'))
    return _base(row, 'no_reply' if draft['status'] == 'no_reply' else 'prepared',
                 draft_id=draft['id'], prepared_at=draft.get('prepared_at'),
                 reason=draft.get('why') or draft.get('gist', ''))


def listing(root, *, rows=None):
    """Read-only, evidence-checked projection; stale verdicts never reach the morning."""
    rows = _owed(today.queue(root) if rows is None else rows)
    saved = read_json(state_path(root, 'night.json'), {}).get('items', {})
    candidates = drafts.candidates(root, refresh_index=False)
    waiting = read_json(state_path(root, 'tasks/waiting.json'), {})
    result = []
    for row in rows:
        entry = saved.get(row['key'], {})
        outcome = entry.get('outcome') if entry.get('revision') == _revision(row) else None
        candidate = _draft_for(row, candidates) if row['reply']['state'] == 'queued' else None
        draft = read_json(drafts.path(root, candidate['id']), {}) if candidate else {}
        if candidate and draft.get('version') == candidate['version'] and draft.get('status') in ('prepared', 'no_reply', 'sent'):
            outcome = _draft_outcome(root, row, draft)
        if outcome and outcome['kind'] == 'task':
            from .tasks import identity, receipt_for
            receipt = receipt_for(root, row['key'])
            # A task not started yet, or approved and still queued, shows why it waits.
            from . import tasks
            if tasks.HOLD and (receipt or {}).get('result') == 'queued':
                receipt = {**receipt, 'result': 'held'}
            elif row['key'] in waiting and (receipt or {}).get('result', 'queued') == 'queued':
                receipt = {**(receipt or {}), 'result': 'waiting', **waiting[row['key']]}
            outcome = {**outcome, 'task': {**outcome['task'], 'id': identity(row['key']), **(receipt or {})}}
        result.append(outcome or _base(row, 'could_not_prepare', reason='Not prepared yet.'))
    return result


def summary(root):
    outcomes = listing(root)
    return {'items': len(outcomes),
            **{field: sum(row['kind'] == kind for row in outcomes) for field, kind in (
                ('drafts', 'prepared'), ('already_handled', 'already_handled'), ('tasks', 'task'),
                ('no_reply', 'no_reply'), ('could_not_prepare', 'could_not_prepare'))},
            'unprepared': [{key: row[key] for key in ('key', 'record', 'title', 'text', 'reason')}
                           for row in outcomes if row['kind'] == 'could_not_prepare']}


def _promise(root, row):
    if not row['reply'].get('last_word_yours'):
        return ''
    from .mail_archive import message_path, observed_message_path
    provider, _, identity = row['reply']['source'].partition(':')
    path = message_path(root, provider, identity)
    if not path.is_file():
        path = observed_message_path(root, provider, identity)
    return today._owner_words(read_json(path, {}).get('body', ''))


def _task(root, row, *, words=None):
    words = _promise(root, row) if words is None else words
    prompt = (f"Prepare the work owed by the owner.\nNotebook page: {row['record']}\n"
              f"Obligation: {row['text']}\nOwner's words: {words or 'No quoted promise.'}\n"
              f"Source: {row['reply'].get('source') or 'the notebook obligation'}\n"
              'Produce a reviewable task result with evidence. State any missing inputs; do not invent completion. '
              'Do not send messages or make external commitments. Leave the result for the morning confirmation.')
    return _base(row, 'task', owner_quote=today._owner_quote(words) if words else '',
                 task={'status': 'ready', 'prompt': prompt})


def _local_outcome(root, row):
    reply = row['reply']
    if reply['state'] == 'replied' and reply.get('promise'):
        return _base(row, 'already_handled', owner_quote=reply['promise'],
                     reason="The owner's newest message answered it.")
    if reply['state'] == 'task':
        return _task(root, row)
    return None


def _recover(root, fetches):
    from .night_mail import fetch_missing
    from .store import refresh
    refresh(root)
    rows, errors = _owed(today.queue(root)), {}
    # Each pass resolves previously unknown citations, then rechecks the newest
    # message across all cited threads. No source is attempted twice in a round.
    while any(row['reply']['state'] == 'unarchived' and row['reply']['source'] not in fetches for row in rows):
        errors.update(fetch_missing(root, rows, fetches=fetches))
        refresh(root)
        rows = _owed(today.queue(root))
    errors.update({source: reason for source, reason in fetches.items() if reason})
    return rows, errors


def _select(candidate, selected, left, attempted, cap):
    if not candidate:
        return 'No replyable original or usable owner words.'
    identity = candidate['id']
    if [identity, candidate['version']] in attempted:
        return 'Draft attempt did not produce an accepted reply.'
    if identity not in selected and len(selected) >= left:
        return f'Nightly draft cap ({cap}) reached.'
    selected[identity] = candidate
    return 'Reply preparation pending.'


def _outcomes(root, rows, candidates, existing, *, left, cap, attempted, errors, stop):
    selected, items = {}, {}
    for row in rows:
        outcome = _local_outcome(root, row)
        if not outcome and existing[row['key']]['kind'] in ('prepared', 'no_reply', 'already_handled', 'task'):
            outcome = existing[row['key']]
        if not outcome:
            candidate = _draft_for(row, candidates) if row['reply']['state'] == 'queued' else None
            reason = errors.get(row['reply'].get('source')) or stop
            reason = reason or _select(candidate, selected, left, attempted, cap)
            outcome = _base(row, 'could_not_prepare', reason=reason)
        outcome.setdefault('prepared_at', service.now().isoformat())
        items[row['key']] = {'revision': _revision(row), 'outcome': outcome}
    return items, list(selected.values())


def prepare(root, config, *, attempted=(), fetches=None, stop=''):
    """Persist all outcomes and return affordable drafts in Today order. Caller holds the writer lock."""
    from .store import refresh
    fetches = {} if fetches is None else fetches
    if stop:
        refresh(root)
        rows, errors = _owed(today.queue(root)), {}
    else:
        rows, errors = _recover(root, fetches)
    _, runs = service.runs_today(service.run_logs(root), service.notebook_zone(config))
    spent = sum(run.get('runner_attempts', 0) for run in runs if run.get('phase') == 'reply-draft')
    cap = config['limits']['drafts_per_night']
    existing = {outcome['key']: outcome for outcome in listing(root, rows=rows)}
    items, selected = _outcomes(root, rows, drafts.queue(root), existing, left=max(0, cap - spent), cap=cap,
                               attempted=attempted, errors=errors, stop=stop)
    write_json(state_path(root, 'night.json'), {'date': service.notebook_today(root).isoformat(), 'items': items})
    return selected


def failed(root, row, reason):
    """Attach an expected writer failure to every obligation sharing the draft."""
    saved = read_json(state_path(root, 'night.json'), {})
    keys = {threads.done_key(item['record'], item['text']) for item in row['obligations']}
    for entry in saved.get('items', {}).values():
        if keys.intersection(entry['outcome']['keys']):
            entry['outcome'].update(kind='could_not_prepare', reason=reason)
    write_json(state_path(root, 'night.json'), saved)
