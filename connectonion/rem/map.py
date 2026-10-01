"""Build a deterministic, resumable entity map before any investigation."""

import collections
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .files import Notebook, atomic_write, maintenance_lock, read_json, state_path
from .scan import (scan_people, scan_projects, canonical_origin, main_checkout, not_a_project,
                   AUTOMATED_HINT, SHORT_SESSION)
from .skill_map import map_skills
from .org_map import _domain, map_orgs, organisation


def _record(category: str, name: str, identity: str) -> str:
    slug = re.sub(r'[^\w-]+', '-', name.lower()).strip('-')[:70] or 'entry'
    return f'{category}/{slug}-{hashlib.sha256(identity.encode()).hexdigest()[:10]}.md'


def _mail_rows(clients: dict, days: int, mine, coverage: list, errors=None, progress=None,
               inventory=None, own_names=None) -> tuple[list[dict], set]:
    own, available, merged = set(mine), {}, {}
    for kind, client in clients.items():
        try:
            own.update(client.my_addresses())
            available[kind] = client
        except Exception as error:  # Provider failures must not block other maps.
            coverage.append(f'{kind}: unavailable ({type(error).__name__}); not searched')
            if errors is not None: errors.append({'source': kind, 'stage': 'account', 'error': type(error).__name__})
    for kind, client in available.items():
        if progress:
            progress(f"scanning {kind} mail metadata")
        try:
            rows = scan_people({kind: client}, days, own,
                               on_row=inventory.mail if inventory else None,
                               on_window=inventory.window if inventory else None, own_names=own_names)
        except Exception as error:
            coverage.append(f'{kind}: metadata scan failed ({type(error).__name__}); incomplete')
            if errors is not None: errors.append({'source': kind, 'stage': 'metadata', 'error': type(error).__name__})
            continue
        # Scanned and found nothing is not the same answer as never scanned, and
        # the count is what tells them apart. Without it an unauthorized mailbox
        # and an empty one read identically, which is the state the init contract
        # names first (#1616).
        found = f'{len(rows)} correspondents' if rows else 'no correspondents in this window'
        coverage.append(f'{kind}: metadata only, {days} days; a seven-day window at the 200-message '
                        'listing cap is split until every message in it is listed; ' + found)
        if progress:
            progress(f"scanned {kind} mail metadata", len(rows))
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
    r'|mailchimpapp\.com|mcsv\.net|sendgrid\.net|klaviyomail\.com|convertkit-mail\d*\.com'
    # Workday writes for an employer from its own domains (hub24management@myworkday.com, #2018).
    r'|myworkday\.com|workday\.com)$'
    r'|@(?:mail|e|eg|email|emails|e-mails|news|newsletter|comms|edm|specials|communication|survey|otp'
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
# Two, since a page is made from two sends (`worth_a_page`, #2057): a nameless
# address written to twice and never answering is held, not queued.
WRITE_ONLY_MIN = 2


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


def owner_tokens(addresses, name: str) -> set[str]:
    """Words of the owner's own: the local parts of addresses already theirs, and their name.

    Four letters or more, so "Xie" or "Wu" alone never makes a stranger the owner.
    """
    generic = {'account', 'owner', 'mail', 'gmail', 'outlook'}
    words = {part for address in addresses for part in re.split(r'[^a-z]+', address.split('@')[0].casefold())}
    words |= set(re.split(r'[^a-z]+', (name or '').casefold()))
    return {word for word in words if len(word) >= 4 and word not in generic}


def looks_own(group: list[dict], tokens: set[str]) -> list[dict]:
    """The rows of `group` worth asking "is this yours?" about (#2008).

    Only write-only rows, and none when any address of the group ever replied:
    a reply is someone else. When the map knows the owner (their addresses or
    name), the address or its display name must also carry one of their words.
    The owner's notebook offered seventeen, and fifteen were colleagues and
    friends who answer on other channels, whom one `--mine` would have made
    the owner. Knowing nothing of the owner, the
    map still asks about every write-only address, as before.
    """
    if any(row.get('received') for row in group):
        return []
    rows = [row for row in group if _write_only(row)]
    if not tokens:
        return rows
    return [row for row in rows if any(
        token in row['address'].split('@')[0].casefold() or token in str(row.get('name') or '').casefold()
        for token in tokens)]


def worth_a_page(sent: int, received: int) -> bool:
    """Someone the owner corresponds with: mail both ways, or the owner wrote to them twice.

    On the owner's 367 correspondents: 41 both ways, 31 written to twice or
    more; the other 295 were one cold mail, a newsletter, a booking (#2057).
    """
    return bool((sent and received) or sent >= 2)


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


CORPORATE = {'ltd', 'limited', 'inc', 'pty', 'llc', 'plc', 'corp', 'co', 'group', 'the'}


