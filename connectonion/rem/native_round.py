"""The persisted daily phase cursor. Evidence is collected once, never replayed."""

from pathlib import Path

from . import daily, extract, investigate, project_pages, runner, service, sessions, translate
from .config import read_config
from .files import Notebook, RemError, read_json, state_path, write_json


def prepare(root, config, *, scheduled):
    worker, moment = service.worker_state(root), service.now()
    slot = service.latest_slot(config, moment + service.EARLY_FIRE) if scheduled else None
    if scheduled and (not worker.get("enabled") or slot is None or worker.get("last_scheduled_slot")
                      and worker["last_scheduled_slot"] >= slot.isoformat()):
        return {"reason": "not due"}
    if not state_path(root, "consent.json").is_file():
        raise RemError("Source access is not authorized yet; run co rem start")
    from .tidy import tidy
    from .languages import refresh
    from .project_material import extract as collect_projects
    imported = sessions.import_sessions(root, consented_only=True, lock_held=True)
    tidy(root, lock_held=True)
    sources = service.subscriptions(root)
    collect_projects(root, sources, lock_held=True)
    refresh(root)
    progress = read_json(state_path(root, "progress.json"), {})
    batch = service.prepare_sync(root, service._selected_sources(root, ""), progress, config)
    batch["progress_before"] = read_json(state_path(root, "progress.json"), {})
    logs = service.run_logs(root)
    today, recent = service.runs_today(logs, service.notebook_zone(config))
    first = not any(row.get("phase") == "daily-investigation" for row in recent)
    phase = "daily-investigation" if first else "daily-update"
    cursor = {"phase": phase, "started_at": moment.isoformat(), "slot": slot.isoformat() if slot else None,
              "batch": batch, "batch_index": 0, "summaries": sessions._summary_candidates(root, 40),
              "jobs": _jobs(root, first, logs, sources), "job_index": 0, "current": None,
              "changed": [], "same_left": 3, "translations": [], "translated": 0, "sessions": imported}
    if not batch["done"] and batch["digested"] is not None:
        _digest(cursor, batch["digested"])
    record, path = daily._reserve(root, phase, 0, {}, moment=moment)
    record.update(outcome="pending", native_round=True)
    write_json(path, record)
    cursor["run"] = record
    write_json(state_path(root, "round.json"), cursor)
    return cursor


def _jobs(root, first, logs, sources):
    if first:
        resting = daily._found_nothing_lately(root)
        return [{**row, "record": row["path"], "kind": daily._route(root, row["path"])}
                for row in daily.unfinished_by_recency(root) if row["path"] not in resting]
    from datetime import datetime, timedelta
    from .people_pages import correspondents_since, queue as people_queue
    previous = max((row["started_at"] for row in logs if row.get("phase") in daily.PHASES),
                   default=(service.now() - timedelta(days=1)).isoformat())
    found = correspondents_since(root, daily._clients(sources), since=datetime.fromisoformat(previous))
    rows = [{**row, "kind": "person"} for row in people_queue(root, since=previous)
            if row["mode"] == "update" or row["record"] in found["records"]]
    rows += [{**row, "kind": "project"} for row in project_pages.queue(root, since=previous)]
    from .refusals import due_for_retry
    queued = {row["record"] for row in rows}
    rows += [{"record": record, "kind": "retry", "entry": entry, "last_activity": entry.get("at", "")}
             for record, entry in due_for_retry(root).items() if record not in queued and Notebook(root).exists(record)]
    return (daily._owner_due(root) + sorted(rows, key=lambda row: row.get("last_activity", ""), reverse=True))[:daily.UPDATE_PAGES]


def _task(handler, task, cursor, *, stage, record="", number=0, operation=""):
    phases = {"sessions": "sessions-summary", "same-person": "same-person", "translate": "daily-translation"}
    return {"handler": handler, "task": task, "stage": stage, "record": record, "round": number,
            "operation": operation or handler,
            "phase": "sync" if operation == "batch" else phases.get(handler, cursor["phase"])}


