"""The daily round: maintain first, then one of two jobs (#1943 stage 3, #1723).

The schedule runs several times a day. Every run maintains first. Then:

- the first run of the local day finishes unfinished pages, most recent
  activity first: a person is one investigation (#1942: gathered by our code,
  searched as files by one turn), over only the mail since their last
  investigation when they had one; a project or organisation also takes the
  rest of the portion's calls and ends it;
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

from . import quota
from .config import read_config
from .files import Notebook, RemError, maintenance_lock, read_json, state_path, write_json
from .investigate import NothingFound, NothingNew, investigate
from .service import mail_client, now, run_logs, run_sync, status, subscriptions

# At most this many calls for the first run's portion. It was "everything but
# two", which at the old cap of 6 meant 4; at 30 it would let one large page
# spend a night's calls. A person is one call, so this is up to 8 people.
INVESTIGATION_CALLS = 8
# Pages a later run updates from new material, one call each.
UPDATE_PAGES = 5
# Activity this recent comes first in the unfinished portion.
RECENT_DAYS = 14
PHASES = ("daily-investigation", "daily-update")
# The window a refused page is investigated over again: run_daily's own default.
RETRY_DAYS = 30


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
    Which people, and over which window, is people_pages.queue's: a person
    investigated before is read only from the mail since then.
    """
    from .people_pages import queue as people_queue
    from .project_material import page_state
    from .queue import order_all
    today = today or now()
    state = read_json(state_path(root, "map.json"), {})
    people_last = {row.get("record"): row.get("last") for row in state.get("people", [])}
    project_last = {row.get("record"): row.get("last") for row in state.get("projects", [])}
    org_people = {row.get("record"): row.get("people") or [] for row in state.get("orgs", [])}
    people = {row["record"]: row for row in people_queue(root)}
    rows = []
    for index, row in enumerate(order_all(root)):
        path = row["path"]
        if path.startswith("people/"):
            if path not in people:
                continue
            rows.append({**row, **people[path], "last_activity": people[path]["last_activity"], "position": index})
            continue
        if row["recent"]:
            continue
        if path.startswith("projects/"):
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
    # The same mailboxes `co rem investigate` reads: every connected one the
    # user did not unsubscribe. Reading only subscribed mailboxes here left the
    # scheduled investigation with no mail -- the #1628 failure, one path over.
    from .service import mail_available
    return {kind: mail_client(kind, attachments=True) for kind in ('outlook', 'gmail')
            if mail_available(kind) and not sources.get(kind, {}).get('unsubscribed')}


def _reserve(root: Path, phase: str, attempts: int, meter: dict) -> tuple[dict, Path]:
    from .service import running_marker
    config = read_config(root)
    # The model and the process, so logs --usage can name one (#1974) and a
    # later run can tell this one died.
    record = {'id': 'run_' + uuid.uuid4().hex, 'started_at': now().isoformat(),
              'outcome': 'running', 'runner_attempts': attempts, 'usage': None,
              'sources': [], 'items': 0, 'changed': [], 'phase': phase,
              'harness': config['runner'], 'model': config['model'], 'speed': config['speed'],
              'quota': {'before': meter}, **running_marker()}
    path = state_path(root, f"runs/{record['id']}.json")
    write_json(path, record)
    return record, path


def _add_usage(total: dict, usage) -> dict:
    for key, value in (usage or {}).items():
        total[key] = total.get(key, 0) + value
    return total


def _record_scheduled_result(root: Path, result: dict, scheduled: bool) -> dict:
    """Keep worker health aligned with the whole scheduled pass, not just mail sync."""
    if scheduled and result['outcome'] == 'partial':
        worker_path = state_path(root, 'worker.json')
        worker = read_json(worker_path, {})
        maintenance = result.get('maintenance') or {}
        reason = 'the last scheduled investigation failed'
        if maintenance.get('outcome') == 'failed':
            reason = maintenance.get('error') or 'the last scheduled maintenance failed'
        write_json(worker_path, {**worker, 'last_scheduled_outcome': 'failed',
                                 'last_scheduled_reason': reason})
    return result


