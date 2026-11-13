"""The owner's next days from his connected calendars, saved by the night run for the reader's Agenda (#2998).

The reader never calls a calendar: opening Agenda must be instant and work
offline, and a calendar login must never start from a page. The night run
reads the next DAYS days from every calendar of each account co can already
read (Google via `co auth google`, Outlook via `co auth microsoft`) and saves
them to `.state/calendar.json`; the reader shows that file. A calendar that
fails one night keeps the events it saved before, with when and why beside
them, so one expired login does not empty the week.

No calendar failure stops the night (the shape of #2986): a provider's own
failure is recorded in words; anything else is a fault in REM, recorded with
its exception's name so the page and `co rem logs` show it, while drafts and
investigations still run.

`calendar_events` is the one place that talks to a provider; tests replace it.
"""

import ssl
from datetime import datetime, timedelta, timezone

from google.auth.exceptions import GoogleAuthError
from httplib2 import HttpLib2Error

from .files import read_json, state_path, write_json

DAYS = 21  # three weeks: the week grid, the next one, and a month view that is not empty past its middle
CAP = 1000  # events per account: paging stops there, so a runaway recurring series cannot fill the file
KINDS = ('google', 'microsoft')
NAMES = {'google': 'Google Calendar', 'microsoft': 'Outlook'}
BUG = 'bug'


def available(kind: str) -> bool:
    """Whether co's saved login can read this calendar, by the same scope test the calendar tool makes; never logs in."""
    from ..provider_credentials import resolve_provider_credentials
    if kind == 'microsoft':
        return 'Calendars' in (resolve_provider_credentials('microsoft').get('SCOPES') or '')
    return bool(resolve_provider_credentials('google').scopes & {'calendar', 'calendar.readonly'})


def _zone_name(zone) -> str:
    return getattr(zone, 'key', 'UTC')


def _google_events(start, end, zone) -> list[dict]:
    from ..useful_tools.google_calendar import GoogleCalendar
    service = GoogleCalendar()._get_service()  # the tool's login and token refresh
    calendars, token = [], None
    while True:
        page = service.calendarList().list(pageToken=token).execute()
        calendars += page.get('items', [])
        token = page.get('nextPageToken')
        if not token:
            break
    events = []
    # The calendars he shows in Google Calendar: his own and the shared ones he ticked, not every subscribed feed.
    for listed in [c for c in calendars if c.get('primary') or c.get('selected')]:
        token = None
        while len(events) < CAP:
            page = service.events().list(calendarId=listed['id'], timeMin=start.isoformat(), timeMax=end.isoformat(),
                                         singleEvents=True, orderBy='startTime', maxResults=250,
                                         timeZone=_zone_name(zone), pageToken=token).execute()
            events += page.get('items', [])
            token = page.get('nextPageToken')
            if not token:
                break
    return events


def _graph_pages(client, endpoint, params, headers) -> list[dict]:
    rows = []
    while endpoint and len(rows) < CAP:
        page = client._request('GET', endpoint, params=params, headers=headers)
        rows += page.get('value', [])
        # The next page is a whole URL with its query already in it.
        endpoint, params = page.get('@odata.nextLink', '').removeprefix(client.GRAPH_API_URL), None
    return rows


def _microsoft_events(start, end, zone) -> list[dict]:
    from ..useful_tools.microsoft_calendar import MicrosoftCalendar
    client = MicrosoftCalendar()
    # Times in the owner's zone: in UTC an all-day event in Sydney starts the afternoon before.
    headers = {'Prefer': f'outlook.timezone="{_zone_name(zone)}"'}
    events = []
    for listed in _graph_pages(client, '/me/calendars', {'$select': 'id,name'}, headers):
        events += _graph_pages(client, f"/me/calendars/{listed['id']}/calendarView", {
            'startDateTime': start.isoformat(), 'endDateTime': end.isoformat(), '$top': 250,
            '$select': 'id,subject,start,end,isAllDay,isCancelled,location,attendees,webLink'}, headers)
    return events


def calendar_events(kind: str, start, end, zone) -> list[dict]:
    """The provider's own event objects between two instants, from every calendar he shows; tests replace this.

    It goes through the co calendar tools for their login and token refresh,
    but asks the API directly: the tools' public methods return text for an
    agent to read, and the reader needs the fields."""
    return (_google_events if kind == 'google' else _microsoft_events)(start, end, zone)


def _graph_moment(value: dict, zone) -> datetime | None:
    """Graph's time has no offset in the string: it is in the zone it names (UTC unless the Prefer was honoured)."""
    text = (value or {}).get('dateTime', '')[:19]
    if not text:
        return None
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc if value.get('timeZone', 'UTC') == 'UTC' else zone)


def _google(item: dict, zone) -> dict:
    start, end = item.get('start', {}), item.get('end', {})
    return {'id': item.get('id', ''), 'title': item.get('summary') or '', 'all_day': 'date' in start,
            'start': start.get('dateTime') or start.get('date', ''), 'end': end.get('dateTime') or end.get('date', ''),
            'location': item.get('location', ''), 'link': item.get('htmlLink', ''),
            'attendees': [a['email'] for a in item.get('attendees', []) if a.get('email') and not a.get('self')],
            'cancelled': item.get('status') == 'cancelled'}


