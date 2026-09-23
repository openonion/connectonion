"""Build a deterministic, resumable entity map before any investigation."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .files import Notebook, atomic_write
from .scan import scan_people, scan_projects, canonical_origin, AUTOMATED_HINT
from .skill_map import map_skills
from .org_map import map_orgs


def _record(category: str, name: str, identity: str) -> str:
    slug = re.sub(r'[^\w-]+', '-', name.lower()).strip('-')[:70] or 'entry'
    return f'{category}/{slug}-{hashlib.sha256(identity.encode()).hexdigest()[:10]}.md'


def _mail_rows(clients: dict, days: int, mine, coverage: list, errors=None) -> tuple[list[dict], set]:
    own, available, merged = set(mine), {}, {}
    for kind, client in clients.items():
        try:
            own.update(client.my_addresses())
            available[kind] = client
        except Exception as error:  # Provider failures must not block other maps.
            coverage.append(f'{kind}: unavailable ({type(error).__name__}); not searched')
            if errors is not None: errors.append({'source': kind, 'stage': 'account', 'error': type(error).__name__})
    for kind, client in available.items():
        try:
            rows = scan_people({kind: client}, days, own)
        except Exception as error:
            coverage.append(f'{kind}: metadata scan failed ({type(error).__name__}); incomplete')
            if errors is not None: errors.append({'source': kind, 'stage': 'metadata', 'error': type(error).__name__})
            continue
        coverage.append(f'{kind}: metadata only, {days} days, at most 200 messages per seven-day window')
        for row in rows:
            old = merged.get(row['address'])
            if old:
                for key in ('mails', 'sent', 'received'):
                    row[key] += old[key]
                row['first'], row['last'] = min(old['first'], row['first']), max(old['last'], row['last'])
                row['boxes'] = sorted(set(old['boxes'] + row['boxes']))
                row['subjects'] = list(dict.fromkeys(old['subjects'] + row['subjects']))[:3]
                row['name'] = row['name'] or old['name']
                row['one_way'] = row['sent'] == 0 or row['received'] == 0
            merged[row['address']] = row
    return sorted(merged.values(), key=lambda row: (-row['mails'], row['address'])), own


# Relays: an event platform writes on someone's behalf from an address of its own.
RELAY = re.compile(r'@(?:[\w-]+\.)*luma-mail\.com$', re.I)
# Where bulk mail comes from: a newsletter platform, or a sending subdomain a
# company keeps apart from its people (mail.aitinkerers.org, e.domain.com.au,
# news.ato.gov.au). A person writes from the company domain itself. On
# 2026-09-23, 176 of 399 people pages were one-way senders, and the named
# ones -- Substack, beehiiv, Coles specials, Medibank comms -- were all of this
# shape, while the one-way *people* (a recruiter, a client who wrote first)
# wrote from their own company domain.
BULK = re.compile(
    r'@(?:[\w-]+\.)*(?:substack\.com|beehiiv\.com|shopifyemail\.com|hs-send\.com|loops\.so|docusign\.net'
    r'|mailchimpapp\.com|mcsv\.net|sendgrid\.net|klaviyomail\.com|convertkit-mail\d*\.com)$'
    r'|@(?:mail|e|eg|email|emails|e-mails|news|newsletter|comms|edm|specials|communication|survey'
    r'|feedback|invoicing|service|team|marketing|info|updates)\.[\w.-]+$', re.I)
# A ConnectOnion agent's own address. It is software writing, not a person.
AGENT_ADDRESS = re.compile(r'^0x[0-9a-f]{6,}@', re.I)


# How much one-way writing stops looking like an unanswered message. Writing to
# a new contact once and hearing nothing is ordinary; writing weekly for months
# and never once hearing back is the shape of an address you own. On the real
# 90-day map of 2026-09-23 the owner's own Gmail carried 106 sent and 0
# received, while the genuinely unanswered strangers sat at one or two.
WRITE_ONLY_MIN = 3


def _write_only(row: dict) -> bool:
    """Mail the owner keeps sending to an address that has never once replied.

    This is the shape of the owner's own other mailbox, and the map cannot tell
    it apart from a person who does not answer -- an assistant, a family member
    on a shared laptop, and a self-addressed notes inbox all look identical from
    the headers. So it is a question to put to the owner, never a merge: the
    cost of guessing wrong is pulling a real person's mail into the owner's page
    or the owner's mail into a stranger's.

    Notice senders are excluded because they are the opposite case -- they write
    to the owner -- and addresses like a support desk that never answers are
    already named by AUTOMATED_HINT.
    """
    if row.get('received') or row.get('sent', 0) < WRITE_ONLY_MIN:
        return False
    address = row['address']
    return not (AUTOMATED_HINT.search(address) or BULK.search(address)
                or RELAY.search(address) or AGENT_ADDRESS.search(address))


def _notice(row: dict) -> bool:
    """Only sends, never hears back, and looks like a system -- or is a relay."""
    address = row['address']
    if RELAY.search(address):
        return True
    return bool(row.get('one_way') and (AUTOMATED_HINT.search(address) or BULK.search(address)
                                         or AGENT_ADDRESS.search(address)))


def _people_groups(rows: list[dict]) -> list[list[dict]]:
    """Rows that are one person: the same full display name (two words or more).

    A single first name ("Aaron", "John") is too common to join on, so it keeps its
    own page. Most mail first, so the busiest address leads its group.
    """
    groups = {}
    for row in rows:
        name = ' '.join(str(row.get('name') or '').split()).casefold()
        key = name if len(name.split()) >= 2 and '@' not in name else row['address'].casefold()
        groups.setdefault(key, []).append(row)
    return sorted(groups.values(), key=lambda g: (-sum(r.get('mails', 0) for r in g), g[0]['address']))


def build_map(root: Path, subscriptions: dict, clients: dict, *, days: int = 150,
              skill_directories=None, mine=(), source_errors=None) -> dict:
    """Map observed identities; correspondent classification remains unassessed."""
    notebook = Notebook(root)
    report = {'phase': 'mapping', 'started': datetime.now(timezone.utc).isoformat(),
              'days': days, 'coverage': [], 'people': [], 'projects': [], 'orgs': [], 'created': [],
              'errors': list(source_errors or []), 'automated_correspondents': [],
              'possible_own_addresses': []}
    state = root / '.state' / 'map.json'
    state.parent.mkdir(parents=True, exist_ok=True)
    def save():
        atomic_write(state, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    save()
    report['skills'] = map_skills(notebook, skill_directories)
    save()
    people, own = _mail_rows(clients, days, mine, report['coverage'], report['errors'])
    roster = notebook.people()
    if own:
        aliases = sorted({address.casefold() for address in own})
        existing = next((p['path'] for p in roster if set(aliases).intersection(p['emails'])), None)
        owner_record = existing or _record('people', 'Account owner', aliases[0])
        if notebook.stub_person(owner_record, 'Account owner', aliases, email=', '.join(aliases)):
            report['created'].append(owner_record)
        report['owner'] = {'record': owner_record, 'addresses': aliases}
        report['people'].append({'record': owner_record, 'classification': 'account owner'})
    org_rows = []
    for group in _people_groups(people):
        addresses = [row['address'] for row in group]
        first = group[0]
        automated = all(AUTOMATED_HINT.search(row['address']) for row in group)
        # A notice sender that never hears back, or someone reachable only through
        # an event platform's relay, is not a person the user deals with. On one
        # real mailbox this was 165 of 565 people pages (Neon Changelog, Airwallex,
        # event platforms). They stay in the map report; they get no page.
        if all(_notice(row) for row in group):
            report['automated_correspondents'].extend(group)
            org_rows += [{'address': a, 'record': None} for a in addresses]
            continue
        if automated:
            report['automated_correspondents'].extend(group)
        existing = next((p['path'] for p in roster if {a.casefold() for a in addresses} & set(p['emails'])), None)
        name = next((row['name'] for row in group if row.get('name')), '') or first['address']
        record = existing or _record('people', name, first['address'])
        made = notebook.stub_person(record, name, addresses, email=', '.join(addresses))
        mails = sum(row.get('mails', 0) for row in group)
        report['people'].append({**first, 'mails': mails, 'addresses': addresses, 'record': record,
                                 'classification': 'automated candidate' if automated else 'unassessed'})
        org_rows += [{'address': a, 'record': record} for a in addresses]
        # Asked about, not acted on: the page stays exactly as it is until the
        # owner answers with --mine, because only they can tell their own
        # mailbox from someone who never writes back.
        report['possible_own_addresses'] += [
            {'address': row['address'], 'sent': row.get('sent', 0), 'record': record,
             'confirm': 'co wiki init --mine ' + row['address']}
            for row in group if _write_only(row)]
        if automated:
            page = notebook.read(record)
            marker = '- Correspondent classification: automated candidate; not verified as a person.'
            if marker not in page:
                notebook.write(record, page.replace('## Uncertainties\n', '## Uncertainties\n' + marker + '\n'))
        if made:
            notes = '- Correspondent classification unassessed; mapping does not establish a person or employer.\n'
            if len(addresses) > 1:
                # One person, several addresses: the same display name on a work and a
                # personal address split one relationship across pages that each knew half.
                notes += (f"- Addresses grouped by the display name “{name}”: {', '.join(addresses)}. "
                          "Confirm they are one person before relying on it.\n")
            notebook.write(record, notebook.read(record).replace('## Uncertainties\n', '## Uncertainties\n' + notes))
            page = notebook.read(record)
            dates = [row.get('first') for row in group if row.get('first')], [row.get('last') for row in group if row.get('last')]
            boxes = sorted({box for row in group for box in row.get('boxes', [])})
            details = (f"Observed mail count: {mails}; first: {min(dates[0]) if dates[0] else 'unknown'}; "
                       f"last: {max(dates[1]) if dates[1] else 'unknown'}; mailboxes: {', '.join(boxes) or 'unknown'}. [1]")
            page = page.replace('## History\n- Unknown — not investigated yet', '## History\n- ' + details)
            page = page.replace('- (none yet)', '- [1] Enumeration metadata, observed ' + report['started'] + ' — .state/map.json; window-limited, not lifetime totals')
            notebook.write(record, page)
            report['created'].append(record)
    report['possible_own_addresses'].sort(key=lambda row: (-row['sent'], row['address']))
    if report['possible_own_addresses']:
        report['coverage'].append(
            f"{len(report['possible_own_addresses'])} addresses received mail from the owner and never replied; "
            "they may be the owner's own. Pages are kept as they are until confirmed with co wiki init --mine")
    if report['automated_correspondents']:
        report['coverage'].append(f"{len(report['automated_correspondents'])} notice or relay senders listed in "
                                  ".state/map.json without people pages")
    report['coverage'] += [f'{kind}: not configured or disabled; not searched' for kind in ('gmail', 'outlook') if kind not in clients]
    report['orgs'], created_orgs = map_orgs(notebook, org_rows, report['started'], days, _record)
    report['created'] += created_orgs
    report['coverage'].append('Organizations: exact observed mail domains, including single contacts and notices; '
                              'known public mailbox domains excluded; mailbox-provider list is not exhaustive; '
                              'organization identity unverified; existing organization pages preserved')
    save()
    groups = {}
    for row in scan_projects(subscriptions, days):
        identity = canonical_origin(row['origin']) or row['repo'] or row['path']
        group = groups.setdefault(identity, {'name': Path(row['repo'] or row['path']).name,
                                            'paths': [], 'sessions': 0, 'first': row['first'], 'last': row['last']})
        group['paths'].append(row['path'])
        group['sessions'] += row['sessions']
        group['first'] = min(group['first'], row['first'])
        group['last'] = max(group['last'], row['last'])
    for identity, row in groups.items():
        record = _record('projects', row['name'], identity)
        existing = next((r for r in notebook.list('projects')
                         if any(path in notebook.read(r).splitlines() or f'- {path}' in notebook.read(r).splitlines()
                                for path in row['paths'])), None)
        record = existing or record
        if notebook.stub_project(record, row['name'], row['paths'], sessions=row['sessions'],
                                 first_seen=row['first'], last_seen=row['last']):
            report['created'].append(record)
        # Refresh only deterministic numeric/date fields inside Paths; retain prose.
        page = notebook.read(record)
        section = re.search(r'(?ms)^## Paths\n(.*?)(?=^## |\Z)', page)
        if section:
            body = section.group(1)
            for label, value in (('Sessions', row['sessions']), ('First seen', row['first']), ('Last seen', row['last'])):
                body = re.sub(r'^- ' + label + r': (?:[0-9-]+)$', '- ' + label + ': ' + str(value), body, flags=re.M)
            for path in row['paths']:
                if '- ' + path not in body.splitlines():
                    body = '- ' + path + '\n' + body
            updated = page[:section.start(1)] + body + page[section.end(1):]
            if updated != page:
                notebook.write(record, updated)
        report['projects'].append({**row, 'record': record})
    report['coverage'] += [f'{name}: {sub.get("root", "")} — ' +
                           ('scanned' if sub.get('enabled', True) and Path(sub.get('root', '')).is_dir() else 'unavailable or disabled')
                           for name, sub in subscriptions.items() if sub.get('kind') in ('codex', 'claude-code')]
    report.update(phase='partial' if report['errors'] else 'mapped', finished=datetime.now(timezone.utc).isoformat(),
                  investigation='not started', classification='unassessed; no correspondents filtered')
    save()
    for category in ('people', 'projects', 'orgs'):
        lines = [f'# {category.capitalize()} map', '', 'Generated enumeration; not an investigation or importance ranking.', '']
        lines += [f'- [{Path(row["record"]).stem}](../{row["record"]})' for row in report[category]]
        notebook.write(f'notes/{category}-map.md', '\n'.join(lines) + '\n')
    return report