def run_daily(root: Path, *, days: int = 30, scheduled: bool = False,
              maintain=None, investigate_one=None, person_one=None, project_one=None, translate_one=None, say=None) -> dict | None:
    """One scheduled run. `investigate_one`, `person_one` and `project_one` replace
    the model calls in tests; `investigate_one` given alone takes every page the
    older way, as before this stage.

    `say` gets one line per step. Run off a terminal, a sync printed nothing
    for 25 minutes and everything at the end (#2033)."""
    say = say or (lambda text: None)
    say("Reading new material…")
    # The archive a sync resumes says its progress through `say` too (#2042).
    sync = maintain or (lambda root, **options: run_sync(root, say=say, **options))
    maintenance = sync(root, scheduled=True) if scheduled else sync(root)
    if maintenance is not None:
        say(f"New material: {maintenance.get('items', 0)} items, "
            f"{len(maintenance.get('changed') or [])} pages changed ({maintenance['outcome']})")
    if maintenance is None:
        return None
    from .runner import ready
    from .sessions import import_sessions, summarise_line, summarise_sessions, summary
    if "sessions" not in maintenance:
        maintenance["sessions"] = import_sessions(root, consented_only=True)
    say(summary(maintenance["sessions"]))
    config = read_config(root)
    if not ready(config)[0]:
        maintenance["sessions_summary"] = summarise_sessions(root, limit=40, say=say)
        say(summarise_line(maintenance["sessions_summary"]))
    with maintenance_lock(root):
        # The owner's languages follow what they wrote lately (languages.py).
        from .languages import refresh
        refresh(root)
    if maintenance['outcome'] not in ('completed', 'no_change'):
        _translate_changed(root, config, maintenance, maintenance.get('changed') or [], translate_one, say)
        return _record_scheduled_result(root, {'outcome': 'partial', 'maintenance': maintenance,
                                                'investigation': None}, scheduled)
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
        result = _follow_new(root, config, maintenance, remaining, meter, stop, previous,
                             person_one=person_one, project_one=project_one, say=say)
    else:
        result = _unfinished(root, config, maintenance, remaining, meter, stop, days,
                             investigate_one=investigate_one, person_one=person_one, say=say)
    changed = [*(maintenance.get('changed') or []), *((result.get('run') or {}).get('changed') or [])]
    _translate_changed(root, config, maintenance, changed, translate_one, say)
    return _record_scheduled_result(root, result, scheduled)


def _translate_changed(root, config, maintenance, changed, translate_one, say):
    """Cache this run's changed pages, sharing the existing maintenance lock."""
    from .languages import owner_languages
    from .runner import ready
    from .translate import cached, translate
    language = next((tag for tag in owner_languages(root)['languages'] if tag.split('-')[0].lower() != 'en'), None)
    if not language or not changed or ready(config)[0]:
        return
    with maintenance_lock(root):
        zone = ZoneInfo(config['schedule']['timezone']) if config['schedule']['timezone'] else timezone.utc
        today = now().astimezone(zone).date()
        spent = sum(log.get('runner_attempts', 0) for log in run_logs(root)
                    if log.get('phase') == 'daily-translation'
                    and datetime.fromisoformat(log['started_at']).astimezone(zone).date() == today)
        remaining = min(config['limits']['translations_per_day'] - spent,
                        config['limits']['runner_calls_per_day'] - status(root)['runner_attempts_today'])
        rows, attempts = [], 0
        record, path = _reserve(root, 'daily-translation', 0, {})
        for page in dict.fromkeys(changed):
            if cached(root, page, language) is not None:
                rows.append({'page': page, 'outcome': 'cached'})
                continue
            if attempts >= remaining:
                continue
            attempts += 1
            record.update(runner_attempts=attempts)
            write_json(path, record)
            say(f"Translating {page} into {language}…")
            try:
                (translate_one or translate)(root, page, language)
                rows.append({'page': page, 'outcome': 'translated'})
            except RemError as error:
                rows.append({'page': page, 'outcome': 'failed', 'error': str(error)})
                say(f"Translation failed for {page}: {error}")
            record['pages'] = rows
            write_json(path, record)
        report = {'language': language, 'pages': rows, 'runner_attempts': attempts}
        maintenance['translations'] = report
        record.update(**report, outcome='partial' if any(row['outcome'] == 'failed' for row in rows) else 'completed',
                      finished_at=now().isoformat())
        write_json(path, record)


