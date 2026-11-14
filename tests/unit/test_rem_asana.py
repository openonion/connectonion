"""Acceptance tests: selected Asana tasks as offline REM material.

Expectations come from the story: collect first, one newest item per task,
names for page matching, and a read-only pending count. Saved material is
created through the exporter, not by constructing its private state format.
The investigation tests cover person/project investigations and the published identity contract.
"""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import socket

import pytest

from connectonion.rem.asana import collect_asana, collect_now, gather_asana, pending_asana
from connectonion.rem.files import RemError
from connectonion.useful_tools import asana_export as export
from tests.unit.test_asana_export import FakeAsana, ACCOUNT, PROJECT, OTHER_PROJECT, TASK, _task, _story


pytestmark = pytest.mark.unit


@pytest.fixture
def asana_material(tmp_path, monkeypatch):
    """Synthetic source and client; no credentials, personal files or network."""
    monkeypatch.delenv('ASANA_ACCESS_TOKEN', raising=False)
    monkeypatch.setenv('AGENT_CONFIG_PATH', str(tmp_path / 'config'))
    monkeypatch.setenv('CO_INBOX_HOME', str(tmp_path / 'inbox'))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))

    def refuse_network(*args, **kwargs):
        pytest.fail('Sync tests must not connect to a network')

    monkeypatch.setattr(socket.socket, 'connect', refuse_network)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse_network)
    monkeypatch.setattr(socket, 'create_connection', refuse_network)
    client = FakeAsana()
    client.tasks[TASK] = _task(name='Launch plan', notes='Keep [red]literal[/red] tags. 中文 🙂',
        assignee={'gid': '500', 'name': 'Alice Assignee'},
        projects=[{'gid': PROJECT, 'name': 'Atlas Project'}],
        permalink_url='https://app.asana.com/0/200/300')
    client.stories[TASK] = [_story(created_by={'gid': '600', 'name': 'Bob Commenter'},
                                 text='Confirm [[Atlas]] on Friday.')]
    source = {'id': 'asana', 'kind': 'asana', 'root': str(tmp_path / 'inbox/asana'),
              'project_gids': [PROJECT], 'enabled': True, 'consented': True, 'adapter': 'available'}
    return source, client


def _save(source, client, projects=None):
    return export.sync_tasks(client, Path(source['root']), projects or source['project_gids'])


def _batch(source, progress=None, **limits):
    return collect_asana(source, progress or {}, limits.get('max_items', 20), limits.get('max_chars', 100000))


