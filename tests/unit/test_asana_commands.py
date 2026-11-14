"""Asana CLI arguments, rendering, listings, exit codes and safe errors."""

from datetime import date, datetime, timedelta, timezone
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import hashlib
import json
import shlex
import time

import httpx
import pytest
from typer.testing import CliRunner

from tests.unit.test_asana import (
    TOKEN, SET_TOKEN, USER_GID, WORKSPACE_GID, PROJECT_GID, TASK_GID, INVALID_STORY_TIMES,
    _failure, _success, _user, _project, _task, _page, _task_detail, _story, _story_with_time,
    isolated_asana_env, mock_http,
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



def test_asana_group_without_token_shows_help(cli, mock_http, monkeypatch):
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')
    result = cli(['asana'])

    assert result.exit_code in (0, 2), result.output
    assert 'Usage:' in result.output
    assert 'check' in result.output
    assert mock_http.requests == []



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


# F13DBREAD-9: workspace selection, native output and saved rows.
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
    assert rows[0].startswith('1. 新项目 🌿')
    assert rows[1].startswith('2. Older')
    assert 'Platform' in rows[0] and '2026-10-07' in rows[0]
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
        assert rows[0].startswith(f"1. {expected[0]['name']}")
        assert rows[-1].startswith(f"{limit}. {expected[-1]['name']}")
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
    assert rows[0].startswith('1. 发布 🌿')
    assert 'Alice' in rows[0] and 'due 2026-10-07' in rows[0] and 'open' in rows[0]
    assert rows[1].startswith('2. Older')
    assert '  -  due -  done' in rows[1]
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
    assert 'stopped after 1' in result.stderr
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


# F13DBREAD-10: source details, activity, references and safe output.
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
        assert 'stopped after 1' in result.stderr
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
        assert 'stopped after 1' in result.stderr


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