def _service(group: list[dict]) -> bool:
    """A sender named after its own domain whose mail mostly comes in: a service, not a person (#1987).

    "Airbnb" <discover@airbnb.com>, "Google Cloud" <googlecloud@google.com>,
    "X" <notify@x.com>: no address says no-reply, so 1.9.0a3 made each a people
    page. The display name's first word is the domain's own name. A person on a
    domain named after them writes from their name (aaron@aaron.dev), and a desk
    the owner answers as often as it writes stays a correspondent.
    """
    received = sum(row.get('received', 0) for row in group)
    sent = sum(row.get('sent', 0) for row in group)
    if not sent and all(_named_by_domain(row['address']) for row in group):
        return received >= 1
    for row in group:
        words = re.sub(r'[^a-z0-9 ]', ' ', str(row.get('name') or '').casefold()).split()
        domain = _domain(row['address'])
        local = row['address'].partition('@')[0].casefold()
        brand = organisation(domain).split('.')[0] if domain else ''
        # Or last: "Team Telnyx" <discover@telnyx.com> made a page on the 1.9.0a5
        # acceptance map (#2018). A person whose address carries one of their names
        # ("Mia Acme" <mia.tan@acme.com>) stays a person.
        own = {part for part in re.split(r'[^a-z0-9]+', local) if part}
        first = words and local != words[0] and brand == words[0]
        last = len(words) > 1 and brand == words[-1] and not own & set(words)
        # Or all of it: "Flagship Minerals" <ceo@flagshipminerals.com> sent the
        # owner an investor update and the 1.9.0a6 daily round spent 100,080
        # tokens investigating it as a person (#2031). A company writing as
        # itself spells its domain in words; a person on it writes their own name.
        whole = len(words) > 1 and ''.join(word for word in words if word not in CORPORATE) == brand \
            and not own & set(words)
        if not domain or not (first or last or whole):
            return False
    # Never written to, one mail is enough: "Apple" <appleid@id.apple.com> and
    # "Microsoft Clarity" <maccount@microsoft.com> each wrote once and stayed
    # people pages on the owner's notebook (#2008).
    return received >= (3 * sent if sent else 1)


def _named_by_domain(address: str) -> bool:
    """The local part carries the domain's own name, and is more than it: mylebara@lebara.com.au (#2018).

    A person writes from their own name; a service puts its brand on the
    mailbox. Only for an address the owner never wrote to (`_service`), and
    never the bare name (aaron@aaron.dev is a person on a domain named after them).
    """
    domain = _domain(address)
    brand = organisation(domain).split('.')[0] if domain else ''
    local = re.sub(r'[^a-z0-9]', '', address.partition('@')[0].casefold())
    return len(brand) >= 4 and brand in local and local != brand


# Addresses that are a system by their shape alone, whatever the mail's direction.
MACHINE = re.compile(r'no-?reply|do-?not-?reply|notification|newsletter|mailer|bounce|notify@|^unsub\+', re.I)


def service_page(title: str, emails: list[str], row: dict | None, automated: set) -> bool:
    """Is this people page a service or an automated sender, by today's rules (#1987, #2008)?

    The map keeps such senders off the people map from now on; this answers the
    same question for a page an older map already made. With the page's `row`
    from the last map, the map's own rule decides, on the direction of its mail.
    Without one, the page is judged on its address and title: listed by that map
    as a notice sender (`automated`), shaped like a system, or named after its
    own domain and only ever writing in.
    """
    addresses = [address.casefold() for address in emails]
    if not addresses:
        return False
    if row:
        group = [{'address': address, 'name': row.get('name') or title, 'sent': row.get('sent', 0),
                  'received': row.get('received', 0),
                  'one_way': row.get('one_way')}
                 for address in addresses]
        return all(_notice(one) for one in group) or _service(group)
    if all(address in automated or MACHINE.search(address) or RELAY.search(address) for address in addresses):
        return True
    return _service([{'address': address, 'name': title, 'sent': 0, 'received': 1} for address in addresses])


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


def _owner_name(clients: dict, given: str = '', sent_names=None) -> str:
    """What the owner is called: what they said, else what others call them, else their sent From name.

    A real account's configured name was "Aaron x", and Outlook stamps it on
    every mail sent, so the sent From name said "Aaron x" too; the people
    writing to him put "Aaron Xie" on his address (#2008). The name others use
    comes first (spellings that differ only in case are one name), then the
    sent From name, then a mailbox's configured name.
    """
    if given.strip():
        return given.strip()
    for key in ('addressed', 'sent'):
        groups = {}
        for name, count in ((sent_names or {}).get(key) or {}).items():
            groups.setdefault(name.strip().casefold(), collections.Counter())[name.strip()] += count
        if groups:
            return max(groups.values(), key=lambda group: sum(group.values())).most_common(1)[0][0]
    for client in clients.values():
        try:
            name = client.my_name() if hasattr(client, 'my_name') else ''
        except Exception:  # A name is a nicety; a failed lookup must not block the map.
            name = ''
        if name and name.strip():
            return name.strip()
    return 'Account owner'


