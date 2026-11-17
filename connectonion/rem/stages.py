"""Read-only counts and last-run dates for the five stages of a REM day."""

from datetime import datetime, timezone

from .files import Notebook, read_json, state_path

STAGES = (
    ('Collect', 'listed mail', ('sync', 'extract', 'collect')),
    ('Investigate', 'page', ('daily-investigation', 'daily-update', 'investigate', 'investigate me',
                             'projects write', 'sessions-summary', 'same-person', 'reply-draft')),
    ('Deepen', 'page', ('enrich', 'muse')),
    ('Abstract', 'captured decision', ('abstract',)),
    ('Translate', 'page translation', ('daily-translation', 'translate')),
)


def collection_backlog(root):
    """Listed mail still queued; disabled or unapproved sources are held separately."""
    from .service import MAIL_KINDS, subscriptions
    progress = read_json(state_path(root, 'progress.json'), {})
    sources, counts = subscriptions(root), {'waiting': 0, 'held': 0}
    for name, source in progress.items():
        if not isinstance(source, dict):
            continue
        subscription = sources.get(name, {})
        if subscription.get('kind', name) not in MAIL_KINDS:
            continue
        eligible = (subscription.get('enabled') and subscription.get('consented')
                    and not subscription.get('unsubscribed'))
        counts['waiting' if eligible else 'held'] += sum(map(len, source.get('pending', {}).values()))
    return counts


def _collection_runs(root, logs):
    """Batch receipts, including a native round's batch rather than its investigation tasks."""
    cursor = read_json(state_path(root, 'round.json'), {})
    rows = [*logs, {'batch': cursor.get('batch', {}).get('record', {})}]
    for row in rows:
        batch = row.get('batch') or row.get('maintenance')
        if isinstance(batch, dict):
            batch = batch.get('record', batch)
            if batch.get('items', 0):
                yield {**batch, 'phase': 'sync', 'started_at': batch.get('started_at') or row.get('started_at')}
        phase = row.get('phase', 'sync')
        if row.get('items', 0) and (phase in STAGES[0][2] or
                (phase in ('daily-investigation', 'daily-update') and
                 (row.get('native_round') or row.get('items_by_source')))):
            yield {**row, 'phase': 'sync'}


def _investigate(root):
    from .queue import order_all
    from .sessions import _summary_candidates
    from .merge import mapped_only
    book = Notebook(root)
    pages = {row['path'] for row in order_all(root) if not row['recent']}
    saved = read_json(state_path(root, 'sessions.json'), {}).get('sessions', {})
    pages.update(row['record'] for row in _summary_candidates(root, len(saved)))
    owner = (read_json(state_path(root, 'map.json'), {}).get('owner') or {}).get('record')
    if owner and book.exists(owner) and mapped_only(book.read(owner)):
        pages.add(owner)
    from . import night, same_person
    pages.update(page for pair in same_person.candidates(root) for page in pair['pages'])
    pages.update(row['record'] for row in night.summary(root)['unprepared'])
    cursor = read_json(state_path(root, 'round.json'), {})
    if not cursor.get('done'):
        pages.update(job['record'] for job in cursor.get('jobs', [])[cursor.get('job_index', 0):])
    # Pages a night's share did not reach are waiting too, listed again or not.
    from .native_round import WAITING
    pages.update(job['record'] for job in read_json(state_path(root, WAITING), {}).get('jobs', [])
                 if book.exists(job['record']))
    return len(pages)


def _counts(root):
    from . import captured_decisions, depth, translate
    return (collection_backlog(root)['waiting'], _investigate(root), len(depth.candidates(root)),
            captured_decisions.pending_count(Notebook(root)),
            sum(len(translate.backlog(root, language)) for language in translate.languages(root)
                if language.split('-')[0].lower() != 'en'))


def _last_run(logs, phases, zone):
    """Native abstract tasks keep the enclosing round's phase and their own stage."""
    stamps = []
    for row in logs:
        stage = (row.get('render_stage') or row.get('stage') or '').removesuffix(' (repair)')
        phase = 'abstract' if stage == 'abstract' else row.get('phase', 'sync')
        if phase not in phases or row.get('outcome') in ('pending', 'busy', 'budget_exhausted', 'skipped'):
            continue
        value = row.get('started_at')
        if value:
            stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            stamp = stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
            stamps.append(stamp.astimezone(zone))
    return max(stamps).date().isoformat() if stamps else None


def _budget_hold(root, config, logs, budget):
    """The investigation hold in words, from the same count of the week's points the Budget line shows.

    Asked only when a round saved a hold: status is read on every sync, and most have none."""
    from . import quota
    from .native_round import hold_in_words
    from .service import _quota_status
    if not hold_in_words(root):
        return ''
    budget = budget or _quota_status(config, logs)
    held = quota.investigation_hold(budget['quota'], budget['investigation_quota']['spent_points'], config['limits'])
    return hold_in_words(root, held=held)


def status(root, config, logs, *, budget=None):
    """`budget`: `service._quota_status`'s result when the caller has counted it already."""
    from .service import notebook_zone
    zone, rows = notebook_zone(config), []
    for (name, unit, phases), count in zip(STAGES, _counts(root)):
        last = _last_run(_collection_runs(root, logs) if name == 'Collect' else logs, phases, zone)
        noun = unit if count == 1 or name == 'Collect' else unit + 's'
        rows.append({'name': name, 'waiting': count, 'last_run': last,
                     'text': f'{name}: {count} {noun} waiting; last ran {last or "never"}'})
        if name == 'Collect':
            rows[-1]['held'] = collection_backlog(root)['held']
            if rows[-1]['held']:
                rows[-1]['text'] += f"; {rows[-1]['held']} held (source disabled or unapproved)"
        if name == 'Investigate':
            from .native_round import shares_in_words, waiting_shares
            # A used share is not a failure: the line says what was done and what waits.
            rows[-1]['shares'] = waiting_shares(root)
            rows[-1]['text'] += ''.join('; ' + words for words in
                                        shares_in_words(rows[-1]['shares'], "the last night's"))
            # Nor is a spent weekly budget: only this stage waits, and the line says until when.
            hold = _budget_hold(root, config, logs, budget)
            if hold:
                rows[-1]['budget_hold'] = hold
                rows[-1]['text'] += '; ' + hold
        if name == 'Translate' and count:
            # Translation is finished in a round, not rationed; this is the round's stated end.
            rows[-1]['round_limit'] = config['limits']['translations_per_round']
            rows[-1]['text'] += f"; a round translates up to {rows[-1]['round_limit']}"
        if name == 'Abstract':
            book = Notebook(root)
            counts = {category: len(book.list(category)) for category in ('decisions', 'knowledge', 'principles')}
            rows[-1]['pages'] = counts
            rows[-1]['text'] += (f"; {counts['decisions']} decisions · {counts['knowledge']} knowledge"
                                f" · {counts['principles']} principles")
    return rows


def calendar_status(root, config):
    """Calendar freshness from the saved snapshot, without asking a connected account."""
    from .service import notebook_zone
    saved = read_json(state_path(root, 'calendar.json'), None)
    reads = (saved or {}).get('read_at', {})
    last = _last_run([{'phase': 'calendar', 'started_at': at} for at in reads.values()],
                     ('calendar',), notebook_zone(config))
    events = len((saved or {}).get('events', []))
    if last:
        detail = f'last read {last}; {events} {"event" if events == 1 else "events"} saved'
    elif saved is not None and not saved.get('errors'):
        detail = 'no calendar is connected'
    else:
        detail = 'never read'
    return {'last_read': last, 'events': events, 'text': 'Calendars: ' + detail}
