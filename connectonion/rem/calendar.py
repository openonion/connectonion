"""The owner's next days from his connected calendars, saved by the night run for the reader's Agenda (#2998).

The reader never calls a calendar: opening Agenda must be instant and work
offline, and a calendar login must never start from a page. The night run
reads the next DAYS days from the owner's own calendars in each account co
can already read (Google via `co auth google`, Outlook via `co auth microsoft`)
and saves them to `.state/calendar.json`; the reader shows that file. A
calendar someone shared with him as free/busy or read-only is never read
(#3087): 15 of his 20 saved events were other people's untitled Busy entries.
The file records how many calendars were read and how many were left out, by
access, so Agenda can say it in words. A calendar that
fails one night keeps the events it saved before, with when and why beside
them, so one expired login does not empty the week.

No calendar failure stops the night (the shape of #2986): a provider's own
failure is recorded in words; anything else is a fault in REM, recorded with
its exception's name so the page and `co rem logs` show it, while drafts and
investigations still run.

`calendar_events` is the one place that talks to a provider; tests replace it.
"""

import html
import re
import ssl
import traceback
from datetime import datetime, timedelta, timezone

from google.auth.exceptions import GoogleAuthError
from httplib2 import HttpLib2Error

from .files import read_json, state_path, write_json

DAYS = 21  # three weeks: the week grid, the next one, and a month view that is not empty past its middle
CAP = 1000  # events per account: paging stops there, so a runaway recurring series cannot fill the file
KINDS = ('google', 'microsoft')
NAMES = {'google': 'Google Calendar', 'microsoft': 'Outlook'}
BUG = 'bug'
# Google's own entries that are not meetings, in the words the page shows when one has no title.
GOOGLE_TYPES = {'focusTime': 'Focus time', 'outOfOffice': 'Out of office'}


def available(kind: str) -> bool:
    """Whether co's saved login can read this calendar, by the same scope test the calendar tool makes; never logs in."""
    from ..provider_credentials import resolve_provider_credentials
    if kind == 'microsoft':
        return 'Calendars' in (resolve_provider_credentials('microsoft').get('SCOPES') or '')
    return bool(resolve_provider_credentials('google').scopes & {'calendar', 'calendar.readonly'})


def _zone_name(zone) -> str:
    return getattr(zone, 'key', 'UTC')


OWN = ('owner', 'writer')  # Google's accessRole for a calendar that is his, or that he can write to


def _google_left_out(listed: dict) -> str | None:
    """Why a listed Google calendar is not read, as the word calendar.json counts it under; None for one that is.

    Shared without write access is never his schedule; one of his own that he
    unticked in Google Calendar is one he chose not to see."""
    access = listed.get('accessRole', '')
    if access not in OWN:
        return access or 'reader'
    return None if listed.get('primary') or listed.get('selected') else 'unticked'


def _counted(listed: list, left_out) -> tuple[list, dict]:
    """The calendars to read, and {'read': n, 'left_out': {why: n}} for the page's sentence."""
    read, why = [], {}
    for one in listed:
        reason = left_out(one)
        if reason:
            why[reason] = why.get(reason, 0) + 1
        else:
            read.append(one)
    return read, {'read': len(read), 'left_out': why}


def _google_events(start, end, zone) -> tuple[list[dict], dict]:
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
    own, counts = _counted(calendars, _google_left_out)
    for listed in own:
        token = None
        # Each event carries its calendar's name and his access to it.
        shown = {'name': listed.get('summaryOverride') or listed.get('summary', ''), 'access': listed.get('accessRole', '')}
        while len(events) < CAP:
            # No `fields`: the whole event resource comes back, `summary` and `eventType` included.
            page = service.events().list(calendarId=listed['id'], timeMin=start.isoformat(), timeMax=end.isoformat(),
                                         singleEvents=True, orderBy='startTime', maxResults=250,
                                         timeZone=_zone_name(zone), pageToken=token).execute()
            events += [{**item, '_calendar': shown} for item in page.get('items', [])]
            token = page.get('nextPageToken')
            if not token:
                break
    return events, counts


def _graph_pages(client, endpoint, params, headers, limit=CAP) -> list[dict]:
    rows = []
    while endpoint and len(rows) < limit:
        page = client._request('GET', endpoint, params=params, headers=headers)
        rows += page.get('value', [])
        # The next page is a whole URL with its query already in it.
        endpoint, params = page.get('@odata.nextLink', '').removeprefix(client.GRAPH_API_URL), None
    return rows


