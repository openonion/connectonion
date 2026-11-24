"""A hierarchy is supported structure, never a guess from an address."""
from datetime import date

import pytest

from connectonion.rem import facts
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.reader import snapshot

ORG = 'orgs/fernhill.md'
COURSE = 'orgs/course.md'
TEAM = 'orgs/team.md'
MARA = 'people/mara.md'
AVERY = 'people/avery.md'


def book_at(root):
    prepare(root)
    book = Notebook(root)
    book.write(ORG, '# Fernhill University\n\n## Facts\n- Kind: university [1]\n')
    return book


def unit(book, path, kind, parent):
    book.write(path, f'# {kind}\n\n## Facts\n- Kind: {kind} [1]\n- Parent: [[{parent}]] [1]\n')


def rows(root):
    return {row['path']: row for row in snapshot(root)['records']}


def test_team_is_a_read_alias_and_upgrade_writes_only_unit():
    old = '# Mara\n\n## Facts\n- Team: Founders Program [1]\n'
    upgraded = facts.upgrade(MARA, old)
    assert '- Team:' not in upgraded
    assert facts.parse(old, MARA)['Unit'] == facts.parse(upgraded, MARA)['Unit']
    assert facts.parse(upgraded, MARA)['Unit'][0]['value'] == 'Founders Program'
    assert facts.upgrade(MARA, upgraded) == upgraded


def test_repeatable_units_and_roles_survive_upgrade_and_citation_filter():
    text = ('# Mara\n\n## Facts\n- Unit: [[orgs/course]] [1]\n'
            '- Role in unit: [[orgs/course]] — tutor [1]\n'
            '- Unit: [[orgs/team]] [2]\n- Role in unit: [[orgs/team]] — Product Owner [2]\n')
    new = facts.upgrade(MARA, text)
    assert len(facts.parse(new, MARA)['Unit']) == 2
    assert len(facts.parse(new, MARA)['Role in unit']) == 2
    dropped, labels = facts.drop_uncited(MARA, new.replace('[[orgs/team]] [2]', '[[orgs/team]]'))
    assert labels == ['Unit']
    assert len(facts.parse(dropped, MARA)['Unit']) == 1


def test_hierarchy_membership_rollup_and_unplaced_are_derived(tmp_path):
    book = book_at(tmp_path)
    unit(book, COURSE, 'course', ORG)
    unit(book, TEAM, 'team', COURSE)
    book.write(MARA, f'# Mara\n\n## Facts\n- Company: [[{ORG}]] [1]\n'
               f'- Unit: [[{TEAM}]] [1]\n- Role in unit: [[{TEAM}]] — Product Owner [1]\n'
               '\n## Open threads\n- The user owes Mara: feedback — due 2026-01-01 [1]\n')
    book.write(AVERY, f'# Avery\n\n## Facts\n- Company: [[{ORG}]] [1]\n')
    data = rows(tmp_path)
    assert data[ORG]['kind'] == 'university' and data[ORG]['unit_kind'] == ''
    assert data[TEAM]['kind'] == '' and data[TEAM]['unit_kind'] == 'team'
    assert data[TEAM]['parent'] == COURSE and data[TEAM]['depth'] == 2
    assert data[ORG]['children'] == [COURSE]
    assert data[ORG]['unplaced']['people'] == [AVERY]
    assert data[MARA]['units'] == [{'path': TEAM, 'role': 'Product Owner'}]
    assert data[TEAM]['rollup'] == {'open_owed': 1, 'people': 1, 'overdue': 1}
    assert data[ORG]['rollup'] == {'open_owed': 1, 'people': 2, 'overdue': 1}
    assert data[TEAM]['people'] == [MARA]


def test_obligation_unit_metadata_routes_only_that_obligation(tmp_path):
    book = book_at(tmp_path)
    unit(book, COURSE, 'course', ORG)
    unit(book, TEAM, 'team', COURSE)
    book.write(ORG, book.read(ORG) + '\n## Open threads\n'
               '- The user owes Fernhill University: feedback — due 2026-01-01 [1]\n'
               f'  - Unit: [[{TEAM}]] [1]\n'
               '- Fernhill University owes the user: agreement [2]\n')
    data = rows(tmp_path)
    assert len(data[ORG]['obligations']) == 2
    assert len(data[TEAM]['obligations']) == 1
    assert data[TEAM]['obligations'][0]['units'] == [TEAM]
    assert len(data[ORG]['unplaced']['obligations']) == 1
    assert data[ORG]['rollup']['open_owed'] == 1


