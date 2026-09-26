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


def _mail_rows(clients: dict, days: int, mine, coverage: list, errors=None,
               inventory=None) -> tuple[list[dict], set]:
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
            rows = scan_people({kind: client}, days, own,
                               on_row=inventory.mail if inventory else None,
                               on_window=inventory.window if inventory else None)
        except Exception as error:
            coverage.append(f'{kind}: metadata scan failed ({type(error).__name__}); incomplete')
            if errors is not None: errors.append({'source': kind, 'stage': 'metadata', 'error': type(error).__name__})
            continue
        # Scanned and found nothing is not the same answer as never scanned, and
        # the count is what tells them apart. Without it an unauthorized mailbox
        # and an empty one read identically, which is the state the init contract
        # names first (#1616).
        found = f'{len(rows)} correspondents' if rows else 'no correspondents in this window'
        coverage.append(f'{kind}: metadata only, {days} days, at most 200 messages per seven-day window; ' + found)
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
    r'|feedback|invoicing|service|team|marketing|info|updates)\.[\w-]+\.[\w.-]+$', re.I)
# A sending subdomain sits *under* a company's domain: mail.aitinkerers.org,
# news.ato.gov.au. Without the second label, anyone@mail.com -- a consumer
# mailbox -- read as bulk and lost their page.
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
    """Only sends, never hears back, and looks like a system -- or is a relay.

    "Never hears back" is nearly never for a notification address: replying to
    a GitHub notification by mail once made notifications@github.com (95 in,
    1 out, display name "Aaron") a person page named after the owner.
    """
    address = row['address']
    if RELAY.search(address):
        return True
    if AUTOMATED_HINT.search(address) and row.get('received', 0) >= 10 * max(row.get('sent', 0), 1):
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


def _session_state(subscription: dict, projects: list) -> str:
    """Disabled, missing, and scanned-but-empty are three different next steps.

    "unavailable or disabled" told the user to check the wrong thing half the
    time: a path that does not exist wants the client installed or a --root, a
    disabled source wants subscribe, and an empty one wants neither.

    `projects` is the whole run's result rather than this source's, because a
    session is filed under the directory it ran in and two sources can share
    one. It is only ever read for emptiness: when nothing at all was mapped,
    every scanned source did come back empty, so the claim holds for each of
    them; when something was, this says only that the source was read.
    """
    if not subscription.get('enabled', True):
        return 'disabled; not scanned'
    if not Path(subscription.get('root', '')).is_dir():
        return 'no session directory at this path; nothing to scan'
    return 'scanned' if projects else 'scanned; no sessions in this window'


def _owner_name(clients: dict, given: str = '') -> str:
    """What the owner is called: what they said, else what a mailbox has on file."""
    if given.strip():
        return given.strip()
    for client in clients.values():
        try:
            name = client.my_name() if hasattr(client, 'my_name') else ''
        except Exception:  # A name is a nicety; a failed lookup must not block the map.
            name = ''
        if name and name.strip():
            return name.strip()
    return 'Account owner'


UNFILLED = '- Unknown — not investigated yet'


