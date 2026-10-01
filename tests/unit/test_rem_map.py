from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.map import build_map


def test_map_groups_project_worktrees_preserves_pages_and_keeps_noise(tmp_path, monkeypatch):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    (skills / 'demo').mkdir(parents=True)
    source = skills / 'demo/SKILL.md'
    source.write_text('---\nname: demo\ndescription: Synthetic demo\n---\nDo something.')
    original = source.read_bytes()
    people = [{'name': 'Notices', 'address': 'noreply@example.org', 'mails': 2}]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [
        {'name': 'Atlas', 'repo': '/repo/atlas', 'origin': 'https://example.org/atlas',
         'path': path, 'sessions': 2, 'first': '2026-09-18', 'last': '2026-09-19'}
        for path in ('/repo/atlas', '/worktree/atlas')])
    first = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert len(first['projects']) == 1
    record = first['projects'][0]['record']
    nb = Notebook(tmp_path)
    assert first['projects'][0]['sessions'] == 4
    assert '/worktree/atlas' in nb.read(record)
    # The noise is kept in the map, not as a page: an automated sender gets none (#2057).
    assert first['people'] == [] and nb.people() == []
    assert [row['address'] for row in first['automated_correspondents']] == ['noreply@example.org']
    curated = nb.read(record).replace('## What it is\n', '## What it is\nCurated purpose.\n')
    curated = curated.replace('- /repo/atlas\n', '- /repo/atlas [1]\n')
    nb.write(record, curated)
    second = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert not second['created']
    assert nb.read(record) == curated
    assert nb.read(record).count('/repo/atlas') == 1
    assert source.read_bytes() == original
    assert second['investigation'] == 'not started'


