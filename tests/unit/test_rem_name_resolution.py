"""A name can offer candidates; only an unambiguous selector can choose one."""

import pytest
from typer.testing import CliRunner

from connectonion.cli.commands.rem_commands import _resolve_page
from connectonion.cli.main import app
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError, state_path, write_json
from connectonion.rem.page_review import link_people, person_names
from connectonion.rem.reader_model import relationships


@pytest.fixture
def notebook(tmp_path):
    prepare(tmp_path)
    nb = Notebook(tmp_path)
    for suffix in ('a', 'b'):
        nb.write(f'people/aster-{suffix}.md', '# Aster Vale\n\n## Facts\n'
                 f'- Email: aster.{suffix}@example.com\n- Also known as: Aster\n\n'
                 f'## History\n- Distinct finding {suffix}.\n')
    return nb


@pytest.mark.parametrize('query', ['Aster', 'Aster Vale', 'ASTER VALE'])
def test_show_lists_candidates_with_emails_and_shows_neither_page(notebook, query):
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook.root), 'show', query])
    assert result.exit_code != 0
    for suffix in ('a', 'b'):
        assert f'people/aster-{suffix}.md' in result.output
        assert f'aster.{suffix}@example.com' in result.output
        assert f'Distinct finding {suffix}' not in result.output


@pytest.mark.parametrize('query', ['aster.b@example.com', 'people/aster-b.md'])
def test_show_exact_address_or_path_selects_only_that_page(notebook, query):
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook.root), 'show', query])
    assert result.exit_code == 0, result.output
    assert 'Distinct finding b' in result.output
    assert 'Distinct finding a' not in result.output


def test_general_page_resolver_refuses_duplicate_person_names(notebook):
    with pytest.raises(RemError, match='More than one page matches') as error:
        _resolve_page(notebook, 'Aster Vale')
    assert all(f'people/aster-{suffix}.md' in str(error.value) for suffix in ('a', 'b'))


@pytest.mark.parametrize('current_name', [False, True])
def test_merged_stem_must_not_choose_a_person_before_other_matches(notebook, current_name):
    aliases = {'people/old/aster.md': {'into': 'people/aster-a.md'}}
    if current_name:
        notebook.write('people/aster-b.md', '# aster\n\n## Facts\n- Email: aster.b@example.com\n')
    else:
        aliases['people/other/aster.md'] = {'into': 'people/aster-b.md'}
    write_json(state_path(notebook.root, 'aliases.json'), aliases)
    with pytest.raises(RemError, match='More than one page matches') as error:
        _resolve_page(notebook, 'aster')
    assert all(f'people/aster-{suffix}.md' in str(error.value) for suffix in ('a', 'b'))
    assert _resolve_page(notebook, 'people/old/aster.md') == 'people/aster-a.md'


def test_mention_hints_do_not_bind_duplicate_names(notebook):
    rows = [{'path': path, 'category': 'people', 'title': 'Aster Vale', 'text': notebook.read(path)}
            for path in notebook.list('people')]
    rows.append({'path': 'projects/pilot.md', 'category': 'projects', 'title': 'Pilot',
                 'text': '# Pilot\n\nAster Vale will review it.\n'})
    assert relationships(rows)['projects/pilot.md'] == []


def test_automatic_person_links_do_not_resolve_case_variant_duplicate_names(notebook):
    notebook.write('people/aster-b.md', '# ASTER VALE\n\n## Facts\n- Email: aster.b@example.com\n')
    text = '# Pilot\n\nAster Vale will review it.\n'
    assert link_people('projects/pilot.md', text, person_names(notebook)) == text


@pytest.mark.parametrize('other_title', ['Aster Vale', 'ASTER'])
def test_first_name_link_inference_must_not_bypass_name_ambiguity(notebook, other_title):
    notebook.write('people/first.md', '# Aster\n\n## Facts\n- Email: astervale@example.com\n')
    notebook.write('people/aster-b.md', f'# {other_title}\n\n## Facts\n- Email: aster.b@example.com\n')
    text = '# Pilot\n\nAster Vale will review it.\n'
    # Full-name pages are ambiguous in the first case; a unique full name remains direct in the second.
    expected = text if other_title == 'Aster Vale' else text.replace('Aster Vale', '[Aster Vale](../people/aster-a.md)')
    assert link_people('projects/pilot.md', text, person_names(notebook)) == expected


