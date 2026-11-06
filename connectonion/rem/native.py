"""A native session supplies model output between explicit prepare/check calls."""

import hashlib
import json
import math
import os
import re
import shlex
import shutil
import sys
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import yaml

from . import quota, runner, service
from .config import read_config
from .daily import record_cap_stop
from .files import WRITE_WAIT_SECONDS, Notebook, RemError, atomic_write, maintenance_lock, read_json, state_path, write_json


SCHEDULED_CONTINUATION = (
    "Do the printed task (its Now step when shown), submit it, then run next again.\n"
    "Read material in pieces with rg/sed, write the candidate, run the submit command, then run next again.\n"
    "Keep going until next says the round is done or stopped."
)
AUDIT_BATCH_SIZE = 8


def pending(root):
    task_id = read_json(state_path(root, "round.json"), {}).get("pending")
    task = read_json(state_path(root, f"tasks/{task_id}/task.json"), {}) if task_id else {}
    return [task] if task.get("status") == "pending" else []


def refuse_pending(root):
    task_id = read_json(state_path(root, "round.json"), {}).get("pending")
    if task_id:
        raise RemError(f"a native task is pending: co rem submit {task_id} or co rem next --discard")


def _hash(path):
    if path.is_symlink():
        raise RemError(f"Task inputs cannot be symlinks: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _config_hash(config):
    # Scheduling, concurrency and budgets govern future work. Prepared material
    # (including its local dates) is already saved. Keep evidence-sizing limits.
    run_limits = {"runner_calls_per_day", "translations_per_day", "timeout_seconds", "workers",
                  "investigation_quota_points", "quota_floor_percent", "depth_quota_points",
                  "depth_workers", "depth_pages_per_slot", "depth_slot_minutes"}
    content = {key: value for key, value in config.items() if key != "schedule"}
    content["limits"] = {key: value for key, value in config["limits"].items() if key not in run_limits}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def _input_hash(root, path):
    digest = _hash(path)
    return _config_hash(read_config(root)) if path == root / "config.yaml" and digest is not None else digest


def _input_matches(root, task, path, digest):
    if _input_hash(root, path) == digest:
        return True
    if path != root / "config.yaml":
        return False
    if _hash(path) == digest:  # Legacy task whose raw config is unchanged.
        return True
    # Old tasks saved only a raw digest. Recover the original config only when
    # its saved stage config reproduces that digest; never guess missing inputs.
    previous = task["task"].get("config")
    return (previous is not None
            and hashlib.sha256(yaml.safe_dump(previous, sort_keys=False).encode()).hexdigest() == digest
            and _config_hash(previous) == _input_hash(root, path))


def _inputs(root, task, directory, *, handler):
    paths = {root / "config.yaml", state_path(root, "map.json"), state_path(root, "languages.json"),
             state_path(root, "progress.json"), state_path(root, "routing.json"),
             state_path(root, "reviews.json"),
             state_path(root, "sessions.json"), state_path(root, "session-tags.json")}
    book = Notebook(root)
    if handler not in ("extract", "translate", "sessions"):
        paths.update(book.path(record) for category in ("people", "orgs") for record in book.list(category))
    paths.update(Path(path) for path in task.get("input_paths", []))
    paths.update(Notebook(root).path(record) for record in task.get("before", {}))
    owner = read_json(state_path(root, "map.json"), {}).get("owner") or {}
    if owner.get("record") in task.get("before", {}):
        paths.update(book.path(record) for record in book.list("projects"))
    if handler not in ("extract", "translate", "sessions") and owner.get("record"):
        paths.add(Notebook(root).path(owner["record"]))
    paths.update(path for path in directory.rglob("*") if path.is_file() and path.name not in ("candidate.md", "notes.md"))
    for item in task.get("items", []):
        if str(item.get("source", "")).startswith("reflection:"):
            paths.add(state_path(root, "reflections/" + item["source"].split(":", 1)[1] + ".json"))
        if item.get("_mail_id"):
            from .mail_archive import message_path, observed_message_path
            provider = item["source"].partition(":")[0]
            paths.update((message_path(root, provider, item["_mail_id"]), observed_message_path(root, provider, item["_mail_id"])))
        for key in ("file", "originals"):
            path = Path(item[key]) if item.get(key) else None
            if path and path.is_file():
                paths.add(path)
                if item.get("role") == "evidence-index" and key == "file":
                    paths.update(child for child in path.parent.rglob("*") if child.is_file())
    return {str(path): _input_hash(root, path) for path in sorted(paths)}


def _audit_progress(task):
    from .project_claim_review import audit_progress
    directory = Path(task["material"])
    notes = directory / "notes.md"
    if task["stage"] != "claim-audit":
        return None
    candidate = read_json(directory / "audit-material.json", {})["candidate"]
    checked, total, unchecked = audit_progress(candidate, directory)
    now = "Now: all citations checked; write audit-output.json from the notes and run the Submit command."
    if unchecked:
        batch = " ".join(f"[{citation}]" for citation in unchecked[:AUDIT_BATCH_SIZE])
        now = (f"Now: check {batch} (next {AUDIT_BATCH_SIZE} unchecked, in Sources order) "
               f"and append one line per citation to {notes} before doing anything else.")
    return f"Audit progress: {checked} of {total} citations checked ({notes})\n{now}"


def _display(root, task):
    result = {key: task[key] for key in ("id", "stage", "record", "round", "created_at", "instructions", "material", "candidate", "submit")}
    refusal = task.get("last_result", {})
    if refusal.get("outcome") == "refused" and task["stage"] == task["render_stage"]:
        result.update(stage=task["stage"] + " (repair)", reason=refusal["reason"], fix=refusal.get("fix"))
    elif refusal.get("outcome") == "refused" and task["stage"] == "claim-audit":
        result["reason"] = refusal["reason"]
    cursor = read_json(state_path(root, "round.json"), {})
    if cursor.get("slot") or cursor.get("scheduled"):
        result["continuation"] = SCHEDULED_CONTINUATION
    progress = _audit_progress(task)
    if progress:
        result["audit_progress"] = progress
    return result


def _stop(root, config):
    logs, meter = service.run_logs(root), quota.read(config)
    reason = quota.blocks(meter, quota.points_spent(logs, meter), config["limits"])
    if not reason and service.daily_cap(root)["remaining"] <= 0:
        reason = "daily cap reached"
    return reason, meter


def next_task(root, *, scheduled=False, discard=False):
    root = root.resolve()
    print("Preparing the next REM task (resuming saved work or checking whether a round is due)…",
          file=sys.stderr, flush=True)
    with maintenance_lock(root, wait=WRITE_WAIT_SECONDS, operation="next", wait_for_native=True) as waited_for, runner.private_task_mask():
        cursor = read_json(state_path(root, "round.json"), {})
        previous = read_json(state_path(root, f"tasks/{cursor['pending']}/task.json"), {}) if cursor.get("pending") else {}
        notices = []
        if cursor.get("pending"):
            notices = _resume(root, cursor, previous, discard=discard, scheduled=scheduled)
        if scheduled and not discard:
            notices += _defer_translation_tail(root, cursor, previous)
        if discard:
            cursor = {}
        tasks = pending(root)
        # A next or submit can publish a task just before its CLI exits (or is
        # reaped). That preparer's advisory claim must not hide the new task.
        preparer = waited_for.get("pid")
        result = (_offer_pending(root, tasks[0], preparer=preparer, takeover=scheduled) if tasks
                  else _next_round(root, cursor, scheduled=scheduled, notices=notices))
        if scheduled and result.get("reason") == "daily cap reached":
            record_cap_stop(root)
        if scheduled and result.get("outcome") == "task":
            # Taking over a manual round must keep later submit/next calls in
            # this turn without claiming a slot that did not start the round.
            cursor = read_json(state_path(root, "round.json"), {})
            if not cursor.get("slot"):
                cursor["scheduled"] = True
                write_json(state_path(root, "round.json"), cursor)
            result["continuation"] = SCHEDULED_CONTINUATION
        return result


def _defer_translation_tail(root, cursor, task):
    from . import native_round
    if not cursor or cursor.get("done"):
        return []
    if cursor.get("pending") and task:
        if task.get("handler") != "translate" or task.get("status") != "pending":
            return []
        claim = task.get("claimed_by")
        if claim and _alive(claim["pid"]):
            return []
    elif not native_round.translations_only(root, cursor):
        return []
    config = read_config(root)
    slot = service.latest_slot(config, service.now() + service.EARLY_FIRE)
    tail_slot = cursor.get("translation_slot", cursor.get("portion_slot", cursor["slot"]))
    if "translation_slot" not in cursor and cursor["slot"] and task.get("handler") == "translate":
        started = service.latest_slot(config, datetime.fromisoformat(task["created_at"]) + service.EARLY_FIRE)
        tail_slot = started.isoformat() if started else None
    if cursor["slot"] is None:
        tail_slot = None
    if slot is None or tail_slot and datetime.fromisoformat(tail_slot) >= slot:
        return []
    reason = "translation deferred: a new scheduled slot must read new material"
    notices = _discard(root, cursor, task, reason) if cursor.get("pending") and task else []
    native_round.defer_translations(root, cursor, reason)
    return notices


def _offer_pending(root, task, *, preparer=None, takeover=False):
    if task.get("review_unreserved"):
        return _offer_review(root, task)
    claim = task.get("claimed_by")
    if not takeover and claim and claim["pid"] != preparer and _alive(claim["pid"]):
        return {"outcome": "claimed", "reason": f"task {task['id']} is being worked on since {claim['started_at']}; "
                "co rem next --discard to take it over"}
    _write_instructions(task, check=True)
    refusal = task.get("last_result", {})
    if (refusal.get("outcome") == "refused" and task["stage"] == task["render_stage"]
            and not task["instructions"].startswith("## Required corrections\n")):
        refusal["fix"] = str(_repair_instructions(task, refusal["reason"]))
        _write_instructions(task)
    # A claim is advisory: a session that died mid-task must not keep tonight's idle.
    _claim(task)
    write_json(Path(task["directory"]) / "task.json", task, readable=True)
    return {"outcome": "task", **_display(root, task)}


def _next_round(root, cursor, *, scheduled, notices):
    from . import native_round
    config = read_config(root)
    if scheduled and (not cursor or cursor.get("done")) and native_round.scheduled_slot(root, config) is None:
        return {"outcome": "done", "reason": "not due", "notices": notices}
    if cursor and scheduled and cursor.get("investigation_left") == 0:
        slot = service.latest_slot(config, service.now() + service.EARLY_FIRE)
        if slot and slot.isoformat() != cursor.get("portion_slot", cursor.get("slot")):
            cursor["investigation_left"] = min(service.daily_cap(root)["remaining"], 8)
            cursor["portion_slot"] = slot.isoformat()
    reason, meter = _stop(root, config)
    if reason:
        return {"outcome": "done", "reason": reason, "notices": notices}
    if not cursor or cursor.get("done"):
        cursor = native_round.prepare(root, config, scheduled=scheduled)
        if cursor.get("reason"):
            return {"outcome": "done", "reason": cursor["reason"], "notices": notices}
    return _new_task(root, cursor, config, meter, notices)


def _new_task(root, cursor, config, meter, notices):
    from . import native_round
    from .daily import _reserve
    task_id = "native-" + uuid4().hex
    directory = state_path(root, f"tasks/{task_id}")
    directory.mkdir(parents=True, mode=0o700)
    prepared = native_round.prepare_task(root, cursor, config, directory)
    if prepared is None or prepared.get("stop"):
        shutil.rmtree(directory)
        write_json(state_path(root, "round.json"), cursor)
        return {"outcome": "done", "reason": prepared["stop"] if prepared else "round done", "notices": notices}
    if prepared["phase"] in ("daily-investigation", "daily-update") and "investigation_left" in cursor:
        cursor["investigation_left"] -= 1
    run, _ = _reserve(root, prepared["phase"], 1, meter, moment=service.now())
    task = {**prepared, "id": task_id, "created_at": service.now().isoformat(), "status": "pending",
            "directory": str(directory), "run": run, "usage": None, "round_started_at": cursor["started_at"]}
    return {"outcome": "task", **_save(root, cursor, task), "notices": notices}


def _resume(root, cursor, task, *, discard, scheduled=False):
    from . import native_round
    if not task:
        cursor["pending"] = None
        return []
    if scheduled and not discard and task.get("handler") == "translate" and task.get("status") == "pending":
        claim = task.get("claimed_by")
        if claim and _alive(claim["pid"]):
            return []
    if discard or task.get("status") == "discarded":
        reason = "explicitly discarded" if discard else task["reason"]
        return _discard(root, cursor, task, reason)
    if task.get("status") == "accepted":
        _accept(root, cursor, task, task["accepted_result"])
        return []
    committed = native_round.recover_commit(root, task)
    if committed is not None or _promoted(root, task):
        _accept(root, cursor, task, committed if committed is not None else _recovered_result(root, task))
    elif service.now() - datetime.fromisoformat(task["created_at"]) > timedelta(days=1):
        return _discard(root, cursor, task, "stale: older than the daily window")
    return []


def _discard(root, cursor, task, reason):
    from . import native_round
    task.update(status="discarded", reason=reason)
    write_json(Path(task["directory"]) / "task.json", task, readable=True)
    _log(root, task, "discarded", reason=reason)
    native_round.advance(root, cursor, task, {"discarded": reason})
    return [f"Discarded {task['id']}: {reason}"]


def _claim(task):
    task["claimed_by"] = {"pid": os.getpid(), "started_at": service.now().isoformat()}


def _alive(pid) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _save(root, cursor, task):
    _claim(task)
    directory = Path(task["directory"])
    stage_task = task["task"]
    prompt = _long_page_inputs(stage_task, directory).replace("\0", "")
    # Slash expansion normally loads the core Skill in co ai. Native receives it explicitly.
    original = (directory / "instructions.md").read_text() if (directory / "instructions.md").is_file() else ""
    match = re.match(r"/rem-([\w-]+)\s+", prompt)
    if match:
        core = (runner.useful_skills_dir() / f"rem-{match[1]}" / "SKILL.md").read_text()
        core = re.sub(r"(?m)^Why these rules: .*\n+", "", core)
        prompt = core + "\n\n" + prompt[match.end():]
    elif original and original not in prompt:
        prompt = original + "\n\n" + prompt
    if "<co_rem_task>" in prompt and "</co_rem_task>" not in prompt:
        prompt += "\n</co_rem_task>"
    if task["handler"] in ("runner", "project"):
        prompt += f"\nWrite your coverage summary to {directory / 'report.md'}; write NO CHANGE there when appropriate."
    if task["handler"] not in ("runner", "project"):
        prompt += runner.today_note(root)
    prompt = f"Task workspace: {directory}. Resolve relative filenames against this directory.\n\n" + prompt
    prompt = _readable_text(prompt)
    atomic_write(directory / "instructions.md", prompt)
    _readable_files(directory)
    task.update(instructions=prompt, material=str(directory), candidate=stage_task["candidate"] or stage_task.get("task_root"),
                submit=f"co rem --root {shlex.quote(str(root))} submit {task['id']}",
                inputs=_inputs(root, stage_task, directory, handler=task["handler"]),
                today=re.findall(r"Today is (\d{4}-\d{2}-\d{2})", prompt)[-1])
    task["render_stage"] = task["stage"]
    task["render_instructions"] = task["instructions"]
    task["source_view"] = _source_view(root, stage_task, handler=task["handler"])
    task["run"].update(outcome="pending", task_id=task["id"], stage=task["stage"],
                       record=task["record"], items=len(stage_task.get("items", [])),
                       instructions_chars=len(prompt))
    write_json(state_path(root, f"runs/{task['run']['id']}.json"), task["run"])
    cursor["pending"] = task["id"]
    write_json(state_path(root, "round.json"), cursor)
    write_json(directory / "task.json", task, readable=True)
    return _display(root, task)


def _log(root, task, outcome, **fields):
    if outcome == "completed" and "after" not in task["run"].get("quota", {}):
        task["run"].setdefault("quota", {})["after"] = quota.read(read_config(root))
    task["run"].update(outcome=outcome, finished_at=service.now().isoformat(), usage=task.get("usage"), **fields)
    write_json(state_path(root, f"runs/{task['run']['id']}.json"), task["run"])


def submit(root, task_id, *, usage=None):
    from . import native_round
    if not re.fullmatch(r"native-[0-9a-f]{32}", task_id):
        raise RemError("Invalid native task id")
    root = root.resolve()
    with maintenance_lock(root, operation="submit"), runner.private_task_mask():
        task = read_json(state_path(root, f"tasks/{task_id}/task.json"), {})
        if task.get("status") != "pending":
            raise RemError("Task does not exist or is not pending")
        cursor = read_json(state_path(root, "round.json"), {})
        if cursor.get("pending") != task_id:
            raise RemError("Task is not the round's pending task")
        _usage(task, usage)
        committed = native_round.recover_commit(root, task)
        if committed is not None:
            return _accept(root, cursor, task, committed)
        if _promoted(root, task):
            return _accept(root, cursor, task, _recovered_result(root, task))
        if (any(not _input_matches(root, task, Path(path), digest) for path, digest in task["inputs"].items())
                or task["source_view"] != _source_view(root, task["task"], handler=task["handler"])):
            raise RemError("Task input changed; preserve the current notebook. Run co rem next --discard")
        result = _check_submission(root, task)
        if result.get("outcome") == "refused":
            return result
        if result.get("needs_review"):
            return _request_review(root, task, result)
        return _accept(root, cursor, task, result)


def _usage(task, usage):
    if usage is None:
        return
    if not isinstance(usage, dict) or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in usage.values()):
        raise RemError("Usage must contain non-negative finite token totals")
    task["usage"] = usage


