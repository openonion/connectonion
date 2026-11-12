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


def test_an_ignored_sender_is_one_dated_line_and_undo_removes_it(tmp_path, rem_clock):
    prepare(tmp_path)
    threads.ignore_sender(tmp_path, 'Deals@Shop.Example.test')
    threads.ignore_sender(tmp_path, 'deals@shop.example.test')
    threads.ignore_sender(tmp_path, 'news@paper.example.test')
    assert threads.ignored_senders(tmp_path) == {'deals@shop.example.test': '2026-09-07', 'news@paper.example.test': '2026-09-07'}
    lines = state_path(tmp_path, 'ignored-senders.txt').read_text().splitlines()
    # Readable and editable by hand: a comment that says what the file is, then one date and address per line.
    assert lines[0].startswith('#')
    assert lines[1:] == ['2026-09-07 deals@shop.example.test', '2026-09-07 news@paper.example.test']
    threads.ignore_sender(tmp_path, 'deals@shop.example.test', ignored=False)
    assert threads.ignored_senders(tmp_path) == {'news@paper.example.test': '2026-09-07'}


def _notebook(root):
    prepare(root)
    write_json(state_path(root, 'map.json'), {'owner': {'record': 'people/avery.md', 'addresses': [OWNER]}})
    Notebook(root).write('orgs/shop.md', '# Shop\n\n## Open threads\n- You owe Shop a reply about the spring sale. [1]\n\n'
                         '## Sources\n- [1] gmail:sale\n')
    Notebook(root).write('people/mara.md', '# Mara\n\n## Open threads\n- You owe Mara a reply about the venue. [1]\n\n'
                         '## Sources\n- [1] gmail:venue\n')
    for identity, sender, thread in [('sale', 'deals@shop.example.test', 'sale'), ('venue', 'mara@example.test', 'venue')]:
        retain_message(root, 'gmail', {'id': identity, 'from': sender, 'to': [OWNER], 'thread': thread,
                                       'subject': thread, 'date': '2026-11-06T03:00:00+00:00'},
                       'Could you reply?', fetched_at='2026-11-08T00:00:00+00:00')
    refresh(root)


def test_today_leaves_out_every_item_from_an_ignored_sender_and_names_each_rows_sender(tmp_path, rem_clock):
    _notebook(tmp_path)
    rows = today.queue(tmp_path, as_of=date(2026, 11, 8))
    assert {row['record']: row['sender'] for row in rows} == {'orgs/shop.md': 'deals@shop.example.test',
                                                              'people/mara.md': 'mara@example.test'}
    threads.ignore_sender(tmp_path, 'deals@shop.example.test')
    assert [row['record'] for row in today.queue(tmp_path, as_of=date(2026, 11, 8))] == ['people/mara.md']
    threads.ignore_sender(tmp_path, 'deals@shop.example.test', ignored=False)
    assert len(today.queue(tmp_path, as_of=date(2026, 11, 8))) == 2


def test_the_night_drafts_no_reply_to_an_ignored_sender(tmp_path, rem_clock):
    _notebook(tmp_path)
    assert {row['to'] for row in drafts.candidates(tmp_path)} == {'deals@shop.example.test', 'mara@example.test'}
    threads.ignore_sender(tmp_path, 'deals@shop.example.test')
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


def test_a_relay_that_carries_peoples_messages_is_never_a_sender_to_ignore(tmp_path, rem_clock):
    # Guests write through express@airbnb.com; ignoring it would silence every one of them.
    prepare(tmp_path)
    write_json(state_path(tmp_path, 'map.json'), {'owner': {'record': 'people/avery.md', 'addresses': [OWNER]}})
    Notebook(tmp_path).write('people/ivo.md', '# Ivo\n\n## Open threads\n- You owe Ivo a call time. [1]\n\n'
                             '## Sources\n- [1] gmail:guest\n')
    retain_message(tmp_path, 'gmail', {'id': 'guest', 'from': 'express@airbnb.com', 'to': [OWNER], 'thread': 'guest',
                                       'subject': 'guest', 'date': '2026-11-06T03:00:00+00:00'},
                   'Which day suits?', fetched_at='2026-11-08T00:00:00+00:00')
    refresh(tmp_path)
    assert [row['sender'] for row in today.queue(tmp_path, as_of=date(2026, 11, 8))] == ['']


def test_ignored_is_its_own_thread_state_that_leaves_today_like_done(host):
    # Stored as done, an ignored ad read "Marked done" in its history; the notebook now says what the owner did.
    payload = json.dumps({'key': 'people/alice-chen.md\nA promise', 'state': 'ignored'}).encode()
    assert call(host.routes, 'POST', '/rem/thread', cookie=f'co_rem={host.token}', body=payload)[0] == 200
    assert threads.listing(host.root)['people/alice-chen.md\nA promise']['state'] == 'ignored'
    assert threads.blocked(host.root, 'people/alice-chen.md\nA promise')
