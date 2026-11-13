"""Agenda shows the owner's next days from his connected calendars (#2998, asked in #2841).

Owner, 2026-11-13: «我需要快速看到我最近日历上有什么事件之类的，但完全没有啊！» The night run saves the
next three weeks from every calendar co can already read into .state/calendar.json; the reader shows
that file. The calendars here are fakes in each provider's own shape, or the real co calendar tools on a
fake transport: no test reaches a real calendar.
"""
import json
import ssl
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from connectonion.credentials import MissingAmbientAPIKey
from connectonion.provider_credentials import ProviderCredentialError
from connectonion.rem import calendar
from connectonion.rem.files import Notebook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))

NIGHT = datetime(2026, 10, 1, 2, 30, tzinfo=timezone.utc)
SYDNEY = ZoneInfo('Australia/Sydney')

GOOGLE = [
    {'id': 'g1', 'summary': 'Pilot renewal call with Fernhill', 'htmlLink': 'https://calendar.example/g1',
     'start': {'dateTime': '2026-10-02T09:30:00+13:00'}, 'end': {'dateTime': '2026-10-02T10:00:00+13:00'},
     'location': 'Video call', 'attendees': [{'email': 'avery@example.test', 'self': True},
                                             {'email': 'Mara@Fernhill.example'}]},
    {'id': 'g2', 'summary': 'Harbour offsite', 'start': {'date': '2026-10-05'}, 'end': {'date': '2026-10-07'}},
    {'id': 'g3', 'summary': 'Cancelled standup', 'status': 'cancelled',
     'start': {'dateTime': '2026-10-03T09:00:00Z'}, 'end': {'dateTime': '2026-10-03T09:15:00Z'}},
]
OUTLOOK = [
    {'id': 'o1', 'subject': 'Quarterly receipts with Ines', 'webLink': 'https://outlook.example/o1',
     'start': {'dateTime': '2026-10-03T01:00:00.0000000', 'timeZone': 'UTC'},
     'end': {'dateTime': '2026-10-03T01:30:00.0000000', 'timeZone': 'UTC'},
     'location': {'displayName': 'Harbour office'}, 'attendees': [{'emailAddress': {'address': 'ines@example.test'}}]},
    {'id': 'o2', 'subject': 'School holiday', 'isAllDay': True,
     'start': {'dateTime': '2026-10-04T00:00:00.0000000', 'timeZone': 'UTC'},
     'end': {'dateTime': '2026-10-05T00:00:00.0000000', 'timeZone': 'UTC'}},
]


@pytest.fixture
def calendars(monkeypatch):
    """Both calendars connected; `answers[kind]` is a list of events or an exception to raise."""
    answers, asked = {'google': GOOGLE, 'microsoft': OUTLOOK}, []
    monkeypatch.setattr(calendar, 'available', lambda kind: kind in answers)

    def events(kind, start, end, zone):
        asked.append((kind, start, end, zone))
        if isinstance(answers[kind], Exception):
            raise answers[kind]
        return answers[kind]

    monkeypatch.setattr(calendar, 'calendar_events', events)
    return answers, asked


def _saved(root):
    return json.loads((root / '.state/calendar.json').read_text())


