"""Retained originals remain inspectable when a derived index lacks their row."""
import hashlib
import json

import pytest

from connectonion.rem.config import prepare
from connectonion.rem.files import state_path, write_json
from connectonion.rem.mail_archive import message_path, observed_message_path
from connectonion.rem.reader_model import cited_context
from connectonion.rem.store import refresh


def retained(root, provider, *, folder='messages', body='I can review a draft, not promise a launch.'):
    native = 'native-' + provider
    source = provider + ':' + hashlib.sha256(native.encode()).hexdigest()[:12]
    path = (message_path if folder == 'messages' else observed_message_path)(root, provider, native)
    saved = {'provider': provider, 'id': native, 'body': body,
             'from': 'partner@example.test', 'to': ['owner@example.test'], 'cc': [],
             'subject': 'Scope', 'date': '2026-09-10T12:00:00Z',
             'fetched_at': '', 'retained_at': '2026-10-20T08:00:00Z',
             'input_scope': 'Historical retained rendering; original retrieval time unknown.',
             'body_format': 'provider-rendered text, not original MIME'}
    write_json(path, saved)
    return source, path, saved


def context(root, source, **options):
    return cited_context(root, [{'text': '## Sources\n- [1] ' + source}], **options)


@pytest.mark.parametrize('provider', ['gmail', 'outlook'])
@pytest.mark.parametrize('indexed', [False, True])
@pytest.mark.parametrize('folder', ['messages', 'observed'])
def test_cited_retained_original_does_not_require_an_index_row(tmp_path, provider, indexed, folder):
    prepare(tmp_path)
    if indexed:
        refresh(tmp_path)  # A valid derived index that predates the retained original.
    source, path, saved = retained(tmp_path, provider, folder=folder)
    # Read-only SQLite may create transient WAL/shared-memory lock files.
    def persistent_files():
        return {p: p.read_bytes() for p in tmp_path.rglob('*')
                if p.is_file() and p.name not in {'rem.db-shm', 'rem.db-wal'}}
    before = persistent_files()
    row = context(tmp_path, source)[source]
    assert row['excerpt'] == saved['body'] and not row['truncated']
    assert row['sender'] == saved['from'] and row['participants']['to'] == saved['to']
    assert row['time'] == saved['date'] and row['retained_at'] == saved['retained_at']
    assert row['captured_at'] == '' and row['input_scope'] == saved['input_scope']
    assert row['thread'] == '', 'A missing index cannot establish a provider conversation'
    assert before == persistent_files()


def test_unindexed_marker_private_original_stays_private(tmp_path):
    prepare(tmp_path)
    source, _, _ = retained(tmp_path, 'gmail', body='[personal] I can review a draft.')
    assert not context(tmp_path, source)
    assert context(tmp_path, source, private=True)[source]['excerpt'].startswith('[personal]')


@pytest.mark.parametrize('field,value', [('provider', 'outlook'), ('id', 'another-native')])
def test_fallback_rejects_wrong_snapshot_identity(tmp_path, field, value):
    prepare(tmp_path)
    source, path, saved = retained(tmp_path, 'gmail')
    write_json(path, {**saved, field: value})
    assert not context(tmp_path, source)


def test_fallback_rejects_symlink_snapshot(tmp_path):
    from connectonion.rem.files import RemError
    prepare(tmp_path)
    source, path, saved = retained(tmp_path, 'gmail')
    outside = tmp_path.parent / 'outside-mail.json'
    outside.write_text(json.dumps(saved))
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(RemError, match='[Ss]ymlink|linked'):
        context(tmp_path, source)


def test_native_citation_also_opens_an_unindexed_retained_original(tmp_path):
    prepare(tmp_path)
    _, _, saved = retained(tmp_path, 'gmail')
    source = 'gmail:' + saved['id']
    assert context(tmp_path, source)[source]['excerpt'] == saved['body']


def test_fallback_keeps_existing_excerpt_budget(tmp_path):
    prepare(tmp_path)
    source, _, saved = retained(tmp_path, 'outlook')
    row = context(tmp_path, source, budget=9)[source]
    assert row['excerpt'] == saved['body'][:9] and row['truncated']


def test_primary_snapshot_wins_over_observed_copy_of_same_native_message(tmp_path):
    prepare(tmp_path)
    source, _, _ = retained(tmp_path, 'gmail', body='First canonical rendering.')
    retained(tmp_path, 'gmail', folder='observed', body='Later observed rendering.')
    assert context(tmp_path, source)[source]['excerpt'] == 'First canonical rendering.'


