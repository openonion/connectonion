"""Organisation UI inputs come from cited notebook facts, not domain guesses."""
from datetime import date

import pytest

from connectonion.rem import census, facts, today
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.reader import snapshot

ORG = 'orgs/fernhill.md'
PERSON = 'people/mara.md'
PROJECT = 'projects/fernhill.md'


def notebook(tmp_path):
    prepare(tmp_path)
    return Notebook(tmp_path)


def test_cited_fields_survive_normalization_and_uncited_values_do_not():
    for path, field, value in [(ORG, 'Kind', 'client_partner'), (ORG, 'To you', '你的客户。'),
                               (PERSON, 'Unit', 'Founders programme')]:
        text = f'# Fernhill Labs\n\n## Facts\n- {field}: {value} [1]\n'
        parsed = facts.parse(facts.upgrade(path, text), path)
        assert parsed[field] == [{'value': value, 'qualifier': '', 'citations': ['1']}]
        dropped, labels = facts.drop_uncited(path, text.replace(' [1]', ''))
        assert labels == [field]
        assert facts.parse(dropped, path)[field] == []


@pytest.mark.parametrize('link', ['[[orgs/fernhill]]', '[[orgs/fernhill.md|Fernhill Labs]]',
                                   '[Fernhill Labs](../orgs/fernhill.md)'])
def test_snapshot_exposes_cited_org_team_and_project_data(tmp_path, link):
    book = notebook(tmp_path)
    book.write(ORG, '# Fernhill Labs\n\n## Facts\n- Kind: client_partner [1]\n- To you: 你的客户。 [1]\n')
    book.write(PERSON, f'# Mara\n\n## Facts\n- Company: {link} [2]\n- Team: Founders programme [2]\n')
    book.write(PROJECT, f'# Fernhill project\n\n## Facts\n- Organisation: {link} [3]\n')
    rows = {row['path']: row for row in snapshot(tmp_path)['records']}
    assert rows[ORG]['kind'] == 'client_partner'
    assert rows[ORG]['to_you'] == '你的客户。'
    assert rows[ORG]['private'] is False
    assert rows[ORG]['people'] == [PERSON]
    assert rows[ORG]['projects'] == [PROJECT]
    assert rows[PERSON]['team'] == 'Founders programme'
    assert rows[PERSON]['organisations'] == [ORG]
    assert rows[PROJECT]['organisations'] == [ORG]
    assert rows[PROJECT]['facts']['Organisation'][0]['citations'] == ['3']
    assert any(rel['path'] == ORG and rel['kind'] == 'linked' for rel in rows[PROJECT]['relations'])


@pytest.mark.parametrize('marker', ['[sensitive]', '[personal]', '- Kind: personal [1]'])
def test_private_org_and_unknown_fields_are_explicit(tmp_path, marker):
    book = notebook(tmp_path)
    book.write(ORG, f'# Fernhill Labs\n\n## Facts\n{marker}\n')
    book.write(PERSON, '# Avery\n\n## Facts\n- Email: avery@fernhill.example\n')
    rows = {row['path']: row for row in snapshot(tmp_path)['records']}
    assert rows[ORG]['private'] is True
    assert rows[ORG]['to_you'] == ''
    assert rows[ORG]['people'] == []
    assert rows[PERSON]['team'] == ''
    assert rows[PERSON]['organisations'] == []


def test_unknown_kind_does_not_become_a_filter_and_source_markers_do_not_hide_org(tmp_path):
    book = notebook(tmp_path)
    book.write(ORG, '# Fernhill Labs\n\n## Facts\n- Kind: spaceship [1]\n\n## Sources\n- [1] gmail:x [personal]\n')
    row = next(row for row in snapshot(tmp_path)['records'] if row['path'] == ORG)
    assert row['kind'] == '' and row['private'] is False


def test_org_threads_share_today_structure_and_dedupe_by_resolved_evidence(tmp_path):
    book = notebook(tmp_path)
    promise = 'The user owes Mara: feedback — “I will send feedback” — since 2026-11-01 — due 2026-11-07'
    book.write(ORG, '# Fernhill Labs\n\n## Open threads\n'
               f'- {promise} [1]\n- Fernhill Labs owes the user: the agreement — since 2026-11-02 [2]\n\n'
               '## Sources\n- [1] gmail:promise\n- [2] gmail:agreement\n')
    book.write(PERSON, '# Mara\n\n## Facts\n- Company: [[orgs/fernhill]] [9]\n\n'
               f'## Open threads\n- {promise} [9]\n\n## Sources\n- [9] gmail:promise\n')
    queue = today.queue(tmp_path, as_of=date(2026, 11, 8))
    assert len(queue) == 2
    owed = next(row for row in queue if row['dir'] == 'mine')
    assert owed['since'] == '2026-11-01' and owed['due'] == '2026-11-07'
    assert len(owed['keys']) == 2
    org = next(row for row in snapshot(tmp_path)['records'] if row['path'] == ORG)
    assert len(org['obligations']) == 2
    assert {row['dir'] for row in org['obligations']} == {'mine', 'theirs'}
    assert next(row for row in org['obligations'] if row['dir'] == 'mine')['people'] == [PERSON]
    assert all(row['record'] and row['title'] and row['key'] for row in org['obligations'])