def test_project_scan_honors_disabled_and_project_scopes(tmp_path):
    import json
    from connectonion.rem.scan import scan_projects
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
    people = [{'name': address, 'address': address, 'mails': 2, 'sent': 1, 'received': 1} for address in (
        'a@EXAMPLE.org', 'b@example.org', 'solo@school.edu.au',
        'noreply@notices.example.org', 'personal@gmail.com', 'invalid-address')]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    orgs = {row['domain']: row for row in result['orgs']}
    # notices.example.org is example.org's sending subdomain, not a second organisation (#1844)
    assert set(orgs) == {'example.org', 'school.edu.au'}
    assert orgs['example.org']['domains'] == ['example.org', 'notices.example.org']
    # The notice sender lends example.org its subdomain but gets no page of its own (#2057).
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
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (
        [{'name': 'Person', 'address': 'person@example.org', 'mails': 2, 'sent': 1, 'received': 1}], set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert result['orgs'][0]['record'] == 'orgs/existing.md'
    assert nb.list('orgs') == ['orgs/existing.md']
    assert nb.read('orgs/existing.md') == old


def test_project_scan_excludes_sandboxes_and_removed_worktrees(tmp_path):
    import json
    from connectonion.rem.scan import scan_projects
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    paths = ['/private/tmp/wiki187/notebook', '/tmp/co-rem-extract-demo',
             '/private/var/folders/xx/session/T/pytest-123/rem',
             '/Users/fictional/.codex/worktrees/1234/browser',
             '/projects/team-a/browser', '/projects/team-b/browser']
    for i, cwd in enumerate(paths):
        (sessions / f'rollout-{i}.jsonl').write_text(json.dumps({
            'type': 'session_meta', 'payload': {'id': str(i), 'cwd': cwd}}) + '\n')
    rows = scan_projects({'local': {'kind': 'codex', 'root': str(sessions)}}, 1)
    assert {r['path'] for r in rows} == set(paths[-2:])


def test_project_scan_does_not_turn_rem_runs_into_a_project(tmp_path, monkeypatch):
    import json
    from connectonion.rem.scan import scan_projects

    root = tmp_path / 'rem'
    nested = root / '.state/tasks/investigate-1/notebook'
    nested.mkdir(parents=True)
    project = tmp_path / 'real-project'
    project.mkdir()
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    for i, cwd in enumerate((root, nested, project)):
        (sessions / f'rollout-{i}.jsonl').write_text(json.dumps({
            'type': 'session_meta', 'payload': {'id': str(i), 'cwd': str(cwd)}}) + '\n')
    monkeypatch.setattr('connectonion.rem.scan.project_exclusion', lambda path: '')

    rows = scan_projects({'local': {'kind': 'codex', 'root': str(sessions)}}, 1, rem_root=root)
    assert [row['path'] for row in rows] == [str(project)]


def test_project_scan_excludes_other_notebooks_task_copies_and_fixtures(tmp_path):
    from pathlib import Path
    from connectonion.rem.scan import project_exclusion

    task_copy = tmp_path / 'another-rem/.state/tasks/investigate-1/notebook'
    fixture = tmp_path / '.worktree/rem-improve-fixture/notebook'
    real = Path('/Users/fictional/company/notebook')
    for path in (task_copy, fixture):
        path.mkdir(parents=True)
    assert project_exclusion(task_copy) == 'co rem task workspace copy'
    assert project_exclusion(fixture) == 'test fixture notebook'
    assert project_exclusion(real) == ''


def test_project_scan_excludes_a_multi_repository_workspace_root(tmp_path):
    from connectonion.rem.scan import project_exclusion

    root = tmp_path / 'projects'
    root.mkdir()
    (root / 'AGENTS.md').write_text('This directory is a workspace, not a repository.\n')
    for name in ('first', 'second'):
        (root / name / '.git').mkdir(parents=True)
    assert project_exclusion(root) == 'multi-repository workspace container'
    (root / 'AGENTS.md').unlink()
    (root / 'CLAUDE.md').write_text('A workspace of six repositories.\n')   # Claude Code's instructions file
    assert project_exclusion(root) == 'multi-repository workspace container'


def test_one_person_on_several_addresses_is_one_page_and_notices_get_none(tmp_path, monkeypatch):
    """On a real mailbox Ody Zhou was four pages -- two Gmail addresses, an event
    platform's relay, and a Drive share notice -- and notice senders were 165 of
    565 people pages. A full display name joins addresses; a sender that only ever
    sends and looks like a system, or writes through a relay, is listed, not paged."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    people = [
        {'name': 'Ody Zhou', 'address': 'zhouodywork@gmail.com', 'mails': 30, 'sent': 12, 'received': 18,
         'one_way': False, 'first': '2026-07-17', 'last': '2026-09-14', 'boxes': ['gmail']},
        {'name': 'Ody Zhou', 'address': 'zhouody@gmail.com', 'mails': 3, 'sent': 1, 'received': 2,
         'one_way': False, 'first': '2026-08-01', 'last': '2026-08-02', 'boxes': ['gmail']},
        {'name': 'Ody Zhou', 'address': 'usr-abc@user.luma-mail.com', 'mails': 1, 'one_way': True},
        {'name': 'Ody Zhou (via Google Drive)', 'address': 'drive-shares-dm-noreply@google.com', 'mails': 2,
         'one_way': True},
        {'name': 'Neon Changelog', 'address': 'changelog@neon.tech', 'mails': 4, 'one_way': True},
        {'name': 'Andrew Suryanto', 'address': 'usr-xyz@user.luma-mail.com', 'mails': 1, 'one_way': True},
        {'name': 'John', 'address': 'john@a.com', 'mails': 2, 'sent': 1, 'received': 1, 'one_way': False},
        {'name': 'John', 'address': 'john@b.com', 'mails': 2, 'sent': 1, 'received': 1, 'one_way': False},
        {'name': 'a16z speedrun', 'address': 'speedrun@substack.com', 'mails': 10, 'one_way': True},
        {'name': 'AI Tinkerers', 'address': 'post-training@mail.aitinkerers.org', 'mails': 13, 'one_way': True},
        {'name': '', 'address': '0xa633fd2e63@mail.openonion.ai', 'mails': 3, 'one_way': True},
        # Each answered at least once: a one-way correspondent gets no page at all (#2057).
        {'name': 'Zhang, Misa', 'address': 'misa.zhang@fisglobal.com', 'mails': 3, 'sent': 1, 'received': 2,
         'one_way': False},
        {'name': 'Lee Chen', 'address': 'lee.chen@mail.com', 'mails': 2, 'sent': 1, 'received': 1,
         'one_way': False},
    ]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    pages = {row['record']: row for row in result['people']}
    ody = next(row for row in result['people'] if row['name'] == 'Ody Zhou')
    assert ody['addresses'] == ['zhouodywork@gmail.com', 'zhouody@gmail.com', 'usr-abc@user.luma-mail.com']
    assert ody['mails'] == 34
    page = Notebook(tmp_path).read(ody['record'])
    assert 'zhouody@gmail.com' in page and 'Confirm they are one person' in page
    assert len(pages) == 5               # Ody, the two Johns, Misa, and a mail.com person
    listed = {row['address'] for row in result['automated_correspondents']}
    assert {'changelog@neon.tech', 'drive-shares-dm-noreply@google.com', 'usr-xyz@user.luma-mail.com',
            'speedrun@substack.com', 'post-training@mail.aitinkerers.org',
            '0xa633fd2e63@mail.openonion.ai'} <= listed
    # listed with the notice senders, but no organisation page: nobody writes from it (#1844)
    assert 'neon.tech' not in {row['domain'] for row in result['orgs']}


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
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])

    asked = {row['address']: row for row in result['possible_own_addresses']}
    assert list(asked) == ['aaronplus1996@gmail.com']    # one reply, or one letter, and it is a person
    assert asked['aaronplus1996@gmail.com']['sent'] == 106
    assert asked['aaronplus1996@gmail.com']['confirm'] == 'co rem init --mine aaronplus1996@gmail.com'
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

    def mail_rows(clients, days, mine, coverage, errors=None, progress=None, **kw):
        own = {a.lower() for a in mine}
        return [row for row in rows if row['address'] not in own], own

    monkeypatch.setattr('connectonion.rem.map._mail_rows', mail_rows)
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
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
    assert ('gmail: metadata only, 90 days; a seven-day window at the 200-message listing cap is '
            'split until every message in it is listed; no correspondents in this window') in coverage
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


def test_the_owners_page_is_filled_from_the_map_and_named(tmp_path, monkeypatch):
    """A first notebook opened on a blank page titled "Account owner" even though
    the map had just learned the owner's name, who they write to most and where
    they have been working. The map fills what it knows, cites itself, and asks
    about possible own addresses on the page; role and company stay Unknown."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()

    class Mail:
        def my_addresses(self): return {'xietianle@outlook.com'}
        def my_name(self): return 'Aaron x'

    people = [
        {'name': 'Ody Zhou', 'address': 'zhouodywork@gmail.com', 'mails': 30, 'sent': 20, 'received': 10,
         'one_way': False, 'first': '2026-07-01', 'last': '2026-09-20', 'boxes': ['gmail']},
        {'name': 'Ody Zhou', 'address': 'zhouody@gmail.com', 'mails': 4, 'sent': 2, 'received': 2,
         'one_way': False, 'boxes': ['outlook']},
        {'name': 'Tamara Berryman', 'address': 'tamara@unsw.example', 'mails': 12, 'sent': 5, 'received': 7,
         'one_way': False, 'boxes': ['outlook']},
        {'name': '', 'address': 'aaronplus1996@gmail.com', 'mails': 106, 'sent': 106, 'received': 0,
         'one_way': True, 'boxes': ['gmail']},
        {'name': 'Aaron', 'address': 'notifications@github.com', 'mails': 96, 'sent': 1, 'received': 95,
         'one_way': False, 'boxes': ['gmail']},
        {'name': '', 'address': 'larryleework7@gmail.com', 'mails': 14, 'sent': 14, 'received': 0,
         'one_way': True, 'boxes': ['gmail']},
    ]
    monkeypatch.setattr('connectonion.rem.map._mail_rows',
                        lambda *a, **kw: (people, {'xietianle@outlook.com'}))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [
        {'origin': '', 'repo': '/w/connectonion', 'path': '/w/connectonion', 'sessions': 40,
         'first': '2026-08-01', 'last': '2026-09-20'}])
    result = build_map(tmp_path, {}, {'outlook': Mail()}, skill_directories=[skills], days=90)
    page = Notebook(tmp_path).read(result['owner']['record'])
    assert page.startswith('# Aaron x\n')
    assert 'Ody Zhou (34)' in page and 'Tamara Berryman (12)' in page
    assert page.index('Ody Zhou (34)') < page.index('Tamara Berryman (12)')
    assert 'aaronplus1996@gmail.com (106' not in page.split('## Uncertainties')[0]   # not a correspondent
    assert 'Possibly also the owner\'s: aaronplus1996@gmail.com' in page
    assert 'co rem init --mine aaronplus1996@gmail.com' in page
    # A colleague who answers on another channel carries none of the owner's
    # words: not named on the page, and not offered to --mine either (#2008).
    assert 'larryleework7@gmail.com' not in {row['address'] for row in result['possible_own_addresses']}
    assert 'larryleework7' not in page.split('## Uncertainties')[1]
    assert 'larryleework7@gmail.com (14)' in page     # someone the owner writes to, like anyone else
    assert 'connectonion (40)' in page and '[1] Enumeration metadata' in page
    assert '- Role: Unknown' in page and '- Company: Unknown' in page
    # GitHub notifications, named after the owner, are a notice, not a person.
    assert 'notifications@github.com' in {row['address'] for row in result['automated_correspondents']}
    assert not any(row.get('address') == 'notifications@github.com' for row in result['people'])

    # A second map never overwrites what an investigation wrote.
    record = result['owner']['record']
    notebook = Notebook(tmp_path)
    notebook.write(record, notebook.read(record).replace('- This is the owner\'s own page. [1]',
                                                         '- Founder of OpenOnion. [2]'))
    build_map(tmp_path, {}, {'outlook': Mail()}, skill_directories=[skills], days=90)
    assert '- Founder of OpenOnion. [2]' in notebook.read(record)


