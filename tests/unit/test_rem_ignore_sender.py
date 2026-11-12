"""忽略 can stop a sender: a line in the notebook keeps their mail out of Today and out of the night's drafts."""
import json
from datetime import date

from tests.unit.test_rem_live_reader import call, host  # noqa: F401
from connectonion.rem import drafts, threads, today
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json
from connectonion.rem.mail_archive import retain_message
from connectonion.rem.store import refresh

OWNER = 'avery@example.test'
SHOP = 'deals@mail.shop.example.test'  # a company's sending subdomain: bulk mail


def test_an_ignored_sender_is_one_dated_line_and_undo_removes_it(tmp_path, rem_clock):
    prepare(tmp_path)
    threads.ignore_sender(tmp_path, 'Deals@Shop.Example.test')
    threads.ignore_sender(tmp_path, 'deals@shop.example.test')
    threads.ignore_sender(tmp_path, 'news@paper.example.test')
    assert threads.ignored_senders(tmp_path) == {'deals@shop.example.test': '2026-09-07', 'news@paper.example.test': '2026-09-07'}
    lines = state_path(tmp_path, 'ignored-senders.txt').read_text().splitlines()
    # Readable and editable by hand: a comment that says what the file is, then one date and address per line.
    assert lines[0].startswith('#') and 'One per line' in lines[1]
    assert [line for line in lines if not line.startswith('#')] == ['2026-09-07 deals@shop.example.test', '2026-09-07 news@paper.example.test']
    threads.ignore_sender(tmp_path, 'deals@shop.example.test', ignored=False)
    assert threads.ignored_senders(tmp_path) == {'news@paper.example.test': '2026-09-07'}


def _notebook(root):
    prepare(root)
    write_json(state_path(root, 'map.json'), {'owner': {'record': 'people/avery.md', 'addresses': [OWNER]}})
    Notebook(root).write('orgs/shop.md', '# Shop\n\n## Open threads\n- You owe Shop a reply about the spring sale. [1]\n\n'
                         '## Sources\n- [1] gmail:sale\n')
    Notebook(root).write('people/mara.md', '# Mara\n\n## Open threads\n- You owe Mara a reply about the venue. [1]\n\n'
                         '## Sources\n- [1] gmail:venue\n')
    for identity, sender, thread in [('sale', SHOP, 'sale'), ('venue', 'mara@example.test', 'venue')]:
        retain_message(root, 'gmail', {'id': identity, 'from': sender, 'to': [OWNER], 'thread': thread,
                                       'subject': thread, 'date': '2026-11-06T03:00:00+00:00'},
                       'Could you reply?', fetched_at='2026-11-08T00:00:00+00:00')
    refresh(root)


def test_today_leaves_out_every_item_from_an_ignored_sender_and_names_each_rows_sender(tmp_path, rem_clock):
    _notebook(tmp_path)
    rows = today.queue(tmp_path, as_of=date(2026, 11, 8))
    # The shop's bulk address is offered; Mara looks like a person, so her address is never offered.
    assert {row['record']: row['sender'] for row in rows} == {'orgs/shop.md': SHOP, 'people/mara.md': ''}
    threads.ignore_sender(tmp_path, SHOP)
    assert [row['record'] for row in today.queue(tmp_path, as_of=date(2026, 11, 8))] == ['people/mara.md']
    threads.ignore_sender(tmp_path, SHOP, ignored=False)
    assert len(today.queue(tmp_path, as_of=date(2026, 11, 8))) == 2


def test_the_night_drafts_no_reply_to_an_ignored_sender(tmp_path, rem_clock):
    _notebook(tmp_path)
    assert {row['to'] for row in drafts.candidates(tmp_path)} == {SHOP, 'mara@example.test'}
    threads.ignore_sender(tmp_path, SHOP)
    assert {row['to'] for row in drafts.candidates(tmp_path)} == {'mara@example.test'}


