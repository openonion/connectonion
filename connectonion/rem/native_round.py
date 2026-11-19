"""The persisted daily phase cursor. Evidence is collected once, never replayed."""

import hashlib
import json
from pathlib import Path

from . import daily, extract, fetch_stalls, investigate, project_pages, runner, service, sessions, translate
from .config import read_config
from .files import Notebook, RemError, read_json, state_path, write_json


class RoundBlocked(RemError):
    """The round finished with nothing it could serve; `next` saves its calendar before reporting it."""


def scheduled_slot(root, config):
    worker = service.worker_state(root)
    slot = service.latest_slot(config, service.now() + service.EARLY_FIRE)
    if not worker.get("enabled") or slot is None or (worker.get("last_scheduled_slot") or "") >= slot.isoformat():
        return None
    return slot


def prepare(root, config, *, scheduled, carry=None):
    from .catchup import identity, limit_runs
    moment = service.now()
    slot = scheduled_slot(root, config) if scheduled else None
    if scheduled and slot is None:
        return {"reason": "not due"}
    if not state_path(root, "consent.json").is_file():
        raise RemError("Source access is not authorized yet; run co rem start")
    from .tidy import tidy
    from .languages import refresh
    from .project_material import extract as collect_projects
    service.refresh_init_mailboxes(root, lock_held=True)
    service._resume_archive(root)
    imported = sessions.import_sessions(root, consented_only=True, lock_held=True)
    tidy(root, lock_held=True)
    sources = service.subscriptions(root)
    collect_projects(root, sources, lock_held=True)
    project_pages.sync_project_repositories(root, now=moment)
    refresh(root)
    from .topic_map import backfill_topics
    # co rem next never calls a model: the native round reuses this week's proposal only.
    topics = backfill_topics(Notebook(root), lock_held=True)
    progress = read_json(state_path(root, "progress.json"), {})
    set_aside = []
    batch = _read_sources(root, service._selected_sources(root, ""), progress, config, set_aside)
    from .people_basics import refresh as refresh_basics
    basics_changed = refresh_basics(root) + project_pages.refresh_last_activity(root)
    # Skill call counts are a script over the session files, like the basics above:
    # only init and `co rem skills map` ran it, so counts froze on the day of init (#2950).
    from .skill_map import map_skills
    if Notebook(root).exists("skills/catalog/index.md"):  # refresh a mapped catalog; init makes one
        map_skills(Notebook(root), lock_held=True, subscriptions=sources)
    from .direct_send import refresh as set_direct_send
    basics_changed += set_direct_send(root, service.notebook_today(root).isoformat())
    batch["progress_before"] = read_json(state_path(root, "progress.json"), {})
    logs = service.run_logs(root)
    recent = limit_runs(root, logs, service.notebook_zone(config))
    first = not any(row.get("phase") == "daily-investigation" for row in recent)
    phase = "daily-investigation" if first else "daily-update"
    cursor = {"phase": phase, "started_at": moment.isoformat(), "slot": slot.isoformat() if slot else None,
              "batch": batch, "batch_index": 0, "summaries": sessions._summary_candidates(root, config["limits"]["summaries_per_round"]),
              "jobs": _queue(_with_parked(root, _with_waiting(root, _jobs(root, first, logs, sources, set_aside)))),
              "job_index": 0, "current": None,
              "changed": basics_changed + topics["created"], "topics": topics, "same_left": 3, "same_new_left": 10, "translations": [], "translated": 0, "sessions": imported,
              "mail_slot": slot.isoformat() if slot else None, "set_aside": set_aside, **identity(root)}
    if carry:
        # A fresh night reads sources again while keeping an unfinished page's
        # draft and remaining jobs. New mail can invalidate that draft as usual.
        carry['run'].update(outcome='partial', finished_at=moment.isoformat(), changed=carry['changed'])
        write_json(state_path(root, f"runs/{carry['run']['id']}.json"), carry['run'])
        jobs = {job['record']: job for job in carry['jobs'][carry['job_index']:]}
        # The pages that round passed over for a used share are not behind its index.
        for job in [*cursor['jobs'], *carry.get('waiting', [])]:
            jobs.setdefault(job['record'], job)
        # Task material is retained while its originating round is unfinished.
        # Keep that work's origin so cleanup cannot delete a carried inquiry plan.
        # The open page's draft belongs to the first job: it keeps that place.
        opened = bool(carry.get('current') or carry.get('project_quote'))
        cursor.update(started_at=carry['started_at'], jobs=_queue(list(jobs.values()), keep_first=opened),
                      current=carry.get('current'), project_quote=carry.get('project_quote'))
    if not batch["done"] and batch["digested"] is not None:
        _digest(cursor, batch["digested"])
    record, path = daily._reserve(root, phase, 0, {}, moment=moment)
    record.update(outcome="pending", native_round=True, batch=batch["record"])
    write_json(path, record)
    cursor["run"] = record
    write_json(state_path(root, "round.json"), cursor)
    return cursor


def read_new_mail(root, cursor, config, slot):
    """A round can run all day; each scheduled slot reads the next mailbox into it.

    Mail used to be read only when a round began, so a 14-hour round left every
    mailbox unread since morning. The batch runs before the round's remaining jobs.
    """
    # A slot's read is one source batch; the coding sessions are read when a round begins.
    stopped = fetch_stalls.stopped(root)
    selected = service._selected_sources(root, "")
    mailboxes = {name: source for name, source in selected.items() if source.get("kind") in service.MAIL_KINDS}
    usable = {name: source for name, source in mailboxes.items() if source["kind"] not in stopped}
    if mailboxes and not usable:
        # Every mailbox is stopped this turn: the slot reads nothing, not the sessions mid-round.
        cursor["mail_slot"] = slot.isoformat()
        return
    batch = _read_sources(root, usable or selected, read_json(state_path(root, "progress.json"), {}), config,
                          cursor.setdefault("set_aside", []))
    batch["progress_before"] = read_json(state_path(root, "progress.json"), {})
    cursor.update(batch=batch, batch_index=0, mail_slot=slot.isoformat())
    if batch["record"].get("items"):
        cursor["run"]["batch"] = batch["record"]
        write_json(state_path(root, f"runs/{cursor['run']['id']}.json"), cursor["run"])
    if not batch["done"] and batch["digested"] is not None:
        _digest(cursor, batch["digested"])


def _read_sources(root, selected, progress, config, set_aside):
    """One source batch; a mailbox whose read failed is recorded and not asked again this turn.

    prepare_sync already keeps one source's failure from ending the batch; without
    this the same failing mailbox was read again at every slot and every turn."""
    batch = service.prepare_sync(root, selected, progress, config)
    for row in batch["record"].get("source_failures", []):
        kind = selected.get(row["source"], {}).get("kind")
        if kind in service.MAIL_KINDS:
            reason = fetch_stalls.failure_in_words(row.get("error", ""), row.get("code", ""))
            set_aside.append(fetch_stalls.mailbox_down(root, kind, reason, "reading new mail"))
    return batch