UNFILLED = '- Unknown — not investigated yet'
POSSIBLY = "- Possibly also the owner's: "
# The History lines the map itself writes on the owner's page, by how they begin.
OWNER_HISTORY = ('- In the ', '- Most mail with: ', '- Coding sessions in the same window: ')
ENUMERATION = re.compile(r'^- \[(\d+)\] Enumeration metadata, observed [^ ]+', re.M)


def owner_possibly(page: str, lines: list[str]) -> str:
    """Every "Possibly also the owner's" line replaced by `lines`, at the top of Uncertainties (#2017).

    Each map used to add its list again when the counts had moved, and nothing
    took back an address confirmed since: the owner's page on the 1.9.0a5
    acceptance run carried nine such lines for three addresses, two of them
    already the owner's. Uncertainties left empty takes its placeholder back.
    """
    kept = [line for line in page.split('\n') if not line.startswith(POSSIBLY)]
    page = '\n'.join(kept)
    if '## Uncertainties\n' not in page:
        return page
    if lines:
        page = page.replace(f'## Uncertainties\n{UNFILLED}\n', '## Uncertainties\n', 1)
        return page.replace('## Uncertainties\n', '## Uncertainties\n' + '\n'.join(lines) + '\n', 1)
    if re.search(r'^## Uncertainties\n(?:\n|## |\Z)', page, re.M):
        empty = UNFILLED if _mapped_only(page) else '- Unknown'
        page = page.replace('## Uncertainties\n', f'## Uncertainties\n{empty}\n', 1)
    return page


def _refresh_owner_history(page: str, lines: list[str], started: str) -> str:
    """The map's own History lines, replaced with today's where an earlier map wrote them (#2017).

    After a re-map the owner's page still said "In the 90 days to 2026-09-25".
    Only lines the map writes, cited to its enumeration source, are touched;
    that source's observed time moves with them.
    """
    source = ENUMERATION.search(page)
    head, found, rest = page.partition('## History\n')
    if not source or not found:
        return page
    body, sep, tail = rest.partition('\n## ')
    old = body.split('\n')
    ours = [i for i, line in enumerate(old) if line.startswith(OWNER_HISTORY)]
    if not ours:
        return page
    new = [line.replace('[1]', f'[{source[1]}]') for line in lines]
    body = '\n'.join(old[:ours[0]] + new + [line for i, line in enumerate(old[ours[0]:], ours[0]) if i not in ours])
    page = head + found + body + sep + tail
    return ENUMERATION.sub(lambda match: f'- [{match[1]}] Enumeration metadata, observed {started}', page, count=1)


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
    # A 1.8 map wrote its confirm hint as `co wiki init --mine`; the command is co rem now (#1974).
    page = page.replace('co wiki init --mine', 'co rem init --mine')
    if mapped_only:
        page = re.sub(r'(## History\n)- Observed mail count:[^\n]*\[1\]\n', rf'\1{UNFILLED}\n', page, count=1)
        page = page.replace('- Correspondent classification unassessed; mapping does not establish a person '
                            'or employer.\n', '')
        addresses = ', '.join(owner['addresses'])
        for label in ('Email', 'Handles', 'Also known as'):
            page = re.sub(rf'^- {label}: .*$', f'- {label}: {addresses}', page, count=1, flags=re.M)
    if mapped_only:
        # Your own page has no "How the user writes to them" (#2008); a real one
        # said "Not applicable" under it.
        page = re.sub(r'^## How the user writes to them\n(?:- [^\n]*\n)*\n?', '', page, count=1, flags=re.M)
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
    page = _refresh_owner_history(page, [f'- {line}' for line in filled['History']], report['started'])
    # init asks about every write-only address; the page names only those that
    # carry the owner's own name. On the real map the write-only list also held
    # two colleagues who answer on other channels, and a page stating they were
    # "possibly the owner's" would mislead whoever reads it.
    tokens = owner_tokens(owner['addresses'], name)
    asked = [f"- Possibly also the owner's: {row['address']} ({row['sent']} sent, none received). "
             f"If it is yours: {row['confirm']}" for row in report['possible_own_addresses']
             if any(token in row['address'].split('@')[0].casefold() for token in tokens)][:5]
    page = owner_possibly(page, asked)
    if '[1]' in page and '\n## Sources\n- (none yet)' in page:
        page = page.replace('\n## Sources\n- (none yet)', '\n## Sources\n- [1] Enumeration metadata, observed '
                            + report['started'] + ' — .state/map.json; window-limited, not lifetime totals', 1)
    if page != original:
        notebook.write(record, page)


