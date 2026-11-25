"""Run the existing night now; only its limit identity advances, never time."""

import re
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
    with maintenance_lock(root):
        # A task an earlier stopped run left pending is resumed by this night's exec
        # round (retried with its refusal, then parked), not refused here: on
        # 2026-11-16 it made every later catchup exit until a command was run by hand.
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
    from .native_round import hold_in_words, waiting_shares
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
            # Cheap stages are finished in a night: what the round's bound left is said, not hidden.
            'translations_waiting': cursor.get('translations_waiting', 0),
            'tagged': cursor.get('tagged', 0), 'tags_waiting': cursor.get('tags_waiting', 0),
            'summarised': sum(row.get('phase') == 'sessions-summary' and row.get('outcome') == 'completed'
                              for row in runs),
            'drafts': len({row['draft'] for row in runs if row.get('phase') == 'reply-draft'
                           and row.get('draft') and row.get('outcome') == 'completed'}),
            'changed': sorted(changed), 'parked': _parked(root, night, runs=service.run_logs(root)),
            # A used share is work that waits, said in the night's line; it is not a stop reason.
            'shares': waiting_shares(root, night=f'catchup:{night}'),
            # So is a spent weekly investigation budget: the night's other stages ran.
            'investigation_hold': hold_in_words(root, night=f'catchup:{night}')}


def _parked(root, night, *, runs):
    """What this night set aside: tasks parked after their retries, then pages whose preparation hung.

    `cause` is what the night's line prints (`refusals.short_cause`); `why` stays whole for
    `--json`. A candidate is named only while its file is there: a parked task keeps
    candidate.md and its reviews, and any other file it wrote goes with the material."""
    from .refusals import refused_pages, short_cause
    found = [(row.get('record'), row.get('reason', ''), row.get('cause'), row.get('candidate'))
             for row in sorted(runs, key=lambda row: row.get('finished_at') or '')
             if row.get('outcome') == 'parked' and row.get('parked_night') == night]
    listed = {record for record, *_ in found}
    found += [(record, entry['parked'], None, entry.get('candidate')) for record, entry in refused_pages(root).items()
              if entry.get('parked_night') == night and record not in listed]
    return [{'record': record, 'why': why.removeprefix('parked: '),
             'cause': cause or short_cause(why.removeprefix('parked: ')),
             'candidate': candidate if candidate and Path(candidate).is_file() else None}
            for record, why, cause, candidate in found]


def _stop(result, row, index):
    reason = result.get('reason', '')
    failed = result.get('outcome') != 'done'
    if not failed and reason in ('round done', 'daily cap reached'):
        reason = ''
    else:
        reason = reason or result.get('outcome', 'round stopped')
    if not (row['written'] or row['translated'] or row['drafts'] or row.get('tagged')):
        reason = f'night {index} produced nothing' + (f'; {reason}' if reason else '')
    return reason, failed


def _depth_counts(root, result, before):
    rounds = result.get('rounds')
    if rounds is None:  # A stopped slot may already have saved complete page rounds.
        history = read_json(state_path(root, 'depth.json'), {})
        rounds = [{'record': record, **row} for record, saved in history.items()
                  for row in saved[len(before.get(record, [])):]]
    # A page whose enrich was refused or failed was not deepened: it is counted apart, with a
    # short cause. 2026-11-16: it counted as deepened and the line carried the raw refusal.
    missed = [row for row in rounds if _stage_failed(row['enrich'])]
    kept = [row for row in rounds if row not in missed]
    problems = [f"{row['record']}: enrich {row['enrich']}, muse {_in_brief(row, 'muse')}" for row in kept
                if any(row[name] != 'completed' for name in ('enrich', 'muse'))]
    reason = '; '.join(part for part in [result['stopped'], *problems] if part)
    return {'deepened': len(kept), 'deepen_reason': reason or ('no qualifying pages' if not rounds else ''),
            'not_deepened': len(missed),
            'not_deepened_reason': 'enrich ' + _in_brief(missed[0], 'enrich') if missed else ''}


def _stage_failed(outcome):
    return outcome == 'refused' or outcome.startswith('failed')


def _in_brief(row, name):
    """`refused: <cause>` or `failed: <cause>`; a round saved before causes were kept gives its first clause."""
    outcome = row[name]
    if not _stage_failed(outcome):
        return outcome
    cause = row.get(f'{name}_cause') or re.split(r':\s|;\s', outcome.removeprefix('failed: '), maxsplit=1)[0][:100]
    return outcome.partition(':')[0] + (f': {cause}' if cause and cause != outcome else '')