def _files(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_pending_before_collection_is_unknown_without_creating_source(asana_material):
    source, client = asana_material
    result = pending_asana(source, {})
    assert result['pending_tasks'] is None
    assert result['body_reads'] is False
    assert not Path(source['root']).exists()
    assert client.calls == []


def test_collection_uses_only_explicit_projects(asana_material):
    source, client = asana_material
    client.projects[OTHER_PROJECT] = ['301']
    client.tasks['301'] = _task('301', name='Private task')
    collect_now(source, client=client)
    assert ('list', PROJECT) in client.calls
    assert ('list', OTHER_PROJECT) not in client.calls
    assert ('task', '301') not in client.calls
    assert len(_batch(source).items) == 1


def test_item_names_assignee_commenter_project_and_preserves_text(asana_material):
    source, client = asana_material
    _save(source, client)
    [item] = _batch(source).items
    for value in ('Launch plan', 'Alice Assignee', 'Bob Commenter', 'Atlas Project',
                  client.tasks[TASK]['notes'], client.stories[TASK][0]['text']):
        assert value in item['text']
    assert item['reference'] == client.tasks[TASK]['permalink_url']
    assert item['source'].startswith(f'asana:{ACCOUNT}:{TASK}:')
    assert item['role'] != 'user'


@pytest.mark.parametrize('change', ['title', 'description', 'comment'])
def test_only_newest_unconsumed_version_reaches_rem(asana_material, change):
    source, client = asana_material
    client.tasks[TASK]['name'] = 'Superseded title'
    _save(source, client)
    if change == 'comment':
        client.stories[TASK][0]['text'] = 'Newest comment'
        expected = 'Newest comment'
    elif change == 'description':
        client.tasks[TASK]['notes'] = 'Newest description'
        expected = 'Newest description'
    else:
        client.tasks[TASK]['name'] = 'Newest title'
        expected = 'Newest title'
    _save(source, client)
    assert pending_asana(source, {})['pending_tasks'] == 1
    [item] = _batch(source).items
    [latest] = export.latest_snapshots(Path(source['root']), account_gid=ACCOUNT, project_gids=[PROJECT])
    assert item['source'] == latest['change_id']
    assert expected in item['text']
    if change == 'title':
        assert 'Superseded title' not in item['text']


def test_task_shared_by_selected_projects_produces_one_item(asana_material):
    source, client = asana_material
    source['project_gids'].append(OTHER_PROJECT)
    client.projects[OTHER_PROJECT] = [TASK]
    client.tasks[TASK]['projects'].append({'gid': OTHER_PROJECT, 'name': 'Second Project'})
    _save(source, client)
    assert pending_asana(source, {})['pending_tasks'] == 1
    [item] = _batch(source).items
    assert 'Atlas Project' in item['text'] and 'Second Project' in item['text']


def test_cached_unselected_tasks_are_not_delivered(asana_material, monkeypatch):
    source, client = asana_material
    client.projects[OTHER_PROJECT] = ['301']
    client.tasks['301'] = _task('301', name='Private task', projects=[{'gid': OTHER_PROJECT}])
    _save(source, client, [PROJECT, OTHER_PROJECT])
    load = export.load_snapshots

    def selected_only(directory, selected):
        assert all(entry['task_gid'] == TASK for entry in selected)
        return load(directory, selected)

    monkeypatch.setattr(export, 'load_snapshots', selected_only)
    assert pending_asana(source, {})['pending_tasks'] == 1
    [item] = _batch(source).items
    assert 'Private task' not in item['text']


def test_pending_reads_index_only_and_writes_nothing(asana_material, monkeypatch):
    source, client = asana_material
    _save(source, client)
    root = Path(source['root']); before = _files(root)
    client.calls.clear()
    monkeypatch.setattr(export, 'load_snapshots', lambda *a, **kw: pytest.fail('Pending read a task body'))
    assert pending_asana(source, {})['pending_tasks'] == 1
    assert _files(root) == before
    assert client.calls == []


def test_batch_is_repeatable_until_its_proposed_progress_is_accepted(asana_material):
    source, client = asana_material
    _save(source, client)
    progress = {}; before = _files(Path(source['root']))
    first = _batch(source, progress); second = _batch(source, progress)
    assert progress == {}
    assert first.items == second.items and first.progress == second.progress
    assert _files(Path(source['root'])) == before
    assert _batch(source, first.progress).items == []
    assert pending_asana(source, first.progress)['pending_tasks'] == 0


@pytest.mark.parametrize('change', ['task', 'add_comment', 'edit_comment', 'delete_comment'])
def test_changed_consumed_task_becomes_pending_once(asana_material, change):
    source, client = asana_material
    _save(source, client); first = _batch(source)
    if change == 'task':
        client.tasks[TASK]['completed'] = True
    elif change == 'add_comment':
        client.stories[TASK].append(_story('401', text='New comment'))
    elif change == 'edit_comment':
        client.stories[TASK][0]['text'] = 'Edited comment'
    else:
        client.stories[TASK] = []
    _save(source, client)
    assert pending_asana(source, first.progress)['pending_tasks'] == 1
    second = _batch(source, first.progress)
    assert len(second.items) == 1 and second.items[0]['source'] != first.items[0]['source']
    assert _batch(source, second.progress).items == []


def test_return_to_old_content_is_not_confused_with_old_consumption(asana_material):
    source, client = asana_material
    original = deepcopy(client.tasks[TASK]); progress = {}; ids = []
    for task in (original, {**original, 'name': 'Temporary change'}, original):
        client.tasks[TASK] = deepcopy(task); _save(source, client)
        batch = _batch(source, progress); assert len(batch.items) == 1
        ids.append(batch.items[0]['source']); progress = batch.progress
    assert len(set(ids)) == 3


@pytest.mark.parametrize('enabled,consented', [(False, False), (False, True), (True, False)])
def test_disabled_or_unapproved_source_cannot_read_material(asana_material, enabled, consented):
    source, client = asana_material
    _save(source, client)
    with pytest.raises(RemError):
        _batch({**source, 'enabled': enabled, 'consented': consented})


@pytest.mark.parametrize('limit', [1, 2])
def test_item_budget_leaves_remaining_tasks_for_next_batch(asana_material, limit):
    source, client = asana_material
    for gid in ('301', '302'):
        client.projects[PROJECT].append(gid); client.tasks[gid] = _task(gid, name=f'Task {gid}')
    _save(source, client)
    first = _batch(source, max_items=limit)
    assert len(first.items) == limit
    assert pending_asana(source, first.progress)['pending_tasks'] == 3 - limit
    second = _batch(source, first.progress)
    assert len(first.items + second.items) == 3
    assert len({item['source'] for item in first.items + second.items}) == 3


def test_character_budget_does_not_mark_waiting_task_consumed(asana_material):
    source, client = asana_material
    client.projects[PROJECT].append('301'); client.tasks['301'] = _task('301', notes='x' * 3000)
    _save(source, client)
    full = _batch(source)
    budget = len(json.dumps(full.items[0], ensure_ascii=False)) + 1
    first = _batch(source, max_chars=budget)
    assert len(first.items) == 1
    assert pending_asana(source, first.progress)['pending_tasks'] == 1
    assert len(_batch(source, first.progress).items) == 1


@pytest.mark.parametrize('fields', [
    {'assignee': None}, {'projects': []}, {'notes': ''},
    {'completed': True, 'completed_at': '2026-11-01T12:00:00Z'},
    {'due_on': '2026-12-03'}, {'due_at': '2026-12-03T10:00:00Z'},
])
def test_optional_task_fields_still_produce_traceable_item(asana_material, fields):
    source, client = asana_material
    client.tasks[TASK].update(fields); _save(source, client)
    [item] = _batch(source).items
    assert item['source'] and item['text'] and item['reference']
    if fields.get('due_on') or fields.get('due_at'):
        assert (fields.get('due_at') or fields['due_on']) in item['text']
    if fields.get('completed'):
        assert 'completed' in item['text'].lower()


def test_comment_names_do_not_depend_on_list_order(asana_material):
    source, client = asana_material
    client.stories[TASK] += [_story('401', created_by={'gid': '601', 'name': 'Carol Commenter'}, text='Later'),
                            _story('402', created_by={'gid': ACCOUNT, 'name': 'Owner'}, text='My commitment')]
    client.stories[TASK].reverse(); _save(source, client)
    [item] = _batch(source).items
    for name in ('Bob Commenter', 'Carol Commenter', 'Owner', 'My commitment'):
        assert name in item['text']
    assert item['role'] != 'user'


def test_empty_project_has_known_zero_pending_after_collection(asana_material):
    source, client = asana_material
    client.projects[PROJECT] = []
    _save(source, client)
    assert pending_asana(source, {})['pending_tasks'] == 0
    assert _batch(source).items == []


@pytest.mark.parametrize('damage', ['missing', 'invalid_json'])
def test_damaged_saved_body_is_not_accepted_as_consumed(asana_material, damage):
    source, client = asana_material
    _save(source, client)
    [daily] = list(Path(source['root']).glob('daily/*/*/*.jsonl'))
    if damage == 'missing':
        daily.unlink()
    else:
        data = daily.read_bytes()
        daily.write_bytes(b'!' + data[1:])
    progress = {}
    with pytest.raises(export.AsanaStoreError):
        _batch(source, progress)
    assert progress == {}


def test_adapter_does_not_poll_asana_when_reading_saved_material(asana_material):
    source, client = asana_material
    _save(source, client)
    client.calls.clear()
    pending_asana(source, {})
    assert len(_batch(source).items) == 1
    assert client.calls == []


# -- investigations over saved, authorized material -----------------------------

WINDOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
PERSON = {'gid': '500', 'name': 'Alice Assignee'}
OTHER_PERSON = {'gid': '501', 'name': 'Bob Commenter'}


@pytest.fixture
def investigation_material(asana_material, monkeypatch):
    """Save through the public exporter, never construct its private index/state."""
    source, client = asana_material
    monkeypatch.setattr(export, '_now', lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    client.tasks[TASK].update(modified_at='2026-10-20T12:00:00Z', assignee=deepcopy(PERSON))
    client.stories[TASK] = [_story(created_at='2026-10-20T13:00:00Z',
                                  created_by=deepcopy(OTHER_PERSON), text='I will send the mockup.')]
    return source, client


def _investigation(source, handles=None, record='people/alice.md', owner=False):
    return gather_asana(source, handles if handles is not None else [PERSON['gid']],
                        start=WINDOW, record=record, owner=owner)


@pytest.mark.parametrize('handle', [PERSON['gid'], PERSON['name']])
def test_investigation_includes_assigned_tasks(investigation_material, handle):
    source, client = investigation_material
    _save(source, client)
    items, coverage = _investigation(source, [handle])
    assert len(items) == 1
    assert 'Launch plan' in items[0]['text']
    assert any('asana:' in line and '1' in line for line in coverage)


@pytest.mark.parametrize('modified', ['2026-09-01T12:00:00Z', '2026-10-20T12:00:00Z'])
def test_investigation_includes_recent_comments_even_on_old_unassigned_tasks(investigation_material, modified):
    source, client = investigation_material
    client.tasks[TASK].update(assignee=None, modified_at=modified)
    client.stories[TASK][0].update(created_by=deepcopy(PERSON), text='My comment remains attributed.')
    _save(source, client)
    [item], _ = _investigation(source)
    assert PERSON['name'] in item['text'] and 'My comment remains attributed.' in item['text']


def test_investigation_does_not_match_someone_elses_recent_comment(investigation_material):
    source, client = investigation_material
    client.tasks[TASK]['assignee'] = deepcopy(OTHER_PERSON)
    client.tasks[TASK]['notes'] = 'Alice Assignee is mentioned, not assigned or commenting.'
    _save(source, client)
    assert _investigation(source)[0] == []


def test_investigation_old_comment_does_not_become_recent_when_task_changes(investigation_material):
    source, client = investigation_material
    client.tasks[TASK]['assignee'] = deepcopy(OTHER_PERSON)
    client.stories[TASK][0].update(created_by=deepcopy(PERSON), created_at='2026-09-30T23:59:59Z')
    _save(source, client)
    assert _investigation(source)[0] == []


@pytest.mark.parametrize('relation', ['assignee', 'commenter', 'project'])
def test_investigation_excludes_tasks_with_only_old_activity(investigation_material, relation):
    source, client = investigation_material
    client.tasks[TASK]['modified_at'] = '2026-09-20T00:00:00Z'
    client.stories[TASK][0]['created_at'] = '2026-09-21T00:00:00Z'
    if relation == 'commenter':
        client.tasks[TASK]['assignee'] = None
        client.stories[TASK][0]['created_by'] = deepcopy(PERSON)
    _save(source, client)
    handles = [PROJECT] if relation == 'project' else [PERSON['gid']]
    record = 'projects/atlas.md' if relation == 'project' else 'people/alice.md'
    assert _investigation(source, handles, record)[0] == []


@pytest.mark.parametrize('subtype', ['assigned', 'marked_complete', 'added_to_project'])
def test_investigation_system_activity_is_not_a_person_comment(investigation_material, subtype):
    source, client = investigation_material
    client.tasks[TASK]['assignee'] = None
    client.stories[TASK][0].update(resource_subtype=subtype, created_by=deepcopy(PERSON))
    _save(source, client)
    assert _investigation(source)[0] == []


def test_investigation_assignment_and_several_comments_still_produce_one_task(investigation_material):
    source, client = investigation_material
    client.stories[TASK] = [_story(str(400 + i), created_by=deepcopy(PERSON),
        created_at='2026-10-20T13:00:00Z', text=f'Comment {i}') for i in range(3)]
    _save(source, client)
    items, _ = _investigation(source, [PERSON['gid'], PERSON['name'], PERSON['gid']])
    assert len(items) == 1
    assert all(f'Comment {i}' in items[0]['text'] for i in range(3))


@pytest.mark.parametrize('handle', [PROJECT, 'Atlas Project'])
def test_investigation_project_gathers_its_tasks_without_person_assignment(investigation_material, handle):
    source, client = investigation_material
    client.tasks[TASK]['assignee'] = None
    _save(source, client)
    assert len(_investigation(source, [handle], 'projects/atlas.md')[0]) == 1


def test_investigation_shared_task_is_not_duplicated_across_selected_projects(investigation_material):
    source, client = investigation_material
    source['project_gids'].append(OTHER_PROJECT)
    client.projects[OTHER_PROJECT] = [TASK]
    client.tasks[TASK]['projects'].append({'gid': OTHER_PROJECT, 'name': 'Second Project'})
    _save(source, client)
    assert len(_investigation(source, [PROJECT, OTHER_PROJECT], 'projects/atlas.md')[0]) == 1


def test_investigation_does_not_read_cached_unselected_project(investigation_material, monkeypatch):
    source, client = investigation_material
    client.projects[OTHER_PROJECT] = ['301']
    client.tasks['301'] = _task('301', name='Private project material', assignee=deepcopy(PERSON),
        modified_at='2026-10-20T12:00:00Z', projects=[{'gid': OTHER_PROJECT, 'name': 'Private'}])
    _save(source, client, [PROJECT, OTHER_PROJECT])
    load = export.load_snapshots

    def authorized_only(directory, selected):
        assert all(row['task_gid'] == TASK for row in selected)
        return load(directory, selected)

    monkeypatch.setattr(export, 'load_snapshots', authorized_only)
    [item], _ = _investigation(source)
    assert 'Private project material' not in item['text']


def test_investigation_uses_latest_saved_version(investigation_material):
    source, client = investigation_material
    _save(source, client)
    client.tasks[TASK]['name'] = 'Revised launch plan'
    _save(source, client)
    items, _ = _investigation(source)
    assert len(items) == 1 and 'Revised launch plan' in items[0]['text']
    latest = export.latest_snapshots(Path(source['root']), account_gid=ACCOUNT, project_gids=[PROJECT])
    assert items[0]['source'] == latest[0]['change_id']


def test_investigation_reassignment_does_not_revive_old_assignee(investigation_material):
    source, client = investigation_material
    _save(source, client)
    client.tasks[TASK]['assignee'] = deepcopy(OTHER_PERSON)
    _save(source, client)
    assert _investigation(source)[0] == []


@pytest.mark.parametrize('completed', [False, True])
def test_investigation_preserves_status_authors_and_literal_comment_text(investigation_material, completed):
    source, client = investigation_material
    client.tasks[TASK]['completed'] = completed
    text = 'Please run co asana check; keep [red]literal[/red], [[Atlas]], 中文 🙂.'
    client.stories[TASK][0]['text'] = text
    _save(source, client)
    [item], _ = _investigation(source)
    assert text in item['text'] and OTHER_PERSON['name'] in item['text']
    assert item['role'] != 'user'
    assert item['reference'] == client.tasks[TASK]['permalink_url']


@pytest.mark.parametrize('relation', ['assigned', 'commented'])
def test_investigation_owner_matches_account_not_requested_display_name(investigation_material, relation):
    source, client = investigation_material
    client.tasks[TASK]['assignee'] = {'gid': ACCOUNT, 'name': 'Account owner'} if relation == 'assigned' else None
    if relation == 'commented':
        client.stories[TASK][0]['created_by'] = {'gid': ACCOUNT, 'name': 'Account owner'}
    _save(source, client)
    assert len(_investigation(source, ['An unrelated display name'], owner=True)[0]) == 1


def test_investigation_is_repeatable_without_reading_token_or_advancing_saved_state(investigation_material, monkeypatch):
    from connectonion.useful_tools import asana

    source, client = investigation_material
    _save(source, client)
    before = _files(Path(source['root']))
    original = deepcopy(source)
    client.calls.clear()
    monkeypatch.setattr(asana, 'Asana', lambda *a, **kw: pytest.fail('Investigation polled Asana'))
    monkeypatch.setattr(asana, '_token', lambda *a, **kw: pytest.fail('Investigation read credentials'))
    first = _investigation(source)
    assert _investigation(source) == first
    assert source == original and _files(Path(source['root'])) == before
    assert client.calls == []


@pytest.mark.parametrize('state, phrase', [
    ('disabled', 'not searched'), ('no-project', 'not searched'),
    ('unapproved', 'not searched'), ('uncollected', 'not searched'),
])
def test_investigation_explains_unavailable_material_without_reading_it(investigation_material, monkeypatch, state, phrase):
    source, client = investigation_material
    if state != 'uncollected':
        _save(source, client)
    if state == 'disabled': source['enabled'] = False
    if state == 'no-project': source['project_gids'] = []
    if state == 'unapproved': source['consented'] = False
    monkeypatch.setattr(export, 'load_snapshots', lambda *a, **kw: pytest.fail('Unavailable material was read'))
    items, coverage = _investigation(source)
    assert items == [] and any('asana:' in line and phrase in line for line in coverage)


def test_investigation_reports_unreadable_cache_as_unsearched(investigation_material, monkeypatch):
    source, client = investigation_material
    _save(source, client)

    def unreadable(*args, **kwargs):
        raise OSError('Synthetic unreadable source')

    monkeypatch.setattr(export, 'load_snapshots', unreadable)
    items, coverage = _investigation(source)
    assert items == []
    assert any('unreadable' in line and 'not searched' in line for line in coverage)


@pytest.mark.parametrize('handle', ['50', 'Alice', 'Alice Assignee Jr', 'Atlas'])
def test_investigation_does_not_match_partial_identity(investigation_material, handle):
    source, client = investigation_material
    _save(source, client)
    assert _investigation(source, [handle])[0] == []


@pytest.mark.parametrize('record', ['people/alice.md', 'projects/atlas.md'])
def test_investigation_same_name_requires_disambiguation(investigation_material, record):
    """The published CLI contract requires one gid, not a union of same-name identities."""
    source, client = investigation_material
    source['project_gids'].append(OTHER_PROJECT)
    client.projects[OTHER_PROJECT] = ['301']
    name = PERSON['name'] if record.startswith('people/') else 'Atlas Project'
    client.tasks['301'] = _task('301', name='A different identity', modified_at='2026-10-20T12:00:00Z',
        assignee={'gid': '999', 'name': PERSON['name']},
        projects=[{'gid': OTHER_PROJECT, 'name': 'Atlas Project'}])
    _save(source, client)
    items, coverage = _investigation(source, [name], record)
    assert items == []
    assert any('ambig' in line.lower() or 'gid' in line.lower() for line in coverage)


def test_investigation_explicit_gid_distinguishes_same_name_people(investigation_material):
    source, client = investigation_material
    client.projects[PROJECT].append('301')
    client.tasks['301'] = _task('301', name='Wrong same-name person', modified_at='2026-10-20T12:00:00Z',
        assignee={'gid': '999', 'name': PERSON['name']})
    _save(source, client)
    [item], _ = _investigation(source)
    assert 'Wrong same-name person' not in item['text']


def test_investigation_explicit_gid_distinguishes_same_name_projects(investigation_material):
    source, client = investigation_material
    source['project_gids'].append(OTHER_PROJECT)
    client.projects[OTHER_PROJECT] = ['301']
    client.tasks['301'] = _task('301', name='Wrong same-name project', modified_at='2026-10-20T12:00:00Z',
        projects=[{'gid': OTHER_PROJECT, 'name': 'Atlas Project'}])
    _save(source, client)
    [item], _ = _investigation(source, [PROJECT], 'projects/atlas.md')
    assert 'Wrong same-name project' not in item['text']


def test_investigation_owner_does_not_take_another_persons_same_display_name(investigation_material):
    source, client = investigation_material
    client.tasks[TASK]['assignee'] = {'gid': '999', 'name': 'Synthetic user'}
    client.stories[TASK][0]['created_by'] = {'gid': '998', 'name': 'Synthetic user'}
    _save(source, client)
    assert _investigation(source, ['Synthetic user'], owner=True)[0] == []


@pytest.mark.parametrize('stamp', ['2026-10-01T01:00:00+02:00', '2026-10-01T01:00:00-02:00'])
def test_investigation_compares_window_as_instants_not_timestamp_strings(investigation_material, stamp):
    source, client = investigation_material
    client.tasks[TASK]['modified_at'] = stamp
    client.stories[TASK] = []
    _save(source, client)
    items, _ = _investigation(source)
    expected = datetime.fromisoformat(stamp) >= WINDOW
    assert bool(items) == expected


@pytest.mark.parametrize('handle', ['alice assignee', '  Alice Assignee  '])
def test_investigation_normalizes_exact_name_handles(investigation_material, handle):
    source, client = investigation_material
    _save(source, client)
    assert len(_investigation(source, [handle])[0]) == 1


def test_investigation_no_longer_includes_removed_comment_author(investigation_material):
    source, client = investigation_material
    client.tasks[TASK]['assignee'] = None
    client.stories[TASK][0]['created_by'] = deepcopy(PERSON)
    _save(source, client)
    client.stories[TASK] = []
    _save(source, client)
    assert _investigation(source)[0] == []


def test_investigation_project_membership_uses_latest_saved_snapshot(investigation_material):
    source, client = investigation_material
    source['project_gids'].append(OTHER_PROJECT)
    client.projects[OTHER_PROJECT] = [TASK]
    _save(source, client)
    client.tasks[TASK]['projects'] = [{'gid': OTHER_PROJECT, 'name': 'Second Project'}]
    _save(source, client)
    assert _investigation(source, [PROJECT], 'projects/atlas.md')[0] == []
    assert len(_investigation(source, [OTHER_PROJECT], 'projects/second.md')[0]) == 1


def test_investigation_coverage_identifies_saved_collection(investigation_material):
    source, client = investigation_material
    _save(source, client)
    _, coverage = _investigation(source)
    status = export.export_status(Path(source['root']))
    assert any(str(status['last_success_at']) in line for line in coverage)