def owner_summary(notebook: Notebook, report: dict) -> dict | None:
    """What the owner's page says right now, for init to print (#1943).

    The one page with value straight after the map is the owner's -- mail
    volume, who they write to most, where they have been coding -- and a first
    run used to end on counts of empty pages without showing it. This reads the
    page itself, so the terminal says what the page says: its title and every
    stated line of Who they are and History, citations dropped, Unknowns left out.
    """
    record = (report.get('owner') or {}).get('record')
    if not record or not notebook.path(record).is_file():
        return None
    page = notebook.read(record)
    title = page.splitlines()[0][2:].strip() if page.startswith('# ') else record
    facts = []
    for section in ('Who they are', 'History'):
        body = re.search(rf'(?ms)^## {re.escape(section)}\n(.*?)(?=^## |\Z)', page)
        for line in (body.group(1).splitlines() if body else []):
            line = re.sub(r'(?:\s*\[\d+\])+\s*$', '', line.strip().removeprefix('- ').strip())
            if line and 'Unknown' not in line:
                facts.append(line)
    return {'record': record, 'path': str(notebook.path(record)), 'title': title, 'facts': facts}


SCRATCH = re.compile(r'/Documents/Codex/\d{4}-\d{2}-\d{2}/([^/]+?)(?:-\d+)?$')


def _scratch_identity(path: str) -> str:
    """Codex's dated scratch folders: one project, however many days it was opened.

    `Documents/Codex/2026-08-22/realtime-voice-chat`, `…/2026-08-26/…` and
    `…-2`, `…-3` were six project pages on a real notebook -- no repository to
    join them by, so each folder was its own project.
    """
    match = SCRATCH.search(path)
    return f"codex-scratch:{match.group(1)}" if match else ''


def _mapped_only(page: str) -> bool:
    return 'not investigated yet' in next(
        (line for line in page.splitlines() if line.startswith('Investigation:')), '')


def _held(group: list[dict], page: str) -> bool:
    """Titled by an address and the owner never wrote to it: kept, but not a person yet (#1844).

    After names were found for 176 pages, 43 of the owner's people pages were
    still titled by a bare address -- automated and one-way senders. Held
    pages are not queued for investigation or listed until a remap finds a
    name or a reply from the owner, or the owner investigates one. An address
    the owner has written to is a correspondent, the agent's own address
    included, so it is never held; an investigated page is someone's work.

    Except one the owner only ever writes to (`_write_only`), with no name:
    the shape of their own other mailbox, which 1.9.0a3 listed as a person
    (aaron@openonion.ai, 10 sent, none received). It is still asked about with
    `init --mine`, and held until that is answered or it replies (#1987).

    Since #2057 an address the owner never wrote to gets no page at all, so the
    write-only case is the one that still arrives here.
    """
    title = page.split('\n', 1)[0]
    return '@' in title and _mapped_only(page) and (
        not any(row.get('sent') for row in group) or all(_write_only(row) for row in group))


def needs_review(root: Path) -> set[str]:
    """Pages the last map held that are still only map output.

    Read from the pages as well as the map, so investigating one promotes it at once.
    """
    notebook = Notebook(root)
    held = {row['record'] for row in read_json(state_path(root, 'map.json'), {}).get('people', [])
            if row.get('needs_review')}
    return {record for record in held if notebook.path(record).is_file() and _mapped_only(notebook.read(record))}


def _archive_stale(notebook: Notebook, report: dict) -> list[str]:
    """Move pages an earlier map made, and nobody investigated, that this map would not make.

    Maps get better and their old output stays: a real notebook carried ten
    project pages for co rem's own task folders, six for one project's scratch
    folders, and two pages for Dora -- one titled by her address from an older
    map. Maintenance saw the duplicates, tried to merge them by deleting one, and
    was refused, batch after batch. Only a page that holds nothing but map output
    is moved, and it is moved, not deleted, to .state/archived/.
    """
    from .investigate import project_paths
    from .scan import project_exclusion
    moved = []
    used = {row.get('record') for row in report['people'] + report['projects'] + report['orgs'] if row.get('record')}
    used.add((report.get('owner') or {}).get('record'))
    covered = {path for row in report['projects'] for path in row.get('paths', [])}
    # A folder this map found is not a project (#1974): its mapped-only page goes too.
    dropped = {row['path'] for row in report.get('projects_dropped', [])}
    emails = {email.casefold() for person in notebook.people() if person['path'] in used for email in person['emails']}
    notices = {row['address'].casefold() for row in report.get('automated_correspondents', [])}
    for person in notebook.people():
        record = person['path']
        if record in used or not _mapped_only(notebook.read(record)):
            continue
        addresses = {email.casefold() for email in person['emails']}
        # Another page keeps this address, or every address is now a notice
        # sender (an older map made a "person" called Google).
        if addresses & emails or (addresses and addresses <= notices):
            moved.append(record)
    for record in notebook.list('projects'):
        page = notebook.read(record)
        if record in used or not _mapped_only(page):
            continue
        paths = project_paths(page)
        if paths and all(path in covered or path in dropped or project_exclusion(Path(path)) for path in paths):
            moved.append(record)
    # An organisation this map would not make: a subdomain now merged into its
    # company, or a domain only notice senders use.
    moved += [record for record in notebook.list('orgs')
              if record not in used and _mapped_only(notebook.read(record))]
    for record in moved:
        target = notebook.root / '.state' / 'archived' / record
        target.parent.mkdir(parents=True, exist_ok=True)
        notebook.path(record).replace(target)
    return sorted(moved)


