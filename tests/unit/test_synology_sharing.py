from unittest.mock import Mock

import pytest

from connectonion.useful_tools.synology_sharing import SharingMixin
from connectonion.useful_tools.synology_state import SynologyState
from connectonion.useful_tools.synology_transport import SynologyError


@pytest.fixture
def nas(tmp_path):
    result = SharingMixin()
    result.state = SynologyState('one',tmp_path)
    result._api = Mock()
    result.info = Mock(return_value={'path':'/home/a','type':'file'})
    result._request = Mock()
    return result


def test_create_requires_expiry_and_does_not_truncate_password(nas):
    with pytest.raises(SynologyError):
        nas.share_create('/home/a')
    with pytest.raises(SynologyError):
        nas.share_create('/home/a',no_expiry=True,password='a'*17)
    nas._request.assert_not_called()


def test_create_applies_exact_expiry_and_returns_only_its_url(nas):
    nas._request.side_effect = [
        {'links':[{'id':'link','path':'/home/a','url':'https://nas.test/sharing/link','error':0}]},
        {'id':'link','path':'/home/a','url':'https://nas.test/sharing/link',
         'has_password':True,'date_expired':'2026-09-30 23:59:59','status':'valid'},
    ]
    result = nas.share_create('/home/a',expires='2026-09-30',password='safe-test')
    assert result['url']=='https://nas.test/sharing/link'
    assert result['nas_timezone'] is None
    assert nas._request.call_args_list[0].kwargs['date_expired']=='"2026-09-30"'
    assert result['expires']=='2026-09-30 23:59:59'
    assert nas._request.call_args_list[1].args[1]=='getinfo'
    assert 'safe-test' not in str(result)


def test_list_masks_bearer_url_by_default_and_binds_pagination(nas):
    nas._request.return_value = {'total':2,'links':[{'id':'link','path':'/home/a',
        'url':'https://nas.test/sharing/bearer','date_expired':'0','has_password':True,'status':'valid'}]}
    result=nas.share_list(limit=1)
    assert 'bearer' not in str(result) and result['items'][0]['protected'] is True
    with pytest.raises(SynologyError):
        nas.share_list(limit=2,cursor=result['next_cursor'])


def test_revoke_inspects_link_and_never_deletes_source(nas):
    nas._request.side_effect = [{'id':'link','path':'/home/a'},{}]
    result = nas.share_revoke('link')
    assert result['revoked']=='link'
    assert all(call.args[0]=='SYNO.FileStation.Sharing' for call in nas._request.call_args_list)
    assert nas._request.call_args.kwargs['id']==['link']


def test_dry_run_does_not_create_or_revoke(nas):
    assert nas.share_create('/home/a',no_expiry=True,dry_run=True)['dry_run']
    nas._request.assert_not_called()
    nas._request.return_value={'id':'link','path':'/home/a'}
    assert nas.share_revoke('link',dry_run=True)['dry_run']
    assert nas._request.call_args.args[1]=='getinfo'


@pytest.mark.parametrize('changed', [{'has_password':False}, {'date_expired':'0'}])
def test_create_rejects_and_revokes_a_link_with_wrong_protection(nas,changed):
    info={'id':'link','path':'/home/a','url':'https://nas.test/sharing/link',
          'has_password':True,'date_expired':'2026-09-30 23:59:59',**changed}
    nas._request.side_effect=[{'links':[{'id':'link','path':'/home/a','url':info['url']}]},info,{}]
    with pytest.raises(SynologyError) as error:
        nas.share_create('/home/a',expires='2026-09-30',password='safe-test')
    assert error.value.code=='share_verification_failed'
    assert nas._request.call_args.args[1]=='delete'
    assert nas._request.call_args.kwargs['id']==['link']


def test_create_does_not_revoke_a_readback_from_another_path(nas):
    nas._request.side_effect=[{'links':[{'id':'link','path':'/home/a','url':'https://nas.test/sharing/link'}]},
                              {'id':'link','path':'/other/private','has_password':False,'date_expired':'0'}]
    with pytest.raises(SynologyError) as error:
        nas.share_create('/home/a',no_expiry=True,password='safe-test')
    assert error.value.code=='submission_unknown'
    assert [call.args[1] for call in nas._request.call_args_list]==['create','getinfo']


def test_readback_failure_never_repeats_creation(nas):
    nas._request.side_effect=[{'links':[{'id':'link','path':'/home/a','url':'https://nas.test/sharing/link'}]},
                             SynologyError('Readback timed out','timeout')]
    with pytest.raises(SynologyError) as error:
        nas.share_create('/home/a',no_expiry=True)
    assert error.value.code=='submission_unknown'
    assert [call.args[1] for call in nas._request.call_args_list]==['create','getinfo']


@pytest.mark.parametrize('expiry', [[], {}, ['0'], False])
def test_malformed_no_expiry_readback_revokes_only_new_link(nas, expiry):
    nas._request.side_effect = [
        {'links':[{'id':'link','path':'/home/a'}]},
        {'id':'link','path':'/home/a','has_password':False,'date_expired':expiry},
        {},
    ]
    with pytest.raises(SynologyError) as error:
        nas.share_create('/home/a',no_expiry=True)
    assert error.value.code == 'share_verification_failed'
    assert nas._request.call_args.kwargs['id'] == ['link']


@pytest.mark.parametrize('cleanup', [{'errors':[{'code':105}]}, SynologyError('timeout','timeout')])
def test_failed_protection_cleanup_never_claims_link_was_revoked(nas, cleanup):
    nas._request.side_effect = [
        {'links':[{'id':'link','path':'/home/a'}]},
        {'id':'link','path':'/home/a','has_password':False,'date_expired':'0'},
        cleanup,
    ]
    with pytest.raises(SynologyError) as error:
        nas.share_create('/home/a',no_expiry=True,password='safe-test')
    assert error.value.code == 'submission_unknown'
    assert 'unconfirmed' in str(error.value)
    assert [call.args[1] for call in nas._request.call_args_list] == ['create','getinfo','delete']


@pytest.mark.parametrize('missing', ['date_expired','has_password'])
def test_absent_security_metadata_is_not_verified(nas, missing):
    info={'id':'link','path':'/home/a','has_password':False,'date_expired':'0'}
    del info[missing]
    nas._request.side_effect=[{'links':[{'id':'link','path':'/home/a'}]},info,{}]
    with pytest.raises(SynologyError) as error:
        nas.share_create('/home/a',no_expiry=True)
    assert error.value.code == 'share_verification_failed'


def test_missing_created_url_requires_inspection_not_repeated_creation(nas):
    nas._request.side_effect=[{'links':[{'id':'link','path':'/home/a'}]},
                             {'id':'link','path':'/home/a','has_password':False,'date_expired':'0'}]
    with pytest.raises(SynologyError) as error:
        nas.share_create('/home/a',no_expiry=True)
    assert error.value.code == 'submission_unknown'
    assert nas._request.call_count == 2


@pytest.mark.parametrize('expiry', ['', '0', 0, None])
def test_no_expiry_accepts_dsm_sentinel_and_reports_null(nas, expiry):
    nas._request.side_effect=[{'links':[{'id':'link','path':'/home/a'}]},
                             {'id':'link','path':'/home/a','has_password':False,
                              'date_expired':expiry,'url':'https://nas.test/sharing/link'}]
    result=nas.share_create('/home/a',no_expiry=True)
    assert result['expires'] is None
    assert result['settings_verified'] is True
    assert nas._request.call_count == 2
