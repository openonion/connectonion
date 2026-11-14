"""Asana CLI arguments, rendering, listings, exit codes and safe errors."""

from datetime import date, datetime, timedelta, timezone
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import hashlib
import json
import re
import shlex
import time

import httpx
import pytest
from click import unstyle

from tests.unit.test_rem_service import asana_registration, asana_sync
from tests.unit.test_rem_asana import asana_material
from typer.testing import CliRunner

from tests.unit.test_asana import (
    TOKEN, SET_TOKEN, USER_GID, WORKSPACE_GID, PROJECT_GID, TASK_GID, INVALID_STORY_TIMES,
    _failure, _success, _user, _project, _task, _page, _task_detail, _story, _story_with_time,
    isolated_asana_env, mock_http,
    _read_failure,
)

pytestmark = [pytest.mark.unit, pytest.mark.cli]
CHECK = ['asana', 'check']



def _assert_no_credentials(result):
    output = result.stdout + result.stderr
    assert TOKEN not in output
    assert 'authorization:' not in output.lower()
    assert f'Bearer {TOKEN}' not in output


def _assert_safe_failure(result, next_step=None):
    assert result.exit_code == 1, result.output
    assert result.stdout.strip() == ''
    assert '✗' in result.stderr
    tips = [line for line in result.stderr.splitlines() if line.startswith('Next: ')]
    assert len(tips) == 1
    assert tips[0].startswith('Next: co ')
    if next_step is not None:
        assert tips[0] == f'Next: {next_step}'
    assert 'Traceback (most recent call last)' not in result.stderr
    _assert_no_credentials(result)


@pytest.fixture
def cli(mock_http):
    from connectonion.cli.main import app
    runner = CliRunner()
    return lambda args: runner.invoke(app, args)



def test_bare_asana_without_token_says_how_to_connect(cli, mock_http, monkeypatch):
    """Bare co asana shows content like bare co gmail: here check, so no token means co auth asana."""
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')
    result = cli(['asana'])

    _assert_safe_failure(result, SET_TOKEN)
    assert 'Usage:' not in result.output
    assert mock_http.requests == []


def test_bare_asana_shows_what_check_shows(cli, mock_http):
    mock_http.responses.append(_success())
    bare = cli(['asana'])
    mock_http.responses.append(_success())
    checked = cli(CHECK)

    assert bare.exit_code == 0, bare.output
    assert bare.stdout == checked.stdout
    assert 'Alice <alice@example.test>' in bare.stdout and 'Usage:' not in bare.stdout



@pytest.mark.parametrize('args', [['asana', '--help'], [*CHECK, '--help']])
def test_help_without_token_never_requests(args, cli, mock_http, monkeypatch):
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')
    result = cli(args)

    assert result.exit_code == 0, result.output
    assert 'Usage:' in result.stdout
    assert 'check' in result.stdout
    assert mock_http.requests == []
    assert mock_http.sleeps == []


def test_check_rejects_json_option(cli, mock_http):
    result = cli([*CHECK, '--json'])

    assert result.exit_code == 2, result.output
    assert '--json' in result.output
    assert mock_http.requests == []


@pytest.mark.parametrize('args', [['--unknown-option'], ['unexpected-argument']])
def test_check_rejects_invalid_arguments(args, cli, mock_http):
    result = cli([*CHECK, *args])

    assert result.exit_code == 2, result.output
    assert mock_http.requests == []


def test_missing_token_is_actionable(cli, mock_http, monkeypatch):
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')
    result = cli(CHECK)

    _assert_safe_failure(result, SET_TOKEN)
    assert mock_http.requests == []


@pytest.mark.parametrize('token', ['', ' ', '\t\n'])
def test_blank_token_is_missing(token, cli, mock_http, monkeypatch):
    monkeypatch.setenv('ASANA_ACCESS_TOKEN', token)
    result = cli(CHECK)

    _assert_safe_failure(result, SET_TOKEN)
    assert mock_http.requests == []


def test_success_never_prints_token(cli, mock_http):
    mock_http.responses.append(_success())
    result = cli(CHECK)

    assert result.exit_code == 0, result.output
    _assert_no_credentials(result)


def test_check_displays_current_user(cli, mock_http):
    mock_http.responses.append(_success())
    result = cli(CHECK)

    assert result.exit_code == 0, result.output
    assert 'Alice <alice@example.test>' in result.stdout


def test_check_displays_single_workspace(cli, mock_http):
    mock_http.responses.append(_success())
    result = cli(CHECK)

    assert result.exit_code == 0, result.output
    assert 'Engineering' in result.stdout
    assert WORKSPACE_GID in result.stdout


def test_check_displays_every_workspace(cli, mock_http):
    workspaces = [{'gid': str(120000000000001 + i), 'name': f'Team-{i}'} for i in range(3)]
    mock_http.responses.append(_success(_user(workspaces)))
    result = cli(CHECK)

    assert result.exit_code == 0, result.output
    for workspace in workspaces:
        assert any(workspace['name'] in line and workspace['gid'] in line
                   for line in result.stdout.splitlines())


def test_check_accepts_no_workspaces(cli, mock_http):
    mock_http.responses.append(_success(_user([])))
    result = cli(CHECK)

    assert result.exit_code == 0, result.output
    assert 'Alice <alice@example.test>' in result.stdout
    assert WORKSPACE_GID not in result.stdout
    assert '✗' not in result.output


def test_duplicate_workspace_names_keep_distinct_gids(cli, mock_http):
    workspaces = [{'gid': str(120000000000001 + i), 'name': 'Same team'} for i in range(2)]
    mock_http.responses.append(_success(_user(workspaces)))
    result = cli(CHECK)

    assert result.exit_code == 0, result.output
    for workspace in workspaces:
        assert any('Same team' in line and workspace['gid'] in line
                   for line in result.stdout.splitlines())


def test_check_has_no_workspace_display_limit(cli, mock_http):
    workspaces = [{'gid': str(120000000000001 + i), 'name': f'Team-{i}'} for i in range(25)]
    mock_http.responses.append(_success(_user(workspaces)))
    result = cli(CHECK)

    assert result.exit_code == 0, result.output
    for workspace in workspaces:
        assert any(workspace['name'] in line and workspace['gid'] in line
                   for line in result.stdout.splitlines())


def test_check_preserves_unicode_text(cli, mock_http):
    user = _user([{'gid': WORKSPACE_GID, 'name': '研发团队 🌿'}], name='张三')
    mock_http.responses.append(_success(user))
    result = cli(CHECK)

    assert result.exit_code == 0, result.output
    assert '张三 <alice@example.test>' in result.stdout
    assert '研发团队 🌿' in result.stdout


def test_workspace_gid_is_displayed_unchanged(cli, mock_http):
    mock_http.responses.append(_success())
    result = cli(CHECK)

    assert result.exit_code == 0, result.output
    assert WORKSPACE_GID in result.stdout


def test_single_workspace_has_projects_next_step(cli, mock_http):
    mock_http.responses.append(_success())
    result = cli(CHECK)

    assert result.exit_code == 0, result.output
    assert 'Next: co asana projects' in result.output


def test_multiple_workspaces_require_explicit_next_step(cli, mock_http):
    workspaces = [{'gid': str(120000000000001 + i), 'name': f'Team-{i}'} for i in range(2)]
    mock_http.responses.append(_success(_user(workspaces)))
    result = cli(CHECK)

    assert result.exit_code == 0, result.output
    assert any(line.startswith('Next: co asana projects') and '--workspace' in line
               for line in result.output.splitlines())


@pytest.mark.parametrize('error', [httpx.ReadTimeout, httpx.ConnectError, httpx.ReadError])
def test_transport_error_cannot_echo_credentials(error, cli, mock_http):
    mock_http.responses.append(error(f'Authorization: Bearer {TOKEN}'))
    result = cli(CHECK)

    _assert_safe_failure(result)


@pytest.mark.parametrize('failure', ['401', 'bad-json', 'network'])
def test_failure_output_uses_stderr_without_traceback(failure, cli, mock_http):
    responses = {'401': _failure(401), 'bad-json': httpx.Response(200, text='{"data": '),
                 'network': httpx.ConnectError('Synthetic connection failure')}
    mock_http.responses.append(responses[failure])
    result = cli(CHECK)

    _assert_safe_failure(result)
    assert 'Alice <alice@example.test>' not in result.output


# workspace selection, native output and saved rows.
PROJECTS = ['asana', 'projects']
TASKS = ['asana', 'tasks', PROJECT_GID]


@pytest.fixture
def listing_dir(monkeypatch, tmp_path):
    from connectonion.cli.commands import asana_commands
    directory = tmp_path / 'asana-listings'
    monkeypatch.setattr(asana_commands, '_listings', lambda: directory)
    return directory


@pytest.fixture
def mock_asana_client(monkeypatch, listing_dir):
    from connectonion.useful_tools import asana
    client = SimpleNamespace(get_user=Mock(return_value=_user()),
                             list_projects=Mock(return_value=[_project()]),
                             list_tasks=Mock(return_value=[_task()]))
    monkeypatch.setattr(asana, 'Asana', Mock(return_value=client))
    return client


def _assert_usage_failure(result, next_step=None):
    assert result.exit_code == 2, result.output
    assert result.stdout.strip() == ''
    assert '✗' in result.stderr
    tips = [line for line in result.stderr.splitlines() if line.startswith('Next: ')]
    assert len(tips) == 1
    if next_step is not None:
        assert tips == [f'Next: {next_step}']
    assert 'Traceback (most recent call last)' not in result.stderr
    _assert_no_credentials(result)


def _seed_listing(directory, family='projects', gids=None, account=USER_GID, now=None):
    from connectonion.cli.commands.gmail_listings import save_listing
    token = save_listing(directory, f'asana:{account}', family,
                         [PROJECT_GID] if gids is None else gids, provider='asana', now=now)
    (directory / f'last-{family}').write_text(token, encoding='ascii')
    return token


def _listing_files(directory):
    return {path.name: path.read_bytes() for path in directory.glob('*') if path.is_file()}


def _records(command, count):
    make_record = _project if command == 'projects' else _task
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [make_record(str(1200000000000500 + i), name=f'Row-{i:03}',
                        modified_at=(start + timedelta(days=i)).isoformat()) for i in range(count)]


def _human_rows(result):
    return [line for line in result.stdout.splitlines() if line.split('.', 1)[0].isdigit()]


def _name_column(rows, names):
    """Rows are aligned columns with the name last: every name starts at the same terminal cell."""
    from rich.cells import cell_len
    starts = set()
    for row, name in zip(rows, names):
        assert row.endswith(name), (row, name)
        starts.add(cell_len(row[:-len(name)]))
    assert len(starts) == 1, rows


def _assert_saved_rows(directory, family, gids):
    token = (directory / f'last-{family}').read_text().strip()
    payload = json.loads((directory / f'{token}.json').read_text())
    assert payload['provider'] == 'asana'
    assert payload['family'] == family
    assert payload['account'] == hashlib.sha256(f'asana:{USER_GID}'.encode()).hexdigest()
    assert payload['ids'] == gids
    assert payload['expires_at'] - payload['created_at'] == 900
    assert TOKEN not in repr(payload)
    assert all(isinstance(gid, str) for gid in payload['ids'])
    return token


@pytest.mark.parametrize('command,flags', [
    ('projects', ['--workspace', '--archived', '--last', '--ids', '--json']),
    ('tasks', ['--workspace', '--assignee', '--status', '--due-from', '--due-to',
               '--modified-since', '--listing', '--last', '--ids', '--json']),
])
def test_list_help_without_token_does_not_request(command, flags, cli, mock_http, monkeypatch):
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')
    result = cli(['asana', command, '--help'])

    assert result.exit_code == 0, result.output
    for flag in flags:
        assert flag in result.stdout
    assert mock_http.requests == []


def test_projects_use_workspaces_from_current_user(cli, mock_asana_client):
    result = cli(PROJECTS)

    assert result.exit_code == 0, result.output
    mock_asana_client.get_user.assert_called_once_with()
    mock_asana_client.list_projects.assert_called_once_with(WORKSPACE_GID)


@pytest.mark.parametrize('workspaces', [[], [
    {'gid': WORKSPACE_GID, 'name': 'Engineering'}, {'gid': '1200000000000102', 'name': 'Other'},
]], ids=['zero', 'multiple'])
def test_projects_require_an_unambiguous_workspace(workspaces, cli, mock_asana_client):
    mock_asana_client.get_user.return_value = _user(workspaces)
    result = cli(PROJECTS)

    if workspaces:
        _assert_usage_failure(result, 'co asana check')
    else:
        _assert_safe_failure(result, 'co asana check')
        assert '✗ This Asana account belongs to no workspace yet' in result.stderr
    mock_asana_client.list_projects.assert_not_called()


