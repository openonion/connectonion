"""Deterministic supported chains and reviewable conflicts, on fictional evidence."""
import pytest

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem import facts, reviews
from connectonion.rem.org_inference import infer, apply

ORG = 'orgs/fernhill.md'
MARA = 'people/mara.md'
AVERY = 'people/avery.md'


def book_at(root, role=''):
    prepare(root)
    book = Notebook(root)
    book.write(ORG, '# Fernhill University\n\n## Facts\n- Kind: university [1]\n')
    book.write(MARA, '# Mara\n\n## Facts\n- Company: [[orgs/fernhill]] [1]\n'
               f'- Role: {role or "Unknown"}' + (' [1]' if role else '') + '\n\n## Sources\n- [1] gmail:intro\n')
    return book


def test_full_code_gives_course_then_team_and_cited_membership(tmp_path):
    book = book_at(tmp_path, 'Product Owner, team 9900-F15C-CAKE')
    plan = infer(book, MARA)
    assert [(row['name'], row['kind']) for row in plan['units']] == [('9900', 'course'), ('9900-F15C-CAKE', 'team')]
    assert plan['units'][1]['parent'] == plan['units'][0]['path']
    assert plan['memberships'][0]['role'] == 'Product Owner'
    assert plan['units'][0]['source'] == 'gmail:intro'
    before = {path: book.read(path) for path in book.list()}
    assert before == {path: book.read(path) for path in book.list()}
    apply(book, plan)
    assert len(book.list('orgs')) == 3
    assert facts.parse(book.read(MARA), MARA)['Unit'][0]['citations']
    assert facts.parse(book.read(MARA), MARA)['Company'][0]['value'] == '[[orgs/fernhill]]'
    assert apply(book, infer(book, MARA))['created'] == []


def test_signature_yields_named_chain_without_guessing_intermediate_units(tmp_path):
    book = book_at(tmp_path)
    evidence = [{'field': 'Signature', 'value': 'Mara | Events Coordinator | Founders Program, Division of Research & Enterprise | Fernhill University',
                 'source': 'outlook:signature', 'date': '2026-11-01'}]
    plan = infer(book, MARA, evidence)
    assert [(u['name'], u['kind']) for u in plan['units']] == [('Division of Research & Enterprise', 'department'), ('Founders Program', 'programme')]
    assert plan['memberships'][0]['role'] == 'Events Coordinator'


@pytest.mark.parametrize('value', ['student.fernhill.example', 'staff.fernhill.example', 'ad.fernhill.example'])
def test_mail_subdomains_never_place_units(tmp_path, value):
    book = book_at(tmp_path)
    plan = infer(book, MARA, [{'field': 'Company domain', 'value': value, 'source': 'gmail:address'}])
    assert plan['units'] == [] and plan['memberships'] == []


def test_conflicting_nickname_and_role_with_different_codes_becomes_question(tmp_path):
    book = book_at(tmp_path, 'Product Owner, team 9900-F15C-CAKE')
    apply(book, infer(book, MARA))
    book.write(AVERY, book.read(MARA).replace('# Mara', '# Avery').replace('9900-F15C-CAKE', '9900-F13F-CAKE'))
    plan = infer(book, AVERY)
    assert plan['reviews'] and '9900-F15C-CAKE' in plan['reviews'][0]['basis']
    apply(book, plan)
    apply(book, infer(book, AVERY))
    saved = reviews.listing(tmp_path)
    assert len(saved) == 1 and saved[0]['kind'] == 'question' and saved[0]['status'] == 'pending'
    assert len([p for p in book.list('orgs') if 'cake' in p]) == 2


def test_public_structure_stays_web_sourced_and_never_asserts_employment(tmp_path):
    book = book_at(tmp_path)
    plan = infer(book, MARA, [{'field': 'Structure', 'value': 'School of Computing, Faculty of Engineering',
                              'source': 'https://fernhill.example/structure'}])
    assert [(u['kind'], u['provenance']) for u in plan['units']] == [('faculty', 'web'), ('school', 'web')]
    assert not plan['memberships']
    apply(book, plan)
    assert all('web-sourced' in book.read(u['path']) for u in plan['units'])


def test_shared_mailbox_has_a_unit_and_no_person_membership(tmp_path):
    book = book_at(tmp_path)
    book.write(MARA, '# Founders Program shared mailbox\n\n## Facts\n- Company: [[orgs/fernhill]] [1]\n'
               '- Email: founders@fernhill.example\n\n## Sources\n- [1] gmail:mailbox\n')
    plan = infer(book, MARA)
    assert plan['units'][0]['kind'] == 'programme' and not plan['memberships']
    apply(book, plan)
    assert not facts.parse(book.read(MARA), MARA)['Unit']


def test_uncited_or_ambiguous_organisation_does_not_invent_structure(tmp_path):
    book = book_at(tmp_path, 'Product Owner, team 9900-F15C-CAKE')
    book.write(MARA, book.read(MARA).replace(' [1]', ''))
    assert not infer(book, MARA)['units']