def prepare_task(root, cursor, config, directory):
    batch = cursor["batch"]
    if not batch["done"]:
        if read_json(state_path(root, "progress.json"), {}) != batch["progress_before"]:
            raise RemError("Source progress changed between tasks; run co rem next --discard")
        if batch["record"]["extracted"] and batch["digested"] is None:
            task = extract.prepare(batch["items"], config, batch["kind"], root=root, directory=directory)
            task["summary"] = False
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
    if cursor["summaries"]:
        rows = cursor["summaries"][:1]
        task = sessions.prepare(root, rows, config, directory=directory)
        task["prompt"] += f"\nWrite the requested JSON to {task['candidate']}."
        task["before"] = {rows[0]["record"]: Notebook(root).read(rows[0]["record"])}
        return _task("sessions", task, cursor, stage="sessions-summary", record=rows[0]["record"])
    while cursor["job_index"] < len(cursor["jobs"]):
        if "investigation_left" not in cursor:
            remaining = service.daily_cap(root)["remaining"]
            cursor["investigation_left"] = min(remaining, max(1, min(remaining - 2, daily.INVESTIGATION_CALLS)))
        if cursor["investigation_left"] <= 0:
            if cursor["current"]:
                return {"stop": "investigation portion cap reached; the next scheduled slot can resume this round"}
            cursor["job_index"] = len(cursor["jobs"])
            break
        task = _prepare_job(root, cursor, config, directory)
        if task:
            return task
    from . import same_person
    pair = next(iter(same_person.candidates(root)), None) if cursor["same_left"] else None
    if pair:
        return _task("same-person", same_person.prepare(root, pair, directory=directory), cursor, stage="same-person")
    from .languages import owner_languages
    zone = service.notebook_zone(config)
    _, today_runs = service.runs_today(service.run_logs(root), zone)
    translations_today = sum(row.get("runner_attempts", 0) for row in today_runs if row.get("phase") in ("daily-translation", "translate"))
    language = next((tag for tag in owner_languages(root)["languages"] if tag.split("-")[0] != "en"), None)
    for record in cursor["changed"] if language and translations_today < config["limits"]["translations_per_day"] else []:
        if record not in cursor["translations"] and translate.cached(root, record, language) is None:
            task = translate.prepare(root, record, language, directory=directory)
            return _task("translate", task, cursor, stage="translate", record=record)
    cursor.update(done=True, pending=None)
    cursor["run"].update(outcome="completed", finished_at=service.now().isoformat(), changed=cursor["changed"])
    write_json(state_path(root, f"runs/{cursor['run']['id']}.json"), cursor["run"])
    if cursor["slot"]:
        write_json(state_path(root, "worker.json"), {**service.worker_state(root), "last_scheduled_slot": cursor["slot"],
                                                   "last_scheduled_outcome": "completed"})
    write_json(state_path(root, "round.json"), cursor)
    return None


