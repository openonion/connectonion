"""The daily round: maintain first, then one of two jobs (#1943 stage 3, #1723).

The schedule runs several times a day. Every run maintains first. Then:

- the first run of the local day finishes unfinished pages, most recent
  activity first: a person is one call (an agent searching their prepared
  evidence), a project or organisation takes the older investigation and ends
  the portion;
- every later run follows what is new: people with mail since the previous
  run and projects with new messages the user typed, each updated from its new
  material only.

Which run is which is decided by what already ran today, not by the clock, so
a machine asleep at the first slot still gets its unfinished portion.
"""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import read_config
from .files import Notebook, WikiError, maintenance_lock, read_json, state_path, write_json
from .service import now, run_logs, run_sync, status, subscriptions, mail_client
from .investigate import investigate
from . import quota


# At most this many calls for the first run's portion. It was "everything but
# two", which at the old cap of 6 meant 4; at 30 it would let one large page
# spend a night's calls. A person is one call, so this is up to 8 people.
INVESTIGATION_CALLS = 8
# Pages a later run updates from new material, one call each.
UPDATE_PAGES = 5
# Activity this recent comes first in the unfinished portion.
RECENT_DAYS = 14
PHASES = ("daily-investigation", "daily-update")


def _last(values) -> str:
    stamps = []
    for value in values:
        value = str(value or "")
        if not value:
            continue
        try:
            stamp = datetime.fromisoformat((value if "T" in value else value + "T00:00:00+00:00").replace("Z", "+00:00"))
            stamps.append(stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc))
        except ValueError:
            continue
    return max(stamps).astimezone(timezone.utc).isoformat() if stamps else ""


def unfinished_by_recency(root: Path, *, today: datetime | None = None) -> list[dict]:
    """Unfinished people, projects and organisations, most recent activity first.

    The busiest page first never fit a day's calls (#1723). The most recent
    one is what is useful now, and with a person costing one call it fits.
    People whose evidence was all written already, or who have none this
    week, are left to the later runs (people_pages.queue decides).
    """
    from .people_pages import last_activity, queue as people_queue
    from .project_material import page_state
    from .queue import order_all
    today = today or now()
    state = read_json(state_path(root, "map.json"), {})
    people_last = {row.get("record"): row.get("last") for row in state.get("people", [])}
    project_last = {row.get("record"): row.get("last") for row in state.get("projects", [])}
    org_people = {row.get("record"): row.get("people") or [] for row in state.get("orgs", [])}
    wanted_people = {row["record"] for row in people_queue(root)}
    rows = []
    for index, row in enumerate(order_all(root)):
        path = row["path"]
        if row["recent"] or (path.startswith("people/") and path not in wanted_people):
            continue
        if path.startswith("people/"):
            last = last_activity(root, path)
        elif path.startswith("projects/"):
            last = _last([project_last.get(path), page_state(root, path).get("last_activity")])
        else:
            last = _last([people_last.get(person) for person in org_people.get(path, [])])
        rows.append({**row, "last_activity": last, "position": index})
    cutoff = (today - timedelta(days=RECENT_DAYS)).isoformat()

    def key(row):
        stamp = row["last_activity"]
        return (not (stamp and stamp >= cutoff), -datetime.fromisoformat(stamp).timestamp() if stamp else 0.0,
                row["position"])
    return sorted(rows, key=key)


def _clients(sources: dict) -> dict:
    # The same mailboxes `co wiki investigate` reads: every connected one the
    # user did not unsubscribe. Reading only subscribed mailboxes here left the
    # scheduled investigation with no mail -- the #1628 failure, one path over.
    from .service import mail_available
    return {kind: mail_client(kind, attachments=True) for kind in ('outlook', 'gmail')
            if mail_available(kind) and not sources.get(kind, {}).get('unsubscribed')}


def _reserve(root: Path, phase: str, attempts: int, meter: dict) -> tuple[dict, Path]:
    record = {'id': 'run_' + uuid.uuid4().hex, 'started_at': now().isoformat(),
              'outcome': 'running', 'runner_attempts': attempts, 'usage': None,
              'sources': [], 'items': 0, 'changed': [], 'phase': phase,
              'quota': {'before': meter}}
    path = state_path(root, f"runs/{record['id']}.json")
    write_json(path, record)
    return record, path


def _add_usage(total: dict, usage) -> dict:
    for key, value in (usage or {}).items():
        total[key] = total.get(key, 0) + value
    return total