def _admit_correspondents(root, sources, since, set_aside):
    """List who wrote since the last round; a mailbox that fails is stopped for the turn and the rest are listed."""
    from .people_pages import correspondents_since
    clients = {kind: client for kind, client in daily._clients(sources).items()
               if kind not in fetch_stalls.stopped(root)}
    while True:
        try:
            return correspondents_since(root, fetch_stalls.labelled(clients), since=since, lock_held=True)
        except Exception as error:  # noqa: BLE001 -- anything not a known mailbox's failure is re-raised
            reason, kind = fetch_stalls.failure(error), getattr(error, "rem_provider", None)
            if reason is None or kind not in clients:
                raise
            set_aside.append(fetch_stalls.mailbox_down(root, kind, reason, "listing new correspondents"))
            clients.pop(kind)


def prepare_translation_round(root, config, *, scheduled):
    slot = scheduled_slot(root, config) if scheduled else None
    if scheduled and slot is None:
        return {"reason": "not due"}
    record, path = daily._reserve(root, "daily-translation", 0, {})
    record.update(outcome="pending", native_round=True)
    write_json(path, record)
    return {"phase": "daily-translation", "started_at": service.now().isoformat(),
            "slot": slot.isoformat() if slot else None, "batch": {"done": True}, "summaries": [],
            "jobs": [], "job_index": 0, "current": None, "changed": [], "same_left": 0,
            "same_new_left": 0, "translations": [], "translated": 0, "run": record}


def _jobs(root, first, logs, sources, set_aside=None):
    from datetime import datetime, timedelta
    from .people_pages import queue as people_queue
    from .catchup import number
    previous = max((row["started_at"] for row in logs if row.get("phase") in daily.PHASES),
                   default=(service.now() - timedelta(days=1)).isoformat())
    _admit_correspondents(root, sources, datetime.fromisoformat(previous), [] if set_aside is None else set_aside)
    if first:
        resting = daily._found_nothing_lately(root)
        rows = [{**row, "record": row["path"], "kind": daily._route(root, row["path"])}
                for row in daily.unfinished_by_recency(root) if row["path"] not in resting]
        if number(root) is None:
            return daily._owner_due(root) + rows
    else:
        rows = [{**row, "kind": "person"} for row in people_queue(root)
                if row["mode"] == "full" or row["last_activity"] > previous]
        rows += [{**row, "kind": "project"} for row in project_pages.queue(root, since=previous, include_backlog=True, now=service.now())]
        queued = {row["record"] for row in rows}
        resting = daily._found_nothing_lately(root)
        rows += [{**row, "record": row["path"], "kind": daily._route(root, row["path"])}
                 for row in daily.unfinished_by_recency(root)
                 if not row["path"].startswith("people/") and row["path"] not in queued and row["path"] not in resting]
    from .refusals import due_for_retry, parked_waiting, waiting_for_material
    from .owner_today import investigated_today
    retries, parked, spent = due_for_retry(root), parked_waiting(root), waiting_for_material(root)
    owner_ran = investigated_today(root)  # the owner investigated it today: not again tonight (#3174)
    rows = [row for row in rows if row["record"] not in owner_ran]
    rows = [row for row in rows if row["record"] not in retries and row["record"] not in parked
            and (row["record"] not in spent or _newer(row.get("last_activity"), spent[row["record"]]))]
    rows += [{"record": record, "kind": "retry", "entry": entry, "last_activity": entry.get("at", "")}
             for record, entry in retries.items() if Notebook(root).exists(record)]
    return daily._owner_due(root) + rows


def _newer(activity, refused_at):
    """A page out of retries is listed again only by something that arrived after its last refusal."""
    from .people_pages import _stamp
    activity, refused_at = _stamp(activity), _stamp(refused_at)
    return bool(activity and refused_at and activity > refused_at)


def _with_parked(root, jobs):
    """Pages set aside on a mailbox failure wait for their retry time, then come back (fetch_stalls)."""
    waiting, due = fetch_stalls.waiting(root), fetch_stalls.due(root)
    jobs = [job for job in jobs if job["record"] not in waiting]
    queued = {job["record"] for job in jobs}
    return jobs + [job for record, job in due.items() if record not in queued]


# The pages a night's share did not reach, kept for the next round. Not under catchup/<night>/:
# the night that left them is not the night that reads them.
WAITING = "investigation-waiting.json"
SHARES = {"investigations": "investigations_per_night", "skill_pages": "skill_pages_per_night"}


def _share(job):
    # A refused page tried again takes its page's kind when prepared; it stays in the main share.
    return "skill_pages" if job.get("kind") == "skill" and not job.get("retry_refused") else "investigations"


def _queue(jobs, *, keep_first=False):
    """Skill pages after every other page, each group in the order it came."""
    head, rest = (jobs[:1], jobs[1:]) if keep_first else ([], jobs)
    return head + sorted(rest, key=lambda job: _share(job) == "skill_pages")


def _with_waiting(root, jobs):
    """The pages an earlier night's share did not reach and this round does not list, then its own listing.

    The listing alone would lose them: a later round of a day lists only people whose
    mail is newer than the last round, so a person passed over once was not listed again.
    They were due for something new, so they lead; a page listed again keeps the place
    this round gives it, and the backlog cannot push a person with new mail back for weeks."""
    queued, book = {job["record"] for job in jobs}, Notebook(root)
    waited = read_json(state_path(root, WAITING), {}).get("jobs", [])
    return [job for job in waited if job["record"] not in queued and book.exists(job["record"])] + jobs


def _night_shares(root, config):
    """(where tonight's served pages are kept, the pages): a night is the schedule's or one catchup night."""
    from .catchup import key, marker
    from .night_stats import _night_of
    day = key(root, _night_of(service.now(), service.notebook_zone(config)))
    path = marker(root, "investigation-night.json")
    saved = read_json(path, {})
    return path, saved if saved.get("day") == day else {"day": day, **{name: [] for name in SHARES}}


def _job_turn(root, cursor, config, directory):
    """The next investigation task within tonight's shares, or None once the queue has been walked."""
    path, served = _night_shares(root, config)
    while cursor["job_index"] < len(cursor["jobs"]):
        job = cursor["jobs"][cursor["job_index"]]
        share = _share(job)
        opened = cursor["current"] or cursor.get("project_quote")
        used = job["record"] not in served[share] and len(served[share]) >= config["limits"][SHARES[share]]
        if not opened and (used or cursor.get("investigation_held")):
            # Tonight's share is used, or the weekly investigation budget is spent: the page
            # waits for a later night and the round goes on. A page already open is finished.
            cursor.setdefault("waiting", []).append(job)
            cursor["job_index"] += 1
            continue
        if "investigation_left" not in cursor:
            cursor["investigation_left"] = PORTION
        if cursor["investigation_left"] <= 0:
            task = _between_portions(root, cursor, config, directory)
            if task:
                return task
            cursor["investigation_left"] = PORTION
        task = _guarded_job(root, cursor, config, directory)
        if task:
            # Only a page handed to the model uses the share; one parked or passed over does not.
            if job["record"] not in served[share]:
                served[share].append(job["record"])
                write_json(path, served)
            return task
        # A page passed over is passed over for good: a later page that hangs ends this
        # process before the round is saved, and the next call would prepare them all again.
        write_json(state_path(root, "round.json"), cursor)
    _keep_waiting(root, cursor, config, served)
    return None


def _keep_waiting(root, cursor, config, served):
    """Save the pages the shares did not reach, with the numbers status and catchup say in words."""
    waiting = cursor.get("waiting", [])
    counts = {name: {"done": len(served[name]), "limit": config["limits"][limit],
                     "waiting": sum(_share(job) == name for job in waiting)} for name, limit in SHARES.items()}
    held = {"held": cursor["investigation_held"]} if cursor.get("investigation_held") else {}
    write_json(state_path(root, WAITING), {"night": served["day"], "jobs": waiting, **counts, **held})


