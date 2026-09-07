"""Path, pagination, search lifetime and non-mutating file preflight contracts."""
from unittest.mock import Mock

import pytest

from connectonion.useful_tools.synology_files import FileMixin, nas_path
from connectonion.useful_tools.synology_state import SynologyState
from connectonion.useful_tools.synology_transport import SynologyError


@pytest.fixture
def nas(tmp_path):
    client = FileMixin()
    client.state = SynologyState('profile-one', tmp_path)
    client._request = Mock()
    client._remaining = lambda: 10
    client._deadline = 1e20
    return client


@pytest.mark.parametrize('path', ['relative', '/home/../other', '/home//a', '/home/./a', '/home/a\x00'])
def test_full_paths_reject_ambiguous_or_escaping_segments(path):
    with pytest.raises(SynologyError):
        nas_path(path)


def test_listing_orders_names_and_keeps_empty_file_size(nas):
    nas._request.return_value = {'total':3, 'files':[
        {'path':'/home/a', 'name':'a', 'isdir':False, 'additional':{'size':0}},
        {'path':'/home/b', 'name':'b', 'isdir':True}]}
    result = nas.list_page('/home', limit=2)
    assert nas._request.call_args.kwargs['sort_by'] == 'name'
    assert nas._request.call_args.kwargs['sort_direction'] == 'asc'
    assert result['items'][0]['size'] == 0 and result['items'][1]['size'] is None
    assert result['next_cursor'] and result['listing_id']
    assert result['snapshot'] is False
    assert nas.state.resolve('1', result['listing_id']) == '/home/a'


def test_cursors_reject_other_profiles_and_changed_parameters(nas, tmp_path):
    nas._request.return_value = {'total':2,'files':[{'path':'/home/a','name':'a','isdir':False}]}
    result = nas.list_page('/home', limit=1)
    with pytest.raises(SynologyError) as error:
        nas.list_page('/other', limit=1, cursor=result['next_cursor'])
    assert error.value.code == 'stale_cursor'
    other = SynologyState('profile-two', tmp_path)
    with pytest.raises(SynologyError):
        other.resolve('1', result['listing_id'])


def test_search_waits_for_complete_snapshot_then_cleans_before_paging(nas):
    nas._request.side_effect = [{'taskid':'task'}, {'finished':False},
        {'finished':True,'total':2,'files':[{'path':'/home/a','name':'a','isdir':False},
                                         {'path':'/home/b','name':'b','isdir':False}]}, {}]
    result = nas.search_page('a', '/home', limit=1, poll_interval=0)
    assert [c.args[1] for c in nas._request.call_args_list] == ['start','list','list','clean']
    assert nas._request.call_args_list[0].kwargs['pattern'] == '*a*'
    second = nas.search_page('a', '/home', limit=1, cursor=result['next_cursor'])
    assert second['items'][0]['path'] == '/home/b' and second['next_cursor'] is None
    assert nas._request.call_count == 4


def test_search_cleans_after_interrupt(nas):
    nas._request.side_effect = [{'taskid':'task'}, KeyboardInterrupt(), {}]
    with pytest.raises(KeyboardInterrupt):
        nas.search_page('a', '/home')
    assert nas._request.call_args.args[1] == 'clean'


def test_plain_search_does_not_silently_enable_globs(nas):
    with pytest.raises(SynologyError, match='--glob'):
        nas.search_page('*.pdf', '/home')
    nas._request.assert_not_called()


def test_info_keeps_realpath_for_boundary_checks(nas):
    nas._request.return_value = {'files':[{'path':'/home/a','name':'a','isdir':False,
                                         'additional':{'real_path':'/volume1/homes/one/a'}}]}
    assert nas.info('/home/a')['real_path'] == '/volume1/homes/one/a'


def test_mkdir_parents_never_creates_shared_roots(nas):
    with pytest.raises(SynologyError, match='shared'):
        nas.mkdir('/brand-new-share', parents=True)
    nas._request.assert_not_called()


def test_mkdir_dry_run_plans_missing_directories_without_writes(nas):
    def info(path):
        if path in {'/home','/home/docs'}:
            return {'path':path,'type':'dir'}
        raise SynologyError('Missing', 'not_found')
    nas.info = info
    result = nas.mkdir('/home/docs/new/empty', parents=True, dry_run=True)
    assert result['create'] == ['/home/docs/new','/home/docs/new/empty']
    nas._request.assert_not_called()
