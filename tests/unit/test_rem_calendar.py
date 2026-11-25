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


# What each account listed: how many calendars were his to read, and the others by the access they were shared with.
LISTED = {'google': {'read': 1, 'left_out': {'freeBusyReader': 2, 'reader': 1}}, 'microsoft': {'read': 2, 'left_out': {}}}


@pytest.fixture
def calendars(monkeypatch):
    """Both calendars connected; `answers[kind]` is a list of events or an exception to raise."""
    answers, asked = {'google': GOOGLE, 'microsoft': OUTLOOK}, []
    monkeypatch.setattr(calendar, 'available', lambda kind: kind in answers)

    def events(kind, start, end, zone):
        asked.append((kind, start, end, zone))
        if isinstance(answers[kind], Exception):
            raise answers[kind]
        return answers[kind], LISTED[kind]

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
                           'attendees': ['Mara@Fernhill.example'], 'label': '', 'calendar_name': '', 'meet': None, 'organizer': '', 'notes': '', 'calendar': 'google'}
    assert by_id['g2']['all_day'] and by_id['g2']['start'] == '2026-10-05'
    # Graph's UTC has no offset in the string; it is written with one.
    assert by_id['o1']['start'] == '2026-10-03T01:00:00+00:00' and by_id['o1']['location'] == 'Harbour office'
    assert by_id['o2']['all_day'] and (by_id['o2']['start'], by_id['o2']['end']) == ('2026-10-04', '2026-10-05')
    # #3087: which calendars were read and which were left out, as counts by access; never another person's name.
    assert saved['calendars'] == LISTED
    read = {row['name']: row for row in calendar.upcoming(tmp_path, [], '')['read']}
    assert (read['Google Calendar']['calendars'], read['Google Calendar']['left_out']) == (1, {'freeBusyReader': 2, 'reader': 1})
    assert (read['Outlook']['calendars'], read['Outlook']['left_out']) == (2, {})


def test_events_saved_from_a_shared_calendar_are_gone_after_the_next_read(tmp_path, calendars):
    """#3087: 15 of the owner's 20 saved events were other people's untitled Busy entries. The next read drops them."""
    answers, _ = calendars
    answers.pop('microsoft')
    answers['google'] = [GOOGLE[0], _timed('theirs', visibility='private', _calendar=SHARED)]
    calendar.save_upcoming(tmp_path, NIGHT)
    assert {event['id'] for event in _saved(tmp_path)['events']} == {'g1', 'theirs'}
    answers['google'] = [GOOGLE[0]]  # what _google_events returns once it reads only his own calendars
    calendar.save_upcoming(tmp_path, NIGHT + timedelta(days=1))
    assert [event['id'] for event in _saved(tmp_path)['events']] == ['g1']


def _google_saved(tmp_path, calendars, items):
    answers, _ = calendars
    answers.pop('microsoft')
    answers['google'] = items
    calendar.save_upcoming(tmp_path, NIGHT)
    return {event['id']: event for event in _saved(tmp_path)['events']}


def _timed(id, **extra):
    return {'id': id, 'start': {'dateTime': '2026-10-02T09:00:00+13:00'}, 'end': {'dateTime': '2026-10-02T10:00:00+13:00'}} | extra


SHARED = {'name': 'Ines Calder', 'access': 'freeBusyReader'}
OWN = {'name': 'Avery', 'access': 'owner'}


def test_where_he_works_that_day_is_not_an_event(tmp_path, calendars):
    """Half the owner's saved events had no title. A working location is Google's own entry, not something he attends."""
    by_id = _google_saved(tmp_path, calendars, [
        _timed('home', eventType='workingLocation', _calendar=OWN),
        {'id': 'office', 'summary': 'Office', 'eventType': 'workingLocation', 'start': {'date': '2026-10-02'},
         'end': {'date': '2026-10-03'}, '_calendar': OWN},
        _timed('call', summary='Pilot call', eventType='default', _calendar=OWN)])
    assert set(by_id) == {'call'} and by_id['call']['label'] == ''