def _microsoft_events(start, end, zone) -> tuple[list[dict], dict]:
    from ..useful_tools.microsoft_calendar import MicrosoftCalendar
    client = MicrosoftCalendar()
    # Times in the owner's zone: in UTC an all-day event in Sydney starts the afternoon before.
    headers = {'Prefer': f'outlook.timezone="{_zone_name(zone)}"'}
    events = []
    # Graph has no access role. `canEdit` is true for a calendar he created and for one shared with write
    # access, which is Google's owner-or-writer; a calendar shared to read (free/busy included) has it false.
    own, counts = _counted(_graph_pages(client, '/me/calendars', {'$select': 'id,name,canEdit'}, headers),
                           lambda listed: None if listed.get('canEdit') else 'reader')
    for listed in own:
        if len(events) >= CAP:
            break
        events += _graph_pages(client, f"/me/calendars/{listed['id']}/calendarView", {
            'startDateTime': start.isoformat(), 'endDateTime': end.isoformat(), '$top': 250,
            '$select': 'id,subject,start,end,isAllDay,isCancelled,location,attendees,webLink,onlineMeeting,onlineMeetingUrl,organizer,bodyPreview'},
            headers, CAP - len(events))
    return events, counts


def calendar_events(kind: str, start, end, zone) -> tuple[list[dict], dict]:
    """The provider's own event objects between two instants from his own calendars, and the count of
    calendars read and left out ({'read': n, 'left_out': {access: n}}); tests replace this.

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


def _google_label(item: dict) -> str:
    """What an event is when Google sends no title: its type, or Busy when the calendar hides its details.

    A calendar shared as free/busy, or a private event on one he can only read, comes without
    `summary`. His own untitled event stays untitled: owners and writers are sent every title."""
    if item.get('eventType') in GOOGLE_TYPES:
        return GOOGLE_TYPES[item['eventType']]
    access = item.get('_calendar', {}).get('access', '')
    hidden = access == 'freeBusyReader' or item.get('visibility') in ('private', 'confidential')
    return 'Busy' if hidden and access not in ('owner', 'writer') and not item.get('summary') else ''


# A meeting link names its service in the event's detail (#3135: "if it has a Meet link, say Meet").
MEETING_SERVICES = (('meet.google.com', 'Google Meet'), ('teams.microsoft.com', 'Microsoft Teams'), ('teams.live.com', 'Microsoft Teams'),
                    ('zoom.us', 'Zoom'), ('webex.com', 'Webex'))
NOTES_LIMIT = 1200


def _meeting(*texts: str) -> dict | None:
    """The first meeting URL among the event's own link, location and notes, with its service's name."""
    for text in texts:
        for url in re.findall(r'https?://[^\s<>"\')]+', text or ''):
            service = next((name for host, name in MEETING_SERVICES if host in url.split('/')[2]), None)
            if service:
                return {'url': url.rstrip('.,;'), 'service': service}
    return None


def _notes(text: str) -> str:
    """An event's description as plain text: Google sends HTML, Outlook a preview; both trimmed."""
    text = re.sub(r'(?i)<br\s*/?>|</p>|</div>|</li>', '\n', text or '')
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    text = '\n'.join(line.strip() for line in text.splitlines()).strip()
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text[:NOTES_LIMIT] + ('…' if len(text) > NOTES_LIMIT else '')


def _google(item: dict, zone) -> dict:
    start, end = item.get('start', {}), item.get('end', {})
    return {'id': item.get('id', ''), 'title': item.get('summary') or '', 'all_day': 'date' in start,
            'start': start.get('dateTime') or start.get('date', ''), 'end': end.get('dateTime') or end.get('date', ''),
            'location': item.get('location', ''), 'link': item.get('htmlLink', ''),
            'attendees': [a['email'] for a in item.get('attendees', []) if a.get('email') and not a.get('self')],
            'label': _google_label(item), 'calendar_name': item.get('_calendar', {}).get('name', ''),
            'meet': _meeting(item.get('hangoutLink', ''), *[point.get('uri', '') for point in (item.get('conferenceData') or {}).get('entryPoints', [])
                                                              if point.get('entryPointType') == 'video'], item.get('location', ''), item.get('description', '')),
            'organizer': (item.get('organizer') or {}).get('displayName') or ('' if (item.get('organizer') or {}).get('self') else (item.get('organizer') or {}).get('email', '')),
            'notes': _notes(item.get('description', '')),
            # Where he works that day is not an event he attends.
            'skip': item.get('status') == 'cancelled' or item.get('eventType') == 'workingLocation'}


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
            'label': '', 'calendar_name': '',
            'meet': _meeting((item.get('onlineMeeting') or {}).get('joinUrl', ''), item.get('onlineMeetingUrl') or '',
                             (item.get('location') or {}).get('displayName', ''), item.get('bodyPreview', '')),
            'organizer': ((item.get('organizer') or {}).get('emailAddress') or {}).get('name', ''),
            'notes': _notes(item.get('bodyPreview', '')),
            'skip': bool(item.get('isCancelled'))}


