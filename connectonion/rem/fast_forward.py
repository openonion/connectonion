"""Run the existing night now; only its limit identity advances, never time."""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from .files import RemError, maintenance_lock, read_json, state_path, write_json

_NIGHT = ContextVar('rem_fast_forward_night', default=None)


def number(root):
    saved = _NIGHT.get()
    return saved[1] if saved and saved[0] == Path(root).resolve() else None


def identity(root):
    night = number(root)
    return {'fast_forward_night': night} if night is not None else {}


def key(root, day):
    night = number(root)
    return f'fast-forward:{night}' if night is not None else str(day)


def marker(root, name, *, night=None):
    night = number(root) if night is None else night
    return state_path(root, f'fast-forward/{night}/{name}' if night is not None else name)


@contextmanager
def scope(root, night):
    token = _NIGHT.set((Path(root).resolve(), night)) if night is not None else None
    try:
        yield
    finally:
        if token is not None:
            _NIGHT.reset(token)


@contextmanager
def resume(root, *, scheduled=False):
    cursor = read_json(state_path(root, 'round.json'), {})
    night = number(root)
    if night is None and not cursor.get('done') and (not scheduled or cursor.get('pending')):
        night = cursor.get('fast_forward_night')
    with scope(root, night):
        yield


def limit_runs(root, logs, zone):
    """Limit accounting is separate from real-date usage reports and weekly quotas."""
    from . import service
    night = number(root)
    if night is not None:
        return [row for row in logs if row.get('fast_forward_night') == night]
    return [row for row in service.runs_today(logs, zone)[1] if 'fast_forward_night' not in row]


def _begin(root):
    from . import native
    with maintenance_lock(root):
        native.refuse_pending(root)
        path = state_path(root, 'fast-forward.json')
        night = read_json(path, {}).get('nights', 0) + 1
        write_json(path, {'nights': night})
        return night


def _counts(root, night):
    from . import service
    cursor = read_json(state_path(root, 'round.json'), {})
    if cursor.get('fast_forward_night') != night:
        cursor = {}
    runs = [row for row in service.run_logs(root) if row.get('fast_forward_night') == night]
    changed = set(cursor.get('changed', []))
    changed.update(record for row in runs for record in row.get('changed', []))
    sources = service.subscriptions(root)
    batch = cursor.get('batch', {}).get('record', {})
    sessions = cursor.get('sessions', {})
    imported = sessions.get('imported', 0) + sessions.get('updated', 0)
    changed.update(sessions.get('changed', []))
    return {'mail': sum(count for name, count in batch.get('items_by_source', {}).items()
                        if sources.get(name, {}).get('kind', name) in service.MAIL_KINDS),
            'sessions': imported, 'written': len(changed),
            'decisions': sum(record.startswith('decisions/') for record in changed),
            'translated': cursor.get('translated', 0),
            'drafts': len({row['draft'] for row in runs if row.get('phase') == 'reply-draft'
                           and row.get('draft') and row.get('outcome') == 'completed'}),
            'changed': sorted(changed)}


def run(root, *, nights=1, progress=lambda number, row: None):
    """One exec round per night; all model calls and checks remain in exec."""
    from . import quota, schedule, service
    from .config import read_config
    if nights < 1:
        raise RemError('Use at least one night: co rem fast-forward --nights 1')
    root, rows, reason, failed = Path(root).resolve(), [], '', False
    for _ in range(nights):
        config = read_config(root)
        meter = quota.meter(root, config)
        reason = quota.blocks(meter, quota.points_spent(service.run_logs(root), meter), config['limits'])
        quota.record_pause(root, meter, config['limits'])
        if reason:
            break
        night = _begin(root)
        with scope(root, night):
            try:
                result = schedule.exec_round(root, scheduled=False)
            finally:  # Include saved work even when the owner stops in the middle of a night.
                row = _counts(root, night)
                rows.append(row)
                progress(len(rows), row)
        stop = result.get('reason', '')
        if result.get('outcome') != 'done' or stop not in ('round done', 'daily cap reached'):
            reason, failed = stop or result.get('outcome', 'round stopped'), result.get('outcome') != 'done'
            if not (row['written'] or row['translated'] or row['drafts']):
                reason = f'night {len(rows)} produced nothing; {reason}'
            break
        if not (row['written'] or row['translated'] or row['drafts']):
            reason = f'night {len(rows)} produced nothing'
            break
    return {'nights': rows, 'reason': reason, 'failed': failed,
            **{name: sum(row[name] for row in rows) for name in ('mail', 'sessions', 'written', 'decisions', 'translated', 'drafts')}}