@pytest.mark.parametrize('kind, words', [('focusTime', 'Focus time'), ('outOfOffice', 'Out of office')])
def test_focus_time_and_out_of_office_are_named_by_their_type(tmp_path, calendars, kind, words):
    by_id = _google_saved(tmp_path, calendars, [_timed('untitled', eventType=kind, _calendar=OWN),
                                                _timed('titled', summary='Deep work', eventType=kind, _calendar=OWN)])
    assert (by_id['untitled']['title'], by_id['untitled']['label']) == ('', words)
    assert (by_id['titled']['title'], by_id['titled']['label']) == ('Deep work', words)


def test_an_entry_from_a_calendar_shared_without_details_is_busy_with_that_calendars_name(tmp_path, calendars):
    by_id = _google_saved(tmp_path, calendars, [
        _timed('freebusy', visibility='private', _calendar=SHARED),
        _timed('bare', _calendar=SHARED),
        _timed('private', visibility='private', _calendar={'name': 'Fernhill team', 'access': 'reader'}),
        _timed('own', _calendar=OWN),
        _timed('own-private', visibility='private', _calendar=OWN)])
    assert [(by_id[key]['label'], by_id[key]['calendar_name']) for key in ('freebusy', 'bare', 'private')] == [
        ('Busy', 'Ines Calder'), ('Busy', 'Ines Calder'), ('Busy', 'Fernhill team')]
    # His own event that he left untitled is not hidden from him: it stays "No title" on the page.
    assert by_id['own']['label'] == '' and by_id['own-private']['label'] == ''
    assert all(event['title'] == '' for event in by_id.values())


@pytest.mark.parametrize('order', [(0, 1), (1, 0)])
def test_a_meeting_on_his_calendar_and_on_a_shared_one_keeps_its_title(tmp_path, calendars, order):
    """Google gives one meeting the same id on every calendar it is on; the colleague's free/busy copy has no title."""
    copies = [_timed('same', summary='Pilot call', _calendar=OWN), _timed('same', visibility='private', _calendar=SHARED)]
    by_id = _google_saved(tmp_path, calendars, [copies[n] for n in order])
    assert (by_id['same']['title'], by_id['same']['label'], by_id['same']['calendar_name']) == ('Pilot call', '', 'Avery')


def test_a_cancelled_instance_is_left_out_even_without_a_title(tmp_path, calendars):
    by_id = _google_saved(tmp_path, calendars, [_timed('gone', status='cancelled', _calendar=OWN), _timed('kept', summary='Kept')])
    assert set(by_id) == {'kept'}


class _FakeGoogle:
    """Google's client in its own shape: the listed calendars, each read one asked for its events; records every request."""

    def __init__(self):
        self.asked = []

    def calendarList(self):
        return self

    def events(self):
        return self

    def list(self, **params):
        self.asked.append(params)
        return self

    def execute(self):
        params = self.asked[-1]
        if 'calendarId' not in params:
            return {'items': [{'id': 'avery@example.test', 'summary': 'avery@example.test', 'summaryOverride': 'Avery',
                               'primary': True, 'accessRole': 'owner'},
                              {'id': 'ines@example.test', 'summary': 'Ines Calder', 'selected': True, 'accessRole': 'freeBusyReader'},
                              {'id': 'tomas@example.test', 'summary': 'Tomas Reed', 'selected': True, 'accessRole': 'freeBusyReader'},
                              {'id': 'fernhill@example.test', 'summary': 'Fernhill team', 'selected': True, 'accessRole': 'reader'},
                              {'id': 'feed@example.test', 'summary': 'Unticked feed', 'accessRole': 'reader'},
                              {'id': 'crew@example.test', 'summary': 'Harbour crew', 'selected': True, 'accessRole': 'writer'},
                              {'id': 'old@example.test', 'summary': 'Old plans', 'accessRole': 'owner'}]}
        return {'items': [_timed('from-' + params['calendarId'])]}