def test_a_name_given_at_init_wins_over_the_mailbox(tmp_path):
    from connectonion.rem.map import _owner_name

    class Mail:
        def my_name(self): return 'Aaron x'

    class Broken:
        def my_name(self): raise RuntimeError('graph down')

    assert _owner_name({'outlook': Mail()}, 'Aaron Xie') == 'Aaron Xie'
    assert _owner_name({'gmail': Broken(), 'outlook': Mail()}) == 'Aaron x'
    assert _owner_name({}) == 'Account owner'


def test_name_alone_makes_the_owners_page_and_a_mailbox_later_keeps_it(tmp_path, monkeypatch):
    """`init --name "X"` with no mailbox made no owner page, though init's help
    promises one; `investigate me` then said "Run init first". The name is
    enough for the page; connecting a mailbox later fills the same page
    rather than starting a second one."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: ([], set()))
    first = build_map(tmp_path, {}, {}, skill_directories=[skills], name='Test User')
    record = first['owner']['record']
    assert Notebook(tmp_path).read(record).startswith('# Test User\n')
    assert record in first['created']

    class Mail:
        def my_addresses(self): return {'test@example.com'}
        def my_name(self): return ''

    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: ([], {'test@example.com'}))
    later = build_map(tmp_path, {}, {'gmail': Mail()}, skill_directories=[skills])
    assert later['owner']['record'] == record
    assert [p['path'] for p in Notebook(tmp_path).people()] == [record]


def test_without_a_name_or_a_mailbox_there_is_no_owner_page(tmp_path, monkeypatch):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: ([], set()))
    assert 'owner' not in build_map(tmp_path, {}, {}, skill_directories=[skills])


def test_an_upgraded_notebook_turns_the_owners_old_correspondent_page_into_the_owners_page(tmp_path, monkeypatch):
    """A notebook mapped by an older version had made aaron@… a correspondent page:
    titled by the address, History "Observed mail count: 1", marked unassessed.
    Re-mapped once the address was known to be the owner's, that page was reused
    as the owner page and left exactly as it was."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    notebook = Notebook(tmp_path)
    notebook.stub_person('people/aaron-mail.md', 'aaron@mail.example', ['aaron@mail.example'], email='aaron@mail.example')
    old = notebook.read('people/aaron-mail.md').replace(
        '## History\n- Unknown — not investigated yet',
        '## History\n- Observed mail count: 1; first: 2026-09-04; last: 2026-09-04; mailboxes: outlook. [1]').replace(
        '## Uncertainties\n', '## Uncertainties\n- Correspondent classification unassessed; mapping does not '
        'establish a person or employer.\n').replace(
        '- (none yet)', '- [1] Enumeration metadata, observed 2026-09-20 — .state/map.json')
    notebook.write('people/aaron-mail.md', old)

    class Mail:
        def my_addresses(self): return {'aaron@mail.example'}
        def my_name(self): return ''

    people = [{'name': 'Ody Zhou', 'address': 'ody@x.example', 'mails': 30, 'sent': 20, 'received': 10,
               'one_way': False, 'boxes': ['gmail']}]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, {'aaron@mail.example'}))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {'gmail': Mail()}, skill_directories=[skills], name='Aaron Xie')
    assert result['owner']['record'] == 'people/aaron-mail.md'
    page = notebook.read('people/aaron-mail.md')
    assert page.startswith('# Aaron Xie\n')
    assert 'Observed mail count: 1' not in page and 'Most mail with: Ody Zhou (30)' in page
    assert 'Correspondent classification unassessed' not in page
    assert '- Email: aaron@mail.example' in page