def test_the_night_saves_both_calendars_next_weeks_in_one_shape(tmp_path, calendars):
    _, asked = calendars
    result = calendar.save_upcoming(tmp_path, NIGHT)
    assert result == {'events': 4, 'read': ['google', 'microsoft'], 'errors': {}, 'capped': []}
    # From the start of yesterday (an event that began last night is still "now") through three weeks.
    assert [(kind, start.isoformat(), (end - start).days) for kind, start, end, _ in asked] == [
        ('google', '2026-09-30T00:00:00+00:00', 22), ('microsoft', '2026-09-30T00:00:00+00:00', 22)]
    saved = _saved(tmp_path)
    assert saved['read_at'] == {'google': '2026-10-01T02:30:00+00:00', 'microsoft': '2026-10-01T02:30:00+00:00'}
    by_id = {event['id']: event for event in saved['events']}
    assert set(by_id) == {'g1', 'g2', 'o1', 'o2'}, 'a cancelled event is not on the calendar'
    assert by_id['g1'] == {'id': 'g1', 'title': 'Pilot renewal call with Fernhill', 'all_day': False,
                           'start': '2026-10-02T09:30:00+13:00', 'end': '2026-10-02T10:00:00+13:00',
                           'location': 'Video call', 'link': 'https://calendar.example/g1',
                           'attendees': ['Mara@Fernhill.example'], 'calendar': 'google'}
    assert by_id['g2']['all_day'] and by_id['g2']['start'] == '2026-10-05'
    # Graph's UTC has no offset in the string; it is written with one.
    assert by_id['o1']['start'] == '2026-10-03T01:00:00+00:00' and by_id['o1']['location'] == 'Harbour office'
    assert by_id['o2']['all_day'] and (by_id['o2']['start'], by_id['o2']['end']) == ('2026-10-04', '2026-10-05')


def test_an_outlook_all_day_event_in_sydney_keeps_its_day(tmp_path, calendars):
    answers, asked = calendars
    # Answered in UTC, Sydney's 4 October starts at 14:00 on the 3rd; answered in Sydney time (the Prefer), at midnight.
    answers['microsoft'] = [
        {'id': 'utc', 'subject': 'Long weekend', 'isAllDay': True,
         'start': {'dateTime': '2026-10-03T14:00:00.0000000', 'timeZone': 'UTC'},
         'end': {'dateTime': '2026-10-04T14:00:00.0000000', 'timeZone': 'UTC'}},
        {'id': 'local', 'subject': 'Harbour picnic', 'isAllDay': True,
         'start': {'dateTime': '2026-10-04T00:00:00.0000000', 'timeZone': 'Australia/Sydney'},
         'end': {'dateTime': '2026-10-05T00:00:00.0000000', 'timeZone': 'Australia/Sydney'}},
        {'id': 'timed', 'subject': 'Coffee with Ines', 'start': {'dateTime': '2026-10-04T09:00:00.0000000', 'timeZone': 'Australia/Sydney'},
         'end': {'dateTime': '2026-10-04T09:30:00.0000000', 'timeZone': 'Australia/Sydney'}}]
    answers['google'] = []
    calendar.save_upcoming(tmp_path, NIGHT, SYDNEY)
    by_id = {event['id']: event for event in _saved(tmp_path)['events']}
    assert by_id['utc']['start'] == '2026-10-04' and by_id['local']['start'] == '2026-10-04'
    assert by_id['timed']['start'] == '2026-10-04T09:00:00+11:00'  # daylight saving began at 02:00 that morning
    # The window is the owner's days, not UTC's.
    assert asked[-1][1].isoformat() == '2026-09-30T00:00:00+10:00'


@pytest.mark.parametrize('error, reason', [
    (TimeoutError('timed out'), 'timeout'),
    (ConnectionResetError(54, 'Connection reset by peer'), 'network'),
    (ssl.SSLError('EOF occurred in violation of protocol'), 'network'),
    (OSError('Credential file is busy. Next: co status'), 'unavailable'),
    (httpx.ReadTimeout('read timed out'), 'timeout'),
    (ProviderCredentialError('reauth_required', 'Microsoft authorization expired.', 'co auth microsoft'), 'auth'),
    (MissingAmbientAPIKey(), 'auth'),
])
def test_a_calendar_that_fails_keeps_what_it_saved_before_and_says_when_and_why(tmp_path, calendars, error, reason):
    answers, _ = calendars
    calendar.save_upcoming(tmp_path, NIGHT)
    answers['microsoft'] = error
    answers['google'] = [GOOGLE[1]]
    later = NIGHT + timedelta(days=1)
    result = calendar.save_upcoming(tmp_path, later)
    assert result['read'] == ['google'] and result['errors'] == {'microsoft': {'reason': reason, 'at': later.isoformat()}}
    saved = _saved(tmp_path)
    assert sorted(event['id'] for event in saved['events']) == ['g2', 'o1', 'o2']
    # Per calendar: Outlook's events are as of the first night, Google's as of tonight.
    assert saved['read_at'] == {'google': later.isoformat(), 'microsoft': NIGHT.isoformat()}


