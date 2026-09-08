"""Mailbox semantics and attachment acceptance with synthetic provider data."""
import base64
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from connectonion.useful_tools.gmail import Gmail


@pytest.fixture
def gmail(monkeypatch):
    client = Gmail.__new__(Gmail)
    monkeypatch.setattr(client, 'get_account_email', lambda: 'me@example.test')
    return client


def message(id, sender, timestamp, labels=(), **headers):
    return {'id': id, 'threadId': 'thread', 'internalDate': str(int(time.time() * 1000) + timestamp), 'labelIds': list(labels),
            'payload': {'headers': [{'name': k, 'value': v} for k,v in {'From': sender, **headers}.items()]}}


def test_unanswered_includes_user_started_support_threads_and_ignores_drafts(gmail, monkeypatch):
    calls = MagicMock(side_effect=[{'threads': [{'id': 'thread'}]}, {'messages': [
        message('draft', 'me@example.test', 300, ['DRAFT']),
        message('incoming', 'Support <support@example.test>', 200),
        message('original', 'me@example.test', 100, ['SENT'])]}])
    monkeypatch.setattr(gmail, '_mailbox_get', calls, raising=False)
    page = gmail.list_unanswered(within_days=30, last=20)
    assert [row['id'] for row in page['items']] == ['incoming']
    assert page['filters']['exclude_automated'] is False


@pytest.mark.parametrize('sender,labels,expected', [
    ('Name <ME@example.test>', [], []), ('notme@example.test', [], ['latest']),
    ('alias@example.test', ['SENT'], []), ('billing@example.test', [], ['latest'])])
def test_unanswered_uses_exact_mailbox_and_provider_sent_evidence(gmail, monkeypatch, sender, labels, expected):
    monkeypatch.setattr(gmail, '_mailbox_get', MagicMock(side_effect=[{'threads':[{'id':'thread'}]},
        {'messages':[message('latest', sender, 100, labels)]}]), raising=False)
    assert [row['id'] for row in gmail.list_unanswered()['items']] == expected


def test_automated_filter_is_opt_in_and_visible(gmail, monkeypatch):
    def read(path, **kwargs):
        return {'threads':[{'id':'thread'}]} if path == 'threads' else {
            'messages':[message('latest', 'billing@example.test', 100, **{'Auto-Submitted':'auto-generated'})]}
    monkeypatch.setattr(gmail, '_mailbox_get', read, raising=False)
    assert len(gmail.list_unanswered()['items']) == 1
    assert gmail.list_unanswered(exclude_automated=True)['items'] == []


def part(name, data=b'hello', id='1', **extra):
    return {'partId': id, 'filename':name, 'mimeType':'text/plain',
            'body':{'size':len(data), 'data':base64.urlsafe_b64encode(data).decode()}, **extra}


def test_nested_and_inline_attachments_have_stable_ids(gmail, monkeypatch):
    payload = {'parts':[{'parts':[part('a.txt', id='1.0'), part('', id='1.1',
        headers=[{'name':'Content-Disposition','value':'inline'}])]}]}
    monkeypatch.setattr(gmail, '_mailbox_get', lambda *a,**kw:{'payload':payload}, raising=False)
    rows = gmail.list_attachments('message')
    assert [row['id'] for row in rows] == ['part:1.0', 'part:1.1']
    assert rows[1]['inline'] is True
    assert 'data' not in str(rows)


def test_download_sanitizes_names_and_never_overwrites(gmail, monkeypatch, tmp_path):
    (tmp_path / 'report.txt').write_bytes(b'old')
    payload = {'parts':[part('../../report.txt', b'one', '1'), part('report.txt', b'two', '2')]}
    monkeypatch.setattr(gmail, '_mailbox_get', lambda *a,**kw:{'payload':payload}, raising=False)
    result = gmail.download_attachments('message', tmp_path, all_attachments=True)
    assert result['complete'] is True
    assert (tmp_path/'report.txt').read_bytes() == b'old'
    assert {Path(row['path']).read_bytes() for row in result['items']} == {b'one', b'two'}
    assert all(Path(row['path']).parent == tmp_path for row in result['items'])


def test_partial_download_preserves_success_and_reports_bad_data(gmail, monkeypatch, tmp_path):
    bad = part('bad.txt', id='2'); bad['body']['data'] = '!!!'
    monkeypatch.setattr(gmail, '_mailbox_get', lambda *a,**kw:{'payload':{'parts':[part('good.txt'),bad]}}, raising=False)
    result = gmail.download_attachments('message', tmp_path, all_attachments=True)
    assert result['complete'] is False
    assert [row['status'] for row in result['items']] == ['saved','failed']
    assert not (tmp_path/'bad.txt').exists()


