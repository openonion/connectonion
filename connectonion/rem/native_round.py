"""The persisted daily phase cursor. Evidence is collected once, never replayed."""

import hashlib
import json
from pathlib import Path

from . import daily, extract, investigate, project_pages, runner, service, sessions, translate
from .config import read_config
from .files import Notebook, RemError, read_json, state_path, write_json


def scheduled_slot(root, config):
    worker = service.worker_state(root)
    slot = service.latest_slot(config, service.now() + service.EARLY_FIRE)
    if not worker.get("enabled") or slot is None or (worker.get("last_scheduled_slot") or "") >= slot.isoformat():
        return None
    return slot


def prepare(root, config, *, scheduled):
    moment = service.now()
    slot = scheduled_slot(root, config) if scheduled else None
    if scheduled and slot is None:
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
    from .people_basics import refresh as refresh_basics
    basics_changed = refresh_basics(root)
    batch["progress_before"] = read_json(state_path(root, "progress.json"), {})
    logs = service.run_logs(root)
    today, recent = service.runs_today(logs, service.notebook_zone(config))
    first = not any(row.get("phase") == "daily-investigation" for row in recent)
    phase = "daily-investigation" if first else "daily-update"
    cursor = {"phase": phase, "started_at": moment.isoformat(), "slot": slot.isoformat() if slot else None,
              "batch": batch, "batch_index": 0, "summaries": sessions._summary_candidates(root, 5),
              "jobs": _jobs(root, first, logs, sources), "job_index": 0, "current": None,
              "changed": basics_changed, "same_left": 3, "same_new_left": 10, "translations": [], "translated": 0, "sessions": imported}
    if not batch["done"] and batch["digested"] is not None:
        _digest(cursor, batch["digested"])
    record, path = daily._reserve(root, phase, 0, {}, moment=moment)
    record.update(outcome="pending", native_round=True)
    write_json(path, record)
    cursor["run"] = record
    write_json(state_path(root, "round.json"), cursor)
    return cursor


def _jobs(root, first, logs, sources):
    limit = read_config(root)["limits"]["jobs_per_round"]
    from datetime import datetime, timedelta
    from .people_pages import correspondents_since, queue as people_queue
    previous = max((row["started_at"] for row in logs if row.get("phase") in daily.PHASES),
                   default=(service.now() - timedelta(days=1)).isoformat())
    found = correspondents_since(root, daily._clients(sources), since=datetime.fromisoformat(previous), lock_held=True)
    if first:
        resting = daily._found_nothing_lately(root)
        return [{**row, "record": row["path"], "kind": daily._route(root, row["path"])}
                for row in daily.unfinished_by_recency(root) if row["path"] not in resting][:limit]
    rows = [{**row, "kind": "person"} for row in people_queue(root, since=previous)
            if row["mode"] == "update" or row["record"] in found["records"]]
    rows += [{**row, "kind": "project"} for row in project_pages.queue(root, since=previous)]
    from .refusals import due_for_retry
    queued = {row["record"] for row in rows}
    rows += [{"record": record, "kind": "retry", "entry": entry, "last_activity": entry.get("at", "")}
             for record, entry in due_for_retry(root).items() if record not in queued and Notebook(root).exists(record)]
    return (daily._owner_due(root) + rows)[:limit]


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
    if cursor["current"] and cursor["current"].get("finalized"):
        _finish_investigation(root, cursor)
    from . import same_person
    pair = next(iter(same_person.candidates(root, uninvestigated=True)), None) if cursor.get("same_new_left", 10) else None
    if pair and cursor["current"] is None:
        task = _task("same-person", same_person.prepare(root, pair, directory=directory), cursor, stage="same-person")
        task["early_pair"] = True
        return task
    while cursor["job_index"] < len(cursor["jobs"]):
        if "investigation_left" not in cursor:
            remaining = service.daily_cap(root)["remaining"]
            cursor["investigation_left"] = min(remaining, max(1, min(remaining - 2, daily.INVESTIGATION_CALLS)))
        if cursor["investigation_left"] <= 0:
            if cursor["current"] or cursor.get("project_quote"):
                return {"stop": "investigation portion cap reached; the next scheduled slot can resume this round"}
            cursor["job_index"] = len(cursor["jobs"])
            break
        task = _prepare_job(root, cursor, config, directory)
        if task:
            return task
    if cursor["summaries"]:
        rows = cursor["summaries"][:1]
        task = sessions.prepare(root, rows, config, directory=directory, native=True)
        task["before"] = {rows[0]["record"]: Notebook(root).read(rows[0]["record"])}
        files = read_json(state_path(root, "sessions.json"), {}).get("files", {})
        task["input_paths"] = [path for path, entry in files.items() if entry.get("session") == rows[0]["key"]]
        return _task("sessions", task, cursor, stage="sessions-summary", record=rows[0]["record"])
    pair = next(iter(same_person.candidates(root, uninvestigated=False)), None) if cursor["same_left"] else None
    if pair:
        return _task("same-person", same_person.prepare(root, pair, directory=directory), cursor, stage="same-person")
    if "translation_slot" not in cursor:
        slot = service.latest_slot(config, service.now() + service.EARLY_FIRE) if cursor["slot"] else None
        cursor["translation_slot"] = slot.isoformat() if slot else None
    from .languages import owner_languages
    zone = service.notebook_zone(config)
    _, today_runs = service.runs_today(service.run_logs(root), zone)
    translations_today = sum(row.get("runner_attempts", 0) for row in today_runs if row.get("phase") in ("daily-translation", "translate"))
    language = next((tag for tag in owner_languages(root)["languages"] if tag.split("-")[0] != "en"), None)
    for record in cursor["changed"] if language and translations_today < config["limits"]["translations_per_day"] else []:
        if record not in cursor["translations"] and translate.cached(root, record, language) is None:
            task = translate.prepare(root, record, language, directory=directory, native=True)
            return _task("translate", task, cursor, stage="translate", record=record)
    finish(root, cursor)
    return None