def _microsoft(item: dict, zone) -> dict:
    all_day = bool(item.get('isAllDay'))
    start, end = _graph_moment(item.get('start'), zone), _graph_moment(item.get('end'), zone)
    # An all-day event is the owner's calendar date, whatever zone Graph answered in.
    shown = (lambda moment: moment.astimezone(zone).date().isoformat()) if all_day else (lambda moment: moment.isoformat())
    return {'id': item.get('id', ''), 'title': item.get('subject') or '', 'all_day': all_day,
            'start': shown(start) if start else '', 'end': shown(end) if end else '',
            'location': (item.get('location') or {}).get('displayName', ''), 'link': item.get('webLink', ''),
            'attendees': [a.get('emailAddress', {}).get('address', '') for a in item.get('attendees', [])
                          if a.get('emailAddress', {}).get('address')],
            'cancelled': bool(item.get('isCancelled'))}


def _reason(error: Exception) -> str | None:
    """The provider's failure as one word of fetch_stalls.PHRASES; None for a fault in REM."""
    from .fetch_stalls import failure
    reason = failure(error)
    if reason:
        return reason
    if isinstance(error, GoogleAuthError):
        return 'auth'
    # A reset connection, a TLS failure, httplib2's own errors.
    if isinstance(error, (ConnectionError, ssl.SSLError, HttpLib2Error)):
        return 'network'
    # Any other OS error on the way: the credential file busy under another co, a socket gone.
    return 'unavailable' if isinstance(error, OSError) else None


def _read(kind: str, start, end, zone) -> list[dict] | None:
    """The kind's events in one shape, or None when co cannot read that calendar."""
    if not available(kind):
        return None
    shape = _google if kind == 'google' else _microsoft
    rows = [{**shape(item, zone), 'calendar': kind} for item in calendar_events(kind, start, end, zone)]
    unique = {row['id']: row for row in rows if not row['cancelled'] and row['start']}
    return [{key: value for key, value in row.items() if key != 'cancelled'} for row in unique.values()]


def save_upcoming(root, moment, zone=timezone.utc, *, days: int = DAYS) -> dict:
    """Read every connected calendar's next `days` days into .state/calendar.json; the night run calls this."""
    path = state_path(root, 'calendar.json')
    saved = read_json(path, {})
    stamp = moment.isoformat(timespec='seconds')
    events, errors, read_at = [], {}, {}
    start = moment.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    for kind in KINDS:
        try:
            rows = _read(kind, start, start + timedelta(days=days + 1), zone)
        except Exception as error:  # noqa: BLE001 - no calendar may stop the night; a fault in REM is named, not hidden
            reason = _reason(error)
            errors[kind] = {'reason': reason or BUG, 'at': stamp, **({} if reason else {'error': type(error).__name__})}
            if kind in saved.get('read_at', {}):
                read_at[kind] = saved['read_at'][kind]
                events += [event for event in saved.get('events', []) if event['calendar'] == kind]
            continue
        if rows is not None:
            events += rows
            read_at[kind] = stamp
    events.sort(key=lambda event: event['start'])
    write_json(path, {'saved_at': stamp, 'days': days, 'read_at': read_at, 'errors': errors, 'events': events})
    return {'events': len(events), 'read': sorted(set(read_at) - set(errors)), 'errors': errors}


def _people_by_address(records: list[dict], owner: str) -> dict:
    """Addresses on a person page's own Email and Handles lines; an address quoted elsewhere names someone else."""
    import re
    found = {}
    for record in records:
        if record['category'] != 'people' or record['path'] == owner:
            continue
        for line in re.findall(r'^- (?:Email|Handles):(.*)$', record['text'], re.M):
            for address in re.findall(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', line):
                found.setdefault(address.casefold(), record['path'])
    return found


def upcoming(root, records: list[dict], owner: str) -> dict | None:
    """What the reader's Agenda shows: the saved events, each with the people pages of its attendees.

    None when no night has saved a calendar; `read` and `errors` both empty when
    none is connected. The page says which, instead of an unexplained empty week."""
    from .fetch_stalls import PHRASES
    saved = read_json(state_path(root, 'calendar.json'), None)
    if saved is None:
        return None
    people = _people_by_address(records, owner)
    events = []
    for event in saved.get('events', []):
        pages = list(dict.fromkeys(people[a.casefold()] for a in event.get('attendees', []) if a.casefold() in people))
        events.append({**{key: value for key, value in event.items() if key != 'attendees'},
                       'people': pages, 'guests': len(event.get('attendees', []))})
    errors, read_at = saved.get('errors', {}), saved.get('read_at', {})
    return {'saved_at': saved.get('saved_at', ''),
            'read': [{'name': NAMES[kind], 'at': at} for kind, at in read_at.items() if kind not in errors],
            'errors': [{'name': NAMES[kind], 'at': error['at'], 'read_at': read_at.get(kind, ''),
                        'reason': PHRASES.get(error['reason'], 'a fault in REM'), 'error': error.get('error', '')}
                       for kind, error in errors.items()],
            'events': events}
