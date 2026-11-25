"""Conservative hierarchy inference, separate read-only plans from locked writes.

Only cited identity statements, subject signatures and explicit structure inputs
are eligible. A domain, arbitrary mention or team nickname is not an edge.
"""
import hashlib
import re
from contextlib import nullcontext

from . import facts
from .files import maintenance_lock
from .reader_model import notebook_links, source_definitions

TEAM_CODE = re.compile(r'\b(\d{4})-[A-Z]\d{2}[A-Z]-[A-Z][A-Z0-9]+\b')
ROLE = re.compile(r'\b(Product Owner|Scrum Master|Gitlab Moderator|Events Coordinator|Course Admin(?:istrator|istration)?|'
                  r'Director of [\w &-]+|[\w -]+ Coordinator|[\w -]+ Manager|[\w -]+ Officer)\b', re.I)
UNIT_NAME = re.compile(r'\b((?:Faculty|School|Department|Division) of [\w &-]+|[\w &-]+ (?:Program(?:me)?|Lab(?:oratory)?|Team))\b', re.I)
SHARED = re.compile(r'\bshared mailbox\b', re.I)


def _title(book, path):
    return book.read(path).split('\n')[0].lstrip('# ').strip()


def _org_for(book, record):
    """Use explicit affiliation only, never a mail domain."""
    text = book.read(record)
    label = 'Parent' if record.startswith('orgs/') else 'Company'
    values = [v for v in facts.parse(text, record).get(label, []) if v['citations']]
    linked = {path for v in values for path in notebook_links(record, v['value']) if path in book.list('orgs')}
    if record.startswith('orgs/'):
        return record
    if not linked:
        names = {v['value'].casefold() for v in values}
        linked = {path for path in book.list('orgs') if _title(book, path).casefold() in names}
    if not linked:
        for path in book.list('orgs'):
            page = book.read(path)
            roster = re.search(r'^## People here\s*\n(.*?)(?=^## |\Z)', page, re.M | re.S)
            contacts = facts.parse(page, path)['Your contacts']
            if record in notebook_links(path, '\n'.join(v['value'] for v in contacts) + '\n' + (roster[1] if roster else '')):
                linked.add(path)
    return next(iter(linked)) if len(linked) == 1 else ''