def _submission_output(task):
    directory = Path(task["directory"])
    output = {"usage": task.get("usage"), "result": ""}
    candidate = Path(task["candidate"] or task["task"]["task_root"])
    outputs = {candidate, Path(task["task"]["candidate"] or task["task"].get("task_root", candidate))}
    if any(path.is_symlink() or path.is_file() and path.stat().st_size > 1_000_000 for path in outputs):
        raise RemError("Output must be a regular file within the one-megabyte limit")
    if task["handler"] in ("sessions", "translate", "same-person"):
        if not candidate.is_file():
            raise RemError(f"Write the output file: {candidate}")
        output["result"] = (json.dumps(read_json(candidate, None), ensure_ascii=False) if candidate.suffix == ".json"
                            else candidate.read_text(encoding="utf-8"))
    report = directory / "report.md"
    if report.is_file():
        output["result"] = report.read_text(encoding="utf-8")
    return output


def _check_submission(root, task):
    from . import native_round
    from .reviews import _problem
    directory = Path(task["directory"])
    # Validation refusals are the native CLI's repairable response boundary.
    try:
        output = _submission_output(task)
        proposals = read_json(directory / "review-candidates.json", [])
        for proposal in proposals[:2] if isinstance(proposals, list) else []:
            _problem(root, proposal)
        return native_round.check_task(root, task, output)
    except (RemError, json.JSONDecodeError) as error:
        if task["stage"] == "claim-audit" and isinstance(error, json.JSONDecodeError):
            return _continue_review(root, task, "Write valid JSON to audit-output.json. "
                                    "Continue checking from the notes and submit when every citation is checked.")
        return _refuse_submission(root, task, str(error))


