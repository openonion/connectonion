"""Map observed mail domains into unverified organization candidates; no model."""

import re

from .scan import personal_mailbox


def _domain(address: str) -> str:
    if address.count('@') != 1:
        return ''
    local, domain = address.rsplit('@', 1)
    domain = domain.casefold().rstrip('.')
    labels = domain.split('.')
    if not local or len(labels) < 2 or not all(
            re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
        return ''
    return '' if personal_mailbox(domain) else domain


# Second-level labels under a country code: unsw.edu.au and example.co.uk are the
# organisation, not edu.au or co.uk. No suffix list ships with the package; these
# cover the mail a real notebook carries, and a miss only leaves a subdomain its
# own page, as before.
SECOND_LEVEL = frozenset({'com', 'net', 'org', 'edu', 'gov', 'co', 'ac', 'id', 'asn', 'or', 'ne', 'go', 'gen'})


def organisation(domain: str) -> str:
    """The registrable domain a mail domain belongs to: accounts.google.com -> google.com."""
    labels = domain.split('.')
    keep = 3 if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in SECOND_LEVEL else 2
    return '.'.join(labels[-keep:])


def map_orgs(notebook, people: list[dict], started: str, days: int, record_for) -> tuple[list[dict], list[str]]:
    """One candidate per organisation someone with a page writes from; no model.

    A company's sending and login subdomains are the company (#1844): on the
    owner's map accounts.google.com and ad.unsw.edu.au were organisations of
    their own. A domain only notice senders use gets no page -- 35 of 272 real
    organisations were login and mailer domains that nobody wrote from.
    """
    existing = {}
    for record in notebook.list('orgs'):
        section = notebook.read(record).partition('## Domains\n')[2].split('\n## ', 1)[0]
        for domain in re.findall(r'^- ([A-Za-z0-9.-]+)\s*$', section, re.M):
            existing.setdefault(domain.casefold().rstrip('.'), record)
    groups = {}
    for person in people:
        domain = _domain(str(person.get('address', '')))
        if domain:
            group = groups.setdefault(organisation(domain), {'domains': set(), 'contacts': set()})
            group['domains'].add(domain)
            if person.get('record'):   # a notice sender has no page to link to
                group['contacts'].add(person['record'])
    groups = {key: group for key, group in groups.items() if group['contacts']}
    rows, created = [], []
    for domain, group in sorted(groups.items()):
        contacts, domains = group['contacts'], sorted(group['domains'] | {domain})
        record = next((existing[d] for d in [domain, *domains] if d in existing), None) \
            or record_for('orgs', domain, domain)
        rows.append({'domain': domain, 'record': record, 'people': sorted(contacts), 'domains': domains,
                     'classification': 'domain candidate; organization identity unverified'})
        if not notebook.stub_org(record, domain, domains, sorted(contacts)):
            continue
        page = notebook.read(record)
        page = page.replace('## Who they are\n- Unknown — not investigated yet',
                            '## Who they are\n- Domain candidate; organization identity unverified. [1]')
        page = page.replace('## People here\n', '## People here\n'
                            '- Observed correspondents using this domain; not evidence of employment. [1]\n')
        page = page.replace('## Uncertainties\n- Unknown — not investigated yet',
                            '## Uncertainties\n- Organization name, ownership and contact roles are unverified. '
                            'A domain can represent a service or personal site. Subdomains are merged into '
                            'their registrable domain; other domains are not.\n- Unknown — not investigated yet')
        page = page.replace('- (none yet)', f'- [1] Enumeration metadata in .state/map.json; observed {started}; '
                            f'{days}-day window; email-domain association only, not verified organization membership.')
        notebook.write(record, page)
        created.append(record)
    return rows, created
