"""A review controls the exact send payload, even with concurrent provider edits."""
import base64
from email.message import EmailMessage
from unittest.mock import MagicMock

import pytest

from connectonion.useful_tools.gmail import Gmail


def raw_message(body='Reviewed body'):
    message = EmailMessage()
    message['To'] = 'recipient@example.test'
    message['Cc'] = 'copy@example.test'
    message['Bcc'] = 'blind@example.test'
    message['Subject'] = 'Review fixture'
    message.set_content(body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


@pytest.fixture
def gmail(monkeypatch):
    client = Gmail.__new__(Gmail)
    service = MagicMock()
    service.users().drafts().get().execute.return_value = {
        'id':'draft-a', 'message':{'raw':raw_message(), 'threadId':'thread-a'}}
    service.users().drafts().send().execute.return_value = {'id':'sent-a'}
    monkeypatch.setattr(client, '_get_service', lambda:service)
    monkeypatch.setattr(client, 'get_account_email', lambda:'owner@example.test')
    monkeypatch.setattr(client, '_require_draft_write_scope', lambda:None)
    return client, service


def test_review_binds_account_draft_thread_and_full_content(gmail):
    from connectonion.cli.commands.gmail_draft_review import prepare_review
    client, service = gmail
    first = prepare_review(client, 'draft-a')
    assert first.manifest['bcc'] == 'blind@example.test'
    assert first.manifest['account'] == 'owner@example.test'
    assert first.manifest['encoded_size'] > 0
    assert first.token == prepare_review(client, 'draft-a').token
    service.users().drafts().get().execute.return_value['message']['raw'] = raw_message('Changed body')
    assert first.token != prepare_review(client, 'draft-a').token


def test_changed_draft_cannot_send_with_old_review(gmail, tmp_path):
    from connectonion.cli.commands.gmail_draft_review import prepare_review, send_reviewed, DraftReviewError
    client, service = gmail
    review = prepare_review(client, 'draft-a')
    service.users().drafts().get().execute.return_value['message']['raw'] = raw_message('Changed independently')
    with pytest.raises(DraftReviewError, match='changed'):
        send_reviewed(client, 'draft-a', review.token, directory=tmp_path)
    service.users().drafts().send.assert_called_once_with()  # mock fixture initialization only


def test_send_carries_frozen_bytes_in_same_provider_request(gmail, tmp_path):
    from connectonion.cli.commands.gmail_draft_review import prepare_review, send_reviewed
    client, service = gmail
    review = prepare_review(client, 'draft-a')
    result = send_reviewed(client, 'draft-a', review.token, directory=tmp_path)
    assert result['id'] == 'sent-a'
    body = service.users().drafts().send.call_args.kwargs['body']
    assert body == {'id':'draft-a', 'message':{'raw':review.raw, 'threadId':'thread-a'}}
    assert b'Reviewed body' in base64.urlsafe_b64decode(body['message']['raw'])


def test_lost_send_response_blocks_resubmission(gmail, tmp_path):
    from connectonion.cli.commands.gmail_draft_review import prepare_review, send_reviewed, DraftReviewError
    from requests import ConnectionError
    client, service = gmail
    review = prepare_review(client, 'draft-a')
    service.users().drafts().send().execute.side_effect = ConnectionError('provider secret body')
    service.users().messages().list().execute.return_value = {'messages':[]}
    with pytest.raises(DraftReviewError, match='uncertain'):
        send_reviewed(client, 'draft-a', review.token, directory=tmp_path)
    before = service.users().drafts().send().execute.call_count
    with pytest.raises(DraftReviewError, match='uncertain'):
        send_reviewed(client, 'draft-a', review.token, directory=tmp_path)
    assert service.users().drafts().send().execute.call_count == before
    assert 'Reviewed body' not in ''.join(path.read_text() for path in tmp_path.glob('*.json'))


def test_repeating_confirmed_send_returns_receipt_without_resending(gmail, tmp_path):
    from connectonion.cli.commands.gmail_draft_review import prepare_review, send_reviewed
    client, service = gmail
    review = prepare_review(client, 'draft-a')
    first = send_reviewed(client, 'draft-a', review.token, directory=tmp_path)
    before = service.users().drafts().send().execute.call_count
    assert send_reviewed(client, 'draft-a', review.token, directory=tmp_path)['id'] == first['id']
    assert service.users().drafts().send().execute.call_count == before


def test_non_tty_send_cannot_be_approved_by_piped_yes(gmail, monkeypatch):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.cli.commands import gmail_commands as gm
    client, service = gmail
    monkeypatch.setattr(gm, '_gmail', lambda:client)
    result = CliRunner().invoke(app, ['gmail','draft','send','draft-a'], input='y\n')
    assert result.exit_code == 1
    assert 'Non-interactive send requires' in result.output
    assert service.users().drafts().send().execute.call_count == 0


def test_json_review_then_confirm_routes_complete_frozen_payload(gmail, monkeypatch):
    import json
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.cli.commands import gmail_commands as gm
    client, service = gmail
    monkeypatch.setattr(gm, '_gmail', lambda:client)
    reviewed = CliRunner().invoke(app, ['gmail','draft','review','draft-a','--json'])
    assert reviewed.exit_code == 0, reviewed.output
    token = json.loads(reviewed.stdout)['data']['review_token']
    sent = CliRunner().invoke(app, ['gmail','draft','send','draft-a','--confirm',token,'--json'])
    assert sent.exit_code == 0, sent.output
    assert json.loads(sent.stdout)['data']['id'] == 'sent-a'
    assert 'raw' in service.users().drafts().send.call_args.kwargs['body']['message']


def test_id_only_sdk_send_is_refused(gmail):
    client, service = gmail
    with pytest.raises(ValueError, match='reviewed raw'):
        client._send_draft('draft-a')
    assert service.users().drafts().send().execute.call_count == 0


def test_edit_after_final_check_cannot_substitute_outgoing_content(gmail, monkeypatch, tmp_path):
    from connectonion.cli.commands.gmail_draft_review import prepare_review, send_reviewed
    client, service = gmail
    review = prepare_review(client, 'draft-a')
    def concurrent_edit():
        service.users().drafts().get().execute.return_value['message']['raw'] = raw_message('Independent late edit')
    monkeypatch.setattr(client, '_require_draft_write_scope', concurrent_edit)
    send_reviewed(client, 'draft-a', review.token, directory=tmp_path)
    outgoing = service.users().drafts().send.call_args.kwargs['body']['message']['raw']
    assert outgoing == review.raw
    assert b'Independent late edit' not in base64.urlsafe_b64decode(outgoing)


def test_unknown_send_recovers_one_sent_receipt_without_resubmission(gmail, tmp_path):
    from connectonion.cli.commands.gmail_draft_review import prepare_review, send_reviewed, DraftReviewError
    client, service = gmail
    review = prepare_review(client, 'draft-a')
    service.users().drafts().send().execute.side_effect = TimeoutError()
    with pytest.raises(DraftReviewError):
        send_reviewed(client, 'draft-a', review.token, directory=tmp_path)
    before = service.users().drafts().send().execute.call_count
    service.users().messages().list().execute.return_value = {'messages':[{'id':'recovered-a'}]}
    assert send_reviewed(client, 'draft-a', review.token, directory=tmp_path) == {'id':'recovered-a', 'recovered':True}
    assert service.users().drafts().send().execute.call_count == before


def test_review_has_provider_preserved_attempt_marker(gmail):
    from email import policy
    from email.parser import BytesParser
    from connectonion.cli.commands.gmail_draft_review import prepare_review
    client, _ = gmail
    review = prepare_review(client, 'draft-a')
    message = BytesParser(policy=policy.SMTP).parsebytes(base64.urlsafe_b64decode(review.raw))
    assert str(message['X-ConnectOnion-Send-Attempt']).strip() == review.token


@pytest.mark.parametrize('rewritten_result', ['single', 'duplicate', 'next_page', 'missing'])
def test_lost_response_recovers_only_unique_complete_marker_match(gmail, tmp_path, rewritten_result):
    from connectonion.cli.commands.gmail_draft_review import prepare_review, send_reviewed, DraftReviewError
    client, service = gmail
    review = prepare_review(client, 'draft-a')
    service.users().drafts().send().execute.side_effect = TimeoutError()
    with pytest.raises(DraftReviewError, match='uncertain'):
        send_reviewed(client, 'draft-a', review.token, directory=tmp_path)
    count = service.users().drafts().send().execute.call_count
    rows = [{'id': 'rewritten-a'}]
    if rewritten_result == 'duplicate':
        rows.append({'id': 'rewritten-b'})
    response = {'messages': rows}
    if rewritten_result == 'next_page':
        response['nextPageToken'] = 'more'
    service.users().messages().list().execute.side_effect = [{'messages': []}, response]
    marker = review.token if rewritten_result != 'missing' else 'unrelated'
    service.users().messages().get().execute.return_value = {
        'payload': {'headers': [{'name': 'x-connectonion-send-attempt', 'value': ' '+marker+' '}]}}
    if rewritten_result == 'single':
        assert send_reviewed(client, 'draft-a', review.token, directory=tmp_path) == {
            'id': 'rewritten-a', 'recovered': True}
    else:
        with pytest.raises(DraftReviewError, match='uncertain'):
            send_reviewed(client, 'draft-a', review.token, directory=tmp_path)
    assert service.users().drafts().send().execute.call_count == count