def project_groups(rows: list[dict], dropped: list | None = None) -> dict:
    """Folders (rows shaped like `scan_projects`') grouped into projects: a worktree
    joins its repository by origin, Codex's dated scratch folders join by name.

    A worktree is listed as its main checkout, never as itself (#1955), and a
    group counts its worktrees instead (#1974). One that no longer exists has no
    origin to join by, so it joins whichever group its checkout is in; else its
    Sessions would overwrite the repository's. A folder that is not a project
    (`scan.not_a_project`) makes no group; it goes to `dropped` with the reason.
    """
    def identity(row):
        return canonical_origin(row['origin']) or row['repo']
    kept, short, out = [], {}, []
    for row in rows:
        why = not_a_project(row)
        # A lone short chat is judged with the rest of its project: one of six
        # dated scratch folders for one piece of work is not a one-off.
        if why == SHORT_SESSION:
            short[row['path']] = why
        elif why:
            out.append({'path': row['path'], 'sessions': row['sessions'], 'reason': why})
            continue
        kept.append(row)
    known = {main_checkout(row['path']) or row['path']: identity(row) for row in kept if identity(row)}
    groups = {}
    for row in kept:
        checkout = main_checkout(row['path'])
        path = checkout or row['path']
        key = identity(row) or known.get(path) or _scratch_identity(path) or path
        group = groups.setdefault(key, {'name': Path(row['repo'] or path).name, 'paths': [], 'worktrees': [],
                                       'members': [],
                                       'sessions': 0, 'first': row['first'], 'last': row['last']})
        group['members'].append(row['path'])
        if path not in group['paths']:
            group['paths'].append(path)
        if checkout and row['path'] not in group['worktrees']:
            group['worktrees'].append(row['path'])
        group['sessions'] += row['sessions']
        group['first'] = min(group['first'], row['first'])
        group['last'] = max(group['last'], row['last'])
    for key, group in list(groups.items()):
        members = [row for row in kept if row['path'] in group['members']]
        if group['sessions'] <= 1 and all(row['path'] in short for row in members):
            out += [{'path': row['path'], 'sessions': row['sessions'], 'reason': SHORT_SESSION} for row in members]
            del groups[key]
            continue
        group['worktrees'] = len(group['worktrees'])
        del group['members']
    if dropped is not None:
        dropped += out
    return groups


def _listed_paths(page: str) -> list[str]:
    """The folders a project page lists, worktrees as their main checkout. An
    investigated page may write one as prose -- "- `/path` — working directory
    recorded ..." -- and that page is still the folder's page."""
    from .investigate import collapse_worktree_paths, project_paths
    listed = project_paths(collapse_worktree_paths(page))
    section = page.partition('## Paths\n')[2].split('\n## ', 1)[0]
    listed += [main_checkout(path) or path for path in re.findall(r'^- `(/[^`]+)`', section, re.M)]
    return list(dict.fromkeys(listed))


def _project_pages(notebook: Notebook, paths: list[str], record: str) -> list[tuple[str, bool]]:
    """Every existing page for one project, with whether it may be merged away.

    A page belongs when the map's identity names it or it lists one of the
    project's folders, worktrees compared as their main checkout. It may be
    merged into another only if it lists no folder of a different project that
    still exists: an older page naming two repositories stays whole.
    """
    wanted = set(paths)
    found = {}
    for page in notebook.list('projects'):
        listed = _listed_paths(notebook.read(page))
        if page == record or wanted.intersection(listed):
            found[page] = not any(path not in wanted and Path(path).exists() for path in listed)
    return list(found.items())


