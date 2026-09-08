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
    nas._request.return_value = {'links':[{'id':'link','path':'/home/a','url':'https://nas.test/sharing/link','error':0}]}
    result = nas.share_create('/home/a',expires='2026-09-30',password='safe-test')
    assert result['url']=='https://nas.test/sharing/link'
    assert result['nas_timezone'] is None
    assert nas._request.call_args.kwargs['date_expired']=='"2026-09-30"'
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
