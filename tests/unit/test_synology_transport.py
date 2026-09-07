"""Verified HTTPS, negotiated APIs, OTP and session persistence boundaries."""
import json
from unittest.mock import Mock

import httpx
import pytest

from connectonion.useful_tools.synology_transport import SynologyTransport, SynologyError


CAPABILITIES = {api:{'path':'entry.cgi','minVersion':1,'maxVersion':version}
                for api,version in [('SYNO.API.Auth',6), ('SYNO.FileStation.List',2)]}


def client(handler, **kwargs):
    nas = SynologyTransport(url='https://nas.test', account='one', password='password', **kwargs)
    nas._transport = httpx.MockTransport(handler)
    return nas


def handler_for(responses, calls):
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=responses.pop(0))
    return handle


def test_negotiates_path_and_posts_secrets_without_redirects():
    calls=[]
    nas = client(handler_for([
        {'success':True,'data':CAPABILITIES},
        {'success':True,'data':{'sid':'opaque'}},
        {'success':True,'data':{'shares':[]}},
    ], calls))
    assert nas._request('SYNO.FileStation.List','list_share')['shares'] == []
    assert 'password' not in str(calls[1].url)
    assert 'passwd=password' in calls[1].content.decode()
    assert '_sid=opaque' in calls[2].content.decode()
    assert nas.tls_verified is True


def test_login_is_ephemeral_until_explicit_profile_publication():
    saved = Mock()
    calls=[]
    nas = client(handler_for([
        {'success':True,'data':CAPABILITIES}, {'success':True,'data':{'sid':'opaque'}},
    ], calls), on_session=saved, persist=False)
    nas._login()
    saved.assert_not_called()


def test_otp_is_requested_once_and_never_persisted():
    saved=Mock(); otp=Mock(return_value='123456'); calls=[]
    nas=client(handler_for([
        {'success':True,'data':CAPABILITIES}, {'success':False,'error':{'code':403}},
        {'success':True,'data':{'sid':'opaque'}},
    ], calls), otp_callback=otp, on_session=saved)
    nas._login()
    otp.assert_called_once_with()
    assert 'otp_code=123456' in calls[-1].content.decode()
    saved.assert_called_once_with('opaque')


def test_noninteractive_otp_requirement_is_typed():
    nas=client(handler_for([
        {'success':True,'data':CAPABILITIES}, {'success':False,'error':{'code':403}},
    ], []))
    with pytest.raises(SynologyError) as error:
        nas._login()
    assert error.value.code == 'otp_required'


def test_api_paths_and_versions_are_checked_before_credentials_are_sent():
    nas=client(handler_for([{'success':True,'data':{
        'SYNO.API.Auth':{'path':'../../outside','minVersion':1,'maxVersion':6}}}], []))
    with pytest.raises(SynologyError) as error:
        nas._login()
    assert error.value.code == 'unsupported_api'


def test_redirect_does_not_forward_credentials():
    seen=[]
    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={'location':'https://other.test'})
    nas=client(handler)
    with pytest.raises(SynologyError):
        nas._login()
    assert len(seen) == 1


def test_ambiguous_mutation_is_not_retried():
    seen=[]
    def handler(request):
        seen.append(request)
        raise httpx.ReadTimeout('PRIVATE_SID_AND_BODY')
    nas=client(handler)
    nas._paths={'SYNO.FileStation.CreateFolder':{'path':'entry.cgi','minVersion':1,'maxVersion':2}}
    nas.sid='opaque'
    with pytest.raises(SynologyError) as error:
        nas._request('SYNO.FileStation.CreateFolder','create', folder_path='/home', name='new')
    assert error.value.code == 'submission_unknown'
    assert 'PRIVATE' not in str(error.value)
    assert len(seen) == 1


def test_explicit_rejected_stale_session_refreshes_only_once():
    calls=[]
    nas=client(handler_for([
        {'success':False,'error':{'code':106}}, {'success':True,'data':{'sid':'new'}},
        {'success':True,'data':{'shares':[]}},
    ], calls))
    nas.sid='old'; nas._paths=CAPABILITIES
    nas._request('SYNO.FileStation.List','list_share')
    assert len(calls)==3
    assert '_sid=new' in calls[-1].content.decode()


def test_http_permission_code_and_response_size_remain_categorical(monkeypatch):
    import connectonion.useful_tools.synology_transport as transport
    nas=client(lambda request: httpx.Response(403, text='PRIVATE'))
    with pytest.raises(SynologyError) as error:
        nas._login()
    assert error.value.code == 'permission_denied'
    monkeypatch.setattr(transport, 'MAX_RESPONSE_BYTES', 8)
    nas=client(lambda request: httpx.Response(200, content=b'x'*9))
    with pytest.raises(SynologyError) as error:
        nas._login()
    assert error.value.code == 'response_too_large'