@pytest.mark.parametrize('given', ['Other', '1200000000000102'])
def test_projects_select_workspace_by_exact_name_or_gid(given, cli, mock_asana_client):
    mock_asana_client.get_user.return_value = _user([
        {'gid': WORKSPACE_GID, 'name': 'Engineering'}, {'gid': '1200000000000102', 'name': 'Other'}])
    result = cli([*PROJECTS, '--workspace', given])

    assert result.exit_code == 0, result.output
    mock_asana_client.list_projects.assert_called_once_with('1200000000000102')


@pytest.mark.parametrize('given', ['Missing', 'engineering'])
def test_projects_reject_unknown_workspace(given, cli, mock_asana_client):
    mock_asana_client.get_user.return_value = _user([{'gid': WORKSPACE_GID, 'name': 'Engineering'}])
    result = cli([*PROJECTS, '--workspace', given])

    _assert_usage_failure(result, 'co asana check')
    mock_asana_client.list_projects.assert_not_called()


def test_projects_reject_duplicate_workspace_listing_each_gid(cli, mock_asana_client):
    workspaces = [{'gid': WORKSPACE_GID, 'name': 'Same'}, {'gid': '1200000000000102', 'name': 'Same'}]
    mock_asana_client.get_user.return_value = _user(workspaces)
    result = cli([*PROJECTS, '--workspace', 'Same'])

    _assert_usage_failure(result, 'co asana projects --workspace <workspace-gid>')
    lines = result.stderr.splitlines()
    assert "Several workspaces are named 'Same'. Pass the workspace gid instead:" in lines[0]
    for workspace in workspaces:
        assert f"  Same  {workspace['gid']}" in lines
    assert not any(line.lstrip().startswith(('1.', '2.')) for line in lines)
    mock_asana_client.list_projects.assert_not_called()


def test_tasks_duplicate_workspace_names_the_project_in_next(cli, mock_asana_client):
    mock_asana_client.get_user.return_value = _user(
        [{'gid': WORKSPACE_GID, 'name': 'Same'}, {'gid': '1200000000000102', 'name': 'Same'}])
    result = cli(['asana', 'tasks', 'Website Redesign', '--workspace', 'Same'])

    _assert_usage_failure(result, "co asana tasks 'Website Redesign' --workspace <workspace-gid>")
    mock_asana_client.list_projects.assert_not_called()
    mock_asana_client.list_tasks.assert_not_called()


@pytest.mark.parametrize('archived', [False, True])
def test_projects_hide_archived_unless_requested(archived, cli, mock_asana_client):
    records = [_project(name='Active'), _project('1200000000000202', name='Old', archived=True)]
    mock_asana_client.list_projects.return_value = records
    result = cli([*PROJECTS, '--json', *(['--archived'] if archived else [])])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == (records if archived else records[:1])


def test_projects_render_sorted_numbered_rows_with_team_date_and_ids(cli, mock_asana_client, listing_dir):
    records = [_project(name='Older', modified_at='2026-10-01T00:00:00Z'),
               _project('1200000000000202', name='新项目 🌿', modified_at='2026-10-07T00:00:00Z')]
    mock_asana_client.list_projects.return_value = records
    result = cli([*PROJECTS, '--ids'])

    assert result.exit_code == 0, result.output
    rows = _human_rows(result)
    assert len(rows) == 2
    assert rows[0].startswith('1.  2026-10-07  Platform') and rows[0].endswith('新项目 🌿')
    assert rows[1].startswith('2.  2026-10-01') and rows[1].endswith('Older')
    _name_column(rows, ['新项目 🌿', 'Older'])
    assert records[1]['gid'] in rows[0] and records[0]['gid'] in rows[1]
    token = _assert_saved_rows(listing_dir, 'projects', [records[1]['gid'], records[0]['gid']])
    assert f'Listing: {token}' in result.stdout
    assert 'Next: co asana tasks 1' in result.stdout
    _assert_no_credentials(result)


@pytest.mark.parametrize('command', ['projects', 'tasks'])
@pytest.mark.parametrize('options,limit', [([], 20), (['-n', '2'], 2), (['--last', '3'], 3),
                                         (['-n', '1'], 1), (['--last', '250'], 250)])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_list_limits_apply_after_sorting(command, options, limit, as_json, cli, mock_asana_client, listing_dir):
    records = _records(command, 251)
    getattr(mock_asana_client, f'list_{command}').return_value = records
    args = PROJECTS if command == 'projects' else TASKS
    result = cli([*args, *options, *(['--json'] if as_json else [])])
    expected = records[::-1][:limit]

    assert result.exit_code == 0, result.output
    if as_json:
        assert json.loads(result.stdout) == expected
        assert _listing_files(listing_dir) == {}
    else:
        rows = _human_rows(result)
        assert len(rows) == limit
        assert rows[0].startswith('1.') and rows[0].endswith(expected[0]['name'])
        assert rows[-1].startswith(f"{limit}.  ") and rows[-1].endswith(expected[-1]['name'])
        assert all(not row.startswith(' ') for row in rows)          # text readers still find the number first
        _name_column(rows, [r['name'] for r in expected])
        _assert_saved_rows(listing_dir, command, [r['gid'] for r in expected])


@pytest.mark.parametrize('command', ['projects', 'tasks'])
@pytest.mark.parametrize('value', ['0', '-1', '251', 'not-a-number'])
def test_list_invalid_limits_do_not_request(command, value, cli, mock_http):
    args = PROJECTS if command == 'projects' else TASKS
    result = cli([*args, '-n', value])

    assert result.exit_code == 2, result.output
    assert mock_http.requests == []


@pytest.mark.parametrize('command', ['projects', 'tasks'])
def test_json_preserves_unicode_source_records_and_does_not_update_listing(
        command, cli, mock_asana_client, listing_dir):
    _seed_listing(listing_dir, command)
    before = _listing_files(listing_dir)
    record = (_project if command == 'projects' else _task)(name='研发 🌿', extra={'nested': [None, {'kept': True}]})
    getattr(mock_asana_client, f'list_{command}').return_value = [record]
    result = cli([*(PROJECTS if command == 'projects' else TASKS), '--json'])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [record]
    assert '研发 🌿' in result.stdout
    assert 'Listing:' not in result.stdout and 'Next:' not in result.stdout
    assert result.stdout.lstrip().startswith('[')
    assert 'Next: co asana ' in result.stderr
    assert _listing_files(listing_dir) == before
    _assert_no_credentials(result)


@pytest.mark.parametrize('command', ['projects', 'tasks'])
def test_non_tty_output_stays_human_without_json_flag(command, cli, mock_asana_client):
    result = cli(PROJECTS if command == 'projects' else TASKS)

    assert result.exit_code == 0, result.output
    assert _human_rows(result)
    assert 'Listing:' in result.stdout and 'Next:' in result.stdout
    assert result.stderr == ''


@pytest.mark.parametrize('reference,index', [('1', 0), ('#1', 0), ('2', 1), ('#3', 2)])
@pytest.mark.parametrize('explicit', [False, True], ids=['recent', 'explicit'])
def test_tasks_resolve_project_rows_from_same_account_listing(
        reference, index, explicit, cli, mock_asana_client, listing_dir):
    gids = ['1200000000000201', '1200000000000202', '1200000000000203']
    token = _seed_listing(listing_dir, gids=gids)
    if explicit:
        _seed_listing(listing_dir, gids=['1200000000000209'])
    result = cli(['asana', 'tasks', reference, *(['--listing', token] if explicit else [])])

    assert result.exit_code == 0, result.output
    assert mock_asana_client.list_tasks.call_args.args == (gids[index],)
    mock_asana_client.list_projects.assert_not_called()


@pytest.mark.parametrize('case,reference', [
    ('missing', '1'), ('out-of-range', '2'), ('zero', '0'), ('expired', '#1'),
    ('wrong-account', '1'), ('wrong-family', '1'), ('invalid-token', '1'), ('four-digits', '9999'),
])
def test_tasks_reject_bad_project_rows_without_gid_fallback(case, reference, cli, mock_asana_client, listing_dir):
    options = []
    if case == 'wrong-family':
        token = _seed_listing(listing_dir, family='tasks')
        options = ['--listing', token]
    elif case == 'invalid-token':
        options = ['--listing', 'invalid']
    elif case != 'missing':
        _seed_listing(listing_dir, account='1200000000000999' if case == 'wrong-account' else USER_GID,
                      now=time.time() - 901 if case == 'expired' else None)
    result = cli(['asana', 'tasks', reference, *options])

    _assert_usage_failure(result, 'co asana projects')
    mock_asana_client.list_tasks.assert_not_called()
    mock_asana_client.list_projects.assert_not_called()


@pytest.mark.parametrize('gid', ['12345', PROJECT_GID])
def test_tasks_direct_gid_bypasses_listing_state(gid, cli, mock_asana_client, listing_dir):
    result = cli(['asana', 'tasks', gid, '--json', '--listing', 'unavailable'])

    assert result.exit_code == 0, result.output
    assert mock_asana_client.list_tasks.call_args.args == (gid,)
    mock_asana_client.list_projects.assert_not_called()
    assert _listing_files(listing_dir) == {}


def test_direct_gid_json_does_not_fetch_account_when_no_cache_is_needed(cli, mock_asana_client):
    result = cli([*TASKS, '--json'])

    assert result.exit_code == 0, result.output
    mock_asana_client.get_user.assert_not_called()


def test_tasks_exact_project_name_uses_selected_workspace(cli, mock_asana_client):
    mock_asana_client.get_user.return_value = _user([
        {'gid': WORKSPACE_GID, 'name': 'Engineering'}, {'gid': '1200000000000102', 'name': 'Other'}])
    mock_asana_client.list_projects.return_value = [_project(name='Website')]
    result = cli(['asana', 'tasks', 'Website', '--workspace', 'Other'])

    assert result.exit_code == 0, result.output
    mock_asana_client.list_projects.assert_called_once_with('1200000000000102')
    assert mock_asana_client.list_tasks.call_args.args == (PROJECT_GID,)


@pytest.mark.parametrize('name', ['website', 'Web', 'Missing'])
def test_tasks_project_name_is_exact_and_case_sensitive(name, cli, mock_asana_client):
    result = cli(['asana', 'tasks', name])

    _assert_usage_failure(result, 'co asana projects')
    mock_asana_client.list_tasks.assert_not_called()


@pytest.mark.parametrize('projects,expected', [
    ([_project(archived=True), _project('1200000000000202')], '1200000000000202'),
    ([_project(archived=True)], PROJECT_GID),
])
def test_tasks_project_name_prefers_active_then_falls_back_to_archived(projects, expected, cli, mock_asana_client):
    mock_asana_client.list_projects.return_value = projects
    result = cli(['asana', 'tasks', 'Website'])

    assert result.exit_code == 0, result.output
    assert mock_asana_client.list_tasks.call_args.args == (expected,)


def test_tasks_duplicate_active_project_names_show_gid_and_team(cli, mock_asana_client):
    projects = [_project(team={'gid': '1200000000000901', 'name': 'Platform'}),
                _project('1200000000000202', team={'gid': '1200000000000902', 'name': 'Mobile'})]
    mock_asana_client.list_projects.return_value = projects
    result = cli(['asana', 'tasks', 'Website'])

    _assert_usage_failure(result, 'co asana tasks <project-gid>')
    lines = result.stderr.splitlines()
    assert "Several projects are named 'Website'. Pass the project gid instead:" in lines[0]
    for project in projects:
        assert f"  Website  {project['team']['name']}  {project['gid']}" in lines
    mock_asana_client.list_tasks.assert_not_called()


@pytest.mark.parametrize('options,expected', [([], False), (['--status', 'open'], False),
                                            (['--status', 'done'], True), (['--status', 'all'], None)])
def test_tasks_status_maps_to_completed_filter(options, expected, cli, mock_asana_client):
    result = cli([*TASKS, *options])

    assert result.exit_code == 0, result.output
    assert mock_asana_client.list_tasks.call_args.kwargs['completed'] is expected


@pytest.mark.parametrize('value', ['closed', 'OPEN', ''])
def test_tasks_invalid_status_is_usage_error_before_requests(value, cli, mock_http):
    result = cli([*TASKS, '--status', value])

    _assert_usage_failure(result, 'co asana tasks --help')
    assert mock_http.requests == []


@pytest.mark.parametrize('value,expected', [(None, None), ('me', USER_GID),
                                          ('1200000000000998', '1200000000000998'),
                                          ('person@example.test', '1200000000000997')])
def test_tasks_assignee_maps_to_native_user_gid(value, expected, cli, mock_asana_client):
    me = _user()
    mock_asana_client.get_user.side_effect = lambda user='me': (
        me if user == 'me' else _user(gid='1200000000000997', email=user))
    result = cli([*TASKS, *(['--assignee', value] if value is not None else [])])

    assert result.exit_code == 0, result.output
    assert mock_asana_client.list_tasks.call_args.kwargs['assignee_gid'] == expected
    if value == 'person@example.test':
        assert any(call.args == (value,) for call in mock_asana_client.get_user.call_args_list)


