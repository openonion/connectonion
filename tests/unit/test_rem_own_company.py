"""The owner's company is described by their work, rather than notices to their domain."""

from datetime import datetime, timedelta, timezone

import pytest

from connectonion.rem import investigate as inv
from connectonion.rem.config import prepare, set_config
from connectonion.rem.files import Notebook, state_path, write_json
from connectonion.rem.mail_archive import retain_message


def _notebook(root):
    prepare(root)
    set_config(root, ['runner', 'codex'])
    book = Notebook(root)
    book.write('people/avery.md', '# Avery Lin\n\nAvery builds Example.\n\n## Facts\n- Company: Example\n')
    book.stub_org('orgs/example.md', 'Example', ['example.ai'])
    book.write('projects/example.md', '# Example\n\nThe company platform.\n\n## Paths\n- /work/example\n')
    book.write('projects/mara.md', '# Mara\n\nA product of Example.\n\n## Paths\n- /work/mara\n')
    book.write('projects/mia.md', '# Mia\n\nAn unrelated project.\n\n## Paths\n- /work/mia\n')
    book.write('people/mia.md', '# Mia Chen\n\nA customer.\n\n## Facts\n- Role: Unknown\n')
    book.stub_org('orgs/customer.md', 'Mia', ['example.com'], ['people/mia.md'])
    book.write('orgs/customer.md', '# Mia\n\nA customer organisation.\n\n## Domains\n- example.com\n')
    book.write('orgs/example.md', book.read('orgs/example.md') + '\n## Products\n- Mara\n')
    state = {'owner': {'record': 'people/avery.md', 'addresses': ['avery.lin@gmail.com', 'avery.lin@outlook.com']},
             'possible_own_addresses': [{'address': 'avery.lin@mail.example.ai'}, {'address': 'mia.chen@example.com'}],
             'people': [{'record': 'people/mia.md', 'addresses': ['mia.chen@example.com'], 'mails': 20}],
             'orgs': [{'record': 'orgs/example.md', 'domains': ['example.ai'], 'people': []},
                      {'record': 'orgs/customer.md', 'domains': ['example.com'], 'people': ['people/mia.md']}],
             'automated_correspondents': [{'address': 'billing@example.com'}]}
    write_json(state_path(root, 'map.json'), state)
    return book, state


