"""The owner's next days from his connected calendars, saved by the night run for the reader's Agenda (#2998).

The reader never calls a calendar: opening Agenda must be instant and work
offline, and a calendar login must never start from a page. The night run
reads the next DAYS days from each calendar co can already read (Google via
`co auth google`, Outlook via `co auth microsoft`) and saves them to
`.state/calendar.json`; the reader shows that file. A calendar that fails one
night keeps the events it saved before, with the reason beside them, so one
expired login does not empty the week.

`calendar_events` is the one place that talks to a provider; tests replace it.
"""

import os
import re
from datetime import timedelta

from google.auth.exceptions import GoogleAuthError
from googleapiclient.errors import HttpError
from httplib2 import HttpLib2Error
from httpx import RequestError

from ..provider_credentials import ProviderCredentialError
from .files import read_json, state_path, write_json

DAYS = 21  # three weeks: the week grid, the next one, and a month view that is not empty past its middle
MAX_EVENTS = 250
KINDS = ('google', 'microsoft')
NAMES = {'google': 'Google Calendar', 'microsoft': 'Outlook'}
FAILURES = (HttpError, GoogleAuthError, HttpLib2Error, RequestError, ProviderCredentialError, ValueError)
EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')


def available(kind: str) -> bool:
    """Whether co's existing login can read this calendar; never starts a login."""
    if kind == 'microsoft':
        scopes = os.getenv('MICROSOFT_SCOPES', '')
        return any(scope.startswith('Calendars.') for scope in scopes.replace(',', ' ').split())
    from ..useful_tools.google_scopes import granted_scopes
    try:
        return bool(granted_scopes() & {'calendar', 'calendar.readonly'})
    except ProviderCredentialError:  # no Google record at all: not connected, not a failure
        return False


def calendar_events(kind: str, start, end) -> list[dict]:
    """The provider's own event objects between two UTC instants; tests replace this.

    It goes through the co calendar tools for their login and token refresh,
    but asks the API directly: the tools' public methods return text for an
    agent to read, and the reader needs the fields.
    """
    stamp = lambda moment: moment.strftime('%Y-%m-%dT%H:%M:%SZ')  # noqa: E731
    if kind == 'google':
        from ..useful_tools.google_calendar import GoogleCalendar
        service = GoogleCalendar()._get_service()
        return service.events().list(calendarId='primary', timeMin=stamp(start), timeMax=stamp(end),
                                     maxResults=MAX_EVENTS, singleEvents=True, orderBy='startTime').execute().get('items', [])
    from ..useful_tools.microsoft_calendar import MicrosoftCalendar
    result = MicrosoftCalendar()._request('GET', '/me/calendar/calendarView', params={
        'startDateTime': stamp(start), 'endDateTime': stamp(end), '$top': MAX_EVENTS, '$orderby': 'start/dateTime',
        '$select': 'id,subject,start,end,isAllDay,isCancelled,location,attendees,webLink,onlineMeetingUrl'})
    return result.get('value', [])


def _graph_time(value: dict) -> str:
    """Graph answers in UTC without saying so in the string ("2026-11-14T03:00:00.0000000")."""
    text = (value or {}).get('dateTime', '')[:19]
    return text + 'Z' if text and (value or {}).get('timeZone', 'UTC') == 'UTC' else text


def _google(item: dict) -> dict:
    start, end = item.get('start', {}), item.get('end', {})
    return {'id': item.get('id', ''), 'title': item.get('summary') or '', 'all_day': 'date' in start,
            'start': start.get('dateTime') or start.get('date', ''), 'end': end.get('dateTime') or end.get('date', ''),
            'location': item.get('location', ''), 'link': item.get('htmlLink', ''),
            'attendees': [a['email'] for a in item.get('attendees', []) if a.get('email') and not a.get('self')],
            'cancelled': item.get('status') == 'cancelled'}


def _microsoft(item: dict) -> dict:
    all_day = bool(item.get('isAllDay'))
    start, end = _graph_time(item.get('start')), _graph_time(item.get('end'))
    return {'id': item.get('id', ''), 'title': item.get('subject') or '', 'all_day': all_day,
            # An all-day event is a date, not midnight UTC, or it lands on the wrong day east of Greenwich.
            'start': start[:10] if all_day else start, 'end': end[:10] if all_day else end,
            'location': (item.get('location') or {}).get('displayName', ''), 'link': item.get('webLink', ''),
            'attendees': [a.get('emailAddress', {}).get('address', '') for a in item.get('attendees', [])
                          if a.get('emailAddress', {}).get('address')],
            'cancelled': bool(item.get('isCancelled'))}


def _reason(error: Exception) -> str:
    """A short plain reason for the reader; never the provider's own text, which can carry tenant details."""
    if isinstance(error, ProviderCredentialError):
        return 'authorization expired' if error.code == 'reauth_required' else 'not allowed' if error.code == 'permission_denied' else 'unavailable'
    if isinstance(error, ValueError):
        return 'not connected for calendar'
    return 'unavailable'


def save_upcoming(root, moment, *, days: int = DAYS) -> dict:
    """Read every connected calendar's next `days` days into .state/calendar.json; the night run calls this."""
    path = state_path(root, 'calendar.json')
    saved = read_json(path, {})
    earlier = {}
    for event in saved.get('events', []):
        earlier.setdefault(event['calendar'], []).append(event)
    events, errors, read = [], {}, []
    start = moment.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    for kind in KINDS:
        if not available(kind):
            continue
        try:
            items = calendar_events(kind, start, start + timedelta(days=days + 1))
        except FAILURES as error:
            errors[kind] = _reason(error)
            events += earlier.get(kind, [])
            continue
        shape = _google if kind == 'google' else _microsoft
        events += [{**row, 'calendar': kind} for row in map(shape, items) if not row['cancelled'] and row['start']]
        read.append(kind)
    for event in events:
        event.pop('cancelled', None)
    events.sort(key=lambda event: event['start'])
    value = {'saved_at': moment.isoformat(timespec='seconds'), 'days': days, 'read': read, 'errors': errors, 'events': events}
    write_json(path, value)
    return {'events': len(events), 'read': read, 'errors': errors}


def _people_by_address(records: list[dict], owner: str) -> dict:
    """Addresses on a person page's own Email and Handles lines; an address quoted elsewhere names someone else."""
    found = {}
    for record in records:
        if record['category'] != 'people' or record['path'] == owner:
            continue
        for line in re.findall(r'^- (?:Email|Handles):(.*)$', record['text'], re.M):
            for address in EMAIL.findall(line):
                found.setdefault(address.casefold(), record['path'])
    return found


def upcoming(root, records: list[dict], owner: str) -> dict | None:
    """What the reader's Agenda shows: the saved events, each with the people pages of its attendees.

    None when no night has saved a calendar, so the page can say that instead of
    showing an empty week as if the owner had nothing on."""
    saved = read_json(state_path(root, 'calendar.json'), None)
    if saved is None:
        return None
    people = _people_by_address(records, owner)
    events = []
    for event in saved.get('events', []):
        pages = list(dict.fromkeys(people[a.casefold()] for a in event.get('attendees', []) if a.casefold() in people))
        events.append({**{key: value for key, value in event.items() if key != 'attendees'},
                       'people': pages, 'guests': len(event.get('attendees', []))})
    return {'saved_at': saved.get('saved_at', ''), 'read': [NAMES[kind] for kind in saved.get('read', [])],
            'errors': {NAMES[kind]: reason for kind, reason in saved.get('errors', {}).items()}, 'events': events}