def _repair_findings(directory, reason):
    lines = []
    for error in read_json(directory / "repair-findings.json", [])[:5]:
        lines.append(f"- Error: {error[:500]}")
    if "Cited-claim audit did not pass" in reason:
        findings = read_json(directory / "claim-review.json", {}).get("findings", [])
        for finding in findings[:5]:
            lines.append(f"- Claim: {finding['claim'][:500]}\n  Required correction: {finding['required_correction'][:500]}")
        if len(findings) > 5:
            lines.append("Further findings: see claim-review.json.")
    return "\n".join(lines)


def _repair_instructions(task, reason):
    directory = Path(task["directory"])
    task["stage"] = task["render_stage"]
    task["candidate"] = task["task"]["candidate"] or task["task"].get("task_root")
    fix = directory / "instructions.md"
    corrections = reason
    if task["handler"] in ("runner", "project") and task.get("record"):
        errors = read_json(directory / "review.json", {}).get("errors") or [reason]
        corrections = runner.repair_instruction(
            task["record"], errors, directory, Path(task["task"]["root"]), native=True)
        fix = directory / "repair-instructions.md"
    task["instructions"] = (
        "## Required corrections\n"
        "The page is already written. Fix only the named problems in the existing candidate.\n"
        "Do not redo the investigation or outside research.\n"
        f"Save the candidate: {task['candidate']}\n"
        f"Run {task['submit']} again in this turn.\n\n"
        f"Refused: {reason}\n" + _repair_findings(directory, reason) + "\n\n" + corrections
        + "\n\n## Reference: full render instructions\n" + task["render_instructions"])
    if fix.name == "repair-instructions.md":
        atomic_write(fix, _readable_text(task["instructions"]))
    return fix