def test_pages_an_older_map_made_are_archived_when_this_map_would_not_make_them(tmp_path, monkeypatch):
    """A real notebook kept ten project pages for co rem's own task folders, six
    for one project's dated scratch folders, and two pages for one person, all from
    an older map. Maintenance kept trying to merge them by deleting, and was refused."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    notebook = Notebook(tmp_path)
    task = '/Users/x/rem-copy/.state/tasks/maintain-abc/notebook'
    notebook.stub_project('projects/notebook-1.md', 'notebook', [task])
    notebook.stub_project('projects/notebook-2.md', 'notebook', [task + '2'])
    investigated = notebook.read('projects/notebook-2.md').replace(
        'not investigated yet', 'investigated 2026-09-20 (codex)')
    notebook.write('projects/notebook-2.md', investigated)                     # someone's work: kept
    notebook.stub_project('projects/rvc-a.md', 'realtime-voice-chat',
                          ['/Users/x/Documents/Codex/2026-08-17/realtime-voice-chat'])
    notebook.stub_project('projects/rvc-b.md', 'realtime-voice-chat-2',
                          ['/Users/x/Documents/Codex/2026-08-22/realtime-voice-chat-2'])
    notebook.stub_person('people/dora-by-address.md', 'dora@example.org', ['dora@example.org'],
                         email='dora@example.org')
    people = [{'name': 'Dora Chen', 'address': 'dora@example.org', 'mails': 40, 'sent': 20, 'received': 20,
               'one_way': False, 'boxes': ['gmail']}]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [
        {'origin': '', 'repo': '', 'path': '/Users/x/Documents/Codex/2026-08-17/realtime-voice-chat',
         'sessions': 2, 'first': '2026-08-17', 'last': '2026-08-17'},
        {'origin': '', 'repo': '', 'path': '/Users/x/Documents/Codex/2026-08-22/realtime-voice-chat-2',
         'sessions': 2, 'first': '2026-08-22', 'last': '2026-08-22'}])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert len(result['projects']) == 1                                       # one scratch project, not two
    kept = result['projects'][0]['record']
    # The other scratch page is merged into the kept one (#1974): moved to the archive too.
    merged = {old for row in result['projects'] for old in row.get('merged', [])}
    assert set(result['archived']) | merged == {'projects/notebook-1.md',
                                                *({'projects/rvc-a.md', 'projects/rvc-b.md'} - {kept})}
    assert all((tmp_path / '.state/archived' / old).is_file() for old in merged)
    assert notebook.path('projects/notebook-2.md').is_file()                  # investigated: never moved
    assert (tmp_path / '.state/archived/projects/notebook-1.md').is_file()    # moved, not deleted
    dora = [row['record'] for row in result['people'] if row.get('name') == 'Dora Chen'][0]
    assert dora == 'people/dora-by-address.md' or 'people/dora-by-address.md' in result['archived']


def test_an_older_maps_person_page_for_a_notice_sender_is_archived(tmp_path, monkeypatch):
    """An older map made a "person" called Google; maintenance matched the word
    Google in session notes and went looking at it."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    notebook = Notebook(tmp_path)
    notebook.stub_person('people/google.md', 'Google', ['no-reply@accounts.google.com'],
                         email='no-reply@accounts.google.com')
    people = [{'name': 'Google', 'address': 'no-reply@accounts.google.com', 'mails': 54, 'sent': 0,
               'received': 54, 'one_way': True, 'boxes': ['gmail']}]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert 'people/google.md' in result['archived']
    assert not notebook.path('people/google.md').exists()


def test_the_map_waits_for_no_one_and_no_one_writes_under_it(tmp_path):
    """A scheduled batch ran during init, lost a lead page to init's archiving, and
    because pages had changed under it, skipped its forty messages as written."""
    import pytest
    from connectonion.rem.files import RemError, maintenance_lock
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    with maintenance_lock(tmp_path):                      # an upkeep batch is running
        with pytest.raises(RemError, match="busy"):
            build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert not (tmp_path / '.state' / 'map.json').exists()      # nothing written under someone else's lock
    assert build_map(tmp_path, {}, {}, skill_directories=[skills])['phase'] in ('mapped', 'partial')


def test_a_companys_subdomains_are_one_organisation(tmp_path, monkeypatch):
    """On the owner's map accounts.google.com, accountprotection.microsoft.com and
    ad.unsw.edu.au were each an organisation of their own (#1844)."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    people = [{'name': 'Ann Lee', 'address': 'ann@unsw.edu.au', 'mails': 4, 'sent': 2, 'received': 2},
              {'name': 'Bo Chen', 'address': 'bo@ad.unsw.edu.au', 'mails': 3, 'sent': 1, 'received': 2},
              {'name': 'Cy Wu', 'address': 'cy@corp.example.co.uk', 'mails': 2, 'sent': 1, 'received': 1}]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    orgs = {row['domain']: row for row in result['orgs']}
    assert set(orgs) == {'unsw.edu.au', 'example.co.uk'}
    assert len(orgs['unsw.edu.au']['people']) == 2
    page = Notebook(tmp_path).read(orgs['unsw.edu.au']['record'])
    assert '- unsw.edu.au' in page and '- ad.unsw.edu.au' in page


def test_a_domain_that_only_sends_notices_gets_no_organisation_page(tmp_path, monkeypatch):
    """35 of 272 organisations on the owner's map were login and mailer domains
    that no person wrote from; each would have cost an investigation (#1844)."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    people = [{'name': 'Google', 'address': 'no-reply@accounts.google.com', 'mails': 54, 'sent': 0,
               'received': 54, 'one_way': True},
              {'name': 'Ann Lee', 'address': 'ann@partner.com.au', 'mails': 4, 'sent': 2, 'received': 2}]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert [row['domain'] for row in result['orgs']] == ['partner.com.au']
    assert Notebook(tmp_path).list('orgs') == [result['orgs'][0]['record']]


def test_an_older_maps_organisation_page_for_a_subdomain_is_archived(tmp_path, monkeypatch):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    notebook = Notebook(tmp_path)
    notebook.stub_org('orgs/accounts-google-com.md', 'accounts.google.com', ['accounts.google.com'])
    notebook.stub_org('orgs/kept.md', 'kept.example', ['kept.example'])
    notebook.write('orgs/kept.md', notebook.read('orgs/kept.md').replace(
        'not investigated yet', 'investigated 2026-09-20 (codex)'))
    people = [{'name': 'Google', 'address': 'no-reply@accounts.google.com', 'mails': 54, 'sent': 0,
               'received': 54, 'one_way': True}]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert 'orgs/accounts-google-com.md' in result['archived']
    assert notebook.path('orgs/kept.md').is_file()                            # investigated: never moved


