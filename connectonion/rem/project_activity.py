"""How much happened on each project, week by week, on one scale (#3096).

The owner could not see activity on the Projects timeline: it drew a tick per session day, so a day of
ninety messages and a day of one looked the same, and nothing compared one project with another. This
counts what the notebook actually dates for a project and hands the reader weekly totals, one scale for
every row, and the order of the rows.

What is counted, and nothing else:
- messages: each message the owner typed to an agent in the project's folders (project_material.stored);
- sessions: a recorded session, once, on a day none of its messages were kept (so it is not counted twice);
- mail: a mail the project's page cites, when the notebook holds its date;
- page: the day the page gives as the project's last activity, when nothing above was counted that day.

Decisions carry no date of their own yet (only the day REM extracted them) and commits are cited without one,
so neither is counted. A week starts on Monday in the notebook's zone.
"""

import re
from collections import Counter
from datetime import date, datetime, timedelta

KINDS = ('messages', 'sessions', 'mail', 'page')
QUIET_DAYS = 30  # the same rule as health() in project_priority.py
RECENT_WEEKS = 12


def local_day(stamp: str, zone) -> str:
    """The calendar day of a timestamp in the notebook's zone; a written day is already one."""
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', stamp):
        return stamp
    return datetime.fromisoformat(stamp).astimezone(zone).date().isoformat()


def week_of(day: str) -> str:
    """The Monday of the week a day falls in."""
    moment = date.fromisoformat(day)
    return (moment - timedelta(days=moment.weekday())).isoformat()


def weekly(days) -> dict[str, int]:
    return dict(sorted(Counter(week_of(day) for day in days).items()))


def dated(messages, session_days, mail_stamps, page_day, zone) -> dict[str, list[str]]:
    """The days of everything counted, by kind."""
    typed = [local_day(message['timestamp'], zone) for message in messages if message.get('timestamp')]
    days = {'messages': typed, 'sessions': [day for day in session_days if day and day not in set(typed)],
            'mail': [local_day(stamp, zone) for stamp in mail_stamps if stamp]}
    page = local_day(page_day, zone) if page_day else ''
    days['page'] = [page] if page and not any(page in found for found in days.values()) else []
    return days


def scale(rows) -> list[int]:
    """The lowest count of steps 1 to 4, from the quartiles of every project's active weeks together."""
    counts = sorted(n for weeks in rows for n in weeks.values() if n)
    bounds = [1]
    for quarter in (.25, .5, .75):
        cut = counts[min(len(counts) - 1, int(len(counts) * quarter))] if counts else 0
        bounds.append(max(bounds[-1] + 1, cut))
    return bounds


def level(count: int, bounds: list[int]) -> int:
    """0 for nothing, then 1 to 4."""
    return sum(count >= bound for bound in bounds)


def quiet(last: str, today: date) -> bool:
    return not last or (today - date.fromisoformat(last)).days > QUIET_DAYS


def order(rows: list[dict]) -> list[dict]:
    """People's rule (the newest contact first), for projects: the week it was last active, newest first;
    within a week the busier of the last twelve first; then by name. Never active goes last."""
    named = sorted(rows, key=lambda row: row['title'].casefold())
    return sorted(named, key=lambda row: (week_of(row['last']) if row['last'] else '', row['recent']), reverse=True)


def _session_days(record: dict, records: list[dict]) -> list[str]:
    """One day per recorded session of the project, by its own field or by a link from the project's page."""
    found = {r['path']: r.get('session_date', '') for r in records
             if r['category'] == 'sessions' and r.get('session_project') == record['path']}
    for relation in record.get('relations', []):
        day = re.match(r'sessions/(\d{4}-\d{2}-\d{2})', relation.get('path', ''))
        if day:
            found.setdefault(relation['path'], day[1])
    return list(found.values())


def _mail_stamps(record: dict, contexts: dict) -> list[str]:
    from .reader_model import SOURCE
    from .source import SESSION_SOURCE_PATTERN
    cited = {source for _, source in SOURCE.findall(record['text'])}
    return [contexts[source].get('time', '') for source in sorted(cited)
            if source in contexts and not re.fullmatch(SESSION_SOURCE_PATTERN, source)]


def _measure(record: dict, records: list[dict], stored, contexts: dict, today: date, zone) -> dict:
    days = dated(stored(record['path']), _session_days(record, records), _mail_stamps(record, contexts),
                 record.get('last_activity') or '', zone)
    every = sorted(day for kind in KINDS for day in days[kind])
    since = week_of((today - timedelta(weeks=RECENT_WEEKS - 1)).isoformat())
    return {'weeks': weekly(every), 'kinds': {kind: len(days[kind]) for kind in KINDS},
            'first': every[0] if every else '', 'last': every[-1] if every else '',
            'recent': sum(day >= since for day in every)}


def attach(records: list[dict], stored, contexts: dict, today: date, zone) -> dict:
    """Give every project record its `activity` and return what the page says once for all of them."""
    projects = [record for record in records if record['category'] == 'projects']
    for record in projects:
        record['activity'] = _measure(record, records, stored, contexts, today, zone)
    ranked = order([{'title': r['title'], 'path': r['path'], **r['activity']} for r in projects])
    rank = {row['path']: i for i, row in enumerate(ranked)}
    for record in projects:
        record['activity'].update(rank=rank[record['path']], quiet=quiet(record['activity']['last'], today))
    weeks = [record['activity']['weeks'] for record in projects]
    return {'scale': scale(weeks), 'kinds': {kind: sum(r['activity']['kinds'][kind] for r in projects) for kind in KINDS},
            'first': min((week for row in weeks for week in row), default=''),
            'this_week': week_of(today.isoformat()), 'quiet_days': QUIET_DAYS, 'recent_weeks': RECENT_WEEKS}