def run_daily(root: Path, *, days: int = 30, scheduled: bool = False,
              maintain=None, investigate_one=None, person_one=None, project_one=None) -> dict | None:
    """One scheduled run. `investigate_one`, `person_one` and `project_one` replace
    the model calls in tests; `investigate_one` given alone takes every page the
    older way, as before this stage."""
    maintenance = (maintain or run_sync)(root, scheduled=True) if scheduled else (maintain or run_sync)(root)
    if maintenance is None:
        return None
    if maintenance['outcome'] not in ('completed', 'no_change'):
        return {'outcome': 'partial', 'maintenance': maintenance, 'investigation': None}
    config = read_config(root)
    with maintenance_lock(root):
        state = status(root)
        zone = ZoneInfo(config['schedule']['timezone']) if config['schedule']['timezone'] else timezone.utc
        logs = run_logs(root)
        today = [record for record in logs if record.get('phase') in PHASES and
                 datetime.fromisoformat(record['started_at']).astimezone(zone).date().isoformat() == state['date']]
        remaining = config['limits']['runner_calls_per_day'] - state['runner_attempts_today']
        # The Codex week (#1843): investigation's own budget, and a floor that
        # leaves the rest of the week to the owner's coding.
        meter = quota.read(config)
        stop = quota.blocks(meter, quota.points_spent(logs, meter), config['limits'])
    if any(record.get('phase') == 'daily-investigation' for record in today):
        previous = max((record['started_at'] for record in logs if record.get('phase') in PHASES), default='')
        return _follow_new(root, config, maintenance, remaining, meter, stop, previous,
                           person_one=person_one, project_one=project_one)
    return _unfinished(root, config, maintenance, remaining, meter, stop, days,
                       investigate_one=investigate_one, person_one=person_one)


def _unfinished(root, config, maintenance, remaining, meter, stop, days, *, investigate_one, person_one):
    """The first run of the day: unfinished pages, most recent activity first."""
    pages = unfinished_by_recency(root)
    from .inquiry import routing
    required = 3 if routing(root) else 1
    # Even a run that starts nothing is the day's first: it is recorded, so the
    # later runs know to follow new material instead.
    why = 'nothing_unfinished' if not pages else 'budget_exhausted' if remaining < required else stop
    if why:
        with maintenance_lock(root):
            record, path = _reserve(root, 'daily-investigation', 0, meter)
            record.update(outcome='completed', reason=why, left=len(pages), finished_at=now().isoformat())
            record['quota']['after'] = meter
            write_json(path, record)
        return {'outcome': 'budget_exhausted' if why == 'budget_exhausted' else 'completed',
                'maintenance': maintenance, 'investigation': None, 'run': record,
                **({'reason': why} if why != 'budget_exhausted' else {}),
                **({'quota': meter} if why == stop else {})}
    # Keep up to two calls for later slots. Reserve before starting so an
    # interrupted investigation cannot restart beyond the daily cap.
    allocation = min(remaining, max(required, min(remaining - 2, INVESTIGATION_CALLS)))
    with maintenance_lock(root):
        record, path = _reserve(root, 'daily-investigation', allocation, meter)
    sources = subscriptions(root)
    notebook = Notebook(root)
    calls, tried, done, usage, changed, failed = allocation, [], [], {}, [], False
    others = 0
    try:
        clients = _clients(sources)
        for page in pages:
            target = page['path']
            if calls < 1 or (done and _stopped(root, config)):
                break
            if target.startswith('people/') and investigate_one is None:
                tried.append(target)
                result = (person_one or _person)(root, target, config=config, clients=clients,
                                                 subscriptions=sources)
                calls -= 0 if result.get('skipped') else 1
            else:
                # The older investigation: it takes what is left of the portion and ends it.
                # The busiest page is also the one least likely to fit: a refusal
                # before any model call tries the next, up to three (#1670).
                if others >= 3:
                    continue
                others += 1
                tried.append(target)
                text = notebook.read(target)
                title = next((line[2:] for line in text.splitlines() if line.startswith('# ')), target)
                person = next((p for p in notebook.people() if p['path'] == target), {})
                handles = list(dict.fromkeys([title, *person.get('emails', []), *person.get('aliases', [])]))
                try:
                    result = (investigate_one or investigate)(root, target, title, handles, days=days,
                                  clients=clients, subscriptions=sources, max_calls=calls)
                except WikiError as error:
                    if 'call budget' not in str(error):
                        raise
                    continue
                calls = 0
            done.append({'page': target, 'outcome': 'skipped' if result.get('skipped') else 'accepted',
                         **({'why': result['skipped']} if result.get('skipped') else {})})
            _add_usage(usage, result.get('usage'))
            changed += result.get('changed', [])
        accepted = [row['page'] for row in done if row['outcome'] == 'accepted']
        left = len(unfinished_by_recency(root))
        record.update(outcome='completed', usage=usage or None, changed=changed, tried=tried, pages=done,
                      left=left, **({'record': accepted[-1]} if accepted else {'reason': 'no_page_fits_budget'}))
        if not accepted and all(row['outcome'] == 'skipped' for row in done) and done:
            record['reason'] = 'no_material'
    except Exception as error:
        record.update(outcome='failed', error=str(error) if isinstance(error, WikiError) else type(error).__name__,
                      usage=getattr(error, 'usage', None) or usage or None, tried=tried, pages=done)
        failed = True
    finally:
        record['finished_at'] = now().isoformat()
        record['quota']['after'] = quota.read(config)
        write_json(path, record)
    investigation = None if failed or not done else {'pages': done, 'left': record.get('left')}
    return {'outcome': 'partial' if failed else 'completed',
            'maintenance': maintenance, 'investigation': investigation, 'run': record}