def _unfinished(root, config, maintenance, remaining, meter, stop, days, *, investigate_one, person_one,
                say=lambda text: None):
    """The first run of the day: unfinished pages, most recent activity first."""
    resting = _found_nothing_lately(root)
    pages = [page for page in unfinished_by_recency(root) if page['path'] not in resting]
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
    calls, tried, done, usage, changed, failed = allocation, [], [], {}, [], False
    others, over_budget = 0, False
    try:
        clients = _clients(sources)
        for page in pages:
            target = page['path']
            if calls < 1 or (done and _stopped(root, config)):
                break
            # Each kind of page has its own investigator: skill pages went to the mail
            # search and came back nothing_found on 2026-10-11, 10-13 and 10-14.
            # `investigate_one` alone, in tests, takes every page the older way.
            route = 'older' if investigate_one is not None else _route(root, target)
            # The older investigation takes what is left of the portion and ends it.
            # The busiest page is also the one least likely to fit: a refusal
            # before any model call tries the next, up to three (#1670).
            if route == 'older' and others >= 3:
                continue
            say(f"Investigating {target}…")
            tried.append(target)
            try:
                result = _investigate_unfinished(root, route, page, clients=clients, sources=sources, days=days,
                                                 calls=calls, config=config, investigate_one=investigate_one,
                                                 person_one=person_one)
            except RemError as error:
                if route == 'older' and 'call budget' in str(error):
                    over_budget = True
                    continue
                # Nothing to write from is this page's answer, not the round's failure;
                # it is not asked again for a week. One stopped before any model call
                # costs the portion nothing (#1984), and takes no slot.
                free = isinstance(error, NothingFound) and not error.usage
                if isinstance(error, NothingFound) and not isinstance(error, NothingNew):
                    _remember_nothing_found(root, target)
                if route != 'older':
                    calls -= 0 if free else required
                elif not free:
                    others += 1
                    # A refused older investigation ends the portion, as an accepted one does.
                    calls = calls if isinstance(error, NothingFound) else 0
                _page_done(record, done, usage, say, {'page': target, 'outcome': _outcome(error),
                                                      'why': str(error)[:300]}, getattr(error, 'usage', None))
                continue
            if route == 'older':
                others += 1
                calls = 0
            else:
                calls -= required
            _page_done(record, done, usage, say, _accepted_row(target, result), result.get('usage'))
            changed += result.get('changed', [])
        accepted = [row['page'] for row in done if row['outcome'] == 'accepted']
        left = len(unfinished_by_recency(root))
        record.update(outcome='completed', usage=usage or None, changed=changed, tried=tried, pages=done,
                      left=left,
                      **({'record': accepted[-1]} if accepted else {'reason': _none_written(done, over_budget)}))
    except Exception as error:
        record.update(outcome='failed', error=str(error) if isinstance(error, RemError) else type(error).__name__,
                      usage=getattr(error, 'usage', None) or usage or None, tried=tried, pages=done)
        failed = True
    finally:
        record['finished_at'] = now().isoformat()
        record['quota']['after'] = quota.read(config)
        # A daily record had no duration, and sync printed "Seconds: Unknown" (#2044).
        record['seconds'] = round((datetime.fromisoformat(record['finished_at'])
                                   - datetime.fromisoformat(record['started_at'])).total_seconds(), 1)
        write_json(path, record)
    investigation = None if failed or not done else {'pages': done, 'left': record.get('left')}
    return {'outcome': 'partial' if failed else 'completed',
            'maintenance': maintenance, 'investigation': investigation, 'run': record}


def _route(root: Path, record: str) -> str:
    """Which investigator a page goes to: a person's, a skill's, the project writer's, or the older one."""
    if record.startswith('people/'):
        return 'person'
    if record.startswith('skills/catalog/'):
        return 'skill'
    from .project_pages import pending
    if record.startswith('projects/') and pending(root, record)[0]:
        return 'project'
    return 'older'


def _investigate_unfinished(root, route, page, *, clients, sources, days, calls, config, investigate_one,
                            person_one, retry_refused=False) -> dict:
    target = page['path']
    if route == 'person':
        return (person_one or _person)(root, {**page, 'retry_refused': retry_refused}, clients=clients,
                                       subscriptions=sources, max_calls=calls)
    if route == 'skill':
        from .skill_runs import investigate_skill_page
        return investigate_skill_page(root, target, [Path.home() / '.co' / 'evals'])
    if route == 'project':
        return _project(root, target, config=config)
    notebook = Notebook(root)
    text = notebook.read(target)
    title = next((line[2:] for line in text.splitlines() if line.startswith('# ')), target)
    person = next((p for p in notebook.people() if p['path'] == target), {})
    handles = list(dict.fromkeys([title, *person.get('emails', []), *person.get('aliases', [])]))
    return (investigate_one or investigate)(root, target, title, handles, days=days, clients=clients,
                                            subscriptions=sources, max_calls=calls,
                                            **({'retry_refused': True} if retry_refused else {}))


