"""Line receipts and repair feedback for captured decisions, including old slices."""

import hashlib

from . import captured_decisions as captured
from .files import read_json, state_path
from .page_review import _quote_bindings


def _bindings(notebook, records):
    return {pair for record in records if record.startswith('decisions/') and notebook.exists(record)
            for pair in _quote_bindings(notebook.read(record)) if pair[1]}


def line_results(notebook, items, changed, refusals=()):
    """Only a promoted quote bound to the same original completes a captured line."""
    refused = {row['record'] for row in refusals}
    passed = _bindings(notebook, (set(changed) | set(notebook.list('decisions'))) - refused)
    sections = {record: (heading, body, sources) for record, heading, body, sources in captured._sections(notebook)}
    for item in items:
        if item['record'] not in sections:
            continue
        heading, body, sources = sections[item['record']]
        if hashlib.sha256(captured._captured(heading, body, sources).encode()).hexdigest() != item['section_sha256']:
            continue  # The original capture changed while the task was running.
        start, end = item['section_start'], item['section_end']
        for match in captured._eligible_lines(body[start:end], sources, root=notebook.root):
            text = match[0] + '\n\n## Sources\n' + sources
            line = {**captured.slice_key(item), 'section_start': start + match.start(),
                    'section_end': start + match.end()}
            yield line, bool(passed.intersection(_quote_bindings(text)))


def _range(key):
    return tuple(map(int, key.split(':')))


def _overlaps(start, end, key):
    left, right = _range(key)
    return left < end and right > start


def retry_details(notebook, items=None):
    """Count pending failed lines, and return their recorded reasons for the prompt."""
    saved = captured._offered(notebook)
    count, reasons = 0, set()
    for record, _, _, digest, offset, lines in captured._pending(notebook):
        state = saved.get(record, {})
        if state.get('sha256') != digest:
            continue
        for line in lines:
            start, end = offset + line.start(), offset + line.end()
            if items is not None and not any(i['record'] == record and i['section_sha256'] == digest
                                            and i['section_start'] <= start and i['section_end'] >= end for i in items):
                continue
            failures = [key for key in state.get('failures', {}) if _overlaps(start, end, key)]
            count += bool(failures)
            reasons.update(state.get('failure_reasons', {}).get(key, '') for key in failures)
    return count, sorted(reasons - {''})


def _reopen(saved, start, end):
    ranges = [[0, saved.get('offset', 0)], *saved.get('completed', [])]
    saved.update(offset=0, completed=[])
    for left, right in ranges:
        for a, b in ((left, min(right, start)), (max(left, end), right)):
            if a < b:
                captured._complete(saved, a, b)


def recover(notebook, offered):
    """Reopen identifiable refused lines hidden by legacy whole-slice successes.

    This is an in-memory migration for read-only status; the next checkpoint
    makes it durable. Already repaired decisions and explicit give-ups stay done.
    """
    legacy = {record for record, saved in offered.items() if not saved.get('line_progress')}
    if not legacy:
        return offered
    passed = _bindings(notebook, notebook.list('decisions'))
    refused = {}
    for path in sorted(state_path(notebook.root, 'tasks').glob('*/review.json'), key=lambda p: p.stat().st_mtime):
        review = read_json(path, {})
        if not isinstance(review.get('accepted'), list) or not review['accepted']:
            continue
        for row in review.get('refused', []):
            if not row['record'].startswith('decisions/'):
                continue
            page = path.parent / 'refused' / row['record']
            if page.is_file():
                for binding in _quote_bindings(page.read_text(encoding='utf-8')):
                    if binding[1] and binding not in passed:
                        # Old receipts cannot distinguish manual runs from
                        # repeated rounds that night. Seed one known refusal.
                        refused[binding] = {'legacy:' + path.parent.name: '; '.join(row['errors'])}
    for record, heading, body, sources in captured._sections(notebook):
        if record not in legacy:
            continue
        saved = offered[record]
        if saved.get('sha256') != hashlib.sha256(captured._captured(heading, body, sources).encode()).hexdigest():
            continue
        for line in captured._eligible_lines(body, sources, root=notebook.root):
            attempts = {}
            for binding in _quote_bindings(line[0] + '\n\n## Sources\n' + sources):
                attempts.update(refused.get(binding, {}))
            if not attempts or any(row['start'] <= line.start() and row['end'] >= line.end()
                                   for row in saved.get('given_up', [])):
                continue
            _reopen(saved, line.start(), line.end())
            key = f'{line.start()}:{line.end()}'
            saved.setdefault('failures', {})[key] = list(attempts)
            saved.setdefault('failure_reasons', {})[key] = '; '.join(sorted(set(attempts.values())))
        saved['line_progress'] = True
    return offered
