"""Two saved days from calendar facts and Today's ranking, without a model (#3058)."""

import re
from datetime import date, datetime, time, timedelta

from .files import Notebook, read_json, state_path, write_json
from .service import notebook_zone

STREET = re.compile(r'\b(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd|way|'
                    r'highway|hwy|terrace|crescent|court|place|square)\b|[路街巷道号]', re.I)

_MONTHS = ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec')
_MONTH_RE = r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
_ISO_TIME = re.compile(r'\b(\d{4}-\d{2}-\d{2})(?:[T\s]+(?:at\s+)?)?(?:(上午|早上|早晨|中午|下午|晚上|傍晚)\s*)?(\d{1,2})(?:[:：](\d{2})|点(半|\d{1,2}分?)?|\s*(am|pm)\b)', re.I)
_EN_MD_TIME = re.compile(rf'\b({_MONTH_RE})\s+(\d{{1,2}})(?:,?\s*(\d{{4}}))?(?:\s+at|\s*,)?\s+(\d{{1,2}})(?::(\d{{2}}))?\s*(am|pm)?\b', re.I)
_EN_DM_TIME = re.compile(rf'\b(\d{{1,2}})\s+({_MONTH_RE})(?:\s+(\d{{4}}))?(?:\s+at|\s*,)?\s+(\d{{1,2}})(?::(\d{{2}}))?\s*(am|pm)?\b', re.I)
_ZH_MD_TIME = re.compile(r'(\d{1,2})月(\d{1,2})[日号]\s*(上午|早上|早晨|中午|下午|晚上|傍晚)?\s*(\d{1,2})\s*(?:[:：](\d{2})|点(半|\d{1,2}分?)?)')
_TODAY_EN_AFTER = re.compile(r'\b(?:today|this\s+(?:morning|afternoon|evening)|tonight)\b[^.\n]{0,24}?(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', re.I)
_TODAY_EN_BEFORE = re.compile(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b[^.\n]{0,20}?\btoday\b', re.I)
_TODAY_ZH = re.compile(r'(?:今天|今日)\s*(上午|早上|早晨|中午|下午|晚上|傍晚)?\s*(\d{1,2})\s*(?:[:：](\d{2})|点(半|\d{1,2}分?)?)')
_DUE_EN_TIME = re.compile(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', re.I)
_DUE_ZH_TIME = re.compile(r'(上午|早上|早晨|中午|下午|晚上|傍晚)\s*(\d{1,2})\s*(?:[:：](\d{2})|点(半|\d{1,2}分?)?)')


def _parse_clock(hour_s, minute_s=None, mer_s=None, zh_part=None, zh_min=None):
    hour = int(hour_s)
    if zh_min == '半':
        minute = 30
    elif zh_min:
        minute = int(zh_min.rstrip('分'))
    elif minute_s is not None and minute_s != '':
        minute = int(minute_s)
    else:
        minute = 0
    mer = (mer_s or '').lower()
    if mer == 'pm' and 1 <= hour <= 11:
        hour += 12
    elif mer == 'am' and hour == 12:
        hour = 0
    elif zh_part in ('下午', '晚上', '傍晚') and 1 <= hour <= 11:
        hour += 12
    elif zh_part == '中午' and 1 <= hour <= 5:
        hour += 12
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def elapsed_appointment(text, moment, zone, *, due=''):
    """Return the local datetime of an elapsed appointment referenced in `text`, or None (#3439)."""
    if not text:
        return None
    local_now = moment.astimezone(zone)
    today = local_now.date()
    candidates = []

    def add(day_obj, clock):
        if day_obj is None or clock is None:
            return
        if (today - day_obj).days > 7:
            return
        candidates.append(datetime(day_obj.year, day_obj.month, day_obj.day, clock[0], clock[1], tzinfo=zone))

    for m in _ISO_TIME.finditer(text):
        if not (m.group(4) or m.group(5) or m.group(6) or m.group(2) or '点' in m.group(0)):
            continue
        try:
            d = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        add(d, _parse_clock(m.group(3), m.group(4), m.group(6), m.group(2), m.group(5)))

    for m in _EN_MD_TIME.finditer(text):
        if not (m.group(5) or m.group(6)):
            continue
        try:
            d = date(int(m.group(3) or today.year), _MONTHS.index(m.group(1)[:3].lower()) + 1, int(m.group(2)))
        except ValueError:
            continue
        add(d, _parse_clock(m.group(4), m.group(5), m.group(6)))

    for m in _EN_DM_TIME.finditer(text):
        if not (m.group(5) or m.group(6)):
            continue
        try:
            d = date(int(m.group(3) or today.year), _MONTHS.index(m.group(2)[:3].lower()) + 1, int(m.group(1)))
        except ValueError:
            continue
        add(d, _parse_clock(m.group(4), m.group(5), m.group(6)))

    for m in _ZH_MD_TIME.finditer(text):
        try:
            d = date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            continue
        add(d, _parse_clock(m.group(4), m.group(5), None, m.group(3), m.group(6)))

    for pat in (_TODAY_EN_AFTER, _TODAY_EN_BEFORE):
        for m in pat.finditer(text):
            if not (m.group(2) or m.group(3)):
                continue
            hint = m.group(0).lower()
            mer = m.group(3) or ('pm' if ('afternoon' in hint or 'evening' in hint or 'tonight' in hint) else None)
            add(today, _parse_clock(m.group(1), m.group(2), mer))

    for m in _TODAY_ZH.finditer(text):
        add(today, _parse_clock(m.group(2), m.group(3), None, m.group(1), m.group(4)))

    if due == today.isoformat():
        for m in _DUE_EN_TIME.finditer(text):
            if not (m.group(2) or m.group(3)):
                continue
            add(today, _parse_clock(m.group(1), m.group(2), m.group(3)))
        for m in _DUE_ZH_TIME.finditer(text):
            add(today, _parse_clock(m.group(2), m.group(3), None, m.group(1), m.group(4)))

    if not candidates or any(dt >= local_now for dt in candidates):
        return None
    return max(candidates)


def address_missing(location):
    """Flag only short venue names: at most six words, no number or street word."""
    return bool(location.strip() and len(location.split()) <= 6
                and not re.search(r'\d', location) and not STREET.search(location))


def _moment(value, zone):
    moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return (moment if moment.tzinfo else moment.replace(tzinfo=zone)).astimezone(zone)


def _bounds(day, config, zone):
    hours = config.get('schedule', {}).get('working_hours', {'start': '09:00', 'end': '18:00'})
    return tuple(datetime.combine(day, time.fromisoformat(hours[key]), zone) for key in ('start', 'end'))


def _events(calendar, day, zone):
    start = datetime.combine(day, time.min, zone)
    end = start + timedelta(days=1)
    rows = []
    for event in (calendar or {}).get('events', []):
        first = _moment(event['start'], zone)
        last = _moment(event.get('end') or event['start'], zone)
        if first >= end or last <= start:
            continue
        begin, finish = max(start, first), min(end, last)
        # Twenty-four hours or more is a trip or a booking, not a meeting: it is listed with the all-day
        # entries and blocks nothing. A shorter one past midnight ends at 24:00 on the day it began.
        all_day = bool(event.get('all_day')) or last - first >= timedelta(days=1)
        rows.append({**event, 'kind': 'event', 'all_day': all_day, 'start': begin.isoformat(), 'end': finish.isoformat(),
                     'time': '' if all_day else begin.strftime('%H:%M'),
                     'end_time': '' if all_day else '24:00' if finish == end else finish.strftime('%H:%M'),
                     'address_missing': address_missing(event.get('location', ''))})
    return sorted(rows, key=_order)


def _order(row):
    """All-day entries lead the day as context; then everything by its time."""
    return (not row.get('all_day'), row.get('start') or '9999')


def _gaps(events, start, end, zone):
    gaps, cursor = [], start
    for event in events:
        first, last = _moment(event['start'], zone), _moment(event['end'], zone)
        if first > cursor:
            gaps.append([cursor, min(first, end)])
        cursor = max(cursor, last)
        if cursor >= end:
            break
    if cursor < end:
        gaps.append([cursor, end])
    return [gap for gap in gaps if gap[1] > gap[0]]


def _slot(gaps):
    """One half hour from the longest usable gap; earlier wins a tie."""
    options = []
    for index, (start, end) in enumerate(gaps):
        rounded = start.replace(minute=0, second=0, microsecond=0)
        rounded += timedelta(minutes=30 * ((start.minute + bool(start.second or start.microsecond) + 29) // 30))
        if rounded + timedelta(minutes=30) <= end:
            options.append((end - rounded, rounded, index))
    if not options:
        return None
    _, start, index = min(options, key=lambda row: (-row[0].total_seconds(), row[1]))
    finish = start + timedelta(minutes=30)
    gaps[index][0] = finish
    return start, finish


def _reasons(row, day):
    from .today import _future_commitment
    reasons, due = [], row.get('due', '')
    if due:
        key = 'late since {date}' if due < day else 'due today' if due == day else 'due {date}'
        reasons.append({'text': key, 'values': {'date': due}})
    name, since = row['title'], row.get('since', '')
    reply = row.get('reply', {})
    if row['record'].startswith('people/') and reply.get('last_word_yours') and _future_commitment(reply.get('promise', '')):
        reasons.append({'text': 'promised to {name}', 'values': {'name': name}})
    elif not row['record'].startswith('people/') or reply.get('last_word_yours'):
        reasons.append({'text': 'open item on {name}', 'values': {'name': name}})
    else:
        reasons.append({'text': '{name} waiting since {date}' if since else '{name} waiting',
                        'values': {'name': name, 'date': since}})
    return reasons


def _proposal(row, day, slot, calendar_read, *, elapsed=None):
    reasons = _reasons(row, day.isoformat())
    if elapsed is not None:
        reasons.append({'text': 'time already passed ({time}) — recheck before sending',
                        'values': {'time': elapsed.strftime('%H:%M')}})
    proposal = {'kind': 'proposal', 'key': row['key'], 'keys': row.get('keys', [row['key']]),
                'record': row['record'], 'title': row['title'],
                'text': re.sub(r'\s*\[\d+\]', '', row['text']).strip(), 'reasons': reasons,
                'reason': '; '.join(reason['text'].format(**reason['values']) for reason in reasons),
                'start': slot[0].isoformat() if slot else '', 'end': slot[1].isoformat() if slot else '',
                'time': slot[0].strftime('%H:%M') if slot else '', 'end_time': slot[1].strftime('%H:%M') if slot else '',
                'placement': 'no free time today' if calendar_read and not slot else ''}
    if elapsed is not None:
        proposal['elapsed'] = True
        proposal['elapsed_at'] = elapsed.isoformat()
    return proposal


def _day(calendar, items, day, config, zone, calendar_read, elapsed_map=None):
    events = _events(calendar, day, zone)
    # Only timed events take working hours: one week-long all-day entry once left every proposal without a time.
    gaps = _gaps([row for row in events if not row['all_day']], *_bounds(day, config, zone), zone)
    proposals = [_proposal(row, day, _slot(gaps) if calendar_read else None, calendar_read,
                           elapsed=(elapsed_map or {}).get(row['key'])) for row in items]
    return {'date': day.isoformat(), 'items': sorted(events + proposals, key=_order)}


def build(calendar, items, config, moment):
    """Pure plan from an enriched saved calendar and the existing Today queue."""
    zone = notebook_zone(config)
    day = moment.astimezone(zone).date()
    read = bool((calendar or {}).get('read') or any(error.get('read_at') for error in (calendar or {}).get('errors', [])))
    eligible = [row for row in items if _eligible(row, day)]
    elapsed_map = {row['key']: elapsed_appointment(row.get('text', ''), moment, zone, due=row.get('due', '')) for row in eligible}
    # #3439: demote already-elapsed appointments behind current/actionable items so they never lead Today.
    chosen = sorted(eligible, key=lambda row: (elapsed_map.get(row['key']) is not None, row['rank']))[:5]
    return {'saved_at': moment.isoformat(timespec='seconds'), 'timezone': str(zone), 'calendar_read': read,
            'calendar_saved_at': (calendar or {}).get('saved_at', ''),
            'calendar_errors': (calendar or {}).get('errors', []),
            'days': [_day(calendar, chosen, day + timedelta(days=n), config, zone, read,
                          elapsed_map if n == 0 else None) for n in (0, 1)]}


def _eligible(row, day):
    old = (day - timedelta(days=60)).isoformat()
    stale = bool(row.get('due') and row.get('since') and row['due'] < old and row['since'] < old)
    return (row['dir'] == 'mine' and not row['closed'] and not row['quiet'] and not stale
            and row.get('reply', {}).get('state') != 'replied')


def save(root, moment):
    """Called immediately after the calendar save by the single background function."""
    from .calendar import upcoming
    from .config import read_config
    from .today import queue
    book = Notebook(root)
    records = [{'path': path, 'category': path.split('/')[0], 'text': book.read(path)} for path in book.list()]
    owner = (read_json(state_path(root, 'map.json'), {}).get('owner') or {}).get('record', '')
    config = read_config(root)
    items = queue(root, records=records, as_of=moment.astimezone(notebook_zone(config)).date())
    plan = build(upcoming(root, records, owner), items, config, moment)
    write_json(state_path(root, 'day-plan.json'), plan)
    return {'dates': [day['date'] for day in plan['days']],
            'events': sum(row['kind'] == 'event' for day in plan['days'] for row in day['items']),
            'proposals': sum(row['kind'] == 'proposal' for day in plan['days'] for row in day['items'])}


def read(root, *, items=None):
    """Saved plan, or untimed proposals before the first save; no network or writes."""
    saved = read_json(state_path(root, 'day-plan.json'), None)
    if saved is not None:
        return saved
    from .config import read_config
    from .service import now
    from .today import queue
    plan = build(None, queue(root) if items is None else items, read_config(root), now())
    plan['calendar_read'] = bool(read_json(state_path(root, 'calendar.json'), {}).get('read_at'))
    plan['not_saved'] = True
    return plan


def _title(row):
    """An event saved without a title says what it is, and whose calendar hid the rest."""
    label = row.get('label') or 'No title'
    named = label == 'Busy' and row.get('calendar_name')
    return row['title'] or (f"{label} ({row['calendar_name']})" if named else label)


def _event_text(row):
    when = 'All day' if row.get('all_day') else row['time'] + '–' + row['end_time']
    parts = [when + ' ' + _title(row), *row.get('people', []), row.get('link', '')]
    if row.get('location'):
        parts += [row['location'], 'address not in the calendar event' if row['address_missing'] else '']
    return ' — '.join(part for part in parts if part)


def text(plan, today):
    """The same saved facts as words for status (its card joins the lines)."""
    day = next((day for day in plan['days'] if day['date'] == today), plan['days'][0])
    lines = ['Your day (' + day['date'] + ')']
    if day['date'] != today:
        lines.append('This saved plan is out of date. Run co rem catchup to refresh it.')
    if not plan['calendar_read']:
        lines.append('No calendar has been read yet.')
    elif plan.get('not_saved'):
        lines.append('No day plan has been saved yet.')
    for error in plan.get('calendar_errors', []):
        last = error.get('read_at', '')[:10] or 'never'
        lines.append(f"{error['name']} could not be read: {error['reason']}; events last read {last}")
    for row in day['items']:
        if row['kind'] == 'event':
            lines.append(_event_text(row))
        else:
            when = (row['time'] + '–' + row['end_time']) if row['time'] else row['placement']
            lines.append(' — '.join(part for part in [when, 'Proposed: ' + row['text'], row['reason'], row['record']] if part))
    tomorrow = next((d for d in plan['days'] if d['date'] == (date.fromisoformat(today) + timedelta(days=1)).isoformat()), None)
    events = [row for row in (tomorrow or {}).get('items', []) if row['kind'] == 'event']
    if events:
        lines.append('Tomorrow: first event — ' + _event_text(events[0]))
        lines.extend('Tomorrow: place to go — ' + _event_text(row) for row in events if row.get('location'))
    return '\n'.join(lines)


def status(root, today):
    plan = read(root)
    return {'saved_at': plan['saved_at'], 'text': text(plan, today).replace('\n', '; ')}
