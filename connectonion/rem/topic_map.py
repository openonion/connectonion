"""Dated topic candidates from extraction notes and cited pages; no model or writes in scan."""

import hashlib
import json
import re
from calendar import monthrange
from datetime import date
from pathlib import Path

from .files import Notebook, split_handles, state_path
from .reader_model import CITATION, PRIVATE, source_definitions

GENERIC = frozenset('email mail meeting meetings project projects knowledge topic topics notes facts insight history sources unknown user assistant work software technology'.split())
VENDORS = frozenset({'google', 'apple', 'microsoft', 'amazon', 'openai', 'anthropic', 'airbnb', 'linkedin', 'feishu', 'lark', 'slack', 'notion'})
HEALTH = re.compile(r'\b(?:health|asthma|illness|medication|therapy|diabetes|cancer|dental|depression|surgery|diagnosis|pregnancy|allergy|reflux|adhd|anxiety)\b|健康|哮喘|疾病|用药|治疗|抑郁|手术|怀孕|过敏|焦虑', re.I)
PERSONAL = re.compile(r'\b(?:family|personal|visa|immigration|legal|lawsuit|divorce)\b|家庭|家人|签证|移民|法律|私人|个人财务', re.I)
REQUEST = re.compile(r'\b(?:remember|learn)\s+(.+?)(?:[.!?。\n]|$)|(?:记住|记下|学习)\s*(.+?)(?:[。！？\n]|$)', re.I)
DAY = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
SOURCE_ID = re.compile(r'\b(?:gmail|outlook|codex|claude-code|telegram|feishu|lark|discord|slack|whatsapp|file|manual):[^\s,;，；)\]]+')


def _plain(text):
    return re.sub(r'\s*\[(?:W?\d+|personal|sensitive)\]', '', re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', text)).strip(' -*`')


def topic_aliases(text):
    title = next((line[2:] for line in text.splitlines() if line.startswith('# ')), '')
    names = [PRIVATE.sub('', title).strip()]
    for line in text.splitlines():
        if re.match(r'^- (?:Also known as|Aliases):', line, re.I):
            names += split_handles(line.split(':', 1)[1])
    return list(dict.fromkeys(n.strip() for n in names if n.strip()))


def _names(pages):
    excluded = set(GENERIC | VENDORS)
    for record, text in pages.items():
        if record.startswith(('people/', 'orgs/', 'projects/', 'skills/')):
            excluded.update(n.casefold() for n in topic_aliases(text))
        if record.startswith('people/'):
            excluded.update(word.casefold() for name in topic_aliases(text) for word in name.split())
        if record.startswith('orgs/'):
            excluded.update(d.split('.')[0].casefold() for d in re.findall(r'^- ([\w.-]+\.[a-z]+)\s*$', text, re.M))
    return excluded


def _allowed(name, excluded):
    return 2 <= len(name) <= 80 and name.casefold() not in excluded and not re.search(r'[/@`=\n]|https?:', name)


