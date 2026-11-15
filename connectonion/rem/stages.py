"""Read-only counts and last-run dates for the five stages of a REM day."""

from datetime import datetime, timezone

from .files import Notebook, read_json, state_path

STAGES = (
    ('Collect', 'locally known item', ('sync', 'extract')),
    ('Investigate', 'page', ('daily-investigation', 'daily-update', 'investigate', 'investigate me',
                             'projects write', 'sessions-summary', 'same-person', 'reply-draft')),
    ('Deepen', 'page', ('enrich', 'muse')),
    ('Abstract', 'captured decision', ('abstract',)),
    ('Translate', 'page translation', ('daily-translation', 'translate')),
)


def _collect(root):
    """Only retained pending items are knowable without reading a mailbox."""
    progress = read_json(state_path(root, 'progress.json'), {})
    return sum(len(items) for source in progress.values() if isinstance(source, dict)
               for items in source.get('pending', {}).values())


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
    return len(pages)


def _counts(root):
    from . import captured_decisions, depth, translate
    return (_collect(root), _investigate(root), len(depth.candidates(root)),
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


def status(root, config, logs):
    from .service import notebook_zone
    zone, rows = notebook_zone(config), []
    for (name, unit, phases), count in zip(STAGES, _counts(root)):
        last = _last_run(logs, phases, zone)
        noun = unit if count == 1 else unit + 's'
        rows.append({'name': name, 'waiting': count, 'last_run': last,
                     'text': f'{name}: {count} {noun} waiting; last ran {last or "never"}'})
    return rows
