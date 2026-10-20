"""Organisation candidates the map writes, from people pages; no model."""

import pytest

from connectonion.rem.files import Notebook
from connectonion.rem.org_map import map_orgs


def _record_for(kind, key, name):
    return f"{kind}/{key.replace('.', '-')}.md"


def test_a_domain_whose_only_correspondents_are_automated_or_one_way_gets_no_page(tmp_path):
    """2026-10-20: an events platform got an org page from sign-in codes and registrations alone."""
    notebook = Notebook(tmp_path)
    people = [
        {"address": "codes@eventsdesk.example", "record": "people/events-codes.md", "automated_hint": True},
        {"address": "hosts@eventsdesk.example", "record": "people/events-hosts.md", "one_way": True},
        {"address": "mia.chen@harbour.example", "record": "people/mia-chen.md"},
    ]
    rows, created = map_orgs(notebook, people, "2026-10-20", 180, _record_for)
    assert [row["domain"] for row in rows] == ["harbour.example"]
    assert created == ["orgs/harbour-example.md"]


def test_one_real_correspondent_keeps_the_domain(tmp_path):
    notebook = Notebook(tmp_path)
    people = [
        {"address": "codes@eventsdesk.example", "record": "people/events-codes.md", "automated_hint": True},
        {"address": "theo.park@eventsdesk.example", "record": "people/theo-park.md"},
    ]
    rows, _ = map_orgs(notebook, people, "2026-10-20", 180, _record_for)
    assert [row["domain"] for row in rows] == ["eventsdesk.example"]
    assert rows[0]["people"] == ["people/events-codes.md", "people/theo-park.md"]


def test_owner_domain_gets_a_company_page_even_without_another_correspondent(tmp_path):
    notebook = Notebook(tmp_path)
    owner = {'record': 'people/avery.md', 'addresses': ['avery.lin@example.ai']}
    notebook.stub_person(owner['record'], 'Avery Lin', email=owner['addresses'][0])
    notebook.write(owner['record'], notebook.read(owner['record']) + '\n- Company: Example\n')
    rows, created = map_orgs(notebook, [], '2026-10-20', 180, _record_for, owner)
    assert rows[0]['domain'] == 'example.ai' and rows[0]['own'] is True
    assert created == ['orgs/example-ai.md']
    assert notebook.path(created[0]).is_file()


def test_company_named_on_owner_page_keeps_a_notice_only_domain(tmp_path):
    notebook = Notebook(tmp_path)
    owner = {'record': 'people/avery.md', 'addresses': ['avery.lin@gmail.com']}
    notebook.write(owner['record'], '# Avery Lin\n\n- Company: Example\n')
    people = [{'address': 'notices@example.ai', 'record': None}]
    rows, created = map_orgs(notebook, people, '2026-10-20', 180, _record_for, owner)
    assert rows[0]['own'] is True and created == ['orgs/example-ai.md']


@pytest.mark.parametrize('domain,company', [
    ('student.example.edu.au', 'Example University'), ('example.edu', 'Example'),
    ('example.ac.uk', 'Example'), ('bigcorp.example', 'Mara Labs'), ('gmail.com', 'Gmail'),
])
def test_sending_address_does_not_make_an_organisation_owned(tmp_path, domain, company):
    notebook = Notebook(tmp_path)
    owner = {'record': 'people/avery.md', 'addresses': [f'avery@{domain}']}
    notebook.write(owner['record'], f'# Avery Lin\n\n- Company: {company}\n')
    rows, created = map_orgs(notebook, [], '2026-10-20', 180, _record_for, owner)
    assert rows == created == []
    people = [{'address': f'mara@{domain}', 'record': 'people/mara.md'}]
    rows, _ = map_orgs(notebook, people, '2026-10-20', 180, _record_for, owner)
    assert all('own' not in row for row in rows)
    assert bool(rows) == (domain != 'gmail.com')


@pytest.mark.parametrize('field', [
    '- Organisation: [Mara Labs Pty Ltd](../orgs/mara.md) [1]',
    '- Website: https://www.maralabs.example/about',
    '- Website: [Mara](https://www.maralabs.example/about) [1]',
])
def test_owned_project_identifies_company_with_unknown_company_field(tmp_path, field):
    notebook = Notebook(tmp_path)
    owner = {'record': 'people/avery.md', 'addresses': ['avery@maralabs.example']}
    notebook.write(owner['record'], '# Avery Lin\n\n- Company: Unknown\n')
    notebook.write('projects/mara.md', '# Mara\n\n' + field + '\n')
    rows, created = map_orgs(notebook, [], '2026-10-20', 180, _record_for, owner)
    assert rows[0]['own'] is True and created == ['orgs/maralabs-example.md']


@pytest.mark.parametrize('field', ['Company', 'Signing entity'])
def test_company_name_uses_legal_suffix_and_markdown_normalisation(field):
    from connectonion.rem.org_map import own_company
    assert own_company('mail.maralabs.example', f'- {field}: [Mara Labs Pty Ltd](mara.md) [1]', [])


@pytest.mark.parametrize('domain', ['example.edu.au', 'example.edu', 'example.ac.uk', 'gmail.com'])
def test_project_website_cannot_make_academic_or_webmail_domains_owned(domain):
    from connectonion.rem.org_map import own_company
    assert not own_company(domain, '- Company: Example\n', [f'- Website: https://{domain}\n'])
