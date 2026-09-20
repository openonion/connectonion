"""Map observed mail domains into unverified organization candidates; no model."""

import re

from .scan import PERSONAL_MAILBOX


def _domain(address: str) -> str:
    if address.count('@') != 1:
        return ''
    local, domain = address.rsplit('@', 1)
    domain = domain.casefold().rstrip('.')
    labels = domain.split('.')
    if not local or len(labels) < 2 or not all(
            re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
        return ''
    return domain if domain not in PERSONAL_MAILBOX else ''


def map_orgs(notebook, people: list[dict], started: str, days: int, record_for) -> tuple[list[dict], list[str]]:
    """Include single contacts and notice-only domains; shortlist ranking is separate."""
    existing = {}
    for record in notebook.list('orgs'):
        section = notebook.read(record).partition('## Domains\n')[2].split('\n## ', 1)[0]
        for domain in re.findall(r'^- ([A-Za-z0-9.-]+)\s*$', section, re.M):
            existing.setdefault(domain.casefold().rstrip('.'), record)
    groups = {}
    for person in people:
        domain = _domain(str(person.get('address', '')))
        if domain:
            groups.setdefault(domain, set()).add(person['record'])
    rows, created = [], []
    for domain, contacts in sorted(groups.items()):
        record = existing.get(domain) or record_for('orgs', domain, domain)
        rows.append({'domain': domain, 'record': record, 'people': sorted(contacts),
                     'classification': 'domain candidate; organization identity unverified'})
        if not notebook.stub_org(record, domain, [domain], sorted(contacts)):
            continue
        page = notebook.read(record)
        page = page.replace('## Who they are\n- Unknown — not investigated yet',
                            '## Who they are\n- Domain candidate; organization identity unverified. [1]')
        page = page.replace('## People here\n', '## People here\n'
                            '- Observed correspondents using this domain; not evidence of employment. [1]\n')
        page = page.replace('## Uncertainties\n- Unknown — not investigated yet',
                            '## Uncertainties\n- Organization name, ownership and contact roles are unverified. '
                            'A domain can represent a service or personal site. Subdomains and other domains '
                            'are not automatically merged.\n- Unknown — not investigated yet')
        page = page.replace('- (none yet)', f'- [1] Enumeration metadata in .state/map.json; observed {started}; '
                            f'{days}-day window; email-domain association only, not verified organization membership.')
        notebook.write(record, page)
        created.append(record)
    return rows, created
