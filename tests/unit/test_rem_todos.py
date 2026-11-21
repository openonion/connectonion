"""Today shows the owner's open to-dos, apart from events (#3087).

Owner, 2026-11-17, on real-data screenshots: Today showed other people's calendar entries and none of his
Outlook or Google to-dos. The step of the night that saves the calendar reads his open Microsoft To Do tasks
into .state/todos.json; the reader shows that file. Every task here is invented, and Graph is the real co
calendar tool on a fake transport: no test reaches Microsoft.
"""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from connectonion.provider_credentials import ProviderCredentialError
from connectonion.rem import todos

NIGHT = datetime(2026, 10, 1, 2, 30, tzinfo=timezone.utc)
SYDNEY = ZoneInfo('Australia/Sydney')
TASKS = [
    {'id': 't1', 'title': 'Renew the harbour permit', 'status': 'notStarted', '_list': 'Tasks',
     'dueDateTime': {'dateTime': '2026-10-05T13:00:00.0000000', 'timeZone': 'UTC'}},
    {'id': 't2', 'title': 'Order lantern glass', 'status': 'inProgress', '_list': 'Workshop'},
    {'id': 't3', 'title': 'Post the old invoice', 'status': 'completed', '_list': 'Tasks'},
]


@pytest.fixture
def todo(monkeypatch):
    """Microsoft To Do connected; `answers[0]` is the tasks Graph returns or an exception to raise."""
    answers = [TASKS]
    monkeypatch.setattr(todos, 'available', lambda: True)
    monkeypatch.setattr(todos, 'google_tasks', lambda: 'reconnect')

    def tasks(zone):
        if isinstance(answers[0], Exception):
            raise answers[0]
        return answers[0]

    monkeypatch.setattr(todos, 'todo_tasks', tasks)
    return answers


def _saved(root):
    return json.loads((root / '.state/todos.json').read_text())


def test_the_night_saves_his_open_to_dos_with_their_list_and_due_day(tmp_path, todo):
    result = todos.save(tmp_path, NIGHT, SYDNEY)
    assert result == {'tasks': 2, 'error': None}
    saved = _saved(tmp_path)
    assert saved['read_at'] == saved['saved_at'] == NIGHT.isoformat()
    # A due date is a day: 13:00 UTC on the 5th is midnight on the 6th in Sydney, the day he set.
    assert saved['tasks'] == [
        {'id': 't1', 'title': 'Renew the harbour permit', 'list': 'Tasks', 'due': '2026-10-06', 'provider': 'microsoft'},
        {'id': 't2', 'title': 'Order lantern glass', 'list': 'Workshop', 'due': '', 'provider': 'microsoft'}]
    assert saved['google'] == 'reconnect'


def test_a_to_do_he_ticked_off_is_gone_after_the_next_read(tmp_path, todo):
    todos.save(tmp_path, NIGHT)
    todo[0] = [TASKS[1]]
    todos.save(tmp_path, NIGHT + timedelta(days=1))
    assert [task['id'] for task in _saved(tmp_path)['tasks']] == ['t2']


@pytest.mark.parametrize('error, reason, words', [
    (TimeoutError('timed out'), 'timeout', 'timed out'),
    (ProviderCredentialError('reauth_required', 'Microsoft authorization expired.', 'co auth microsoft'), 'auth', 'authorization expired'),
])
def test_a_read_that_fails_keeps_the_to_dos_saved_before_and_says_when_and_why(tmp_path, todo, error, reason, words):
    todos.save(tmp_path, NIGHT)
    todo[0] = error
    later = NIGHT + timedelta(days=1)
    assert todos.save(tmp_path, later) == {'tasks': 2, 'error': {'reason': reason, 'at': later.isoformat()}}
    shown = todos.read(tmp_path)
    assert [task['id'] for task in shown['tasks']] == ['t1', 't2'] and shown['read_at'] == NIGHT.isoformat()
    assert shown['error'] == {'at': later.isoformat(), 'reason': words, 'error': ''}


def test_a_fault_in_rem_is_named_and_its_traceback_never_reaches_the_page(tmp_path, todo):
    todo[0] = AttributeError("'MicrosoftCalendar' object has no attribute '_request'")
    result = todos.save(tmp_path, NIGHT)
    assert result['error'] == {'reason': 'bug', 'at': NIGHT.isoformat(), 'error': 'AttributeError'}
    assert 'Traceback' in result['traceback'] and 'Traceback' not in (tmp_path / '.state/todos.json').read_text()
    assert todos.read(tmp_path)['error'] == {'at': NIGHT.isoformat(), 'reason': 'a fault in REM', 'error': 'AttributeError'}


