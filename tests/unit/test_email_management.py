from unittest.mock import patch,Mock
import time,json
import pytest
import typer
from connectonion import address
from connectonion.cli.commands import email_workflows as flow,email_transfer as transfer
SETTINGS={'addresses':[{'id':7,'address':'me@mail.openonion.ai'}],'prices':{'change_local_part':9.9,'change_domain':2.9}}
def test_address_change_preview_never_charges():
    with patch.object(flow,'_request',return_value=SETTINGS) as request:
        flow.handle_email_change('me@mail.openonion.ai',domain='steadmail.com')
    request.assert_called_once_with('GET','addresses')
def test_address_change_uses_owned_record_id():
    with patch.object(flow,'_request',side_effect=[SETTINGS,{'message':'Changed'}]) as request:
        flow.handle_email_change('me@mail.openonion.ai',name='new',buy=True)
    assert request.call_args.args==('PATCH','addresses/7')
    assert request.call_args.kwargs=={'json':{'local_part':'new'}}
def test_quota_buy_requires_explicit_idempotency_key():
    with patch.object(flow,'_request') as request:
        with pytest.raises(typer.Exit):flow.handle_email_quota(buy=True)
    request.assert_not_called()
def test_quota_purchase_reuses_the_given_key():
    with patch.object(flow,'_request',return_value={}) as request:
        flow.handle_email_quota(buy=True,idempotency_key='quota-test')
    request.assert_called_once_with('POST','purchase-quota',headers={'Idempotency-Key':'quota-test'})
def test_purge_default_is_preview_without_network():
    with patch.object(flow,'_request') as request:flow.handle_email_delete_history('me@mail.openonion.ai')
    request.assert_not_called()
def test_purge_targets_only_named_address_and_explicit_scope():
    with patch.object(flow,'_request',return_value={}) as request:flow.handle_email_delete_history('me@mail.openonion.ai',yes=True)
    assert request.call_args.args==('DELETE','addresses/me%40mail.openonion.ai/mail')
    assert request.call_args.kwargs['params']=={'include_sent':'false'}
def approved(tmp_path):
    owner,recipient=address.generate(),address.generate()
    request,approval=tmp_path/'request.json',tmp_path/'approval.json'
    with patch.object(transfer,'_identity',return_value=owner):transfer.prepare('me@mail.openonion.ai',recipient['address'],request)
    with patch.object(transfer,'_identity',return_value=recipient):transfer.accept(request,approval)
    return request,approval,owner,recipient
def test_transfer_requires_both_keys_and_uses_backend_protocol(tmp_path):
    request,approval,owner,recipient=approved(tmp_path)
    data=json.loads(approval.read_text())
    expected=f"ConnectOnion-Transfer-Address-me@mail.openonion.ai-and-its-mail-from-{owner['address']}-to-{recipient['address']}-{data['timestamp']}"
    assert transfer.transfer_message(data)==expected
    assert address.verify(owner['address'],expected.encode(),bytes.fromhex(data['from_signature']))
    assert address.verify(recipient['address'],expected.encode(),bytes.fromhex(data['to_signature']))
    assert approval.stat().st_mode&0o777==0o600
    with patch.object(transfer.requests,'post') as send:transfer.complete(approval)
    send.assert_not_called()
def test_transfer_rejects_tampering_expiry_and_wrong_recipient(tmp_path):
    request,approval,owner,recipient=approved(tmp_path)
    data=json.loads(approval.read_text());data['address']='other@mail.openonion.ai'
    with pytest.raises(ValueError,match='signature'):transfer._validate(data,complete=True)
    data=json.loads(approval.read_text());data['timestamp']=int(time.time())-301
    with pytest.raises(ValueError,match='expired'):transfer._validate(data,complete=True)
    with patch.object(transfer,'_identity',return_value=owner):
        with pytest.raises(ValueError,match='recipient'):transfer.accept(request,tmp_path/'wrong.json')
def test_transfer_does_not_overwrite_a_signature_file(tmp_path):
    request,approval,owner,recipient=approved(tmp_path)
    with patch.object(transfer,'_identity',return_value=owner):
        with pytest.raises(FileExistsError):transfer.prepare('me@mail.openonion.ai',recipient['address'],request)
def test_transfer_submission_requires_explicit_yes(tmp_path):
    request,approval,*_=approved(tmp_path)
    response=Mock(ok=True);response.json.return_value={'moved':{'email_addresses':1}}
    with patch.object(transfer.requests,'post',return_value=response) as send:transfer.complete(approval,yes=True)
    assert send.call_args.args[0].endswith('/addresses/transfer')
    assert 'to_signature' in send.call_args.kwargs['json']


def test_case_only_name_does_not_change_domain_only_price(capsys):
    with patch.object(flow,'_request',return_value=SETTINGS):flow.handle_email_change('me@mail.openonion.ai',name='ME',domain='steadmail.com')
    output=capsys.readouterr().out
    assert '$2.90' in output and '$9.90' not in output

def test_quota_retry_header_reaches_authenticated_transport():
    response=Mock(ok=True);response.json.return_value={}
    with patch.object(flow,'load_api_key',return_value='test-token'),patch.object(flow.requests,'request',return_value=response) as request:
        flow._request('POST','purchase-quota',headers={'Idempotency-Key':'same-key'})
    assert request.call_args.kwargs['headers']=={'Authorization':'Bearer test-token','Idempotency-Key':'same-key'}
