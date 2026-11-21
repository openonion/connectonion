"""The owner's open to-dos, saved by the night beside his calendar for Today (#3087).

Owner, 2026-11-17: Today showed none of his Outlook or Google to-dos. The step
of the night that saves `.state/calendar.json` reads his open Microsoft To Do
tasks into `.state/todos.json`; the reader shows that file and never calls
Microsoft. A read that fails keeps the tasks saved before, with when and why,
and never stops the night (calendar.py's shape): a provider's failure is one
word, a fault in REM carries its exception's name and its traceback to the log.

Google Tasks are not read. The Google login has only the calendar scope, and
REM never adds a scope or starts a login: `google_tasks` says which of the two
is missing so the page can say it in words.

`todo_tasks` is the one place that talks to Microsoft; tests replace it.
"""

import traceback
from datetime import timezone

from .files import read_json, state_path, write_json

CAP = 1000  # tasks in all: paging stops there


def available() -> bool:
    """Whether co's saved Microsoft login can read tasks; never logs in.

    The Graph client is the calendar tool's, which wants the calendar scope too."""
    from ..provider_credentials import resolve_provider_credentials
    from .calendar import available as calendar_available
    return calendar_available('microsoft') and 'Tasks' in (resolve_provider_credentials('microsoft').get('SCOPES') or '')


def google_tasks() -> str | None:
    """Why Google Tasks are not on the page: 'reconnect' without the tasks scope, 'not_read' with it; None with no Google login."""
    from ..provider_credentials import resolve_provider_credentials
    scopes = resolve_provider_credentials('google').scopes
    if not scopes:
        return None
    return 'not_read' if scopes & {'tasks', 'tasks.readonly'} else 'reconnect'


def todo_tasks(zone) -> list[dict]:
    """Graph's own todoTask objects that are not completed, each with its list's name; tests replace this."""
    from ..useful_tools.microsoft_calendar import MicrosoftCalendar
    from .calendar import _graph_pages, _zone_name
    client = MicrosoftCalendar()  # the tool's login and token refresh
    headers = {'Prefer': f'outlook.timezone="{_zone_name(zone)}"'}
    tasks = []
    for listed in _graph_pages(client, '/me/todo/lists', None, headers):
        if len(tasks) >= CAP:
            break
        rows = _graph_pages(client, f"/me/todo/lists/{listed['id']}/tasks",
                            {'$filter': "status ne 'completed'", '$top': 100}, headers, CAP - len(tasks))
        tasks += [{**row, '_list': listed.get('displayName', '')} for row in rows]
    return tasks


def _task(item: dict, zone) -> dict:
    from .calendar import _graph_moment
    due = _graph_moment(item.get('dueDateTime'), zone)
    # A due date is a day: Graph sends it as midnight in his zone, written in the zone it answered in.
    return {'id': item.get('id', ''), 'title': item.get('title') or '', 'list': item.get('_list', ''),
            'due': due.astimezone(zone).date().isoformat() if due else '', 'provider': 'microsoft'}


def save(root, moment, zone=timezone.utc) -> dict:
    """Read his open to-dos into .state/todos.json; the night's calendar step calls this."""
    from .calendar import BUG, _reason
    path = state_path(root, 'todos.json')
    saved = read_json(path, {})
    stamp = moment.isoformat(timespec='seconds')
    state = {'saved_at': stamp, 'read_at': '', 'google': google_tasks(), 'error': None, 'tasks': []}
    fault = {}
    if available():
        try:
            # Graph was asked for open tasks; one that answers with a completed task is still not a to-do.
            state['tasks'] = [_task(item, zone) for item in todo_tasks(zone) if item.get('status') != 'completed']
            state['read_at'] = stamp
        except Exception as error:  # noqa: BLE001 - no to-do read may stop the night; a fault in REM is named, not hidden
            reason = _reason(error)
            state['error'] = {'reason': reason or BUG, 'at': stamp, **({} if reason else {'error': type(error).__name__})}
            state.update(read_at=saved.get('read_at', ''), tasks=saved.get('tasks', []))
            fault = {} if reason else {'traceback': traceback.format_exc()}
    write_json(path, state)
    return {'tasks': len(state['tasks']), 'error': state['error'], **fault}


def read(root) -> dict | None:
    """What Today's to-do section shows; None when no night has saved to-dos."""
    from .fetch_stalls import PHRASES
    saved = read_json(state_path(root, 'todos.json'), None)
    if saved is None:
        return None
    error = saved.get('error')
    return {'tasks': saved.get('tasks', []), 'read_at': saved.get('read_at', ''), 'google': saved.get('google'),
            'error': error and {'at': error['at'], 'reason': PHRASES.get(error['reason'], 'a fault in REM'),
                                'error': error.get('error', '')}}
