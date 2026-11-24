"""Read-only organisation trees. Edges need evidence; aggregates never live on pages."""
import re
from datetime import date

from . import facts
from .reader_model import PRIVATE, notebook_links, source_definitions


def _links(path, values):
    return list(dict.fromkeys(link for value in values for link in notebook_links(path, value['value'])
                              if link.startswith('orgs/')))


def _cited(values):
    return [value for value in values if value['citations']]


def _open(values):
    """A labelled membership stays behind its curtain: it never places a person in a unit."""
    return [value for value in _cited(values) if not PRIVATE.search(value['value'])]


def _parents(orgs):
    """Reject ambiguous, missing or cyclic edges, including paths leading into cycles."""
    parents, issues = {}, {path: [] for path in orgs}
    for path, org in orgs.items():
        values = org['facts']['Parent']
        links = _links(path, _cited(values))
        if values and (len(values) != 1 or len(links) != 1 or links[0] not in orgs):
            issues[path].append('Parent must cite exactly one existing organisation')
        elif values and not org['unit_kind']:
            issues[path].append('Parent requires a unit Kind')
        elif links:
            parents[path] = links[0]
    for path in list(parents):
        seen, cursor = set(), path
        while cursor in parents and cursor not in seen:
            seen.add(cursor)
            cursor = parents[cursor]
        if cursor in seen:
            issues[path].append('Parent chain contains a cycle')
    return {path: parent for path, parent in parents.items() if not issues[path]}, issues


def _structure_source(org):
    numbers = {n for label in ('Parent', 'Kind') for value in org['facts'][label] for n in value['citations']}
    sources = dict(source_definitions(org['text'].partition('\n## Sources\n')[2]))
    return 'web' if any(re.search(r'https?://|web:', sources.get(n, '')) for n in numbers) else ''


def _unit_role(person, unit):
    for row in _open(person['facts']['Role in unit']):
        if unit in notebook_links(person['path'], row['value']):
            return re.sub(r'^[\s:—–-]+', '', re.sub(r'\[\[[^\]]+\]\]|\[[^\]]+\]\([^)]+\)', '', row['value'])).strip()
    # A bare role immediately after one Unit line names that edge too.
    current = []
    span = facts._bounds(person['text'], 'Facts')
    for line in person['text'][span[0]:span[1]].splitlines() if span else []:
        if line.startswith('- Unit:'):
            current = _links(person['path'], _open(facts.values(line.partition(':')[2])))
        elif line.startswith('- Role in unit:') and current == [unit]:
            roles = _open(facts.values(line.partition(':')[2]))
            if len(roles) == 1 and not notebook_links(person['path'], roles[0]['value']):
                return roles[0]['value']
    return ''


def _ancestors(path, orgs):
    seen = set()
    while path in orgs and path not in seen:
        seen.add(path)
        yield path
        path = orgs[path]['parent']


def structure(records, owner=''):
    """Populate valid edges and direct unit memberships before obligation grouping."""
    orgs = {row['path']: row for row in records if row['category'] == 'orgs'}
    for org in orgs.values():
        kind = '; '.join(v['value'] for v in _cited(org['facts']['Kind']))
        you = '; '.join(v['value'] for v in _cited(org['facts']['You are']))
        org.update(parent='', unit_kind=kind if kind in facts.UNIT_KINDS else '',
                   you_are=you if you in facts.YOU_ARE else '', children=[], depth=0,
                   structure_source=_structure_source(org))
    parents, issues = _parents(orgs)
    for path, org in orgs.items():
        org['parent'] = parents.get(path, '')
        org['hierarchy_issues'] = issues[path]
        if org['parent']:
            orgs[org['parent']]['children'].append(path)
        if org['unit_kind'] and not org['parent']:
            org['depth'] = None
    for path, org in orgs.items():
        chain = list(_ancestors(path, orgs))
        org['depth'] = len(chain) - 1 if orgs[chain[-1]]['depth'] is not None else None
        org['children'].sort()
    for person in (row for row in records if row['category'] == 'people'):
        units = [path for path in _links(person['path'], _open(person['facts']['Unit']))
                 if path in orgs and orgs[path]['unit_kind']]
        person['units'] = [{'path': path, 'role': _unit_role(person, path)} for path in units]
        if person['path'] == owner or person.get('service') or person.get('needs_review'):
            person['units'] = []
            continue
        for path in units:
            if person['path'] not in orgs[path]['people']:
                orgs[path]['people'].append(person['path'])
            chain = list(_ancestors(path, orgs))
            if orgs[chain[-1]]['depth'] == 0 and chain[-1] not in person['organisations']:
                person['organisations'].append(chain[-1])


def obligation_units(row, records):
    """Indented Unit is metadata on one thread, never a separate obligation."""
    by_path = {record['path']: record for record in records}
    units = []
    for key in row['keys']:
        origin, _, text = key.partition('\n')
        record = by_path.get(origin, {})
        # A unit page's own thread is already scoped, without a redundant Unit line.
        if record.get('unit_kind'):
            units.append(origin)
        for raw in re.findall(r'(?:^|\s)- Unit:[ \t]*(.*?)(?=\s- Unit:|$)', text):
            for path in _links(origin, _cited(facts.values(raw))):
                if by_path.get(path, {}).get('unit_kind'):
                    units.append(path)
    return sorted(set(units))


def rollups(records, as_of=None):
    """Walk Parent, union identities, then count. A person/obligation counts once per ancestor."""
    orgs = {row['path']: row for row in records if row['category'] == 'orgs'}
    people = {path: set(org['people']) for path, org in orgs.items()}
    obligations = {path: {row['key']: row for row in org['obligations']} for path, org in orgs.items()}
    for path in orgs:
        for ancestor in _ancestors(path, orgs):
            people[ancestor].update(orgs[path]['people'])
            obligations[ancestor].update({row['key']: row for row in orgs[path]['obligations']})
    for path, org in orgs.items():
        placed_people = {person['path'] for person in records for unit in person.get('units', [])
                         if path in set(_ancestors(unit['path'], orgs))}
        placed = {row['key'] for row in obligations[path].values() if row.get('units')}
        org['unplaced'] = {'people': sorted(set(org['people']) - placed_people),
                           'obligations': sorted(set(obligations[path]) - placed)}
        org['obligations'] = list(obligations[path].values())
        org['rollup'] = {'open_owed': sum(row['dir'] == 'mine' for row in org['obligations']),
                         'people': len(people[path]),
                         'overdue': sum(row['dir'] == 'mine' and bool(row['due'])
                                        and row['due'] < (as_of or date.today()).isoformat()
                                        for row in org['obligations'])}