@pytest.mark.parametrize('value', ['Alice', '@example.test', 'person@', 'person @example.test'])
def test_tasks_invalid_assignee_does_not_request_tasks(value, cli, mock_http, listing_dir):
    # A permissive reply must not turn an invalid argument into a successful command.
    mock_http.responses.extend([_success(), _success(_user(gid='1200000000000998')), _page([_task()])])
    result = cli([*TASKS, '--assignee', value])

    _assert_usage_failure(result)
    assert all(request.url.path == '/api/1.0/users/me' for request in mock_http.requests)
    assert _listing_files(listing_dir) == {}


@pytest.mark.parametrize('options,start,end', [
    (['--due-from', '2026-10-07'], date(2026, 10, 7), None),
    (['--due-to', '2026-10-08'], None, date(2026, 10, 8)),
    (['--due-from', '2026-10-07', '--due-to', '2026-10-08'], date(2026, 10, 7), date(2026, 10, 8)),
])
def test_tasks_due_flags_map_to_dates(options, start, end, cli, mock_asana_client):
    result = cli([*TASKS, *options])

    assert result.exit_code == 0, result.output
    kwargs = mock_asana_client.list_tasks.call_args.kwargs
    assert kwargs['due_from'] == start and kwargs['due_to'] == end
    assert start is None or type(kwargs['due_from']) is date
    assert end is None or type(kwargs['due_to']) is date


@pytest.mark.parametrize('flag', ['--due-from', '--due-to'])
@pytest.mark.parametrize('value', ['2026-02-30', 'not-a-date', '2026-10-07T09:30:00Z'])
def test_tasks_invalid_due_date_is_usage_error_before_requests(flag, value, cli, mock_http):
    result = cli([*TASKS, flag, value])

    _assert_usage_failure(result, 'co asana tasks --help')
    assert mock_http.requests == []


def test_tasks_reversed_due_range_does_not_request_tasks(cli, mock_http, listing_dir):
    mock_http.responses.append(_success())
    result = cli([*TASKS, '--due-from', '2026-10-08', '--due-to', '2026-10-07'])

    _assert_usage_failure(result)
    assert all(request.url.path == '/api/1.0/users/me' for request in mock_http.requests)
    assert _listing_files(listing_dir) == {}


@pytest.mark.parametrize('value', ['2026-10-07T09:00:00+11:00', '2026-10-06T22:00:00Z'])
def test_tasks_aware_modified_since_maps_to_datetime(value, cli, mock_asana_client):
    result = cli([*TASKS, '--modified-since', value])

    assert result.exit_code == 0, result.output
    since = mock_asana_client.list_tasks.call_args.kwargs['modified_since']
    assert since == datetime.fromisoformat(value.replace('Z', '+00:00'))
    assert since.utcoffset() is not None


@pytest.mark.parametrize('value', ['2026-10-07T09:00:00', 'not-a-time', '2026-10-07'])
def test_tasks_invalid_modified_since_does_not_request_tasks(value, cli, mock_http, listing_dir):
    mock_http.responses.append(_success())
    result = cli([*TASKS, '--modified-since', value])

    _assert_usage_failure(result)
    assert all(request.url.path == '/api/1.0/users/me' for request in mock_http.requests)
    assert _listing_files(listing_dir) == {}


def test_long_assignees_are_cut_so_names_fit_an_80_column_terminal(cli, mock_asana_client, listing_dir):
    """Review: a long assignee with --ids pushed every name to column 95."""
    from rich.cells import cell_len
    long_name = 'Alexandria Montgomery-Fitzgerald the Third'
    records = [_task(str(1200000000000400 + i), name=f'Task {i}', assignee={'gid': '1', 'name': long_name if i == 3 else 'Al'},
                     modified_at=f'2026-10-{i + 1:02}T00:00:00Z') for i in range(12)]
    mock_asana_client.list_tasks.return_value = records
    result = cli([*TASKS, '--status', 'all', '--ids'])

    assert result.exit_code == 0, result.output
    rows = _human_rows(result)
    names = [r['name'] for r in records[::-1]]
    _name_column(rows, names)
    start = cell_len(rows[0][:-len(names[0])])
    assert start <= 64                                            # 16+ cells left for the name at 80 columns
    assert 'Alexandria Mont…' in result.stdout and long_name not in result.stdout


def test_tasks_render_sorted_rows_status_placeholders_and_ids(cli, mock_asana_client, listing_dir, monkeypatch):
    from connectonion.useful_tools import asana
    monkeypatch.setattr(asana, '_local_zone', lambda: timezone(timedelta(hours=11)))
    records = [_task(name='Older', completed=True, assignee=None, modified_at='2026-10-01T00:00:00Z'),
               _task('1200000000000302', name='发布 🌿', due_at='2026-10-06T22:30:00Z')]
    mock_asana_client.list_tasks.return_value = records
    result = cli([*TASKS, '--status', 'all', '--ids'])

    assert result.exit_code == 0, result.output
    rows = _human_rows(result)
    assert len(rows) == 2
    assert rows[0].startswith('1.  open  due 2026-10-07  Alice') and rows[0].endswith('发布 🌿')
    assert rows[1].startswith('2.  done  due -           -    ') and rows[1].endswith('Older')
    _name_column(rows, ['发布 🌿', 'Older'])
    assert records[1]['gid'] in rows[0] and records[0]['gid'] in rows[1]
    _assert_saved_rows(listing_dir, 'tasks', [records[1]['gid'], records[0]['gid']])
    assert 'Next: co asana task 1' in result.stdout
    _assert_no_credentials(result)