def test_fallback_does_not_override_ambiguous_indexed_pointers(tmp_path):
    import sqlite3
    prepare(tmp_path)
    refresh(tmp_path)
    source, path, _ = retained(tmp_path, 'outlook')
    pointer = str(path.relative_to(tmp_path / '.state'))
    with sqlite3.connect(state_path(tmp_path, 'rem.db')) as db:
        db.executemany('insert into messages (id,source,body_path) values (?,?,?)', [
            ('outlook:native-outlook', 'outlook', pointer), ('outlook:conflicting-id', 'outlook', pointer)])
    assert not context(tmp_path, source)


def test_ambiguous_retained_short_hash_does_not_pick_an_arbitrary_original(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from connectonion.rem import reader_model
    prepare(tmp_path)
    handle = 'a' * 12
    digests = {'first': handle + '1' * 52, 'second': handle + '2' * 52}
    for native, digest in digests.items():
        write_json(state_path(tmp_path, 'mail/messages/gmail/' + digest + '.json'),
                   {'provider': 'gmail', 'id': native, 'body': native})
    real_sha = hashlib.sha256
    def digest(data):
        value = digests.get(data.decode()) or real_sha(data).hexdigest()
        return SimpleNamespace(hexdigest=lambda: value)
    monkeypatch.setattr(reader_model, 'hashlib', SimpleNamespace(sha256=digest))
    assert not context(tmp_path, 'gmail:' + handle)


def test_short_hash_and_a_native_id_with_same_spelling_are_ambiguous(tmp_path):
    prepare(tmp_path)
    native = 'first-native-message'
    handle = hashlib.sha256(native.encode()).hexdigest()[:12]
    for message_id, body in [(native, 'The first retained statement.'),
                             (handle, 'An unrelated second statement.')]:
        write_json(message_path(tmp_path, 'gmail', message_id),
                   {'provider': 'gmail', 'id': message_id, 'body': body})
    assert not context(tmp_path, 'gmail:' + handle)


def test_unindexed_empty_body_preserves_header_only_evidence(tmp_path):
    prepare(tmp_path)
    source, _, saved = retained(tmp_path, 'outlook', body='')
    row = context(tmp_path, source)[source]
    assert row['body_empty'] and row['excerpt'] == '' and not row['truncated']
    assert row['subject'] == saved['subject'] and row['sender'] == saved['from']


def test_fallback_rejects_a_forged_full_digest_filename(tmp_path):
    prepare(tmp_path)
    source, path, _ = retained(tmp_path, 'gmail')
    last = '0' if path.stem[-1] != '0' else '1'
    path.rename(path.with_name(path.stem[:-1] + last + '.json'))
    assert not context(tmp_path, source)


def test_fallback_requires_a_nonempty_native_identity(tmp_path):
    prepare(tmp_path)
    digest = hashlib.sha256(b'').hexdigest()
    write_json(state_path(tmp_path, 'mail/messages/gmail/' + digest + '.json'),
               {'provider': 'gmail', 'id': '', 'body': 'No native identity.'})
    assert not context(tmp_path, 'gmail:' + digest[:12])


@pytest.mark.parametrize('native_handle', [False, True])
def test_indexed_mail_metadata_without_a_body_pointer_can_use_retained_original(tmp_path, native_handle):
    import sqlite3
    prepare(tmp_path)
    refresh(tmp_path)
    source, _, saved = retained(tmp_path, 'gmail')
    native_source = 'gmail:' + saved['id']
    with sqlite3.connect(state_path(tmp_path, 'rem.db')) as db:
        db.execute('insert into messages (id,source,thread,body_path) values (?,?,?,?)',
                   (native_source, 'gmail', 'mail:gmail:known-thread', None))
    handle = native_source if native_handle else source
    result = context(tmp_path, handle)[handle]
    assert result['excerpt'] == saved['body']
    assert result['thread'] == 'mail:gmail:known-thread'


def test_verified_archive_does_not_override_a_conflicting_native_index_pointer(tmp_path):
    import sqlite3
    prepare(tmp_path)
    refresh(tmp_path)
    source, _, saved = retained(tmp_path, 'gmail')
    wrong = message_path(tmp_path, 'gmail', 'different-native')
    write_json(wrong, {'provider': 'gmail', 'id': 'different-native', 'body': 'Other statement.'})
    with sqlite3.connect(state_path(tmp_path, 'rem.db')) as db:
        db.execute('insert into messages (id,source,body_path) values (?,?,?)',
                   ('gmail:' + saved['id'], 'gmail', str(wrong.relative_to(tmp_path / '.state'))))
    assert not context(tmp_path, source)
