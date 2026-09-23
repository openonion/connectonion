from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook
from connectonion.wiki.map import build_map


def test_map_groups_project_worktrees_preserves_pages_and_keeps_noise(tmp_path, monkeypatch):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    (skills / 'demo').mkdir(parents=True)
    source = skills / 'demo/SKILL.md'
    source.write_text('---\nname: demo\ndescription: Synthetic demo\n---\nDo something.')
    original = source.read_bytes()
    people = [{'name': 'Notices', 'address': 'noreply@example.org', 'mails': 2}]
    monkeypatch.setattr('connectonion.wiki.map._mail_rows', lambda *a: (people, set()))
    monkeypatch.setattr('connectonion.wiki.map.scan_projects', lambda *a: [
        {'name': 'Atlas', 'repo': '/repo/atlas', 'origin': 'https://example.org/atlas',
         'path': path, 'sessions': 2, 'first': '2026-09-18', 'last': '2026-09-19'}
        for path in ('/repo/atlas', '/worktree/atlas')])
    first = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert len(first['people']) == len(first['projects']) == 1
    record = first['projects'][0]['record']
    nb = Notebook(tmp_path)
    assert first['projects'][0]['sessions'] == 4
    assert '/worktree/atlas' in nb.read(record)
    assert first['people'][0]['classification'] == 'automated candidate'
    nb.write(record, nb.read(record).replace('## What it is\n', '## What it is\nCurated purpose.\n'))
    second = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert not second['created']
    assert 'Curated purpose.' in nb.read(record)
    assert source.read_bytes() == original
    assert second['investigation'] == 'not started'


def test_project_scan_honors_disabled_and_project_scopes(tmp_path):
    import json
    from connectonion.wiki.scan import scan_projects
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    for i, cwd in enumerate(('/allowed', '/outside')):
        (sessions / f'rollout-{i}.jsonl').write_text(json.dumps({'type': 'session_meta', 'payload': {
            'id': str(i), 'cwd': cwd, 'originator': 'codex_cli_rs'}}) + '\n')
    sub = {'kind': 'codex', 'root': str(sessions), 'enabled': True, 'project': '/allowed'}
    assert [r['path'] for r in scan_projects({'local': sub}, 1)] == ['/allowed']
    assert scan_projects({'local': {**sub, 'enabled': False}}, 1) == []


def test_unavailable_mail_does_not_stop_other_maps(tmp_path):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    class Unavailable:
        def my_addresses(self):
            raise RuntimeError('private provider detail')
    result = build_map(tmp_path, {}, {'gmail': Unavailable()}, skill_directories=[skills])
    assert result['phase'] == 'partial'
    assert 'gmail: unavailable (RuntimeError); not searched' in result['coverage']
    assert 'private provider detail' not in str(result)


def test_map_creates_owner_from_verified_account_aliases(tmp_path):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    class Mail:
        def my_addresses(self):
            return {'owner@example.org'}
        def list_between(self, start, end, limit):
            return []
    result = build_map(tmp_path, {}, {'gmail': Mail()}, skill_directories=[skills])
    owner = result['owner']['record']
    assert 'owner@example.org' in Notebook(tmp_path).read(owner)
    assert 'not investigated yet' in Notebook(tmp_path).read(owner)
    assert build_map(tmp_path, {}, {'gmail': Mail()}, skill_directories=[skills])['owner']['record'] == owner