def _block(text, heading):
    match = re.search(r'^## ' + heading + r'\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    return match[1] if match else ''


def _topic_rows(text):
    for line in _block(text, 'Topics').splitlines():
        parts = [p.strip() for p in line.lstrip('- ').split('|', 4)]
        if len(parts) != 5:
            continue
        name, aliases, record, attribution, sentence = parts
        dates, sources = DAY.findall(attribution), SOURCE_ID.findall(attribution)
        if not dates or not sources:
            continue
        speaker = attribution.split(',', 1)[0].strip()
        yield {'name': name, 'aliases': [name, *split_handles(aliases)], 'record': record.strip('`'),
               'source': sources[0], 'date': dates[0], 'speaker': speaker, 'sentence': sentence}


def _legacy_seeds(text):
    """Explicitly named subjects, never every repeated word or source description."""
    body = _block(text, 'Knowledge') + '\n' + _block(text, 'Insight')
    for name in re.findall(r'\*\*([^*\n]{2,80})\*\*', body):
        # Bold field labels describe the page shape, not a subject.
        if not name.endswith(':'):
            yield name
    for name in re.findall(r'^### ([^\n]{2,80})$', _block(text, 'Knowledge'), re.M):
        yield name
    # Legacy notes had no Topics block. Only a quoted request can bootstrap a
    # one-off name; "wants to learn about" is not an instruction to remember.
    quoted = re.findall(r'["“「]([^"”」\n]+)["”」]', text.partition('\n## Sources')[0])
    for match in REQUEST.finditer('\n'.join(q for q in quoted if REQUEST.match(q))):
        yield (match[1] or match[2]).strip(' `"“”')
    knowledge = _block(text, 'Knowledge')
    for name in re.findall(r'^- (?:The )?([A-Z][\w-]*(?: [A-Za-z][\w-]*){0,4}?)(?= (?:is|are|uses|requires|depends|must|can)\b)', knowledge, re.M):
        yield name


def _pattern(aliases):
    return re.compile(r'(?<![a-z0-9])(?:' + '|'.join(re.escape(a) for a in sorted(aliases, key=len, reverse=True)) + r')(?![a-z0-9])', re.I)


def _page_evidence(record, text, aliases, indexed):
    folded, definitions = indexed
    if not any(a.casefold() in folded for a in aliases):
        return
    pattern = _pattern(aliases)
    for line in text.partition('\n## Sources')[0].splitlines():
        if line.startswith(('#', '- Also known as:', '- Aliases:')) or not pattern.search(_plain(line)):
            continue
        evidence = []
        for label in CITATION.findall(line):
            source = definitions.get(label, '')
            ids, dates = SOURCE_ID.findall(source), DAY.findall(source)
            if ids and dates:
                evidence.append({'record': record, 'source': ids[0], 'date': dates[0],
                                 'speaker': '', 'sentence': _plain(line),
                                 'private': bool(PRIVATE.search(line) or PRIVATE.search(text.split('\n', 1)[0]))})
        yield line, evidence


def _merge_groups(seeds):
    groups = []
    for seed in seeds:
        keys = {a.casefold() for a in seed['aliases']}
        matches = [g for g in groups if keys & {a.casefold() for a in g['aliases']}]
        group = {'name': seed['name'], 'aliases': [], 'evidence': [], 'existing': []}
        for old in matches:
            groups.remove(old)
            for key in ('aliases', 'evidence', 'existing'):
                group[key] += old[key]
            group['name'] = old['name']
        group['aliases'] = list(dict.fromkeys([*group['aliases'], *seed['aliases']]))
        group['evidence'] += seed.get('evidence', [])
        group['existing'] += seed.get('existing', [])
        groups.append(group)
    return groups


def _valid_day(day):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        return False
    year, month, number = map(int, day.split('-'))
    return year > 0 and 1 <= month <= 12 and 1 <= number <= monthrange(year, month)[1]


def _owner_health(evidence):
    sentence = evidence['sentence']
    # Require an actual owner-health attribution, not a stray "I discussed".
    return bool(re.search(r"\b(?:my|the user's|user's|owner's)\s+(?:(?:chronic|severe|mild|own)\s+)?(?:" + HEALTH.pattern + ')'
                          + r'|(?:我的|用户的)(?:健康|哮喘|疾病|用药|治疗|抑郁|手术|怀孕|过敏|焦虑)', sentence, re.I))


def _requested(evidence, aliases):
    if evidence['speaker'].casefold() not in ('user', 'owner'):
        return False
    sentence = evidence['sentence']
    for match in REQUEST.finditer(sentence):
        before = sentence[max(0, match.start() - 20):match.start()].casefold()
        if re.search(r"(?:not|never|don't|do not)\s+$|不要$|别$", before):
            continue
        target = (match[1] or match[2]).strip(' `"“”').casefold()
        if any(target == a.casefold() or target.startswith(a.casefold() + ';') for a in aliases):
            return True
    return False


def _extracted_evidence(texts, aliases, source_records):
    pattern = _pattern(aliases)
    found = []
    for text in texts:
        # Structured Topics have already been parsed with their own attribution.
        text = re.sub(r'^## Topics\s*\n.*?(?=^## |\Z)', '', text, flags=re.M | re.S)
        for line in text.splitlines():
            if not pattern.search(line):
                continue
            days = set(DAY.findall(line))
            if len(days) != 1:
                continue  # A date range cannot date each ID independently.
            speaker = 'user' if re.search(r'[—–]\s*user\s*,', line, re.I) else ''
            for source in SOURCE_ID.findall(line):
                for record in source_records.get(source, []):
                    found.append({'record': record, 'source': source, 'date': next(iter(days)),
                                  'speaker': speaker, 'sentence': _plain(line), 'private': bool(PRIVATE.search(line))})
    return found


def _candidate(group, pages, extracts, source_records, page_index):
    aliases = group['aliases']
    evidence, doubtful, mentions = list(group['evidence']), [], set()
    pattern = _pattern(aliases)
    for record, text in pages.items():
        if record.startswith('knowledge/'):
            continue
        if record.startswith(('sessions/', 'skills/')) and pattern.search(_plain(text.partition('\n## Sources')[0])):
            mentions.add(record)
        for line, found in _page_evidence(record, text, aliases, page_index[record]):
            evidence += found
            if not found and record.startswith(('people/', 'orgs/', 'projects/')):
                doubtful.append({'record': record, 'sentence': _plain(line)})
    evidence += _extracted_evidence(extracts, aliases, source_records)
    health = bool(HEALTH.search(' '.join(aliases)))
    # Even an owner speaking about somebody else's diagnosis is not permission
    # to turn their health into an entity. Ambiguous health stays out as well.
    evidence = [e for e in evidence if _valid_day(e['date']) and (not health or _owner_health(e))]
    source_dates = {}
    for e in evidence:
        source_dates.setdefault(e['source'], set()).add(e['date'])
    evidence = [e for e in evidence if len(source_dates[e['source']]) == 1]
    requested = any(_requested(e, aliases) for e in evidence)
    private = health or bool(PERSONAL.search(' '.join(aliases))) or any(e.get('private') or PRIVATE.search(e['sentence']) for e in evidence)
    # Structured extraction precedes page summaries; keep its known speaker.
    unique = {(e['source'], e['record']): e for e in reversed(evidence)}
    evidence = sorted(unique.values(), key=lambda e: (e['date'], e['source'], e['record']))
    sources = {e['source'] for e in evidence}
    records = sorted({e['record'] for e in evidence if e['record'] in pages})
    dates = sorted({e['date'] for e in evidence if re.fullmatch(r'\d{4}-\d{2}-\d{2}', e['date'])})
    span = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days if dates else 0
    slug_name = next((a for a in aliases if a.isascii()), '')
    slug = re.sub(r'[^a-z0-9]+', '-', slug_name.casefold()).strip('-')[:70]
    slug = slug or 'topic-' + hashlib.sha256(group['name'].encode()).hexdigest()[:10]
    return {**group, 'record': next(iter(group['existing']), f'knowledge/{slug}.md'),
            'evidence': evidence, 'doubtful': list({d['record']: d for d in doubtful if d['record'] not in records}.values()),
            'source_count': len(sources), 'records': records, 'span_days': span, 'requested': requested,
            'first': dates[0] if dates else '', 'last': dates[-1] if dates else '', 'private': private,
            'sessions': sum(r.startswith('sessions/') for r in mentions | set(records)),
            'skills': sum(r.startswith('skills/') for r in mentions | set(records)),
            'qualified': bool(requested or (len(sources) >= 3 and span >= 14 and len(records) >= 2))}


def scan_topics(notebook: Notebook) -> list[dict]:
    """Return candidates with aliases and evidence; never write, merge or call a model."""
    pages = {r: notebook.read(r) for r in notebook.list()
             if not r.startswith(('logs/', 'notes/')) and r != 'skills/catalog/index.md'}
    excluded = _names(pages)
    extracts = state_path(notebook.root, 'extracts')
    notes = [p.read_text(encoding='utf-8') for p in sorted(extracts.rglob('*.md')) if p.is_file() and not p.is_symlink()]
    notes += [value['notes'] for p in sorted(extracts.rglob('*.json'))
              if p.is_file() and not p.is_symlink()
              for value in [json.loads(p.read_text(encoding='utf-8'))]
              if isinstance(value, dict) and isinstance(value.get('notes'), str)]
    texts = [text for record, text in pages.items() if not record.startswith(('sessions/', 'skills/'))] + notes
    seeds = []
    for record, text in pages.items():
        if record.startswith('knowledge/'):
            aliases = topic_aliases(text)
            if aliases:
                seeds.append({'name': aliases[0], 'aliases': aliases, 'existing': [record]})
    for text in texts:
        for row in _topic_rows(text):
            row['aliases'] = [a for a in row['aliases'] if a.casefold() not in VENDORS | GENERIC]
            if _allowed(row['name'], excluded) and not any(a.casefold() in excluded for a in row['aliases']):
                seeds.append({'name': row['name'], 'aliases': row['aliases'], 'evidence': [row]})
        for name in _legacy_seeds(text):
            if _allowed(name, excluded):
                seeds.append({'name': name, 'aliases': [name]})
    source_records, page_index = {}, {}
    for record, text in pages.items():
        definitions = dict(source_definitions(_block(text, 'Sources')))
        page_index[record] = (text.casefold(), definitions)
        for value in definitions.values():
            for source in SOURCE_ID.findall(value):
                source_records.setdefault(source, []).append(record)
    rows = [_candidate(group, pages, notes, source_records, page_index) for group in _merge_groups(seeds)]
    used = set(pages)
    for row in rows:
        if not row['existing'] and row['record'] in used:
            suffix = hashlib.sha256(row['name'].casefold().encode()).hexdigest()[:10]
            row['record'] = row['record'].removesuffix('.md') + '-' + suffix + '.md'
        used.add(row['record'])
    return sorted((row for row in rows if row['evidence'] or row['existing']), key=lambda r: (-r['source_count'], r['name']))


def map_topics(notebook: Notebook) -> tuple[list[dict], list[str]]:
    """File qualifying stubs and exact-alias merges; caller holds the maintenance lock."""
    from .merge import merge_into, weight
    from .reviews import ingest
    rows, created = [], []
    for row in scan_topics(notebook):
        if not row['qualified'] and not row['existing']:
            continue
        if row['existing']:
            kept = max(row['existing'], key=lambda r: weight(notebook.read(r)))
            for old in row['existing']:
                if old != kept:
                    merge_into(notebook, kept, old, 'shared exact topic alias')
            row['record'] = kept
        if notebook.stub_topic(row['record'], row['name'], row['aliases'], private=row['private']):
            created.append(row['record'])
        # A private topic stays private through a merge or a new evidence pass.
        text = notebook.read(row['record'])
        if row['private'] and not PRIVATE.search(text.splitlines()[0]):
            notebook.write(row['record'], text.replace('\n', ' [personal]\n', 1))
        text = notebook.read(row['record'])
        alias_line = '- Also known as: ' + '; '.join(row['aliases'])
        updated = re.sub(r'^- (?:Also known as|Aliases):.*$', alias_line, text, count=1, flags=re.M)
        if updated == text and alias_line not in text:
            updated = text.replace('\n', '\n' + alias_line + '\n', 1)
        if updated != text:
            notebook.write(row['record'], updated)
        proposals = [{'kind': 'link', 'subjects': [row['record'], d['record']],
                      'question': f"Does {d['record']} concern this topic?", 'basis': d['sentence']}
                     for d in row['doubtful']]
        for proposal in proposals:
            ingest(notebook.root, [proposal])
        rows.append(row)
    return rows, created


def apply_review(notebook, review, verdict):
    """A yes writes one cited topic link; a no records the negative match locally."""
    import posixpath
    record, target = review['subjects']
    text = notebook.read(record)
    if verdict == 'no':
        marker = f'<!-- topic-negative: {target} -->'
        if marker not in text:
            notebook.write(record, text.rstrip() + '\n\n' + marker + '\n')
        return
    section = {'people': 'People', 'orgs': 'Orgs', 'projects': 'Projects'}.get(target.split('/')[0])
    if not section:
        return
    numbers = [int(n) for n in re.findall(r'\[(\d+)\]', text)]
    number = max(numbers, default=0) + 1
    title = topic_aliases(notebook.read(target))[0]
    relative = posixpath.relpath(target, posixpath.dirname(record))
    line = f'- [{title}]({relative}) — {review["basis"]} [{number}]\n'
    if f']({relative})' not in text:
        text = text.replace(f'## {section}\n', f'## {section}\n' + line, 1)
        text = text.replace('## Sources\n', f'## Sources\n- [{number}] review:{review["id"]} — owner accepted {review["decided_at"][:10]}\n', 1)
        notebook.write(record, text)


def topic_material(notebook, record):
    """Candidate notes and matching pages for alias investigation, not primary proof."""
    row = next((r for r in scan_topics(notebook) if r['record'] == record or record in r['existing']), None)
    if not row:
        return []
    stamp = row['last'] or '1970-01-01'
    items = [{'role': 'extract', 'source': 'investigation:topic-candidate',
              'sources': sorted({e['source'] for e in row['evidence']}),
              'timestamp': stamp, 'text': json.dumps(row, ensure_ascii=False)}]
    for target in row['records']:
        items.append({'role': 'context', 'source': f'investigation:topic-page:{target}',
                      'timestamp': stamp, 'text': f'Notebook context, not primary proof: {target}\n' + notebook.read(target)})
    return items