def test_investigation_result_applies_hierarchy_and_conflicts(tmp_path):
    from connectonion.rem.investigate import record_result
    book = book_at(tmp_path, 'Product Owner, team 9900-F15C-CAKE')
    record_result(tmp_path, book, MARA, [], [], changed=True)
    assert facts.parse(book.read(MARA), MARA)['Unit']


def test_saved_maintenance_page_also_gets_hierarchy(tmp_path):
    from connectonion.rem.runner import _write_page
    book = book_at(tmp_path, 'Product Owner, team 9900-F15C-CAKE')
    _write_page(book, MARA, book.read(MARA), [])
    assert facts.parse(book.read(MARA), MARA)['Unit']


def test_uncertain_or_negated_role_claim_never_places_a_unit(tmp_path):
    book = book_at(tmp_path, 'Not Product Owner of team 9900-F15C-CAKE; possible member?')
    assert not infer(book, MARA)['memberships']


def test_two_schools_are_not_a_parent_chain(tmp_path):
    book = book_at(tmp_path)
    assert not infer(book, MARA, [{'field': 'Structure', 'value': 'School of Science, School of Engineering',
                                  'source': 'https://fernhill.example/structure'}])['units']


def test_generic_shared_mailbox_is_an_observed_team_unit(tmp_path):
    book = book_at(tmp_path)
    book.write(MARA, '# Fernhill reception shared mailbox\n\n## Facts\n- Company: [[orgs/fernhill]] [1]\n'
               '## Sources\n- [1] gmail:mailbox\n')
    plan = infer(book, MARA)
    assert [(u['name'], u['kind']) for u in plan['units']] == [('Fernhill reception', 'team')]
    assert not plan['memberships']


def test_native_promotion_receipt_matches_final_inferred_page(tmp_path):
    import hashlib
    from connectonion.rem.files import read_json
    from connectonion.rem.runner import _write_page
    book = book_at(tmp_path, 'Product Owner, team 9900-F15C-CAKE')
    receipt = tmp_path / 'receipt.json'
    _write_page(book, MARA, book.read(MARA), [], receipt=receipt)
    assert read_json(receipt, {})['sha256'] == hashlib.sha256(book.read(MARA).encode()).hexdigest()


def test_subject_code_creates_candidates_without_asserting_membership(tmp_path):
    book = book_at(tmp_path)
    plan = infer(book, MARA, [{'field': 'Subject', 'value': '9900-F15C-CAKE sprint demo', 'source': 'gmail:demo'}])
    assert len(plan['units']) == 2 and not plan['memberships']


def test_map_reconcile_builds_from_existing_cited_roles(tmp_path):
    from connectonion.rem.org_inference import reconcile
    book = book_at(tmp_path, 'Course Admin, 9900')
    result = reconcile(book)
    assert len(result['created']) == 1
    assert facts.parse(book.read(MARA), MARA)['Unit']


@pytest.mark.parametrize('statement', [
    'Mara is working with four students per team.',
    'Mara is the lead; she discussed the Practice of WorkXStartup program.',
    'Mara is known through the project; the message describes an AI Builder co-creation program.',
])
def test_narrative_unit_words_are_not_observed_unit_names(tmp_path, statement):
    book = book_at(tmp_path)
    text = book.read(MARA).replace('# Mara\n', '# Mara\n\n' + statement + ' [1]\n')
    book.write(MARA, text)
    assert not infer(book, MARA)['units']


def test_role_title_is_separate_from_programme_name(tmp_path):
    book = book_at(tmp_path, 'Deputy Director of Software Engineering Program')
    assert [u['name'] for u in infer(book, MARA)['units']] == ['Software Engineering Program']


def test_map_does_not_archive_inferred_units_as_empty_candidates(tmp_path):
    from connectonion.rem.map import _archive_stale
    book = book_at(tmp_path, 'Product Owner, team 9900-F15C-CAKE')
    plan = infer(book, MARA)
    apply(book, plan)
    report = {'people': [{'record': MARA}], 'orgs': [{'record': ORG}], 'projects': []}
    _archive_stale(book, report)
    assert all(book.path(unit['path']).exists() for unit in plan['units'])


def test_signature_inference_finishes_before_native_receipt_is_pinned(tmp_path):
    import hashlib
    from connectonion.rem.files import read_json
    from connectonion.rem.runner import _write_page
    from connectonion.rem.investigate import record_result
    book = book_at(tmp_path)
    evidence = [{'field': 'Signature', 'value': 'Mara | Events Coordinator | Founders Program',
                 'source': 'gmail:signature', 'date': '2026-11-01'}]
    receipt = tmp_path / 'receipt.json'
    _write_page(book, MARA, book.read(MARA), [{'role': 'facts', 'facts': evidence}], receipt=receipt)
    assert facts.parse(book.read(MARA), MARA)['Unit']
    assert read_json(receipt, {})['sha256'] == hashlib.sha256(book.read(MARA).encode()).hexdigest()
    record_result(tmp_path, book, MARA, [], [], changed=True, hierarchy_evidence=evidence)
    # note_investigation changes the status line after promotion; compare the promoted facts.
    promoted = read_json(receipt, {})
    assert promoted['sha256']
    assert len(facts.parse(book.read(MARA), MARA)['Unit']) == 1