def _waiting(root, night):
    """What the last walked queue saved, or {} when that was not `night`'s round."""
    saved = read_json(state_path(root, WAITING), {})
    return {} if night is not None and saved.get("night") != night else saved


def waiting_shares(root, *, night=None):
    """What the last walked queue left waiting for a used share, or {}.

    Empty while the weekly budget held that queue: its pages waited for the budget,
    and "0 of tonight's 12 investigations done" would read as a share that was used."""
    saved = _waiting(root, night)
    return {} if not saved or saved.get("held") else {name: saved[name] for name in SHARES}


def hold_in_words(root, *, night=None, **now):
    """'investigation is waiting for its weekly budget (…); 40 pages wait', or '' when it is not held.

    Over once the week has reset, whether or not a round has walked the queue since.
    `held=` (status) is the hold as the week's points count now, or None: the sentence a
    round saved is that round's count. 2026-11-17: status said "38 of 35 points used"
    here and "14.3 of 35" on its Budget line, a day after the count was corrected."""
    saved = _waiting(root, night)
    held = now["held"] if "held" in now else saved.get("held")
    if not held or (held["until"] and held["until"] <= service.now().timestamp()):
        return ""
    count = len(saved.get("jobs", []))
    return held["reason"] + (f"; {count} {'page waits' if count == 1 else 'pages wait'}" if count else "")


def shares_in_words(shares, whose="tonight's"):
    """'12 of tonight's 12 investigations done; 319 wait for later nights', for each share that left pages."""
    nouns = {"investigations": "investigations", "skill_pages": "skill pages"}
    return [f"{row['done']} of {whose} {row['limit']} {nouns[name]} done; "
            f"{row['waiting']} {'waits' if row['waiting'] == 1 else 'wait'} for later nights"
            for name, row in shares.items() if row["waiting"]]


def _task(handler, task, cursor, *, stage, record="", number=0, operation=""):
    phases = {"sessions": "sessions-summary", "same-person": "same-person", "translate": "daily-translation",
              "draft": "reply-draft", "tag": "tag"}
    return {"handler": handler, "task": task, "stage": stage, "record": record, "round": number,
            "operation": operation or handler,
            "phase": "sync" if operation == "batch" else phases.get(handler, cursor["phase"])}


def prepare_batch(root, cursor, config, directory):
    """The round's next source-batch task, or None once the batch is done and its progress saved."""
    batch = cursor["batch"]
    if batch["done"]:
        return None
    if read_json(state_path(root, "progress.json"), {}) != batch["progress_before"]:
        raise RemError("Source progress changed between tasks; run co rem next --discard")
    if batch["record"]["extracted"] and batch["digested"] is None:
        task = extract.prepare(batch["items"], config, batch["kind"], root=root, directory=directory, native=True)
        return _task("extract", task, cursor, stage="extract", operation="batch")
    leads = batch["leads"] or [None]
    if cursor["batch_index"] < len(leads) and batch["items"]:
        record = leads[cursor["batch_index"]]
        items = batch["items"]
        if record:
            page = {"role": "page", "record": record, "source": "investigation:page", "one_page": True,
                    "timestamp": service.now().isoformat(), "text": Notebook(root).read(record)}
            items = [page, *(i for i in items if not i.get("feedback_revision")
                            or record in i["feedback_pending_targets"])]
        task = runner.prepare(Notebook(root), items, config, batch["kind"], directory=directory, native=True)
        return _task("runner", task, cursor, stage="maintain", record=record, operation="batch")
    batch["done"] = True
    if not batch.get("abandoned"):
        if read_json(state_path(root, "progress.json"), {}) != batch["progress_before"]:
            raise RemError("Source progress changed between tasks; run co rem next --discard")
        write_json(state_path(root, "progress.json"), batch["updated"])
    extract.forget_digest(root)
    return None


def _progress_not_saved(root, cursor, batch):
    """An abandoned batch leaves the scan point where it was; its run record says so, and why.

    2026-11-16: the save was skipped without a word, so the same 40 mails were read five
    times in a day and status could only say the mailbox was "not read since" nine days ago.
    Said when the batch is abandoned: a discarded extract closes the batch at once."""
    batch["record"]["progress_not_saved"] = batch["abandoned_reason"]
    cursor["run"]["batch"] = batch["record"]
    write_json(state_path(root, f"runs/{cursor['run']['id']}.json"), cursor["run"])


def prepare_task(root, cursor, config, directory):
    _reset_attempts(root, cursor)
    task = prepare_batch(root, cursor, config, directory)
    if task:
        return task
    if cursor["phase"] == "daily-translation":
        task = prepare_translation(root, cursor, config, directory)
        if not task:
            finish(root, cursor)
        return task
    if cursor["current"] and cursor["current"].get("finalized"):
        # A named step: a deadline here parks this page and moves the round on (#3128). Unnamed, the stall
        # parked nothing and every later call finished the same page again.
        from .native import progress_step
        record = cursor["current"]["record"]
        progress_step(f"finishing {record}", round=cursor["started_at"], job_index=cursor["job_index"], record=record)
        _finish_investigation(root, cursor)
    from . import same_person
    # Same-person checks are investigation runs (quota.INVESTIGATION_PHASES): they wait with it.
    held = cursor.get("investigation_held")
    pair = (next(iter(same_person.candidates(root, uninvestigated=True)), None)
            if cursor.get("same_new_left", 10) and not held else None)
    if pair and cursor["current"] is None:
        task = _task("same-person", same_person.prepare(root, pair, directory=directory), cursor, stage="same-person")
        task["early_pair"] = True
        return task
    from . import drafts, night
    rows = night.prepare(root, config, attempted=cursor.get("draft_attempts", []),
                         fetches=cursor.setdefault("night_fetches", {}))
    if rows:
        row = rows[0]
        task = drafts.prepare(root, row, config, directory=directory)
        return _task("draft", task, cursor, stage="reply-draft", record=row["id"])
    from .tasks import auto_dispatch
    auto_dispatch(root, config)
    readmitted = fetch_stalls.readmit(root, {job["record"] for job in cursor["jobs"][cursor["job_index"]:]})
    if readmitted:
        # readmit has already dropped their hold on disk: a call that ends here must not lose them.
        cursor["jobs"] += readmitted
        write_json(state_path(root, "round.json"), cursor)
    task = _job_turn(root, cursor, config, directory)
    if task:
        return task
    task = _summary_turn(root, cursor, config, directory) or prepare_abstract(root, cursor, config, directory)
    if task:
        return task
    pair = next(iter(same_person.candidates(root, uninvestigated=False)), None) if cursor["same_left"] and not held else None
    if pair:
        return _task("same-person", same_person.prepare(root, pair, directory=directory), cursor, stage="same-person")
    if "translation_slot" not in cursor:
        slot = service.latest_slot(config, service.now() + service.EARLY_FIRE) if cursor["slot"] else None
        cursor["translation_slot"] = slot.isoformat() if slot else None
    task = _closing_translation(root, cursor, config, directory) or _closing_tags(root, cursor, config, directory)
    if task:
        return task
    from .night import listing
    parked = fetch_stalls.last_night(root)
    reasons = [row['reason'] for row in listing(root)
               if row['kind'] == 'could_not_prepare' and 'no longer exists' in row['reason']]
    if cursor.get('served_turn') != fetch_stalls._turn() and ((parked or {}).get('parked') or reasons):
        pages = [f"{row['record']}: {row.get('error') or fetch_stalls.PHRASES[row['reason']]}"
                 for row in (parked or {}).get('parked', [])]
        cursor['blocked_reason'] = 'All remaining candidates are parked: ' + '; '.join(pages + reasons)
    finish(root, cursor)
    if cursor.get('blocked_reason'):
        raise RoundBlocked(cursor['blocked_reason'])
    return None