def _fill_owner(notebook: Notebook, report: dict, name: str) -> None:
    """The owner's page, filled with what the map itself knows.

    Every other page is written from the owner's point of view, and a first
    notebook opened on a blank page titled "Account owner" showed nothing of
    what the map had just learned. Only facts the enumeration holds go here --
    addresses, mailboxes, who the owner writes to most, where they have been
    working -- each cited to the map. Role, company and language are not in
    mail headers and stay Unknown for investigation. A section someone has
    already filled is never touched.
    """
    owner = report.get('owner')
    if not owner:
        return
    record = owner['record']
    page = notebook.read(record)
    original = page
    # A page nobody has investigated holds only what a map wrote, so the map
    # may rewrite it. That matters on an upgraded notebook: an older map, not
    # knowing aaron@… was the owner, made it a correspondent page -- titled by
    # the address, History "Observed mail count: 1", marked unassessed -- and
    # when the owner was recognised that page was reused as-is, still empty.
    mapped_only = 'not investigated yet' in next(
        (line for line in page.splitlines() if line.startswith('Investigation:')), '')
    title = page.splitlines()[0][2:].strip() if page.startswith('# ') else ''
    if name != 'Account owner' and (title == 'Account owner' or (
            mapped_only and title.casefold() in {a.casefold() for a in owner['addresses']})):
        page = f'# {name}\n' + page.split('\n', 1)[1]
    if mapped_only:
        page = re.sub(r'(## History\n)- Observed mail count:[^\n]*\[1\]\n', rf'\1{UNFILLED}\n', page, count=1)
        page = page.replace('- Correspondent classification unassessed; mapping does not establish a person '
                            'or employer.\n', '')
        addresses = ', '.join(owner['addresses'])
        for label in ('Email', 'Handles', 'Also known as'):
            page = re.sub(rf'^- {label}: .*$', f'- {label}: {addresses}', page, count=1, flags=re.M)
    days, date = report['days'], report['started'][:10]
    own = {row['record'] for row in report['possible_own_addresses']}
    people = [row for row in report['people'] if row.get('classification') == 'unassessed'
              and row['record'] not in own and row.get('mails')]
    people.sort(key=lambda row: (-row['mails'], row['record']))
    sent = sum(row.get('sent', 0) for row in people)
    received = sum(row.get('received', 0) for row in people)
    top = ', '.join(f"{row.get('name') or row['address']} ({row['mails']})" for row in people[:5])
    projects = sorted(report['projects'], key=lambda row: (-row['sessions'], row['name']))
    sessions = sum(row['sessions'] for row in projects)
    boxes = sorted({box for row in people for box in row.get('boxes', [])})
    filled = {
        'Who they are': [f"The owner of this notebook{'' if name == 'Account owner' else ', ' + name}; "
                         f"the other pages are written from their side. [1]"],
        'Why they are here': ['This is the owner\'s own page. [1]'],
        # With no mailbox (a page made from --name alone) there is no mail
        # history to state; leaving it Unknown lets a later init fill it.
        'History': (([f"In the {days} days to {date}: wrote {sent} and received {received} messages with "
                      f"{len(people)} correspondents in {', '.join(boxes) or 'no mailbox'}. [1]"]
                     if owner['addresses'] else [])
                    + ([f"Most mail with: {top}. [1]"] if top else [])
                    + ([f"Coding sessions in the same window: {sessions} across {len(projects)} projects; most: "
                        + ', '.join(f"{row['name']} ({row['sessions']})" for row in projects[:5]) + '. [1]']
                       if projects else [])),
    }
    for section, lines in filled.items():
        if not lines:
            continue
        page = page.replace(f'## {section}\n{UNFILLED}', f'## {section}\n' + '\n'.join(f'- {line}' for line in lines), 1)
    # init asks about every write-only address; the page names only those that
    # carry the owner's own name. On the real map the write-only list also held
    # two colleagues who answer on other channels, and a page stating they were
    # "possibly the owner's" would mislead whoever reads it.
    tokens = {part for address in owner['addresses'] for part in re.split(r'[^a-z]+', address.split('@')[0])
              if len(part) >= 4} | {part for part in re.split(r'[^a-z]+', name.casefold()) if len(part) >= 4}
    asked = [f"- Possibly also the owner's: {row['address']} ({row['sent']} sent, none received). "
             f"If it is yours: {row['confirm']}" for row in report['possible_own_addresses']
             if any(token in row['address'].split('@')[0].casefold() for token in tokens)][:5]
    if asked and '## Uncertainties\n' in page and asked[0] not in page:
        page = page.replace(f'## Uncertainties\n{UNFILLED}\n', '## Uncertainties\n', 1)
        page = page.replace('## Uncertainties\n', '## Uncertainties\n' + '\n'.join(asked) + '\n', 1)
    if '[1]' in page and '\n## Sources\n- (none yet)' in page:
        page = page.replace('\n## Sources\n- (none yet)', '\n## Sources\n- [1] Enumeration metadata, observed '
                            + report['started'] + ' — .state/map.json; window-limited, not lifetime totals', 1)
    if page != original:
        notebook.write(record, page)