def _mail(sender, key, recipient='mia.chen@example.com'):
    return {'id': key, 'from': sender, 'to': [recipient], 'subject': 'Our next step',
            'date': (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}


class Mail:
    def __init__(self, address, rows):
        self.address, self.rows = address, rows

    def my_addresses(self):
        return {self.address}

    def list_between(self, start, end, limit):
        return [row for row in self.rows if start <= row['date'] < end]

    def list_with(self, term, start, end, **kwargs):
        return self.list_between(start, end, 200)

    def get_email_body(self, key):
        return 'I will ship Mara and send Mia Chen the deal terms. ' + key


@pytest.mark.parametrize('product', ['Mara', 'Mara [1]', '[Mara](../projects/mara.md) [1]'])
def test_company_uses_owner_sent_mail_sessions_and_context(tmp_path, monkeypatch, product):
    book, _ = _notebook(tmp_path)
    book.write('people/avery.md', book.read('people/avery.md').replace('Company: Example',
               'Company: [Example](../orgs/example.md) [1]'))
    book.write('orgs/example.md', book.read('orgs/example.md').replace('## Products\n- Mara', '## Products\n- ' + product))
    gmail = Mail('avery.lin@gmail.com', [_mail('avery.lin@gmail.com', 'sent'),
                 _mail('avery.lin@mail.example.ai', 'agent'),
                 _mail('billing@example.com', 'receipt', 'avery.lin@mail.example.ai'),
                 _mail('mara@example.ai', 'team', 'avery.lin@gmail.com')])
    outlook = Mail('avery.lin@outlook.com', [_mail('avery.lin@outlook.com', 'deal')])
    sessions = [{'source': f'codex:session{i}:0', 'role': 'user', 'timestamp': '2026-10-20T00:00:00+00:00',
                 'project': path, 'text': 'Ship the next version.'}
                for i, path in enumerate(['/work/example', '/work/mara', '/work/mia'])]
    monkeypatch.setattr(inv, '_window_items', lambda *a: (sessions, 0))
    monkeypatch.setattr(inv, 'website_items', lambda *a, **kw: ([], []))
    monkeypatch.setattr(inv, 'project_mentions', lambda *a: ([], 'project documents: none'))
    monkeypatch.setattr(inv, 'quote_pass', lambda *a: None)
    seen = []

    def runner(notebook, items, config, stage):
        seen.extend(items)
        return {'changed': []}

    result = inv.investigate(tmp_path, 'orgs/example.md', 'Example', [], days=10,
                             clients={'gmail': gmail, 'outlook': outlook},
                             subscriptions={'codex': {'kind': 'codex', 'root': str(tmp_path)}}, runner=runner)
    mail = [item for item in seen if item['source'].split(':')[0] in inv.MAIL_KINDS]
    assert len(mail) == 4
    assert len([item for item in mail if item['role'] == 'user']) == 3
    agent = next(item for item in mail if item['speaker'] == 'avery.lin@mail.example.ai')
    assert agent['role'] == 'user'
    assert not any('receipt' in item['text'] for item in mail)
    assert {item['project'] for item in seen if item['source'].startswith('codex:')} == {'/work/example', '/work/mara'}
    note = next(item for item in seen if item['role'] == 'own-company')['text']
    assert inv.OWN_COMPANY_NOTE in note and 'Owner: Avery Lin' in note
    assert 'avery.lin@mail.example.ai' in note and 'mia.chen@example.com' not in note
    assert 'people/mia.md: A customer.' in note and 'orgs/customer.md: A customer organisation.' in note
    assert 'projects/mia.md: An unrelated project.' in note
    assert "owner's company: written from the owner's sent mail (3 of 3) and sessions (2)" in result['coverage']


def test_possible_own_address_does_not_establish_company_ownership(tmp_path):
    book, _ = _notebook(tmp_path)
    book.write('people/avery.md', '# Avery Lin\n\n## Facts\n- Company: Mara\n')
    owner = inv.company_owner(book, ['example.ai'])
    assert owner == {}
    assert inv.company_owner(book, ['example.com']) == {}


def test_company_context_keeps_fifteen_busiest_pages_and_excludes_owner_agents(tmp_path):
    book, state = _notebook(tmp_path)
    book.write('people/agent.md', '# Avery Lin\n\nThe owner’s agent.\n\n## Facts\n')
    state['possible_own_addresses'][0]['record'] = 'people/agent.md'
    state['people'].append({'record': 'people/agent.md', 'mails': 1000})
    for i in range(16):
        record = f'people/mia-{i}.md'
        book.write(record, '# Mia Chen\n\nA customer lead.\n\nA later paragraph.\n\n## Facts\n')
        state['people'].append({'record': record, 'mails': 100 - i})
    write_json(state_path(tmp_path, 'map.json'), state)
    context = inv.company_context(book, 'orgs/example.md', inv.company_owner(book, ['example.ai']))
    assert sum(line.startswith('people/') for line in context.splitlines()) == 15
    assert 'people/mia-0.md: A customer lead.' in context and 'people/mia-15.md' not in context
    assert 'people/agent.md' not in context and 'A later paragraph.' not in context
    assert all(project in context for project in ('projects/example.md', 'projects/mara.md', 'projects/mia.md'))


def test_archived_agent_sent_mail_is_owner_evidence_without_a_connected_mailbox(tmp_path, monkeypatch):
    book, state = _notebook(tmp_path)
    now = datetime.now(timezone.utc)
    write_json(state_path(tmp_path, 'mail/archive.json'), {
        'phase': 'complete', 'providers': ['gmail'], 'owner_addresses': state['owner']['addresses'],
        'range_start': (now - timedelta(days=20)).isoformat(), 'range_end': (now + timedelta(minutes=1)).isoformat()})
    retain_message(tmp_path, 'gmail', _mail('avery.lin@mail.example.ai', 'agent'), 'I will ship Mara.',
                   fetched_at=now.isoformat())
    items, coverage = inv.company_material(book, inv.company_owner(book, ['example.ai']), [], record='orgs/example.md', days=10,
                                           clients={}, subscriptions={}, archive_root=tmp_path)
    assert len(items) == 1 and items[0]['role'] == 'user' and items[0]['text'] == 'I will ship Mara.'
    assert "owner's company: written from the owner's sent mail (1 of 1) and sessions (0)" in coverage


def test_ordinary_org_does_not_gather_owner_mail_or_get_company_note(tmp_path, monkeypatch):
    book, _ = _notebook(tmp_path)
    book.write('people/avery.md', '# Avery Lin\n\n## Facts\n- Company: Mara\n')
    calls, seen = [], []

    def gather(*args, **kwargs):
        calls.append(kwargs)
        return ([{'source': 'gmail:one', 'role': 'other', 'speaker': 'mia.chen@example.com',
                  'timestamp': '2026-10-20T00:00:00+00:00', 'text': 'Here are the deal terms.'}], ['gmail: 1 read'])

    monkeypatch.setattr(inv, 'gather', gather)
    monkeypatch.setattr(inv, 'website_items', lambda *a, **kw: ([], []))
    monkeypatch.setattr(inv, 'project_mentions', lambda *a: ([], 'project documents: none'))
    monkeypatch.setattr(inv, 'quote_pass', lambda *a: None)

    def runner(notebook, items, config, stage):
        seen.extend(items)
        return {'changed': []}

    inv.investigate(tmp_path, 'orgs/customer.md', 'Mia', [], days=10, clients={}, subscriptions={}, runner=runner)
    assert len(calls) == 1 and calls[0]['sent_only'] is False
    assert not any(item['role'] == 'own-company' for item in seen)
