"""Downloads preserve old bytes; uploads never retry ambiguous submissions."""
import hashlib
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from connectonion.useful_tools.synology_transfers import TransferMixin, local_target
from connectonion.useful_tools.synology_files import FileMixin
from connectonion.useful_tools.synology_transport import SynologyError, SynologyTransport


class NAS(TransferMixin, FileMixin, SynologyTransport):
    pass


@pytest.fixture
def nas():
    result = NAS('https://nas.test','one',sid='opaque')
    result._paths = {f'SYNO.FileStation.{api}':{'path':'entry.cgi','minVersion':2,'maxVersion':2}
                     for api in ('Download','Upload')}
    result.info = Mock(side_effect=lambda path: {'path':path,'type':'dir' if path=='/home' else 'file',
                       'size':3,'real_path':'/volume1'+path,'mount_point_type':None})
    return result


def test_local_destination_missing_trailing_slash_is_not_guessed(tmp_path):
    with pytest.raises(SynologyError, match='directory'):
        local_target(str(tmp_path/'missing')+'/', 'a')


def test_download_is_atomic_and_checks_length(nas, tmp_path):
    target = tmp_path/'a'
    target.write_bytes(b'old')
    nas._transport = httpx.MockTransport(lambda r: httpx.Response(200,content=b'ab',headers={'Content-Length':'2'}))
    result = nas.download('/home/a',str(target),overwrite=True)
    assert result['status'] == 'partial' and result['failed'][0]['code']=='length_mismatch'
    assert target.read_bytes()==b'old' and list(tmp_path.iterdir())==[target]


def test_download_defaults_to_conflict_and_dry_run_does_not_create_files(nas,tmp_path):
    target = tmp_path/'a'; target.write_bytes(b'old')
    nas._transport = httpx.MockTransport(lambda r: pytest.fail('must not download'))
    with pytest.raises(SynologyError) as error:
        nas.download('/home/a',str(target))
    assert error.value.code=='conflict'
    result = nas.download('/home/a',str(tmp_path/'b'),dry_run=True)
    assert result['dry_run'] and not (tmp_path/'b').exists()


def test_download_hash_and_zero_byte_files(nas,tmp_path):
    nas.info.side_effect = lambda p: {'path':p,'type':'file' if p=='/home/a' else 'dir',
                                    'size':0,'real_path':'/volume1'+p}
    nas._transport = httpx.MockTransport(lambda r: httpx.Response(200,content=b''))
    result = nas.download('/home/a',str(tmp_path))
    assert result['completed'][0]['sha256'] == hashlib.sha256(b'').hexdigest()
    assert (tmp_path/'a').read_bytes() == b''


def test_download_rejects_remote_scope_escape(nas,tmp_path):
    nas.info.side_effect = lambda p: {'path':p,'type':'file' if p=='/home/a' else 'dir',
                                    'size':3,'real_path':'/volume2/private' if p=='/home/a' else '/volume1/home'}
    with pytest.raises(SynologyError) as error:
        nas.download('/home/a',str(tmp_path))
    assert error.value.code == 'path_escape'


def test_download_rejects_local_symlink_parent(nas,tmp_path):
    (tmp_path/'real').mkdir(); (tmp_path/'link').symlink_to(tmp_path/'real',target_is_directory=True)
    with pytest.raises(SynologyError) as error:
        nas.download('/home/a',str(tmp_path/'link'/'a'),dry_run=True)
    assert error.value.code=='path_escape'


def test_upload_ambiguous_failure_is_not_retried(nas,tmp_path):
    source = tmp_path/'a'; source.write_bytes(b'new')
    nas._maybe_info = Mock(return_value=None)
    calls=[]
    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout('private transport detail')
    nas._transport = httpx.MockTransport(fail)
    result = nas.upload(str(source),'/home')
    assert len(calls)==1 and result['failed'][0]['code']=='submission_unknown'
    assert 'private transport' not in str(result)
    assert calls[0].url.params['_sid']=='opaque'
    assert b'name="file"' in calls[0].content


def test_upload_disallows_implicit_parent_creation(nas,tmp_path):
    source=tmp_path/'a'; source.write_bytes(b'new')
    nas._maybe_info = Mock(return_value=None)
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json={'success':True})
    nas._transport=httpx.MockTransport(respond)
    assert nas.upload(str(source),'/home')['status']=='complete'
    assert b'name="create_parents"\r\n\r\nfalse' in calls[0].content
    assert calls[0].content.index(b'name="overwrite"') < calls[0].content.index(b'name="file"')


def test_download_refreshes_only_explicit_stale_session_once(nas,tmp_path):
    calls=[]
    def respond(request):
        calls.append(request)
        if len(calls)==1:
            return httpx.Response(200,json={'success':False,'error':{'code':119}})
        return httpx.Response(200,content=b'new')
    nas._transport=httpx.MockTransport(respond)
    nas._login=Mock()
    result=nas.download('/home/a',str(tmp_path))
    assert result['status']=='complete' and len(calls)==2
    nas._login.assert_called_once()
    assert (tmp_path/'a').read_bytes()==b'new'


def test_recursive_download_preserves_empty_directories(nas,tmp_path):
    entries={
        '/home':{'path':'/home','type':'dir','real_path':'/volume1/home'},
        '/home/folder':{'path':'/home/folder','type':'dir','real_path':'/volume1/home/folder'},
        '/home/folder/empty':{'path':'/home/folder/empty','type':'dir','real_path':'/volume1/home/folder/empty'},
    }
    nas.info.side_effect=lambda path:entries[path]
    nas._list_raw=lambda p,*a: ([entries['/home/folder/empty']],1) if p=='/home/folder' else ([],0)
    result=nas.download('/home/folder',str(tmp_path),recursive=True)
    assert result['status']=='complete' and (tmp_path/'folder'/'empty').is_dir()