def _accepted_row(page: str, result: dict) -> dict:
    """An accepted page, with any round of it that was refused: those were dropped from
    the daily rows, so Briar's refused round (2026-10-12) showed as plainly accepted."""
    return {'page': page, 'outcome': 'accepted', 'evidence': result.get('evidence', []),
            'report': result.get('report', ''),
            **({'refused_rounds': result['refused_rounds']} if result.get('refused_rounds') else {})}


def _none_written(done: list[dict], over_budget: bool) -> str:
    """Why the first run accepted no page. It said `no_page_fits_budget` on 2026-10-13
    when every page tried had come back nothing_found."""
    outcomes = {row['outcome'] for row in done}
    if not done:
        return 'no_page_fits_budget' if over_budget else 'nothing_unfinished'
    if outcomes <= {'nothing_found', 'nothing_new'}:
        return 'nothing_found'
    return 'refused' if 'refused' in outcomes else 'failed'


# A page whose investigation found nothing to write from is not asked again for
# a week: on 2026-10-13 all three of the day's slots went to job-followup,
# x-reply and historical-notes, nothing was accepted, and orgs/connectonion-com
# was never reached.
NOTHING_FOUND = 'nothing-found.json'
NOTHING_FOUND_DAYS = 7


def _remember_nothing_found(root: Path, record: str) -> None:
    path = state_path(root, NOTHING_FOUND)
    write_json(path, {**read_json(path, {}), record: now().isoformat()})


def _found_nothing_lately(root: Path) -> set:
    cutoff = (now() - timedelta(days=NOTHING_FOUND_DAYS)).isoformat()
    return {record for record, at in read_json(state_path(root, NOTHING_FOUND), {}).items() if at > cutoff}


def _page_done(record: dict, done: list, usage: dict, say, row: dict, page_usage, kind: str = 'person') -> None:
    """One page finished: kept in the record, its tokens under its stage, and said now.

    Outcomes appeared only in the record dumped at the end of a sync (#2044),
    and a daily run's tokens had no stage in logs --usage (#2043).
    """
    done.append(row)
    _add_usage(usage, page_usage)
    if page_usage:
        stage = 'projects' if kind == 'project' else 'investigate'
        _add_usage(record.setdefault('usage_by_stage', {}).setdefault(stage, {}), page_usage)
    say(outcome_line(row))


def outcome_line(row: dict) -> str:
    """`Updated people/x.md (accepted)` / `Refused people/y.md: over 20,000 characters`."""
    page, outcome = row['page'], row['outcome']
    why = ' '.join(str(row.get('why') or '').split())
    why = why if len(why) <= 160 else why[:157].rsplit(' ', 1)[0] + '…'
    if outcome == 'accepted':
        return f"Updated {page} (accepted)"
    words = {'refused': 'Refused', 'failed': 'Failed', 'nothing_new': 'Nothing new for',
             'nothing_found': 'Nothing found for'}.get(outcome, outcome.capitalize())
    return f"{words} {page}" + (f": {why}" if why and outcome in ('refused', 'failed') else "")


def _outcome(error: RemError) -> str:
    """What one page's run came to, in the words logs use."""
    return ('nothing_new' if isinstance(error, NothingNew) else 'nothing_found' if isinstance(error, NothingFound)
            else 'refused' if 'rejected' in str(error) else 'failed')


def _stopped(root, config) -> str:
    """Before each further page: the weekly budget or the floor, read again."""
    meter = quota.read(config)
    return quota.blocks(meter, quota.points_spent(run_logs(root), meter), config['limits'])


def _person(root, row, *, clients, subscriptions, max_calls=None):
    from .people_pages import investigate_person
    return investigate_person(root, row, clients=clients, subscriptions=subscriptions, max_calls=max_calls)


def _project(root, record, *, config):
    from .project_pages import write_page
    return write_page(root, record, config=config)


