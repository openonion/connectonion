"""Evidence-backed joins from human obligations to existing or inferred projects."""
import posixpath
import re
from collections import defaultdict

from .project_obligations import evidence, sections, source_entries
from .reader_model import CITATION, REFERENCE


def links(record, text):
    return {posixpath.normpath(posixpath.join(posixpath.dirname(record['path']), raw))
            for _, raw in REFERENCE.findall(text)}


def project_names(record):
    aliases = re.findall(r'^\s*-?\s*(?:also known as|aliases|aka|别名)[:：]\s*(.*)$', record['text'], re.I | re.M)
    title = record['title']
    short = re.fullmatch(r'[a-z]{2}-([a-z]{3,})', title)
    return [title, title.replace('-', ' '), *([short[1].upper()] if short else []),
            *(name.strip(' `') for line in aliases for name in re.split(r'[,;、]', CITATION.sub('', line)))]


def name_patterns(projects):
    found = []
    for row in projects:
        for name in project_names(row):
            if len(name) < 3:
                continue
            term = re.escape(name)
            if name.islower() and name.isalpha():
                term = rf'(?:`{term}`|(?:project|repository|repo)\s+{term})'
            found.append((row['path'], re.compile(r'(?<!\w)' + term + r'(?!\w)'), name.casefold()))
    return found


def join_index(projects, contexts):
    index = defaultdict(set)
    for row in projects:
        for _, source in source_entries(row):
            index[('source', source)].add(row['path'])
            thread = contexts.get(source, {}).get('thread')
            if thread:
                index[('thread', source.split(':')[0], thread)].add(row['path'])
        for target in links(row, sections(row['text']).get('facts', '')):
            if target.startswith('orgs/'):
                index[('org', target)].add(row['path'])
    return index


def matches(record, item, projects, contexts, index, names):
    # Direct links and task names are more specific than an organisation's portfolio.
    task_links = links(record, item['text'])
    direct = {p['path'] for p in projects if p['path'] in task_links}
    named = {path for path, pattern, literal in names if literal in item['text'].casefold()
             and pattern.search(item['text'])}
    if direct or named:
        return direct | named, 'explicit task link or project name', evidence(record, item['text'])[0]
    found = set()
    for source in item['sources']:
        found |= index[('source', source['source'])]
        thread = contexts.get(source['source'], {}).get('thread')
        if thread:
            found |= index[('thread', source['source'].split(':')[0], thread)]
    if found:
        return found, 'cited source or conversation belongs to project', item['sources'][0]
    body = '\n'.join(v for k, v in sections(record['text']).items() if k != 'sources')
    targets = links(record, body)
    declared = '\n'.join(line for line in sections(record['text']).get('facts', '').splitlines()
                         if re.match(r'\s*-?\s*Projects?:', line, re.I))
    direct = {p['path'] for p in projects if p['path'] in links(record, declared)}
    if len(direct) == 1:
        line = next(line for line in body.splitlines() if links(record, line) & direct)
        return direct, 'explicit project link on counterparty page', evidence(record, line, 'facts')[0]
    orgs = {record['path']} if record['category'] == 'orgs' else {t for t in links(record, sections(record['text']).get('facts', '')) if t.startswith('orgs/')}
    found = set().union(*(index[('org', org)] for org in orgs))
    line = next((line for line in body.splitlines() if links(record, line) & orgs), '')
    return found if len(found) == 1 else set(), 'shared counterparty organisation; needs review', evidence(record, line, 'facts')[0]


def candidate(record, item):
    facts = sections(record['text']).get('facts', '')
    role = re.search(r'^\s*-?\s*Role:\s*(?!Unknown\b)(.+)', facts, re.M | re.I)
    label = CITATION.sub('', role[1]).strip() if role else ''
    title = label if label and label.casefold() != 'unknown' else record['title'] + ' — unassigned obligation'
    return {'title': title,
            'suggestion': True, 'needs_review': True, 'record': record['path'],
            'text': item['text'], 'kind': item['kind'], 'evidence': item['sources'],
            'promised': item['promised'], 'path': record['path'], 'open': [item]}


def join_obligations(records, contexts, owner=None):
    projects = [r for r in records if r['category'] == 'projects']
    by_path = {p['path']: p for p in projects}
    index, candidates = join_index(projects, contexts), []
    names = name_patterns(projects)
    for row in records:
        if row['category'] not in ('people', 'orgs'):
            continue
        row['inferred_projects'] = []
        if row['path'] == owner:
            continue
        for item in row['open']:
            if item['kind'] not in ('owed', 'waiting') or item['needs_review']:
                continue
            targets, basis, source = matches(row, item, projects, contexts, index, names)
            for target in sorted(targets):
                joined = {**item, 'joined_from': row['path'],
                          'project_match': {'reason': basis, 'needs_review': basis.startswith('shared'), **source}}
                existing = by_path[target]['open']
                if not any(other['text'] == item['text'] and other['sources'] == item['sources'] for other in existing):
                    existing.append(joined)
            if (not targets or basis.startswith('shared')) and item['kind'] == 'owed':
                inferred = candidate(row, item)
                inferred['project_candidates'] = sorted(targets)
                row['inferred_projects'].append(inferred)
                candidates.append(inferred)
    return candidates