def _summary_turn(root, cursor, config, directory):
    """The next session summary of the round's (`limits.summaries_per_round`), or None when none waits."""
    # A session still being written changes under its task: wait for a later round (#3099).
    cursor["summaries"] = [row for row in cursor["summaries"] if not sessions.being_written(root, row["key"])]
    if not cursor["summaries"]:
        return None
    rows = cursor["summaries"][:1]
    task = sessions.prepare(root, rows, config, directory=directory, native=True)
    task["before"] = {rows[0]["record"]: Notebook(root).read(rows[0]["record"])}
    files = read_json(state_path(root, "sessions.json"), {}).get("files", {})
    task["input_paths"] = [path for path, entry in files.items() if entry.get("session") == rows[0]["key"]]
    return _task("sessions", task, cursor, stage="sessions-summary", record=rows[0]["record"])


def prepare_abstract(root, cursor, config, directory):
    """Reserve slices until two consecutive empty rounds, exhaustion or the nightly cap."""
    from .captured_decisions import material
    from .night_stats import _night_of
    from .catchup import identity, key, marker
    day = key(root, _night_of(service.now(), service.notebook_zone(config)))
    path = marker(root, "abstract-night.json")
    saved = read_json(path, {})
    if saved.get("day") != day:
        saved = {}
    rounds = saved.get("rounds", 1) if saved.get("day") == day else 0
    if rounds >= config["limits"]["abstract_rounds_per_night"] or (rounds and saved.get("stopped", True)):
        return None
    items = material(Notebook(root), config, attempted=saved.get("attempted", []))
    if not items:
        return None
    prepared = runner.prepare(Notebook(root), items, config, stage="abstract", directory=directory, native=True)
    prepared.update(abstract_night=day, abstract_round=rounds + 1, **identity(root))
    # Count reservations before execution: an unfinished turn must survive a restart
    # without admitting another slice. A durable outcome reopens it unless two were empty.
    write_json(path, {**saved, "day": day, "rounds": rounds + 1, "stopped": True})
    return _task("runner", prepared, cursor, stage="abstract", operation="abstract")


def record_abstract_result(root, prepared, *, promoted, deferred=False):
    """Record a reservation once, keeping empty slices aside until the next night."""
    from .captured_decisions import slice_key
    from .catchup import marker
    path = marker(root, "abstract-night.json", night=prepared.get('catchup_night'))
    saved = read_json(path, {})
    if (prepared.get("abstract_night") and saved.get("day") == prepared["abstract_night"]
            and saved.get("rounds", 1) == prepared.get("abstract_round", 1)
            and saved.get("result_round") != saved.get("rounds", 1)):
        empty = 0 if promoted else saved.get("empty_rounds", 0) + 1
        attempted = saved.get("attempted", [])
        if not promoted or deferred:
            attempted += [slice_key(item) for item in prepared.get("items", [])]
        write_json(path, {**saved, "empty_rounds": empty, "stopped": empty >= 2,
                            "attempted": attempted, "result_round": saved.get("rounds", 1),
                            "set_aside": saved.get("set_aside", 0) + deferred})


def _reset_attempts(root, cursor):
    from .catchup import key
    day = key(root, service.notebook_today(root))
    if cursor.get("task_day") != day:
        cursor.update(task_day=day, draft_attempts=[], translation_attempts=[], night_fetches={})
        # A round that crosses midnight reads Today again: yesterday's rows are not today's.
        cursor.pop("shown_today", None)


# D-104: a portion interleaves the night's work and never stops it. After PORTION
# investigation turns the other stages take their turn (`_between_portions`), then
# investigation resumes in the same turn.
# 2: one investigation turn measured 20 to 60 minutes on a real notebook, and a
# 3-hour catchup night completed one page (2026-11-16). At 8 turns the first Abstract
# round and the first translation were 3 to 8 hours into a night, so any night cut
# short (a deadline, the quota floor, two faults, the 3-hour turn) left them at 0.
# After 2 turns they are reached in the first 40 minutes to 2 hours.
PORTION = 2


def _between_portions(root, cursor, config, directory):
    """Between two portions of investigation: one session summary, one Abstract round, one tag turn, then translation's share.

    Each of them used to wait for the whole night's share of investigations (12 pages
    of many turns each), so a night that was cut short had only investigated. Abstract
    stays within `abstract_rounds_per_night` and the round's summaries are still five:
    what a break serves is not served again by the round's closing steps.
    `portions` counts the breaks begun; whoever runs whole rounds starts the round's
    one deepen slot once the first has been served (`schedule.early_depth`)."""
    if "between" not in cursor:
        cursor["between"] = ["sessions", "abstract", "tag"]
        cursor["portions"] = cursor.get("portions", 0) + 1
    while cursor["between"]:
        step = {"sessions": _summary_turn, "abstract": prepare_abstract,
                "tag": prepare_tagging}[cursor["between"].pop(0)]
        task = step(root, cursor, config, directory)
        if task:
            return task
    # Translation's share is sized from its backlog (D-71: "翻译…应该安排的轮次不够多").
    task = _translation_turn(root, cursor, config, directory)
    if task:
        return task
    cursor.pop("between")
    return None


def translations_waiting(root):
    """Page translations waiting, over every language but English."""
    # Only the count matters here, so Today's order is not asked for.
    return sum(len(translate.backlog(root, tag)) for tag in translate.languages(root)
               if tag.split("-")[0].lower() != "en")


