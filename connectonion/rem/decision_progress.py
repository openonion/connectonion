"""Line receipts and repair feedback for captured decisions, including old slices."""

import hashlib
import re

from . import captured_decisions as captured
from .files import read_json, state_path
from .page_review import _quote_bindings


def _bindings(notebook, records):
    return {pair for record in records if record.startswith('decisions/') and notebook.exists(record)
            for pair in _quote_bindings(notebook.read(record)) if pair[1]}


def _verdicts(report):
    verdicts = {}
    for line in report.splitlines():
        match = re.fullmatch(r'VERDICT (d[0-9a-f]{12}) (not-a-decision|merged (decisions/\S+\.md))', line.strip())
        if match:
            verdicts.setdefault(match[1], set()).add(('merged', match[3]) if match[3] else ('not_decision', ''))
    return {key: next(iter(rows)) for key, rows in verdicts.items() if len(rows) == 1}


def _result(notebook, text, passed, changed, refusals, verdict, reason, unassigned):
    bindings = _quote_bindings(text)
    if passed.intersection(bindings):
        return {'state': 'written'}
    state, page = verdict
    words = {words for words, _ in bindings}
    refused = [row for row in refusals if row['record'] == page or
               words.intersection(row.get('quotes', [])) or (not state and 'quotes' not in row)]
    if not state:
        refused += [row for row in unassigned if row not in refused]
    if refused:
        return {'state': 'refused', 'reason': '; '.join(dict.fromkeys(e for row in refused for e in row['errors']))}
    if state == 'not_decision':
        return {'state': state}
    if state == 'merged' and page in changed and notebook.exists(page):
        return {'state': state, 'page': page}
    return {'state': 'no_answer', 'reason': (reason or 'No answer for this captured line') if not state else
            'Merged page did not pass this round: ' + page}


def _offered_lines(notebook, items):
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
            identity = captured.line_id(line['record'], line['section_sha256'], line['section_start'], line['section_end'])
            yield line, text, identity


def line_results(notebook, items, changed, refusals=(), *, report='', reason=''):
    """A bound quote or an explicit verdict accounts for each offered line."""
    lines = list(_offered_lines(notebook, items))
    identities = {identity for _, _, identity in lines}
    verdicts = {key: value for key, value in _verdicts(report).items() if key in identities}
    words = {words for _, text, _ in lines for words, _ in _quote_bindings(text)}
    targets = {page for _, page in verdicts.values()}
    # An inexact quote has no exact line match. Preserve its check feedback for
    # unanswered lines, without spreading an identifiable refusal to other lines.
    unassigned = [row for row in refusals if row['record'] not in targets and not words.intersection(row.get('quotes', []))]
    refused = {row['record'] for row in refusals}
    passed = _bindings(notebook, (set(changed) | set(notebook.list('decisions'))) - refused)
    changed = set(changed) - refused
    for line, text, identity in lines:
        yield line, _result(notebook, text, passed, changed, refusals,
                            verdicts.get(identity, ('', '')), reason, unassigned)


def counts(notebook):
    """Count current line outcomes once, including exhausted retries."""
    offered = captured._offered(notebook)
    counts = dict.fromkeys(('written', 'merged', 'not_decision', 'refused', 'no_answer', 'given_up'), 0)
    for record, heading, body, sources in captured._sections(notebook):
        saved = offered.get(record, {})
        if saved.get('sha256') != hashlib.sha256(captured._captured(heading, body, sources).encode()).hexdigest():
            continue
        for line in captured._eligible_lines(body, sources, root=notebook.root):
            verdict = saved.get('verdicts', {}).get(f'{line.start()}:{line.end()}', {})
            if verdict.get('state') in counts:
                counts[verdict['state']] += 1
                counts['given_up'] += verdict['state'] in ('refused', 'no_answer') and any(
                    row['start'] <= line.start() and row['end'] >= line.end() for row in saved.get('given_up', []))
    return counts


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
    makes it durable. Pre-verdict give-ups get one more offer with their history;
    repaired decisions and give-ups from verdict-aware rounds stay done.
    """
    for saved in offered.values():
        if not saved.get('verdict_progress'):
            for row in saved.get('given_up', []):
                _reopen(saved, row['start'], row['end'])
                key = f"{row['start']}:{row['end']}"
                saved.setdefault('failures', {})[key] = row['nights'][:]
                saved.setdefault('failure_reasons', {})[key] = row['reason']
            saved['verdict_progress'] = True
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