def test_google_reads_only_his_own_ticked_calendars_and_counts_the_rest_by_access(monkeypatch):
    """#3087: his own calendar and one he can write to are read; free/busy and read-only shares never are."""
    from connectonion.useful_tools.google_calendar import GoogleCalendar
    service = _FakeGoogle()
    monkeypatch.setattr(GoogleCalendar, '__init__', lambda self: None)
    monkeypatch.setattr(GoogleCalendar, '_get_service', lambda self: service)
    events, listed = calendar._google_events(NIGHT, NIGHT + timedelta(days=1), SYDNEY)
    assert [(event['id'], event['_calendar']) for event in events] == [
        ('from-avery@example.test', OWN), ('from-crew@example.test', {'name': 'Harbour crew', 'access': 'writer'})]
    assert listed == {'read': 2, 'left_out': {'freeBusyReader': 2, 'reader': 2, 'unticked': 1}}
    # A `fields` mask that left out `summary` would empty every title; none is sent, so Google returns the whole event.
    asked = [params for params in service.asked if 'calendarId' in params]
    assert all('summary' in params.get('fields', 'summary') for params in asked) and len(asked) == 2
    assert [calendar._google(event, SYDNEY)['label'] for event in events] == ['', '']


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
    assert saved['calendars'] == LISTED, 'the calendar that failed keeps the counts of the night its events are from'
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