def _refuse_submission(root, task, reason):
    directory = Path(task["directory"])
    fix = _repair_instructions(task, reason)
    task["review_unreserved"] = False
    display = _display(root, task)
    task["last_result"] = {"outcome": "refused", "reason": reason, "fix": str(fix),
                           **{key: display[key] for key in ("candidate", "submit", "continuation") if key in display}}
    _write_instructions(task)
    write_json(directory / "task.json", task, readable=True)
    _log(root, task, "refused", reason=reason)
    return task["last_result"]


def _continue_review(root, task, reason):
    display = _display(root, task)
    result = {"outcome": "refused", "reason": reason,
              **{key: display[key] for key in ("id", "stage", "candidate", "submit", "audit_progress", "continuation") if key in display}}
    task["last_result"] = result
    write_json(Path(task["directory"]) / "task.json", task, readable=True)
    _log(root, task, "pending", stage="claim-audit", reason=reason)
    return result


def _request_review(root, task, result):
    if result.get("continue_review"):
        return _continue_review(root, task, result["continue_review"])
    directory = Path(task["directory"])
    task["review_unreserved"] = True
    task["stage"] = "claim-audit"
    task["instructions"], task["candidate"] = result["needs_review"], result["candidate"]
    _log(root, task, "pending", stage=task["render_stage"], pending_review=True)
    atomic_write(directory / "audit-instructions.md", task["instructions"])
    _write_instructions(task)
    write_json(directory / "task.json", task, readable=True)
    return _offer_review(root, task)


