"""Source-backed obligations and dates, without changing notebook prose."""
import calendar
import posixpath
import re

from .census import direction, threads
from .reader_model import CITATION, REFERENCE, source_definitions

KINDS = ('owed', 'waiting', 'agent', 'answerable')
DAY = r'\d{4}-\d{2}-\d{2}'
MONTH = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
DATE_TEXT = rf'{DAY}|\d{{4}}年\d{{1,2}}月\d{{1,2}}日|{MONTH} \d{{1,2}}(?:,? \d{{4}})?|\d{{1,2}}月\d{{1,2}}日'
PROMISE = re.compile(rf'\b(?:due(?: on| is)?|deadline(?: is)?|by(?: the)?|deliver(?:y)? on|promised for)\s*:?\s*({DATE_TEXT})|(?:截止|承诺|交付日期)[：\s]*({DATE_TEXT})', re.I)
REQUEST = re.compile(r'\b(?:the user|user|you)\s+(?:asked|asks|requested|requests|instructed|wanted|proposed)\b|用户(?:要求|让|希望)|你(?:让|要求)', re.I)
QUERY = re.compile(r'\b(?:how many|how much|what|which|when|where|whether|status|check|find out)\b|多少|进度|状态|是否|几点|哪里', re.I)


def sections(text):
    found, name = {}, ''
    for line in text.splitlines():
        if line.startswith('## '):
            name = line[3:].strip().casefold()
        else:
            found.setdefault(name, []).append(line)
    return {key: '\n'.join(lines) for key, lines in found.items()}


def source_map(record):
    return {label: value.strip().lstrip(':').strip().split(' — ')[0].split(' – ')[0]
            for label, value in source_definitions(sections(record['text']).get('sources', ''))}


def source_entries(record):
    return [(label, source.strip()) for label, value in source_map(record).items()
            for source in re.split(r';\s*(?=[a-z][\w-]*:)', value) if source.strip()]


def evidence(record, text, section='open-threads'):
    entries = source_entries(record)
    return [{'source': source, 'cite': label, 'path': record['path']}
            for label in dict.fromkeys(CITATION.findall(text))
            for source in ([value for number, value in entries if number == label] or [f"{record['path']}#citation-{label}"])] or [
        {'source': f"{record['path']}#{section}", 'cite': None, 'path': record['path']}]


def iso_day(raw):
    """Validate written calendar days; never fill in missing years."""
    match = re.match(rf'({DAY})(?:$|[T\s])', raw or '')
    if not match:
        return None
    year, month, day = map(int, match[1].split('-'))
    if 1 <= year <= 9999 and 1 <= month <= 12 and 1 <= day <= calendar.monthrange(year, month)[1]:
        return match[1]
    return None


def explicit_day(raw):
    if iso_day(raw):
        return iso_day(raw)
    chinese = re.fullmatch(r'(\d{4})年(\d{1,2})月(\d{1,2})日', raw)
    if chinese:
        return iso_day('%04d-%02d-%02d' % tuple(map(int, chinese.groups())))
    english = re.fullmatch(rf'({MONTH}) (\d{{1,2}}),? (\d{{4}})', raw, re.I)
    if english:
        month = [m.casefold() for m in calendar.month_name].index(english[1].casefold())
        return iso_day(f'{english[3]}-{month:02}-{int(english[2]):02}')
    return None


def promises(text, source):
    return [{'date': explicit_day(match[1] or match[2]), 'text': match[0], **source}
            for match in PROMISE.finditer(text)]


def mail_promises(text, obligation_text, source):
    # Quoted history is not a new promise. Match the task in the same sentence.
    current = re.split(r'\n(?:On .+wrote:|-----Original Message-----|From:)', text, maxsplit=1)[0]
    return [promise for line in current.splitlines() if not line.lstrip().startswith('>')
            for sentence in re.split(r'(?<=[.!?。])\s+', line)
            if _task_terms(sentence) & _task_terms(obligation_text)
            for promise in promises(sentence, source)]