def test_case_variant_first_name_pages_do_not_infer_a_full_name(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.write('people/a.md', '# Aster\n\n## Facts\n- Email: astervale@example.com\n')
    notebook.write('people/b.md', '# ASTER\n\n## Facts\n- Email: aster.other@example.com\n')
    text = '# Pilot\n\nAster Vale will review it.\n'
    assert link_people('projects/pilot.md', text, person_names(notebook)) == text


def test_qualified_duplicate_full_name_is_not_safe_to_link(notebook):
    notebook.write('people/aster-b.md', '# Aster Vale (work)\n\n## Facts\n- Email: aster.b@example.com\n')
    text = '# Pilot\n\nAster Vale will review it.\n'
    assert link_people('projects/pilot.md', text, person_names(notebook)) == text


def test_automatic_links_must_count_existing_alias_matches(notebook):
    notebook.write('people/aster-b.md', '# Nova Reed\n\n## Facts\n'
                   '- Email: nova@example.com\n- Also known as: Aster Vale\n')
    assert len(notebook.find_people('Aster Vale')) == 2
    text = '# Pilot\n\nAster Vale will review it.\n'
    assert link_people('projects/pilot.md', text, person_names(notebook)) == text


def test_owner_exclusion_must_not_make_another_same_named_person_unique(notebook):
    text = '# Pilot\n\nAster Vale will review it.\n'
    assert link_people('projects/pilot.md', text, person_names(notebook, owner='people/aster-a.md')) == text


@pytest.mark.parametrize('title, detail', [
    ('Aster Vale (work)', ''),
    ('Nova Reed', '- Also known as: Aster Vale\n'),
])
def test_relationship_hints_do_not_bypass_qualified_or_alias_ambiguity(title, detail):
    rows = [{'path': 'people/a.md', 'category': 'people', 'title': 'Aster Vale', 'text': '# Aster Vale\n'},
            {'path': 'people/b.md', 'category': 'people', 'title': title, 'text': f'# {title}\n\n## Facts\n{detail}'},
            {'path': 'projects/pilot.md', 'category': 'projects', 'title': 'Pilot',
             'text': '# Pilot\n\nAster Vale will review it.\n'}]
    assert relationships(rows)['projects/pilot.md'] == []


def test_general_resolver_does_not_treat_a_qualified_duplicate_as_unique(notebook):
    notebook.write('people/aster-b.md', '# Aster Vale (work)\n\n## Facts\n- Email: aster.b@example.com\n')
    with pytest.raises(RemError, match='More than one page matches'):
        _resolve_page(notebook, 'Aster Vale')


@pytest.mark.parametrize('title, detail', [
    ('Aster Vale', ''), ('Aster Vale (work)', ''),
    ('Nova Reed', '- Also known as: Aster Vale\n'),
])
def test_session_followup_links_do_not_choose_an_ambiguous_person(notebook, title, detail):
    from connectonion.rem.sessions import _followup_lines
    notebook.write('people/aster-b.md', f'# {title}\n\n## Facts\n{detail}')
    assert _followup_lines({'followups': ['Ask Aster Vale to review it.']}, notebook) == [
        '- Ask Aster Vale to review it.']


def test_session_followup_does_not_choose_between_identical_qualified_titles(notebook):
    from connectonion.rem.sessions import _followup_lines
    for path in notebook.list('people'):
        notebook.write(path, '# Aster Vale (work)\n\n## Facts\n- Email: fictional@example.com\n')
    assert _followup_lines({'followups': ['Ask Aster Vale (work) to review it.']}, notebook) == [
        '- Ask Aster Vale (work) to review it.']