def _readable_text(text):
    return "\n".join(textwrap.fill(line, width=400, replace_whitespace=False, drop_whitespace=False)
                     if len(line) > 4000 else line for line in text.split("\n"))


def _long_page_inputs(task, directory):
    """Keep an exceptional long page exact, without handing out an unreadable file."""
    prompt = task["prompt"]
    for name in ("page.md", "candidate.md"):
        path = directory / name
        if path.is_file() and any(len(line) > 4000 for line in path.read_text().splitlines()):
            original = path.with_suffix(".json") if name == "page.md" else directory / "candidate-original.json"
            write_json(original, path.read_text(), readable=True)
            path.unlink()
            if name == "page.md":
                prompt = prompt.replace("page.md", "page.json")
            else:
                prompt += f"\nThe candidate has not been prefilled because its original has long lines. Read {original} and write the complete candidate to {path}."
            prompt += "\nIn exact JSON, __rem_text_parts__ lists consecutive text pieces; only escaped \\n marks an original newline. Read the pieces directly; no reconstruction script is needed."
    return prompt


def _readable_files(directory):
    """Bound generated display files; retain exact source/state strings in JSON."""
    generated_json = {"material.json", "audit-material.json", "audit-task.json", "task.json", "originals.json",
                      "review.json", "claim-review.json", "repair-findings.json", "translation-constraints.json",
                      "commit.json", "promotion.json", "source-ids.json", "page.json", "candidate-original.json",
                      "feedback-checkpoint.json"}
    for path in directory.rglob("*"):
        relative = path.relative_to(directory)
        if relative.parts[0] in ("web", "notebook"):
            continue
        json_input = path.name in generated_json or path.suffix == ".json" and relative.parts[0] == "sessions"
        display = (path.suffix == ".md" and path.name not in ("candidate.md", "page.md", "report.md", "notes.md")
                   and relative.parts[0] not in ("web", "notebook"))
        if (json_input or display) and path.is_file() and not path.is_symlink():
            text = path.read_text(encoding="utf-8")
            if any(len(line) > 4000 for line in text.splitlines()):
                if json_input:
                    write_json(path, read_json(path, None), readable=True)
                else:
                    atomic_write(path, _readable_text(text))


