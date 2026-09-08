"""Public parser, JSON, account context, scopes and partial mutation outcomes."""
import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import gmail_commands as gm


@pytest.fixture
def client(tmp_path, monkeypatch):
    client = MagicMock()
    client.get_account_email.return_value = 'me@example.test'
    client._credentials.scopes = {'gmail.modify'}
    client.message_page.return_value = {'items':[], 'truncated':False, 'next_cursor':None, 'total_estimate':0, 'complete':True}
    client.read_message.return_value = {'id':'message-id', 'body':'Hello', 'headers':{}, 'body_truncated':False}
    monkeypatch.setattr(gm, '_gmail', lambda:client)
    monkeypatch.setattr(gm, 'INBOX_CACHE', tmp_path/'legacy.json')
    return client


@pytest.mark.parametrize('args,method', [
    (['mark','message-id','--read'],'mark_read'), (['mark','message-id','--unread'],'mark_unread'),
    (['star','message-id'],'star_email'), (['star','message-id','--remove'],'unstar_email'),
    (['archive','message-id'],'archive_email'),
    (['label','add','message-id','Projects'],'add_label'), (['label','remove','message-id','Projects'],'remove_label')])
def test_actions_route_and_emit_one_complete_envelope(client, args, method):
    getattr(client, method).return_value = 'done'
    result = CliRunner().invoke(app, ['gmail', *args, '--json'])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data['schema_version'] == 1 and data['account'] == 'me@example.test'
    assert data['complete'] is True and data['data']['id'] == 'message-id'
    assert result.stderr == ''
    assert getattr(client, method).call_args.args == ('message-id',)


@pytest.mark.parametrize('args', [['mark','id'], ['mark','id','--read','--unread'],
    ['download','id','--to','.'], ['download','id','--to','.','--all','--attachment','a'],
    ['inbox','--last','501'], ['read']])
def test_json_usage_failures_are_exit_two_without_provider_access(client, args):
    result = CliRunner().invoke(app, ['gmail', *args, '--json'])
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)['error']['code'] == 'usage_error'
    client.get_account_email.assert_not_called()


def test_read_json_does_not_mutate_unless_requested(client):
    result = CliRunner().invoke(app, ['gmail','read','message-id','--json'])
    assert result.exit_code == 0
    assert json.loads(result.stdout)['data']['body'] == 'Hello'
    client.mark_read.assert_not_called()


def test_known_readonly_grant_blocks_mutation_and_returns_typed_error(client):
    client._credentials.scopes = {'gmail.readonly'}
    result = CliRunner().invoke(app, ['gmail','read','message-id','--mark-read','--json'])
    assert result.exit_code == 1
    assert json.loads(result.stdout)['error']['code'] == 'permission_denied'
    client.mark_read.assert_not_called()


def test_unknown_scope_metadata_allows_provider_authority(client):
    client._credentials.scopes = set()
    client.mark_read.return_value = 'done'
    result = CliRunner().invoke(app, ['gmail','mark','message-id','--read','--json'])
    assert result.exit_code == 0
    client.mark_read.assert_called_once_with('message-id')


def test_partial_download_is_nonzero_with_successes_preserved(client):
    client.download_attachments.return_value = {'complete':False, 'items':[
        {'id':'one', 'status':'saved', 'path':'/tmp/one'},
        {'id':'two', 'status':'failed', 'error':{'code':'size_mismatch'}}]}
    result = CliRunner().invoke(app, ['gmail','download','message-id','--all','--to','.', '--json'])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data['status'] == 'partial'
    assert len(data['data']['items']) == 2


def test_inbox_json_exposes_pagination_and_full_ids(client):
    client.message_page.return_value['items'] = [{'id':'full-very-long-message-id'}]
    result = CliRunner().invoke(app, ['gmail','inbox','--json'])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data['data']['items'][0]['id'] == 'full-very-long-message-id'
    assert data['next_command'] == 'co gmail read full-very-long-message-id'


def test_cursor_is_forwarded_with_original_search(client):
    result = CliRunner().invoke(app, ['gmail','search','in:sent','--last','4','--cursor','cursor', '--json'])
    assert result.exit_code == 0, result.output
    client.message_page.assert_called_once_with('in:sent', last=4, cursor='cursor')
