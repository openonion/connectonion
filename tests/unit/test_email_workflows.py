from unittest.mock import patch
import json
import pytest
import typer
from connectonion.cli.commands import email_workflows as flow
MESSAGE={'id':7000,'from':'Alice <alice@example.com>','to':'me@example.com','subject':'Plan [draft]','message':'Hello\nWorld','timestamp':'2026-10-24'}
@pytest.mark.parametrize('to,prefix,recipient',[(None,'Re:','alice@example.com'),('bob@example.com','Fwd:','bob@example.com')])
def test_reply_and_forward_reuse_send_and_keep_idempotency(to,prefix,recipient):
    with patch.object(flow,'_read',return_value=MESSAGE),patch.object(flow,'handle_email_send') as send:
        flow.handle_email_reply('7000','My note',to=to,from_address='me@example.com',idempotency_key='retry-key')
    args=send.call_args.args
    assert args[0]==recipient and args[1]==prefix+' Plan [draft]'
    assert args[2].startswith('My note\n\n') and '> Hello\n> World' in args[2]
    assert send.call_args.kwargs=={'from_address':'me@example.com','idempotency_key':'retry-key'}
def test_reply_refuses_an_invalid_sender_without_sending():
    with patch.object(flow,'_read',return_value={**MESSAGE,'from':'not-an-email'}),patch.object(flow,'handle_email_send') as send:
        with pytest.raises(typer.Exit):flow.handle_email_reply('7000','note')
    send.assert_not_called()
@pytest.mark.parametrize('unread,method',[(False,'mark_read'),(True,'mark_unread')])
def test_both_read_states_reuse_the_existing_mail_tools(unread,method):
    with patch.object(flow,'_require_auth'),patch('connectonion.useful_tools.get_emails.'+method) as mutate:
        flow.handle_email_mark(['7','8'],unread=unread)
    assert [c.args for c in mutate.call_args_list]==[('7',),('8',)]
def test_all_ids_are_validated_before_any_write():
    with patch('connectonion.useful_tools.get_emails.mark_read') as mutate:
        with pytest.raises(typer.Exit):flow.handle_email_mark(['7','bad'])
    mutate.assert_not_called()
def test_search_reports_its_scope_and_treats_markup_as_text(capsys):
    with patch.object(flow,'_require_auth'),patch('connectonion.useful_tools.get_emails.get_emails',return_value=[MESSAGE]) as read:
        flow.handle_email_search('[draft]',last=100,offset=200,json_output=True)
    data=json.loads(capsys.readouterr().out)
    assert data['scanned']==1 and data['offset']==200 and data['emails'][0]['id']==7000
    read.assert_called_once_with(last=100,offset=200)
def test_tier_is_read_only_and_uses_the_existing_endpoint(capsys):
    with patch.object(flow,'_request',return_value={'tier':'free'}) as request:
        flow.handle_email_tier(json_output=True)
    request.assert_called_once_with('GET','tier')
    assert json.loads(capsys.readouterr().out)=={'tier':'free'}


def test_partial_bulk_update_reports_what_changed(capsys):
    import requests
    with patch.object(flow,'_require_auth'),patch('connectonion.useful_tools.get_emails.mark_read',side_effect=[True,requests.ConnectionError('private host')]):
        with pytest.raises(typer.Exit):flow.handle_email_mark(['7','8'])
    text=capsys.readouterr().out
    assert 'Updated 1 of 2 messages' in text and 'private host' not in text


def test_reply_uses_receiving_owned_address_and_preserves_payg_cap():
    with patch.object(flow,'_read',return_value=MESSAGE),patch.object(flow,'_request',return_value={'addresses':[{'address':'primary@example.com'},{'address':'me@example.com'}]}) as request,patch.object(flow,'handle_email_send') as send:
        flow.handle_email_reply('7000','My note',max_cost_usd='0.003',idempotency_key='reply-one')
    request.assert_called_once_with('GET','addresses')
    assert send.call_args.kwargs=={'from_address':'me@example.com','idempotency_key':'reply-one','max_cost_usd':'0.003'}


def test_send_status_does_not_post_or_resend(capsys):
    with patch.object(flow,'_request',return_value={'state':'unconfirmed','charged_usd':'0','reserved_usd':'0.003','message':'Check later'}) as request:
        flow.handle_email_send_status('send/one',True)
    request.assert_called_once_with('GET','send-status?idempotency_key=send%2Fone')
    assert json.loads(capsys.readouterr().out)['reserved_usd']=='0.003'


def test_invalid_status_key_refuses_before_network():
    with patch.object(flow,'_request') as request:
        with pytest.raises(typer.Exit):flow.handle_email_send_status('bad key')
    request.assert_not_called()
