"""REM sets direct-send tiers from each person's page (D-101). Fictional people only."""
import json
import sqlite3

import pytest

from connectonion.rem import direct_send
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json


def page(name, relationship, writes='Unknown', facts=''):
    return (f'# {name}\n\n## Facts\n- Email: {name.split()[0].lower()}@example.test\n- Role: Co-founder\n{facts}'
            f'- Language: English\n\n## Our relationship\n{relationship}\n\n'
            f'## How the user writes to them\n{writes}\n\n## Sources\n- [1] gmail:one\n')


@pytest.mark.parametrize('relationship,writes,sent,expected', [
    ('The user describes Mara as a co-founder.', 'Formal.', 0, 'partner'),
    ('Mara is the user\'s 合伙人.', 'Formal.', 0, 'partner'),
    ('The user described Mara as a very good friend.', 'Formal.', 0, 'close'),
    ('They coordinate on the pilot.', 'The user writes informally, by first name.', 12, 'close'),
    ('They coordinate on the pilot.', 'The user writes informally, by first name.', 3, 'none'),
    # Her own company's co-founder title is in Role, not in how she relates to the user.
    ('A prospective vendor evaluation.', 'Informal.', 40, 'none'),
    ('A client collaboration; Mara is a co-founder at the client.', 'Informal.', 40, 'none'),
    ('Outreach only.', 'Formal.', 1, 'none'),
])
def test_the_rule_reads_the_relationship_not_the_job_title(relationship, writes, sent, expected):
    assert direct_send.tier(page('Mara Quill', relationship, writes), sent) == expected


def _mail(root, owner, to, count):
    database = state_path(root, 'rem.db')
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as db:
        db.execute('create table if not exists messages (id text, sender text, recipients text)')
        db.executemany('insert into messages values (?, ?, ?)',
                       [(f'm{index}', owner, json.dumps([to])) for index in range(count)])


def test_the_night_writes_rems_tier_and_never_overwrites_the_owners(tmp_path):
    prepare(tmp_path)
    book = Notebook(tmp_path)
    write_json(state_path(tmp_path, 'map.json'), {'owner': {'record': 'people/me.md', 'addresses': ['me@example.test']}})
    book.write('people/me.md', page('Me Self', 'Account owner. co-founder of everything.'))
    book.write('people/mara.md', page('Mara Quill', 'The user describes Mara as a co-founder.'))
    book.write('people/fern.md', page('Fern Vale', 'They coordinate on the pilot.', 'The user writes casually.'))
    book.write('people/wren.md', page('Wren Hale', 'Wren is a co-founder of the user.',
                                       facts='- Direct send: none\n'))
    book.write('people/ivo.md', page('Ivo Marsh', 'A client of the studio.'))
    _mail(tmp_path, 'me@example.test', 'fern@example.test', 11)
    changed = direct_send.refresh(tmp_path, '2026-11-09')
    assert sorted(changed) == ['people/fern.md', 'people/mara.md']
    assert '- Direct send: partner (set by REM, 2026-11-09; change it any time)\n' in book.read('people/mara.md')
    assert '- Direct send: close (set by REM, 2026-11-09; change it any time)\n' in book.read('people/fern.md')
    assert '- Direct send: none\n' in book.read('people/wren.md')  # the owner's own value
    assert 'Direct send' not in book.read('people/ivo.md') + book.read('people/me.md')
    # Facts stays one list: the line sits with the other facts.
    assert '- Language: English\n- Direct send: partner' in book.read('people/mara.md')
    assert direct_send.refresh(tmp_path, '2026-11-10') == []  # unchanged tiers keep their date
    book.write('people/fern.md', book.read('people/fern.md').replace('They coordinate', 'A prospective client;'))
    assert direct_send.refresh(tmp_path, '2026-11-10') == ['people/fern.md']
    assert 'Direct send' not in book.read('people/fern.md')  # REM's own line follows its rule down


def test_a_tier_set_by_rem_lets_the_writer_send_after_the_hold(tmp_path):
    from connectonion.rem import drafts
    prepare(tmp_path)
    book = Notebook(tmp_path)
    book.write('people/mara.md', page('Mara Quill', 'Co-founder.',
                                       facts='- Direct send: partner (set by REM, 2026-11-09; change it any time)\n'))
    assert drafts._page_excerpt(tmp_path, 'people/mara.md', ('Facts',))['direct_send'] == 'partner'


@pytest.mark.parametrize('relationship,expected', [
    # Later sentences tell history: a customer setup handed over does not make a co-founder a client.
    ('The user describes Mara as a co-founder. On 2026-10-22 the user sent Mara a customer setup handoff.', 'partner'),
    # Someone else's co-founder, named in passing, does not make this contact a partner.
    ('Mara is a professional contact. She described the fund as the family office of a co-founder of Fernhill.', 'none'),
    ('- The relationship is a course project collaboration. Mara and teammate Ivo shared feedback.', 'none'),
])
def test_only_the_first_sentence_says_what_the_relationship_is(relationship, expected):
    assert direct_send.tier(page('Mara Quill', relationship), 0) == expected


def test_today_lists_the_replies_rem_sent_itself(tmp_path, rem_clock):
    from connectonion.rem import reader, service
    prepare(tmp_path)
    write_json(state_path(tmp_path, 'approvals.json'), {
        'reply:mara': {'id': 'reply:mara', 'kind': 'reply', 'by': 'rem', 'status': 'sent', 'title': 'Mara Quill',
                       'text': 'pilot date', 'release_at': service.now().isoformat()},
        'reply:fern': {'id': 'reply:fern', 'kind': 'reply', 'by': 'owner', 'status': 'sent', 'title': 'Fern Vale',
                       'text': 'notes', 'release_at': service.now().isoformat()}})
    sent = reader.snapshot(tmp_path, local=True, today=True)['sent_by_rem']
    assert [row['title'] for row in sent] == ['Mara Quill']
    assert 'REM.sent_by_rem' in reader.TEMPLATE.read_text()  # the night card names them