def _page_evidence(book, record):
    text = book.read(record)
    sources = dict(source_definitions(text.partition('\n## Sources\n')[2]))
    parsed = facts.parse(text, record)
    rows = []
    for label in ('Role', 'Unit'):
        for value in parsed.get(label, []):
            for number in value['citations']:
                if number in sources:
                    rows.append({'field': label, 'value': value['value'], 'source': sources[number]})
    # The lead / identity section may establish membership when Company is Unknown.
    identity = text.partition('## Facts')[0]
    section = re.search(r'^## Who they are\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    identity += '\n' + (section[1] if section else '')
    name = _title(book, record).split()[0]
    for line in identity.splitlines():
        if not re.match(rf'^(?:- )?{re.escape(name)}\b.*?\b(?:is|identifies|signs)\b', line, re.I):
            continue
        numbers = facts.CITES.search(line.rstrip(' .'))
        for number in re.findall(r'\[(W?\d+)\]', numbers[1]):
            if number in sources:
                rows.append({'field': 'Identity', 'value': re.sub(r'\[W?\d+\]', '', line), 'source': sources[number]})
    if SHARED.search(_title(book, record)):
        source = next((sources[n] for v in parsed.get('Company', []) for n in v['citations'] if n in sources), '')
        if source:
            rows.append({'field': 'Mailbox', 'value': re.sub(r'^Not a person:\s*', '', SHARED.sub('', _title(book, record)), flags=re.I).strip(), 'source': source})
    return rows


def _chain(value, *, named=True):
    codes = list(dict.fromkeys(match[0] for match in TEAM_CODE.finditer(value)))
    if codes:
        # Multiple codes in one assertion are ambiguous, not multiple jobs.
        return [(codes[0].split('-')[0], 'course'), (codes[0], 'team')] if len(codes) == 1 else []
    units = []
    for part in re.split(r'[|,;\n]', value):
        part = re.split(r'\b(?:at|in)\s+', part.strip(), flags=re.I)[-1]
        part = re.sub(r'^(?:(?:Deputy|Associate|Assistant) )?(?:Director|Head|Manager|Coordinator) (?:of|for) ', '', part, flags=re.I)
        part = re.sub(r'^(?:the|a|an) ', '', part, flags=re.I)
        match = UNIT_NAME.search(part) if named else None
        if not match and named:
            match = re.fullmatch(r'(?:[A-Z][\w-]* )*Founders', part)
        if match:
            name = match[0].strip()
            if not name[0].isupper() or len(name) > 90:
                continue
            first, last = name.split()[0].casefold(), name.split()[-1].casefold()
            kind = {'faculty': 'faculty', 'school': 'school', 'department': 'department', 'division': 'department'}.get(first)
            kind = kind or ('programme' if last.startswith('program') or last == 'founders' else 'lab' if last.startswith('lab') else 'team')
            units.append((name, kind))
    if units:
        if len({kind for _, kind in units}) != len(set(units)):
            return []  # Equal-level names establish siblings, never a parent edge.
        order = {'faculty': 0, 'school': 1, 'department': 2, 'programme': 3, 'lab': 4, 'team': 5}
        return sorted(dict.fromkeys(units), key=lambda unit: order[unit[1]])
    bare = re.search(r'\b(?:course|course admin(?:istrator|istration)?)\b[^\d]*([0-9]{4}(?:/[0-9]{4})?)\b', value, re.I)
    if bare:
        return [(bare[1], 'course')]
    courses = re.findall(r'\b[A-Z]{2,8}(\d{4})(?:/(?:[A-Z]{2,8})?(\d{4}))?\b', value)
    return [('/'.join(part for part in courses[0] if part), 'course')] if len(courses) == 1 else []


def _unit_path(book, parent, name, kind):
    for path in book.list('orgs'):
        parsed = facts.parse(book.read(path), path)
        parents = [p for v in parsed['Parent'] for p in notebook_links(path, v['value'])]
        if _title(book, path).casefold() == name.casefold() and parents == [parent] and any(v['value'] == kind for v in parsed['Kind']):
            return path
    slug = re.sub(r'[^a-z0-9]+', '-', name.casefold()).strip('-')[:70]
    digest = hashlib.sha256(f'{parent}\n{name.casefold()}'.encode()).hexdigest()[:10]
    return f'orgs/{slug}-{digest}.md'


def infer(book, record, evidence=()):
    """No writes. Return units, memberships and existing-review-format questions."""
    plan = {'record': record, 'units': [], 'memberships': [], 'reviews': []}
    org = _org_for(book, record)
    if not org:
        return plan
    shared = bool(SHARED.search(_title(book, record)))
    for row in [*_page_evidence(book, record), *evidence]:
        if row.get('field') not in ('Role', 'Unit', 'Identity', 'Signature', 'Structure', 'Mailbox', 'Subject') or not row.get('source'):
            continue
        if row['source'].startswith(('investigation:', 'review:')):
            continue
        if re.search(r'\b(?:not|no longer|former|possibly|possible|unconfirmed|unknown)\b|\?', row['value'], re.I):
            continue
        parent = org
        chain = _chain(row['value'], named=row['field'] not in ('Identity', 'Subject'))
        if not chain and row['field'] == 'Mailbox':
            chain = [(row['value'], 'team')]
        for name, kind in chain:
            path = _unit_path(book, parent, name, kind)
            candidate = dict(path=path, name=name, kind=kind, parent=parent, source=row['source'],
                             date=row.get('date', ''), provenance='web' if row['source'].startswith(('http:', 'https:', 'web:')) else 'mail')
            if not any(u['path'] == path for u in plan['units']):
                plan['units'].append(candidate)
            parent = path
        role = ROLE.search(row['value'])
        if chain and record.startswith('people/') and not shared and row['field'] not in ('Structure', 'Subject'):
            membership = dict(path=parent, role=role[0].strip() if role else '', source=row['source'], date=row.get('date', ''))
            if not any(m['path'] == parent for m in plan['memberships']):
                plan['memberships'].append(membership)
    plan['reviews'] = _conflicts(book, plan, org)
    return plan


def _conflicts(book, plan, org):
    questions = []
    for member in plan['memberships']:
        candidate = next(u for u in plan['units'] if u['path'] == member['path'])
        code = TEAM_CODE.fullmatch(candidate['name'])
        if not code or not member['role']:
            continue
        for person in book.list('people'):
            if person == plan['record'] or _org_for(book, person) != org:
                continue
            for row in _page_evidence(book, person):
                other_role = ROLE.search(row['value'])
                for other in TEAM_CODE.finditer(row['value']):
                    if other[0] == code[0] or other[0].split('-')[-1] != code[0].split('-')[-1]:
                        continue
                    if other_role and other_role[0].casefold() == member['role'].casefold():
                        question = f"Do these {member['role']} claims refer to distinct teams: {other[0]} and {code[0]}?"
                        questions.append(dict(kind='question', subjects=[candidate['path']], question=question,
                                              basis=f"{person}: {other[0]} ({row['source']}); {plan['record']}: {code[0]} ({member['source']}). Different codes retained."))
    return list({q['question']: q for q in questions}.values())


def _append_fact(book, path, label, value, row):
    text = facts.upgrade(path, book.read(path))
    if any(v['value'] == value for v in facts.parse(text, path)[label]):
        return
    text, number = facts._cite(text, row)
    line = f'- {label}: {value} [{number}]'
    unknown = rf'(?m)^- {re.escape(label)}: Unknown$'
    if re.search(unknown, text):
        text = re.sub(unknown, lambda _: line, text, count=1)
    else:
        at = facts._bounds(text, 'Facts')[1]
        text = text[:at].rstrip() + '\n' + line + '\n\n' + text[at:]
    book.write(path, text)


def apply(book, plan, *, lock_held=False):
    """Save a deterministic plan during authorised maintenance, never during reads."""
    from .reviews import ingest
    created = []
    with nullcontext() if lock_held else maintenance_lock(book.root):
        for unit in plan['units']:
            if book.path(unit['path']).exists():
                continue  # Existing facts are never overwritten by inference.
            book.stub_org(unit['path'], unit['name'])
            _append_fact(book, unit['path'], 'Kind', unit['kind'], unit)
            _append_fact(book, unit['path'], 'Parent', f"[[{unit['parent']}]]", unit)
            if unit['provenance'] == 'web':
                text = book.read(unit['path']).replace(unit['source'] + ' —', unit['source'] + ' — web-sourced;')
                book.write(unit['path'], text)
            created.append(unit['path'])
        for member in plan['memberships']:
            link = f"[[{member['path']}]]"
            _append_fact(book, plan['record'], 'Unit', link, member)
            if member['role']:
                _append_fact(book, plan['record'], 'Role in unit', link + ' — ' + member['role'], member)
        # ingest has a two-question budget per call; keep every deterministic conflict.
        for question in plan['reviews']:
            ingest(book.root, [question])
    return {'created': created, 'reviews': plan['reviews']}


def subject_evidence(book, record, metadata):
    """Authored subjects create candidates only; merely being cc'd proves no unit."""
    from .mail import _address
    addresses = {v['value'].casefold() for v in facts.parse(book.read(record), record).get('Email', [])}
    return [{'field': 'Subject', 'value': row.get('subject', ''),
             'source': row['id'] if str(row['id']).startswith(('gmail:', 'outlook:')) else f"{row['source']}:{row['id']}",
             'date': row.get('date', '')[:10]}
            for row in metadata if row.get('id') and _address(row.get('from', '')).casefold() in addresses
            and TEAM_CODE.search(row.get('subject', ''))]


def reconcile(book, metadata=(), *, lock_held=False):
    """Cheap map pass over supported existing affiliations, no model or network."""
    created, questions = [], []
    with nullcontext() if lock_held else maintenance_lock(book.root):
        for record in book.list('people'):
            plan = infer(book, record, subject_evidence(book, record, metadata))
            result = apply(book, plan, lock_held=True)
            created += result['created']
            questions += result['reviews']
    return {'created': created, 'reviews': questions}