@pytest.mark.parametrize('parents', [
    {COURSE: TEAM, TEAM: COURSE}, {COURSE: 'orgs/missing.md'},
    {COURSE: ORG + ']] [1]; [[' + TEAM}, {COURSE: COURSE},
])
def test_bad_parents_never_create_a_tree_or_loop(tmp_path, parents):
    book = book_at(tmp_path)
    for path, parent in parents.items():
        unit(book, path, 'team', parent)
    data = rows(tmp_path)
    assert data[COURSE]['parent'] == '' and data[COURSE]['depth'] is None
    assert data[COURSE]['hierarchy_issues']


def test_cited_you_are_and_web_provenance(tmp_path):
    book = book_at(tmp_path)
    unit(book, COURSE, 'course', ORG)
    book.write(COURSE, book.read(COURSE) + '- You are: client [2]\n\n## Sources\n'
               '- [1] https://fernhill.example/structure — web-sourced\n- [2] gmail:terms\n')
    data = rows(tmp_path)
    assert data[COURSE]['you_are'] == 'client'
    assert data[COURSE]['structure_source'] == 'web'


def test_flat_and_free_text_team_do_not_invent_units(tmp_path):
    book = book_at(tmp_path)
    book.write(MARA, f'# Mara\n\n## Facts\n- Company: [[{ORG}]] [1]\n- Team: Unknown team [1]\n')
    data = rows(tmp_path)
    assert data[ORG]['children'] == [] and data[ORG]['depth'] == 0
    assert data[MARA]['units'] == []
    assert data[ORG]['unplaced']['people'] == [MARA]


def test_rollup_dedupes_people_in_two_units_and_copied_obligations(tmp_path):
    book = book_at(tmp_path)
    unit(book, COURSE, 'course', ORG)
    unit(book, TEAM, 'team', COURSE)
    promise = '- The user owes Mara: feedback — due 2026-01-01 [1]\n'
    book.write(MARA, f'# Mara\n\n## Facts\n- Unit: [[{COURSE}]] [1]; [[{TEAM}]] [1]\n'
               '\n## Open threads\n' + promise + '\n## Sources\n- [1] gmail:promise\n')
    book.write(TEAM, book.read(TEAM) + '\n## Open threads\n' + promise + '\n## Sources\n- [1] gmail:promise\n')
    data = rows(tmp_path)
    assert data[ORG]['rollup'] == {'open_owed': 1, 'people': 1, 'overdue': 1}
    assert data[MARA]['organisations'] == [ORG]


def test_doctor_names_broken_unit_and_parent_facts(tmp_path):
    from connectonion.rem.tidy import notebook_checks
    book = book_at(tmp_path)
    unit(book, TEAM, 'team', 'orgs/missing.md')
    book.write(MARA, '# Mara\n\n## Facts\n- Unit: [[orgs/missing]] [1]\n')
    checks = [row for row in notebook_checks(tmp_path) if not row['ok']]
    assert any('Parent' in row['fix'] and TEAM in row['detail'] for row in checks)
    assert any('Unit' in row['fix'] and MARA in row['detail'] for row in checks)


def test_repeated_unit_lines_do_not_share_citations_or_hide_values(tmp_path):
    book = book_at(tmp_path)
    unit(book, COURSE, 'course', ORG)
    unit(book, TEAM, 'team', COURSE)
    book.write(MARA, '# Mara\n\n## Facts\n- Unit: [[orgs/course]]\n- Unit: [[orgs/team]] [1]\n')
    assert rows(tmp_path)[MARA]['units'] == [{'path': TEAM, 'role': ''}]
    book.write(MARA, '# Mara\n\n## Facts\n- Unit: Unknown\n- Unit: [[orgs/team]] [1]\n')
    assert rows(tmp_path)[MARA]['units'] == [{'path': TEAM, 'role': ''}]


def test_repeated_parent_lines_are_ambiguous_even_when_both_exist(tmp_path):
    book = book_at(tmp_path)
    unit(book, COURSE, 'course', ORG)
    unit(book, TEAM, 'team', ORG)
    book.write(TEAM, book.read(TEAM) + '- Parent: [[orgs/course]] [1]\n')
    assert rows(tmp_path)[TEAM]['parent'] == ''


