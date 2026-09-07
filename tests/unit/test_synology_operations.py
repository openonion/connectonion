"""Known async tasks survive restart; unknown submissions are never repeated."""
from unittest.mock import Mock

import pytest

from connectonion.useful_tools.synology_operations import OperationMixin
from connectonion.useful_tools.synology_files import FileMixin
from connectonion.useful_tools.synology_state import SynologyState
from connectonion.useful_tools.synology_transport import SynologyError


class NAS(OperationMixin,FileMixin):
    pass


@pytest.fixture
def nas(tmp_path):
    result=NAS(); result.state=SynologyState('one',tmp_path)
    result._api=Mock(); result._remaining=lambda: 10
    result._request=Mock()
    def info(path):
        if path in {'/home','/home/docs','/home/dest'}:
            return {'path':path,'type':'dir','real_path':'/volume1'+path}
        if path=='/home/docs/a':
            return {'path':path,'type':'file','real_path':'/volume1'+path}
        raise SynologyError('Missing','not_found')
    result.info=info
    result._remote_tree=lambda p,r: [info(p)]
    result._remote_boundary=lambda p: ('/home','/volume1/home')
    result._check_remote=lambda i,b: None
    return result


def test_copy_awaits_task_and_omits_overwrite_instead_of_silent_skip(nas):
    nas._request.side_effect=[{'taskid':'task'},{'finished':True}]
    result=nas.copy('/home/docs/a','/home/dest/')
    assert result['status']=='complete'
    assert nas._request.call_args_list[0].kwargs['overwrite'] is None
    assert nas._request.call_args_list[0].kwargs['remove_src'] is False


def test_pending_task_survives_restart_and_status_never_submits(nas):
    nas._request.side_effect=[{'taskid':'task'},SynologyError('Budget expired','timeout')]
    result=nas.move('/home/docs/a','/home/dest/')
    assert result['status']=='operation_pending' and result['operation_id']
    nas._request=Mock(return_value={'finished':True})
    result=nas.operation_status(result['operation_id'],wait=True)
    assert result['status']=='complete'
    assert [c.args[1] for c in nas._request.call_args_list]==['status']


def test_unknown_submission_does_not_claim_a_pollable_task_or_resubmit(nas):
    nas._request.side_effect=SynologyError('No response','submission_unknown')
    first=nas.copy('/home/docs/a','/home/dest/')
    assert first['status']=='submission_unknown' and first['task_id'] is None
    assert nas.copy('/home/docs/a','/home/dest/')['status']=='submission_unknown'
    assert nas._request.call_count==1


def test_exact_new_filename_uses_owned_staging_and_no_directory_merge(nas):
    nas._request.side_effect=[{}, {'taskid':'stage-task'}, {'finished':True}, {},
                             {'taskid':'place-task'}, {'finished':True}, {}]
    result=nas.move('/home/docs/a','/home/dest/final')
    assert result['status']=='complete'
    calls=nas._request.call_args_list
    assert [c.args[1] for c in calls]==['create','start','status','rename','start','status','delete']
    assert calls[-1].kwargs['recursive'] is False
    assert '/.co-operation-' in calls[-1].kwargs['path'][0]


def test_status_never_advances_into_new_write_stage(nas):
    nas._request.side_effect=[{}, {'taskid':'stage-task'},SynologyError('Expired','timeout')]
    pending=nas.move('/home/docs/a','/home/dest/final')
    nas._request=Mock(return_value={'finished':True})
    result=nas.operation_status(pending['operation_id'],wait=True)
    assert result['status']=='continuation_required'
    assert all(c.args[1]=='status' for c in nas._request.call_args_list)


def test_dry_run_never_creates_state_or_submits(nas):
    result=nas.copy('/home/docs/a','/home/dest/final',dry_run=True)
    assert result['dry_run']
    nas._request.assert_not_called()
    assert not nas.state.directory.exists() or not list(nas.state.directory.iterdir())


def test_self_descendant_and_missing_trailing_slash_are_rejected(nas):
    with pytest.raises(SynologyError) as error:
        nas.move('/home/docs','/home/docs/new')
    assert error.value.code=='path_conflict'
    with pytest.raises(SynologyError):
        nas.copy('/home/docs/a','/home/missing/')