@pytest.mark.parametrize('link', ['[[orgs/missing]]', '[Fernhill Labs](../orgs/missing.md)'])
def test_hygiene_reports_missing_org_and_a_concrete_fix(tmp_path, link):
    from connectonion.rem.tidy import notebook_checks
    book = notebook(tmp_path)
    book.write(PERSON, f'# Mara\n\n## Facts\n- Company: {link} [1]\n')
    checks = [row for row in notebook_checks(tmp_path) if not row['ok']]
    assert len(checks) == 1
    assert PERSON in checks[0]['detail'] and 'orgs/missing.md' in checks[0]['detail']
    assert 'Company' in checks[0]['fix'] and 'create' in checks[0]['fix'].lower()


@pytest.mark.parametrize('title,body', [
    ('Fernhill Labs', '## Domains\n- fernhill.example [1]\n'),
    ('Fernhill Labs shared mailbox', '## Facts\n- Email: team@fernhill.example\n'),
])
def test_written_non_people_are_flagged_and_excluded_from_counts(tmp_path, title, body):
    from connectonion.rem.tidy import notebook_checks
    book = notebook(tmp_path)
    book.write(ORG, '# Fernhill Labs\n')
    book.write(PERSON, f'# {title}\n\n{body}\n## Our relationship\nA shared contact. [1]\n')
    assert census.counts(tmp_path)['people']['mapped'] == 0
    checks = [row for row in notebook_checks(tmp_path) if not row['ok']]
    assert any(PERSON in row['detail'] and 'people/' in row['fix'] for row in checks)
    rows = {row['path']: row for row in snapshot(tmp_path)['records']}
    assert rows[PERSON]['service'] is True
    assert rows[ORG]['people'] == []


def test_org_list_keeps_distinct_obligations_on_one_source_and_honours_done(tmp_path):
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.threads import done_key
    book = notebook(tmp_path)
    feedback = 'The user owes Mara: feedback — since 2026-11-01 [1]'
    agreement = 'The user owes Mara: the agreement — since 2026-11-01 [1]'
    book.write(ORG, f'# Fernhill Labs\n\n## Open threads\n- {feedback}\n- {agreement}\n\n## Sources\n- [1] gmail:request\n')
    row = next(row for row in snapshot(tmp_path, local=True)['records'] if row['path'] == ORG)
    assert len(row['obligations']) == 2
    write_json(state_path(tmp_path, 'threads.json'), {done_key(ORG, feedback): {'state': 'done'}})
    row = next(row for row in snapshot(tmp_path, local=True)['records'] if row['path'] == ORG)
    assert [item['text'] for item in row['obligations']] == [agreement]


def test_named_person_is_not_a_shared_mailbox_just_because_of_their_role(tmp_path):
    book = notebook(tmp_path)
    book.write(PERSON, '# Mara\n\n## Facts\n- Email: mara@fernhill.example\n'
               '- Role: Team lead managing a shared mailbox [1]\n')
    assert census.counts(tmp_path)['people']['mapped'] == 1


def test_doctor_command_includes_notebook_hygiene(tmp_path, monkeypatch):
    import json
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    book = notebook(tmp_path)
    book.write(PERSON, '# Mara\n\n## Facts\n- Company: [[orgs/missing]] [1]\n')
    monkeypatch.setattr('connectonion.rem.runner.ready', lambda config: ('', ''))
    result = CliRunner().invoke(app, ['rem', '--root', str(tmp_path), '--json', 'doctor'])
    checks = json.loads(result.stdout)['data']
    check = next(row for row in checks if row['check'] == 'organisation link')
    assert not check['ok'] and PERSON in check['detail'] and 'create orgs/missing.md' in check['fix']


def test_explicit_org_roster_links_students_without_guessing_employment(tmp_path):
    book = notebook(tmp_path)
    book.write(ORG, '# Fernhill Labs\n\n## People here\n- [Mara](../people/mara.md) — student [1]\n')
    book.write(PERSON, '# Mara\n\n## Facts\n- Company: Unknown\n- Team: Student team [1]\n\n'
               '## Open threads\n- The user owes Mara: feedback — due 2026-11-07 [1]\n')
    rows = {row['path']: row for row in snapshot(tmp_path)['records']}
    assert rows[ORG]['people'] == [PERSON]
    assert len(rows[ORG]['obligations']) == 1
    assert rows[PERSON]['facts']['Company'] == []
    assert rows[PERSON]['organisations'] == [ORG]


@pytest.mark.parametrize('statement,direction', [
    ('The user owes Mara', 'mine'), ('Mara owes the user', 'theirs'),
    ('The user asked Mara', 'theirs'), ('Mara asked the user', 'mine'),
])
def test_org_only_thread_names_its_known_counterpart_without_duplicate_writing(tmp_path, statement, direction):
    book = notebook(tmp_path)
    book.write(ORG, '# Fernhill Labs\n\n## Facts\n- Your contacts: [[people/mara]] [1]\n\n'
               f'## Open threads\n- {statement}: feedback — due 2026-11-07 [1]\n'
               '- Fernhill Labs owes the user: agreement — since 2026-11-01 [2]\n')
    book.write(PERSON, '# Mara\n\n## Facts\n- Team: Founders programme [1]\n')
    org = next(row for row in snapshot(tmp_path)['records'] if row['path'] == ORG)
    feedback = next(row for row in org['obligations'] if 'feedback' in row['text'])
    assert feedback['dir'] == direction and feedback['people'] == [PERSON]
    assert next(row for row in org['obligations'] if 'agreement' in row['text'])['people'] == []
