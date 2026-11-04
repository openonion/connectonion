"""A native session supplies model output between explicit prepare/check calls."""

import hashlib
import json
import math
import re
import shlex
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from . import quota, runner, service
from .config import read_config
from .files import Notebook, RemError, atomic_write, maintenance_lock, read_json, state_path, write_json


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


def _inputs(root, task, directory):
    paths = {root / "config.yaml", state_path(root, "map.json"), state_path(root, "languages.json"),
             state_path(root, "progress.json"), state_path(root, "routing.json"),
             state_path(root, "reviews.json"),
             state_path(root, "sessions.json"), state_path(root, "session-tags.json")}
    book = Notebook(root)
    paths.update(book.path(record) for category in ("people", "orgs") for record in book.list(category))
    paths.update(Path(path) for path in task.get("input_paths", []))
    paths.update(Notebook(root).path(record) for record in task.get("before", {}))
    owner = read_json(state_path(root, "map.json"), {}).get("owner") or {}
    if owner.get("record") in task.get("before", {}):
        paths.update(book.path(record) for record in book.list("projects"))
    if owner.get("record"):
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
    return {str(path): _hash(path) for path in sorted(paths)}


def _display(task):
    return {key: task[key] for key in ("id", "stage", "record", "round", "created_at", "instructions", "material", "candidate", "submit")}


def _stop(root, config):
    logs, meter = service.run_logs(root), quota.read(config)
    reason = quota.blocks(meter, quota.points_spent(logs, meter), config["limits"])
    if not reason and service.daily_cap(root)["remaining"] <= 0:
        reason = "daily cap reached"
    return reason, meter


def next_task(root, *, scheduled=False, discard=False):
    from . import native_round
    root = root.resolve()
    with maintenance_lock(root), runner.private_task_mask():
        cursor = read_json(state_path(root, "round.json"), {})
        notices = []
        if discard and cursor and not cursor.get("pending"):
            cursor = {}
        if cursor.get("pending"):
            previous = read_json(state_path(root, f"tasks/{cursor['pending']}/task.json"), {})
            if previous.get("status") == "accepted" or _promoted(root, previous):
                _accept(root, cursor, previous, previous.get("accepted_result") or _recovered_result(root, previous))
            elif previous.get("status") == "discarded":
                native_round.advance(root, cursor, previous, {"discarded": previous.get("reason", "discarded")})
            elif not previous:
                cursor["pending"] = None
        for task in pending(root):
            stale = service.now() - datetime.fromisoformat(task["created_at"]) > timedelta(days=1)
            if not discard and not stale:
                return _offer_review(root, task) if task.get("review_unreserved") else {"outcome": "task", **_display(task)}
            reason = "stale: older than the daily window" if stale else "explicitly discarded"
            task.update(status="discarded", reason=reason)
            write_json(Path(task["directory"]) / "task.json", task)
            _log(root, task, "discarded", reason=reason)
            native_round.advance(root, cursor, task, {"discarded": reason})
            notices.append(f"Discarded {task['id']}: {reason}")
        config = read_config(root)
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
        task_id = "native-" + uuid4().hex
        directory = state_path(root, f"tasks/{task_id}")
        directory.mkdir(parents=True, mode=0o700)
        prepared = native_round.prepare_task(root, cursor, config, directory)
        if prepared and prepared.get("stop"):
            shutil.rmtree(directory)
            write_json(state_path(root, "round.json"), cursor)
            return {"outcome": "done", "reason": prepared["stop"], "notices": notices}
        if prepared is None:
            shutil.rmtree(directory)
            return {"outcome": "done", "reason": "round done", "notices": notices}
        if prepared["phase"] in ("daily-investigation", "daily-update") and "investigation_left" in cursor:
            cursor["investigation_left"] -= 1
        from .daily import _reserve
        run, _ = _reserve(root, prepared["phase"], 1, meter, moment=service.now())
        task = {**prepared, "id": task_id, "created_at": service.now().isoformat(), "status": "pending",
                "directory": str(directory), "run": run, "usage": None, "round_started_at": cursor["started_at"]}
        return {"outcome": "task", **_save(root, cursor, task), "notices": notices}


def _save(root, cursor, task):
    directory = Path(task["directory"])
    stage_task = task["task"]
    prompt = stage_task["prompt"].replace("\0", "")
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
    atomic_write(directory / "instructions.md", prompt)
    task.update(instructions=prompt, material=str(directory), candidate=stage_task["candidate"] or stage_task.get("task_root"),
                submit=f"co rem --root {shlex.quote(str(root))} submit {task['id']}",
                inputs=_inputs(root, stage_task, directory),
                today=re.findall(r"Today is (\d{4}-\d{2}-\d{2})", prompt)[-1])
    task["render_stage"] = task["stage"]
    task["render_instructions"] = task["instructions"]
    task["source_view"] = _source_view(root, stage_task)
    task["run"].update(outcome="pending", task_id=task["id"], stage=task["stage"],
                       record=task["record"], items=len(stage_task.get("items", [])),
                       instructions_chars=len(prompt))
    write_json(state_path(root, f"runs/{task['run']['id']}.json"), task["run"])
    cursor["pending"] = task["id"]
    write_json(state_path(root, "round.json"), cursor)
    write_json(directory / "task.json", task)
    return _display(task)