def _round(root, schedule, stage, say):
    """One exec round. An error that stops the round is the night's stop reason, not a bare error.

    2026-11-16: "Task does not exist or is not pending" ended catchup after the
    night's line with `Error:` and no totals, and the line said "exec interrupted".
    Ctrl-C still leaves through `_night`'s finally, with its own report."""
    try:
        return schedule.exec_round(root, scheduled=False, stage=stage, say=say)
    except RemError as error:
        return {'outcome': 'failed', 'reason': str(error)}


def _night(root, night, rows, progress, stage, say):
    from . import schedule
    before = read_json(state_path(root, 'depth.json'), {})
    deepening = {'rounds': [], 'stopped': 'exec interrupted'}
    calendar = None
    with scope(root, night):
        try:
            result = _round(root, schedule, stage, say)
            calendar = result.get('calendar')
            reason, failed = _stop(result, _counts(root, night), len(rows) + 1)
            deepening = result.get('depth', {'rounds': [], 'stopped': f'exec stopped: {reason or result.get("reason", "")}'})
        finally:  # Include saved slot work even if exec's deepen slot was interrupted.
            rows.append(_row(root, night, deepening, calendar, before))
            progress(len(rows), rows[-1])
    return reason, failed


def _row(root, night, deepening, calendar, before):
    """The night's line from what is saved, so a night cut short still reports the work it did."""
    cursor = read_json(state_path(root, 'round.json'), {})
    if cursor.get('catchup_night') == night:
        deepening = cursor.get('depth', deepening)
        calendar = cursor.get('calendar', calendar)
    row = {**_counts(root, night), **_depth_counts(root, deepening, before)}
    if calendar is not None:
        row['calendar'] = calendar
        if 'day_plan' in calendar:
            row['day_plan'] = calendar['day_plan']
    return row


def _ended(root, night, rows, progress, why):
    """The run's result when a deadline has to end the process under this night.

    2026-11-16: a preparation past its deadline ended catchup with exit 75 and
    neither the night's line nor the totals. Nothing after the exit runs (no
    `finally`), so the line and the result are made here, from the watcher's
    thread, before it."""
    row = _row(root, night, {'rounds': [], 'stopped': f'exec stopped: {why}'}, None, {})
    rows.append(row)
    progress(len(rows), row)
    reason, _ = _stop({'outcome': 'stopped', 'reason': why}, row, len(rows))
    return _result(root, rows, reason, True, None)


MODEL_STAGES = ['Investigate', 'Deepen', 'Abstract', 'Translate', 'Tag']


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


def run(root, *, nights=1, progress=lambda number, row: None, stage=None, say=None, cut_short=lambda value: None):
    """One exec round including its deepen slot per productive, completed night.

    `cut_short` prints the result when a deadline ends the process mid-night."""
    from .codex_exec import BUSY, NotebookBusy, round_lock
    if nights < 1:
        raise RemError('Use at least one night: co rem catchup --nights 1')
    try:
        with round_lock(root):
            return _nights(Path(root).resolve(), nights, progress, stage, say, cut_short)
    except NotebookBusy:
        return {'outcome': 'busy', 'reason': BUSY + ' No night was counted.', 'failed': True, 'held': None}


def _nights(root, nights, progress, stage, say, cut_short):
    from . import native, quota
    from .config import read_config
    rows, reason, failed, held = [], '', False, None
    for _ in range(nights):
        config = read_config(root)
        meter = quota.meter(root, config)
        # Only the floor holds a whole night. A spent investigation budget holds
        # investigation, inside the round; the night still runs its other stages.
        reason = quota.floor_block(meter, config['limits'])
        quota.record_pause(root, meter, config['limits'])
        if reason:
            # A night that ran has read the sources and the calendar already.
            held = None if rows else _held(root, reason, meter)
            break
        night = _begin(root)
        with native.last_words(lambda why: cut_short(_ended(root, night, rows, progress, why))):
            reason, failed = _night(root, night, rows, progress, stage, say)
        if reason:
            break
    return _result(root, rows, reason, failed, held)


def _result(root, rows, reason, failed, held):
    totals = {name: sum(row[name] for row in rows) for name in
              ('mail', 'sessions', 'written', 'decisions', 'translated', 'summarised', 'drafts', 'deepened',
               'not_deepened')}
    totals['tagged'] = sum(row.get('tagged', 0) for row in rows)
    return {'nights': rows, 'reason': reason, 'failed': failed, 'held': held,
            'parked': [page for row in rows for page in row['parked']], 'candidates': str(state_path(root, 'tasks')),
            'deepen_reason': '' if totals['deepened'] else
                '; '.join(dict.fromkeys(row['deepen_reason'] for row in rows if row['deepen_reason']))
                or (f'not started: {reason}' if not rows else ''),
            'not_deepened_reason': next((row['not_deepened_reason'] for row in rows if row['not_deepened_reason']), ''),
            **totals}
