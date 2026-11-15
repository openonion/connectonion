"""Run the existing night now; only its limit identity advances, never time."""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from .files import RemError, maintenance_lock, read_json, state_path, write_json

_NIGHT = ContextVar('rem_catchup_night', default=None)


def number(root):
    saved = _NIGHT.get()
    return saved[1] if saved and saved[0] == Path(root).resolve() else None


def identity(root):
    night = number(root)
    return {'catchup_night': night} if night is not None else {}


def key(root, day):
    night = number(root)
    return f'catchup:{night}' if night is not None else str(day)


def marker(root, name, *, night=None):
    night = number(root) if night is None else night
    return state_path(root, f'catchup/{night}/{name}' if night is not None else name)


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
        night = cursor.get('catchup_night')
    with scope(root, night):
        yield


def limit_runs(root, logs, zone):
    """Limit accounting is separate from real-date usage reports and weekly quotas."""
    from . import service
    night = number(root)
    if night is not None:
        return [row for row in logs if row.get('catchup_night') == night]
    return [row for row in service.runs_today(logs, zone)[1] if 'catchup_night' not in row]


def _begin(root):
    from . import native
    with maintenance_lock(root):
        native.refuse_pending(root)
        path = state_path(root, 'catchup.json')
        night = read_json(path, {}).get('nights', 0) + 1
        write_json(path, {'nights': night})
        return night


def _mail(root, batch):
    from . import service
    sources = service.subscriptions(root)
    return sum(count for name, count in batch.get('items_by_source', {}).items()
               if sources.get(name, {}).get('kind', name) in service.MAIL_KINDS)


def _counts(root, night):
    from . import service
    cursor = read_json(state_path(root, 'round.json'), {})
    if cursor.get('catchup_night') != night:
        cursor = {}
    runs = [row for row in service.run_logs(root) if row.get('catchup_night') == night]
    changed = set(cursor.get('changed', []))
    changed.update(record for row in runs for record in row.get('changed', []))
    sessions = cursor.get('sessions', {})
    imported = sessions.get('imported', 0) + sessions.get('updated', 0)
    changed.update(sessions.get('changed', []))
    return {'mail': _mail(root, cursor.get('batch', {}).get('record', {})),
            'sessions': imported, 'written': len(changed),
            'decisions': sum(record.startswith('decisions/') for record in changed),
            'translated': cursor.get('translated', 0),
            'drafts': len({row['draft'] for row in runs if row.get('phase') == 'reply-draft'
                           and row.get('draft') and row.get('outcome') == 'completed'}),
            'changed': sorted(changed)}


def _stop(result, row, index):
    reason = result.get('reason', '')
    failed = result.get('outcome') != 'done'
    if not failed and reason in ('round done', 'daily cap reached'):
        reason = ''
    else:
        reason = reason or result.get('outcome', 'round stopped')
    if not (row['written'] or row['translated'] or row['drafts']):
        reason = f'night {index} produced nothing' + (f'; {reason}' if reason else '')
    return reason, failed


def _depth_counts(root, result, before):
    rounds = result.get('rounds')
    if rounds is None:  # A stopped slot may already have saved complete page rounds.
        history = read_json(state_path(root, 'depth.json'), {})
        rounds = [{'record': record, **row} for record, saved in history.items()
                  for row in saved[len(before.get(record, [])):]]
    problems = [f"{row['record']}: enrich {row['enrich']}, muse {row['muse']}" for row in rounds
                if any(row[name] != 'completed' for name in ('enrich', 'muse'))]
    reason = '; '.join(part for part in [result['stopped'], *problems] if part)
    return {'deepened': len(rounds), 'deepen_reason': reason or ('no qualifying pages' if not rounds else '')}


def _night(root, night, rows, progress, stage, say):
    from . import schedule
    before = read_json(state_path(root, 'depth.json'), {})
    deepening = {'rounds': [], 'stopped': 'exec interrupted'}
    calendar = None
    with scope(root, night):
        try:
            result = schedule.exec_round(root, scheduled=False, stage=stage, say=say)
            calendar = result.get('calendar')
            reason, failed = _stop(result, _counts(root, night), len(rows) + 1)
            deepening = result.get('depth', {'rounds': [], 'stopped': f'exec stopped: {reason or result.get("reason", "")}'})
        finally:  # Include saved slot work even if exec's deepen slot was interrupted.
            cursor = read_json(state_path(root, 'round.json'), {})
            if cursor.get('catchup_night') == night:
                deepening = cursor.get('depth', deepening)
                calendar = cursor.get('calendar', calendar)
            row = {**_counts(root, night), **_depth_counts(root, deepening, before)}
            if calendar is not None:
                row['calendar'] = calendar
                if 'day_plan' in calendar:
                    row['day_plan'] = calendar['day_plan']
            rows.append(row)
            progress(len(rows), row)
    return reason, failed


MODEL_STAGES = ['Investigate', 'Deepen', 'Abstract', 'Translate']


def _held(root, reason, meter):
    """The steps of a night that call no model, once, while a limit holds the rest.

    2026-11-16: at the 99% floor catchup printed "Done: 0 nights", exited 0 and read
    nothing, while the schedule on the same notebook kept reading mail.
    """
    from datetime import datetime
    from . import native, schedule
    found = native.collect_while_held(root, reason)
    calendar = schedule.calendar_round(root)
    changed = found.get('changed', [])
    resets = meter.get('resets_at')
    # sessions is None when only the mailboxes were read into a round already open.
    return {'note': found['note'], 'mail': _mail(root, found.get('batch', {})), 'sessions': found.get('sessions'),
            'written': len(changed), 'changed': changed, 'calendar': calendar, 'day_plan': calendar['day_plan'],
            'waiting': MODEL_STAGES,
            'resumes_at': datetime.fromtimestamp(resets).astimezone().isoformat() if resets else None}


def run(root, *, nights=1, progress=lambda number, row: None, stage=None, say=None):
    """One exec round including its deepen slot per productive, completed night."""
    from . import quota, service
    from .config import read_config
    if nights < 1:
        raise RemError('Use at least one night: co rem catchup --nights 1')
    root, rows, reason, failed, held = Path(root).resolve(), [], '', False, None
    for _ in range(nights):
        config = read_config(root)
        meter = quota.meter(root, config)
        reason = quota.blocks(meter, quota.points_spent(service.run_logs(root), meter), config['limits'])
        quota.record_pause(root, meter, config['limits'])
        if reason:
            # A night that ran has read the sources and the calendar already.
            held = None if rows else _held(root, reason, meter)
            break
        night = _begin(root)
        reason, failed = _night(root, night, rows, progress, stage, say)
        if reason:
            break
    totals = {name: sum(row[name] for row in rows) for name in
              ('mail', 'sessions', 'written', 'decisions', 'translated', 'drafts', 'deepened')}
    return {'nights': rows, 'reason': reason, 'failed': failed, 'held': held,
            'deepen_reason': '' if totals['deepened'] else
                '; '.join(dict.fromkeys(row['deepen_reason'] for row in rows if row['deepen_reason']))
                or (f'not started: {reason}' if not rows else ''), **totals}