def _write_instructions(task, *, check=False):
    path = Path(task["directory"]) / "instructions.md"
    # Older pending audits/repairs kept writer instructions in this file.
    # Restore the active instructions only if the prepared file is intact.
    if check and _hash(path) != task["inputs"].get(str(path)):
        raise RemError("Task input changed; preserve the current notebook. Run co rem next --discard")
    task["instructions"] = _readable_text(task["instructions"])
    atomic_write(path, task["instructions"])
    _readable_files(Path(task["directory"]))
    task["inputs"][str(path)] = _hash(path)


def _promoted(root, task):
    if not task:
        return False
    receipt = read_json(Path(task["directory"]) / "promotion.json", {})
    return bool(receipt) and _hash(Notebook(root).path(receipt["record"])) == receipt["sha256"]


def _accept(root, cursor, task, result):
    from . import native_round
    _readable_files(Path(task["directory"]))
    task.update(status="accepted", last_result={"outcome": "accepted"}, accepted_result=result)
    _log(root, task, "completed", changed=result.get("changed", []))
    write_json(Path(task["directory"]) / "task.json", task, readable=True)
    native_round.advance(root, cursor, task, result)
    return {"outcome": "accepted", "id": task["id"], "changed": result.get("changed", []),
            "same_turn": bool(cursor.get("slot") or cursor.get("scheduled"))}