def _task_terms(text):
    generic = {'you', 'your', 'they', 'them', 'their', 'owner', 'owe', 'owes', 'need', 'needs',
               'return', 'send', 'deliver', 'give', 'provide', 'request', 'requested', 'due', 'deadline',
               'promised', 'since', 'before', 'after', 'must', 'should', 'can', 'will'}
    # Names alone cannot establish that a mail sentence concerns this task.
    names = {name.casefold() for name in re.findall(r'\b[A-Z][a-z]+\b', text)}
    return _terms(text) - generic - names


def linked_people(record, text, records):
    linked = [path for _, raw in REFERENCE.findall(text)
            if (path := posixpath.normpath(posixpath.join(posixpath.dirname(record['path']), raw))) in records
            and records[path]['category'] in ('people', 'orgs')]
    names = {}
    for path, row in records.items():
        if row['category'] in ('people', 'orgs') and len(row['title']) >= 3:
            names.setdefault(row['title'].casefold(), []).append(path)
    prose = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    mentioned = [paths[0] for name, paths in names.items() if len(paths) == 1
                 and re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', prose, re.I)]
    return list(dict.fromkeys(linked + mentioned))


def classify(record, text, sources, people, owner_name='', names=()):
    """Human direction wins over source medium; explicit agent addressees win over mentions."""
    agent_to = re.search(r'\b(?:asked|instructed|told)\s+(?:the\s+)?(?:agent|codex|claude)\b', text, re.I)
    session = any(re.match(r'(?:codex|claude-code|session):', s['source']) for s in sources)
    request = REQUEST.search(text)
    tail = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text[request.end():]) if request else ''
    addressed = any(re.match(r'\s+(?:that\s+)?' + re.escape(name) + r'(?!\w)', tail, re.I)
                    or re.search(r'\bfrom\s+' + re.escape(name) + r'(?!\w)', tail, re.I) for name in names)
    if agent_to or (request and not addressed and (session or re.search(r'asked\s*:', text, re.I))):
        return 'agent', 'owner instruction to a coding session or named agent', False
    debt = direction(text, owner_name)
    if re.search(r'我(?:在)?等|欠我|等对方', text):
        debt = 'theirs'
    if re.search(r'我欠|等我|等你|你欠', text):
        debt = 'mine'
    if debt in ('mine', 'theirs'):
        return ('owed' if debt == 'mine' else 'waiting'), 'explicit owner/counterparty direction', False
    if session and not people:
        return 'agent', 'session source with no human counterparty', False
    if record['category'] == 'projects' and not people:
        return 'agent', 'project action without an identified human waiter', True
    return 'owed', 'human-page obligation with unspecified direction; needs review', True


def _terms(text):
    stop = {'the', 'user', 'asked', 'how', 'many', 'much', 'what', 'which', 'when', 'where', 'were', 'was', 'are', 'has', 'have', 'been', 'please', 'could', 'would', 'status', 'check', 'answer', 'that', 'this'}
    return {word for word in re.findall(r'[a-z]{3,}|[\u4e00-\u9fff]{2,}', text.casefold()) if word not in stop}


def _matches_answer(question, answer):
    if REQUEST.search(answer) or '?' in answer or '？' in answer or re.search(r'unknown|not (?:known|reported|verified)|no .*reports|未确认|未知', answer, re.I):
        return False
    question_terms, answer_terms = _terms(question), _terms(answer)
    common = question_terms & answer_terms
    if len(common) < 2 and not any(len(term) >= 4 and re.search(r'[\u4e00-\u9fff]', term) for term in common):
        return False
    if not question_terms <= answer_terms:
        return False
    if not set(re.findall(DAY, question)) <= set(re.findall(DAY, answer)):
        return False
    numeric = re.search(r'how many|how much|多少', question, re.I)
    quantity = re.sub(DAY, '', CITATION.sub('', answer))
    quantity = re.sub(r'`[^`]*`|https?://\S+|\b[\w]+[:_-][\w:-]+\b', '', quantity)
    if numeric:
        return bool(re.search(r'(?<!\w)\d+(?:\.\d+)?(?!\w)', quantity)) and not re.search(r'\bnot\b|未处理', quantity, re.I)
    return bool(re.search(r'\b(?:is|are|was|were|answer|completed|located)\b|答案|完成|当前', answer, re.I))