def test_the_real_outlook_tool_reads_every_calendar_he_can_write_and_every_page_in_the_owners_zone(monkeypatch):
    from connectonion.useful_tools import microsoft_calendar
    monkeypatch.setenv('MICROSOFT_SCOPES', 'Calendars.Read')
    monkeypatch.setenv('MICROSOFT_ACCESS_TOKEN', 'fake-token')
    monkeypatch.setenv('MICROSOFT_TOKEN_EXPIRES_AT', (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    graph, seen = 'https://graph.microsoft.com/v1.0', []

    def answer(request):
        seen.append((request.url.path, request.headers.get('prefer'), request.headers.get('authorization')))
        if request.url.path == '/v1.0/me/calendars':
            assert 'canEdit' in request.url.params['$select']
            # Graph: canEdit is true for a calendar he created and for one shared with write access.
            return httpx.Response(200, json={'value': [{'id': 'work', 'canEdit': True}, {'id': 'family', 'canEdit': True},
                                                       {'id': 'ines', 'canEdit': False}, {'id': 'holidays', 'canEdit': False}]})
        if request.url.path.endswith('/work/calendarView') and 'skip' not in str(request.url):
            assert request.url.params['startDateTime'].startswith('2026-09-30T00:00:00')
            return httpx.Response(200, json={'value': [OUTLOOK[0]], '@odata.nextLink': graph + '/me/calendars/work/calendarView?skip=1'})
        if request.url.path.endswith('/work/calendarView'):
            return httpx.Response(200, json={'value': [OUTLOOK[1]]})
        return httpx.Response(200, json={'value': [{**OUTLOOK[0], 'id': 'f1', 'subject': 'School pickup'}]})

    client = httpx.Client(transport=httpx.MockTransport(answer))
    monkeypatch.setattr(microsoft_calendar.httpx, 'request', client.request)
    start = datetime(2026, 9, 30, tzinfo=SYDNEY)
    items, listed = calendar.calendar_events('microsoft', start, start + timedelta(days=22), SYDNEY)
    assert listed == {'read': 2, 'left_out': {'reader': 2}}
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
        page({'items': [{'id': 'primary-id', 'primary': True, 'accessRole': 'owner'}], 'nextPageToken': 'p2'}),
        page({'items': [{'id': 'team-id', 'selected': True, 'accessRole': 'writer'}, {'id': 'holidays-id', 'accessRole': 'reader'}]}),
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
    items, listed = calendar.calendar_events('google', start, start + timedelta(days=22), timezone.utc)
    assert listed == {'read': 2, 'left_out': {'reader': 1}}
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
    assert [(row['name'], row['at']) for row in shown['read']] == [('Google Calendar', NIGHT.isoformat()), ('Outlook', NIGHT.isoformat())]
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


def _round(root, monkeypatch, *, scheduled=False):
    from connectonion.rem.config import prepare
    from connectonion.rem.daily import run_daily
    prepare(root)
    Notebook(root).write('projects/a.md', '# A\nUnknown\n')
    monkeypatch.setattr('connectonion.rem.daily.subscriptions', lambda root: {})
    drafted = []
    monkeypatch.setattr('connectonion.rem.daily._draft_replies', lambda *args: drafted.append(True))
    result = run_daily(root, scheduled=scheduled, maintain=lambda root, **kw: {'outcome': 'no_change'},
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
        return [], {'read': 1, 'left_out': {}}

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


@pytest.mark.parametrize('path', ['scheduled sync', 'exec round', 'codex_exec', 'native round'])
@pytest.mark.parametrize('fault', [None, TimeoutError('offline'), AttributeError('broken calendar adapter')])
def test_every_background_path_saves_calendar_once_outside_writer_lock(tmp_path, monkeypatch, calendars, path, fault):
    from subprocess import CompletedProcess
    from connectonion.rem import codex_exec, depth, native, runner, schedule, service
    from connectonion.rem.config import prepare
    from connectonion.rem.files import read_json, state_path, write_json

    prepare(tmp_path)
    answers, asked = calendars
    if fault:
        answers.update(google=fault, microsoft=fault)
    saved, original = [], calendar.save_upcoming

    def save(root, moment, zone):
        assert not _locked(state_path(root, 'maintenance.lock'))
        saved.append(moment)
        return original(root, moment, zone)

    monkeypatch.setattr(calendar, 'save_upcoming', save)
    monkeypatch.setattr(depth, 'slot', lambda *a, **kw: {'rounds': [], 'stopped': ''})
    monkeypatch.setattr('connectonion.rem.codex_schedule.CodexNative.recent_desktop_fire', lambda *a: False)
    cursor = {'started_at': NIGHT.isoformat(), 'run': {'id': 'fixture'}, 'done': False}
    tasks = iter([{'outcome': 'task', 'id': 'fixture', 'stage': 'abstract',
                   'instructions': 'fixture', 'material': str(tmp_path)},
                  {'outcome': 'done', 'reason': 'round done'}])

    def next_task(root, **options):
        task = next(tasks)
        current = read_json(state_path(root, 'round.json'), cursor)
        write_json(state_path(root, 'round.json'), {**current, 'done': task['outcome'] == 'done'})
        return task

    monkeypatch.setattr(native, '_next_task', next_task)
    monkeypatch.setattr(native, 'submit', lambda *a, **kw: {'outcome': 'accepted'})
    monkeypatch.setattr(runner, 'run_task', lambda *a, **kw: {})
    if path == 'scheduled sync':
        result, _ = _round(tmp_path, monkeypatch, scheduled=True)
        report = result['maintenance']['calendar']
    elif path == 'exec round':
        result = schedule.exec_round(tmp_path, scheduled=False)
        report = result.get('calendar')
        assert result['outcome'] == 'done'
    elif path == 'codex_exec':
        monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
        monkeypatch.setattr(codex_exec, '_reap_orphan_maintenance', lambda *a: [])

        def run(command, **options):
            native.next_task(tmp_path)
            native.next_task(tmp_path)
            return CompletedProcess(command, 0)

        assert codex_exec.run_turn(tmp_path, run=run) == 'completed'
        report = read_json(state_path(tmp_path, 'last-turn.json'), {}).get('calendar')
    else:
        native.next_task(tmp_path)
        native.next_task(tmp_path)
        report = read_json(state_path(tmp_path, 'round.json'), {}).get('calendar')
    assert len(saved) == 1, f'{path} must save once per round'
    plan = read_json(state_path(tmp_path, 'day-plan.json'), None)
    assert plan is not None, f'{path} must save the day plan immediately after the calendar'
    assert plan['saved_at'] == saved[0].isoformat(timespec='seconds')
    assert len(plan['days']) == 2
    assert 'day_plan' in report
    assert len(asked) == 2, 'each connected provider is asked once'
    assert report['events'] == (0 if fault else 4)
    faults = [run for run in service.run_logs(tmp_path) if run.get('phase') == 'calendar']
    assert len(faults) == (2 if isinstance(fault, AttributeError) else 0)
    assert 'traceback' not in json.dumps(report)


@pytest.mark.parametrize('saved, expected', [
    (None, 'Calendars: never read'),
    ({'read_at': {}, 'events': [], 'errors': {}}, 'Calendars: no calendar is connected'),
    ({'read_at': {}, 'events': [], 'errors': {'google': {'reason': 'timeout'}}}, 'Calendars: never read'),
    ({'read_at': {'google': '2026-10-01T23:30:00+00:00'}, 'events': [{}], 'errors': {}},
     'Calendars: last read 2026-10-02; 1 event saved'),
    ({'read_at': {'google': '2026-10-01T23:30:00+00:00'}, 'events': [{}, {}], 'errors': {}},
     'Calendars: last read 2026-10-02; 2 events saved'),
    ({'read_at': {'google': '2026-10-01T23:30:00+00:00'}, 'events': [], 'errors': {}},
     'Calendars: last read 2026-10-02; 0 events saved'),
])
def test_calendar_status_one_line_from_saved_state_without_network(tmp_path, monkeypatch, saved, expected):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.rem import service
    from connectonion.rem.config import prepare, set_config
    from connectonion.rem.files import state_path, write_json
    prepare(tmp_path)
    set_config(tmp_path, ['schedule.timezone', 'Australia/Sydney'])
    if saved is not None:
        write_json(state_path(tmp_path, 'calendar.json'), saved)
    monkeypatch.setattr(calendar, 'available', lambda *a: pytest.fail('status checked a live account'))
    monkeypatch.setattr(calendar, 'calendar_events', lambda *a: pytest.fail('status read calendar'))
    result = CliRunner().invoke(app, ['rem', '--root', str(tmp_path), 'status'])
    assert result.exit_code == 0, result.output
    assert [line.strip() for line in result.stdout.splitlines() if line.strip().startswith('Calendars:')] == [expected]
    assert service.status(tmp_path)['calendar']['text'] == expected


def test_calendar_snapshot_save_fault_does_not_fail_exec_or_lose_its_traceback(tmp_path, monkeypatch):
    from connectonion.rem import native, schedule, service
    from connectonion.rem.config import prepare
    from connectonion.rem.files import state_path, write_json
    prepare(tmp_path)
    write_json(state_path(tmp_path, 'round.json'), {'started_at': NIGHT.isoformat(), 'done': True})
    calls = []

    def broken_save(*args):
        calls.append(True)
        raise OSError('fixture snapshot write failed')

    monkeypatch.setattr(calendar, 'save_upcoming', broken_save)
    monkeypatch.setattr(native, 'next_task', lambda *a, **kw: {'outcome': 'done', 'reason': 'daily cap reached'})
    result = schedule.exec_round(tmp_path, scheduled=False)
    assert result['outcome'] == 'done' and result['calendar']['errors']['rem']['error'] == 'OSError'
    assert 'traceback' not in json.dumps(result)
    [logged] = [run for run in service.run_logs(tmp_path) if run.get('phase') == 'calendar']
    assert logged['outcome'] == 'failed' and 'fixture snapshot write failed' in logged['error']
    assert 'Traceback' in logged['error']
    schedule.exec_round(tmp_path, scheduled=False)
    assert calls == [True], 'a failed read is still attempted only once in this round'


def test_codex_exec_saves_calendar_when_child_only_writes_round_state(tmp_path, monkeypatch, calendars):
    from subprocess import CompletedProcess
    from connectonion.rem import codex_exec, depth
    from connectonion.rem.config import prepare
    from connectonion.rem.files import read_json, state_path, write_json
    prepare(tmp_path)
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_exec, '_reap_orphan_maintenance', lambda *a: [])
    monkeypatch.setattr('connectonion.rem.codex_schedule.CodexNative.recent_desktop_fire', lambda *a: False)
    monkeypatch.setattr(depth, 'slot', lambda *a, **kw: {'rounds': [], 'stopped': ''})

    def run(command, **options):
        write_json(state_path(tmp_path, 'round.json'), {'started_at': NIGHT.isoformat(), 'done': True})
        return CompletedProcess(command, 0)

    assert codex_exec.run_turn(tmp_path, run=run) == 'completed'
    assert len(calendars[1]) == 2
    assert read_json(state_path(tmp_path, 'last-turn.json'), {})['calendar']['events'] == 4
    assert codex_exec.run_turn(tmp_path, run=lambda *a, **kw: CompletedProcess(a, 0)) == 'completed'
    assert len(calendars[1]) == 2, 'an unchanged finished round is not read again'


def test_an_event_brings_its_meeting_link_organiser_and_notes():
    """#3135 (owner, 2026-11-19): the detail said only 'Open in Outlook'; a Meet link should be named plainly."""
    google = calendar._google({'id': 'g1', 'summary': 'Design review', 'start': {'dateTime': '2026-11-20T10:00:00+11:00'},
                               'end': {'dateTime': '2026-11-20T10:30:00+11:00'}, 'htmlLink': 'https://calendar.google.com/x',
                               'hangoutLink': 'https://meet.google.com/abc-defg-hij', 'organizer': {'email': 'ana@example.test', 'displayName': 'Ana'},
                               'description': '<p>Agenda:<br>1. Header</p>'}, SYDNEY)
    assert google['meet'] == {'url': 'https://meet.google.com/abc-defg-hij', 'service': 'Google Meet'}
    assert google['organizer'] == 'Ana' and google['notes'] == 'Agenda:\n1. Header'
    outlook = calendar._microsoft({'id': 'o1', 'subject': 'Sync', 'start': {'dateTime': '2026-11-20T10:00:00', 'timeZone': 'UTC'},
                                   'end': {'dateTime': '2026-11-20T10:30:00', 'timeZone': 'UTC'}, 'webLink': 'https://outlook.office.com/x',
                                   'onlineMeeting': {'joinUrl': 'https://teams.microsoft.com/l/meetup-join/1'},
                                   'organizer': {'emailAddress': {'name': 'Bo', 'address': 'bo@example.test'}},
                                   'bodyPreview': 'Please read the doc first.'}, SYDNEY)
    assert outlook['meet'] == {'url': 'https://teams.microsoft.com/l/meetup-join/1', 'service': 'Microsoft Teams'}
    assert outlook['organizer'] == 'Bo' and outlook['notes'] == 'Please read the doc first.'
    zoom = calendar._microsoft({'id': 'o2', 'subject': 'Call', 'start': {}, 'end': {},
                                'location': {'displayName': 'https://us02web.zoom.us/j/123?pwd=x'}}, SYDNEY)
    assert zoom['meet'] == {'url': 'https://us02web.zoom.us/j/123?pwd=x', 'service': 'Zoom'}
    plain = calendar._microsoft({'id': 'o3', 'subject': 'Lunch', 'start': {}, 'end': {}, 'location': {'displayName': 'Cafe'}}, SYDNEY)
    assert plain['meet'] is None and plain['notes'] == '' and plain['organizer'] == ''


def test_scheduling_window_comes_from_complete_owner_read_and_expires_on_partial_read(tmp_path, calendars):
    answers, asked = calendars
    calendar.save_upcoming(tmp_path, NIGHT, SYDNEY, days=7)
    _, start, end, _ = asked[0]
    assert calendar.upcoming(tmp_path, [], '')['window'] == {
        'start': start.isoformat(), 'end': end.isoformat(), 'timezone': 'Australia/Sydney'}
    assert start.utcoffset() != end.utcoffset()  # providers were queried across a DST change
    answers['microsoft'] = TimeoutError()
    calendar.save_upcoming(tmp_path, NIGHT + timedelta(days=1), SYDNEY)
    assert 'window' not in calendar.upcoming(tmp_path, [], '')
    answers['microsoft'] = []
    answers['google'] = [{'id': 'unknown time', 'end': {'date': '2026-10-05'}}]
    calendar.save_upcoming(tmp_path, NIGHT, SYDNEY)
    assert 'window' not in calendar.upcoming(tmp_path, [], '')


def test_reply_window_requires_all_own_calendars_and_all_pages(tmp_path, calendars, monkeypatch):
    answers, _ = calendars
    answers.pop('microsoft')
    monkeypatch.setitem(LISTED['google']['left_out'], 'unticked', 1)
    calendar.save_upcoming(tmp_path, NIGHT)
    assert 'window' not in calendar.upcoming(tmp_path, [], '')
    monkeypatch.delitem(LISTED['google']['left_out'], 'unticked')
    monkeypatch.setattr(calendar, 'CAP', len(GOOGLE))
    calendar.save_upcoming(tmp_path, NIGHT)
    assert 'window' not in calendar.upcoming(tmp_path, [], '')
    answers['google'] = []
    calendar.save_upcoming(tmp_path, NIGHT)
    assert 'window' in calendar.upcoming(tmp_path, [], '')


def test_reply_window_waits_for_previously_read_feed_to_return(tmp_path, calendars):
    answers, _ = calendars
    calendar.save_upcoming(tmp_path, NIGHT)
    del answers['microsoft']
    for day in (1, 2):
        calendar.save_upcoming(tmp_path, NIGHT + timedelta(days=day))
        assert 'window' not in calendar.upcoming(tmp_path, [], '')
    answers['microsoft'] = []
    calendar.save_upcoming(tmp_path, NIGHT + timedelta(days=3))
    assert 'window' in calendar.upcoming(tmp_path, [], '')