def test_rem_sender_endpoint_has_the_thread_routes_gates_and_undo(host):
    payload = json.dumps({'address': 'deals@shop.example.test', 'ignored': True}).encode()
    cookie = f'co_rem={host.token}'
    assert call(host.routes, 'POST', '/rem/sender', body=payload)[0] == 401
    assert call(host.routes, 'POST', '/rem/sender', cookie=cookie, body=payload, content_type='text/plain')[0] == 415
    for kwargs in ({'client': '192.168.1.2'}, {'host_header': 'evil.test'}):
        assert call(host.routes, 'POST', '/rem/sender', cookie=cookie, body=payload, **kwargs)[0] == 404
    status, _, body = call(host.routes, 'POST', '/rem/sender', cookie=cookie, body=payload)
    assert status == 200 and list(json.loads(body)['ignored']) == ['deals@shop.example.test']
    assert 'deals@shop.example.test' in state_path(host.root, 'ignored-senders.txt').read_text()
    undo = json.dumps({'address': 'deals@shop.example.test', 'ignored': False}).encode()
    assert call(host.routes, 'POST', '/rem/sender', cookie=cookie, body=undo)[0] == 200
    assert threads.ignored_senders(host.root) == {}
    for value in ({'address': 'not an address', 'ignored': True}, {'address': 'a@b.test'}, {}, [],
                  {'address': 'a@b.test\n2026-01-01 c@d.test', 'ignored': True}):
        assert call(host.routes, 'POST', '/rem/sender', cookie=cookie, body=json.dumps(value).encode())[0] == 400


def test_a_relay_that_carries_peoples_messages_is_never_a_sender_to_ignore(tmp_path, rem_clock, monkeypatch):
    # Many people write through one relay address; ignoring it would silence every one of them.
    import re
    monkeypatch.setattr('connectonion.rem.map.RELAY', re.compile(r'^relay@stays\.example$'))
    prepare(tmp_path)
    write_json(state_path(tmp_path, 'map.json'), {'owner': {'record': 'people/avery.md', 'addresses': [OWNER]}})
    Notebook(tmp_path).write('people/ivo.md', '# Ivo\n\n## Open threads\n- You owe Ivo a call time. [1]\n\n'
                             '## Sources\n- [1] gmail:relayed\n')
    retain_message(tmp_path, 'gmail', {'id': 'relayed', 'from': 'relay@stays.example', 'to': [OWNER], 'thread': 'relayed',
                                       'subject': 'relayed', 'date': '2026-11-06T03:00:00+00:00'},
                   'Which day suits?', fetched_at='2026-11-08T00:00:00+00:00')
    refresh(tmp_path)
    assert [row['sender'] for row in today.queue(tmp_path, as_of=date(2026, 11, 8))] == ['']


def test_ignored_is_its_own_thread_state_that_leaves_today_like_done(host):
    # Stored as done, an ignored ad read "Marked done" in its history; the notebook now says what the owner did.
    payload = json.dumps({'key': 'people/alice-chen.md\nA promise', 'state': 'ignored'}).encode()
    assert call(host.routes, 'POST', '/rem/thread', cookie=f'co_rem={host.token}', body=payload)[0] == 200
    assert threads.listing(host.root)['people/alice-chen.md\nA promise']['state'] == 'ignored'
    assert threads.blocked(host.root, 'people/alice-chen.md\nA promise')


def _cited(root, owner_listed, cites, mails):
    """One row on Mara's page citing `cites` of `mails` ({id: sender})."""
    prepare(root)
    write_json(state_path(root, 'map.json'), {'owner': {'record': 'people/avery.md', 'addresses': [OWNER] if owner_listed else []}})
    Notebook(root).write('people/mara.md', '# Mara\n\n## Open threads\n- You owe Mara the venue plan. ' + cites + '\n\n## Sources\n'
                         + ''.join(f'- [{n}] gmail:{identity}\n' for n, identity in enumerate(mails, 1)))
    for identity, sender in mails.items():
        retain_message(root, 'gmail', {'id': identity, 'from': sender, 'to': [OWNER, 'mara@example.test'], 'thread': identity,
                                       'subject': identity, 'date': '2026-11-06T03:00:00+00:00'}, 'x', fetched_at='2026-11-08T00:00:00+00:00')
    refresh(root)
    return today.queue(root, as_of=date(2026, 11, 8))