def _prepare_job(root, cursor, config, directory):
    job = cursor["jobs"][cursor["job_index"]]
    record, book = job["record"], Notebook(root)
    if job["kind"] == "retry":
        from .refusals import mark_retried
        mark_retried(root, record)
        if job["entry"].get("material"):
            return _retry_task(root, cursor, config, directory, job)
        job.update(kind=daily._route(root, record), days=daily.RETRY_DAYS, retry_refused=True)
    if job["kind"] == "project":
        return _project_task(root, cursor, config, directory, record)
    if cursor["current"] is None:
        cursor["current"] = _prepare_investigation(root, cursor, job, directory)
        if cursor["current"] is None:
            cursor["job_index"] += 1
            return None
    state = cursor["current"]
    items = investigate.prepare_round(book, state) if not state.get("tail") else None
    if items is None:
        items = _followup_items(book, state)
    if items is None:
        _finish_investigation(root, cursor)
        return None
    task_inputs = state.get("input_paths", [])
    from . import inquiry
    inquiry_phase = state.get("inquiry", "plan")
    if inquiry.routing(root) and inquiry_phase != "render":
        task = inquiry.prepare(root, directory, items, config, inquiry_phase, plan_path=state.get("plan_path"))
        task["before"] = {record: book.read(record)}
        return _task("inquiry", task, cursor, stage=inquiry_phase, record=record,
                     number=state["number"], operation="inquiry")
    task = runner.prepare(book, items, config, stage="investigate", directory=directory, native=True)
    task["input_paths"] = task_inputs
    if state.get("findings_path"):
        task["prompt"] += f"\nRead inquiry findings at {state['findings_path']}."
        task["input_paths"].append(state["findings_path"])
    return {**_task("runner", task, cursor, stage="investigate", record=record,
                    number=state["number"], operation="investigation"), "pass": state.get("tail", "parts")}


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
    task["retry"] = prepared
    return _task("runner", task, cursor, stage="maintain", record=job["record"], operation="retry")


def _prepare_investigation(root, cursor, job, directory):
    record = job["record"]
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
            clients=daily._clients(service.subscriptions(root)), subscriptions=service.subscriptions(root),
            sent_only=job["kind"] == "owner", rounds=job.get("rounds"), retry_refused=job.get("retry_refused", False),
            prepare_only=True, lock_held=True, directory=directory)
    except investigate.NothingFound as error:
        if not isinstance(error, investigate.NothingNew):
            daily._remember_nothing_found(root, record)
        cursor.setdefault("skipped", []).append({"record": record, "reason": str(error)})
        return None


def _followup_items(book, state):
    record = state["record"]
    if not state.get("tail"):
        state["tail"] = "editing" if state["multi"] else "quotes"
    if state["tail"] == "editing":
        items = investigate.prepare_editing(book, record, state["context"])
        if items:
            return items
        state["tail"] = "quotes"
    if state["tail"] == "quotes" and record.startswith("people/"):
        owner = (read_json(state_path(book.root, "map.json"), {}).get("owner") or {}).get("record")
        target = 3 if record == owner else 2
        counts = investigate.falls_short(book.read(record), min_insight=target)
        if counts:
            return investigate.prepare_quotes(book, record, state["parts"], counts, state["context"], insight_target=target)
    return None


def _project_task(root, cursor, config, directory, record):
    previous = cursor.get("project_quote")
    if not previous:
        task = project_pages.prepare(root, record, config=config, directory=directory)
        return _task("project", task, cursor, stage="investigate", record=record)
    items = previous["items"]
    counts = project_pages.project_falls_short(Notebook(root).read(record), sum(i.get("role") == "user" for i in items))
    if counts is None:
        _finish_project(root, cursor, record, previous["through"])
        return None
    task = project_pages.prepare_quotes(Notebook(root), record, items, counts, directory=directory, config=config)
    task["through"] = previous["through"]
    return _task("project", task, cursor, stage="investigate", record=record, operation="project-quote")


def _finish_project(root, cursor, record, through):
    from .project_material import page_state
    from .refusals import forget_refusal
    previous = cursor["project_quote"]
    items = previous["items"]
    messages = sum(item.get("role") == "user" for item in items)
    project_pages.mark_written(root, record, through, inputs_read=messages,
                               inputs_available=len(project_pages.pending(root, record)[0]))
    forget_refusal(root, record)
    Notebook(root).note_pass(record, "written", "own messages")
    cursor["job_index"] += 1
    cursor["project_quote"] = None