def test_a_page_an_older_map_titled_with_an_address_takes_the_name_found_now(tmp_path, monkeypatch):
    """1.8.9b16 learned names, but only a new page used them: re-running init
    kept 176 of the owner's pages titled `larryleework7@gmail.com`. A page nobody
    investigated is still map output, so the map may retitle it; an investigated
    one is someone's work and keeps its title."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    notebook = Notebook(tmp_path)
    notebook.stub_person('people/larry.md', 'larry@q.com', ['larry@q.com'], email='larry@q.com')
    notebook.stub_person('people/kept.md', 'kept@q.com', ['kept@q.com'], email='kept@q.com')
    notebook.write('people/kept.md', notebook.read('people/kept.md').replace(
        'not investigated yet', 'investigated 2026-09-20 (codex)'))
    people = [{'name': 'Larry', 'address': 'larry@q.com', 'mails': 14, 'sent': 14, 'received': 0},
              {'name': 'Kept Person', 'address': 'kept@q.com', 'mails': 3, 'sent': 2, 'received': 1}]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert notebook.read('people/larry.md').startswith('# Larry\n')
    assert notebook.read('people/kept.md').startswith('# kept@q.com\n')


def _map(tmp_path, monkeypatch, people):
    skills = tmp_path / 'installed'
    skills.mkdir(exist_ok=True)
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    return build_map(tmp_path, {}, {}, skill_directories=[skills])


def test_a_nameless_address_the_owner_never_wrote_to_waits_for_review(tmp_path, monkeypatch):
    """After names were found for 176 pages, 43 of the owner's people pages were
    still titled by a bare address: senders the owner never wrote to. Each would
    have cost an investigation and filled the contents with addresses (#1844).
    Held back, never deleted; a nameless address the owner wrote to, and the
    agent's own address, stay people.
    #2057: an address the owner never wrote to now gets no page at all, named or
    not; the one nameless page still held is one the owner only writes to."""
    from connectonion.rem.queue import order
    from connectonion.rem.reader import snapshot
    prepare(tmp_path)
    result = _map(tmp_path, monkeypatch, [
        {'name': '', 'address': 'x7@shop.example', 'mails': 5, 'sent': 0, 'received': 5, 'one_way': True},
        {'name': '', 'address': 'client@firm.example', 'mails': 2, 'sent': 1, 'received': 1, 'one_way': False},
        {'name': '', 'address': '0xa633fd2e63@mail.openonion.ai', 'mails': 6, 'sent': 3, 'received': 3,
         'one_way': False},
        {'name': 'Ann Lee', 'address': 'ann@partner.example', 'mails': 1, 'sent': 0, 'received': 1,
         'one_way': True},
        {'name': '', 'address': 'desk@quiet.example', 'mails': 3, 'sent': 3, 'received': 0, 'one_way': True}])
    pages = {row['addresses'][0]: row['record'] for row in result['people']}
    assert {row['address'] for row in result['without_page']} == {'x7@shop.example', 'ann@partner.example'}
    assert not {'x7@shop.example', 'ann@partner.example'} & set(pages)
    held = pages['desk@quiet.example']
    assert result['needs_review'] == [held]
    assert Notebook(tmp_path).read(held).startswith('# desk@quiet.example\n')       # kept, not deleted
    assert Notebook(tmp_path).read(pages['0xa633fd2e63@mail.openonion.ai']).startswith('# 0xa633fd2e63@')
    queued = [row['path'] for row in order(tmp_path, 'people')]
    assert held not in queued
    assert {pages['client@firm.example'], pages['0xa633fd2e63@mail.openonion.ai']} <= set(queued)
    records = {row['path']: row for row in snapshot(tmp_path)['records']}
    assert records[held]['needs_review']                          # still linkable, left off the contents
    assert not any(row.get('needs_review') for path, row in records.items() if path != held)


def test_a_sender_named_after_its_own_domain_is_a_service_not_a_person(tmp_path, monkeypatch):
    """1.9.0a3 on the owner's notebook: Apple Developer, Airbnb, Google Cloud,
    Retool and X were people pages. None of their addresses says no-reply; what
    gives them away is a display name that is the sender's own domain, and mail
    that mostly comes in (#1987)."""
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person('people/airbnb.md', 'Airbnb', ['discover@airbnb.com'], email='discover@airbnb.com')
    result = _map(tmp_path, monkeypatch, [
        {'name': 'Apple Developer', 'address': 'developer@email.apple.com', 'mails': 4, 'sent': 1, 'received': 3,
         'one_way': False},
        {'name': 'Apple Developer', 'address': 'developer@insideapple.apple.com', 'mails': 3, 'sent': 0,
         'received': 3, 'one_way': True},
        {'name': 'Airbnb', 'address': 'discover@airbnb.com', 'mails': 6, 'sent': 0, 'received': 6, 'one_way': True},
        {'name': 'Google Cloud', 'address': 'googlecloud@google.com', 'mails': 5, 'sent': 0, 'received': 5,
         'one_way': True},
        {'name': 'Retool', 'address': 'learn@retool.com', 'mails': 5, 'sent': 0, 'received': 5, 'one_way': True},
        {'name': 'X', 'address': 'notify@x.com', 'mails': 4, 'sent': 1, 'received': 3, 'one_way': False},
        # People stay: one whose own domain is their name, one who wrote first,
        # and a company desk the owner writes back to as often as it writes.
        {'name': 'Aaron Wu', 'address': 'aaron@aaron.dev', 'mails': 6, 'sent': 1, 'received': 5, 'one_way': False},
        {'name': 'Mia Tan', 'address': 'mia@acme.example', 'mails': 5, 'sent': 0, 'received': 5, 'one_way': True},
        {'name': 'Acme Sales', 'address': 'sales@acme.example', 'mails': 4, 'sent': 2, 'received': 2,
         'one_way': False}])
    assert {row.get('name') for row in result['people']} == {'Aaron Wu', 'Acme Sales'}
    # Mia only ever wrote: a person without a page yet, not a service (#2057).
    assert [row['address'] for row in result['without_page']] == ['mia@acme.example']
    listed = {row['address'] for row in result['automated_correspondents']}
    assert {'developer@email.apple.com', 'developer@insideapple.apple.com', 'discover@airbnb.com',
            'googlecloud@google.com', 'learn@retool.com', 'notify@x.com'} <= listed
    assert 'people/airbnb.md' in result['archived']                   # map output only: moved, not deleted


def test_an_address_titled_page_the_owner_only_ever_writes_to_is_held(tmp_path, monkeypatch):
    """1.9.0a3 listed aaron@openonion.ai as a person: 10 sent, none received, no
    name -- the shape of the owner's own other mailbox. It is still asked about
    with --mine, and held off the list and the queue until it is answered (#1987)."""
    from connectonion.rem.map import needs_review
    prepare(tmp_path)
    result = _map(tmp_path, monkeypatch, [
        {'name': '', 'address': 'aaron@openonion.ai', 'mails': 10, 'sent': 10, 'received': 0, 'one_way': True},
        {'name': '', 'address': 'client@firm.example', 'mails': 2, 'sent': 1, 'received': 1, 'one_way': False},
        {'name': 'Dana Reyes', 'address': 'dana@client.example', 'mails': 4, 'sent': 4, 'received': 0,
         'one_way': True}])
    pages = {row['addresses'][0]: row['record'] for row in result['people']}
    assert result['needs_review'] == [pages['aaron@openonion.ai']] == sorted(needs_review(tmp_path))
    assert 'aaron@openonion.ai' in {row['address'] for row in result['possible_own_addresses']}


def test_a_reply_or_a_name_on_a_later_map_brings_the_page_back(tmp_path, monkeypatch):
    """#2057: an address that only ever wrote to the owner gets no page, held or
    not, until the owner writes back; the held pages are the nameless ones the
    owner only writes to, and a reply or a name releases them."""
    from connectonion.rem.map import needs_review
    prepare(tmp_path)
    quiet = [{'name': '', 'address': 'a@one.example', 'mails': 3, 'sent': 3, 'received': 0, 'one_way': True},
             {'name': '', 'address': 'b@two.example', 'mails': 3, 'sent': 3, 'received': 0, 'one_way': True}]
    silent = {'name': '', 'address': 'c@three.example', 'mails': 2, 'sent': 0, 'received': 2, 'one_way': True}
    first = _map(tmp_path, monkeypatch, [*quiet, silent])
    assert len(first['needs_review']) == 2 and needs_review(tmp_path) == set(first['needs_review'])
    assert [row['address'] for row in first['without_page']] == ['c@three.example']
    answered = [{**quiet[0], 'mails': 4, 'received': 1, 'one_way': False}, {**quiet[1], 'name': 'Bo Chen'},
                {**silent, 'mails': 3, 'sent': 1, 'one_way': False}]
    second = _map(tmp_path, monkeypatch, answered)
    assert second['needs_review'] == [] and needs_review(tmp_path) == set()
    paged = {row['address']: row['record'] for row in second['people']}
    assert {paged['a@one.example'], paged['b@two.example']} == set(first['needs_review'])
    assert 'c@three.example' in paged and second['without_page'] == []      # its reply brings a page


def test_an_investigated_page_is_never_held_for_review(tmp_path, monkeypatch):
    """Investigating a held page is the owner asking for it, so it leaves the
    bucket at once; a page someone has investigated is never put in it."""
    from connectonion.rem.map import needs_review
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person('people/kept.md', 'kept@q.example', ['kept@q.example'], email='kept@q.example')
    notebook.note_investigation('people/kept.md', 'gmail')
    before = notebook.read('people/kept.md')
    # The investigated page keeps its row although its mail is one-way; a map-only
    # one-way page would get none (#2057), so the held one is written to, never answered.
    result = _map(tmp_path, monkeypatch, [
        {'name': '', 'address': 'kept@q.example', 'mails': 2, 'sent': 0, 'received': 2, 'one_way': True},
        {'name': '', 'address': 'held@q.example', 'mails': 3, 'sent': 3, 'received': 0, 'one_way': True}])
    assert 'people/kept.md' in {row['record'] for row in result['people']}
    held = result['needs_review']
    assert len(held) == 1 and 'people/kept.md' not in held
    assert notebook.read('people/kept.md') == before
    notebook.note_investigation(held[0], 'gmail')
    assert needs_review(tmp_path) == set()


def _repository_with_worktrees(tmp_path):
    """A main checkout, a live agent worktree (a `.git` file pointing home) and
    one Claude Code already removed, as ~/projects/connectonion looked (#1955)."""
    main = tmp_path / 'code/connectonion'
    (main / '.git/worktrees/agent-a1').mkdir(parents=True)
    live = main / '.claude/worktrees/agent-a1'
    live.mkdir(parents=True)
    (live / '.git').write_text(f'gitdir: {main}/.git/worktrees/agent-a1\n')
    return main, live, main / '.claude/worktrees/agent-b2'


def test_worktrees_collapse_to_the_main_checkout_and_an_old_page_is_corrected(tmp_path, monkeypatch):
    main, live, gone = _repository_with_worktrees(tmp_path)
    root = tmp_path / 'notebook'
    prepare(root)
    nb = Notebook(root)
    # The page an earlier map wrote: worktrees only, and a folder the owner added.
    nb.stub_project('projects/connectonion-old.md', 'connectonion', [str(live), str(gone), '/elsewhere/notes'],
                    sessions=3, first_seen='2026-09-01', last_seen='2026-09-02')
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: ([], set()))
    origin = 'https://github.com/openonion/connectonion'
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [
        {'path': str(main), 'repo': str(main), 'origin': origin,
         'sessions': 2, 'first': '2026-09-10', 'last': '2026-09-29'},
        {'path': str(live), 'repo': str(main), 'origin': origin,
         'sessions': 5, 'first': '2026-09-20', 'last': '2026-09-30'},
        {'path': str(gone), 'repo': '', 'origin': '',
         'sessions': 1, 'first': '2026-09-05', 'last': '2026-09-06'}])
    report = build_map(root, {}, {}, skill_directories=[])
    assert [row['record'] for row in report['projects']] == ['projects/connectonion-old.md']
    assert report['projects'][0]['sessions'] == 8
    page = nb.read('projects/connectonion-old.md')
    paths = page.partition('## Paths\n')[2].split('\n## ', 1)[0].splitlines()
    assert paths[0] == f'- {main}'
    assert '.claude/worktrees' not in page
    assert '- /elsewhere/notes' in paths
    assert {'- Sessions: 8', '- First seen: 2026-09-05', '- Last seen: 2026-09-30'} <= set(paths)


