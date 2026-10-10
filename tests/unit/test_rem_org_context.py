"""Organization conclusions compare primary mail across contact candidates, without identity merges."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256

from connectonion.rem import investigate as inv
from connectonion.rem.config import prepare, set_config
from connectonion.rem.files import Notebook, state_path, write_json
from connectonion.rem.mail_archive import message_path


def _notebook(root):
    prepare(root)
    set_config(root, ['runner', 'codex'])
    book = Notebook(root)
    book.stub_person('people/alex.md', 'Alex', email='alex@first.example, alex@second.example')
    book.stub_person('people/other-alex.md', 'Alex', email='alex@unrelated.example')
    rows = [
        {'record': 'orgs/first.md', 'domain': 'first.example', 'domains': ['first.example'], 'people': ['people/alex.md']},
        {'record': 'orgs/second.md', 'domain': 'second.example', 'domains': ['second.example'], 'people': ['people/alex.md']},
        {'record': 'orgs/unrelated.md', 'domain': 'unrelated.example', 'domains': ['unrelated.example'], 'people': ['people/other-alex.md']},
    ]
    for row in rows:
        book.stub_org(row['record'], 'ExampleCo' if 'unrelated' not in row['record'] else 'OtherCo', row['domains'], row['people'])
    write_json(state_path(root, 'map.json'), {'orgs': rows})
    return book


def _archive(root):
    now = datetime.now(timezone.utc)
    write_json(state_path(root, 'mail/archive.json'), {
        'phase': 'complete', 'providers': ['gmail'], 'owner_addresses': ['me@owner.example'],
        'range_start': (now - timedelta(days=10)).isoformat(), 'range_end': (now + timedelta(minutes=1)).isoformat(),
    })
    rows = [('trial', 'alex@first.example', ['me@owner.example'], [], 5, 'I am ExampleCo co-founder; here is a free month offer.'),
            ('credits', 'alex@second.example', ['me@owner.example'], [], 4, 'I am ExampleCo co-founder; here are credits and the startup tier.'),
            ('accept', 'me@owner.example', ['alex@second.example'], [], 3, 'I accept the credits and startup tier; please arrange a call.'),
            ('cc', 'me@owner.example', [], ['alex@first.example'], 2, 'Please send the meeting link.'),
            ('unrelated', 'stranger@second.example', ['me@owner.example'], [], 1, 'Different contact, no canonical link.'),
            ('spoof', 'stranger@unrelated.example', ['me@owner.example'], [], 1, 'first.example was mentioned in prose.')]
    for key, sender, to, cc, ago, body in rows:
        write_json(message_path(root, 'gmail', key), {'id': key, 'provider': 'gmail', 'date': (now-timedelta(days=ago)).isoformat(),
                   'from': sender, 'to': to, 'cc': cc, 'subject': body, 'body': body})


def test_same_display_name_does_not_expand_organization_context(tmp_path):
    book = _notebook(tmp_path)
    related = inv.org_contact_context(book, 'orgs/first.md')
    assert related['addresses'] == ['alex@second.example']
    assert [row['record'] for row in related['candidates']] == ['orgs/second.md']
    assert inv.org_contact_context(book, 'people/alex.md') == {'domains': [], 'addresses': [], 'candidates': []}


def test_archive_compares_exact_contact_mail_and_cc_without_reading_entire_other_domain(tmp_path):
    _notebook(tmp_path)
    _archive(tmp_path)
    items, _ = inv.gather('ExampleCo', ['first.example', 'alex@second.example'], days=8,
                          clients={}, subscriptions={}, archive_root=tmp_path, record='orgs/first.md')
    assert [item['source'] for item in items] == ['gmail:' + sha256(key.encode()).hexdigest()[:12] for key in ['trial', 'credits', 'accept', 'cc']]
    assert [item['text'] for item in items if item.get('relationship_scope')] == [
        'I am ExampleCo co-founder; here are credits and the startup tier.',
        'I accept the credits and startup tier; please arrange a call.']
    assert all(item['source'].startswith('gmail:') for item in items)


def test_cross_domain_comparison_retains_cited_primary_mail_and_does_not_force_candidate_dates(tmp_path, monkeypatch):
    book = _notebook(tmp_path)
    _archive(tmp_path)
    original, _ = inv.gather('ExampleCo', ['first.example'], days=8, clients={}, subscriptions={},
                             archive_root=tmp_path, record='orgs/first.md')
    first = original[0]
    book.write('orgs/first.md', '# ExampleCo\n\n## Domains\n- first.example [1]\n- second.example — ownership unverified [1]\n\n## Sources\n- [1] '
               + first['source'] + '\nInvestigation: investigated 2026-10-01\n')
    monkeypatch.setattr('connectonion.rem.runner.check_skill', lambda *a: None)
    seen = []
    def runner(notebook, items, config, stage):
        seen.extend(items)
        return {'changed': []}
    inv.investigate(tmp_path, 'orgs/first.md', 'ExampleCo', ['ExampleCo'], days=8,
                    clients={}, subscriptions={}, runner=runner)
    mail = [item for item in seen if item['source'].startswith('gmail:')]
    assert [item['source'] for item in mail] == ['gmail:' + sha256(key.encode()).hexdigest()[:12] for key in ['trial', 'credits', 'accept', 'cc']]
    context = next(item for item in seen if item['role'] == 'org-contact-context')
    assert 'not proof' in context['text'] and 'distinct offers' in context['text']
    facts = [row for item in seen if item['role'] == 'facts' for row in item['facts']]
    assert all(row['source'] not in {item['source'] for item in mail if item.get('relationship_scope')} for row in facts)
    assert not any(row['field'] in ('First contact', 'Last contact') for row in facts)


def test_contact_scope_survives_searchable_evidence_files(tmp_path):
    from connectonion.rem.evidence import write_evidence
    item = {'source': 'gmail:one', 'timestamp': '2026-09-20', 'role': 'user', 'text': 'I accept the credits.',
            'relationship_scope': 'Related contact outside the target mail domains; verify identity.'}
    write_evidence(tmp_path, [item])
    text = next((tmp_path / 'gmail').glob('*.md')).read_text()
    assert item['source'] in text and 'Relationship scope: ' + item['relationship_scope'] in text


def test_server_results_keep_exact_contact_context_and_reject_prose_only_domain_matches():
    when = datetime.now(timezone.utc).isoformat()
    rows = [{'id': 'own', 'from': 'alex@first.example', 'to': ['me@owner.example'], 'date': when},
            {'id': 'context', 'from': 'me@owner.example', 'cc': ['alex@second.example'], 'date': when},
            {'id': 'stranger', 'from': 'stranger@second.example', 'to': [], 'date': when},
            {'id': 'spoof', 'from': 'stranger@unrelated.example', 'subject': 'first.example', 'date': when}]
    class Mail:
        def my_addresses(self): return {'me@owner.example'}
        def list_with(self, term, start, end, **kwargs): return rows
        def get_email_body(self, key): return 'Original body ' + key
    items, _ = inv.gather('ExampleCo', ['first.example', 'alex@second.example'], days=8,
                          clients={'gmail': Mail()}, subscriptions={}, record='orgs/first.md')
    assert [item['text'] for item in items] == ['Original body own', 'Original body context']
    assert not items[0].get('relationship_scope') and items[1]['relationship_scope']


def test_org_prompt_distinguishes_offer_acceptance_from_setup_and_identity():
    from connectonion.rem.runner import instructions
    text = instructions('investigate', page_kind='org')
    assert 'shared page or display name is a lead, not identity proof' in text
    assert 'accepted credits/tier' in text and 'distinct free-month offer' in text
    assert 'Do not merge legal entities' in text