def _offer_review(root, task):
    reason, meter = _stop(root, read_config(root))
    if reason:
        return {"outcome": "done", "reason": reason}
    _write_instructions(task, check=True)
    from .daily import _reserve
    _log(root, task, "completed", changed=[], pending_review=True)
    task.setdefault("runs", []).append(task["run"]["id"])
    task["run"], _ = _reserve(root, task["phase"], 1, meter, moment=service.now())
    task["usage"] = None
    task["run"].update(task_id=task["id"], native_step="claim-audit")
    task["review_unreserved"] = False
    _claim(task)
    _log(root, task, "pending", stage="claim-audit")
    write_json(Path(task["directory"]) / "task.json", task, readable=True)
    return {"outcome": "task", **_display(root, task)}


def _source_view(root, task, *, handler):
    if handler in ("extract", "translate", "sessions"):
        return None
    from .reader_model import _source_ids, cited_context, later_in_threads
    items = task.get("items", [])
    sources = {item["source"] for item in items if item.get("source")}
    for item in items:
        sources.update(item.get("sources", []))
        sources.update(row["source"] for row in item.get("facts", []) if row.get("source"))
    records = [{"text": text} for text in task.get("before", {}).values()]
    records.append({"text": "\n## Sources\n" + "\n".join(f"- [{n}] {source}" for n, source in enumerate(sorted(sources), 1))})
    sources.update(_source_ids(records))
    value = {"contexts": cited_context(root, records), "tails": later_in_threads(root, sources),
             "lookups": {kind: Notebook(root).list(kind) for kind in ("people", "orgs")}}
    if str(task.get("record", "")).startswith("projects/"):
        from .project_material import stored
        value["project"] = stored(root, task["record"])
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()



def _recovered_result(root, task):
    receipt = read_json(Path(task["directory"]) / "promotion.json", {})
    record = receipt["record"]
    original = task["task"].get("before", {}).get(record)
    changed = original is None or hashlib.sha256(original.encode()).hexdigest() != receipt["sha256"]
    report = Path(task["directory"]) / "report.md"
    return {"changed": [record] if changed else [], "report": report.read_text() if report.is_file() else ""}