def test_a_1_8_confirm_hint_on_the_owner_s_page_is_corrected_to_co_rem(tmp_path, monkeypatch):
    """The owner's page kept "If it is yours: co wiki init --mine …" from a 1.8 map."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()

    class Mail:
        def my_addresses(self): return {'me@outlook.example'}
        def my_name(self): return 'Me Owner'

    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: ([], {'me@outlook.example'}))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {'outlook': Mail()}, skill_directories=[skills], days=90)
    record = result['owner']['record']
    notebook = Notebook(tmp_path)
    notebook.write(record, notebook.read(record).replace(
        '## Uncertainties\n', '## Uncertainties\n- Possibly also the owner\'s: me2@x.example (9 sent, none '
                              'received). If it is yours: co wiki init --mine me2@x.example\n'))
    build_map(tmp_path, {}, {'outlook': Mail()}, skill_directories=[skills], days=90)
    page = notebook.read(record)
    # No longer asked by this map, so the line goes rather than stay stale (#2017).
    assert 'co wiki' not in page and 'me2@x.example' not in page


def test_the_owner_is_named_as_others_address_them_not_as_the_mailbox_is_configured(tmp_path, monkeypatch):
    """#2008: a real account's configured name was "Aaron x" and the page was
    people/account-owner-….md. Outlook stamps that name on every sent mail too
    (83 times on the real 7-day map); the people writing to him put "Aaron Xie"
    (and "Aaron xie") on his address, and "xietianle" is only the address again."""
    import collections
    from connectonion.rem.map import _owner_name

    class Mail:
        def my_addresses(self): return {'xietianle@example.org'}
        def my_name(self): return 'Aaron x'

        def list_between(self, start, end, limit):
            day = start[:10]
            return [{'id': f'{day}-1', 'date': start, 'from': 'xietianle@example.org', 'from_name': 'Aaron x',
                     'to': ['Bob Stone <bob@partner.example>'], 'subject': 'Plan'},
                    {'id': f'{day}-2', 'date': start, 'from': 'Aaron x <xietianle@example.org>',
                     'to': ['bob@partner.example'], 'subject': 'Plan 2'},
                    {'id': f'{day}-3', 'date': start, 'from': 'Bob Stone <bob@partner.example>',
                     'to': ['Aaron Xie <xietianle@example.org>'], 'subject': 'Re: Plan'},
                    {'id': f'{day}-4', 'date': start, 'from': 'Ann Lee <ann@partner.example>',
                     'to': ['Bob Stone <bob@partner.example>'], 'cc': ['Aaron xie <xietianle@example.org>'],
                     'subject': 'Intro'},
                    {'id': f'{day}-5', 'date': start, 'from': 'Cy <cy@partner.example>',
                     'to': ['xietianle <xietianle@example.org>'], 'subject': 'Hi'}]

    def names(addressed=(), sent=()):
        return {'addressed': collections.Counter(dict(addressed)), 'sent': collections.Counter(dict(sent))}

    assert _owner_name({'o': Mail()}, '', names({'Aaron Xie': 2, 'Aaron xie': 1, 'Aaron x': 2},
                                                {'Aaron x': 83})) == 'Aaron Xie'
    assert _owner_name({'o': Mail()}, '', names(sent={'Ada Owner': 3})) == 'Ada Owner'
    assert _owner_name({'o': Mail()}, 'Given Name', names({'Aaron Xie': 3})) == 'Given Name'
    assert _owner_name({'o': Mail()}, '', names()) == 'Aaron x'

    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {'outlook': Mail()}, skill_directories=[skills], days=14)
    record = result['owner']['record']
    assert record.startswith('people/aaron-xie-')
    page = Notebook(tmp_path).read(record)
    assert page.startswith('# Aaron Xie\n')
    # Your own page has no "How the user writes to them" (#2008).
    assert '## How the user writes to them' not in page and '## Cadence' in page
    # A later map keeps the file where it is, whatever the name turns out to be.
    assert build_map(tmp_path, {}, {'outlook': Mail()}, skill_directories=[skills], days=14,
                     name='Someone Else')['owner']['record'] == record


# ------------------------------------------- the 1.9.0a5 acceptance run (#2017, #2018)


def _row(name, address, sent, received):
    return {'name': name, 'address': address, 'mails': sent + received, 'sent': sent, 'received': received,
            'one_way': not (sent and received), 'boxes': ['gmail']}


def test_a_fresh_map_makes_no_page_for_booking_otp_and_portal_senders(tmp_path, monkeypatch):
    """#2018: the acceptance map made team-telnyx and held pages for Workday's OTP
    sender, Singapore Airlines' booking desk, Lebara and Telnyx's portal; tidy,
    run before the map, had nothing to act on. The notebook a map leaves is tidy."""
    from connectonion.rem.map import service_page
    from connectonion.rem.tidy import tidy
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    services = [_row('Team Telnyx', 'discover@telnyx.com', 0, 3), _row('', 'portal@telnyx.com', 0, 2),
                _row('', 'booking@singaporeair.com', 0, 1), _row('', 'hub24management@otp.workday.com', 0, 1),
                _row('', 'hub24management@myworkday.com', 0, 1), _row('', 'mylebara@lebara.com.au', 0, 1)]
    people = [_row('Mia Tan', 'mia@acme.example', 0, 5), _row('John Smith', 'john@smith.dev', 0, 2),
              _row('Ann Lee', 'ann@partner.com.au', 2, 2), _row('', 'eishi.sn@gmail.com', 0, 2)]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (services + people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    listed = {row['address'] for row in result['automated_correspondents']}
    assert listed >= {row['address'] for row in services}
    # People, not services: Ann has a page, and the three who only wrote wait
    # without one until the owner answers (#2057).
    assert {row.get('address') for row in result['people']} >= {'ann@partner.com.au'}
    assert {row['address'] for row in result['without_page']} == {
        'mia@acme.example', 'john@smith.dev', 'eishi.sn@gmail.com'}
    assert not any(service_page(p['title'], p['emails'], None, set()) for p in Notebook(tmp_path).people())
    assert tidy(tmp_path) == {}


def test_an_older_maps_held_page_for_a_service_is_archived_by_the_next_map(tmp_path, monkeypatch):
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    notebook = Notebook(tmp_path)
    notebook.stub_person('people/portal.md', 'portal@telnyx.com', ['portal@telnyx.com'], email='portal@telnyx.com')
    monkeypatch.setattr('connectonion.rem.map._mail_rows',
                        lambda *a, **kw: ([_row('', 'portal@telnyx.com', 0, 2)], set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert 'people/portal.md' in result['archived']
    assert notebook.people() == []


def test_a_mailbox_provider_or_an_event_relay_is_never_an_organisation(tmp_path, monkeypatch):
    """#2018: orgs/yahoo-com-hk (Ian, ischihang@yahoo.com.hk) and luma-mail.com,
    reached through a person whose display name joined a relay address."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    people = [_row('Ian', 'ischihang@yahoo.com.hk', 22, 1), _row('Tracy Wu', 'tracy@hotmail.co.uk', 3, 1),
              _row('Kim Park', 'kim@naver.com', 1, 1), _row('Jo Lin', 'jo@outlook.com.au', 1, 1),
              _row('Sam Lee', 'sam@acme.com.au', 2, 2), _row('Sam Lee', 'sam-lee@user.luma-mail.com', 0, 253)]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert [row['domain'] for row in result['orgs']] == ['acme.com.au']


