"""Incremental Asana collection, tested with synthetic tasks and an offline Asana client."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import socket

import pytest

from connectonion.useful_tools import asana_export as export
from connectonion.useful_tools.asana import AsanaError


pytestmark = pytest.mark.unit
START = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
ACCOUNT = '100'
PROJECT = '200'
OTHER_PROJECT = '201'
TASK = '300'


def _task(gid=TASK, **fields):
    task = {'gid': gid, 'name': 'Lecture notes', 'notes': '原文\n[red]literal[/red]',
            'completed': False, 'due_on': None, 'assignee': None,
            'modified_at': '2026-10-01T10:00:00Z', 'projects': [{'gid': PROJECT}]}
    task.update(fields)
    return task


def _story(gid='400', **fields):
    story = {'gid': gid, 'resource_subtype': 'comment_added',
             'created_at': '2026-10-01T10:01:00Z', 'text': '评论 🙂'}
    story.update(fields)
    return story


class FakeAsana:
    """Return independent copies, with failures at the public client boundary."""

    def __init__(self):
        self.account = ACCOUNT
        self.projects = {PROJECT: [TASK]}
        self.tasks = {TASK: _task()}
        self.stories = {TASK: [_story()]}
        self.calls = []
        self.failure = None
        self.on_list = None

    def _call(self, method, ref=None):
        self.calls.append((method, ref))
        if self.failure == (method, ref):
            raise AsanaError('Synthetic upstream failure', 'co asana check', status=500)

    def get_user(self):
        self._call('user')
        return {'gid': self.account, 'name': 'Synthetic user'}

    def list_tasks(self, project_gid, *, modified_since=None):
        self._call('list', project_gid)
        self.calls.append(('since', project_gid, modified_since))
        if self.on_list:
            self.on_list()
        return [{'gid': gid} for gid in self.projects.get(project_gid, [])]

    def get_task(self, task_gid):
        self._call('task', task_gid)
        return deepcopy(self.tasks[task_gid])

    def list_stories(self, task_gid):
        self._call('stories', task_gid)
        return deepcopy(self.stories.get(task_gid, []))


@pytest.fixture(autouse=True)
def isolated_export(monkeypatch, tmp_path):
    """No real credentials, network, clock or personal source directories."""
    monkeypatch.delenv('ASANA_ACCESS_TOKEN', raising=False)
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    monkeypatch.chdir(tmp_path)
    attempts = []

    def refuse_network(*args, **kwargs):
        attempts.append(True)
        pytest.fail('Export tests must not connect to a network')

    monkeypatch.setattr(socket.socket, 'connect', refuse_network)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse_network)
    monkeypatch.setattr(socket, 'create_connection', refuse_network)
    clock = [START]
    monkeypatch.setattr(export, '_now', lambda: clock[0])
    yield clock
    assert not attempts


@pytest.fixture
def client():
    return FakeAsana()


def _selected(source, projects=None, account=ACCOUNT):
    return export.latest_snapshots(source, account_gid=account,
                                   project_gids=[PROJECT] if projects is None else projects)


def _loaded(source, projects=None):
    return export.load_snapshots(source, _selected(source, projects))


def _records(source):
    return [json.loads(line) for path in sorted((source / 'daily').rglob('*.jsonl'))
            for line in path.read_text(encoding='utf-8').splitlines()]


def _time(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))


def test_first_run_preserves_task_details_and_all_stories(tmp_path, client):
    client.stories[TASK].append(_story('401', resource_subtype='marked_complete', text='Done'))
    original = deepcopy((client.tasks, client.stories))
    source = tmp_path / 'asana'
    result = export.sync_tasks(client, source, [PROJECT])
    assert result['appended_records'] == 1
    assert _loaded(source)[0]['task'] == client.tasks[TASK]
    assert _loaded(source)[0]['stories'] == client.stories[TASK]
    assert export.export_status(source)['record_count'] == 1
    assert (client.tasks, client.stories) == original
    assert ('since', PROJECT, None) in client.calls


def test_first_run_includes_completed_and_old_tasks(tmp_path, client):
    client.tasks[TASK].update(completed=True, modified_at='2001-01-01T00:00:00Z')
    export.sync_tasks(client, tmp_path, [PROJECT])
    assert _loaded(tmp_path)[0]['task']['completed'] is True
    assert ('since', PROJECT, None) in client.calls


def test_unchanged_run_appends_nothing(tmp_path, client, isolated_export):
    export.sync_tasks(client, tmp_path, [PROJECT])
    before = {p: p.read_bytes() for p in tmp_path.rglob('*.jsonl')}
    isolated_export[0] += timedelta(hours=1)
    result = export.sync_tasks(client, tmp_path, [PROJECT])
    assert result['appended_records'] == 0
    assert export.export_status(tmp_path)['record_count'] == 1
    assert {p: p.read_bytes() for p in tmp_path.rglob('*.jsonl')} == before


@pytest.mark.parametrize('field,value', [
    ('name', 'Changed'), ('notes', 'Updated\n正文'), ('completed', True),
    ('due_on', '2026-12-01'), ('assignee', {'gid': '500', 'name': 'Alice'}),
])
def test_task_change_appends_one_latest_snapshot(tmp_path, client, field, value):
    export.sync_tasks(client, tmp_path, [PROJECT])
    client.tasks[TASK][field] = value
    result = export.sync_tasks(client, tmp_path, [PROJECT])
    assert result['appended_records'] == 1
    assert export.export_status(tmp_path)['record_count'] == 2
    assert _loaded(tmp_path)[0]['task'][field] == value


@pytest.mark.parametrize('change', ['add', 'edit', 'delete'])
def test_story_change_versions_a_listed_task(tmp_path, client, change):
    export.sync_tasks(client, tmp_path, [PROJECT])
    version = _selected(tmp_path)[0]['content_version']
    if change == 'add':
        client.stories[TASK].append(_story('401'))
    elif change == 'edit':
        client.stories[TASK][0]['text'] = 'Edited comment'
    else:
        client.stories[TASK] = []
    assert export.sync_tasks(client, tmp_path, [PROJECT])['appended_records'] == 1
    assert _selected(tmp_path)[0]['content_version'] != version
    assert _loaded(tmp_path)[0]['stories'] == client.stories[TASK]


def test_unlisted_task_is_not_polled_for_comment_changes(tmp_path, client):
    export.sync_tasks(client, tmp_path, [PROJECT])
    client.projects[PROJECT] = []
    client.stories[TASK].append(_story('401'))
    client.calls.clear()
    assert export.sync_tasks(client, tmp_path, [PROJECT])['appended_records'] == 0
    assert not any(call[0] in ('task', 'stories') for call in client.calls)
    assert export.export_status(tmp_path)['record_count'] == 1


def test_return_to_previous_content_is_a_new_change(tmp_path, client):
    original = deepcopy(client.tasks[TASK])
    export.sync_tasks(client, tmp_path, [PROJECT])
    first = _selected(tmp_path)[0]
    client.tasks[TASK]['name'] = 'B'
    export.sync_tasks(client, tmp_path, [PROJECT])
    second = _selected(tmp_path)[0]
    client.tasks[TASK] = original
    export.sync_tasks(client, tmp_path, [PROJECT])
    third = _selected(tmp_path)[0]
    assert export.export_status(tmp_path)['record_count'] == 3
    assert first['content_version'] == third['content_version'] != second['content_version']
    assert len({row['change_id'] for row in (first, second, third)}) == 3


def test_shared_task_is_read_and_saved_once_per_run(tmp_path, client):
    client.projects[OTHER_PROJECT] = [TASK, TASK]
    client.tasks[TASK]['projects'].append({'gid': OTHER_PROJECT})
    result = export.sync_tasks(client, tmp_path, [PROJECT, OTHER_PROJECT])
    assert result['appended_records'] == 1
    assert client.calls.count(('task', TASK)) == 1
    assert client.calls.count(('stories', TASK)) == 1
    assert set(_loaded(tmp_path, [PROJECT, OTHER_PROJECT])[0]['project_gids']) == {PROJECT, OTHER_PROJECT}


def test_identical_content_does_not_merge_distinct_task_ids(tmp_path, client):
    client.projects[PROJECT].append('301')
    client.tasks['301'] = _task('301')
    result = export.sync_tasks(client, tmp_path, [PROJECT])
    assert result['appended_records'] == 2
    assert {row['task']['gid'] for row in _loaded(tmp_path)} == {TASK, '301'}


def test_each_project_has_its_own_checkpoint_and_new_projects_are_full_reads(tmp_path, client, isolated_export):
    export.sync_tasks(client, tmp_path, [PROJECT])
    isolated_export[0] += timedelta(hours=2)
    client.projects[OTHER_PROJECT] = []
    client.calls.clear()
    export.sync_tasks(client, tmp_path, [PROJECT, OTHER_PROJECT])
    since = {call[1]: call[2] for call in client.calls if call[0] == 'since'}
    assert _time(since[PROJECT]) == START - timedelta(minutes=5)
    assert since[OTHER_PROJECT] is None
    assert all(_time(value) == isolated_export[0]
               for value in export.export_status(tmp_path)['checkpoints'].values())
    isolated_export[0] += timedelta(hours=1)
    export.sync_tasks(client, tmp_path, [PROJECT])
    checkpoints = export.export_status(tmp_path)['checkpoints']
    assert _time(checkpoints[PROJECT]) == START + timedelta(hours=3)
    assert _time(checkpoints[OTHER_PROJECT]) == START + timedelta(hours=2)


def test_checkpoint_and_daily_file_use_start_time_even_across_midnight(tmp_path, client, isolated_export):
    started = datetime(2026, 11, 1, 23, 59, 59, tzinfo=timezone.utc)
    isolated_export[0] = started
    client.on_list = lambda: isolated_export.__setitem__(0, started + timedelta(minutes=2))
    export.sync_tasks(client, tmp_path, [PROJECT])
    assert _time(export.export_status(tmp_path)['checkpoints'][PROJECT]) == started
    assert [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*.jsonl')] == ['daily/2026/11/01.jsonl']
    assert _time(_loaded(tmp_path)[0]['collected_at']) == started


@pytest.mark.parametrize('text', ['', '中文 🙂', 'line one\nline two\r\n',
                                'Keep [red]literal[/red] tags', '"quote" \\ path\tend'])
def test_jsonl_preserves_literal_content_and_uses_byte_locators(tmp_path, client, text):
    client.tasks[TASK]['notes'] = text
    export.sync_tasks(client, tmp_path, [PROJECT])
    item = _selected(tmp_path)[0]
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', item['content_version'])
    locator = item['locator']
    assert item['change_id'] == f"asana:{ACCOUNT}:{TASK}:{locator['file']}:{locator['offset']}"
    raw = (tmp_path / locator['file']).read_bytes()
    record = json.loads(raw[locator['offset']:locator['offset'] + locator['length']])
    assert record['task_gid'] == TASK
    assert record['task']['notes'] == text
    assert _loaded(tmp_path)[0]['task']['notes'] == text
    assert len(raw.splitlines()) == 1


@pytest.mark.parametrize('method,ref', [('user', None), ('list', PROJECT),
                                       ('task', TASK), ('stories', TASK)])
def test_upstream_failure_keeps_committed_views_and_progress(tmp_path, client, method, ref):
    export.sync_tasks(client, tmp_path, [PROJECT])
    before = export.export_status(tmp_path)
    selected = _selected(tmp_path)
    loaded = _loaded(tmp_path)
    client.tasks[TASK]['name'] = 'New version'
    client.failure = (method, ref)
    with pytest.raises(AsanaError, match='Synthetic upstream failure'):
        export.sync_tasks(client, tmp_path, [PROJECT])
    after = export.export_status(tmp_path)
    assert after['last_failure'] is not None
    assert {k: v for k, v in after.items() if k != 'last_failure'} == {
        k: v for k, v in before.items() if k != 'last_failure'}
    assert _selected(tmp_path) == selected
    assert export.load_snapshots(tmp_path, selected) == loaded
    client.failure = None
    assert export.sync_tasks(client, tmp_path, [PROJECT])['appended_records'] == 1
    assert export.sync_tasks(client, tmp_path, [PROJECT])['appended_records'] == 0
    assert export.export_status(tmp_path)['record_count'] == 2
    assert export.export_status(tmp_path)['last_failure'] is None


def test_later_task_failure_does_not_publish_earlier_task(tmp_path, client):
    export.sync_tasks(client, tmp_path, [PROJECT])
    client.projects[PROJECT].append('301')
    client.tasks['301'] = _task('301')
    client.tasks[TASK]['name'] = 'Changed'
    client.failure = ('stories', '301')
    before = _selected(tmp_path)
    with pytest.raises(AsanaError):
        export.sync_tasks(client, tmp_path, [PROJECT])
    assert _selected(tmp_path) == before
    assert export.export_status(tmp_path)['record_count'] == 1
    client.failure = None
    assert export.sync_tasks(client, tmp_path, [PROJECT])['appended_records'] == 2


def test_failed_state_publish_hides_tail_and_retry_commits_once(tmp_path, client, monkeypatch):
    export.sync_tasks(client, tmp_path, [PROJECT])
    before = export.export_status(tmp_path)
    selected = _selected(tmp_path)
    loaded = _loaded(tmp_path)
    client.tasks[TASK]['name'] = 'Changed'
    replace = os.replace
    failed = []

    def fail_once(src, dst, *args, **kwargs):
        if Path(dst).name == 'state.json' and not failed:
            failed.append(True)
            raise OSError('Synthetic state publication failure')
        return replace(src, dst, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', fail_once)
        with pytest.raises(export.AsanaStoreError):
            export.sync_tasks(client, tmp_path, [PROJECT])
    assert failed
    after = export.export_status(tmp_path)
    assert {k: v for k, v in after.items() if k != 'last_failure'} == {
        k: v for k, v in before.items() if k != 'last_failure'}
    assert _selected(tmp_path) == selected
    assert export.load_snapshots(tmp_path, selected) == loaded
    assert export.sync_tasks(client, tmp_path, [PROJECT])['appended_records'] == 1
    assert export.sync_tasks(client, tmp_path, [PROJECT])['appended_records'] == 0
    assert len(_records(tmp_path)) == 2


def test_uncommitted_tail_is_invisible_and_removed_on_next_write(tmp_path, client):
    export.sync_tasks(client, tmp_path, [PROJECT])
    selected = _selected(tmp_path)
    file = tmp_path / selected[0]['locator']['file']
    with file.open('ab') as stream:
        stream.write(b'{"interrupted":')
    assert export.load_snapshots(tmp_path, selected)[0]['task'] == client.tasks[TASK]
    assert export.export_status(tmp_path)['record_count'] == 1
    client.tasks[TASK]['name'] = 'Changed'
    export.sync_tasks(client, tmp_path, [PROJECT])
    assert len(_records(tmp_path)) == 2


def test_status_and_snapshot_selection_do_not_read_daily_bodies(tmp_path, client, monkeypatch):
    export.sync_tasks(client, tmp_path, [PROJECT])
    selected = _selected(tmp_path)
    original = Path.open

    def refuse_daily(path, *args, **kwargs):
        assert path.suffix != '.jsonl', 'Metadata query opened a daily record'
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', refuse_daily)
    assert export.export_status(tmp_path)['record_count'] == 1
    assert _selected(tmp_path) == selected


def test_inspecting_missing_source_creates_nothing(tmp_path):
    source = tmp_path / 'missing'
    assert export.export_status(source)['initialized'] is False
    assert _selected(source) == []
    assert not source.exists()


def test_empty_success_is_distinct_from_never_collected(tmp_path, client):
    client.projects[PROJECT] = []
    export.sync_tasks(client, tmp_path, [PROJECT])
    status = export.export_status(tmp_path)
    assert status['initialized'] is True
    assert status['record_count'] == 0
    assert status['last_success_at'] is not None
    assert _selected(tmp_path) == []


@pytest.mark.parametrize('selection', [[], [''], ['abc'], ['../200']])
def test_invalid_project_selection_has_no_side_effects(tmp_path, client, selection):
    source = tmp_path / 'new'
    with pytest.raises(ValueError):
        export.sync_tasks(client, source, selection)
    assert not source.exists()
    assert client.calls == []


def test_other_account_cannot_read_or_overwrite_saved_material(tmp_path, client):
    export.sync_tasks(client, tmp_path, [PROJECT])
    selected = _selected(tmp_path)
    daily = {p: p.read_bytes() for p in tmp_path.rglob('*.jsonl')}
    client.account = '101'
    with pytest.raises(export.AsanaStoreError):
        export.sync_tasks(client, tmp_path, [PROJECT])
    with pytest.raises(export.AsanaStoreError):
        _selected(tmp_path, account='101')
    assert _selected(tmp_path) == selected
    assert {p: p.read_bytes() for p in tmp_path.rglob('*.jsonl')} == daily


def test_project_queries_only_return_matching_tasks(tmp_path, client):
    client.projects[OTHER_PROJECT] = ['301']
    client.tasks['301'] = _task('301', projects=[{'gid': OTHER_PROJECT}])
    export.sync_tasks(client, tmp_path, [PROJECT, OTHER_PROJECT])
    assert [row['task']['gid'] for row in _loaded(tmp_path)] == [TASK]
    assert [row['task']['gid'] for row in _loaded(tmp_path, [OTHER_PROJECT])] == ['301']


@pytest.mark.parametrize('damage', ['missing', 'short', 'invalid_json', 'symlink'])
def test_reader_rejects_missing_damaged_or_linked_daily_data(tmp_path, client, damage):
    source = tmp_path / 'source'
    export.sync_tasks(client, source, [PROJECT])
    selected = _selected(source)
    file = source / selected[0]['locator']['file']
    raw = file.read_bytes()
    if damage == 'missing':
        file.unlink()
    elif damage == 'short':
        file.write_bytes(raw[:5])
    elif damage == 'invalid_json':
        file.write_bytes(b'x' * len(raw))
    else:
        outside = tmp_path / 'outside.jsonl'
        outside.write_bytes(raw)
        file.unlink()
        file.symlink_to(outside)
    with pytest.raises(export.AsanaStoreError):
        export.load_snapshots(source, selected)


def test_corrupt_state_is_preserved_instead_of_reset(tmp_path, client):
    export.sync_tasks(client, tmp_path, [PROJECT])
    state = tmp_path / 'state.json'
    state.write_text('{broken', encoding='utf-8')
    daily = {p: p.read_bytes() for p in tmp_path.rglob('*.jsonl')}
    with pytest.raises(export.AsanaStoreError):
        export.sync_tasks(client, tmp_path, [PROJECT])
    assert state.read_text() == '{broken'
    assert {p: p.read_bytes() for p in tmp_path.rglob('*.jsonl')} == daily


def test_new_project_collects_old_completed_task_without_a_window(tmp_path, client):
    export.sync_tasks(client, tmp_path, [PROJECT])
    client.projects[OTHER_PROJECT] = ['301']
    client.tasks['301'] = _task('301', completed=True, projects=[{'gid': OTHER_PROJECT}],
                                modified_at='2000-01-01T00:00:00Z')
    result = export.sync_tasks(client, tmp_path, [PROJECT, OTHER_PROJECT])
    assert result['appended_records'] == 1
    assert ('since', OTHER_PROJECT, None) in client.calls
    assert _loaded(tmp_path, [OTHER_PROJECT])[0]['task']['completed'] is True


def test_failed_first_run_has_no_success_or_visible_records(tmp_path, client):
    client.failure = ('stories', TASK)
    with pytest.raises(AsanaError):
        export.sync_tasks(client, tmp_path, [PROJECT])
    status = export.export_status(tmp_path)
    assert status['initialized'] is False
    assert status['checkpoints'] == {}
    assert status['record_count'] == 0
    assert status['last_success_at'] is None
    assert status['last_failure'] is not None
    assert _selected(tmp_path) == []
    client.failure = None
    assert export.sync_tasks(client, tmp_path, [PROJECT])['appended_records'] == 1


def test_failed_second_project_does_not_advance_first_project(tmp_path, client, isolated_export):
    client.projects[OTHER_PROJECT] = []
    export.sync_tasks(client, tmp_path, [PROJECT, OTHER_PROJECT])
    before = export.export_status(tmp_path)
    isolated_export[0] += timedelta(hours=1)
    client.failure = ('list', OTHER_PROJECT)
    with pytest.raises(AsanaError):
        export.sync_tasks(client, tmp_path, [PROJECT, OTHER_PROJECT])
    after = export.export_status(tmp_path)
    assert after['checkpoints'] == before['checkpoints']
    assert after['last_success_at'] == before['last_success_at']


def test_next_utc_day_appends_without_overwriting_yesterday(tmp_path, client, isolated_export):
    export.sync_tasks(client, tmp_path, [PROJECT])
    first = _selected(tmp_path)
    old_file = tmp_path / first[0]['locator']['file']
    old_bytes = old_file.read_bytes()
    isolated_export[0] += timedelta(days=1)
    client.tasks[TASK]['name'] = 'Tomorrow'
    export.sync_tasks(client, tmp_path, [PROJECT])
    assert old_file.read_bytes() == old_bytes
    assert (tmp_path / 'daily/2026/11/02.jsonl').is_file()
    assert export.load_snapshots(tmp_path, first)[0]['task']['name'] == 'Lecture notes'
    assert _loaded(tmp_path)[0]['task']['name'] == 'Tomorrow'


def test_loading_selected_snapshots_preserves_requested_order(tmp_path, client):
    client.projects[PROJECT].append('301')
    client.tasks['301'] = _task('301')
    export.sync_tasks(client, tmp_path, [PROJECT])
    selected = list(reversed(_selected(tmp_path)))
    assert [row['change_id'] for row in export.load_snapshots(tmp_path, selected)] == [
        row['change_id'] for row in selected]


@pytest.mark.parametrize('field,value', [('file', '../outside.jsonl'),
                                        ('file', '/tmp/outside.jsonl'),
                                        ('offset', -1), ('offset', 10**9),
                                        ('length', 10**9)])
def test_reader_rejects_locators_outside_committed_material(tmp_path, client, field, value):
    export.sync_tasks(client, tmp_path, [PROJECT])
    selected = deepcopy(_selected(tmp_path))
    selected[0]['locator'][field] = value
    with pytest.raises(export.AsanaStoreError):
        export.load_snapshots(tmp_path, selected)


@pytest.mark.parametrize('field,value', [('task_gid', '999'), ('change_id', 'asana:wrong')])
def test_reader_checks_snapshot_identity(tmp_path, client, field, value):
    export.sync_tasks(client, tmp_path, [PROJECT])
    selected = deepcopy(_selected(tmp_path))
    selected[0][field] = value
    with pytest.raises(export.AsanaStoreError):
        export.load_snapshots(tmp_path, selected)


def test_missing_state_does_not_erase_existing_daily_material(tmp_path, client):
    export.sync_tasks(client, tmp_path, [PROJECT])
    (tmp_path / 'state.json').unlink()
    before = {p: p.read_bytes() for p in tmp_path.rglob('*.jsonl')}
    with pytest.raises(export.AsanaStoreError):
        export.sync_tasks(client, tmp_path, [PROJECT])
    assert {p: p.read_bytes() for p in tmp_path.rglob('*.jsonl')} == before


def test_fsync_failure_keeps_previous_committed_snapshot(tmp_path, client, monkeypatch):
    export.sync_tasks(client, tmp_path, [PROJECT])
    selected = _selected(tmp_path)
    before = export.export_status(tmp_path)
    client.tasks[TASK]['name'] = 'Changed'
    fsync = os.fsync
    failed = []

    def fail_once(descriptor):
        if not failed:
            failed.append(True)
            raise OSError('Synthetic flush failure')
        return fsync(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(os, 'fsync', fail_once)
        with pytest.raises(export.AsanaStoreError):
            export.sync_tasks(client, tmp_path, [PROJECT])
    assert _selected(tmp_path) == selected
    after = export.export_status(tmp_path)
    assert after['checkpoints'] == before['checkpoints']
    assert after['record_count'] == before['record_count']
    assert after['last_success_at'] == before['last_success_at']
    assert export.sync_tasks(client, tmp_path, [PROJECT])['appended_records'] == 1
    assert len(_records(tmp_path)) == 2