def build_map(root: Path, subscriptions: dict, clients: dict, *, days: int = 150,
              skill_directories=None, mine=(), source_errors=None, absent=None, name: str = '',
              capture_sources: bool = False, progress=None) -> dict:
    """Map observed identities; correspondent classification remains unassessed."""
    notebook = Notebook(root)
    report = {'phase': 'mapping', 'started': datetime.now(timezone.utc).isoformat(),
              'days': days, 'coverage': [], 'people': [], 'projects': [], 'orgs': [], 'created': [],
              'errors': list(source_errors or []), 'automated_correspondents': [],
              'possible_own_addresses': []}
    state = root / '.state' / 'map.json'
    from .source_inventory import SourceInventory
    inventory = SourceInventory(root, progress) if capture_sources else None
    if inventory:
        inventory.snapshot_report = report
        report['source_inventory'] = inventory.save(report)
    state.parent.mkdir(parents=True, exist_ok=True)
    # The owner's page from an earlier init, so a page made from --name alone
    # is the one a mailbox connected later fills, not a second owner.
    earlier = json.loads(state.read_text()).get('owner') if state.is_file() else None
    earlier = earlier['record'] if earlier and notebook.path(earlier['record']).is_file() else None
    def save():
        atomic_write(state, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    save()
    if progress:
        progress('Skills: scanning installed metadata and creating catalog')
    report['skills'] = map_skills(notebook, skill_directories)
    if inventory:
        for skill in report['skills']['skills']:
            inventory.skill(skill)
        inventory.save(report)
    save()
    if progress:
        progress(f'Mail: scanning {len(clients)} connected source(s) over {days} days')
    if inventory:
        people, own = _mail_rows(clients, days, mine, report['coverage'], report['errors'], inventory=inventory)
    else:
        people, own = _mail_rows(clients, days, mine, report['coverage'], report['errors'])
    if progress:
        progress(f'People and organizations: grouping {len(people)} observed correspondents')
    roster = notebook.people()
    if own:
        aliases = sorted({address.casefold() for address in own})
        existing = next((p['path'] for p in roster if set(aliases).intersection(p['emails'])), None)
        owner_record = existing or earlier or _record('people', 'Account owner', aliases[0])
        owner_name = _owner_name(clients, name)
        if notebook.stub_person(owner_record, 'Account owner', aliases, email=', '.join(aliases)):
            report['created'].append(owner_record)
        report['owner'] = {'record': owner_record, 'addresses': aliases}
        report['people'].append({'record': owner_record, 'classification': 'account owner'})
    elif name.strip() or earlier:
        # init's help promises your own page, titled with your name. Without a
        # mailbox there are no addresses to key it on, but the name is enough;
        # without it `investigate me` said "Run init first" after init had run.
        owner_record = earlier or _record('people', 'Account owner', 'owner')
        owner_name = name.strip() or 'Account owner'
        if notebook.stub_person(owner_record, 'Account owner'):
            report['created'].append(owner_record)
        report['owner'] = {'record': owner_record, 'addresses': []}
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
                                 'sent': sum(row.get('sent', 0) for row in group),
                                 'received': sum(row.get('received', 0) for row in group),
                                 'boxes': sorted({box for row in group for box in row.get('boxes', [])}),
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
        count = len(report['possible_own_addresses'])
        report['coverage'].append(
            f"{count} address{'es' if count > 1 else ''} received mail from the owner and never replied; "
            f"{'they may be' if count > 1 else 'it may be'} the owner's own. Pages are kept as they are "
            "until confirmed with co wiki init --mine")
    if report['automated_correspondents']:
        report['coverage'].append(f"{len(report['automated_correspondents'])} notice or relay senders listed in "
                                  ".state/map.json without people pages")
    # Why a mailbox is not here is the command layer's knowledge, not the map's:
    # from inside, a mailbox nobody connected, one the user unsubscribed, and one
    # that failed to open are all equally absent. It says what it was told, and
    # falls back to the honest vagueness when it was told nothing.
    absent = dict(absent or {})
    report['coverage'] += [f'{kind}: ' + (absent.get(kind) or 'not configured or disabled; not searched')
                           for kind in ('gmail', 'outlook') if kind not in clients]
    report['orgs'], created_orgs = map_orgs(notebook, org_rows, report['started'], days, _record)
    report['created'] += created_orgs
    report['coverage'].append('Organizations: exact observed mail domains, including single contacts and notices; '
                              'known public mailbox domains excluded; mailbox-provider list is not exhaustive; '
                              'organization identity unverified; existing organization pages preserved')
    save()
    if progress:
        progress('Projects: scanning local session metadata')
    groups = {}
    project_rows = (scan_projects(subscriptions, days, root, on_session=inventory.session)
                    if inventory else scan_projects(subscriptions, days, root))
    for row in project_rows:
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
    report['coverage'] += [f'{name}: {sub.get("root", "")} — ' + _session_state(sub, report['projects'])
                           for name, sub in subscriptions.items() if sub.get('kind') in ('codex', 'claude-code')]
    if report.get('owner'):
        _fill_owner(notebook, report, owner_name)
    report.update(phase='partial' if report['errors'] else 'mapped', finished=datetime.now(timezone.utc).isoformat(),
                  investigation='not started', classification='unassessed; no correspondents filtered')
    if inventory:
        report['source_inventory'] = inventory.save(report)
    save()
    for category in ('people', 'projects', 'orgs'):
        lines = [f'# {category.capitalize()} map', '', 'Generated enumeration; not an investigation or importance ranking.', '']
        lines += [f'- [{Path(row["record"]).stem}](../{row["record"]})' for row in report[category]]
        notebook.write(f'notes/{category}-map.md', '\n'.join(lines) + '\n')
    if progress:
        progress(f"Map saved: {len(report['people'])} people, {len(report['orgs'])} organizations, "
                 f"{len(report['projects'])} projects; {len(report['errors'])} source error(s)")
    return report