def translation_share(root):
    """Translation turns per portion: a tenth of the pages waiting, at least 10, never more than wait.

    It was a fiftieth, at least 4: 7 turns of under a minute beside two investigation
    turns of 20 to 60 minutes each (owner, 2026-11-17: "schedule more of them per batch")."""
    waiting = translations_waiting(root)
    return min(waiting, max(10, -(-waiting // 10)))


def _closing_translation(root, cursor, config, directory):
    """After the queue, translation goes on until no page waits; `prepare_translation` holds the bound.

    It took one share, like a portion's, because an unbounded pass over 361 pages kept
    the round from completing and Deepen started only after a completed round. One share
    a night was 9, 8, 9 and 0 pages of some 350 over four nights (2026-11-17), at under a
    minute a page. Deepen no longer waits for it: `closing` is what `schedule._depth_early`
    reads to start the slot of a round that had no portion of investigation."""
    task = prepare_translation(root, cursor, config, directory)
    if task:
        cursor["closing"] = True
    return task


def _translation_turn(root, cursor, config, directory):
    cursor.setdefault("translation_left", translation_share(root))
    task = prepare_translation(root, cursor, config, directory) if cursor["translation_left"] > 0 else None
    if task:
        cursor["translation_left"] -= 1
        return task
    cursor.pop("translation_left")
    return None


def prepare_translation(root, cursor, config, directory):
    _reset_attempts(root, cursor)
    # A round's stated end, between portions and after the queue alike: how many pages
    # it left waiting is kept for the night's line.
    if len(cursor.get("translations", [])) >= config["limits"]["translations_per_round"]:
        cursor.setdefault("translations_waiting", translations_waiting(root))
        return None
    # The owner's one-click job is translating the same pages: the night's pass stands aside.
    if translate.claimed(root):
        return None
    # Today's pages lead; its queue reads the whole notebook, so it is computed once per round, not per turn.
    if "shown_today" not in cursor:
        cursor["shown_today"] = translate.shown_today(root)
    for language in translate.languages(root):
        if language.split("-")[0].lower() == "en":
            continue
        attempted = cursor.get("translation_attempts", [])
        room = min(translate.BATCH, config["limits"]["translations_per_round"] - len(cursor.get("translations", [])))
        records = [record for record in translate.backlog(root, language, changed=cursor["changed"],
                                                          shown=cursor["shown_today"])
                   if [language, record] not in attempted][:room]
        if records:
            task = translate.prepare_batch(root, records, language, directory=directory)
            return _task("translate", task, cursor, stage="translate", record=records[0] if len(records) == 1 else "")
    return None


def _closing_tags(root, cursor, config, directory):
    """After the closing translation, tag turns go on until no page waits; `prepare_tagging` holds the bound."""
    task = prepare_tagging(root, cursor, config, directory)
    if task:
        cursor["closing"] = True
    return task


def prepare_tagging(root, cursor, config, directory):
    """The next batch of pages waiting for tags, or None: none waits, or the round offered its
    `limits.tags_per_round`. A batch offered once is not offered again in the same round,
    so a reply the review refuses cannot hold the round (docs/cli/rem-tags.md)."""
    from . import tag_stage
    attempted = cursor.setdefault("tag_attempts", [])
    room = config["limits"]["tags_per_round"] - len(attempted)
    waiting = [record for record in tag_stage.candidates(root) if record not in set(attempted)]
    if room <= 0:
        cursor.setdefault("tags_waiting", len(waiting))
        return None
    records = waiting[:min(room, tag_stage.BATCH)]
    if not records:
        return None
    attempted += records
    task = tag_stage.prepare(root, records, directory=directory, native=True)
    return _task("tag", task, cursor, stage="tag")


def finish(root, cursor):
    from .night_stats import recent
    cursor.update(done=True, pending=None)
    outcome = 'failed' if cursor.get('blocked_reason') else 'completed'
    cursor["run"].update(outcome=outcome, finished_at=service.now().isoformat(), changed=cursor["changed"],
                         night=recent(root, nights=1)[0])
    if cursor.get('blocked_reason'):
        cursor['run']['reason'] = cursor['blocked_reason']
    write_json(state_path(root, f"runs/{cursor['run']['id']}.json"), cursor["run"])
    if cursor["slot"]:
        write_json(state_path(root, "worker.json"), {**service.worker_state(root), "last_scheduled_slot": cursor["slot"],
                                                   "last_scheduled_outcome": outcome})
    write_json(state_path(root, "round.json"), cursor)


def _guarded_job(root, cursor, config, directory):
    """A mailbox failing while one page is prepared sets that page aside; the round goes on.

    2026-11-12: a Graph 404 and then a ReadTimeout on one person's page left
    co rem next before the cursor was saved, so 30 turns in a row tried the
    same page and ended with no task."""
    index = cursor["job_index"]
    job = cursor["jobs"][index]
    from .refusals import parked_waiting
    if cursor["current"] is None and not cursor.get("project_quote") and job["record"] in parked_waiting(root):
        # Parked since this round listed it (a preparation that passed its deadline): not in this round.
        cursor["job_index"] = index + 1
        return None
    held = _stopped_mailboxes(root, job) if cursor["current"] is None else {}
    if held:
        # Not asked again this turn; the page comes back next round with no back-off.
        fetch_stalls.hold(root, job, held)
        cursor["job_index"] = index + 1
        return None
    try:
        task = _prepare_job(root, cursor, config, directory)
    except Exception as error:  # noqa: BLE001 -- park() returns None for anything not a mailbox's: re-raised
        notice = fetch_stalls.park(root, job, error)
        if notice is None:
            raise
        cursor.setdefault("set_aside", []).append(notice)
        cursor.update(job_index=index + 1, current=None, project_quote=None)
        return None
    fetch_stalls.clear(root, job["record"])
    return task


def _stopped_mailboxes(root, job):
    """The mailboxes stopped for this turn that this page's investigation would ask."""
    # A retry with held material reads that material, not a mailbox; every page that is
    # investigated reads each connected mailbox (by address, or by name when it has none).
    reads_mail = job["kind"] not in ("project", "skill") and not (job["kind"] == "retry" and job["entry"].get("material"))
    stopped = fetch_stalls.stopped(root) if reads_mail else {}
    return {kind: why for kind, why in stopped.items() if kind in daily._clients(service.subscriptions(root))}


def _prepare_job(root, cursor, config, directory):
    job = cursor["jobs"][cursor["job_index"]]
    record, book = job["record"], Notebook(root)
    from .native import progress_step
    progress_step(f"preparing {record}", round=cursor["started_at"], job_index=cursor["job_index"], record=record)
    if job["kind"] == "retry":
        from .refusals import mark_retried
        mark_retried(root, record)
        if job["entry"].get("material"):
            return _retry_task(root, cursor, config, directory, job)
        job.update(kind=daily._route(root, record), days=daily.RETRY_DAYS, retry_refused=True)
    if job["kind"] == "project":
        return _project_task(root, cursor, config, directory, record)
    if (cursor["current"] and cursor["current"].get("before", book.read(record)) != book.read(record)
            and not _carried_past_basics(book, cursor["current"])):
        # The page changed under its open investigation (mail read while the floor held
        # the round, or the owner): investigate it again from the page as it is now.
        cursor["current"] = None
    if cursor["current"] is None:
        cursor["current"] = _prepare_investigation(root, cursor, job, directory)
        if cursor["current"] is None:
            cursor["job_index"] += 1
            return None
    state = cursor["current"]
    state.setdefault("before", book.read(record))
    page = {**state["page"], "text": state.get("draft", state["before"])}
    items = investigate.prepare_round(book, state, page=page) if not state.get("tail") else None
    if items is None:
        items = _followup_items(book, state)
    if items is None:
        if state.get("draft") and not state.get("finalized"):
            return _final_investigation(book, cursor, config, directory, state)
        _finish_investigation(root, cursor)
        return None
    items += state.get("research", [])
    task_inputs = state.get("input_paths", [])
    from . import inquiry
    inquiry_phase = state.get("inquiry", "plan")
    if inquiry.inquiry_routed(root) and inquiry_phase != "render":
        task = inquiry.prepare(root, directory, items, config, inquiry_phase, plan_path=state.get("plan_path"), native=True)
        task["before"] = {record: book.read(record)}
        return _task("inquiry", task, cursor, stage=inquiry_phase, record=record,
                     number=state["number"], operation="inquiry")
    task = runner.prepare(book, items, config, stage="investigate", directory=directory, native=True)
    task["draft_only"] = True
    task["draft_before"] = state.get("draft", state["before"])
    task["prior_items"] = [item for part in state["parts"][:state["number"] - 1] for item in part]
    Path(task["candidate"]).write_text(state.get("draft", state["before"]), encoding="utf-8")
    task["input_paths"] = task_inputs
    if state.get("findings_path"):
        task["prompt"] += f"\nRead inquiry findings at {state['findings_path']}."
        task["input_paths"].append(state["findings_path"])
    return {**_task("runner", task, cursor, stage="investigate", record=record,
                    number=state["number"], operation="investigation"), "pass": state.get("tail", "parts")}


def _carried_past_basics(book, state):
    """Keep an accepted draft when the only change to its page is the contact script's own.

    2026-11-16 (#3083): a person's parts pass was accepted, the night ended, and the
    next night's preparation filled Last contact with a mail the draft had already
    read. That rewrite alone restarted the page at parts round 1: 2,158 s and 10.75M
    tokens over three turns. When the script applied to the page the draft started
    from gives the page as it is now, nothing else changed; the same script is
    applied to the draft, as it is to every page after promotion, and the round goes
    on to its next pass. Any other change is still read again from the start."""
    from .people_basics import fill
    record, page = state["record"], book.read(state["record"])
    if not state.get("draft") or fill(book, record, state["before"]) != page:
        return False
    state.update(before=page, draft=fill(book, record, state["draft"]))
    return True


def _retry_task(root, cursor, config, directory, job):
    prepared = daily.prepare_retry(root, job["record"], job["entry"], config)
    if prepared is None:
        cursor["job_index"] += 1
        return None
    page = {"role": "page", "record": job["record"], "source": "investigation:page", "one_page": True,
            "text": Notebook(root).read(job["record"])}
    task = runner.prepare(Notebook(root), [page, *prepared["material"]], config,
                          prepared["kind"] if prepared["kind"] in service.READABLE else "",
                          directory=directory, native=True)
    prepared["progress_before"] = read_json(state_path(root, "progress.json"), {})
    task["retry"] = prepared
    return _task("runner", task, cursor, stage="maintain", record=job["record"], operation="retry")


def _prepare_investigation(root, cursor, job, directory):
    from .native import preparation_stage
    record = job["record"]
    if job['kind'] == 'owner':
        from .catchup import key, marker
        write_json(marker(root, 'owner-refresh.json'), {'date': key(root, service.notebook_today(root))})
    if job["kind"] == "skill":
        from . import skill_runs
        prepared = skill_runs.prepare(root, record, [Path.home() / ".co/evals"], directory=directory, lock_held=True)
        return {"record": record, "parts": [prepared["items"][1:]], "context": [], "page": prepared["items"][0],
                "number": 1, "multi": False, "edited": False, "ledgers": [], "leads": [], "changed": [],
                "refused_sources": [], "refused_rounds": [], "searched": ["skill source", "retained evals"],
                "repository_items": [], "session_items": [], "skill_records": prepared["skill_records"],
                "input_paths": [prepared["source_path"]], "skill_items": [*prepared["items"], *prepared["references"]]}
    try:
        title, handles = investigate.page_handles(Notebook(root), record)
        return investigate.investigate(
            root, record, title, job.get("addresses") or handles, days=job.get("days", 30),
            clients=fetch_stalls.labelled(daily._clients(service.subscriptions(root))),
            subscriptions=service.subscriptions(root),
            sent_only=job["kind"] == "owner", rounds=job.get("rounds"), retry_refused=job.get("retry_refused", False),
            prepare_only=True, lock_held=True, directory=directory, stage_progress=preparation_stage)
    except investigate.NothingFound as error:
        if not isinstance(error, investigate.NothingNew):
            daily._remember_nothing_found(root, record)
        cursor.setdefault("skipped", []).append({"record": record, "reason": str(error)})
        return None


def _followup_items(book, state):
    record = state["record"]
    if state.get("append"):
        return None  # An append ends with its parts: no editing or quote turn rewrites lines it did not touch (#3105).
    page = state.get("draft", book.read(record))
    if not state.get("tail"):
        state["tail"] = "editing" if state["multi"] else "quotes"
    if state["tail"] == "editing":
        items = investigate.prepare_editing(book, record, state["context"], page=page)
        if items:
            return items
        state["tail"] = "quotes"
    if state["tail"] == "quotes" and record.startswith("people/"):
        owner = (read_json(state_path(book.root, "map.json"), {}).get("owner") or {}).get("record")
        target = 3 if record == owner else 2
        counts = investigate.falls_short(page, min_insight=target)
        if counts:
            return investigate.prepare_quotes(book, record, state["parts"], counts, state["context"], insight_target=target, page=page)
    return None


def _final_investigation(book, cursor, config, directory, state):
    record = state["record"]
    items = [{**state["page"], "text": state["draft"]}, *state["context"],
             {"role": "round", "source": "investigation:round", "text": "\n\n".join(state["ledgers"])},
             *(item for part in state["parts"] for item in part), *state.get("research", [])]
    task = runner.prepare(book, items, config, stage="investigate", directory=directory, native=True)
    task["before"] = {record: state["before"]}
    task["input_paths"] = state.get("input_paths", [])
    Path(task["candidate"]).write_text(state["draft"], encoding="utf-8")
    task["prompt"] = f"Investigation rounds are complete. Submit {task['candidate']} for the final claim audit. " + runner.today_note(book.root)
    return {**_task("runner", task, cursor, stage="investigate", record=record,
                   number=state["number"], operation="investigation"), "pass": "final"}


def _project_task(root, cursor, config, directory, record):
    previous = cursor.get("project_quote")
    if not previous:
        task = project_pages.prepare(root, record, config=config, directory=directory, native=True)
        task["draft_only"] = True
        return _task("project", task, cursor, stage="investigate", record=record)
    if "draft" not in previous:  # A pre-upgrade task already passed its audit and wrote the page.
        previous["draft"] = Notebook(root).read(record)
        if previous["draft"] == previous["before"][record]:
            cursor["job_index"] += 1
            cursor["project_quote"] = None
            return None
        previous["before"] = {record: previous["draft"]}
        if project_pages.project_falls_short(previous["draft"], sum(i.get("role") == "user" for i in previous["items"])) is None:
            _finish_project(root, cursor, record, previous["through"])
            return None
    if Notebook(root).read(record) != previous["before"][record]:
        cursor["project_quote"] = None  # the page changed under it: write it again from the page as it is now
        return _project_task(root, cursor, config, directory, record)
    items = previous["items"]
    counts = project_pages.project_falls_short(previous["draft"], sum(i.get("role") == "user" for i in items))
    if counts is None or previous.get("quotes_done"):
        task = {**previous, "directory": str(directory), "candidate": str(directory / "candidate.md"), "draft_only": False}
        Path(task["candidate"]).write_text(previous["draft"], encoding="utf-8")
        task["prompt"] = f"Investigation rounds are complete. Submit {task['candidate']} for the final claim audit. " + runner.today_note(root)
        return _task("project", task, cursor, stage="investigate", record=record, operation="project-final")
    task = project_pages.prepare_quotes(Notebook(root), record, items, counts, directory=directory, config=config,
                                        native=True, page=previous["draft"])
    task["through"] = previous["through"]
    task["draft_only"] = True
    return _task("project", task, cursor, stage="investigate", record=record, operation="project-quote")


def _finish_project(root, cursor, record, through):
    from .project_material import page_state
    from .refusals import forget_refusal
    previous = cursor["project_quote"]
    items = previous["items"]
    timestamps = [item["timestamp"] for item in items if item.get("role") == "user" and item.get("timestamp")]
    through = min(through, max(timestamps))
    messages = sum(item.get("role") == "user" and item.get("timestamp", "") <= through for item in items)
    project_pages.mark_written(root, record, through, inputs_read=messages,
                               inputs_available=len(project_pages.pending(root, record)[0]))
    forget_refusal(root, record)
    Notebook(root).note_pass(record, "written", "own messages")
    cursor["job_index"] += 1
    cursor["project_quote"] = None


def check_task(root, task, output):
    handler, prepared = task["handler"], task["task"]
    if handler == "draft":
        from . import drafts
        plan = drafts.check(prepared, output)
        current = next((row for row in drafts.candidates(root) if row["id"] == plan["id"]), None)
        if not current or current["version"] != plan["version"] or drafts.closed(root, current):
            return {"discarded": "Reply thread changed; a fresh draft is queued", "changed": []}
        return _commit(root, task, plan, {"draft": plan["id"]})
    if handler == "extract":
        return extract.check(prepared, output)
    if handler == "sessions":
        result = sessions.check(prepared, output)
        plan = sessions.prepare_summaries(root, result["summaries"], read_config(root))
        result["changed"] = [entry["snapshot"]["record"] for entry in plan["entries"]]
        return _commit(root, task, plan, result)
    if handler == "inquiry":
        from . import inquiry
        return {"value": inquiry.check(prepared, output)}
    if handler == "translate" and "pages" in prepared:
        result = translate.check_batch(prepared, output)
        return {"translated_records": result["translated"], "refused_pages": result["refused"]}
    if handler == "translate":  # a one-page task prepared before batches (#3099)
        translate.check(prepared, output)
        return {}
    if handler == "tag":
        from . import tag_stage
        plan = tag_stage.check(root, prepared, output)
        return {"changed": tag_stage.promote(root, plan), "tagged": len(plan["pages"]), "refused_tags": plan["refused"]}
    if handler == "same-person":
        from . import same_person
        plan = same_person.prepare_verdict(prepared, output)
        return _commit(root, task, plan, plan["result"])
    if task.get("pass") == "editing":
        before = prepared.get("draft_before", prepared["before"][task["record"]])
        candidate = Path(prepared["candidate"])
        if candidate.is_file() and investigate._cut_too_much(before, candidate.read_text()):
            raise runner.RunFailed("Editing round cut the lead or a third of the page; fix the candidate")
        if candidate.is_file():
            candidate.write_text(investigate.keep_editing(before, candidate.read_text()), encoding="utf-8")
    if handler == "project":
        result = project_pages.check(prepared, output, lock_held=True, native=True)
    else:
        result = runner.check(prepared, output, maintenance_lock_held=True, automatic_repairs=False, native=True)
    if isinstance(result, dict) and result.get("needs_review"):
        return result
    if isinstance(result, dict) and result.get("no_change"):
        return {"changed": [], "no_change": True, "report": output["result"]}
    if prepared.get("draft_only"):
        from .evidence import additional_research
        return {"changed": [], "draft": Path(prepared["candidate"]).read_text(encoding="utf-8"),
                "research": additional_research(root, Path(task["directory"]), prepared["items"]), "report": output["result"]}
    record = task["record"]
    receipt = read_json(Path(task["directory"]) / "promotion.json", {})
    if not record and receipt:
        from .native import _recovered_result
        return {**_recovered_result(root, task), "report": output["result"]}
    changed = [record] if record and Notebook(root).read(record) != prepared["before"][record] else []
    return {"changed": changed, "report": output["result"],
            "review_candidates": read_json(Path(task["directory"]) / "review-candidates.json", [])}


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _summary_outputs(root, plan):
    from .project_material import SECRET_SHAPES, REDACTED
    outputs = {state_path(root, "session-tags.json"): [_json_text(plan["tags"])]}
    for entry in plan["entries"]:
        saved, snapshot = entry["saved"], entry["snapshot"]
        outputs[sessions.summary_path(root, saved["key"])] = [_json_text(saved)]
        outputs[Notebook(root).path(snapshot["record"])] = [entry["page"]]
        for message in snapshot["messages"]:
            source = message["source"]
            path = state_path(root, "session-sources/" + hashlib.sha256(source.encode()).hexdigest() + ".json")
            outputs[path] = [_json_text({"source": source, "text": SECRET_SHAPES.sub(REDACTED, message["text"]),
                "timestamp": message.get("timestamp") or "", "input_scope": message.get("input_scope") or ""})]
    return outputs


def _merge_outputs(root, plan):
    from . import merge, same_person
    outputs = {state_path(root, same_person.VERDICTS): [_json_text(plan["verdicts"])]}
    if plan["merge"] is None:
        return outputs
    merged, book = plan["merge"], Notebook(root)
    outputs.update({book.path(merged["kept"]): [merged["page"]], book.path(merged["old"]): [None],
                    root / merged["aliases"][merged["old"]]["archived"]: [book.read(merged["old"])],
                    state_path(root, merge.ALIASES): [_json_text(merged["aliases"])]})
    for record, text in merged["relinked"].items():
        outputs.setdefault(book.path(record), []).append(text)
    return outputs


def _commit(root, task, plan, result):
    from .native import _hash
    if task["handler"] == "draft":
        from . import drafts
        plan = {**plan, "status": drafts.prepared_status(plan), "prepared_at": service.now().isoformat()}
        outputs = {drafts.path(root, plan["id"]): [_json_text(plan)]}
    else:
        outputs = _summary_outputs(root, plan) if task["handler"] == "sessions" else _merge_outputs(root, plan)
    files = {str(path): {"before": _hash(path),
             "after": [hashlib.sha256(text.encode()).hexdigest() if text is not None else None for text in texts]}
             for path, texts in outputs.items()}
    write_json(Path(task["directory"]) / "commit.json",
               {"handler": task["handler"], "plan": plan, "result": result, "files": files})
    return recover_commit(root, task)


def recover_commit(root, task):
    from .native import _hash
    receipt = read_json(Path(task["directory"]) / "commit.json", None)
    if receipt is None:
        return None
    current = {path: _hash(Path(path)) for path in receipt["files"]}
    if any(current[path] not in [state["before"], *state["after"]] for path, state in receipt["files"].items()):
        raise RemError("Committed task output changed; preserve the current notebook. Run co rem next --discard")
    if all(current[path] == state["after"][-1] for path, state in receipt["files"].items()):
        return receipt["result"]
    if receipt["handler"] == "draft":
        from . import drafts
        write_json(drafts.path(root, receipt["plan"]["id"]), receipt["plan"])
    elif receipt["handler"] == "sessions":
        sessions.promote_summaries(root, receipt["plan"])
    elif receipt["handler"] == "same-person":
        from . import same_person
        same_person.promote_verdict(root, receipt["plan"])
    return receipt["result"]


def _digest(cursor, notes):
    batch = cursor["batch"]
    batch["digested"] = notes
    batch["items"] = [] if notes.strip() == extract.NOTHING else [extract.extraction_item(notes, batch["items"])]


def _finish_investigation(root, cursor):
    state = cursor["current"]
    investigate.record_result(root, Notebook(root), state["record"], [], state["searched"],
                              changed=bool(state["changed"]), repository_items=state["repository_items"],
                              session_items=state["session_items"], skill_records=state.get("skill_records", []), lock_held=True)
    if state["record"].startswith("people/"):
        from datetime import datetime
        from .people_pages import mark_investigated
        mark_investigated(root, state["record"], datetime.fromisoformat(cursor["started_at"]), lock_held=True)
    if state.get("skill_items") and state["changed"]:
        from .skill_runs import retain_instruction_context
        from .reader_model import _source_ids
        retain_instruction_context(root, state["skill_items"], _source_ids([{"text": Notebook(root).read(state["record"])}]),
                                   lock_held=True)
    from .refusals import remember_refusal, forget_refusal
    if state["refused_sources"]:
        remember_refusal(root, state["record"], state["refused_sources"], state["refused_rounds"][-1], stage="investigation round")
    else:
        forget_refusal(root, state["record"])
    cursor["current"] = None
    cursor["job_index"] += 1


def _finish_feedback(root, progress, before, items, task, result):
    from . import feedback
    checkpoint = Path(task["directory"]) / "feedback-checkpoint.json"
    applied = read_json(checkpoint, None)
    current = read_json(state_path(root, "progress.json"), {})
    if applied is not None and current == applied:
        return applied
    if current != before:
        raise RemError("Source progress changed; preserve the current checkpoint and run co rem next --discard")
    feedback.finish(root, progress, items, task["record"], result, checkpoint=checkpoint)
    return read_json(state_path(root, "progress.json"), {})


def _parked_lead(task):
    """One page of the batch was parked: the batch was read, and that page's material is in the ledger.

    2026-11-16: a parked page abandoned its whole batch, so one page that could not pass
    its claim audit sent the same 40 mails through extract and maintain again every round.
    A discarded extract, a task discarded for any other reason and a parked task with no
    page of its own still abandon the batch: nothing holds their material."""
    return bool(task.get("parked") and task["handler"] != "extract" and task.get("record"))


def _advance_batch(root, cursor, task, result):
    batch = cursor["batch"]
    if result.get("discarded") and not _parked_lead(task):
        batch.update(abandoned=True, abandoned_reason=result["discarded"])
        _progress_not_saved(root, cursor, batch)
        if task["handler"] == "extract":
            batch["done"] = True
    elif batch["selected_feedback"] and task["record"]:
        batch["updated"] = _finish_feedback(root, batch["updated"], batch["progress_before"],
                                            batch["selected_feedback"], task, result)
        batch["progress_before"] = batch["updated"]
    if task["handler"] == "extract" and not result.get("discarded"):
        _digest(cursor, result["notes"])
    else:
        cursor["batch_index"] += 1


def _advance_retry(root, cursor, task, result):
    if not result.get("discarded"):
        from .refusals import forget_refusal
        retry = task["task"]["retry"]
        if retry["managed"]:
            _finish_feedback(root, retry["progress"], retry["progress_before"], retry["material"], task, result)
        forget_refusal(root, task["record"])
    cursor["job_index"] += 1


def _advance_investigation(cursor, task, result):
    state = cursor["current"]
    if task.get("pass") == "final":
        state["changed"] = result.get("changed", [])
        state["finalized"] = not result.get("discarded")
        if result.get("discarded"):
            state.pop("draft", None)
        return
    if "draft" in result:
        state["draft"] = result["draft"]
        state.setdefault("research", []).extend(result.get("research", []))
        result = {**result, "changed": [state["record"]] if result["draft"] != state["before"] else []}
    if result.get("discarded"):
        from .refusals import material_sources
        if state["number"] <= len(state["parts"]):
            state["refused_sources"] += material_sources(state["parts"][state["number"] - 1])
        state["refused_rounds"].append(result["discarded"])
    investigate.check_round(state, result)
    state["inquiry"] = "plan"
    state.pop("findings_path", None)
    if task.get("pass") in ("editing", "quotes"):
        state["tail"] = "quotes" if task["pass"] == "editing" else "done"


def _remember_maintenance(root, task, result):
    if task["operation"] in ("batch", "retry") and task["record"] and not result.get("discarded") and not result.get("refused"):
        from .leads import remember_no_change
        remember_no_change(root, task["record"], task["record"] not in result.get("changed", []))


def advance(root, cursor, task, result):
    from .reviews import ingest
    ingest(root, result.get("review_candidates", []))
    cursor["changed"] = sorted({*cursor["changed"], *result.get("changed", [])})
    _remember_maintenance(root, task, result)
    operation = task["operation"]
    if operation == "batch":
        _advance_batch(root, cursor, task, result)
    elif operation == "sessions":
        cursor["summaries"] = cursor["summaries"][1:]
    elif operation == "retry":
        _advance_retry(root, cursor, task, result)
    elif operation == "inquiry":
        state = cursor["current"]
        stage = task["task"]["stage"]
        state["inquiry"] = "synthesize" if stage == "plan" else "render"
        state["plan_path" if stage == "plan" else "findings_path"] = task["candidate"]
    elif operation == "investigation":
        _advance_investigation(cursor, task, result)
    elif operation == "project":
        if result.get("discarded") or result.get("no_change"):
            cursor["job_index"] += 1
        else:
            cursor["project_quote"] = dict(task["task"])
            if "draft" in result:
                cursor["project_quote"]["draft"] = result["draft"]
            cursor["project_quote"]["items"] += result.get("research", [])
    elif operation == "project-quote":
        cursor["project_quote"].update(quotes_done=True)
        if "draft" in result:
            cursor["project_quote"]["draft"] = result["draft"]
            cursor["project_quote"]["items"] += result.get("research", [])
    elif operation == "project-final":
        if result.get("changed") and not result.get("discarded"):
            _finish_project(root, cursor, task["record"], task["task"]["through"])
        else:
            cursor["job_index"] += 1
            cursor["project_quote"] = None
    elif operation == "same-person":
        key = "same_new_left" if task.get("early_pair") else "same_left"
        cursor[key] = cursor.get(key, 10) - 1
        if task.get("early_pair") and result.get("kept"):
            from .people_pages import FIRST_WINDOW_DAYS
            jobs = {}
            for job in cursor["jobs"][cursor["job_index"]:]:
                if job["record"] in result["pages"]:
                    job = {**job, "record": result["kept"], "days": FIRST_WINDOW_DAYS}
                jobs.setdefault(job["record"], job)
            cursor.update(jobs=list(jobs.values()), job_index=0)
    elif operation == "draft":
        row = task["task"]["row"]
        cursor.setdefault("draft_attempts", []).append([row["id"], row["version"]])
        if not result.get("discarded"):
            from .approvals import send_direct
            send_direct(root, row["id"])  # only a send=now reply to a partner/close person; 10-minute Undo
    elif operation == "tag":
        cursor["tagged"] = cursor.get("tagged", 0) + result.get("tagged", 0)
    elif operation == "translate":
        # A page the batch's review refused is set aside for this round like a parked one-page task;
        # the backlog offers it again in the next round.
        records = task["task"].get("records") or [task["record"]]
        cursor["translations"] += records
        cursor.setdefault("translation_attempts", []).extend([task["task"]["language"], record] for record in records)
        if not result.get("discarded"):
            cursor["translated"] += len(result.get("translated_records", records))
    cursor["pending"] = None
    write_json(state_path(root, "round.json"), cursor)