def test_without_a_task_login_nothing_is_asked_and_the_page_can_say_google_must_be_reconnected(tmp_path, monkeypatch):
    monkeypatch.setenv('MICROSOFT_SCOPES', 'Mail.Read Calendars.Read offline_access')
    monkeypatch.setenv('GOOGLE_SCOPES', 'https://www.googleapis.com/auth/calendar')
    monkeypatch.setattr(todos, 'todo_tasks', lambda zone: pytest.fail('asked for tasks the login cannot read'))
    assert todos.read(tmp_path) is None, 'before any night there is nothing to say'
    assert todos.save(tmp_path, NIGHT) == {'tasks': 0, 'error': None}
    assert todos.read(tmp_path) == {'tasks': [], 'read_at': '', 'google': 'reconnect', 'error': None}


@pytest.mark.parametrize('scopes, state', [
    ('', None),  # no Google login at all: nothing to reconnect
    ('https://www.googleapis.com/auth/calendar', 'reconnect'),
    ('https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/tasks.readonly', 'not_read'),
])
def test_google_tasks_are_never_a_silent_skip(monkeypatch, scopes, state):
    monkeypatch.setenv('GOOGLE_SCOPES', scopes)
    assert todos.google_tasks() == state


def test_the_real_graph_client_reads_every_list_and_every_page_of_open_tasks(monkeypatch):
    from connectonion.useful_tools import microsoft_calendar
    monkeypatch.setenv('MICROSOFT_SCOPES', 'Calendars.Read Tasks.ReadWrite')
    monkeypatch.setenv('MICROSOFT_ACCESS_TOKEN', 'fake-token')
    monkeypatch.setenv('MICROSOFT_TOKEN_EXPIRES_AT', (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    graph, seen = 'https://graph.microsoft.com/v1.0', []

    def answer(request):
        seen.append((request.url.path, request.url.params.get('$filter'), request.headers.get('authorization')))
        if request.url.path == '/v1.0/me/todo/lists':
            return httpx.Response(200, json={'value': [{'id': 'a', 'displayName': 'Tasks'}, {'id': 'b', 'displayName': 'Workshop'}]})
        if request.url.path.endswith('/a/tasks') and 'skip' not in str(request.url):
            return httpx.Response(200, json={'value': [TASKS[0]], '@odata.nextLink': graph + '/me/todo/lists/a/tasks?skip=1'})
        if request.url.path.endswith('/a/tasks'):
            return httpx.Response(200, json={'value': [TASKS[2]]})
        return httpx.Response(200, json={'value': [TASKS[1]]})

    client = httpx.Client(transport=httpx.MockTransport(answer))
    monkeypatch.setattr(microsoft_calendar.httpx, 'request', client.request)
    assert todos.available()
    rows = todos.todo_tasks(SYDNEY)
    assert [(row['title'], row['_list']) for row in rows] == [
        ('Renew the harbour permit', 'Tasks'), ('Post the old invoice', 'Tasks'), ('Order lantern glass', 'Workshop')]
    assert [path for path, _, _ in seen] == ['/v1.0/me/todo/lists', '/v1.0/me/todo/lists/a/tasks',
                                             '/v1.0/me/todo/lists/a/tasks', '/v1.0/me/todo/lists/b/tasks']
    assert seen[1][1] == "status ne 'completed'" and {auth for _, _, auth in seen} == {'Bearer fake-token'}


def test_the_calendar_step_of_the_night_saves_the_to_dos_and_no_failure_stops_it(tmp_path, monkeypatch, todo):
    from connectonion.rem import calendar, schedule
    from connectonion.rem.config import prepare
    from connectonion.rem.service import run_logs
    prepare(tmp_path)
    monkeypatch.setattr(calendar, 'available', lambda kind: False)
    result = schedule.calendar_round(tmp_path)
    assert result['todos'] == {'tasks': 2, 'error': None} and len(_saved(tmp_path)['tasks']) == 2
    todo[0] = AttributeError('broken task adapter')
    result = schedule.calendar_round(tmp_path)
    assert result['todos']['error']['error'] == 'AttributeError' and 'traceback' not in result['todos']
    assert 'day_plan' in result, 'the day plan is still saved'
    logged = [run for run in run_logs(tmp_path) if run.get('phase') == 'todos']
    assert len(logged) == 1 and logged[0]['outcome'] == 'failed' and 'Traceback' in logged[0]['error']


def test_only_the_owners_own_reader_carries_his_to_dos(tmp_path, todo):
    from connectonion.rem.config import prepare
    from connectonion.rem.reader import snapshot
    prepare(tmp_path)
    todos.save(tmp_path, NIGHT)
    assert [task['id'] for task in snapshot(tmp_path, local=True)['todos']['tasks']] == ['t1', 't2']
    assert snapshot(tmp_path)['todos'] is None
