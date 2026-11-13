"""Agenda shows the owner's next days from his connected calendars (#2998, asked in #2841).

Owner, 2026-11-13: «我需要快速看到我最近日历上有什么事件之类的，但完全没有啊！» The night run saves the
next three weeks from each calendar co can already read into .state/calendar.json; the reader shows
that file. The calendars here are fakes in each provider's own shape: no test reaches a real one.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from connectonion.provider_credentials import ProviderCredentialError
from connectonion.rem import calendar
from connectonion.rem.files import Notebook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))

NIGHT = datetime(2026, 10, 1, 2, 30, tzinfo=timezone.utc)

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

    def events(kind, start, end):
        asked.append((kind, start, end))
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
    assert result == {'events': 4, 'read': ['google', 'microsoft'], 'errors': {}}
    # From the start of yesterday (an event that began last night is still "now") through three weeks.
    assert [(kind, start.isoformat(), (end - start).days) for kind, start, end in asked] == [
        ('google', '2026-09-30T00:00:00+00:00', 22), ('microsoft', '2026-09-30T00:00:00+00:00', 22)]
    saved = _saved(tmp_path)
    assert saved['saved_at'] == '2026-10-01T02:30:00+00:00' and saved['errors'] == {}
    by_id = {event['id']: event for event in saved['events']}
    assert set(by_id) == {'g1', 'g2', 'o1', 'o2'}, 'a cancelled event is not on the calendar'
    assert by_id['g1'] == {'id': 'g1', 'title': 'Pilot renewal call with Fernhill', 'all_day': False,
                           'start': '2026-10-02T09:30:00+13:00', 'end': '2026-10-02T10:00:00+13:00',
                           'location': 'Video call', 'link': 'https://calendar.example/g1',
                           'attendees': ['Mara@Fernhill.example'], 'calendar': 'google'}
    assert by_id['g2']['all_day'] and by_id['g2']['start'] == '2026-10-05'
    # Graph's UTC has no Z; an all-day Outlook event is a date, never midnight UTC.
    assert by_id['o1']['start'] == '2026-10-03T01:00:00Z' and by_id['o1']['location'] == 'Harbour office'
    assert by_id['o2']['all_day'] and (by_id['o2']['start'], by_id['o2']['end']) == ('2026-10-04', '2026-10-05')
    assert [event['start'][:10] for event in saved['events']] == sorted(event['start'][:10] for event in saved['events'])


def test_a_calendar_that_fails_keeps_what_it_saved_before_and_says_why(tmp_path, calendars):
    answers, _ = calendars
    calendar.save_upcoming(tmp_path, NIGHT)
    answers['microsoft'] = ProviderCredentialError('reauth_required', 'Microsoft authorization expired.', 'co auth microsoft')
    answers['google'] = [GOOGLE[1]]
    result = calendar.save_upcoming(tmp_path, NIGHT)
    assert result['read'] == ['google'] and result['errors'] == {'microsoft': 'authorization expired'}
    assert sorted(event['id'] for event in _saved(tmp_path)['events']) == ['g2', 'o1', 'o2']


def test_a_calendar_co_cannot_read_is_never_asked(tmp_path, monkeypatch):
    monkeypatch.setattr(calendar, 'available', lambda kind: False)
    monkeypatch.setattr(calendar, 'calendar_events', lambda *args: pytest.fail('asked a calendar that is not connected'))
    assert calendar.save_upcoming(tmp_path, NIGHT) == {'events': 0, 'read': [], 'errors': {}}


def test_without_a_login_no_calendar_is_available(monkeypatch):
    # The test HOME has no co keys at all: neither calendar may count as connected, and nothing starts a login.
    monkeypatch.delenv('MICROSOFT_SCOPES', raising=False)
    assert not calendar.available('google') and not calendar.available('microsoft')
    monkeypatch.setenv('MICROSOFT_SCOPES', 'Mail.Read Calendars.Read offline_access')
    assert calendar.available('microsoft')


def test_the_reader_gets_each_event_with_its_peoples_pages_and_none_before_a_night(tmp_path, calendars):
    records = [{'path': 'people/mara.md', 'category': 'people',
                'text': '# Mara\n\n## Facts\n- Email: mara@fernhill.example (work) [1]\n'},
               {'path': 'people/tomas.md', 'category': 'people',
                'text': '# Tomás\n\nHe forwarded ines@example.test the invoice [2].\n'},
               {'path': 'people/avery.md', 'category': 'people', 'text': '# Avery\n- Email: avery@example.test\n'}]
    assert calendar.upcoming(tmp_path, records, 'people/avery.md') is None
    calendar.save_upcoming(tmp_path, NIGHT)
    shown = calendar.upcoming(tmp_path, records, 'people/avery.md')
    assert shown['read'] == ['Google Calendar', 'Outlook'] and shown['errors'] == {}
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


def test_the_nightly_round_saves_the_calendars(tmp_path, monkeypatch, calendars):
    from connectonion.rem.config import prepare
    from connectonion.rem.daily import run_daily
    prepare(tmp_path)
    Notebook(tmp_path).write('projects/a.md', '# A\nUnknown\n')
    monkeypatch.setattr('connectonion.rem.daily.subscriptions', lambda root: {})
    run_daily(tmp_path, maintain=lambda root: {'outcome': 'no_change'},
              investigate_one=lambda *args, **kw: {'changed': [], 'usage': {}})
    assert len(_saved(tmp_path)['events']) == 4