def _follow_new(root, config, maintenance, remaining, meter, stop, previous, *, person_one, project_one,
                say=lambda text: None):
    """A later run: only people and projects with new material since the previous run."""
    from .people_pages import correspondents_since
    from .people_pages import queue as people_queue
    from .project_material import extract
    from .project_pages import queue as project_queue
    since = previous or (now() - timedelta(days=1)).isoformat()
    sources = subscriptions(root)
    clients = _clients(sources)
    # Step 1, no model: who has new material. One mailbox listing since the
    # last run says who wrote; new session lines are filed under their
    # project pages. Each person's own mail is gathered by the investigation.
    found = correspondents_since(root, clients, since=datetime.fromisoformat(since))
    extract(root, sources)
    rows = [{**row, 'kind': 'person'} for row in people_queue(root, since=since)
            if row['mode'] == 'update' or row['record'] in found['records']]
    rows += [{**row, 'kind': 'project'} for row in project_queue(root, since=since)]
    # Refused pages are retried once a day: from the material held for them when
    # a sync's maintenance refused them, otherwise by their own investigator.
    from .refusals import due_for_retry
    queued = {row['record'] for row in rows}
    rows += [{'record': record, 'kind': 'retry', 'mode': 'retry', 'last_activity': entry.get('at', ''),
              'entry': entry} for record, entry in due_for_retry(root).items()
             if record not in queued and Notebook(root).path(record).is_file()]
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
            say(f"Updating {row.get('record') or row.get('path')}…")
            try:
                if row['kind'] == 'person':
                    result = (person_one or _person)(root, row, clients=clients, subscriptions=sources)
                elif row['kind'] == 'retry':
                    result = _retry(root, row['record'], row['entry'], clients=clients, sources=sources,
                                    config=config, person_one=person_one)
                else:
                    result = (project_one or _project)(root, row['record'], config=config)
                _page_done(record, done, usage, say, {**_accepted_row(row['record'], result), 'mode': row['mode']},
                           result.get('usage'), row['kind'])
                changed += result.get('changed', [])
            except RemError as error:
                # One refused page does not stop the others; its material stays pending.
                _page_done(record, done, usage, say, {'page': row['record'], 'mode': row['mode'],
                                                      'outcome': _outcome(error), 'why': str(error)[:300]},
                           getattr(error, 'usage', None), row['kind'])
        left = len(rows) - sum(1 for row in done if row['outcome'] == 'accepted')
        record.update(outcome='completed', usage=usage or None, changed=changed, pages=done, left=left,
                      since=since, listed=found['listed'])
    except Exception as error:
        record.update(outcome='failed', error=str(error) if isinstance(error, RemError) else type(error).__name__,
                      usage=usage or None, pages=done)
        failed = True
    finally:
        record['finished_at'] = now().isoformat()
        record['quota']['after'] = quota.read(config)
        # A daily record had no duration, and sync printed "Seconds: Unknown" (#2044).
        record['seconds'] = round((datetime.fromisoformat(record['finished_at'])
                                   - datetime.fromisoformat(record['started_at'])).total_seconds(), 1)
        write_json(path, record)
    return {'outcome': 'partial' if failed else 'completed', 'maintenance': maintenance,
            'investigation': None if failed else {'pages': done, 'left': record.get('left')}, 'run': record}


def _retry(root, record, entry, *, clients, sources, config, person_one=None) -> dict:
    """One refused page, again. Stamped first, so a retry that crashes waits a day too."""
    from .refusals import mark_retried
    mark_retried(root, record)
    if entry.get('material'):
        return _maintain_again(root, record, entry, config)
    page = {'path': record, 'record': record, 'days': RETRY_DAYS}
    return _investigate_unfinished(root, _route(root, record), page, clients=clients, sources=sources,
                                   days=RETRY_DAYS, calls=None, config=config, investigate_one=None,
                                   person_one=person_one, retry_refused=True)


def _maintain_again(root, record, entry, config) -> dict:
    """The one-page maintenance turn a sync refused, from the material held for it."""
    from .refusals import forget_refusal
    from .runner import RunFailed
    from .service import READABLE, _hold_for_refused, _maintain_pages
    material = entry['material']
    kind = str(material[0].get('source', '')).split(':', 1)[0]
    with maintenance_lock(root):
        result = _maintain_pages(root, material, config, kind if kind in READABLE else '', [record])
        _hold_for_refused(root, result, material)
        if result['refused']:
            raise RunFailed(result['refusals'][0]['errors'][0], result.get('usage'))
        forget_refusal(root, record)
    return result