def check_task(root, task, output):
    handler, prepared = task["handler"], task["task"]
    if handler == "extract":
        return extract.check(prepared, output)
    if handler == "sessions":
        result = sessions.check(prepared, output)
        result["changed"] = sessions._save_summaries(root, result["summaries"], read_config(root))
        return result
    if handler == "inquiry":
        from . import inquiry
        return {"value": inquiry.check(prepared, output)}
    if handler == "translate":
        translate.check(prepared, output)
        return {}
    if handler == "same-person":
        from . import same_person
        return same_person.check(prepared, output, lock_held=True)
    if task.get("pass") == "editing":
        before = prepared["before"][task["record"]]
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
    record = task["record"]
    receipt = read_json(Path(task["directory"]) / "promotion.json", {})
    if not record and receipt:
        return {"changed": [receipt["record"]], "report": output["result"]}
    changed = [record] if record and Notebook(root).read(record) != prepared["before"][record] else []
    return {"changed": changed, "report": output["result"],
            "review_candidates": read_json(Path(task["directory"]) / "review-candidates.json", [])}


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
        retain_instruction_context(root, state["skill_items"], _source_ids([{"text": Notebook(root).read(state["record"])}]))
    from .refusals import remember_refusal, forget_refusal
    if state["refused_sources"]:
        remember_refusal(root, state["record"], state["refused_sources"], state["refused_rounds"][-1], stage="investigation round")
    else:
        forget_refusal(root, state["record"])
    cursor["current"] = None
    cursor["job_index"] += 1


def advance(root, cursor, task, result):
    from .reviews import ingest
    ingest(root, result.get("review_candidates", []))
    cursor["changed"] = sorted({*cursor["changed"], *result.get("changed", [])})
    operation = task["operation"]
    if operation == "batch":
        batch = cursor["batch"]
        if result.get("discarded"):
            batch["abandoned"] = True
            if task["handler"] == "extract":
                batch["done"] = True
        elif batch["selected_feedback"] and task["record"]:
            if read_json(state_path(root, "progress.json"), {}) != batch["progress_before"]:
                raise RemError("Source progress changed; preserve the current checkpoint and run co rem next --discard")
            from . import feedback
            feedback.finish(root, batch["updated"], batch["selected_feedback"], task["record"], result)
            batch["progress_before"] = read_json(state_path(root, "progress.json"), {})
        if task["handler"] == "extract" and not result.get("discarded"):
            _digest(cursor, result["notes"])
        else:
            cursor["batch_index"] += 1
    elif operation == "sessions":
        cursor["summaries"] = cursor["summaries"][1:]
    elif operation == "retry":
        if not result.get("discarded"):
            from . import feedback
            from .refusals import forget_refusal
            retry = task["task"]["retry"]
            if retry["managed"]:
                feedback.finish(root, retry["progress"], retry["material"], task["record"], result)
            forget_refusal(root, task["record"])
        cursor["job_index"] += 1
    elif operation == "inquiry":
        state = cursor["current"]
        stage = task["task"]["stage"]
        state["inquiry"] = "synthesize" if stage == "plan" else "render"
        state["plan_path" if stage == "plan" else "findings_path"] = task["candidate"]
    elif operation == "investigation":
        state = cursor["current"]
        if result.get("discarded"):
            from .refusals import material_sources
            state["refused_sources"] += material_sources(state["parts"][state["number"] - 1]) if state["number"] <= len(state["parts"]) else []
            state["refused_rounds"].append(result["discarded"])
        investigate.check_round(state, result)
        state["inquiry"] = "plan"
        state.pop("findings_path", None)
        if task.get("pass") in ("editing", "quotes"):
            state["tail"] = "quotes" if task["pass"] == "editing" else "done"
    elif operation == "project":
        if result.get("discarded"):
            cursor["job_index"] += 1
        else:
            cursor["project_quote"] = task["task"]
    elif operation == "project-quote":
        _finish_project(root, cursor, task["record"], task["task"]["through"])
    elif operation == "same-person":
        cursor["same_left"] -= 1
    elif operation == "translate":
        cursor["translations"].append(task["record"])
        cursor["translated"] += 1
    cursor["pending"] = None
    write_json(state_path(root, "round.json"), cursor)