def translations_only(root, cursor):
    from . import same_person
    if (not cursor["batch"]["done"] or cursor["summaries"] or cursor["current"]
            or cursor["job_index"] < len(cursor["jobs"])):
        return False
    return not ((cursor.get("same_new_left", 10) and same_person.candidates(root, uninvestigated=True))
                or (cursor["same_left"] and same_person.candidates(root, uninvestigated=False)))


def defer_translations(root, cursor, reason):
    from .languages import owner_languages
    language = next((tag for tag in owner_languages(root)["languages"] if tag.split("-")[0] != "en"), None)
    pages = [{"page": record, "outcome": "skipped", "reason": reason}
             for record in cursor["changed"] if language and translate.cached(root, record, language) is None]
    cursor["run"]["translations"] = {"language": language, "pages": pages}
    finish(root, cursor)


def finish(root, cursor):
    cursor.update(done=True, pending=None)
    cursor["run"].update(outcome="completed", finished_at=service.now().isoformat(), changed=cursor["changed"])
    write_json(state_path(root, f"runs/{cursor['run']['id']}.json"), cursor["run"])
    if cursor["slot"]:
        write_json(state_path(root, "worker.json"), {**service.worker_state(root), "last_scheduled_slot": cursor["slot"],
                                                   "last_scheduled_outcome": "completed"})
    write_json(state_path(root, "round.json"), cursor)


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
    state.setdefault("before", book.read(record))
    if book.read(record) != state["before"]:
        raise RemError("Task input changed; preserve the current notebook. Run co rem next --discard")
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
    if inquiry.routing(root) and inquiry_phase != "render":
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
        raise RemError("Task input changed; preserve the current notebook. Run co rem next --discard")
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
    if handler == "translate":
        translate.check(prepared, output)
        return {}
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
        return {"changed": [receipt["record"]], "report": output["result"]}
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
    if receipt["handler"] == "sessions":
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
        retain_instruction_context(root, state["skill_items"], _source_ids([{"text": Notebook(root).read(state["record"])}]))
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


def _advance_batch(root, cursor, task, result):
    batch = cursor["batch"]
    if result.get("discarded"):
        batch["abandoned"] = True
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
    elif operation == "translate":
        cursor["translations"].append(task["record"])
        if not result.get("discarded"):
            cursor["translated"] += 1
    cursor["pending"] = None
    write_json(state_path(root, "round.json"), cursor)
