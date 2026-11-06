"""Direct Asana tool tests for account checks, project lists and task filters."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import json
import socket

import httpx
import pytest

from connectonion.useful_tools import asana


pytestmark = pytest.mark.unit

TOKEN = 'test-token-check'
SET_TOKEN = 'co env set ASANA_ACCESS_TOKEN <pat> --secret'
USER_GID = '120012345678901234567890'
WORKSPACE_GID = '000120012345678901234567891'
FIELDS = {'gid', 'name', 'email', 'workspaces.gid', 'workspaces.name'}


def _user(workspaces=None, **fields):
    user = {
        'gid': USER_GID,
        'name': 'Alice',
        'email': 'alice@example.test',
        'workspaces': [{'gid': WORKSPACE_GID, 'name': 'Engineering'}]
        if workspaces is None else workspaces,
    }
    user.update(fields)
    return user


def _success(user=None):
    return httpx.Response(200, json={'data': _user() if user is None else user})


def _failure(status, message='Request failed', headers=None):
    return httpx.Response(status, json={'errors': [{'message': message}]},
                          headers=headers)


@pytest.fixture(autouse=True)
def isolated_asana_env(monkeypatch, tmp_path):
    """Keep configuration, secrets and all network access inside this test."""
    monkeypatch.setenv('AGENT_CONFIG_PATH', str(tmp_path / 'config'))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    monkeypatch.setenv('ASANA_ACCESS_TOKEN', TOKEN)
    monkeypatch.setenv('CO_DEBUG_ENV', '0')
    for name in ('FORCE_COLOR', 'CLICOLOR_FORCE', 'CLICOLOR', 'COLORTERM'):
        monkeypatch.delenv(name, raising=False)
    attempts = []

    def refuse_network(*args, **kwargs):
        attempts.append('blocked')
        raise AssertionError('Asana check tests must not open network connections')

    monkeypatch.setattr(socket.socket, 'connect', refuse_network)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse_network)
    monkeypatch.setattr(socket, 'create_connection', refuse_network)
    from connectonion import environment, secret_store
    monkeypatch.setattr(environment, '_selected', None)
    monkeypatch.setattr(environment, '_selection_error', None)
    monkeypatch.setattr(environment, '_loaded', {})
    monkeypatch.setattr(environment, '_announced', set())
    monkeypatch.setattr(secret_store, 'stored_names', lambda directory: [])
    monkeypatch.setattr(secret_store, 'get',
                        lambda *args: pytest.fail('Unexpected secret-store read'))
    monkeypatch.chdir(tmp_path)
    yield
    assert not attempts, 'An attempted network connection was blocked'


@pytest.fixture
def mock_http(monkeypatch, isolated_asana_env):
    """Use an isolated client through the Asana-specific HTTP seam."""
    from connectonion.useful_tools import asana
    mocked = SimpleNamespace(requests=[], responses=[], sleeps=[], clients=[])

    def respond(request):
        mocked.requests.append(request)
        assert len(mocked.requests) <= 8, 'Unbounded check requests'
        assert mocked.responses, 'Unexpected request without a mock response'
        response = mocked.responses.pop(0)
        if isinstance(response, httpx.TransportError):
            raise response
        return response

    def fake_http():
        client = httpx.Client(timeout=30, transport=httpx.MockTransport(respond))
        mocked.clients.append(client)
        return client

    def record_wait(seconds):
        mocked.sleeps.append(seconds)
        assert len(mocked.sleeps) <= 8, 'Unbounded check waits'

    monkeypatch.setattr(asana, '_http', fake_http)
    monkeypatch.setattr(asana, 'sleep', record_wait)
    yield mocked
    for client in mocked.clients:
        client.close()



def _assert_tool_error(error, next_step=None):
    assert isinstance(error, asana.AsanaError)
    assert str(error)
    assert error.next_step.startswith('co ')
    if next_step is not None:
        assert error.next_step == next_step
    text = '\n'.join((str(error), repr(error), repr(error.args), repr(vars(error))))
    assert TOKEN not in text
    assert 'authorization:' not in text.lower()
    assert 'Traceback (most recent call last)' not in text



def test_get_user_sends_get_to_current_user_path(mock_http):
    mock_http.responses.append(_success())
    asana.Asana().get_user()
    request = mock_http.requests[0]
    assert request.method == 'GET'
    assert request.url.path == '/api/1.0/users/me'


def test_get_user_uses_bearer_authentication(mock_http):
    mock_http.responses.append(_success())
    asana.Asana().get_user()
    assert mock_http.requests[0].headers['Authorization'] == f'Bearer {TOKEN}'


def test_get_user_requests_required_fields(mock_http):
    mock_http.responses.append(_success())
    asana.Asana().get_user()
    fields = set(mock_http.requests[0].url.params['opt_fields'].split(','))
    assert FIELDS <= fields


def test_get_user_success_uses_one_request(mock_http):
    mock_http.responses.append(_success())
    asana.Asana().get_user()
    assert len(mock_http.requests) == 1
    assert mock_http.requests[0].url.path == '/api/1.0/users/me'
    assert mock_http.requests[0].method == 'GET'


def test_rejected_token_raises_without_retry(mock_http):
    mock_http.responses.append(_failure(401))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value, SET_TOKEN)
    assert len(mock_http.requests) == 1
    assert mock_http.sleeps == []


def test_forbidden_response_raises_asana_error(mock_http):
    mock_http.responses.extend((_failure(403) for _ in range(8)))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)
    assert 1 <= len(mock_http.requests) <= 8


def test_not_found_response_raises_asana_error(mock_http):
    mock_http.responses.append(_failure(404))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


@pytest.mark.parametrize('status', [500, 502, 503])
def test_server_error_is_not_retried(status, mock_http):
    mock_http.responses.append(_failure(status))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)
    assert len(mock_http.requests) == 1
    assert mock_http.sleeps == []


@pytest.mark.parametrize('error', [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout])
def test_timeout_raises_asana_error(error, mock_http):
    mock_http.responses.append(error('Synthetic timeout'))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


@pytest.mark.parametrize('error', [httpx.ConnectError, httpx.ReadError])
def test_connection_failure_raises_asana_error(error, mock_http):
    mock_http.responses.append(error('Synthetic connection failure'))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


def test_html_response_is_rejected(mock_http):
    mock_http.responses.append(httpx.Response(200, text='<html>Not JSON</html>'))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


def test_malformed_json_is_rejected(mock_http):
    mock_http.responses.append(httpx.Response(200, text='{"data": '))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


@pytest.mark.parametrize('body', [None, [], 'value', 1])
def test_non_object_response_is_rejected(body, mock_http):
    mock_http.responses.append(httpx.Response(200, content=json.dumps(body)))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


def test_missing_user_data_is_rejected(mock_http):
    mock_http.responses.append(httpx.Response(200, json={'meta': 'missing data'}))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


@pytest.mark.parametrize('data', [None, [], 'value', 1])
def test_non_record_user_data_is_rejected(data, mock_http):
    mock_http.responses.append(httpx.Response(200, json={'data': data}))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


@pytest.mark.parametrize('fields', [{}, {'gid': ''}, {'gid': None}, {'gid': 123}])
def test_invalid_user_gid_is_rejected(fields, mock_http):
    user = _user()
    user.pop('gid')
    user.update(fields)
    mock_http.responses.append(_success(user))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


@pytest.mark.parametrize('workspaces', [None, {}, 'value'])
def test_invalid_workspace_collection_is_rejected(workspaces, mock_http):
    user = _user()
    user['workspaces'] = workspaces
    mock_http.responses.append(_success(user))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


@pytest.mark.parametrize('workspace', [None, 'value', {}])
def test_invalid_workspace_record_is_rejected(workspace, mock_http):
    mock_http.responses.append(_success(_user([workspace])))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


@pytest.mark.parametrize('fields', [{}, {'gid': ''}, {'gid': None}, {'gid': 123}])
def test_invalid_workspace_gid_is_rejected(fields, mock_http):
    mock_http.responses.append(_success(_user([{'name': 'Engineering', **fields}])))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


def test_bad_workspace_prevents_partial_success(mock_http):
    workspaces = [{'gid': WORKSPACE_GID, 'name': 'Engineering'}, {'name': 'Invalid'}]
    mock_http.responses.append(_success(_user(workspaces)))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)


def test_rate_limit_then_success_honors_retry_after(mock_http):
    mock_http.responses.extend([_failure(429, headers={'Retry-After': '2'}), _success()])
    asana.Asana().get_user()
    assert len(mock_http.requests) == 2
    assert mock_http.sleeps == [2]


def test_missing_retry_after_defaults_to_one_second(mock_http):
    mock_http.responses.extend([_failure(429), _success()])
    asana.Asana().get_user()
    assert len(mock_http.requests) == 2
    assert mock_http.sleeps == [1]


def test_success_on_third_retry(mock_http):
    mock_http.responses.extend((_failure(429, headers={'Retry-After': '1'}) for _ in range(3)))
    mock_http.responses.append(_success())
    asana.Asana().get_user()
    assert len(mock_http.requests) == 4
    assert mock_http.sleeps == [1, 1, 1]


def test_repeated_rate_limit_is_bounded(mock_http):
    mock_http.responses.extend((_failure(429, headers={'Retry-After': '1'}) for _ in range(8)))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)
    assert 1 < len(mock_http.requests) <= 4
    assert len(mock_http.sleeps) <= 3
    assert sum(mock_http.sleeps) <= 60


def test_sixty_second_total_wait_is_allowed(mock_http):
    mock_http.responses.extend((_failure(429, headers={'Retry-After': '20'}) for _ in range(3)))
    mock_http.responses.append(_success())
    asana.Asana().get_user()
    assert mock_http.sleeps == [20, 20, 20]
    assert len(mock_http.requests) == 4


def test_retry_after_above_budget_is_not_waited(mock_http):
    mock_http.responses.append(_failure(429, headers={'Retry-After': '61'}))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)
    assert mock_http.sleeps == []
    assert len(mock_http.requests) == 1


def test_cumulative_wait_never_exceeds_budget(mock_http):
    mock_http.responses.extend([_failure(429, headers={'Retry-After': '30'}), _failure(429, headers={'Retry-After': '31'})])
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)
    assert mock_http.sleeps == [30]
    assert len(mock_http.requests) == 2


def test_zero_retry_after_cannot_loop_forever(mock_http):
    mock_http.responses.extend((_failure(429, headers={'Retry-After': '0'}) for _ in range(8)))
    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()
    _assert_tool_error(exc.value)
    assert 1 < len(mock_http.requests) <= 4
    assert sum(mock_http.sleeps) == 0



@pytest.mark.parametrize('explicit', [True, False], ids=['explicit', 'configured'])
def test_asana_construction_never_requests(explicit, mock_http, capsys):
    client = asana.Asana(token=TOKEN) if explicit else asana.Asana()

    assert isinstance(client, asana.Asana)
    assert mock_http.requests == []
    assert mock_http.sleeps == []
    assert TOKEN not in repr(client)
    assert capsys.readouterr() == ('', '')



@pytest.mark.parametrize('source', ['explicit', 'configured'])
@pytest.mark.parametrize('token', [None, '', ' ', '\t\n'])
def test_missing_or_blank_token_raises_safely(source, token, monkeypatch, capsys):
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')
    if source == 'configured' and token is not None:
        monkeypatch.setenv('ASANA_ACCESS_TOKEN', token)

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana(token=token) if source == 'explicit' else asana.Asana()

    _assert_tool_error(exc.value, SET_TOKEN)
    assert capsys.readouterr() == ('', '')



def test_explicit_token_overrides_configured_token(mock_http, monkeypatch):
    monkeypatch.setenv('ASANA_ACCESS_TOKEN', 'test-configured-asana-token')
    mock_http.responses.append(_success())

    assert asana.Asana(token=TOKEN).get_user() == _user()
    assert mock_http.requests[0].headers['Authorization'] == f'Bearer {TOKEN}'



def test_token_from_environment_file(mock_http, monkeypatch, tmp_path):
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')
    directory = tmp_path / 'config'
    directory.mkdir()
    (directory / 'keys.env').write_text(f'ASANA_ACCESS_TOKEN={TOKEN}\n')
    mock_http.responses.append(_success())
    client = asana.Asana()

    assert mock_http.requests == []
    assert client.get_user() == _user()
    assert TOKEN not in repr(client)



def test_token_from_secret_store(mock_http, monkeypatch):
    from connectonion import secret_store
    monkeypatch.delenv('ASANA_ACCESS_TOKEN')
    monkeypatch.setattr(secret_store, 'stored_names', lambda directory: ['asana_access_token'])
    monkeypatch.setattr(secret_store, 'get', Mock(return_value=TOKEN))
    mock_http.responses.append(_success())
    client = asana.Asana()

    assert mock_http.requests == []
    assert client.get_user() == _user()
    assert TOKEN not in repr(client)



def test_http_returns_client_without_request():
    with asana._http() as client:
        assert isinstance(client, httpx.Client)



def test_http_client_has_thirty_second_timeout():
    with asana._http() as client:
        assert client.timeout.connect == 30
        assert client.timeout.read == 30
        assert client.timeout.write == 30
        assert client.timeout.pool == 30



def test_get_user_returns_source_data(mock_http):
    user = _user()
    mock_http.responses.append(httpx.Response(200, json={'data': user, 'meta': {'ignored': True}}))
    result = asana.Asana().get_user()

    assert result == user
    assert set(result) == set(user)
    assert isinstance(result['gid'], str)
    assert isinstance(result['workspaces'][0]['gid'], str)



def test_get_user_preserves_extra_and_nested_fields(mock_http):
    user = _user()
    user['extra'] = {'nested': [None, {'value': 'retained'}]}
    user['workspaces'][0]['extra'] = {'nested': {'value': [1, 2]}}
    before = deepcopy(user)
    mock_http.responses.append(_success(user))
    result = asana.Asana().get_user()

    assert result == before
    assert result['extra'] == before['extra']
    assert result['workspaces'] == before['workspaces']
    assert user == before



def test_get_user_preserves_empty_workspaces(mock_http):
    user = _user([])
    mock_http.responses.append(_success(user))

    assert asana.Asana().get_user() == user
    assert mock_http.requests[0].url.path == '/api/1.0/users/me'



@pytest.mark.parametrize('fields', [
    {'name': None}, {'email': None}, {'optional': None}, {'workspaces': [
        {'gid': WORKSPACE_GID, 'name': None, 'optional': None},
    ]},
])
def test_get_user_preserves_valid_null_fields(fields, mock_http):
    user = _user(**fields)
    mock_http.responses.append(_success(user))

    assert asana.Asana().get_user() == user



def test_get_user_preserves_missing_optional_fields(mock_http):
    user = {'gid': USER_GID}
    mock_http.responses.append(_success(user))
    result = asana.Asana().get_user()

    assert result == user
    assert 'email' not in result
    assert 'workspaces' not in result



@pytest.mark.parametrize('error', [httpx.ReadTimeout, httpx.ConnectError, httpx.ReadError])
def test_transport_error_does_not_expose_credentials(error, mock_http):
    mock_http.responses.append(error(f'Authorization: Bearer {TOKEN}'))

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_user()

    _assert_tool_error(exc.value)


# F13DBREAD-9: native lists, pagination and filters.
PROJECT_GID = '000120012345678901234567892'
TASK_GID = '000120012345678901234567893'
PROJECT_FIELDS = {'gid', 'name', 'archived', 'modified_at', 'permalink_url',
                  'workspace.gid', 'workspace.name', 'team.gid', 'team.name'}
TASK_FIELDS = {'gid', 'name', 'completed', 'due_on', 'due_at', 'modified_at',
               'permalink_url', 'assignee.gid', 'assignee.name', 'projects.gid', 'projects.name'}


def _project(gid=PROJECT_GID, **fields):
    project = {'gid': gid, 'name': 'Website', 'archived': False,
               'modified_at': '2026-10-07T01:00:00Z',
               'permalink_url': f'https://app.asana.com/0/{gid}',
               'workspace': {'gid': WORKSPACE_GID, 'name': 'Engineering'},
               'team': {'gid': '1200000000000999', 'name': 'Platform'}}
    project.update(fields)
    return project


def _task(gid=TASK_GID, **fields):
    task = {'gid': gid, 'name': 'Ship website', 'completed': False,
            'assignee': {'gid': USER_GID, 'name': 'Alice'},
            'due_on': None, 'due_at': None, 'modified_at': '2026-10-07T01:00:00Z',
            'permalink_url': f'https://app.asana.com/0/{gid}',
            'projects': [{'gid': PROJECT_GID, 'name': 'Website'}]}
    task.update(fields)
    return task


def _page(records, offset=None):
    return httpx.Response(200, json={'data': records,
                                   'next_page': None if offset is None else {'offset': offset}})


def _list_resource(resource, **filters):
    client = asana.Asana()
    if resource == 'projects':
        return client.list_projects(WORKSPACE_GID)
    return client.list_tasks(PROJECT_GID, **filters)


@pytest.mark.parametrize('resource,record,fields,scope', [
    ('projects', _project(archived=True), PROJECT_FIELDS, ('workspace', WORKSPACE_GID)),
    ('tasks', _task(), TASK_FIELDS, ('project', PROJECT_GID)),
])
def test_list_request_preserves_native_records(resource, record, fields, scope, mock_http):
    record['extra'] = {'nested': [None, {'name': '开发 🌿'}]}
    before = deepcopy(record)
    mock_http.responses.append(_page([record]))

    assert _list_resource(resource) == [before]
    assert record == before
    assert len(mock_http.requests) == 1
    request = mock_http.requests[0]
    assert request.method == 'GET'
    assert request.url.path == f'/api/1.0/{resource}'
    assert request.url.params[scope[0]] == scope[1]
    assert fields <= set(request.url.params['opt_fields'].split(','))
    assert isinstance(record['gid'], str)


@pytest.mark.parametrize('resource,make_record', [('projects', _project), ('tasks', _task)])
@pytest.mark.parametrize('pages', [1, 2, 3])
def test_lists_read_every_offset_page_in_source_order(resource, make_record, pages, mock_http):
    records = [make_record(str(1200000000000200 + i)) for i in range(pages)]
    offsets = ['cursor +/=一', 'second cursor']
    for i, record in enumerate(records):
        mock_http.responses.append(_page([record], offsets[i] if i < pages - 1 else None))

    assert _list_resource(resource) == records
    assert len(mock_http.requests) == pages
    assert 'offset' not in mock_http.requests[0].url.params
    for i, request in enumerate(mock_http.requests[1:]):
        assert request.url.params['offset'] == offsets[i]
        assert request.url.params.get('workspace', request.url.params.get('project')) == (
            WORKSPACE_GID if resource == 'projects' else PROJECT_GID)


@pytest.mark.parametrize('resource,make_record', [('projects', _project), ('tasks', _task)])
def test_lists_keep_records_found_only_after_an_empty_page(resource, make_record, mock_http):
    record = make_record()
    mock_http.responses.extend([_page([], 'later'), _page([record])])

    assert _list_resource(resource) == [record]
    assert len(mock_http.requests) == 2


@pytest.mark.parametrize('resource', ['projects', 'tasks'])
def test_lists_accept_empty_final_page(resource, mock_http):
    mock_http.responses.append(_page([]))

    assert _list_resource(resource) == []
    assert len(mock_http.requests) == 1


@pytest.mark.parametrize('resource', ['projects', 'tasks'])
@pytest.mark.parametrize('body', [
    pytest.param({'next_page': None}, id='missing-data'),
    pytest.param({'data': None, 'next_page': None}, id='null-data'),
    pytest.param({'data': {}, 'next_page': None}, id='object-data'),
    pytest.param({'data': 'tasks', 'next_page': None}, id='string-data'),
    pytest.param({'data': []}, id='missing-next-page'),
    pytest.param({'data': [], 'next_page': []}, id='array-next-page'),
    pytest.param({'data': [], 'next_page': 'cursor'}, id='string-next-page'),
    pytest.param({'data': [], 'next_page': {}}, id='missing-offset'),
    pytest.param({'data': [], 'next_page': {'offset': None}}, id='null-offset'),
    pytest.param({'data': [], 'next_page': {'offset': 1}}, id='integer-offset'),
    pytest.param({'data': [], 'next_page': {'offset': ''}}, id='empty-offset'),
])
def test_lists_reject_malformed_pagination(resource, body, mock_http):
    mock_http.responses.append(httpx.Response(200, json=body))

    with pytest.raises(asana.AsanaError) as exc:
        _list_resource(resource)

    _assert_tool_error(exc.value)
    assert exc.value.read_count == 0
    assert len(mock_http.requests) == 1


@pytest.mark.parametrize('resource,make_record', [('projects', _project), ('tasks', _task)])
@pytest.mark.parametrize('offsets', [('same', 'same'), ('first', 'second', 'first')],
                         ids=['repeated', 'cycle'])
def test_lists_stop_repeated_offsets(resource, make_record, offsets, mock_http):
    for offset in offsets:
        mock_http.responses.append(_page([make_record()], offset))

    with pytest.raises(asana.AsanaError) as exc:
        _list_resource(resource)

    _assert_tool_error(exc.value)
    assert len(mock_http.requests) == len(offsets)
    assert exc.value.read_count == len(offsets)


@pytest.mark.parametrize('resource,make_record', [('projects', _project), ('tasks', _task)])
@pytest.mark.parametrize('successful_pages', [1, 2])
@pytest.mark.parametrize('failure', ['403', '500', 'timeout', 'network', 'bad-record'])
def test_later_page_failure_never_returns_partial_lists(
        resource, make_record, successful_pages, failure, mock_http):
    for i in range(successful_pages):
        mock_http.responses.append(_page([make_record(), make_record()], f'page-{i + 1}'))
    responses = {'403': _failure(403), '500': _failure(500),
                 'timeout': httpx.ReadTimeout('Synthetic later-page timeout'),
                 'network': httpx.ConnectError('Synthetic later-page connection failure'),
                 'bad-record': _page([{'gid': None}])}
    mock_http.responses.append(responses[failure])

    with pytest.raises(asana.AsanaError) as exc:
        _list_resource(resource)

    _assert_tool_error(exc.value)
    assert exc.value.read_count == successful_pages * 2
    assert str(successful_pages * 2) in str(exc.value)
    assert len(mock_http.requests) == successful_pages + 1


@pytest.mark.parametrize('resource,make_record', [('projects', _project), ('tasks', _task)])
@pytest.mark.parametrize('recovers', [True, False])
def test_later_page_rate_limit_is_bounded_and_all_or_error(resource, make_record, recovers, mock_http):
    records = [make_record('1200000000000201'), make_record('1200000000000202')]
    mock_http.responses.append(_page(records[:1], 'second'))
    retries = 1 if recovers else 4
    mock_http.responses.extend(_failure(429, headers={'Retry-After': '2'}) for _ in range(retries))
    if recovers:
        mock_http.responses.append(_page(records[1:]))
        assert _list_resource(resource) == records
    else:
        with pytest.raises(asana.AsanaError) as exc:
            _list_resource(resource)
        _assert_tool_error(exc.value)
        assert exc.value.read_count == 1
    assert len(mock_http.requests) == (3 if recovers else 5)
    assert mock_http.sleeps == ([2] if recovers else [2, 2, 2])
    assert sum(mock_http.sleeps) <= 60
    assert all(r.url.params['offset'] == 'second' for r in mock_http.requests[1:])


@pytest.mark.parametrize('resource', ['projects', 'tasks'])
@pytest.mark.parametrize('gid', [None, '', ' ', '\t\n', 123, True, [], {}])
def test_list_invalid_scope_fails_before_http(resource, gid, mock_http):
    client = asana.Asana()
    method = client.list_projects if resource == 'projects' else client.list_tasks

    with pytest.raises(ValueError):
        method(gid)

    assert mock_http.requests == []


@pytest.mark.parametrize('completed,expected', [(False, [0, 2]), (True, [1]), (None, [0, 1, 2])])
def test_completed_filter_runs_after_all_pages(completed, expected, mock_http):
    records = [_task(str(1200000000000300 + i), completed=i == 1) for i in range(3)]
    mock_http.responses.extend([_page(records[:2], 'later'), _page(records[2:])])

    assert asana.Asana().list_tasks(PROJECT_GID, completed=completed) == [records[i] for i in expected]
    for request in mock_http.requests:
        if completed is False:
            assert request.url.params['completed_since'] == 'now'
        else:
            assert 'completed_since' not in request.url.params


@pytest.mark.parametrize('assignee,expected', [(USER_GID, [0]), ('1200000000000998', [1]),
                                              ('1200000000000997', []), (None, [0, 1, 2])])
def test_assignee_filter_keeps_only_matching_native_records(assignee, expected, mock_http):
    records = [_task(), _task('1200000000000301', assignee={'gid': '1200000000000998', 'name': 'Bob'}),
               _task('1200000000000302', assignee=None)]
    mock_http.responses.append(_page(records))

    assert asana.Asana().list_tasks(PROJECT_GID, assignee_gid=assignee) == [records[i] for i in expected]


@pytest.mark.parametrize('start,end,expected', [
    (date(2026, 10, 7), None, [1, 2, 3]),
    (None, date(2026, 10, 8), [0, 1, 2]),
    (date(2026, 10, 7), date(2026, 10, 8), [1, 2]),
    (date(2026, 10, 7), date(2026, 10, 7), [1]),
    (None, None, [0, 1, 2, 3, 4]),
])
def test_due_filters_include_endpoints_and_handle_missing_dates(start, end, expected, mock_http):
    records = [_task(str(1200000000000300 + i), due_on=f'2026-10-{6 + i:02}') for i in range(4)]
    records.append(_task('1200000000000304'))
    mock_http.responses.append(_page(records))

    assert asana.Asana().list_tasks(PROJECT_GID, due_from=start, due_to=end) == [records[i] for i in expected]


@pytest.mark.parametrize('fields,expected', [
    ({'due_on': None, 'due_at': None}, None),
    ({'due_on': '2026-10-09', 'due_at': None}, date(2026, 10, 9)),
    ({'due_on': None, 'due_at': '2026-10-06T22:30:00Z'}, date(2026, 10, 7)),
    ({'due_on': None, 'due_at': '2026-10-07T09:30:00+11:00'}, date(2026, 10, 7)),
    ({'due_on': '2026-10-08', 'due_at': '2026-10-06T22:30:00Z'}, date(2026, 10, 8)),
])
def test_due_day_uses_pinned_local_day_and_due_on_precedence(fields, expected, monkeypatch):
    monkeypatch.setattr(asana, '_local_zone', lambda: timezone(timedelta(hours=11)))
    task = _task(**fields)
    before = deepcopy(task)

    assert asana.due_day(task) == expected
    assert task == before


@pytest.mark.parametrize('due_on,expected', [(None, True), ('2026-10-08', False)])
def test_due_at_local_day_is_used_by_list_filter(due_on, expected, monkeypatch, mock_http):
    monkeypatch.setattr(asana, '_local_zone', lambda: timezone(timedelta(hours=11)))
    task = _task(due_on=due_on, due_at='2026-10-06T22:30:00Z')
    mock_http.responses.append(_page([task]))

    assert asana.Asana().list_tasks(PROJECT_GID, due_from=date(2026, 10, 7),
                                   due_to=date(2026, 10, 7)) == ([task] if expected else [])


def test_combined_filters_find_only_later_page_match(mock_http):
    records = [_task('1200000000000400', completed=True, due_on='2026-10-07'),
               _task('1200000000000401', assignee=None, due_on='2026-10-07'),
               _task('1200000000000402', due_on='2026-10-06'),
               _task('1200000000000403', due_on='2026-10-07', extra={'kept': [None]})]
    mock_http.responses.extend([_page(records[:3], 'later'), _page(records[3:])])

    assert asana.Asana().list_tasks(PROJECT_GID, completed=False, assignee_gid=USER_GID,
                                   due_from=date(2026, 10, 7), due_to=date(2026, 10, 7)) == records[3:]
    assert len(mock_http.requests) == 2


@pytest.mark.parametrize('filters', [
    pytest.param({'assignee_gid': ''}, id='empty-assignee'),
    pytest.param({'assignee_gid': ' '}, id='blank-assignee'),
    pytest.param({'assignee_gid': 123}, id='integer-assignee'),
    pytest.param({'assignee_gid': True}, id='bool-assignee'),
    pytest.param({'completed': 0}, id='integer-completed'),
    pytest.param({'completed': 'False'}, id='string-completed'),
    pytest.param({'due_from': '2026-10-07'}, id='string-due-from'),
    pytest.param({'due_to': '2026-10-08'}, id='string-due-to'),
    pytest.param({'due_from': datetime(2026, 10, 7)}, id='datetime-due-from'),
    pytest.param({'due_to': datetime(2026, 10, 8)}, id='datetime-due-to'),
    pytest.param({'due_from': 1}, id='integer-due-from'),
    pytest.param({'due_to': False}, id='bool-due-to'),
    pytest.param({'due_from': date(2026, 10, 8), 'due_to': date(2026, 10, 7)}, id='reversed-range'),
    pytest.param({'modified_since': '2026-10-07T00:00:00Z'}, id='string-modified-since'),
    pytest.param({'modified_since': date(2026, 10, 7)}, id='date-modified-since'),
    pytest.param({'modified_since': datetime(2026, 10, 7)}, id='naive-modified-since'),
])
def test_invalid_filters_fail_before_http(filters, mock_http):
    with pytest.raises(ValueError):
        asana.Asana().list_tasks(PROJECT_GID, **filters)

    assert mock_http.requests == []


@pytest.mark.parametrize('since', [datetime(2026, 10, 7, tzinfo=timezone.utc),
                                  datetime(2026, 10, 7, 9, tzinfo=timezone(timedelta(hours=11)))])
def test_aware_modified_since_is_sent_to_api(since, mock_http):
    mock_http.responses.append(_page([]))

    assert asana.Asana().list_tasks(PROJECT_GID, modified_since=since) == []
    sent = mock_http.requests[0].url.params['modified_since']
    assert datetime.fromisoformat(sent.replace('Z', '+00:00')) == since


@pytest.mark.parametrize('resource,make_record', [('projects', _project), ('tasks', _task)])
@pytest.mark.parametrize('fields', [{}, {'gid': None}, {'gid': ''}, {'gid': 123}, {'gid': True}])
def test_list_records_require_nonempty_string_gid(resource, make_record, fields, mock_http):
    record = make_record()
    record.pop('gid')
    record.update(fields)
    mock_http.responses.append(_page([record]))

    with pytest.raises(asana.AsanaError) as exc:
        _list_resource(resource)

    _assert_tool_error(exc.value)


@pytest.mark.parametrize('field,value', [
    ('completed', None), ('completed', 0), ('completed', 1), ('completed', 'False'),
    ('assignee', []), ('assignee', 'Alice'), ('assignee', {}),
    ('assignee', {'gid': None}), ('assignee', {'gid': ''}), ('assignee', {'gid': 123}),
    ('due_on', '2026-02-30'), ('due_on', 'not-a-date'), ('due_on', 123),
    ('due_on', '2026-10-07T00:00:00Z'),
    ('due_at', '2026-10-07T09:30:00'), ('due_at', '2026-10-07'),
    ('due_at', 'not-a-time'), ('due_at', '2026-02-30T09:00:00Z'), ('due_at', 123),
])
def test_task_records_reject_invalid_filter_fields(field, value, mock_http):
    mock_http.responses.append(_page([_task(**{field: value})]))

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().list_tasks(PROJECT_GID)

    _assert_tool_error(exc.value)


@pytest.mark.parametrize('field', ['completed', 'assignee', 'due_on', 'due_at'])
def test_task_records_require_each_filter_field(field, mock_http):
    record = _task()
    record.pop(field)
    mock_http.responses.append(_page([record]))

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().list_tasks(PROJECT_GID)

    _assert_tool_error(exc.value)


@pytest.mark.parametrize('fields', [
    {'assignee': None, 'due_on': None, 'due_at': None},
    {'assignee': {'gid': USER_GID, 'extra': [None]}},
    {'due_on': '2026-10-07'}, {'due_at': '2026-10-06T22:30:00Z'},
    {'due_at': '2026-10-07T09:30:00+11:00'}, {'name': None},
])
def test_task_records_preserve_valid_nulls_and_native_fields(fields, mock_http):
    record = _task(**fields, extra={'nested': [None, {'value': '保留'}]})
    mock_http.responses.append(_page([record]))

    assert asana.Asana().list_tasks(PROJECT_GID) == [record]


def test_task_name_can_be_missing_without_reshaping_record(mock_http):
    record = _task()
    record.pop('name')
    mock_http.responses.append(_page([record]))

    assert asana.Asana().list_tasks(PROJECT_GID) == [record]


@pytest.mark.parametrize('user', [USER_GID, 'person@example.test', 'person+tag/a?#@example.test'])
def test_get_user_gid_and_email_paths_preserve_source_data(user, mock_http):
    from urllib.parse import quote
    record = _user(extra={'native': [None, {'kept': True}]})
    mock_http.responses.append(_success(record))

    assert asana.Asana().get_user(user) == record
    assert len(mock_http.requests) == 1
    request = mock_http.requests[0]
    assert request.method == 'GET'
    assert request.url.raw_path.split(b'?')[0] == f'/api/1.0/users/{quote(user, safe="")}'.encode()
    assert FIELDS <= set(request.url.params['opt_fields'].split(','))


# F13DBREAD-10: task details and the complete source activity stream.
STORY_GID = '000120012345678901234567894'
INVALID_STORY_TIMES = [
    pytest.param({}, id='missing'),
    pytest.param({'created_at': None}, id='null'),
    pytest.param({'created_at': 123}, id='integer'),
    pytest.param({'created_at': True}, id='bool'),
    pytest.param({'created_at': []}, id='array'),
    pytest.param({'created_at': 'not-a-timestamp'}, id='malformed'),
    pytest.param({'created_at': '2026-02-30T08:00:00Z'}, id='invalid-calendar-date'),
]


def _task_detail(gid=TASK_GID, **fields):
    detail = _task(gid, notes='Original notes [literal]\n第二段 🌿',
                   created_at='2026-10-01T08:00:00Z',
                   workspace={'gid': WORKSPACE_GID, 'name': 'Engineering'},
                   followers=[{'gid': '1200000000000801', 'name': 'Bob'},
                              {'gid': '1200000000000802', 'name': 'Carol', 'extra': [None]}],
                   custom_fields=[{'gid': '1200000000000803', 'name': 'Priority',
                                   'display_value': 'High', 'enum_value': {'gid': '1200000000000804',
                                                                         'name': 'High', 'extra': [None]}}])
    detail['projects'].append({'gid': '1200000000000805', 'name': 'Mobile', 'extra': {'kept': True}})
    detail.update(fields)
    return detail


def _story(gid=STORY_GID, **fields):
    story = {'gid': gid, 'created_at': '2026-10-08T08:00:00Z',
             'created_by': {'gid': USER_GID, 'name': 'Alice'},
             'text': 'Original comment [literal] 🌿', 'type': 'comment',
             'resource_subtype': 'comment_added', 'target': {'gid': TASK_GID, 'name': 'Ship website'}}
    story.update(fields)
    return story


def _story_with_time(fields):
    story = _story()
    story.pop('created_at')
    story.update(fields)
    return story


@pytest.mark.parametrize('method', ['get_task', 'list_stories'])
@pytest.mark.parametrize('gid', [None, '', ' ', '\t\n', 123, True, [], {}])
def test_detail_methods_reject_invalid_gid_before_http(method, gid, mock_http):
    with pytest.raises(ValueError):
        getattr(asana.Asana(), method)(gid)

    assert mock_http.requests == []


def test_get_task_requests_native_detail_without_stories(mock_http):
    detail = _task_detail(extra={'nested': [None, {'kept': '保留'}]})
    before = deepcopy(detail)
    mock_http.responses.append(httpx.Response(200, json={'data': detail}))

    result = asana.Asana().get_task(TASK_GID)

    assert result == before and detail == before
    assert len(mock_http.requests) == 1
    request = mock_http.requests[0]
    assert request.method == 'GET'
    assert request.url.path == f'/api/1.0/tasks/{TASK_GID}'
    fields = set(request.url.params['opt_fields'].split(','))
    assert TASK_FIELDS | {'notes', 'created_at'} <= fields
    for name in ('followers', 'workspace', 'custom_fields'):
        assert name in fields or {f'{name}.gid', f'{name}.name'} <= fields
    assert isinstance(result['gid'], str)
    assert result['followers'] != [result['assignee']]
    assert result['projects'] == before['projects']
    assert result['custom_fields'] == before['custom_fields']


@pytest.mark.parametrize('assignee', [None, {'gid': USER_GID, 'name': 'Alice'}])
def test_get_task_keeps_followers_independent_of_assignee(assignee, mock_http):
    detail = _task_detail(assignee=assignee)
    mock_http.responses.append(httpx.Response(200, json={'data': detail}))

    result = asana.Asana().get_task(TASK_GID)

    assert result == detail
    assert result['assignee'] == assignee
    assert [f['gid'] for f in result['followers']] == ['1200000000000801', '1200000000000802']
    assert all(f['gid'] != USER_GID for f in result['followers'])


@pytest.mark.parametrize('fields', [{'name': None}, {'notes': None}, {'notes': ''}])
def test_get_task_preserves_valid_optional_nulls(fields, mock_http):
    detail = _task_detail(**fields)
    mock_http.responses.append(httpx.Response(200, json={'data': detail}))

    assert asana.Asana().get_task(TASK_GID) == detail


def test_get_task_preserves_missing_optional_name(mock_http):
    detail = _task_detail()
    detail.pop('name')
    mock_http.responses.append(httpx.Response(200, json={'data': detail}))

    result = asana.Asana().get_task(TASK_GID)

    assert result == detail
    assert 'name' not in result


@pytest.mark.parametrize('data', [None, [], 'task', 123, {'gid': None}])
def test_get_task_rejects_non_task_detail(data, mock_http):
    mock_http.responses.append(httpx.Response(200, json={'data': data}))

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_task(TASK_GID)

    _assert_tool_error(exc.value)


@pytest.mark.parametrize('fields', [{}, {'gid': None}, {'gid': ''}, {'gid': 123}])
def test_get_task_requires_native_record_gid(fields, mock_http):
    detail = _task_detail()
    detail.pop('gid')
    detail.update(fields)
    mock_http.responses.append(httpx.Response(200, json={'data': detail}))

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_task(TASK_GID)

    _assert_tool_error(exc.value)


def test_get_task_404_is_operational_and_does_not_claim_deletion(mock_http):
    mock_http.responses.append(_failure(404, 'Not Found'))

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().get_task(TASK_GID)

    _assert_tool_error(exc.value)
    assert exc.value.status == 404
    message = str(exc.value).lower()
    assert any(phrase in message for phrase in ('not found', 'no asana task', 'not visible', 'cannot see'))
    assert 'deleted' not in message
    assert len(mock_http.requests) == 1


@pytest.mark.parametrize('pages', [1, 2, 3])
def test_list_stories_reads_all_pages_without_reordering_source(pages, mock_http):
    times = ['2026-10-08T10:30:00Z', '2026-10-08T08:00:00Z', '2026-10-08T09:15:00Z']
    records = [_story(str(1200000000000900 + i), created_at=times[i]) for i in range(pages)]
    offsets = ['opaque +/=一', 'second opaque cursor']
    for i, record in enumerate(records):
        mock_http.responses.append(_page([record], offsets[i] if i < pages - 1 else None))

    assert asana.Asana().list_stories(TASK_GID) == records
    assert len(mock_http.requests) == pages
    for i, request in enumerate(mock_http.requests):
        assert request.method == 'GET'
        assert request.url.path == f'/api/1.0/tasks/{TASK_GID}/stories'
        assert request.url.params.get('offset') == (None if i == 0 else offsets[i - 1])
        assert 'resource_subtype' not in request.url.params
        fields = set(request.url.params['opt_fields'].split(','))
        assert {'gid', 'created_at', 'created_by.gid', 'created_by.name', 'text',
                'type', 'resource_subtype', 'target.gid', 'target.name'} <= fields


@pytest.mark.parametrize('later', [False, True], ids=['empty', 'later-page-only'])
def test_list_stories_accepts_empty_page_and_follows_next_offset(later, mock_http):
    mock_http.responses.append(_page([], 'later' if later else None))
    records = [_story()] if later else []
    if later:
        mock_http.responses.append(_page(records))

    assert asana.Asana().list_stories(TASK_GID) == records
    assert len(mock_http.requests) == (2 if later else 1)


@pytest.mark.parametrize('offsets', [('same', 'same'), ('first', 'second', 'first')],
                         ids=['repeated', 'cycle'])
def test_list_stories_bounds_repeated_offsets(offsets, mock_http):
    for offset in offsets:
        mock_http.responses.append(_page([_story()], offset))

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().list_stories(TASK_GID)

    _assert_tool_error(exc.value)
    assert len(mock_http.requests) == len(offsets)
    assert exc.value.read_count == len(offsets)


@pytest.mark.parametrize('body', [
    pytest.param({'data': []}, id='missing-next-page'),
    pytest.param({'data': None, 'next_page': None}, id='null-data'),
    pytest.param({'data': [], 'next_page': []}, id='array-next-page'),
    pytest.param({'data': [], 'next_page': {'offset': 1}}, id='integer-offset'),
])
def test_list_stories_rejects_malformed_pagination(body, mock_http):
    mock_http.responses.append(httpx.Response(200, json=body))

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().list_stories(TASK_GID)

    _assert_tool_error(exc.value)
    assert exc.value.read_count == 0


@pytest.mark.parametrize('successful_pages', [1, 2])
@pytest.mark.parametrize('failure', ['500', 'network'])
def test_list_stories_later_failure_is_all_or_error(successful_pages, failure, mock_http):
    for i in range(successful_pages):
        mock_http.responses.append(_page([_story()], f'page-{i + 1}'))
    mock_http.responses.append(_failure(500) if failure == '500' else httpx.ConnectError('Later-page failure'))

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().list_stories(TASK_GID)

    _assert_tool_error(exc.value)
    assert exc.value.read_count == successful_pages
    assert len(mock_http.requests) == successful_pages + 1


def test_list_stories_preserves_every_activity_type_and_source_record(mock_http):
    records = [_story(extra={'nested': [None, {'kept': '保留'}]}),
               _story('1200000000000901', type='system', resource_subtype='assigned', text='Assigned to Bob'),
               _story('1200000000000902', type='system', resource_subtype='marked_complete', text='Completed'),
               _story('1200000000000903', type='system', resource_subtype='due_date_changed', created_by=None)]
    records[-1].pop('text')
    before = deepcopy(records)
    mock_http.responses.append(_page(records))

    assert asana.Asana().list_stories(TASK_GID) == before
    assert records == before
    assert 'resource_subtype' not in mock_http.requests[0].url.params


@pytest.mark.parametrize('fields', [{'created_by': None}, {'text': None},
                                  {'created_at': '2026-10-08T19:00:00+11:00'},
                                  {'created_by': {'gid': USER_GID, 'name': None, 'extra': [None]}}])
def test_list_stories_preserves_valid_nullable_source_fields(fields, mock_http):
    record = _story(**fields, extra={'native': [None]})
    mock_http.responses.append(_page([record]))

    assert asana.Asana().list_stories(TASK_GID) == [record]


@pytest.mark.parametrize('fields', INVALID_STORY_TIMES)
def test_list_stories_requires_valid_created_at_and_never_drops_bad_record(fields, mock_http):
    mock_http.responses.append(_page([_story(), _story_with_time(fields)]))

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().list_stories(TASK_GID)

    _assert_tool_error(exc.value)
    assert exc.value.read_count == 0
    assert len(mock_http.requests) == 1


@pytest.mark.parametrize('fields', INVALID_STORY_TIMES)
def test_list_stories_invalid_created_at_on_later_page_fails_whole_list(fields, mock_http):
    mock_http.responses.extend([_page([_story()], 'later'), _page([_story(), _story_with_time(fields)])])

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().list_stories(TASK_GID)

    _assert_tool_error(exc.value)
    assert exc.value.read_count == 1
    assert len(mock_http.requests) == 2


@pytest.mark.parametrize('data', [None, 'story', 123, {}, {'gid': None}, {'gid': ''}, {'gid': 123}])
def test_list_stories_rejects_invalid_story_records(data, mock_http):
    record = data
    if isinstance(data, dict):
        record = _story()
        record.pop('gid')
        record.update(data)
    mock_http.responses.append(_page([record]))

    with pytest.raises(asana.AsanaError) as exc:
        asana.Asana().list_stories(TASK_GID)

    _assert_tool_error(exc.value)