def _stopped(root, config) -> str:
    """Before each further page: the weekly budget or the floor, read again."""
    meter = quota.read(config)
    return quota.blocks(meter, quota.points_spent(run_logs(root), meter), config['limits'])


def _person(root, record, *, config, clients, subscriptions):
    from .people_pages import write_page
    return write_page(root, record, config=config, clients=clients, subscriptions=subscriptions)


def _project(root, record, *, config):
    from .project_pages import write_page
    return write_page(root, record, config=config)


def _follow_new(root, config, maintenance, remaining, meter, stop, previous, *, person_one, project_one):
    """A later run: only people and projects with new material since the previous run."""
    from .people_evidence import correspondents_since, prepare
    from .people_pages import queue as people_queue
    from .project_material import extract
    from .project_pages import queue as project_queue
    since = previous or (now() - timedelta(days=1)).isoformat()
    sources = subscriptions(root)
    clients = _clients(sources)
    # Step 1, no model: who has new material. One mailbox listing since the
    # last run; each person found is brought up to date; new session lines
    # are filed under their project pages.
    found = correspondents_since(root, clients, since=datetime.fromisoformat(since))
    for person in found['records']:
        if Notebook(root).path(person).is_file():
            prepare(root, person, clients=clients, subscriptions=sources)
    extract(root, sources)
    rows = [{**row, 'kind': 'person'} for row in people_queue(root, since=since)
            if row['mode'] == 'update' or row['record'] in found['records']]
    rows += [{**row, 'kind': 'project'} for row in project_queue(root, since=since)]
    rows.sort(key=lambda row: row['last_activity'] or '', reverse=True)
    if not rows:
        return {'outcome': 'completed', 'maintenance': maintenance, 'investigation': None,
                'reason': 'nothing_new', 'listed': found['listed']}
    if stop:
        return {'outcome': 'completed', 'maintenance': maintenance, 'investigation': None,
                'reason': stop, 'quota': meter, 'left': len(rows)}
    chosen = rows[:max(0, min(UPDATE_PAGES, remaining))]
    if not chosen:
        return {'outcome': 'budget_exhausted', 'maintenance': maintenance, 'investigation': None,
                'left': len(rows)}
    with maintenance_lock(root):
        record, path = _reserve(root, 'daily-update', len(chosen), meter)
    done, usage, changed, failed = [], {}, [], False
    try:
        for row in chosen:
            if done and _stopped(root, config):
                break
            try:
                if row['kind'] == 'person':
                    result = (person_one or _person)(root, row['record'], config=config, clients=clients,
                                                     subscriptions=sources)
                else:
                    result = (project_one or _project)(root, row['record'], config=config)
                done.append({'page': row['record'], 'mode': row['mode'],
                             'outcome': 'skipped' if result.get('skipped') else 'accepted'})
                _add_usage(usage, result.get('usage'))
                changed += result.get('changed', [])
            except WikiError as error:
                # One refused page does not stop the others; its material stays pending.
                done.append({'page': row['record'], 'mode': row['mode'],
                             'outcome': 'refused' if 'rejected' in str(error) else 'failed',
                             'why': str(error)[:300]})
                _add_usage(usage, getattr(error, 'usage', None))
        left = len(rows) - sum(1 for row in done if row['outcome'] in ('accepted', 'skipped'))
        record.update(outcome='completed', usage=usage or None, changed=changed, pages=done, left=left,
                      since=since, listed=found['listed'])
    except Exception as error:
        record.update(outcome='failed', error=str(error) if isinstance(error, WikiError) else type(error).__name__,
                      usage=usage or None, pages=done)
        failed = True
    finally:
        record['finished_at'] = now().isoformat()
        record['quota']['after'] = quota.read(config)
        write_json(path, record)
    return {'outcome': 'partial' if failed else 'completed', 'maintenance': maintenance,
            'investigation': None if failed else {'pages': done, 'left': record.get('left')}, 'run': record}
