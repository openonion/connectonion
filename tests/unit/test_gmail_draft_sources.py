"""Managed source metadata survives provider MIME round trips and restart."""
from email.message import EmailMessage

import pytest

from connectonion.useful_tools.gmail import Gmail
from connectonion.useful_tools import gmail_draft_sources as sources


def message():
    result = EmailMessage()
    result['To'] = 'recipient@example.test'
    result['Cc'] = 'copy@example.test'
    result['Bcc'] = 'blind@example.test'
    result['Subject'] = 'Unicode résumé'
    result.set_content('Body with an ordinary URL: https://drive.google.com/file/d/ordinary/view\n')
    return result


def item(id='file-a'):
    return {'id':id, 'name':'Budget', 'type':'application/pdf', 'raw_size':5,
            'link':f'https://drive.google.com/file/d/{id}/view'}


def test_arbitrary_body_url_is_never_a_managed_item():
    assert sources.read_links(message()) == []


def test_link_round_trip_keeps_account_recipients_and_explicit_record():
    original = message()
    sources.add_link(original, item())
    restored = Gmail._decode_message(Gmail._encode_message(original))
    rows = sources.read_links(restored)
    assert len(rows) == 1 and rows[0]['drive_file_id'] == 'file-a'
    assert rows[0]['sharing'] == 'unchanged; recipient access unverified'
    assert str(restored['Bcc']) == 'blind@example.test'
    assert str(restored['Subject']) == 'Unicode résumé'
    assert item()['link'] in restored.get_content()


def test_remove_link_leaves_arbitrary_body_url_untouched():
    original = message()
    sources.add_link(original, item())
    sources.remove_link(original, 0)
    assert sources.read_links(original) == []
    assert '/ordinary/view' in original.get_content()
    assert '/file-a/view' not in original.get_content()


def test_independent_link_edit_cannot_keep_stale_managed_record():
    original = message()
    sources.add_link(original, item())
    original.set_content(original.get_content().replace('/file-a/', '/different/'))
    with pytest.raises(ValueError, match='changed'):
        sources.read_links(original)


def test_file_source_survives_mime_round_trip_and_detects_changed_bytes():
    original = message()
    original.add_attachment(b'original', maintype='application', subtype='pdf', filename='résumé.pdf')
    part = list(original.iter_attachments())[0]
    sources.tag_file(part, b'original', {'source':'drive_attachment','drive_file_id':'file-a','export_type':'application/pdf'})
    restored = Gmail._decode_message(Gmail._encode_message(original))
    part = list(restored.iter_attachments())[0]
    assert sources.file_source(part)['drive_file_id'] == 'file-a'
    part.set_payload('altered')
    with pytest.raises(ValueError, match='changed'):
        sources.file_source(part)

@pytest.fixture
def provider(monkeypatch):
    from unittest.mock import MagicMock
    client = Gmail.__new__(Gmail)
    service = MagicMock()
    current = {'message': message()}
    def fetch(**kwargs):
        request = MagicMock()
        request.execute.return_value = {'message':{'raw':Gmail._encode_message(current['message'])}}
        return request
    def update(**kwargs):
        current['message'] = Gmail._decode_message(kwargs['body']['message']['raw'])
        return MagicMock()
    service.users().drafts().get.side_effect = fetch
    service.users().drafts().update.side_effect = update
    monkeypatch.setattr(client, '_get_service', lambda:service)
    monkeypatch.setattr(client, '_require_draft_write_scope', lambda:None)
    monkeypatch.setattr(client, 'get_account_email', lambda:'owner@example.test')
    return client, service, current


def test_unified_items_survive_fetch_remove_and_replace_in_one_update(provider):
    client, service, current = provider
    client._add_draft_attachment('draft-a', 'local.txt', 'text/plain', b'local', source={'source':'local'})
    client._add_managed_draft_link('draft-a', item())
    restored = client.get_draft('draft-a')
    assert [row['source'] for row in restored['items']] == ['local', 'drive_link']
    assert restored['attachment_size'] == 5
    before = service.users().drafts().update.call_count
    client._replace_draft_attachment('draft-a', 2, 'new.txt', 'text/plain', b'new', source={'source':'local'})
    assert service.users().drafts().update.call_count == before + 1
    assert '/file-a/view' not in client.get_draft('draft-a')['body']
    client._replace_draft_link('draft-a', 1, item('file-b'))
    restored = client.get_draft('draft-a')
    assert [row['source'] for row in restored['items']] == ['local', 'drive_link']
    client.remove_draft_attachment('draft-a', 2)
    assert len(client.get_draft('draft-a')['items']) == 1
    assert '/ordinary/view' in client.get_draft('draft-a')['body']


def test_failed_link_replacement_keeps_old_provider_item(provider):
    client, service, current = provider
    client._add_managed_draft_link('draft-a', item())
    before = Gmail._encode_message(current['message'])
    with pytest.raises(ValueError, match='HTTPS'):
        client._replace_draft_link('draft-a', 1, {**item(), 'link':'http://untrusted.test'})
    assert Gmail._encode_message(current['message']) == before


def test_send_strips_internal_records_but_review_shows_sources(provider):
    from connectonion.cli.commands.gmail_draft_review import prepare_review
    client, service, current = provider
    client._add_draft_attachment('draft-a', 'a.txt', 'text/plain', b'a', source={'source':'local'})
    client._add_managed_draft_link('draft-a', item())
    reviewed = prepare_review(client, 'draft-a')
    outgoing = Gmail._decode_message(reviewed.raw)
    assert [row['source'] for row in reviewed.manifest['items']] == ['local','drive_link']
    assert all(sources.SOURCE_HEADER not in part and sources.LINK_HEADER not in part for part in outgoing.walk())
    assert item()['link'] in client._message_body(outgoing)


def test_mime_limit_rejects_update_before_provider_mutation(provider, monkeypatch):
    from connectonion.useful_tools import gmail_draft_mime
    client, service, current = provider
    monkeypatch.setattr(gmail_draft_mime, 'MIME_LIMIT', 100)
    with pytest.raises(ValueError, match='MIME'):
        client._add_draft_attachment('draft-a', 'a.txt', 'text/plain', b'a')
    service.users().drafts().update.assert_not_called()


def test_managed_link_handles_provider_crlf_round_trip():
    from email import policy
    from email.parser import BytesParser
    original = message()
    sources.add_link(original, item())
    restored = BytesParser(policy=policy.default).parsebytes(original.as_bytes(policy=policy.SMTP))
    assert sources.read_links(restored)[0]['drive_file_id'] == 'file-a'
    sources.remove_link(restored, 0)
    assert '/file-a/view' not in restored.get_content()


def test_drive_stream_budget_excludes_only_replaced_file(provider, monkeypatch):
    import connectonion.useful_tools.gmail as gmail_module
    client, service, current = provider
    client._add_draft_attachment('draft-a', 'a.txt', 'text/plain', b'1234')
    client._add_managed_draft_link('draft-a', item())
    monkeypatch.setattr(gmail_module, 'GMAIL_ATTACHMENT_LIMIT', 10)
    assert client._draft_attachment_budget('draft-a') == 6
    assert client._draft_attachment_budget('draft-a', replacing=1) == 10
    assert client._draft_attachment_budget('draft-a', replacing=2) == 6