def test_a_fault_in_rem_is_named_and_the_night_goes_on(tmp_path, calendars):
    answers, _ = calendars
    answers['google'] = AttributeError("'GoogleCalendar' object has no attribute '_get_service'")
    result = calendar.save_upcoming(tmp_path, NIGHT)
    fault = result['errors']['google']
    assert {key: fault[key] for key in ('reason', 'at', 'error')} == {'reason': 'bug', 'at': NIGHT.isoformat(), 'error': 'AttributeError'}
    assert 'Traceback' in fault['traceback'] and 'traceback' not in _saved(tmp_path)['errors']['google'], 'the page never gets it'
    shown = calendar.upcoming(tmp_path, [], '')
    assert shown['errors'] == [{'name': 'Google Calendar', 'at': NIGHT.isoformat(), 'read_at': '',
                                'reason': 'a fault in REM', 'error': 'AttributeError'}]
    assert [event['id'] for event in shown['events']] == ['o1', 'o2']


def test_a_calendar_co_cannot_read_is_never_asked_and_the_page_can_say_none_is_connected(tmp_path, monkeypatch):
    monkeypatch.setattr(calendar, 'calendar_events', lambda *args: pytest.fail('asked a calendar that is not connected'))
    # The test HOME has no co keys at all: neither calendar counts as connected, and nothing starts a login.
    assert calendar.save_upcoming(tmp_path, NIGHT) == {'events': 0, 'read': [], 'errors': {}, 'capped': []}
    shown = calendar.upcoming(tmp_path, [], '')
    assert (shown['read'], shown['errors'], shown['events']) == ([], [], [])


def test_available_asks_the_same_saved_scopes_the_calendar_tools_check(monkeypatch):
    monkeypatch.setenv('MICROSOFT_SCOPES', 'Mail.Read Calendars.Read offline_access')
    monkeypatch.setenv('GOOGLE_SCOPES', 'https://www.googleapis.com/auth/gmail.readonly')
    assert calendar.available('microsoft') and not calendar.available('google')
    monkeypatch.setenv('GOOGLE_SCOPES', 'https://www.googleapis.com/auth/calendar.readonly')
    assert calendar.available('google')


