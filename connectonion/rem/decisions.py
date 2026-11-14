"""Write captured decisions by hand, sharing the night's queue but not its cap."""

from uuid import uuid4

from . import captured_decisions, runner
from .config import read_config
from .files import Notebook, WRITE_WAIT_SECONDS, maintenance_lock, state_path, write_json
from .service import now


def status(root):
    notebook = Notebook(root)
    return {"decisions": len(notebook.list("decisions")), "principles": len(notebook.list("principles")),
            "waiting": captured_decisions.pending_count(notebook), "skipped": captured_decisions.skipped_counts(notebook)}


def _round(notebook, items, config):
    from .inquiry import stage_config
    config = stage_config(notebook.root, config, "abstract")
    started = now().isoformat()
    count = sum(bool(line.strip()) for item in items
                for line in item["text"].split("\n\n## Sources\n", 1)[0].splitlines()[1:])
    try:
        result = runner.run_stage(notebook, items, config, stage="abstract", maintenance_lock_held=True)
        row = {"read": count, "changed": result["changed"], "refused": result.get("refusals", []),
               "usage": result.get("usage"), "threads": result.get("threads", []), "reason": ""}
    except runner.RunFailed as error:
        row = {"read": count, "changed": error.changed, "refused": error.refusals,
               "usage": error.usage, "reason": str(error)}
    # Save the outcome before moving the queue; an interrupted turn stays pending.
    run_id = "run_" + uuid4().hex
    write_json(state_path(notebook.root, f"runs/{run_id}.json"), {
        **row, "id": run_id, "phase": "abstract", "stage": "abstract", "manual": True,
        "started_at": started, "finished_at": now().isoformat(), "items": len(items),
        "outcome": "completed" if row["changed"] and not row["reason"] else "failed",
        "harness": config["runner"], "model": config["model"], "runner_attempts": 0})
    deferred = captured_decisions.remember_offered(notebook.root, items, promoted=bool(row["changed"]),
                                                  night=f"manual:{run_id}", reason=row["reason"] or "Round wrote no page")
    row["set_aside"] = bool(deferred)
    return row


def write(root, *, rounds=None, progress=None):
    notebook, config = Notebook(root), read_config(root)
    rows = []
    reason = ""
    last_failure = ""
    attempted, empty_rounds, set_aside = [], 0, 0
    while rounds is None or len(rows) < rounds:
        with maintenance_lock(root, wait=WRITE_WAIT_SECONDS):
            items = captured_decisions.material(notebook, config, attempted=attempted)
            if not items:
                if captured_decisions.pending_count(notebook, attempted=attempted):
                    reason = "No pending decision fits the configured input character limit"
                elif attempted and not any(row["changed"] for row in rows):
                    reason = "No unattempted slices left: " + last_failure
                break
            row = _round(notebook, items, config)
        rows.append(row)
        if progress:
            progress(len(rows), row)
        empty_rounds = 0 if row["changed"] else empty_rounds + 1
        if not row["changed"]:
            attempted.extend(captured_decisions.slice_key(item) for item in items)
            set_aside += row["set_aside"]
            last_failure = row["reason"] or "Round wrote no page"
        if empty_rounds >= 2:
            reason = "Stopped after two empty rounds in a row: " + last_failure
            break
    else:
        if last_failure and not any(row["changed"] for row in rows):
            reason = "Round limit reached without a page: " + last_failure
    written = sum(len(row["changed"]) for row in rows)
    return {"rounds": rows, "written": written, "refused": sum(len(row["refused"]) for row in rows),
            "left": captured_decisions.pending_count(notebook), "reason": reason, "set_aside": set_aside,
            "skipped": captured_decisions.skipped_counts(notebook),
            "failed": not written and bool(reason)}