def _reason(error: Exception) -> str | None:
    """The provider's failure as one word of fetch_stalls.PHRASES; None for a fault in REM."""
    from ..credentials import AmbientCredentialError
    from .fetch_stalls import failure
    reason = failure(error)
    if reason:
        return reason
    # No OpenOnion key to refresh the token with, or one for another account: a login to fix, not a bug.
    if isinstance(error, (GoogleAuthError, AmbientCredentialError)):
        return 'auth'
    # A reset connection, a TLS failure, httplib2's own errors.
    if isinstance(error, (ConnectionError, ssl.SSLError, HttpLib2Error)):
        return 'network'
    # Any other OS error on the way: the credential file busy under another co, a socket gone.
    return 'unavailable' if isinstance(error, OSError) else None


def _read(kind: str, start, end, zone) -> tuple[list[dict], bool, dict] | None:
    """The kind's events in one shape, whether CAP cut them short, and its calendar counts; None when co cannot read it."""
    if not available(kind):
        return None
    shape = _google if kind == 'google' else _microsoft
    items, counts = calendar_events(kind, start, end, zone)
    rows = [{**shape(item, zone), 'calendar': kind} for item in items]
    unique = {}
    for row in rows:
        # One meeting can come from two of his calendars: keep the copy with a title.
        if not row['skip'] and row['start'] and (row['id'] not in unique or (row['title'] and not unique[row['id']]['title'])):
            unique[row['id']] = row
    return [{key: value for key, value in row.items() if key != 'skip'} for row in unique.values()], len(items) >= CAP, counts


def save_upcoming(root, moment, zone=timezone.utc, *, days: int = DAYS) -> dict:
    """Read every connected calendar's next `days` days into .state/calendar.json; the night run calls this."""
    path = state_path(root, 'calendar.json')
    saved = read_json(path, {})
    stamp = moment.isoformat(timespec='seconds')
    events, errors, read_at, capped, calendars = [], {}, {}, [], {}
    start = moment.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    for kind in KINDS:
        try:
            result = _read(kind, start, start + timedelta(days=days + 1), zone)
        except Exception as error:  # noqa: BLE001 - no calendar may stop the night; a fault in REM is named, not hidden
            reason = _reason(error)
            # A fault in REM carries its traceback to the night's run log (daily.py), never to the page.
            errors[kind] = {'reason': reason or BUG, 'at': stamp,
                            **({} if reason else {'error': type(error).__name__, 'traceback': traceback.format_exc()})}
            if kind in saved.get('read_at', {}):
                read_at[kind] = saved['read_at'][kind]
                # The counts belong to the night its kept events are from; a file saved before #3087 has none.
                calendars |= {kind: saved['calendars'][kind]} if kind in saved.get('calendars', {}) else {}
                events += [event for event in saved.get('events', []) if event['calendar'] == kind]
            continue
        if result is not None:
            events += result[0]
            read_at[kind] = stamp
            calendars[kind] = result[2]
            if result[1]:
                capped.append(kind)
    events.sort(key=lambda event: event['start'])
    shown = {kind: {key: value for key, value in error.items() if key != 'traceback'} for kind, error in errors.items()}
    write_json(path, {'saved_at': stamp, 'days': days, 'read_at': read_at, 'errors': shown, 'capped': capped,
                      'calendars': calendars, 'events': events})
    return {'events': len(events), 'read': sorted(set(read_at) - set(errors)), 'errors': errors, 'capped': capped}


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
    errors, read_at, counts = saved.get('errors', {}), saved.get('read_at', {}), saved.get('calendars', {})
    return {'saved_at': saved.get('saved_at', ''),
            'read': [{'name': NAMES[kind], 'at': at, **({'capped': CAP} if kind in saved.get('capped', []) else {}),
                      **({'calendars': counts[kind]['read'], 'left_out': counts[kind]['left_out']} if kind in counts else {})}
                     for kind, at in read_at.items() if kind not in errors],
            'errors': [{'name': NAMES[kind], 'at': error['at'], 'read_at': read_at.get(kind, ''),
                        'reason': PHRASES.get(error['reason'], 'a fault in REM'), 'error': error.get('error', '')}
                       for kind, error in errors.items()],
            'events': events}