def file_project(notebook: Notebook, identity: str, row: dict, *, refresh: bool = True) -> tuple[str, bool]:
    """The page for one project group: the page already listing one of its paths,
    else a new mapped stub. Returns (record, created).

    One definition of how a project page is made, for the map and for
    `project_material` (a folder with the user's messages and no page, #1943).
    `refresh=False` only adds missing paths: the caller saw part of the project,
    so its counts must not replace the map's.

    Several existing pages for one repository -- a page per worktree, from maps
    before #1955 and #1974 -- become one: the page with the most written content
    is kept and the others are merged into it (`merge.merge_into`), never deleted.
    """
    from .investigate import collapse_worktree_paths, project_paths
    from .merge import merge_into, resolve, weight
    record = resolve(notebook.root, _record('projects', row['name'], identity))
    pages = _project_pages(notebook, row['paths'], record)
    if pages:
        # Most written first; on a tie the page the map would name.
        pages.sort(key=lambda item: (weight(notebook.read(item[0])), item[0] == record), reverse=True)
        record = pages[0][0]
        for other, mergeable in pages[1:]:
            if mergeable:
                row.setdefault('merged', []).append(merge_into(notebook, record, other, 'same repository')['from'])
    worktrees = row.get('worktrees') or 0
    created = notebook.stub_project(record, row['name'], row['paths'], worktrees=worktrees,
                                    sessions=row['sessions'], first_seen=row['first'], last_seen=row['last'])
    # Refresh only deterministic numeric/date fields inside Paths; retain prose.
    original = notebook.read(record)
    page = collapse_worktree_paths(original)
    section = re.search(r'(?ms)^## Paths\n(.*?)(?=^## |\Z)', page)
    if section:
        body = section.group(1)
        refreshed = (('Sessions', row['sessions']), ('First seen', row['first']), ('Last seen', row['last']))
        for label, value in refreshed if refresh else ():
            body = re.sub(r'^- ' + label + r': (?:[0-9-]+)$', '- ' + label + ': ' + str(value), body, flags=re.M)
        if refresh and worktrees:
            if re.search(r'^- Worktrees: \d+$', body, re.M):
                body = re.sub(r'^- Worktrees: \d+$', f'- Worktrees: {worktrees}', body, flags=re.M)
            else:
                lines = body.splitlines(keepends=True)
                last = max((i for i, line in enumerate(lines) if line.startswith('- /')), default=-1)
                lines.insert(last + 1, f'- Worktrees: {worktrees}\n')
                body = ''.join(lines)
        recorded_paths = set(project_paths(page))
        for path in row['paths']:
            if path not in recorded_paths:
                body = '- ' + path + '\n' + body
        updated = page[:section.start(1)] + body + page[section.end(1):]
        if updated != original:
            notebook.write(record, updated)
    return record, created


def build_map(root: Path, subscriptions: dict, clients: dict, *args, **options) -> dict:
    """Map under the lock every other writer holds.

    The map moves pages now (stale ones go to .state/archived/). On a real
    notebook a scheduled maintenance batch started while init was running,
    chose a page as a lead, and failed when init archived it; and because pages
    had changed during the batch -- init's, not its own -- the batch was taken
    as written and its forty messages were skipped. One writer at a time: a
    tick during init finds co rem busy and retries five minutes later.
    """
    with maintenance_lock(root):
        return _build_map(root, subscriptions, clients, *args, **options)