def test_a_remap_rewrites_the_owners_map_lines_instead_of_adding_more(tmp_path, monkeypatch):
    """#2017: after a re-map the owner's page still said "In the 90 days to
    2026-09-25", and each map added its "Possibly also the owner's" lines again
    at the new counts."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()

    class Mail:
        def my_addresses(self): return {'xietianle@outlook.com'}
        def my_name(self): return 'Aaron Xie'

    counts = iter([101, 108, 110])

    def mail_rows(*a, **kw):
        sent = next(counts)
        rows = [_row('', 'aaronplus1996@gmail.com', sent, 0), _row('Ody Zhou', 'ody@x.example', sent, 5)]
        return rows, {'xietianle@outlook.com'}

    monkeypatch.setattr('connectonion.rem.map._mail_rows', mail_rows)
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    first = build_map(tmp_path, {}, {'outlook': Mail()}, skill_directories=[skills], days=90)
    notebook = Notebook(tmp_path)
    record = first['owner']['record']
    stale = notebook.read(record).replace(f"to {first['started'][:10]}:", 'to 2026-09-25:')
    notebook.write(record, stale.replace('observed ' + first['started'], 'observed 2026-09-25T10:00:00+00:00'))
    # Someone investigated the address's page, so tidy leaves it and the map keeps asking.
    mine = first['possible_own_addresses'][0]['record']
    notebook.write(mine, notebook.read(mine).replace('not investigated yet', 'investigated 2026-09-28'))
    build_map(tmp_path, {}, {'outlook': Mail()}, skill_directories=[skills], days=90)
    last = build_map(tmp_path, {}, {'outlook': Mail()}, skill_directories=[skills], days=90)
    page = notebook.read(record)
    possibly = [line for line in page.splitlines() if line.startswith("- Possibly also the owner's:")]
    assert possibly == ["- Possibly also the owner's: aaronplus1996@gmail.com (110 sent, none received). "
                        "If it is yours: co rem init --mine aaronplus1996@gmail.com"]
    history = [line for line in page.splitlines() if line.startswith('- In the ')]
    assert history == [f"- In the 90 days to {last['started'][:10]}: wrote 110 and received 5 messages with "
                       "1 correspondents in gmail. [1]"]
    assert '2026-09-25' not in page and page.count('Most mail with:') == 1
    assert f"- [1] Enumeration metadata, observed {last['started']}" in page


# ------------------------------------------- the 1.9.0a6 acceptance run (#2031)


def test_a_company_writing_as_itself_is_a_service_and_its_people_stay_people(tmp_path, monkeypatch):
    """#2031: "Flagship Minerals" <ceo@flagshipminerals.com>, one investor update never
    answered, was queued as a person and cost 100,080 tokens. Its display name is
    its own domain written as words; a person writing from a company domain is not."""
    from connectonion.rem.map import service_page
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    services = [_row('Flagship Minerals', 'ceo@flagshipminerals.com', 0, 1),
                _row('Blue Sky Ventures Ltd', 'investors@blueskyventures.com', 0, 2)]
    people = [_row('Mia Tan', 'mia@miatan.com', 0, 1), _row('Ann Smith', 'ann@flagshipminerals.com', 3, 2),
              _row('Ann Lee', 'ann@flagship.com.au', 0, 1)]
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (services + people, set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    listed = {row['address'] for row in result['automated_correspondents']}
    assert listed >= {row['address'] for row in services}
    # People, not services: the one who corresponds has a page, the two who
    # only wrote are listed without one (#2057).
    assert {row.get('address') for row in result['people']} >= {'ann@flagshipminerals.com'}
    assert {row['address'] for row in result['without_page']} == {'mia@miatan.com', 'ann@flagship.com.au'}
    assert service_page('Flagship Minerals', ['ceo@flagshipminerals.com'], None, set())


# ------------------------------------------- fewer pages (#2057)


def test_a_page_is_for_someone_the_owner_corresponds_with(tmp_path, monkeypatch):
    """#2057: 374 of the owner's 381 people pages were empty templates, most for
    one mail either way. A page comes with mail both ways, or when the owner
    writes twice; one mail sent or one received is listed in the map, not paged,
    and its domain makes no organisation page."""
    prepare(tmp_path)
    result = _map(tmp_path, monkeypatch, [
        _row('Kai Ng', 'kai@both.example', 1, 1), _row('Lu Fang', 'lu@twice.example', 2, 0),
        _row('Ola Berg', 'ola@sentone.example', 1, 0), _row('Pat Kim', 'pat@gotone.example', 0, 1)])
    paged = {row['address']: row['record'] for row in result['people']}
    assert set(paged) == {'kai@both.example', 'lu@twice.example'}
    notebook = Notebook(tmp_path)
    assert sorted(email for page in notebook.people() for email in page['emails']) == [
        'kai@both.example', 'lu@twice.example']
    assert {row['address']: (row['sent'], row['received']) for row in result['without_page']} == {
        'ola@sentone.example': (1, 0), 'pat@gotone.example': (0, 1)}
    assert {row['domain'] for row in result['orgs']} == {'both.example', 'twice.example'}
    assert notebook.list('orgs') == sorted(row['record'] for row in result['orgs'])
    assert any('2 correspondents with mail one way only' in line for line in result['coverage'])


def test_a_new_person_page_states_the_last_contact_in_its_lead_and_leaves_history_empty(tmp_path, monkeypatch):
    """#2059: 379 of 424 History bullets on the owner's people pages were the map's
    "Observed mail count: N; first: …; last: …", cited to .state/map.json."""
    prepare(tmp_path)
    skills = tmp_path / 'installed'
    skills.mkdir()
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: (
        [{'name': 'Basem Suleiman', 'address': 'b@unsw.edu.au', 'mails': 6, 'sent': 2, 'received': 4,
          'first': '2026-08-01', 'last': '2026-09-06', 'boxes': ['outlook']}], set()))
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    record = next(row['record'] for row in result['people'] if row.get('address') == 'b@unsw.edu.au')
    page = Notebook(tmp_path).read(record)
    assert 'Last contact: 2026-09-06; 6 mails (outlook).' in page
    assert 'Observed mail count' not in page and 'Enumeration metadata' not in page
    assert 'classification unassessed' not in page
    assert '## History\n- Unknown — not investigated yet' in page