def find_answer(record, text, contexts):
    if not QUERY.search(text):
        return None
    # Relative/current questions cannot be settled by a historical summary.
    if re.search(r'\b(?:yesterday|last night|today|now|current|latest)\b|昨晚|昨天|现在|今天|当前|最新', text, re.I):
        return None
    for name, body in sections(record['text']).items():
        if name in ('open threads', 'sources', 'uncertainties', ''):
            continue
        for line in body.splitlines():
            sources = evidence(record, line, name)
            input_only = any(contexts.get(s['source'], {}).get('input_scope') for s in sources)
            if CITATION.search(line) and not input_only and _matches_answer(text, line):
                return {'text': line.strip().lstrip('- '), **evidence(record, line, name)[0]}
    for _, source in source_entries(record):
        context = contexts.get(source, {})
        if context.get('input_scope') or context.get('role') == 'user':
            continue
        answer = context.get('excerpt', '')
        if _matches_answer(text, answer):
            return {'text': answer, 'source': source, 'cite': None, 'path': record['path']}
    return None


def obligation(record, text, records, contexts, owner_name=''):
    sources = evidence(record, text)
    people = linked_people(record, text, records)
    kind, rule, review = classify(record, text, sources, people, owner_name, [records[p]['title'] for p in people])
    promised = promises(text, sources[0])
    for source in sources:
        if source['source'].startswith(('gmail:', 'outlook:')):
            promised += mail_promises(contexts.get(source['source'], {}).get('excerpt', ''), text, source)
    due = next((p['date'] for p in promised if p['date']), None)
    since_match = re.search(rf'\b(?:since|requested(?: on)?|asked(?: on)?)\s*:?\s*({DAY})', text, re.I)
    leading = re.match(rf'({DAY})\b', text)
    since = iso_day((since_match or leading)[1]) if since_match or leading else None
    since = since or min((day for s in sources if (day := iso_day(contexts.get(s['source'], {}).get('time')))), default=None)
    answer = find_answer(record, text, contexts) if kind == 'agent' else None
    who = people[0] if people else record['path'] if record['category'] in ('people', 'orgs') else None
    if kind == 'agent':
        who = None
    return {'text': text, 'kind': 'answerable' if answer else kind, 'kind_reason': rule if not answer else 'matching cited answer retained',
            'needs_review': review, 'who': who, 'since': since, 'due': due, 'sources': sources,
            'promised': promised, 'answer': answer}


def open_items(record, records, contexts, owner_name='', states=None):
    from .threads import blocked, done_key
    return [obligation(record, text, records, contexts, owner_name) for text in threads(record['text'])
            if not blocked(None, done_key(record['path'], text), states=states or {})]


def project_dates(record, contexts):
    parts = sections(record['text'])
    facts = parts.get('facts', '')
    result = {'started': None, 'last_activity': None, 'date_sources': {}}
    for field, label in (('started', 'Started'), ('last_activity', 'Last activity')):
        match = re.search(rf'^\s*(?:-\s*)?{label}:\s*({DAY})([^\n]*)', facts, re.M | re.I)
        if match and iso_day(match[1]):
            result[field] = match[1]
            result['date_sources'][field] = evidence(record, match[0], 'facts')[0]
    # The scoped project fact wins over timestamps of broader workspace inputs.
    if result['last_activity']:
        return result
    candidates = []
    for name, body in parts.items():
        for match in re.finditer(rf'^\s*-\s*Last seen:\s*({DAY})\b[^\n]*', body, re.I | re.M):
            if iso_day(match[1]):
                candidates.append((match[1], evidence(record, match[0], name)[0]))
    for line in parts.get('where it stands', '').splitlines():
        match = re.match(rf'^\s*-\s*({DAY})\b', line)
        if match and iso_day(match[1]):
            candidates.append((match[1], evidence(record, line, 'where-it-stands')[0]))
    candidates += [(day, {'source': source, 'cite': label, 'path': record['path']})
                   for label, source in source_entries(record) if (day := iso_day(contexts.get(source, {}).get('time')))]
    for day, source in sorted(candidates, key=lambda pair: pair[0]):
        if not result['last_activity'] or day > result['last_activity']:
            result['last_activity'], result['date_sources']['last_activity'] = day, source
    return result
