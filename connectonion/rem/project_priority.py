"""Daily, explainable project pressure: bounded debt, deadlines, money and activity."""
import re
from datetime import date

from .project_obligations import evidence, iso_day, sections


def reason(text, points, source):
    text = ' '.join(text.split())
    text = text if len(text) <= 180 else text[:176].rsplit(' ', 1)[0] + '…'
    return {'text': text, 'points': points, **source, 'sources': [source]}


def time_factor(item, today):
    if item['due']:
        days = (date.fromisoformat(item['due']) - today).days
        return min(5, 3 + ((-days) // 7) * .5) if days < 0 else 2 if days <= 7 else 1
    days = (today - date.fromisoformat(item['since'])).days if item['since'] else 0
    return 1.5 if days > 14 else 1 if days > 7 else .5


def waiter_weight(item, records):
    if item['kind'] == 'waiting':
        return .5, 'counterparty owes owner'
    if item['kind'] == 'agent':
        return 1, 'agent task'
    person = records.get(item['who'], {})
    context = sections(person.get('text', '')).get('facts', '') + '\n' + item['text']
    for pattern, weight, label in [
        (r'paying client|paid client|paid subscription|付费客户', 5, 'paying client'),
        (r'\bpartner\b|\binvestor\b|event organi[sz]er|合作方|投资人|活动方', 3, 'partner/investor'),
        (r'\bstudent\b|\bcapstone\b|学生', 2, 'student'),
    ]:
        if re.search(pattern, context, re.I):
            return weight, label
    return 1, 'unclassified human waiter'


def debt_reasons(items, records, today):
    found = []
    agent_added = False
    for item in items:
        if item['kind'] == 'answerable' or item.get('project_match', {}).get('needs_review'):
            continue
        if item['kind'] == 'agent':
            if not agent_added:
                found.append(reason('Open agent instructions (bounded contribution)', .5, item['sources'][0]))
                agent_added = True
            continue
        weight, label = waiter_weight(item, records)
        factor = time_factor(item, today)
        entry = reason(f'{label}: {weight} × {factor:g}; {item["text"]}', weight * factor, item['sources'][0])
        person = records.get(item['who'])
        if person and weight > 1:
            entry['sources'] += evidence(person, sections(person['text']).get('facts', ''), 'facts')
        found.append(entry)
    return sorted(found, key=lambda row: -row['points'])[:3]


def deadline_reason(promised, today):
    upcoming = [(date.fromisoformat(p['date']) - today).days for p in promised if p['date']]
    days = min((day for day in upcoming if 0 <= day <= 14), default=None)
    if days is None:
        return []
    source = next(p for p in promised if p['date'] and (date.fromisoformat(p['date']) - today).days == days)
    return [reason(f'Explicit delivery/deadline in {days} days', 4 if days <= 7 else 2,
                   {key: source[key] for key in ('source', 'cite', 'path')})]


def money_reasons(record, contexts):
    parts = sections(record['text'])
    candidates = [(line, evidence(record, line, name)[0]) for name in ('facts', 'at stake')
                  for line in parts.get(name, '').splitlines()]
    for item in record['open']:
        if item['kind'] == 'answerable' or item.get('project_match', {}).get('needs_review'):
            continue
        candidates.append((item['text'], item['sources'][0]))
    found = []
    for text, source in candidates:
        if not re.search(r'unpaid|unissued|outstanding invoice|invoice (?:due|owed)|payment due|contract delivery payment|paid subscription|paying client|待开发票|未收|未开|付费订阅', text, re.I):
            continue
        amounts = [float(value.replace(',', '')) for value in re.findall(r'(?:AUD\s*\$?|A\$)\s*([\d,]+(?:\.\d+)?)', text, re.I)]
        points = 6 if max(amounts, default=0) > 10000 else 4
        found.append(reason('Outstanding payment or paid subscription: ' + text.strip(), points, source))
    return sorted(found, key=lambda row: -row['points'])[:1]


def issue_reasons(issues, record, today):
    found, seen, labelled, unlabelled = [], set(), 0, 0
    for issue in issues:
        source = issue.get('url') or issue.get('source')
        updated = iso_day(issue.get('updatedAt') or issue.get('updated_at'))
        if not source or source in seen or str(issue.get('state', '')).lower() != 'open' or not updated:
            continue
        seen.add(source)
        if not 0 <= (today - date.fromisoformat(updated)).days <= 30:
            continue
        labels = {label['name'] if isinstance(label, dict) else label for label in issue.get('labels', [])}
        high = bool(labels & {'priority:high', 'bug'})
        points = min(1, 4 - labelled) if high else min(.1, 1 - unlabelled) if not labels else 0
        labelled += points if high else 0
        unlabelled += points if not high else 0
        if points > 0:
            found.append(reason('Recent open GitHub issue: ' + (issue.get('title') or source), points,
                                {'source': source, 'cite': None, 'path': record['path']}))
    return found


def issue_deadlines(issues, record):
    return [{'date': day, 'text': 'GitHub milestone deadline', 'source': row['url'], 'cite': None, 'path': record['path']}
            for row in issues if str(row.get('state', '')).lower() == 'open' and row.get('url')
            and (day := iso_day((row.get('milestone') or {}).get('dueOn')))]


def priority(score):
    return 0 if score <= 0 else 1 if score >= 20 else 2 if score >= 10 else 3 if score >= 5 else 4


def score_project(record, records, contexts, issues, today):
    reasons = debt_reasons(record['open'], records, today)
    confirmed = [p for item in record['open'] if item['kind'] != 'answerable' and not item.get('project_match', {}).get('needs_review')
                 for p in item['promised']] + issue_deadlines(issues, record)
    reasons += deadline_reason(confirmed, today) + money_reasons(record, contexts)
    reasons += issue_reasons(issues, record, today)
    last = record['last_activity']
    if last and 0 <= (today - date.fromisoformat(last)).days <= 7:
        reasons.append(reason('Activity within seven days', 1, record['date_sources']['last_activity']))
    status = re.search(r'^\s*-?\s*Status:\s*(completed|done|已完成)\b[^\n]*', sections(record['text']).get('facts', ''), re.I | re.M)
    if status:
        reasons = [reason('Project explicitly marked completed', 0, evidence(record, status[0], 'facts')[0])]
    score = round(sum(row['points'] for row in reasons), 2)
    return {'score': score, 'priority': priority(score), 'reasons': sorted(reasons, key=lambda row: -row['points'])[:3], 'pinned': False}


def health(record, today, issues=()):
    open_items = [item for item in record['open'] if item['kind'] != 'answerable' and not item.get('project_match', {}).get('needs_review')]
    active_promises = [p for item in open_items for p in item['promised']] + issue_deadlines(issues, record)
    overdue = next((p for p in active_promises if p['date'] and p['date'] < today.isoformat()), None)
    if overdue:
        return 'off_track', {'text': f'An open obligation or milestone is past its explicit deadline {overdue["date"]}.',
                             **{key: overdue[key] for key in ('source', 'cite', 'path')}}
    near = next((p for p in active_promises if p['date'] and 0 <= (date.fromisoformat(p['date']) - today).days <= 7), None)
    if near:
        return 'at_risk', {'text': f'An open obligation or milestone is due within seven days ({near["date"]}).',
                          **{key: near[key] for key in ('source', 'cite', 'path')}}
    stale = next((item for item in open_items if item['kind'] == 'owed' and (
        (item['since'] and (today - date.fromisoformat(item['since'])).days > 14)
        or re.search(r'overdue|blocking|blocked|逾期|受阻', item['text'], re.I))), None)
    if stale:
        return 'at_risk', {'text': 'An unresolved human obligation is stale or explicitly overdue/blocked.', **stale['sources'][0]}
    risks = [r for r in issue_reasons(issues, record, today) if r['points'] == 1]
    if risks:
        return 'at_risk', {'text': 'A recently updated open GitHub bug or high-priority issue needs attention.',
                          **{key: risks[0][key] for key in ('source', 'cite', 'path')}}
    blocker = recorded_blocker(record)
    if blocker:
        return 'at_risk', blocker
    last = record['last_activity']
    if not last or (today - date.fromisoformat(last)).days > 30:
        return 'quiet', {'text': 'No dated activity in the last thirty days is recorded; completion is not inferred.',
                         **record['date_sources'].get('last_activity', evidence(record, '', 'facts')[0])}
    return 'on_track', {'text': 'Dated activity is recent and no overdue or near-term obligation is recorded.',
                        **record['date_sources']['last_activity']}


def recorded_blocker(record):
    for line in sections(record['text']).get('latest issues', '').splitlines():
        if not re.search(r'\b(?:blocked|blocking|unresolved|outage|server problem)\b|受阻|未解决', line, re.I):
            continue
        if re.search(r'\b(?:not blocked|resolved|recovered|fixed)\b|已解决', line, re.I):
            continue
        return {'text': 'The latest-issues section records an unresolved blocker: ' + line.strip().lstrip('- '),
                **evidence(record, line, 'latest-issues')[0]}
    return None


def apply_override(record, override, today):
    source = {'source': '.state/project-overrides.json#' + record['path'], 'cite': None, 'path': record['path']}
    snooze = iso_day(override.get('snooze_until'))
    record['pinned'] = bool(override.get('pin'))
    if snooze and today.isoformat() < snooze:
        record.update(score=0, priority=0, pinned=False, reasons=[reason(f'Owner snoozed until {snooze} (set {override.get("at", "date unrecorded")})', 0, source)])
    elif record['pinned']:
        record['priority'] = 1
        record['reasons'] = [reason(f'Owner manually pinned (set {override.get("at", "date unrecorded")}); sort pinned projects first', 0, source), *record['reasons'][:2]]