def test_attachment_length_mismatch_is_failure(gmail, monkeypatch, tmp_path):
    payload = part('wrong.txt'); payload['body']['size'] = 99
    monkeypatch.setattr(gmail, '_mailbox_get', lambda *a,**kw:{'payload':payload}, raising=False)
    result = gmail.download_attachments('message', tmp_path, all_attachments=True)
    assert result['items'][0]['error']['code'] == 'size_mismatch'
    assert list(tmp_path.iterdir()) == []


def test_page_cursor_cannot_cross_account_or_query(gmail, monkeypatch):
    from connectonion.useful_tools.gmail_mailbox import MailboxError
    monkeypatch.setattr(gmail, '_mailbox_get', MagicMock(return_value={'messages':[], 'nextPageToken':'provider-next', 'resultSizeEstimate':123}), raising=False)
    page = gmail.message_page('in:inbox', last=10)
    assert page['total_estimate'] == 123 and page['truncated'] is True
    with pytest.raises(MailboxError, match='cursor'):
        gmail.message_page('in:sent', last=10, cursor=page['next_cursor'])
    monkeypatch.setattr(gmail, 'get_account_email', lambda:'other@example.test')
    with pytest.raises(MailboxError, match='cursor'):
        gmail.message_page('in:inbox', last=10, cursor=page['next_cursor'])


def test_response_stream_is_bounded_before_json_decode(gmail, monkeypatch):
    from connectonion.useful_tools import gmail_mailbox as module
    from connectonion.provider_credentials import resolve_provider_credentials
    gmail._credentials = resolve_provider_credentials('google')
    monkeypatch.setattr(gmail, '_get_service', lambda:None)
    monkeypatch.setattr(module, 'RESPONSE_LIMIT', 10)
    response = MagicMock(status_code=200)
    response.iter_content.return_value = [b'123456', b'789012']
    response.__enter__.return_value = response
    monkeypatch.setattr(module.requests, 'get', MagicMock(return_value=response))
    with pytest.raises(module.MailboxError, match='limit'):
        gmail._mailbox_get('messages/id')
    response.__exit__.assert_called_once()
    assert module.requests.get.call_args.kwargs['allow_redirects'] is False


def test_recent_draft_does_not_make_old_incoming_message_unanswered(gmail, monkeypatch):
    old = message('old', 'other@example.test', -60 * 86400 * 1000)
    draft = message('draft', 'me@example.test', 0, ['DRAFT'])
    monkeypatch.setattr(gmail, '_mailbox_get', MagicMock(side_effect=[{'threads':[{'id':'thread'}]},
        {'messages':[old, draft]}]), raising=False)
    assert gmail.list_unanswered(within_days=30)['items'] == []


def test_symlink_collision_cannot_replace_or_modify_target(gmail, monkeypatch, tmp_path):
    outside = tmp_path/'outside'; outside.write_bytes(b'private')
    directory = tmp_path/'downloads'; directory.mkdir()
    (directory/'file.txt').symlink_to(outside)
    monkeypatch.setattr(gmail, '_mailbox_get', lambda *a,**kw:{'payload':part('file.txt')}, raising=False)
    result = gmail.download_attachments('message', directory, all_attachments=True)
    assert result['complete'] is True and outside.read_bytes() == b'private'
    assert Path(result['items'][0]['path']).name == 'file (1).txt'


def test_container_without_own_bytes_is_not_a_fake_empty_attachment(gmail, monkeypatch):
    payload = {'filename':'attached.eml', 'mimeType':'message/rfc822', 'body':{'size':0},
               'parts':[part('inner.txt', id='1.0')]}
    monkeypatch.setattr(gmail, '_mailbox_get', lambda *a,**kw:{'payload':payload}, raising=False)
    assert [row['filename'] for row in gmail.list_attachments('message')] == ['inner.txt']


def test_total_budget_stops_later_files_without_losing_saved_files(gmail, monkeypatch, tmp_path):
    from connectonion.useful_tools import gmail_mailbox as module
    monkeypatch.setattr(module, 'DOWNLOAD_LIMIT', 7)
    monkeypatch.setattr(gmail, '_mailbox_get', lambda *a,**kw:{'payload':{'parts':[
        part('first.txt', b'1234','1'),part('second.txt',b'5678','2')]}}, raising=False)
    result = gmail.download_attachments('message', tmp_path, all_attachments=True)
    assert [row['status'] for row in result['items']] == ['saved','failed']
    assert result['decoded_bytes'] == 4
    assert result['items'][1]['error']['code'] == 'attachment_too_large'