def _log(root, task, outcome, **fields):
    task["run"].update(outcome=outcome, finished_at=service.now().isoformat(), usage=task.get("usage"), **fields)
    write_json(state_path(root, f"runs/{task['run']['id']}.json"), task["run"])


def submit(root, task_id, *, usage=None):
    from . import native_round
    if not re.fullmatch(r"native-[0-9a-f]{32}", task_id):
        raise RemError("Invalid native task id")
    with maintenance_lock(root), runner.private_task_mask():
        directory = state_path(root, f"tasks/{task_id}")
        task = read_json(directory / "task.json", {})
        if task.get("status") != "pending":
            raise RemError("Task does not exist or is not pending")
        cursor = read_json(state_path(root, "round.json"), {})
        if _promoted(root, task):
            return _accept(root, cursor, task, _recovered_result(root, task))
        if (any(_hash(Path(path)) != digest for path, digest in task["inputs"].items())
                or task["source_view"] != _source_view(root, task["task"])):
            raise RemError("Task input changed; preserve the current notebook. Run co rem next --discard")
        cursor = read_json(state_path(root, "round.json"), {})
        if cursor.get("pending") != task_id:
            raise RemError("Task is not the round's pending task")
        if usage is not None:
            if not isinstance(usage, dict) or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in usage.values()):
                raise RemError("Usage must contain non-negative finite token totals")
            task["usage"] = usage
        output = {"usage": task.get("usage"), "result": ""}
        candidate = Path(task["candidate"] or task["task"]["task_root"])
        outputs = {candidate, Path(task["task"]["candidate"] or task["task"].get("task_root", candidate))}
        if any(path.is_symlink() or path.is_file() and path.stat().st_size > 1_000_000 for path in outputs):
            return {"outcome": "refused", "reason": "Output must be a regular file within the one-megabyte limit"}
        if task["handler"] in ("sessions", "translate", "same-person"):
            if not candidate.is_file():
                return {"outcome": "refused", "reason": f"Write the output file: {candidate}"}
            output["result"] = candidate.read_text(encoding="utf-8")
        report = directory / "report.md"
        if report.is_file():
            output["result"] = report.read_text(encoding="utf-8")
        try:
            from .reviews import _problem
            proposals = read_json(directory / "review-candidates.json", [])
            for proposal in proposals[:2] if isinstance(proposals, list) else []:
                _problem(root, proposal)
            result = native_round.check_task(root, task, output)
        except (RemError, json.JSONDecodeError) as error:
            task["stage"] = task["render_stage"]
            task["instructions"] = task["render_instructions"]
            task["candidate"] = task["task"]["candidate"] or task["task"].get("task_root")
            task["review_unreserved"] = False
            task["last_result"] = {"outcome": "refused", "reason": str(error)}
            write_json(directory / "task.json", task)
            _log(root, task, "refused", reason=str(error))
            return task["last_result"]
        if result.get("needs_review"):
            task["review_unreserved"] = True
            task["stage"] = "claim-audit"
            task["instructions"], task["candidate"] = result["needs_review"], result["candidate"]
            _log(root, task, "pending", stage=task["render_stage"], pending_review=True)
            atomic_write(directory / "audit-instructions.md", task["instructions"])
            write_json(directory / "task.json", task)
            return _offer_review(root, task)
        return _accept(root, cursor, task, result)


def _promoted(root, task):
    if not task:
        return False
    receipt = read_json(Path(task["directory"]) / "promotion.json", {})
    return bool(receipt) and _hash(Notebook(root).path(receipt["record"])) == receipt["sha256"]


def _accept(root, cursor, task, result):
    from . import native_round
    task.update(status="accepted", last_result={"outcome": "accepted"}, accepted_result=result)
    write_json(Path(task["directory"]) / "task.json", task)
    _log(root, task, "completed", changed=result.get("changed", []))
    native_round.advance(root, cursor, task, result)
    return {"outcome": "accepted", "id": task["id"], "changed": result.get("changed", [])}


def _offer_review(root, task):
    reason, meter = _stop(root, read_config(root))
    if reason:
        return {"outcome": "done", "reason": reason}
    from .daily import _reserve
    _log(root, task, "completed", changed=[], pending_review=True)
    task.setdefault("runs", []).append(task["run"]["id"])
    task["run"], _ = _reserve(root, task["phase"], 1, meter, moment=service.now())
    task["usage"] = None
    task["run"].update(task_id=task["id"], native_step="claim-audit")
    task["review_unreserved"] = False
    _log(root, task, "pending", stage="claim-audit")
    write_json(Path(task["directory"]) / "task.json", task)
    return {"outcome": "task", **_display(task)}


def _source_view(root, task):
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