@pytest.mark.parametrize('command', ['projects', 'tasks'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_empty_lists_succeed_and_offer_appropriate_next(command, as_json, cli, mock_asana_client):
    getattr(mock_asana_client, f'list_{command}').return_value = []
    result = cli([*(PROJECTS if command == 'projects' else TASKS), *(['--json'] if as_json else [])])

    assert result.exit_code == 0, result.output
    if as_json:
        assert json.loads(result.stdout) == []
        assert 'Next: co asana ' in result.stderr
    else:
        assert _human_rows(result) == []
        assert '0 ' in result.stdout
        assert 'Next: co asana ' in result.stdout
        if command == 'tasks':
            assert '--status all' in result.stdout
        assert 'Next: co asana task 1' not in result.stdout
        assert 'Next: co asana tasks 1' not in result.stdout


@pytest.mark.parametrize('command', ['projects', 'tasks'])
def test_empty_human_list_invalidates_recent_pointer_for_its_family(
        command, cli, mock_asana_client, listing_dir):
    other = 'tasks' if command == 'projects' else 'projects'
    _seed_listing(listing_dir, command)
    other_token = _seed_listing(listing_dir, other)
    getattr(mock_asana_client, f'list_{command}').return_value = []
    result = cli(PROJECTS if command == 'projects' else TASKS)

    assert result.exit_code == 0, result.output
    assert not (listing_dir / f'last-{command}').exists()
    assert (listing_dir / f'last-{other}').read_text() == other_token


@pytest.mark.parametrize('command', ['projects', 'tasks'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_later_page_cli_failure_is_safe_and_does_not_save_partial_rows(
        command, as_json, cli, mock_http, listing_dir, monkeypatch):
    from connectonion.useful_tools import asana
    _seed_listing(listing_dir, command)
    before = _listing_files(listing_dir)
    record = _project() if command == 'projects' else _task()
    direct_json = command == 'tasks' and as_json

    def respond(request):
        mock_http.requests.append(request)
        assert len(mock_http.requests) <= 3, 'Unexpected pagination request'
        if request.url.path == '/api/1.0/users/me':
            assert not direct_json, 'Direct GID JSON must not request the account'
            return _success()
        assert request.url.path == f'/api/1.0/{command}'
        offset = request.url.params.get('offset')
        assert offset in (None, 'second')
        return _page([record], 'second') if offset is None else _failure(500)

    monkeypatch.setattr(asana, '_http', lambda: httpx.Client(timeout=30, transport=httpx.MockTransport(respond)))
    result = cli([*(PROJECTS if command == 'projects' else TASKS), *(['--json'] if as_json else [])])

    _assert_safe_failure(result)
    assert f'Read 1 {"project" if command == "projects" else "task"}, incomplete' in result.stderr
    assert 'HTTP 500' in result.stderr
    assert _listing_files(listing_dir) == before
    expected_paths = ([] if direct_json else ['/api/1.0/users/me']) + [f'/api/1.0/{command}'] * 2
    assert [request.url.path for request in mock_http.requests] == expected_paths
    assert [request.url.params.get('offset') for request in mock_http.requests[-2:]] == [None, 'second']


@pytest.mark.parametrize('command', ['projects', 'tasks'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_malformed_list_cli_response_is_safe(command, as_json, cli, mock_http, listing_dir):
    mock_http.responses.extend([_success(), _page([{'gid': None}])])
    result = cli([*(PROJECTS if command == 'projects' else TASKS), *(['--json'] if as_json else [])])

    _assert_safe_failure(result)
    assert _listing_files(listing_dir) == {}


@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_bad_project_reference_has_usage_exit_and_empty_stdout(as_json, cli, mock_asana_client):
    result = cli(['asana', 'tasks', 'Missing', *(['--json'] if as_json else [])])

    _assert_usage_failure(result, 'co asana projects')
    mock_asana_client.list_tasks.assert_not_called()


def test_project_name_can_be_resolved_only_on_later_api_page(cli, mock_http, listing_dir):
    mock_http.responses.extend([_success(), _page([_project(name='Other')], 'second'),
                                _page([_project('1200000000000202', name='Target')]), _page([])])
    result = cli(['asana', 'tasks', 'Target', '--json'])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == []
    assert len(mock_http.requests) == 4
    assert mock_http.requests[2].url.params['offset'] == 'second'
    assert mock_http.requests[3].url.params['project'] == '1200000000000202'
    assert _listing_files(listing_dir) == {}


# source details, activity, references and safe output.
@pytest.fixture
def mock_detail_client(monkeypatch, listing_dir):
    from connectonion.useful_tools import asana
    client = SimpleNamespace(get_user=Mock(return_value=_user()),
                             get_task=Mock(return_value=_task_detail()),
                             list_stories=Mock(return_value=[_story()]), flow=Mock())
    client.flow.attach_mock(client.get_task, 'get_task')
    client.flow.attach_mock(client.list_stories, 'list_stories')
    monkeypatch.setattr(asana, 'Asana', Mock(return_value=client))
    return client


@pytest.fixture
def detail_http(monkeypatch, mock_http, listing_dir):
    from connectonion.useful_tools import asana
    mocked = SimpleNamespace(detail=_task_detail(), detail_failure=None,
                             pages={None: _page([_story()])}, requests=mock_http.requests)

    def respond(request):
        mocked.requests.append(request)
        assert len(mocked.requests) <= 8, 'Unbounded detail requests'
        assert request.method == 'GET'
        if request.url.path == '/api/1.0/users/me':
            return _success()
        if request.url.path == f'/api/1.0/tasks/{TASK_GID}':
            return mocked.detail_failure or httpx.Response(200, json={'data': mocked.detail})
        assert request.url.path == f'/api/1.0/tasks/{TASK_GID}/stories'
        offset = request.url.params.get('offset')
        assert offset in mocked.pages, 'Unexpected story offset'
        response = mocked.pages[offset]
        if isinstance(response, httpx.TransportError):
            raise response
        return response

    def fake_http():
        client = httpx.Client(timeout=30, transport=httpx.MockTransport(respond))
        mock_http.clients.append(client)
        return client

    monkeypatch.setattr(asana, '_http', fake_http)
    return mocked


def _assert_detail_success(result):
    assert result.exit_code == 0, result.output
    tips = [line for line in (result.stdout + result.stderr).splitlines() if line.startswith('Next: ')]
    assert len(tips) == 1 and tips[0].startswith('Next: co ')
    assert 'Traceback (most recent call last)' not in result.output
    _assert_no_credentials(result)


def _next_arguments(result):
    line = next(line for line in (result.stdout + result.stderr).splitlines() if line.startswith('Next: '))
    return shlex.split(line.removeprefix('Next: '))


def _json_contains(value, source):
    """Check raw content without choosing the unspecified task wrapper keys."""
    if value == source:
        return True
    if isinstance(value, dict):
        return any(_json_contains(child, source) for child in value.values())
    if isinstance(value, list):
        return any(_json_contains(child, source) for child in value)
    return False


@pytest.mark.parametrize('command', ['task', 'stories'])
def test_detail_help_without_token_never_requests(command, cli, mock_http, monkeypatch):
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')
    result = cli(['asana', command, '--help'])

    assert result.exit_code == 0, result.output
    assert '--listing' in result.stdout and '--json' in result.stdout
    assert mock_http.requests == []


@pytest.mark.parametrize('command', ['task', 'stories'])
@pytest.mark.parametrize('arguments', [[], [TASK_GID, '--unknown-option']])
def test_detail_commands_reject_invalid_syntax_without_http(command, arguments, cli, mock_http):
    result = cli(['asana', command, *arguments])

    assert result.exit_code == 2, result.output
    assert mock_http.requests == []


@pytest.mark.parametrize('command', ['task', 'stories'])
@pytest.mark.parametrize('reference,index', [('1', 0), ('#1', 0), ('2', 1)])
@pytest.mark.parametrize('explicit', [False, True], ids=['recent', 'explicit'])
def test_detail_commands_resolve_task_rows_to_native_gid(
        command, reference, index, explicit, cli, mock_detail_client, listing_dir):
    gids = [TASK_GID, '1200000000000902']
    token = _seed_listing(listing_dir, family='tasks', gids=gids)
    if explicit:
        _seed_listing(listing_dir, family='tasks', gids=['1200000000000909'])
    mock_detail_client.get_task.return_value = _task_detail(gids[index])
    result = cli(['asana', command, reference, *(['--listing', token] if explicit else [])])

    _assert_detail_success(result)
    mock_detail_client.list_stories.assert_called_once_with(gids[index])
    if command == 'task':
        mock_detail_client.get_task.assert_called_once_with(gids[index])
        assert [call[0] for call in mock_detail_client.flow.mock_calls] == ['get_task', 'list_stories']
    else:
        mock_detail_client.get_task.assert_not_called()


@pytest.mark.parametrize('command', ['task', 'stories'])
@pytest.mark.parametrize('gid', ['12345', TASK_GID])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_detail_direct_gid_bypasses_account_and_listing_state(command, gid, as_json, cli, mock_detail_client):
    mock_detail_client.get_task.return_value = _task_detail(gid)
    result = cli(['asana', command, gid, '--listing', 'unavailable', *(['--json'] if as_json else [])])

    _assert_detail_success(result)
    mock_detail_client.get_user.assert_not_called()
    mock_detail_client.list_stories.assert_called_once_with(gid)
    if command == 'task':
        mock_detail_client.get_task.assert_called_once_with(gid)
    else:
        mock_detail_client.get_task.assert_not_called()
    assert '--listing' not in _next_arguments(result)


@pytest.mark.parametrize('command', ['task', 'stories'])
@pytest.mark.parametrize('case,reference', [
    ('missing', '1'), ('out-of-range', '2'), ('four-digits', '9999'), ('zero', '#0'),
    ('expired', '#1'), ('wrong-account', '1'), ('wrong-family', '1'), ('invalid-token', '1'),
])
def test_detail_bad_row_is_usage_error_without_gid_fallback(
        command, case, reference, cli, mock_detail_client, listing_dir):
    options = []
    if case == 'wrong-family':
        token = _seed_listing(listing_dir, family='projects', gids=[TASK_GID])
        options = ['--listing', token]
    elif case == 'invalid-token':
        options = ['--listing', 'invalid']
    elif case != 'missing':
        _seed_listing(listing_dir, family='tasks', gids=[TASK_GID],
                      account='1200000000000999' if case == 'wrong-account' else USER_GID,
                      now=time.time() - 901 if case == 'expired' else None)
    result = cli(['asana', command, reference, *options])

    _assert_usage_failure(result)
    mock_detail_client.get_task.assert_not_called()
    mock_detail_client.list_stories.assert_not_called()


@pytest.mark.parametrize('command', ['task', 'stories'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_detail_commands_reject_textual_task_name(command, as_json, cli, mock_detail_client):
    result = cli(['asana', command, 'Ship website', *(['--json'] if as_json else [])])

    _assert_usage_failure(result)
    mock_detail_client.get_task.assert_not_called()
    mock_detail_client.list_stories.assert_not_called()


@pytest.mark.parametrize('assignee', [None, {'gid': USER_GID, 'name': 'Alice'}])
def test_task_human_view_shows_source_details_followers_and_projects(assignee, cli, mock_detail_client):
    detail = _task_detail(assignee=assignee)
    before = deepcopy(detail)
    mock_detail_client.get_task.return_value = detail
    result = cli(['asana', 'task', TASK_GID])

    _assert_detail_success(result)
    assert detail['name'] in result.stdout and TASK_GID in result.stdout
    assert detail['notes'] in result.stdout
    assert 'Website' in result.stdout and 'Mobile' in result.stdout
    follower_line = next(line for line in result.stdout.splitlines() if 'Followers' in line)
    assert 'Bob' in follower_line and 'Carol' in follower_line
    assert 'Alice' not in follower_line
    assignee_line = next(line for line in result.stdout.splitlines() if 'Assignee' in line)
    assert ('Alice' if assignee else '-') in assignee_line
    assert detail == before


@pytest.mark.parametrize('fields', [{'name': None}, {'notes': None}, {'notes': ''}, {'followers': []}])
def test_task_human_view_handles_valid_empty_optional_fields(fields, cli, mock_detail_client):
    detail = _task_detail(**fields)
    before = deepcopy(detail)
    mock_detail_client.get_task.return_value = detail
    result = cli(['asana', 'task', TASK_GID])

    _assert_detail_success(result)
    assert TASK_GID in result.stdout
    assert 'None' not in result.stdout
    assert detail == before


@pytest.mark.parametrize('with_comment', [False, True], ids=['only-system', 'mixed'])
def test_task_comment_view_does_not_present_system_activity_as_comments(with_comment, cli, mock_detail_client):
    records = [_story(type='system', resource_subtype='assigned', text='System assignment marker')]
    if with_comment:
        records.append(_story('1200000000000901', text='User comment marker'))
    before = deepcopy(records)
    mock_detail_client.list_stories.return_value = records
    result = cli(['asana', 'task', TASK_GID])

    _assert_detail_success(result)
    assert 'System assignment marker' not in result.stdout
    assert ('User comment marker' in result.stdout) is with_comment
    assert records == before


@pytest.mark.parametrize('command', ['task', 'stories'])
@pytest.mark.parametrize('kind', ['empty', 'comment', 'mixed', 'system', 'null-author', 'missing-text'])
def test_activity_views_handle_empty_comments_system_and_nullable_fields(kind, command, cli, mock_detail_client):
    records = [] if kind == 'empty' else [_story(text='Comment source marker')]
    if kind in ('mixed', 'system'):
        system = _story('1200000000000901', type='system', resource_subtype='marked_complete',
                        text='System completion marker')
        records = records + [system] if kind == 'mixed' else [system]
    if kind == 'null-author':
        records[0]['created_by'] = None
        mock_detail_client.get_task.return_value = _task_detail(assignee=None)
    if kind == 'missing-text':
        records[0].pop('text')
        records[0]['created_by'] = {'gid': USER_GID, 'name': 'Textless Author'}
    before = deepcopy(records)
    mock_detail_client.list_stories.return_value = records
    result = cli(['asana', command, TASK_GID])

    _assert_detail_success(result)
    if kind in ('comment', 'mixed', 'null-author'):
        assert 'Comment source marker' in result.stdout
    if command == 'stories' and kind in ('system', 'mixed'):
        assert 'System completion marker' in result.stdout
        assert 'marked_complete' in result.stdout
    if kind == 'null-author':
        assert 'Alice' not in result.stdout
    if kind == 'missing-text':
        assert 'Textless Author' in result.stdout
    assert records == before


@pytest.mark.parametrize('command', ['task', 'stories'])
@pytest.mark.parametrize('times', [
    ['2026-10-08T10:30:00Z', '2026-10-08T08:00:00Z', '2026-10-08T09:15:00Z'],
    ['2026-10-08T21:30:00+11:00', '2026-10-08T09:00:00+01:00', '2026-10-08T09:15:00Z'],
], ids=['shuffled-z', 'shuffled-offsets'])
def test_human_activity_is_chronological_without_mutating_source(
        command, times, cli, mock_detail_client, monkeypatch):
    from connectonion.useful_tools import asana
    monkeypatch.setattr(asana, '_local_zone', lambda: timezone.utc)
    records = [_story(str(1200000000000900 + i), text=f'Chronological-{label}', created_at=moment)
               for i, (label, moment) in enumerate(zip(('C', 'A', 'B'), times))]
    before = deepcopy(records)
    mock_detail_client.list_stories.return_value = records
    result = cli(['asana', command, TASK_GID])

    _assert_detail_success(result)
    positions = [result.stdout.index(f'Chronological-{label}') for label in ('A', 'B', 'C')]
    assert positions == sorted(positions)
    for label, clock in zip(('A', 'B', 'C'), ('08:00', '09:15', '10:30')):
        line = next(line for line in result.stdout.splitlines() if f'Chronological-{label}' in line)
        assert clock in line
        assert 'Alice' in line
    assert records == before


@pytest.mark.parametrize('command', ['task', 'stories'])
@pytest.mark.parametrize('reference', ['1', '#1'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_explicit_task_listing_is_used_and_preserved_in_context_next(
        command, reference, as_json, cli, mock_detail_client, listing_dir):
    token = _seed_listing(listing_dir, family='tasks', gids=[TASK_GID])
    _seed_listing(listing_dir, family='tasks', gids=['1200000000000999'])
    result = cli(['asana', command, reference, '--listing', token, *(['--json'] if as_json else [])])

    _assert_detail_success(result)
    mock_detail_client.list_stories.assert_called_once_with(TASK_GID)
    if command == 'task':
        mock_detail_client.get_task.assert_called_once_with(TASK_GID)
    next_args = _next_arguments(result)
    if next_args[:3] in (['co', 'asana', 'task'], ['co', 'asana', 'stories']):
        assert '--listing' in next_args
        assert next_args[next_args.index('--listing') + 1] == token


@pytest.mark.parametrize('command', ['task', 'stories'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_direct_task_gid_next_does_not_add_listing(command, as_json, cli, mock_detail_client):
    result = cli(['asana', command, TASK_GID, *(['--json'] if as_json else [])])

    _assert_detail_success(result)
    assert '--listing' not in _next_arguments(result)


@pytest.mark.parametrize('command', ['task', 'stories'])
def test_activity_cli_reads_every_page_before_human_output(command, cli, detail_http):
    records = [_story(str(1200000000000900 + i), text=f'Page-{i + 1} activity marker') for i in range(3)]
    detail_http.pages = {None: _page(records[:1], 'opaque +/='),
                         'opaque +/=': _page(records[1:2], 'third'), 'third': _page(records[2:])}
    result = cli(['asana', command, TASK_GID])

    _assert_detail_success(result)
    for record in records:
        assert record['text'] in result.stdout
    requests = [r for r in detail_http.requests if r.url.path.endswith('/stories')]
    assert [r.url.params.get('offset') for r in requests] == [None, 'opaque +/=', 'third']


@pytest.mark.parametrize('command', ['task', 'stories'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
@pytest.mark.parametrize('later', [False, True], ids=['first-story-page', 'later-story-page'])
def test_activity_cli_failure_never_emits_partial_detail_or_json(command, as_json, later, cli, detail_http):
    detail_http.pages = ({None: _page([_story()], 'later'), 'later': _failure(500)}
                         if later else {None: _failure(500)})
    result = cli(['asana', command, TASK_GID, *(['--json'] if as_json else [])])

    _assert_safe_failure(result)
    assert result.stdout == ''
    assert 'HTTP 500' in result.stderr
    if command == 'task':
        assert detail_http.requests[0].url.path == f'/api/1.0/tasks/{TASK_GID}'
    if later:
        assert 'Read 1 story, incomplete' in result.stderr
    assert 'Original notes' not in result.stdout


@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_task_404_is_safe_operational_failure_without_deletion_claim(as_json, cli, detail_http):
    detail_http.detail_failure = _failure(404, 'Not Found')
    result = cli(['asana', 'task', TASK_GID, *(['--json'] if as_json else [])])

    _assert_safe_failure(result)
    assert result.stdout == ''
    error_line = next(line for line in result.stderr.splitlines() if '✗' in line).lower()
    assert 'task' in error_line
    assert any(phrase in error_line for phrase in ('not found', 'not visible', 'cannot see', 'no asana task'))
    assert 'deleted' not in result.output.lower()
    assert len(detail_http.requests) == 1


@pytest.mark.parametrize('command', ['task', 'stories'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
@pytest.mark.parametrize('later', [False, True], ids=['first-page', 'later-page'])
@pytest.mark.parametrize('fields', INVALID_STORY_TIMES)
def test_invalid_story_created_at_fails_whole_cli_operation(
        fields, later, command, as_json, cli, detail_http):
    bad = _story_with_time(fields)
    detail_http.pages = ({None: _page([_story()], 'later'), 'later': _page([bad])}
                         if later else {None: _page([_story(), bad])})
    result = cli(['asana', command, TASK_GID, *(['--json'] if as_json else [])])

    _assert_safe_failure(result)
    assert result.stdout == ''
    if later:
        assert 'Read 1 story, incomplete' in result.stderr


@pytest.mark.parametrize('command', ['task', 'stories'])
def test_detail_json_contains_raw_unicode_data_without_assuming_task_wrapper(command, cli, mock_detail_client):
    detail = _task_detail(name='发布 🌿', extra={'nested': [None, {'kept': True}]})
    records = [_story(text='用户评论 🌿', extra={'nested': [None]}),
               _story('1200000000000902', type='system', resource_subtype='assigned', created_by=None)]
    records[-1].pop('text')
    before = deepcopy((detail, records))
    mock_detail_client.get_task.return_value = detail
    mock_detail_client.list_stories.return_value = records
    result = cli(['asana', command, TASK_GID, '--json'])

    _assert_detail_success(result)
    payload = json.loads(result.stdout)
    assert _json_contains(payload, records)
    if command == 'task':
        assert _json_contains(payload, detail)
        assert '发布 🌿' in result.stdout
    assert '用户评论 🌿' in result.stdout
    assert 'Next:' not in result.stdout and 'Listing:' not in result.stdout
    assert 'Next: co ' in result.stderr
    assert (detail, records) == before


@pytest.mark.parametrize('command', ['task', 'stories'])
def test_detail_non_tty_output_is_human_without_json_flag(command, cli, mock_detail_client):
    result = cli(['asana', command, TASK_GID])

    _assert_detail_success(result)
    assert 'Original comment' in result.stdout
    assert 'Next: co ' in result.stdout
    assert result.stderr == ''
    assert not result.stdout.lstrip().startswith(('{', '['))


# ---------------------------------------------------------------------------
# co asana update / co asana comment
# ---------------------------------------------------------------------------

def _data(data, status=200):
    return httpx.Response(status, json={'data': data})


def _writes(mocked):
    return [request for request in mocked.requests if request.method != 'GET']


def _next(output):
    [line] = [line for line in output.splitlines() if line.startswith('Next: ')]
    return line.removeprefix('Next: ')


@pytest.fixture
def write_cli(mock_http, listing_dir):
    from connectonion.cli.main import app
    runner = CliRunner()
    return lambda args, **kwargs: runner.invoke(app, args, **kwargs)


def _replay(write_cli, next_command, **kwargs):
    words = shlex.split(next_command)
    assert words[0] == 'co'
    return write_cli(words[1:], **kwargs)


def test_update_preview_changes_nothing_and_names_the_rerun(write_cli, mock_http):
    mock_http.responses.append(_data(_task_detail(due_on='2026-10-14')))

    result = write_cli(['asana', 'update', TASK_GID, '--due-on', '2026-10-30', '--done'])

    assert result.exit_code == 0, result.output
    assert _writes(mock_http) == []
    assert 'Preview' in result.stdout and 'Nothing changed in Asana' in result.stdout
    assert '2026-10-14 → 2026-10-30' in result.stdout
    assert 'open → done' in result.stdout
    assert _next(result.stdout) == f'co asana update {TASK_GID} --due-on 2026-10-30 --done --yes'


def test_update_open_preview_then_yes_puts_completed_false(write_cli, mock_http):
    mock_http.responses.append(_data(_task_detail(completed=True)))
    preview = write_cli(['asana', 'update', TASK_GID, '--open'])

    assert preview.exit_code == 0, preview.output
    assert _writes(mock_http) == []
    assert 'done → open' in preview.stdout
    assert _next(preview.stdout) == f'co asana update {TASK_GID} --open --yes'

    mock_http.responses += [_data(_task_detail(completed=True)), _data(_task_detail(completed=False))]
    result = _replay(write_cli, _next(preview.stdout))

    assert result.exit_code == 0, result.output
    [put] = _writes(mock_http)
    assert put.method == 'PUT'
    assert json.loads(put.content) == {'data': {'completed': False}}
    assert 'Updated' in result.stdout and 'open' in result.stdout
    assert _next(result.stdout) == f'co asana task {TASK_GID}'


@pytest.mark.parametrize('args, message', [
    (['--open', '--done'], 'not both'),
    ([], 'Nothing to change'),
    (['--due-on', '30/10'], '--due-on'),
])
def test_update_usage_errors_exit_2_without_requests(args, message, write_cli, mock_http):
    result = write_cli(['asana', 'update', TASK_GID, *args])

    assert result.exit_code == 2, result.output
    assert message in result.output
    assert mock_http.requests == []


def test_update_due_on_refuses_a_task_with_a_time(write_cli, mock_http):
    mock_http.responses.append(_data(_task_detail(due_on='2026-10-14', due_at='2026-10-14T06:30:00Z')))

    result = write_cli(['asana', 'update', TASK_GID, '--due-on', '2026-10-30', '--yes'])

    assert result.exit_code == 2, result.output
    assert _writes(mock_http) == []


def test_update_json_preview_is_parseable(write_cli, mock_http):
    mock_http.responses.append(_data(_task_detail()))

    result = write_cli(['asana', 'update', TASK_GID, '--done', '--json'])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {'preview': True, 'task_gid': TASK_GID,
                                         'changes': {'completed': {'before': False, 'after': True}}}
    assert _next(result.stderr) == f'co asana update {TASK_GID} --done --yes --json'


def test_write_row_number_needs_listing(write_cli, mock_http):
    result = write_cli(['asana', 'update', '1', '--done'])

    assert result.exit_code == 2, result.output
    assert mock_http.requests == []


def test_write_row_number_with_listing_previews_the_gid(write_cli, mock_http, listing_dir):
    token = _seed_listing(listing_dir, family='tasks', gids=[TASK_GID])
    mock_http.responses += [_success(), _data(_task_detail())]

    result = write_cli(['asana', 'update', '1', '--listing', token, '--done'])

    assert result.exit_code == 0, result.output
    assert _writes(mock_http) == []
    assert _next(result.stdout) == f'co asana update {TASK_GID} --done --yes'


def test_update_unknown_outcome_points_to_the_task_and_is_not_resent(write_cli, mock_http):
    mock_http.responses += [_data(_task_detail()), httpx.ReadTimeout('slow')]

    result = write_cli(['asana', 'update', TASK_GID, '--done', '--yes'])

    assert result.exit_code == 1, result.output
    assert len(_writes(mock_http)) == 1
    assert 'may have been saved' in result.stderr
    assert 'Check before running it again' in result.stderr
    assert _next(result.stderr) == f'co asana task {TASK_GID}'


def test_update_5xx_shows_asanas_message(write_cli, mock_http):
    mock_http.responses += [_data(_task_detail()), _failure(503, 'Server is undergoing maintenance.')]

    result = write_cli(['asana', 'update', TASK_GID, '--done', '--yes'])

    assert result.exit_code == 1, result.output
    assert 'Server is undergoing maintenance' in result.stderr
    assert _next(result.stderr) == f'co asana task {TASK_GID}'


def test_comment_yes_posts_exact_text_and_accepts_201(write_cli, mock_http):
    text = 'Moved\n"x" [literal]'
    mock_http.responses += [_data(_task_detail()), _data(_story(text=text), 201)]

    result = write_cli(['asana', 'comment', TASK_GID, text, '--yes'])

    assert result.exit_code == 0, result.output
    [post] = _writes(mock_http)
    assert post.method == 'POST'
    assert json.loads(post.content) == {'data': {'text': text}}
    assert 'Commented on' in result.stdout
    assert _next(result.stdout) == f'co asana stories {TASK_GID}'


@pytest.mark.parametrize('args, stdin', [(['   '], None), (['-'], ''), (['-'], ' \n')])
def test_comment_empty_text_exits_2(args, stdin, write_cli, mock_http):
    result = write_cli(['asana', 'comment', TASK_GID, *args], input=stdin)

    assert result.exit_code == 2, result.output
    assert mock_http.requests == []


def test_comment_argument_preview_next_replays_the_same_text(write_cli, mock_http):
    text = "It's done; see #42"
    mock_http.responses.append(_data(_task_detail()))
    preview = write_cli(['asana', 'comment', TASK_GID, text])

    assert preview.exit_code == 0, preview.output
    assert _writes(mock_http) == []

    mock_http.responses += [_data(_task_detail()), _data(_story(text=text), 201)]
    result = _replay(write_cli, _next(preview.stdout))

    assert result.exit_code == 0, result.output
    assert json.loads(_writes(mock_http)[0].content) == {'data': {'text': text}}


@pytest.fixture(params=[False, True], ids=['plain', 'terminal'])
def tip_console(request, monkeypatch):
    from rich.console import Console
    from connectonion.cli import style

    monkeypatch.setenv('TERM', 'xterm-256color')

    def console(stderr=False):
        return Console(theme=style.THEME, stderr=stderr, force_terminal=request.param,
                       highlight=False, soft_wrap=True)

    monkeypatch.setattr(style, 'console', console)


@pytest.mark.parametrize('text', [
    'Keep [red]literal[/red] tags',
    '[bold]Keep[/bold] [dim]all[/dim] [yellow]these[/yellow] [cyan]tags[/cyan] [green]too[/green]',
    'Keep :smile: and [red]literal[/red] text',
])
@pytest.mark.parametrize('as_json', [False, True])
@pytest.mark.parametrize('piped', [False, True], ids=['argument', 'stdin'])
def test_comment_preview_next_preserves_literal_formatting(text, as_json, piped, tip_console, write_cli, mock_http):
    flags = ['--json'] if as_json else []
    mock_http.responses.append(_data(_task_detail()))

    preview = write_cli(['asana', 'comment', TASK_GID, '-' if piped else text, *flags],
                        input=text if piped else None)

    assert preview.exit_code == 0, preview.output
    assert _writes(mock_http) == []
    if as_json:
        assert json.loads(preview.stdout)['changes'] == {'comment': text}
    next_command = _next(unstyle(preview.stderr if as_json else preview.stdout))
    assert text in shlex.split(next_command)

    mock_http.responses += [_data(_task_detail()), _data(_story(text=text), 201)]
    result = _replay(write_cli, next_command, input='')

    assert result.exit_code == 0, result.output
    [post] = _writes(mock_http)
    assert post.method == 'POST'
    assert json.loads(post.content) == {'data': {'text': text}}


@pytest.mark.parametrize('text', [
    'Please run co asana check',
    "It's [red]literal[/red]: co asana check; then co asana tasks",
])
@pytest.mark.parametrize('as_json', [False, True])
@pytest.mark.parametrize('piped', [False, True], ids=['argument', 'stdin'])
def test_comment_preview_next_env_file_preserves_body(text, as_json, piped, tip_console, write_cli, mock_http, tmp_path):
    env_file = tmp_path / "account's [red]team.env"
    env_file.write_text(f'ASANA_ACCESS_TOKEN={TOKEN}\n', encoding='utf-8')
    flags = ['--json'] if as_json else []
    mock_http.responses.append(_data(_task_detail()))

    preview = write_cli(['--env-file', str(env_file), 'asana', 'comment', TASK_GID,
                         '-' if piped else text, *flags], input=text if piped else None)

    assert preview.exit_code == 0, preview.output
    assert _writes(mock_http) == []
    if as_json:
        assert json.loads(preview.stdout)['changes'] == {'comment': text}
    next_command = _next(unstyle(preview.stderr if as_json else preview.stdout))
    words = shlex.split(next_command)
    assert words[:3] == ['co', '--env-file', str(env_file)]
    assert words.count('--env-file') == 1
    assert text in words

    mock_http.responses += [_data(_task_detail()), _data(_story(text=text), 201)]
    result = _replay(write_cli, next_command, input='')

    assert result.exit_code == 0, result.output
    [post] = _writes(mock_http)
    assert post.method == 'POST'
    assert json.loads(post.content) == {'data': {'text': text}}


def test_comment_stdin_one_line_next_carries_the_text(write_cli, mock_http):
    text = "Moved to Friday, it's fine"
    mock_http.responses.append(_data(_task_detail()))
    preview = write_cli(['asana', 'comment', TASK_GID, '-'], input=text)

    assert preview.exit_code == 0, preview.output
    assert _writes(mock_http) == []
    assert text in preview.stdout
    assert 'pipe the same text' not in preview.stdout
    assert ' - ' not in _next(preview.stdout)

    # Replayed exactly as printed, with nothing on standard input.
    mock_http.responses += [_data(_task_detail()), _data(_story(text=text), 201)]
    result = _replay(write_cli, _next(preview.stdout), input='')

    assert result.exit_code == 0, result.output
    assert json.loads(_writes(mock_http)[0].content) == {'data': {'text': text}}


@pytest.mark.parametrize('text', ['Line one\nLine two', 'Moved to Friday\n', 'Two trailing newlines\n\n', '-'])
def test_comment_stdin_that_cannot_be_one_argument_is_piped_again_exactly(text, write_cli, mock_http):
    mock_http.responses.append(_data(_task_detail()))
    preview = write_cli(['asana', 'comment', TASK_GID, '-'], input=text)

    assert preview.exit_code == 0, preview.output
    assert _writes(mock_http) == []
    assert 'pipe the same text' in preview.stdout
    assert _next(preview.stdout) == f'co asana comment {TASK_GID} - --yes'

    mock_http.responses += [_data(_task_detail()), _data(_story(text=text), 201)]
    result = _replay(write_cli, _next(preview.stdout), input=text)

    assert result.exit_code == 0, result.output
    # Sent exactly as piped: no trailing newline removed, "-" kept as text.
    assert json.loads(_writes(mock_http)[0].content) == {'data': {'text': text}}


@pytest.mark.parametrize('args, stdin', [(['--', '-x is fixed'], None), (['-'], '--flag-like text')])
def test_comment_text_starting_with_a_dash_replays_after_double_dash(args, stdin, write_cli, mock_http):
    text = stdin if stdin is not None else args[-1]
    mock_http.responses.append(_data(_task_detail()))
    preview = write_cli(['asana', 'comment', TASK_GID, *args], input=stdin)

    assert preview.exit_code == 0, preview.output
    assert _next(preview.stdout) == f'co asana comment {TASK_GID} --yes -- {shlex.quote(text)}'

    mock_http.responses += [_data(_task_detail()), _data(_story(text=text), 201)]
    result = _replay(write_cli, _next(preview.stdout), input='')

    assert result.exit_code == 0, result.output
    assert json.loads(_writes(mock_http)[0].content) == {'data': {'text': text}}


def test_comment_stdin_json_preview_keeps_stdout_parseable(write_cli, mock_http):
    mock_http.responses.append(_data(_task_detail()))

    result = write_cli(['asana', 'comment', TASK_GID, '-', '--json'], input='a\nb\n')

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['changes'] == {'comment': 'a\nb\n'}
    assert 'pipe the same text' in result.stderr
    assert _next(result.stderr) == f'co asana comment {TASK_GID} - --yes --json'


def test_comment_unknown_outcome_points_to_stories(write_cli, mock_http):
    mock_http.responses += [_data(_task_detail()), httpx.ReadTimeout('slow')]

    result = write_cli(['asana', 'comment', TASK_GID, 'hi', '--yes'])

    assert result.exit_code == 1, result.output
    assert len(_writes(mock_http)) == 1
    assert 'may have been' in result.stderr
    assert _next(result.stderr) == f'co asana stories {TASK_GID}'


# exercise the registered commands with a synthetic Asana transport.

def _write_args(command, ref=TASK_GID):
    values = ['--done'] if command == 'update' else ['Reviewed 🌿']
    return ['asana', command, ref, *values]


@pytest.mark.parametrize('command, flags', [
    ('update', ['--due-on', '--done', '--open', '--listing', '--yes', '--json']),
    ('comment', ['--listing', '--yes', '--json']),
])
def test_write_help_without_credentials_never_connects(command, flags, write_cli, mock_http, monkeypatch):
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')

    result = write_cli(['asana', command, '--help'])

    assert result.exit_code == 0, result.output
    assert all(flag in result.stdout for flag in flags)
    assert mock_http.requests == []


@pytest.mark.parametrize('command', ['update', 'comment'])
def test_write_missing_token_is_safe_and_never_sends(command, write_cli, mock_http, monkeypatch):
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')

    result = write_cli([*_write_args(command), '--yes', '--json'])

    _assert_safe_failure(result, SET_TOKEN)
    assert mock_http.requests == []


@pytest.mark.parametrize('flags, changes', [
    (['--due-on', '2028-02-29'], {'due_on': {'before': None, 'after': '2028-02-29'}}),
    (['--open'], {'completed': {'before': True, 'after': False}}),
    (['--due-on', '2026-11-02', '--open'], {'due_on': {'before': None, 'after': '2026-11-02'},
                                         'completed': {'before': True, 'after': False}}),
])
def test_update_json_preview_lists_only_requested_before_and_after_values(flags, changes, write_cli, mock_http):
    mock_http.responses.append(_data(_task_detail(completed=True)))

    result = write_cli(['asana', 'update', TASK_GID, *flags, '--json'])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {'preview': True, 'task_gid': TASK_GID, 'changes': changes}
    assert [request.method for request in mock_http.requests] == ['GET']
    words = shlex.split(_next(result.stderr))
    assert words[:4] == ['co', 'asana', 'update', TASK_GID]
    assert '--yes' in words and '--json' in words


@pytest.mark.parametrize('flags, sent', [
    (['--due-on', '2026-11-02'], {'due_on': '2026-11-02'}),
    (['--done'], {'completed': True}),
    (['--due-on', '2026-11-02', '--open'], {'due_on': '2026-11-02', 'completed': False}),
])
def test_update_yes_json_returns_the_server_task_not_the_preview(flags, sent, write_cli, mock_http):
    returned = _task_detail(name='Server returned name', completed=False, due_on='2026-11-03',
                            extra={'revision': [2, None, '原生']})
    mock_http.responses += [_data(_task_detail()), _data(returned)]

    result = write_cli(['asana', 'update', TASK_GID, *flags, '--yes', '--json'])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == returned
    assert [request.method for request in mock_http.requests] == ['GET', 'PUT']
    assert json.loads(mock_http.requests[-1].content) == {'data': sent}
    assert all(request.url.path == f'/api/1.0/tasks/{TASK_GID}' for request in mock_http.requests)
    assert _next(result.stderr) == f'co asana task {TASK_GID}'
    _assert_no_credentials(result)


def test_update_yes_reloads_the_task_instead_of_reusing_preview_data(write_cli, mock_http):
    mock_http.responses.append(_data(_task_detail(due_on='2026-10-01')))
    preview = write_cli(['asana', 'update', TASK_GID, '--due-on', '2026-11-02'])
    assert preview.exit_code == 0, preview.output

    # A remote change between commands must be checked on the execution call.
    mock_http.responses.append(_data(_task_detail(due_at='2026-11-01T10:00:00Z')))
    result = _replay(write_cli, _next(preview.stdout))

    _assert_usage_failure(result)
    assert _writes(mock_http) == []
    assert [request.method for request in mock_http.requests] == ['GET', 'GET']


@pytest.mark.parametrize('flags', [['--done'], ['--open']])
def test_status_only_update_leaves_existing_due_at_alone(flags, write_cli, mock_http):
    due_at = '2026-11-02T10:00:00Z'
    mock_http.responses += [_data(_task_detail(due_at=due_at)), _data(_task_detail(due_at=due_at))]

    result = write_cli(['asana', 'update', TASK_GID, *flags, '--yes', '--json'])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['due_at'] == due_at
    assert json.loads(_writes(mock_http)[0].content) == {'data': {'completed': flags == ['--done']}}


@pytest.mark.parametrize('value', ['', '2026-02-29', '2026-13-01', '2026-11-00', '2026-11-02T10:00:00Z'])
def test_update_invalid_calendar_date_is_a_usage_error_without_http(value, write_cli, mock_http):
    result = write_cli(['asana', 'update', TASK_GID, '--due-on', value, '--yes', '--json'])

    _assert_usage_failure(result)
    assert mock_http.requests == []


@pytest.mark.parametrize('command', ['update', 'comment'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_write_preview_is_success_without_mutation_or_automatic_json(command, as_json, write_cli, mock_http):
    mock_http.responses.append(_data(_task_detail(name='[red]原始任务 🌿[/red]')))

    result = write_cli([*_write_args(command), *(['--json'] if as_json else [])])

    assert result.exit_code == 0, result.output
    assert [request.method for request in mock_http.requests] == ['GET']
    if as_json:
        payload = json.loads(result.stdout)
        assert payload['preview'] is True and payload['task_gid'] == TASK_GID
        if command == 'comment':
            assert payload['changes'] == {'comment': 'Reviewed 🌿'}
        assert '--yes' in shlex.split(_next(result.stderr))
    else:
        assert '[red]原始任务 🌿[/red]' in result.stdout and TASK_GID in result.stdout
        assert not result.stdout.lstrip().startswith(('{', '['))
        assert '--yes' in shlex.split(_next(result.stdout))
    _assert_no_credentials(result)


@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_comment_preview_displays_the_entire_body_without_posting(as_json, write_cli, mock_http):
    text = 'First line [literal]\n第二行 🌿 "quoted"\nLast line'
    mock_http.responses.append(_data(_task_detail()))

    result = write_cli(['asana', 'comment', TASK_GID, text, *(['--json'] if as_json else [])])

    assert result.exit_code == 0, result.output
    if as_json:
        assert json.loads(result.stdout) == {'preview': True, 'task_gid': TASK_GID, 'changes': {'comment': text}}
    else:
        assert all(line in result.stdout for line in text.splitlines())
    assert _writes(mock_http) == []


def test_comment_yes_json_returns_native_story_author_time_and_extra_fields(write_cli, mock_http):
    returned = _story(text='Server text', created_by={'gid': '1200000000000999', 'name': '服务端作者'},
                      extra={'kept': [None, '🌿']})
    mock_http.responses += [_data(_task_detail()), _data(returned, 201)]

    result = write_cli(['asana', 'comment', TASK_GID, 'Submitted text', '--yes', '--json'])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == returned
    assert [request.method for request in mock_http.requests] == ['GET', 'POST']
    assert json.loads(_writes(mock_http)[0].content) == {'data': {'text': 'Submitted text'}}
    assert _next(result.stderr) == f'co asana stories {TASK_GID}'


@pytest.mark.parametrize('text', ['  do not trim  ', '中文 🌿 "quote" \\path; $(literal)', '\tfirst\nsecond\n\n'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_comment_stdin_execution_preserves_text_in_both_output_modes(text, as_json, write_cli, mock_http):
    mock_http.responses += [_data(_task_detail()), _data(_story(text=text), 201)]

    result = write_cli(['asana', 'comment', TASK_GID, '-', '--yes', *(['--json'] if as_json else [])], input=text)

    assert result.exit_code == 0, result.output
    assert json.loads(_writes(mock_http)[0].content) == {'data': {'text': text}}
    assert len(_writes(mock_http)) == 1
    _assert_no_credentials(result)


@pytest.mark.parametrize('command', ['update', 'comment'])
@pytest.mark.parametrize('yes', [False, True], ids=['preview', 'execute'])
def test_write_bare_row_refuses_even_when_a_recent_tasks_list_exists(command, yes, write_cli, mock_http, listing_dir):
    _seed_listing(listing_dir, family='tasks', gids=[TASK_GID])

    result = write_cli([*_write_args(command, '1'), *(['--yes'] if yes else [])])

    _assert_usage_failure(result)
    assert '--listing' in result.stderr
    assert mock_http.requests == []


@pytest.mark.parametrize('command', ['update', 'comment'])
@pytest.mark.parametrize('ref', ['Ship website', '0', '#0', '2'])
def test_write_name_or_unavailable_row_never_mutates(command, ref, write_cli, mock_http, listing_dir):
    token = _seed_listing(listing_dir, family='tasks', gids=[TASK_GID])
    if ref != 'Ship website':
        mock_http.responses.append(_success())

    result = write_cli([*_write_args(command, ref), '--listing', token, '--yes', '--json'])

    _assert_usage_failure(result)
    assert _writes(mock_http) == []
    assert all(request.url.path == '/api/1.0/users/me' for request in mock_http.requests)


@pytest.mark.parametrize('command', ['update', 'comment'])
@pytest.mark.parametrize('bad_binding', ['account', 'family', 'expired', 'corrupt', 'missing'])
def test_write_listing_binding_failure_prevents_target_reads_and_writes(
        command, bad_binding, write_cli, mock_http, listing_dir):
    token = _seed_listing(listing_dir, family='projects' if bad_binding == 'family' else 'tasks',
                          gids=[TASK_GID], account='1200000000000999' if bad_binding == 'account' else USER_GID,
                          now=100 if bad_binding == 'expired' else None)
    if bad_binding == 'corrupt':
        (listing_dir / f'{token}.json').write_text('{broken', encoding='utf-8')
    if bad_binding == 'missing':
        (listing_dir / f'{token}.json').unlink()
    mock_http.responses.append(_success())

    result = write_cli([*_write_args(command, '1'), '--listing', token, '--yes', '--json'])

    _assert_usage_failure(result)
    assert _writes(mock_http) == []
    assert all(request.url.path == '/api/1.0/users/me' for request in mock_http.requests)


@pytest.mark.parametrize('command', ['update', 'comment'])
@pytest.mark.parametrize('ref', ['1', '#1'])
def test_write_explicit_listing_pins_the_target_after_the_recent_list_changes(
        command, ref, write_cli, mock_http, listing_dir):
    token = _seed_listing(listing_dir, family='tasks', gids=[TASK_GID])
    _seed_listing(listing_dir, family='tasks', gids=['1200000000000999'])
    before = _listing_files(listing_dir)
    returned = _task_detail(completed=True) if command == 'update' else _story(text='Reviewed 🌿')
    mock_http.responses += [_success(), _data(_task_detail()), _data(returned, 200 if command == 'update' else 201)]

    result = write_cli([*_write_args(command, ref), '--listing', token, '--yes', '--json'])

    assert result.exit_code == 0, result.output
    [write] = _writes(mock_http)
    endpoint = f'/api/1.0/tasks/{TASK_GID}' + ('/stories' if command == 'comment' else '')
    assert write.url.path == endpoint
    assert json.loads(result.stdout) == returned
    assert _listing_files(listing_dir) == before


@pytest.mark.parametrize('command', ['update', 'comment'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_write_preread_failure_cannot_become_preview_or_success(command, as_json, write_cli, mock_http):
    mock_http.responses.append(_failure(404, 'Not visible'))

    result = write_cli([*_write_args(command), '--yes', *(['--json'] if as_json else [])])

    _assert_safe_failure(result)
    assert [request.method for request in mock_http.requests] == ['GET']


@pytest.mark.parametrize('command', ['update', 'comment'])
@pytest.mark.parametrize('status', [401, 403, 404, 500, 503])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
def test_write_http_failure_has_no_success_output_or_automatic_resend(command, status, as_json, write_cli, mock_http):
    mock_http.responses += [_data(_task_detail()), _failure(status, 'Synthetic write refusal')]

    result = write_cli([*_write_args(command), '--yes', *(['--json'] if as_json else [])])

    _assert_safe_failure(result)
    assert len(_writes(mock_http)) == 1 and mock_http.sleeps == []
    if status >= 500:
        assert 'Synthetic write refusal' in result.stderr
        words = shlex.split(_next(result.stderr))
        assert words[:3] == ['co', 'asana', 'task' if command == 'update' else 'stories']
        assert words[3] == TASK_GID and '--yes' not in words


@pytest.mark.parametrize('command', ['update', 'comment'])
@pytest.mark.parametrize('error', [httpx.ReadTimeout, httpx.ReadError, httpx.WriteError])
def test_write_transport_failure_never_leaks_headers_or_suggests_duplicate_mutation(command, error, write_cli, mock_http):
    mock_http.responses += [_data(_task_detail()), error(f'Authorization: Bearer {TOKEN}')]

    result = write_cli([*_write_args(command), '--yes', '--json'])

    _assert_safe_failure(result)
    assert len(_writes(mock_http)) == 1 and mock_http.sleeps == []
    assert shlex.split(_next(result.stderr)) == ['co', 'asana', 'task' if command == 'update' else 'stories', TASK_GID]


@pytest.mark.parametrize('command', ['update', 'comment'])
def test_write_invalid_success_is_reported_as_unknown_not_returned_as_json(command, write_cli, mock_http):
    mock_http.responses += [_data(_task_detail()), _data({'gid': None}, 200 if command == 'update' else 201)]

    result = write_cli([*_write_args(command), '--yes', '--json'])

    _assert_safe_failure(result)
    assert len(_writes(mock_http)) == 1
    assert shlex.split(_next(result.stderr)) == ['co', 'asana', 'task' if command == 'update' else 'stories', TASK_GID]


@pytest.mark.parametrize('command', ['update', 'comment'])
def test_write_429_can_recover_without_printing_partial_success(command, write_cli, mock_http):
    returned = _task_detail(completed=True) if command == 'update' else _story(text='Reviewed 🌿')
    mock_http.responses += [_data(_task_detail()), _failure(429, 'Wait', {'Retry-After': '2'}),
                            _data(returned, 200 if command == 'update' else 201)]

    result = write_cli([*_write_args(command), '--yes', '--json'])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == returned
    assert mock_http.sleeps == [2]
    writes = _writes(mock_http)
    assert len(writes) == 2 and writes[0].content == writes[1].content


# public error reporting and the documented CLI contract.
@pytest.fixture
def error_read_cli(monkeypatch, mock_http, write_cli):
    from connectonion.useful_tools import asana
    state = SimpleNamespace(pages=[], page_requests=[])

    def respond(request):
        mock_http.requests.append(request)
        assert len(mock_http.requests) <= 8, 'Unbounded error-reporting requests'
        assert request.method == 'GET'
        if request.url.path == '/api/1.0/users/me':
            return _success()
        if request.url.path == f'/api/1.0/tasks/{TASK_GID}':
            return _data(_task_detail())
        state.page_requests.append(request)
        assert state.pages, 'Unexpected page without a mock response'
        response = state.pages.pop(0)
        if isinstance(response, httpx.TransportError):
            raise response
        return response

    def fake_http():
        client = httpx.Client(timeout=30, transport=httpx.MockTransport(respond))
        mock_http.clients.append(client)
        return client

    monkeypatch.setattr(asana, '_http', fake_http)
    return state


def _error_command(command):
    if command == 'projects':
        return ['asana', 'projects', '--workspace', WORKSPACE_GID]
    return ['asana', command, PROJECT_GID if command == 'tasks' else TASK_GID]


def _error_record(command, index):
    gid = str(1200000000000800 + index)
    if command == 'projects':
        return _project(gid, name='Private project marker')
    if command == 'tasks':
        return _task(gid, name='Private task marker')
    return _story(gid, text='Private comment marker')


def _assert_incomplete_read(result, count):
    _assert_safe_failure(result)
    assert re.search(rf'Read {count} (?:projects?|tasks?|stor(?:y|ies)|items?), incomplete', result.stderr)
    assert 'nothing was listed' in result.stderr
    assert '✓' not in result.stdout + result.stderr
    assert 'Private ' not in result.stdout


@pytest.mark.parametrize('command', ['projects', 'tasks', 'task', 'stories'])
@pytest.mark.parametrize('as_json', [False, True], ids=['human', 'json'])
@pytest.mark.parametrize('pages', [0, 1, 2])
@pytest.mark.parametrize('failure', ['401', '403', '404', '429', '500', 'timeout', 'network', 'json'])
def test_interrupted_read_reports_count_and_no_partial_output(
        command, as_json, pages, failure, error_read_cli, write_cli, listing_dir):
    before = _listing_files(listing_dir)
    for index in range(pages):
        records = [_error_record(command, index * 10 + j) for j in range(index + 1)]
        error_read_cli.pages.append(_page(records, f'page-{index + 1}'))
    error_read_cli.pages += [_read_failure(failure) for _ in range(4 if failure == '429' else 1)]

    result = write_cli([*_error_command(command), *(['--json'] if as_json else [])])

    _assert_incomplete_read(result, pages * (pages + 1) // 2)
    assert _listing_files(listing_dir) == before
    assert len(error_read_cli.page_requests) == pages + (4 if failure == '429' else 1)
    if failure == '401':
        assert 'ASANA_ACCESS_TOKEN' in result.stderr
        assert _next(result.stderr) == SET_TOKEN
    elif failure.isdigit():
        assert f'HTTP {failure}' in result.stderr


@pytest.mark.parametrize('command', ['projects', 'tasks', 'task', 'stories'])
@pytest.mark.parametrize('as_json', [False, True])
def test_empty_page_then_failure_reports_zero_incomplete(command, as_json, error_read_cli, write_cli):
    error_read_cli.pages += [_page([], 'after-empty'), _failure(500)]

    result = write_cli([*_error_command(command), *(['--json'] if as_json else [])])

    _assert_incomplete_read(result, 0)
    assert [request.url.params.get('offset') for request in error_read_cli.page_requests] == [None, 'after-empty']


@pytest.mark.parametrize('command', ['projects', 'tasks', 'task', 'stories'])
@pytest.mark.parametrize('as_json', [False, True])
@pytest.mark.parametrize('empty', [False, True])
def test_complete_read_never_claims_incomplete(command, as_json, empty, error_read_cli, write_cli):
    records = [] if empty else [_error_record(command, 0)]
    error_read_cli.pages.append(_page(records))

    result = write_cli([*_error_command(command), *(['--json'] if as_json else [])])

    assert result.exit_code == 0, result.output
    assert 'incomplete' not in result.stdout + result.stderr
    assert len(error_read_cli.page_requests) == 1
    if as_json:
        json.loads(result.stdout)
        assert _next(result.stderr).startswith('co ')
    else:
        assert _next(result.stdout).startswith('co ')


@pytest.mark.parametrize('command', ['projects', 'tasks', 'task', 'stories'])
@pytest.mark.parametrize('as_json', [False, True])
def test_rate_limit_recovery_keeps_page_and_final_count(command, as_json, error_read_cli, write_cli, mock_http):
    error_read_cli.pages += [_page([_error_record(command, 0)], 'second'),
                             _failure(429, headers={'Retry-After': '2'}),
                             _page([_error_record(command, 1)], 'third'), _failure(503)]

    result = write_cli([*_error_command(command), *(['--json'] if as_json else [])])

    _assert_incomplete_read(result, 2)
    assert mock_http.sleeps == [2]
    assert [request.url.params.get('offset') for request in error_read_cli.page_requests] == [None, 'second', 'second', 'third']
    assert error_read_cli.page_requests[1].url == error_read_cli.page_requests[2].url


@pytest.mark.parametrize('command', ['', 'check', 'projects', 'tasks', 'task', 'stories', 'update', 'comment'])
def test_help_documents_exit_codes_without_credentials_or_effects(command, write_cli, mock_http, monkeypatch, tmp_path):
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}

    result = write_cli(['asana', *([command] if command else []), '--help'])

    assert result.exit_code == 0, result.output
    text = ' '.join(unstyle(result.stdout).split()).lower()
    assert re.search(r'exit 0\b', text)
    assert re.search(r'\b1\b.*failure', text)
    assert re.search(r'\b2\b.*wrong argument', text)
    assert 'example:' in text
    if command in ('projects', 'tasks', 'task', 'stories'):
        assert 'read n' in text and 'incomplete' in text
    assert mock_http.requests == mock_http.sleeps == []
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    assert after == before


@pytest.mark.parametrize('args', [
    ['check', '--json'], ['projects', '-n', '0'], ['tasks'], ['task'], ['stories'],
    ['update', TASK_GID], ['comment', TASK_GID],
])
def test_usage_errors_keep_documented_exit_two_without_requests(args, write_cli, mock_http):
    from connectonion.cli.commands.command_tips import forget_next_step_named
    forget_next_step_named()
    result = write_cli(['asana', *args], prog_name='co')

    assert result.exit_code == 2, result.output
    assert 'Next: co ' in result.stdout + result.stderr
    assert 'Traceback' not in result.stdout + result.stderr
    assert mock_http.requests == mock_http.sleeps == []


@pytest.mark.parametrize('header', ['1.5', 'not-a-delay'])
def test_exhausted_rate_limit_reports_cause_and_recovery(header, write_cli, mock_http):
    mock_http.responses += [_failure(429, 'Synthetic rate limit', {'Retry-After': header}) for _ in range(4)]

    result = write_cli(['asana', 'check'])

    _assert_safe_failure(result)
    assert '429' in result.stderr
    assert re.search(r'retry|wait|rate limit', result.stderr, re.I)
    assert _next(result.stderr).startswith('co ')
    assert len(mock_http.requests) == 4
    assert len(mock_http.sleeps) == 3
    assert sum(mock_http.sleeps) <= 60


# -- REM source registration ------------------------------------


@pytest.fixture
def asana_sources_cli(asana_registration):
    from connectonion.cli.main import app
    root = asana_registration
    runner = CliRunner()

    def invoke(*args, as_json=True):
        prefix = ['rem', '--root', str(root), *(['--json'] if as_json else [])]
        return runner.invoke(app, [*prefix, 'sources', *args])

    return root, invoke


def _asana_source_payload(result):
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload['ok'] is True
    assert payload['next'].startswith('co rem ')
    return payload['data']


def test_rem_asana_default_listing_is_off_and_read_only(asana_sources_cli):
    root, invoke = asana_sources_cli
    source = _asana_source_payload(invoke())['asana']
    assert source['enabled'] is False
    assert source['project_gids'] == []
    assert source['consented'] is False
    assert not root.exists()


@pytest.mark.parametrize('as_json', [False, True])
def test_rem_asana_add_then_list_preserves_project_and_root(asana_sources_cli, as_json):
    root, invoke = asana_sources_cli
    gid = '000120012345678901234567890'
    result = invoke('add', 'asana', '--project', gid, as_json=as_json)
    assert result.exit_code == 0, result.output
    assert gid in result.stdout
    assert 'Traceback' not in result.output
    source = _asana_source_payload(invoke())['asana']
    assert source['project_gids'] == [gid]
    assert source['enabled'] is True
    assert source['consented'] is False
    if as_json:
        assert str(root) in json.loads(result.stdout)['next']
    else:
        assert 'Next: co rem ' in result.stdout
        assert str(root) in result.stdout


def test_rem_asana_missing_token_is_visible_without_losing_scope(asana_sources_cli):
    _, invoke = asana_sources_cli
    assert invoke('add', 'asana', '--project', '200').exit_code == 0
    source = _asana_source_payload(invoke())['asana']
    assert 'waiting for token' in json.dumps(source).lower()
    assert source['project_gids'] == ['200']


def test_rem_asana_multiple_adds_and_project_removal(asana_sources_cli):
    _, invoke = asana_sources_cli
    for gid in ('200', '201', '200'):
        assert invoke('add', 'asana', '--project', gid).exit_code == 0
    source = _asana_source_payload(invoke())['asana']
    assert set(source['project_gids']) == {'200', '201'}
    assert len(source['project_gids']) == 2
    assert invoke('remove', 'asana', '--project', '200').exit_code == 0
    source = _asana_source_payload(invoke())['asana']
    assert source['project_gids'] == ['201']
    assert source['enabled'] is True
    assert invoke('remove', 'asana').exit_code == 0
    assert _asana_source_payload(invoke())['asana']['enabled'] is False


@pytest.mark.parametrize('value', ['abc', '../200', '/work/demo', '-1', '12 3', '1.5'])
@pytest.mark.parametrize('as_json', [False, True])
def test_rem_asana_bad_gid_fails_without_changing_selection(asana_sources_cli, value, as_json):
    from connectonion.rem.files import state_path
    root, invoke = asana_sources_cli
    assert invoke('add', 'asana', '--project', '200').exit_code == 0
    path = state_path(root, 'subscriptions.json')
    before = path.read_bytes()
    result = invoke('add', 'asana', f'--project={value}', as_json=as_json)
    assert result.exit_code != 0, result.output
    assert 'Traceback' not in result.output
    assert path.read_bytes() == before
    if as_json:
        payload = json.loads(result.stdout)
        assert payload['ok'] is False
        assert payload['next'].startswith('co rem ')
    else:
        assert 'Next: co rem ' in result.stderr


def test_rem_asana_missing_project_never_enables_all_projects(asana_sources_cli):
    _, invoke = asana_sources_cli
    result = invoke('add', 'asana')
    assert result.exit_code != 0, result.output
    source = _asana_source_payload(invoke())['asana']
    assert source['enabled'] is False
    assert source['project_gids'] == []


@pytest.mark.parametrize('flags', [['--chat', '123'], ['--about', 'browser']])
def test_rem_asana_rejects_unrelated_source_flags(asana_sources_cli, flags):
    _, invoke = asana_sources_cli
    result = invoke('add', 'asana', '--project', '200', *flags)
    assert result.exit_code != 0, result.output
    assert _asana_source_payload(invoke())['asana']['enabled'] is False


@pytest.mark.parametrize('as_json', [False, True])
def test_rem_asana_never_prints_or_saves_token(asana_sources_cli, monkeypatch, as_json):
    from connectonion.rem.files import state_path
    root, invoke = asana_sources_cli
    token = 'synthetic-asana-secret-for-story23'
    monkeypatch.setenv('ASANA_ACCESS_TOKEN', token)
    for result in (invoke('add', 'asana', '--project', '200', as_json=as_json),
                   invoke(as_json=as_json), invoke('remove', 'asana', as_json=as_json)):
        assert result.exit_code == 0, result.output
        assert token not in result.output
        assert f'Bearer {token}' not in result.output
    assert token not in state_path(root, 'subscriptions.json').read_text()


@pytest.mark.parametrize('words', [[], ['add'], ['remove']])
def test_rem_asana_sources_help_reads_no_credentials_or_files(asana_sources_cli, monkeypatch, words):
    from connectonion.useful_tools import asana
    root, invoke = asana_sources_cli
    attempts = []

    def refuse_credentials(*args, **kwargs):
        attempts.append(True)
        pytest.fail('Help must not read Asana credentials')

    monkeypatch.setattr(asana, '_token', refuse_credentials)
    before = {str(path): path.read_bytes() for path in root.parent.rglob('*') if path.is_file()}
    result = invoke(*words, '--help', as_json=False)
    assert result.exit_code == 0, result.output
    assert 'Usage:' in result.stdout and 'Example:' in result.stdout
    assert '--project' in result.stdout
    assert attempts == []
    assert not root.exists()
    assert {str(path): path.read_bytes() for path in root.parent.rglob('*') if path.is_file()} == before
    assert 'read-only' in result.stdout.lower() or 'Changes' in result.stdout or 'Writes' in result.stdout


def test_rem_asana_listing_after_registration_writes_nothing(asana_sources_cli):
    root, invoke = asana_sources_cli
    assert invoke('add', 'asana', '--project', '200').exit_code == 0
    before = {str(path): path.read_bytes() for path in root.rglob('*') if path.is_file()}
    assert invoke().exit_code == 0
    assert {str(path): path.read_bytes() for path in root.rglob('*') if path.is_file()} == before


def test_rem_asana_choice_survives_a_fresh_cli_process(asana_sources_cli, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    root, invoke = asana_sources_cli
    assert invoke('add', 'asana', '--project', '200').exit_code == 0
    script = '''
import socket
import sys
from typer.testing import CliRunner
from connectonion.cli.main import app
from connectonion.rem import service
from connectonion import secret_store
service.mail_available = lambda kind: False
secret_store.stored_names = lambda directory: []
def refuse(*args, **kwargs):
    raise AssertionError('No network in source inspection')
socket.socket.connect = refuse
socket.socket.connect_ex = refuse
socket.create_connection = refuse
result = CliRunner().invoke(app, ['rem', '--root', sys.argv[1], '--json', 'sources'])
print(result.stdout, end='')
sys.exit(result.exit_code)
'''
    child_env = dict(os.environ, ASANA_ACCESS_TOKEN='', AGENT_CONFIG_PATH=str(tmp_path / 'config'),
                     HOME=str(tmp_path), CO_INBOX_HOME=str(tmp_path / 'inbox'))
    checkout = Path(__file__).resolve().parents[2]
    child_env['PYTHONPATH'] = str(checkout)
    child = subprocess.run([sys.executable, '-c', script, str(root)], cwd=tmp_path,
                           env=child_env, capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout)['data']['asana']['project_gids'] == ['200']


@pytest.mark.parametrize('as_json', [False, True])
def test_rem_asana_corrupt_settings_report_safe_error(asana_sources_cli, as_json):
    from connectonion.rem.files import state_path
    root, invoke = asana_sources_cli
    assert invoke('add', 'asana', '--project', '200').exit_code == 0
    path = state_path(root, 'subscriptions.json')
    path.write_text('{broken')
    result = invoke(as_json=as_json)
    assert result.exit_code == 1, result.output
    assert 'Traceback' not in result.output
    assert path.read_text() == '{broken'
    if as_json:
        assert json.loads(result.stdout)['ok'] is False
    else:
        assert 'Next: co rem ' in result.stderr


@pytest.mark.parametrize('value', [' 200 ', '\t200\n', '\r\n200\t'])
def test_rem_asana_project_trims_surrounding_whitespace(asana_sources_cli, value):
    _, invoke = asana_sources_cli
    assert invoke('add', 'asana', f'--project={value}').exit_code == 0
    assert _asana_source_payload(invoke())['asana']['project_gids'] == ['200']


@pytest.mark.parametrize('value', ['', ' ', '\t\n'])
def test_rem_asana_first_blank_project_cannot_enable_source(asana_sources_cli, value):
    _, invoke = asana_sources_cli
    result = invoke('add', 'asana', f'--project={value}')
    assert result.exit_code != 0, result.output
    source = _asana_source_payload(invoke())['asana']
    assert source['enabled'] is False
    assert source['project_gids'] == []


# -- Asana sync inspection -------------------------------------


@pytest.mark.parametrize('as_json', [False, True])
def test_rem_asana_dry_run_shows_unknown_before_collection(asana_sync, as_json):
    from connectonion.cli.main import app
    root, client, calls, runner = asana_sync
    args = ['rem', '--root', str(root), *(['--json'] if as_json else []),
            'sync', '--source', 'asana', '--dry-run']
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    if as_json:
        assert json.loads(result.stdout)['data']['sources']['asana']['pending_tasks'] is None
        assert json.loads(result.stdout)['next'].startswith('co ')
    else:
        assert 'not collected' in result.stdout.lower() or 'unknown' in result.stdout.lower()
        assert re.search(r'Next:\s+co ', unstyle(result.stdout + result.stderr))
    assert client.calls == calls == []


@pytest.mark.parametrize('as_json', [False, True])
def test_rem_asana_dry_run_reports_latest_pending_count(asana_sync, as_json):
    from pathlib import Path
    from connectonion.cli.main import app
    from connectonion.rem.service import subscriptions
    from connectonion.useful_tools import asana_export
    root, client, calls, runner = asana_sync
    source = Path(subscriptions(root)['asana']['root'])
    for title in ('Old saved task', 'Latest saved task'):
        client.tasks['300']['name'] = title
        asana_export.sync_tasks(client, source, ['200'])
    client.calls.clear()
    before = {p: p.read_bytes() for p in root.parent.rglob('*') if p.is_file()}
    result = CliRunner().invoke(app, ['rem', '--root', str(root), *(['--json'] if as_json else []),
                                    'sync', '--source', 'asana', '--dry-run'])
    assert result.exit_code == 0, result.output
    if as_json:
        assert json.loads(result.stdout)['data']['sources']['asana']['pending_tasks'] == 1
    else:
        assert 'asana' in result.stdout.lower() and '1' in result.stdout
    assert 'Latest saved task' not in result.stdout + result.stderr
    assert client.calls == calls == []
    assert {p: p.read_bytes() for p in root.parent.rglob('*') if p.is_file()} == before


def test_rem_sync_help_is_safe_and_describes_asana_collection(asana_sync, monkeypatch):
    from connectonion.cli.main import app
    root, client, calls, runner = asana_sync
    monkeypatch.delenv('ASANA_ACCESS_TOKEN', raising=False)
    before = {p: p.read_bytes() for p in root.parent.rglob('*') if p.is_file()}
    result = CliRunner().invoke(app, ['rem', '--root', str(root), 'sync', '--help'])
    assert result.exit_code == 0, result.output
    text = unstyle(result.stdout).lower()
    assert 'example:' in text and '--dry-run' in text and '--source' in text
    assert 'asana' in text and 'newest' in text
    assert re.search(r'next:\s+co ', unstyle(result.stdout + result.stderr).lower())
    assert client.calls == calls == []
    assert {p: p.read_bytes() for p in root.parent.rglob('*') if p.is_file()} == before


# -- colour in `co asana tasks` (11-12): due day and assignee ------------------

def _coloured_rows(monkeypatch, tasks, me_gid='1200000000000001', today=date(2026, 11, 12)):
    from connectonion.cli.commands import asana_commands
    from connectonion.useful_tools import asana
    monkeypatch.setattr(asana, '_local_zone', lambda: timezone(timedelta(hours=11)))
    monkeypatch.setattr(asana_commands, '_today', lambda: today)
    return asana_commands._task_lines(tasks, tasks, 'Website', 'all', False, me_gid)[1:]


def _row(name, **fields):
    task = {'gid': '1200000000000300', 'name': name, 'completed': False,
            'assignee': {'gid': '1200000000000002', 'name': 'Bob'}, 'due_on': None, 'due_at': None}
    task.update(fields)
    return task


def test_due_day_is_red_past_due_yellow_today_dim_when_undated_or_done(monkeypatch):
    rows = _coloured_rows(monkeypatch, [
        _row('late', due_on='2026-11-11'),
        _row('today', due_on='2026-11-12'),
        _row('soon', due_on='2026-11-13'),
        _row('none'),
        _row('finished late', due_on='2026-11-01', completed=True),
        _row('at a time today', due_at='2026-11-11T22:30:00Z'),     # 09:30 on 12 Nov at +11
    ])
    late, today, soon, none, finished, timed = rows
    assert '[co.error]due 2026-11-11[/co.error]' in late
    assert '[co.warn]due 2026-11-12[/co.warn]' in today
    assert 'due 2026-11-13' in soon and '[co.' not in soon       # a later day, someone else's: no colour
    assert '[co.muted]due -' in none
    assert '[co.muted]due 2026-11-01' in finished                  # done is never overdue
    assert '[co.warn]due 2026-11-12' in timed                       # the same local day --due-to uses


def test_own_tasks_are_bold_and_unassigned_ones_dim(monkeypatch):
    mine, theirs, nobody = _coloured_rows(monkeypatch, [
        _row('mine', assignee={'gid': '1200000000000001', 'name': 'Eric z'}),
        _row('theirs'),
        _row('nobody', assignee=None),
    ])
    assert '[co.label]Eric z' in mine
    assert '[co.label]' not in theirs and '[co.muted]Bob' not in theirs and 'Bob' in theirs
    assert '[co.muted]-' in nobody


def test_colour_keeps_columns_aligned_and_names_plain(monkeypatch):
    from rich.console import Console
    from rich.text import Text
    from connectonion.cli import style
    rows = _coloured_rows(monkeypatch, [
        _row('[urgent] 发布 🌿', due_on='2026-11-11', assignee={'gid': '1200000000000001', 'name': '[bot] 祁晟'}),
        _row('Plain', assignee=None),
    ])
    console = Console(theme=style.THEME, width=200, force_terminal=False)
    plain = [Text.from_markup(r).plain for r in rows]
    assert plain[0].endswith('[urgent] 发布 🌿') and '[bot] 祁晟' in plain[0]   # brackets shown once, not escaped twice
    from rich.cells import cell_len
    assert cell_len(plain[0][:-len('[urgent] 发布 🌿')]) == cell_len(plain[1][:-len('Plain')])
    for r in rows:
        console.print(r)                                            # every co.* name resolves in the theme