def test_a_newsletter_cited_beside_a_person_is_not_offered_and_ignoring_it_keeps_her_item(tmp_path, rem_clock):
    mails = {'n1': 'digest@notify.example.test', 'm1': 'mara@example.test'}
    assert [row['sender'] for row in _cited(tmp_path, True, '[1] [2]', mails)] == ['']
    threads.ignore_sender(tmp_path, 'digest@notify.example.test')
    assert len(today.queue(tmp_path, as_of=date(2026, 11, 8))) == 1


def test_a_row_leaves_today_only_when_every_cited_sender_is_ignored(tmp_path, rem_clock):
    mails = {'n1': 'digest@notify.example.test', 'n2': 'news@mail.paper.example.test'}
    assert len(_cited(tmp_path, True, '[1] [2]', mails)) == 1
    threads.ignore_sender(tmp_path, 'digest@notify.example.test')
    assert len(today.queue(tmp_path, as_of=date(2026, 11, 8))) == 1
    threads.ignore_sender(tmp_path, 'news@mail.paper.example.test')
    assert today.queue(tmp_path, as_of=date(2026, 11, 8)) == []


def test_without_the_owners_addresses_no_sender_is_offered(tmp_path, rem_clock):
    # Unknown owner: his own noreply-looking alias could be offered and would hide his own mail.
    assert [row['sender'] for row in _cited(tmp_path, False, '[1]', {'o1': 'noreply@example.test'})] == ['']


def test_only_a_machine_or_bulk_looking_sole_sender_is_offered(tmp_path, rem_clock):
    assert [row['sender'] for row in _cited(tmp_path, True, '[1]', {'n1': 'noreply@shop.example.test'})] == ['noreply@shop.example.test']
    other = tmp_path / 'person'
    assert [row['sender'] for row in _cited(other, True, '[1]', {'m1': 'mara@example.test'})] == ['']


def test_a_draft_for_an_ignored_sender_says_so(tmp_path, rem_clock):
    import pytest
    from connectonion.rem.files import RemError
    _notebook(tmp_path)
    row = next(row for row in drafts.candidates(tmp_path) if row['to'] == SHOP)
    drafts.promote(tmp_path, {**row, 'body': 'Thanks.', 'sources': ['gmail:sale']})
    threads.ignore_sender(tmp_path, SHOP)
    with pytest.raises(RemError, match='sender is ignored'):
        drafts._current(tmp_path, row['id'])


def test_hand_written_lines_keep_a_bare_address_and_the_angle_form(tmp_path, rem_clock):
    prepare(tmp_path)
    state_path(tmp_path, 'ignored-senders.txt').write_text(
        '# my list\nnews@mail.paper.example.test\nShop Deals <Deals@Mail.Shop.example.test>\n2026-10-01 a@notify.example.test\n')
    assert threads.ignored_senders(tmp_path) == {'news@mail.paper.example.test': '', SHOP: '', 'a@notify.example.test': '2026-10-01'}


def test_a_shared_snapshot_names_no_sender(tmp_path, rem_clock):
    from connectonion.rem import reader
    _notebook(tmp_path)
    threads.ignore_sender(tmp_path, 'news@mail.paper.example.test')
    shared, local = reader.snapshot(tmp_path), reader.snapshot(tmp_path, local=True)
    assert shared['ignored_senders'] == {} and all('sender' not in row for row in shared['today_queue'])
    assert local['ignored_senders'] and any(row.get('sender') == SHOP for row in local['today_queue'])