def test_the_real_outlook_tool_reads_every_calendar_and_every_page_in_the_owners_zone(monkeypatch):
    from connectonion.useful_tools import microsoft_calendar
    monkeypatch.setenv('MICROSOFT_SCOPES', 'Calendars.Read')
    monkeypatch.setenv('MICROSOFT_ACCESS_TOKEN', 'fake-token')
    monkeypatch.setenv('MICROSOFT_TOKEN_EXPIRES_AT', (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    graph, seen = 'https://graph.microsoft.com/v1.0', []

    def answer(request):
        seen.append((request.url.path, request.headers.get('prefer'), request.headers.get('authorization')))
        if request.url.path == '/v1.0/me/calendars':
            return httpx.Response(200, json={'value': [{'id': 'work'}, {'id': 'family'}]})
        if request.url.path.endswith('/work/calendarView') and 'skip' not in str(request.url):
            assert request.url.params['startDateTime'].startswith('2026-09-30T00:00:00')
            return httpx.Response(200, json={'value': [OUTLOOK[0]], '@odata.nextLink': graph + '/me/calendars/work/calendarView?skip=1'})
        if request.url.path.endswith('/work/calendarView'):
            return httpx.Response(200, json={'value': [OUTLOOK[1]]})
        return httpx.Response(200, json={'value': [{**OUTLOOK[0], 'id': 'f1', 'subject': 'School pickup'}]})

    client = httpx.Client(transport=httpx.MockTransport(answer))
    monkeypatch.setattr(microsoft_calendar.httpx, 'request', client.request)
    start = datetime(2026, 9, 30, tzinfo=SYDNEY)
    items = calendar.calendar_events('microsoft', start, start + timedelta(days=22), SYDNEY)
    assert [item['subject'] for item in items] == ['Quarterly receipts with Ines', 'School holiday', 'School pickup']
    assert [path for path, _, _ in seen] == ['/v1.0/me/calendars', '/v1.0/me/calendars/work/calendarView',
                                             '/v1.0/me/calendars/work/calendarView', '/v1.0/me/calendars/family/calendarView']
    assert {prefer for _, prefer, _ in seen} == {'outlook.timezone="Australia/Sydney"'}
    assert {auth for _, _, auth in seen} == {'Bearer fake-token'}


def test_the_real_google_tool_reads_every_shown_calendar_and_every_page(monkeypatch):
    from googleapiclient.discovery import build
    from googleapiclient.http import HttpMockSequence
    from connectonion.useful_tools.google_calendar import GoogleCalendar
    monkeypatch.setenv('GOOGLE_SCOPES', 'https://www.googleapis.com/auth/calendar.readonly')
    monkeypatch.setenv('GOOGLE_ACCESS_TOKEN', 'fake-token')
    page = lambda body: ({'status': '200'}, json.dumps(body))  # noqa: E731
    http = HttpMockSequence([
        page({'items': [{'id': 'primary-id', 'primary': True}], 'nextPageToken': 'p2'}),
        page({'items': [{'id': 'team-id', 'selected': True}, {'id': 'holidays-id'}]}),
        page({'items': [GOOGLE[0]], 'nextPageToken': 'e2'}),
        page({'items': [GOOGLE[1]]}),
        page({'items': [{**GOOGLE[0], 'id': 't1', 'summary': 'Team retro'}]}),
    ])
    asked = []
    original = http.request

    def request(uri, method='GET', **kw):
        asked.append(uri.split('?')[0].rsplit('/v3/', 1)[1])
        return original(uri, method, **kw)

    http.request = request
    # The tool's own service, built on the fake transport: a renamed _get_service fails here, not on the owner's night.
    monkeypatch.setattr(GoogleCalendar, '_get_service', lambda self: build('calendar', 'v3', http=http, static_discovery=True))
    start = datetime(2026, 9, 30, tzinfo=timezone.utc)
    items = calendar.calendar_events('google', start, start + timedelta(days=22), timezone.utc)
    assert [item['summary'] for item in items] == ['Pilot renewal call with Fernhill', 'Harbour offsite', 'Team retro']
    assert asked == ['users/me/calendarList', 'users/me/calendarList', 'calendars/primary-id/events',
                     'calendars/primary-id/events', 'calendars/team-id/events'], 'an unticked calendar is not read'


def test_the_reader_gets_each_event_with_its_peoples_pages_and_none_before_a_night(tmp_path, calendars):
    records = [{'path': 'people/mara.md', 'category': 'people',
                'text': '# Mara\n\n## Facts\n- Email: mara@fernhill.example (work) [1]\n'},
               {'path': 'people/tomas.md', 'category': 'people',
                'text': '# Tomás\n\nHe forwarded ines@example.test the invoice [2].\n'},
               {'path': 'people/avery.md', 'category': 'people', 'text': '# Avery\n- Email: avery@example.test\n'}]
    assert calendar.upcoming(tmp_path, records, 'people/avery.md') is None
    calendar.save_upcoming(tmp_path, NIGHT)
    shown = calendar.upcoming(tmp_path, records, 'people/avery.md')
    assert shown['read'] == [{'name': 'Google Calendar', 'at': NIGHT.isoformat()}, {'name': 'Outlook', 'at': NIGHT.isoformat()}]
    by_id = {event['id']: event for event in shown['events']}
    assert by_id['g1']['people'] == ['people/mara.md'] and by_id['g1']['guests'] == 1
    # An address only quoted on someone else's page does not make the meeting theirs.
    assert by_id['o1']['people'] == [] and by_id['o1']['guests'] == 1
    assert 'attendees' not in by_id['g1'], 'addresses stay in .state; the page carries page links'


def test_only_the_owners_own_reader_carries_his_calendar(tmp_path, calendars):
    from rem_reader_notebook import build
    from connectonion.rem.reader import snapshot
    root = build(tmp_path / 'rem', NIGHT)
    calendar.save_upcoming(root, NIGHT)
    mine = snapshot(root, local=True)['calendar']
    assert [event['title'] for event in mine['events']][:2] == ['Pilot renewal call with Fernhill', 'Quarterly receipts with Ines']
    assert snapshot(root, local=False)['calendar'] is None


def _round(root, monkeypatch):
    from connectonion.rem.config import prepare
    from connectonion.rem.daily import run_daily
    prepare(root)
    Notebook(root).write('projects/a.md', '# A\nUnknown\n')
    monkeypatch.setattr('connectonion.rem.daily.subscriptions', lambda root: {})
    drafted = []
    monkeypatch.setattr('connectonion.rem.daily._draft_replies', lambda *args: drafted.append(True))
    result = run_daily(root, maintain=lambda root: {'outcome': 'no_change'},
                       investigate_one=lambda *args, **kw: {'changed': [], 'usage': {}})
    return result, drafted


def test_the_nightly_round_saves_the_calendars(tmp_path, monkeypatch, calendars):
    result, drafted = _round(tmp_path, monkeypatch)
    assert len(_saved(tmp_path)['events']) == 4 and drafted and result['outcome'] == 'completed'


@pytest.mark.parametrize('error', [TimeoutError('timed out'), OSError('Credential file is busy. Next: co status'),
                                   AttributeError('_get_service')])
def test_no_calendar_failure_stops_the_night(tmp_path, monkeypatch, calendars, error):
    answers, _ = calendars
    answers['google'] = answers['microsoft'] = error
    result, drafted = _round(tmp_path, monkeypatch)
    assert drafted and result['outcome'] == 'completed', 'drafts and the investigation still ran'
    assert set(_saved(tmp_path)['errors']) == {'google', 'microsoft'}
    from connectonion.rem.service import run_logs
    logged = [run for run in run_logs(tmp_path) if run.get('phase') == 'calendar']
    if isinstance(error, AttributeError):
        # A fault in REM is a failed run with its traceback, one per calendar, out of the round's result.
        assert len(logged) == 2 and all(run['outcome'] == 'failed' and 'Traceback' in run['error'] for run in logged)
        assert 'traceback' not in result['maintenance']['calendar']['errors']['google']
    else:
        assert logged == [], "a provider's failure is not a fault to log"


def test_the_calendars_are_read_outside_the_writer_lock(tmp_path, monkeypatch, calendars):
    from connectonion.rem import files
    held = []

    def events(kind, start, end, zone):
        held.append(_locked(files.state_path(tmp_path, 'maintenance.lock')))
        return []

    monkeypatch.setattr(calendar, 'calendar_events', events)
    _round(tmp_path, monkeypatch)
    assert held == [False, False]


def _locked(path):
    """flock is per open file: a second open in this process sees the round's hold."""
    import fcntl
    with open(path, 'a+') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False


def test_a_cap_that_skipped_events_is_said_in_words(tmp_path, calendars, monkeypatch):
    answers, _ = calendars
    monkeypatch.setattr(calendar, 'CAP', 3)
    calendar.save_upcoming(tmp_path, NIGHT)  # Google answers its cap of 3, Outlook 2
    read = {row['name']: row for row in calendar.upcoming(tmp_path, [], '')['read']}
    assert read['Google Calendar']['capped'] == 3 and 'capped' not in read['Outlook']