def test_unit_metadata_does_not_split_copies_of_the_same_promise(tmp_path):
    book = book_at(tmp_path)
    unit(book, TEAM, 'team', ORG)
    promise = '- The user owes Mara: feedback — due 2026-01-01 [1]\n'
    book.write(ORG, book.read(ORG) + '\n## Open threads\n' + promise + f'  - Unit: [[{TEAM}]] [1]\n'
               '\n## Sources\n- [1] gmail:promise\n')
    book.write(MARA, '# Mara\n\n## Facts\n- Company: [[orgs/fernhill]] [1]\n\n## Open threads\n' + promise +
               '\n## Sources\n- [1] gmail:promise\n')
    data = rows(tmp_path)
    assert len(data[ORG]['obligations']) == 1
    assert data[ORG]['rollup']['open_owed'] == 1


def test_plain_roles_stay_paired_when_upgrade_reorders_fields(tmp_path):
    book = book_at(tmp_path)
    unit(book, COURSE, 'course', ORG)
    unit(book, TEAM, 'team', COURSE)
    text = ('# Mara\n\n## Facts\n- Unit: [[orgs/course]] [1]\n- Role in unit: tutor [1]\n'
            '- Unit: [[orgs/team]] [2]\n- Role in unit: Product Owner [2]\n')
    book.write(MARA, facts.upgrade(MARA, text))
    assert rows(tmp_path)[MARA]['units'] == [{'path': COURSE, 'role': 'tutor'}, {'path': TEAM, 'role': 'Product Owner'}]


def test_invalid_explicit_unit_does_not_fall_back_to_some_other_membership(tmp_path):
    book = book_at(tmp_path)
    unit(book, TEAM, 'team', ORG)
    book.write(MARA, '# Mara\n\n## Facts\n- Unit: [[orgs/team]] [1]\n\n## Open threads\n'
               '- The user owes Mara: feedback [1]\n  - Unit: [[orgs/missing]] [1]\n')
    assert rows(tmp_path)[TEAM]['rollup']['open_owed'] == 0


def test_unit_structure_citation_cannot_merge_distinct_promises(tmp_path):
    book = book_at(tmp_path)
    unit(book, TEAM, 'team', ORG)
    promise = '- The user owes Mara: feedback [1]\n  - Unit: [[orgs/team]] [2]\n'
    book.write(ORG, book.read(ORG) + '\n## Open threads\n' + promise +
               '\n## Sources\n- [1] gmail:promise-a\n- [2] gmail:structure\n')
    book.write(MARA, '# Mara\n\n## Facts\n- Company: [[orgs/fernhill]] [2]\n\n## Open threads\n' + promise +
               '\n## Sources\n- [1] gmail:promise-b\n- [2] gmail:structure\n')
    assert len(rows(tmp_path)[ORG]['obligations']) == 2


def test_disjoint_explicit_unit_scopes_do_not_merge(tmp_path):
    book = book_at(tmp_path)
    unit(book, COURSE, 'course', ORG)
    unit(book, TEAM, 'team', ORG)
    promise = '- The user owes Mara: feedback [1]\n'
    book.write(ORG, book.read(ORG) + '\n## Open threads\n' + promise + f'  - Unit: [[{COURSE}]] [1]\n' +
               promise + f'  - Unit: [[{TEAM}]] [1]\n\n## Sources\n- [1] gmail:promises\n')
    assert len(rows(tmp_path)[ORG]['obligations']) == 2


@pytest.mark.parametrize('label', ['[personal]', '[sensitive]'])
def test_a_labelled_tie_on_the_persons_own_page_does_not_place_them_in_the_org(tmp_path, label):
    # Once a labelled passage stopped curtaining the whole organisation, a person whose only tie
    # was a labelled Company or Unit line on their own page appeared among the people you know there.
    book = book_at(tmp_path)
    unit(book, TEAM, 'team', ORG)
    book.write(MARA, f'# Mara\n\n## Facts\n- Company: [[{ORG}]] [1]\n')
    book.write(AVERY, f'# Avery\n\n## Facts\n- Company: [[{ORG}]] met at the clinic {label} [1]\n'
               f'- Unit: [[{TEAM}]] {label} [1]\n- Role in unit: [[{TEAM}]] — patient liaison {label} [1]\n')
    data = rows(tmp_path)
    assert data[ORG]['people'] == [MARA]
    assert data[TEAM]['people'] == []
    assert data[AVERY]['organisations'] == [] and data[AVERY]['units'] == []
    assert AVERY not in data[ORG]['unplaced']['people']
    # Nor does the labelled line draw an edge on the map or the org's local graph.
    edges = {(e['source'], e['target']) for e in snapshot(tmp_path)['graph']['edges']}
    assert (ORG, AVERY) not in edges and (TEAM, AVERY) not in edges and (ORG, MARA) in edges