def test_init_maps_domain_candidates_without_claiming_employment(tmp_path, monkeypatch):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    people = [{'name': address, 'address': address, 'mails': 1} for address in (
        'a@EXAMPLE.org', 'b@example.org', 'solo@school.edu.au',
        'noreply@notices.example.org', 'personal@gmail.com', 'invalid-address')]
    monkeypatch.setattr('connectonion.wiki.map._mail_rows', lambda *a: (people, set()))
    monkeypatch.setattr('connectonion.wiki.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    orgs = {row['domain']: row for row in result['orgs']}
    assert set(orgs) == {'example.org', 'school.edu.au', 'notices.example.org'}
    assert len(orgs['example.org']['people']) == 2
    nb = Notebook(tmp_path)
    for row in orgs.values():
        page = nb.read(row['record'])
        assert 'Domain candidate; organization identity unverified' in page
        assert 'not evidence of employment' in page
        assert 'not investigated yet' in page and '.state/map.json' in page
        for person in row['people']:
            assert f'../{person}' in page
            assert nb.path(person).is_file()
        assert row['record'] in result['created']
    assert 'mailbox-provider list is not exhaustive' in ' '.join(result['coverage'])
    assert nb.path('notes/orgs-map.md').is_file()
    record = orgs['example.org']['record']
    curated = nb.read(record).replace('not investigated yet', 'reviewed by user') + '\nUser correction.\n'
    nb.write(record, curated)
    repeated = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert nb.read(record) == curated
    assert not repeated['created']


def test_init_reuses_existing_org_with_matching_domain(tmp_path, monkeypatch):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    nb = Notebook(tmp_path)
    nb.stub_org('orgs/existing.md', 'Known organization', ['EXAMPLE.ORG'])
    old = nb.read('orgs/existing.md')
    monkeypatch.setattr('connectonion.wiki.map._mail_rows', lambda *a: (
        [{'name': 'Person', 'address': 'person@example.org', 'mails': 1}], set()))
    monkeypatch.setattr('connectonion.wiki.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert result['orgs'][0]['record'] == 'orgs/existing.md'
    assert nb.list('orgs') == ['orgs/existing.md']
    assert nb.read('orgs/existing.md') == old


def test_project_scan_excludes_sandboxes_and_removed_worktrees(tmp_path):
    import json
    from connectonion.wiki.scan import scan_projects
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    paths = ['/private/tmp/wiki187/notebook', '/tmp/co-wiki-extract-demo',
             '/private/var/folders/xx/session/T/pytest-123/wiki',
             '/Users/fictional/.codex/worktrees/1234/browser',
             '/projects/team-a/browser', '/projects/team-b/browser']
    for i, cwd in enumerate(paths):
        (sessions / f'rollout-{i}.jsonl').write_text(json.dumps({
            'type': 'session_meta', 'payload': {'id': str(i), 'cwd': cwd}}) + '\n')
    rows = scan_projects({'local': {'kind': 'codex', 'root': str(sessions)}}, 1)
    assert {r['path'] for r in rows} == set(paths[-2:])


def test_one_person_on_several_addresses_is_one_page_and_notices_get_none(tmp_path, monkeypatch):
    """On a real mailbox Ody Zhou was four pages -- two Gmail addresses, an event
    platform's relay, and a Drive share notice -- and notice senders were 165 of
    565 people pages. A full display name joins addresses; a sender that only ever
    sends and looks like a system, or writes through a relay, is listed, not paged."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    people = [
        {'name': 'Ody Zhou', 'address': 'zhouodywork@gmail.com', 'mails': 30, 'one_way': False,
         'first': '2026-07-17', 'last': '2026-09-14', 'boxes': ['gmail']},
        {'name': 'Ody Zhou', 'address': 'zhouody@gmail.com', 'mails': 3, 'one_way': False,
         'first': '2026-08-01', 'last': '2026-08-02', 'boxes': ['gmail']},
        {'name': 'Ody Zhou', 'address': 'usr-abc@user.luma-mail.com', 'mails': 1, 'one_way': True},
        {'name': 'Ody Zhou (via Google Drive)', 'address': 'drive-shares-dm-noreply@google.com', 'mails': 2,
         'one_way': True},
        {'name': 'Neon Changelog', 'address': 'changelog@neon.tech', 'mails': 4, 'one_way': True},
        {'name': 'Andrew Suryanto', 'address': 'usr-xyz@user.luma-mail.com', 'mails': 1, 'one_way': True},
        {'name': 'John', 'address': 'john@a.com', 'mails': 2, 'one_way': False},
        {'name': 'John', 'address': 'john@b.com', 'mails': 2, 'one_way': False},
        {'name': 'a16z speedrun', 'address': 'speedrun@substack.com', 'mails': 10, 'one_way': True},
        {'name': 'AI Tinkerers', 'address': 'post-training@mail.aitinkerers.org', 'mails': 13, 'one_way': True},
        {'name': '', 'address': '0xa633fd2e63@mail.openonion.ai', 'mails': 3, 'one_way': True},
        {'name': 'Zhang, Misa', 'address': 'misa.zhang@fisglobal.com', 'mails': 3, 'one_way': True},
    ]
    monkeypatch.setattr('connectonion.wiki.map._mail_rows', lambda *a: (people, set()))
    monkeypatch.setattr('connectonion.wiki.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    pages = {row['record']: row for row in result['people']}
    ody = next(row for row in result['people'] if row['name'] == 'Ody Zhou')
    assert ody['addresses'] == ['zhouodywork@gmail.com', 'zhouody@gmail.com', 'usr-abc@user.luma-mail.com']
    assert ody['mails'] == 34
    page = Notebook(tmp_path).read(ody['record'])
    assert 'zhouody@gmail.com' in page and 'Confirm they are one person' in page
    assert len(pages) == 4               # Ody, the two Johns kept apart, and Misa, who wrote first
    listed = {row['address'] for row in result['automated_correspondents']}
    assert {'changelog@neon.tech', 'drive-shares-dm-noreply@google.com', 'usr-xyz@user.luma-mail.com',
            'speedrun@substack.com', 'post-training@mail.aitinkerers.org',
            '0xa633fd2e63@mail.openonion.ai'} <= listed
    assert 'neon.tech' in {row['domain'] for row in result['orgs']}   # the domain is still mapped


def test_addresses_the_owner_writes_to_and_never_hears_from_are_asked_about_not_merged(tmp_path, monkeypatch):
    """On the real 90-day map of 2026-09-23 the second-largest people page was the
    owner's own Gmail: 106 sent, 0 received. Investigating it would have pulled the
    owner's mail into a page about a nobody. The map asks instead of deciding --
    an assistant and a relative look exactly the same from the headers (#1635)."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    people = [
        {'name': 'openonion ai', 'address': 'aaronplus1996@gmail.com', 'mails': 106, 'sent': 106,
         'received': 0, 'one_way': True, 'first': '2026-06-25', 'last': '2026-09-23', 'boxes': ['gmail']},
        {'name': 'Support', 'address': 'support@vendor.example', 'mails': 4, 'sent': 4, 'received': 0,
         'one_way': True},
        {'name': 'Dana Reyes', 'address': 'dana@client.example', 'mails': 1, 'sent': 1, 'received': 0,
         'one_way': True},
        {'name': 'Misa Zhang', 'address': 'misa@fisglobal.example', 'mails': 9, 'sent': 4, 'received': 5,
         'one_way': False},
    ]
    monkeypatch.setattr('connectonion.wiki.map._mail_rows', lambda *a: (people, set()))
    monkeypatch.setattr('connectonion.wiki.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])

    asked = {row['address']: row for row in result['possible_own_addresses']}
    assert list(asked) == ['aaronplus1996@gmail.com']    # one reply, or one letter, and it is a person
    assert asked['aaronplus1996@gmail.com']['sent'] == 106
    assert asked['aaronplus1996@gmail.com']['confirm'] == 'co wiki init --mine aaronplus1996@gmail.com'
    assert any('1 address received mail from the owner and never replied' in line for line in result['coverage'])

    # Nothing is merged on a guess: the page is still there, still a person page.
    page = asked['aaronplus1996@gmail.com']['record']
    assert page in {row['record'] for row in result['people']}
    assert 'aaronplus1996@gmail.com' in Notebook(tmp_path).read(page)
    assert result.get('owner') is None


def test_confirming_an_own_address_stops_the_question_and_keeps_the_page_as_the_owner(tmp_path, monkeypatch):
    """--mine is the answer to the question init asked, so the second run must not
    ask it again, and must reuse the page rather than leave a stranger's page and
    an owner page both holding the same address."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    rows = [{'name': 'openonion ai', 'address': 'aaronplus1996@gmail.com', 'mails': 106, 'sent': 106,
             'received': 0, 'one_way': True, 'first': '2026-06-25', 'last': '2026-09-23', 'boxes': ['gmail']}]

    def mail_rows(clients, days, mine, coverage, errors=None):
        own = {a.lower() for a in mine}
        return [row for row in rows if row['address'] not in own], own

    monkeypatch.setattr('connectonion.wiki.map._mail_rows', mail_rows)
    monkeypatch.setattr('connectonion.wiki.map.scan_projects', lambda *a: [])
    first = build_map(tmp_path, {}, {}, skill_directories=[skills])
    page = first['possible_own_addresses'][0]['record']

    second = build_map(tmp_path, {}, {}, skill_directories=[skills], mine=['aaronplus1996@gmail.com'])
    assert second['possible_own_addresses'] == []
    assert second['owner']['record'] == page
    assert Notebook(tmp_path).list('people') == [page]


def test_coverage_separates_scanned_empty_from_never_scanned(tmp_path):
    """The init contract asks for four source states to stay apart. Two of them are
    the map's own to tell: a mailbox it read and found nobody in, and a session
    directory that is not there. "unavailable or disabled" sent the user to check
    the wrong thing half the time (#1616)."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    missing = tmp_path / 'no-sessions'
    off = tmp_path / 'off'
    off.mkdir()

    class Empty:
        def my_addresses(self):
            return {'owner@example.org'}
        def list_between(self, start, end, limit):
            return []

    subscriptions = {'codex': {'kind': 'codex', 'root': str(missing), 'enabled': True},
                     'claude-code': {'kind': 'claude-code', 'root': str(off), 'enabled': False}}
    result = build_map(tmp_path, subscriptions, {'gmail': Empty()}, skill_directories=[skills])
    coverage = '\n'.join(result['coverage'])
    assert 'gmail: metadata only, 150 days, at most 200 messages per seven-day window; no correspondents in this window' in coverage
    assert f'codex: {missing} — no session directory at this path; nothing to scan' in coverage
    assert f'claude-code: {off} — disabled; not scanned' in coverage


def test_the_map_reports_the_absence_reason_it_was_given(tmp_path):
    """Why a mailbox is missing is the command layer's knowledge; the map states it
    rather than guessing, and still says something true when told nothing."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    told = build_map(tmp_path, {}, {}, skill_directories=[skills],
                     absent={'gmail': 'authorized but could not be opened (TimeoutError); not searched'})
    assert 'gmail: authorized but could not be opened (TimeoutError); not searched' in told['coverage']
    assert 'outlook: not configured or disabled; not searched' in told['coverage']
