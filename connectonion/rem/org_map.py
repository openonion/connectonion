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


LEGAL_SUFFIX = re.compile(r'\b(?:pty|ltd|limited|inc|llc|corp|co|gmbh)\b\.?', re.I)


def own_domain(domain: str, owner: dict | None, owner_page: str) -> bool:
    """Is this the owner's own organisation? Never a counterparty.

    The 2026-10-10 notebook made orgs/openonion-ai from the owner's colleagues
    writing from the owner's own domain, and orgs/connectonion-com from
    pypi@connectonion.com -- CONNECTONION PTY LTD is the owner's signing entity.
    Own is a domain the owner writes from, or one named like the Company or
    Signing entity on the owner's page."""
    mine = {organisation(d) for d in map(_domain, (owner or {}).get('addresses', [])) if d}
    names = set()
    for line in re.findall(r'^- (?:Company|Signing entity): (.+)$', owner_page, re.M):
        line = re.sub(r'\[(\d+)\]', '', re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', line))
        names |= {re.sub(r'[^a-z0-9]', '', LEGAL_SUFFIX.sub('', part).casefold()) for part in re.split(r'[;,/]', line)}
    org = organisation(domain)
    return org in mine or org.split('.')[0] in names - {'', 'unknown'}


def map_orgs(notebook, people: list[dict], started: str, days: int, record_for,
             owner: dict | None = None) -> tuple[list[dict], list[str]]:
    """One candidate per organisation someone with a page writes from; no model.

    A company's sending and login subdomains are the company (#1844): on the
    owner's map accounts.google.com and ad.unsw.edu.au were organisations of
    their own. A domain only notice senders use gets no page -- 35 of 272 real
    organisations were login and mailer domains that nobody wrote from. Nor
    does one whose every correspondent is automated or one-way: lu.ma got a
    page from sign-in codes and registrations alone (2026-10-20).
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
            group = groups.setdefault(organisation(domain), {'domains': set(), 'contacts': set(), 'talks': False})
            group['domains'].add(domain)
            if person.get('record'):   # a notice sender has no page to link to
                group['contacts'].add(person['record'])
                group['talks'] |= not (person.get('automated_hint') or person.get('one_way'))
    owner_page = notebook.read(owner['record']) if owner and notebook.path(owner['record']).is_file() else ''
    for domain in map(_domain, (owner or {}).get('addresses', [])):
        if domain:
            group = groups.setdefault(organisation(domain), {'domains': set(), 'contacts': set(), 'talks': False})
            group['domains'].add(domain)
    groups = {key: group for key, group in groups.items()
              if own_domain(key, owner, owner_page) or (group['contacts'] and group['talks'])}
    rows, created = [], []
    for domain, group in sorted(groups.items()):
        contacts, domains = group['contacts'], sorted(group['domains'] | {domain})
        record = next((existing[d] for d in [domain, *domains] if d in existing), None) \
            or record_for('orgs', domain, domain)
        rows.append({'domain': domain, 'record': record, 'people': sorted(contacts), 'domains': domains,
                     **({'own': True} if own_domain(domain, owner, owner_page) else {}),
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