def _build_map(root: Path, subscriptions: dict, clients: dict, *, days: int = 90,
               skill_directories=None, mine=(), source_errors=None, absent=None, name: str = '',
               progress=None, capture_sources: bool = False) -> dict:
    """Map observed identities; correspondent classification remains unassessed."""
    notebook = Notebook(root)
    report = {'phase': 'mapping', 'started': datetime.now(timezone.utc).isoformat(),
              'days': days, 'coverage': [], 'people': [], 'projects': [], 'orgs': [], 'created': [],
              'errors': list(source_errors or []), 'automated_correspondents': [], 'without_page': [],
              'possible_own_addresses': []}
    state = root / '.state' / 'map.json'
    from .source_inventory import SourceInventory
    inventory = SourceInventory(root, progress) if capture_sources else None
    if inventory:
        inventory.snapshot_report = report
        report['source_inventory'] = inventory.save(report)
    state.parent.mkdir(parents=True, exist_ok=True)
    # An upgraded notebook is tidied first, from the map before this one (#1999).
    from .tidy import tidy
    report['tidied'] = tidy(root, lock_held=True)
    # The owner's page from an earlier init, so a page made from --name alone
    # is the one a mailbox connected later fills, not a second owner.
    earlier = json.loads(state.read_text()).get('owner') if state.is_file() else None
    # An address confirmed once (--mine, or folded into the owner's page by
    # tidy) stays the owner's: without this the next map, run without --mine,
    # made it a correspondent page again (#2008).
    mine = sorted({*mine, *((earlier or {}).get('addresses') or [])})
    earlier = earlier['record'] if earlier and notebook.path(earlier['record']).is_file() else None
    def save():
        atomic_write(state, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    save()
    if progress:
        progress("mapping installed skills")
    report['skills'] = map_skills(notebook, skill_directories, lock_held=True, subscriptions=subscriptions,
                                  **({'progress': progress} if progress else {}))
    if progress:
        progress("mapped installed skills", len(report['skills']['created']) + len(report['skills']['preserved']))
    if inventory:
        for skill in report['skills']['skills']:
            inventory.skill(skill)
        inventory.save(report)
    save()
    sent_names = {"addressed": collections.Counter(), "sent": collections.Counter()}
    if inventory:
        people, own = _mail_rows(clients, days, mine, report['coverage'], report['errors'], progress,
                                 inventory=inventory, own_names=sent_names)
    else:
        people, own = _mail_rows(clients, days, mine, report['coverage'], report['errors'], progress,
                                 own_names=sent_names)
    roster = notebook.people()
    if own:
        aliases = sorted({address.casefold() for address in own})
        existing = next((p['path'] for p in roster if set(aliases).intersection(p['emails'])), None)
        owner_name = _owner_name(clients, name, sent_names)
        # A new notebook's file is named after the owner, not "account-owner-…";
        # an existing page keeps its path (links and runs point at it).
        owner_record = existing or earlier or _record('people', owner_name, aliases[0])
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
    owner = report.get('owner') or {}
    tokens = owner_tokens(owner.get('addresses') or [], owner_name if owner else '')
    org_rows = []
    for group in _people_groups(people):
        addresses = [row['address'] for row in group]
        first = group[0]
        automated = all(AUTOMATED_HINT.search(row['address']) for row in group)
        # A notice sender that never hears back, or someone reachable only through
        # an event platform's relay, is not a person the user deals with. On one
        # real mailbox this was 165 of 565 people pages (Neon Changelog, Airwallex,
        # event platforms). They stay in the map report; they get no page.
        if all(_notice(row) for row in group) or _service(group):
            report['automated_correspondents'].extend(group)
            org_rows += [{'address': a, 'record': None} for a in addresses]
            continue
        existing = next((p['path'] for p in roster if {a.casefold() for a in addresses} & set(p['emails'])), None)
        sent, received = sum(row.get('sent', 0) for row in group), sum(row.get('received', 0) for row in group)
        kept = existing and not _mapped_only(notebook.read(existing))
        if not kept and (automated or not worth_a_page(sent, received)):
            # 374 of the owner's 381 people pages were empty templates, most
            # for one mail either way: Apple, a newsletter, one cold outreach
            # (#2057). They stay in the map, and get a page once they write back.
            report['automated_correspondents' if automated else 'without_page'].append(
                {**first, 'addresses': addresses, 'sent': sent, 'received': received,
                 **({'record': existing} if existing else {})})
            org_rows += [{'address': a, 'record': None} for a in addresses]
            continue
        if automated:
            report['automated_correspondents'].extend(group)
        name = next((row['name'] for row in group if row.get('name')), '') or first['address']
        record = existing or _record('people', name, first['address'])
        made = notebook.stub_person(record, name, addresses, email=', '.join(addresses))
        if not made and '@' not in name:
            # A page an older map titled with an address, now that a name is
            # known. Only map output is retitled; an investigated page keeps its title.
            page = notebook.read(record)
            title = page.split('\n', 1)[0]
            if title.startswith('# ') and '@' in title and _mapped_only(page):
                notebook.write(record, f'# {name}\n' + page.split('\n', 1)[1])
        mails = sum(row.get('mails', 0) for row in group)
        report['people'].append({**first, 'mails': mails, 'addresses': addresses, 'record': record,
                                 'sent': sum(row.get('sent', 0) for row in group),
                                 'received': sum(row.get('received', 0) for row in group),
                                 'boxes': sorted({box for row in group for box in row.get('boxes', [])}),
                                 'classification': 'automated candidate' if automated else 'unassessed',
                                 'needs_review': _held(group, notebook.read(record))})
        # A relay address is the platform's, not the person's employer: luma-mail.com
        # became an organisation through one person's 253 event mails (#2018).
        org_rows += [{'address': a, 'record': None if RELAY.search(a) else record} for a in addresses]
        # Asked about, not acted on: the page stays exactly as it is until the
        # owner answers with --mine, because only they can tell their own
        # mailbox from someone who never writes back.
        report['possible_own_addresses'] += [
            {'address': row['address'], 'sent': row.get('sent', 0), 'record': record,
             'confirm': 'co rem init --mine ' + row['address']}
            for row in looks_own(group, tokens)]
        if automated:
            page = notebook.read(record)
            marker = '- Correspondent classification: automated candidate; not verified as a person.'
            if marker not in page:
                notebook.write(record, page.replace('## Uncertainties\n', '## Uncertainties\n' + marker + '\n'))
        if made:
            notes = ''
            if len(addresses) > 1:
                # One person, several addresses: the same display name on a work and a
                # personal address split one relationship across pages that each knew half.
                notes += (f"- Addresses grouped by the display name “{name}”: {', '.join(addresses)}. "
                          "Confirm they are one person before relying on it.\n")
            notebook.write(record, notebook.read(record).replace('## Uncertainties\n', '## Uncertainties\n' + notes))
            page = notebook.read(record)
            dates = [row.get('first') for row in group if row.get('first')], [row.get('last') for row in group if row.get('last')]
            boxes = sorted({box for row in group for box in row.get('boxes', [])})
            # The count is the map's, not the person's history: 379 of 424 History
            # bullets on the owner's people pages were this line (#2059). It goes in
            # the lead, where the reader shows it and the census dates the page.
            last = max(dates[1]) if dates[1] else 'Unknown'
            plural = '' if mails == 1 else 's'
            page = page.replace(Notebook.PERSON_LEAD, f"Unknown — not investigated yet. Last contact: {last}; "
                                f"{mails} mail{plural} ({', '.join(boxes) or 'mail'}).", 1)
            notebook.write(record, page)
            report['created'].append(record)
    report['possible_own_addresses'].sort(key=lambda row: (-row['sent'], row['address']))
    report['needs_review'] = [row['record'] for row in report['people'] if row.get('needs_review')]
    if report['possible_own_addresses']:
        count = len(report['possible_own_addresses'])
        report['coverage'].append(
            f"{count} address{'es' if count > 1 else ''} received mail from the owner and never replied; "
            f"{'they may be' if count > 1 else 'it may be'} the owner's own. Pages are kept as they are "
            "until confirmed with co rem init --mine")
    if report['automated_correspondents']:
        report['coverage'].append(f"{len(report['automated_correspondents'])} notice or relay senders listed in "
                                  ".state/map.json without people pages")
    if report['without_page']:
        report['coverage'].append(f"{len(report['without_page'])} correspondents with mail one way only, and at "
                                  "most one from the owner, listed in .state/map.json without people pages; a page "
                                  "comes when mail goes both ways or the owner writes twice")
    # Why a mailbox is not here is the command layer's knowledge, not the map's:
    # from inside, a mailbox nobody connected, one the user unsubscribed, and one
    # that failed to open are all equally absent. It says what it was told, and
    # falls back to the honest vagueness when it was told nothing.
    absent = dict(absent or {})
    report['coverage'] += [f'{kind}: ' + (absent.get(kind) or 'not configured or disabled; not searched')
                           for kind in ('gmail', 'outlook') if kind not in clients]
    report['orgs'], created_orgs = map_orgs(notebook, org_rows, report['started'], days, _record)
    if progress:
        progress("mapped people and organizations", len(report['people']) + len(report['orgs']))
    report['created'] += created_orgs
    report['coverage'].append('Organizations: exact observed mail domains, including single contacts and notices; '
                              'known public mailbox domains excluded; mailbox-provider list is not exhaustive; '
                              'organization identity unverified; existing organization pages preserved')
    save()
    if progress:
        progress("scanning local projects")
    # Only what is given is passed: a progress-less caller keeps the call it always made.
    project_rows = scan_projects(subscriptions, days, root, **({'on_session': inventory.session} if inventory else {}),
                                 **({'progress': progress} if progress else {}))
    dropped = []
    for identity, row in project_groups(project_rows, dropped).items():
        record, created = file_project(notebook, identity, row)
        if created:
            report['created'].append(record)
        report['projects'].append({**row, 'record': record})
    report['projects_dropped'] = dropped
    if dropped:
        report['coverage'].append(f"{len(dropped)} folder{'s' if len(dropped) > 1 else ''} with sessions not made "
                                  "projects (home, caches, one-off chats; reasons in .state/map.json)")
    merged = [name for row in report['projects'] for name in row.get('merged', [])]
    if merged:
        report['coverage'].append(f"{len(merged)} project page{'s' if len(merged) > 1 else ''} for the same "
                                  "repository merged into one; the old names are aliases in .state/aliases.json")
    report['coverage'] += [f'{name}: {sub.get("root", "")} — ' + _session_state(sub, report['projects'])
                           for name, sub in subscriptions.items() if sub.get('kind') in ('codex', 'claude-code')]
    if report.get('owner'):
        _fill_owner(notebook, report, owner_name)
    # And tidied again after (#2018): the acceptance run's map made pages that
    # tidy, run only before it, never saw. Tidy reads this map's rows. The
    # owner's own addresses wait for the next run: this map has just asked
    # about them, and init shows the question.
    save()
    for action, pages in tidy(root, lock_held=True, own_addresses=False).items():
        report['tidied'][action] = sorted({*report['tidied'].get(action, []), *pages})
    report['people'] = [row for row in report['people'] if notebook.path(row['record']).is_file()]
    report['archived'] = report['tidied'].get('archived service', []) + _archive_stale(notebook, report)
    if report['archived']:
        report['coverage'].append(f"{len(report['archived'])} pages an earlier map made and nobody investigated were "
                                  "duplicates or sandboxes; moved to .state/archived/")
    report.update(phase='partial' if report['errors'] else 'mapped', finished=datetime.now(timezone.utc).isoformat(),
                  investigation='not started', classification='unassessed; no correspondents filtered')
    if inventory:
        report['source_inventory'] = inventory.save(report)
    if progress:
        progress("mapped projects", len(report['projects']))
    save()
    for category in ('people', 'projects', 'orgs'):
        lines = [f'# {category.capitalize()} map', '', 'Generated enumeration; not an investigation or importance ranking.', '']
        lines += [f'- [{Path(row["record"]).stem}](../{row["record"]})' for row in report[category]]
        notebook.write(f'notes/{category}-map.md', '\n'.join(lines) + '\n')
    # The index the table and thread views read, from what this map just wrote (#2067).
    # Derived and rebuilt next time, so a failure is reported, never the map's.
    from .store import refresh_safely
    report['store'] = refresh_safely(root)
    save()
    return report
