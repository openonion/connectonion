"""One refused or hung task can no longer eat the whole night (sprint 11).

11-07: about 30 turns on one native task refused again and again; nothing else
ran. 11-08: one `co rem next --scheduled` printed nothing for hours. Fictional
notebooks only.
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import daily, native, native_round, project_pages, quota, refusals, runner, service
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import Notebook, RemError, read_json, state_path, write_json
from connectonion.rem.project_material import mark_written

pytestmark = pytest.mark.usefixtures("rem_clock")

NEW = "2026-10-02T00:00:00Z"


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    root = tmp_path / "fixture-notebook"
    prepare(root)
    set_config(root, ["schedule.timezone", "UTC"])
    write_json(state_path(root, "subscriptions.json"), {})
    write_json(state_path(root, "consent.json"), {"authorized_at": service.now().isoformat()})
    monkeypatch.setattr(quota, "read", lambda config: {"unknown": "fixture"})
    monkeypatch.setattr(daily, "_clients", lambda sources: {})
    monkeypatch.setattr(runner, "run_task", lambda *a, **kw: pytest.fail("No child model"))
    monkeypatch.setattr(runner, "run_claim_task", lambda *a, **kw: pytest.fail("No child audit"))
    return root


def two_projects(root, monkeypatch, names=("fern", "heron")):
    """Fern and Heron each have one unread input, so an unchanged candidate is refused."""
    book, records = Notebook(root), [f"projects/{name}.md" for name in names]
    items = {}
    for number, record in enumerate(records, 1):
        book.stub_project(record, Path(record).stem.title())
        mark_written(root, record, "2026-10-01T00:00:00Z", inputs_read=0, inputs_available=0)
        items[record] = {"role": "user", "source": f"codex:{Path(record).stem}:{number}", "timestamp": NEW,
                         "text": "Please review the pilot."}
    monkeypatch.setattr(project_pages, "material", lambda root, record, **kw: ([
        {"role": "page", "record": record, "source": "investigation:page", "text": book.read(record)},
        items[record]], NEW))
    monkeypatch.setattr(project_pages, "pending", lambda root, record: ([items[record]], "update"))
    cursor = native_round.prepare(root, read_config(root), scheduled=False)
    cursor.update(batch={"done": True}, jobs=[{"record": r, "kind": "project"} for r in records], summaries=[])
    write_json(state_path(root, "round.json"), cursor)
    return records


def refuse(root, task, monkeypatch, citation=3):
    """The 11-07 shape: the checker names a dropped source ID on every submit."""
    def dropped(*args):
        raise RemError(f"Candidate dropped source ID [{citation}] codex:fern:{citation}")
    monkeypatch.setattr(native_round, "check_task", dropped)
    return native.submit(root, task["id"])


def test_two_same_refusals_park_the_task_and_next_serves_other_work(notebook, monkeypatch):
    fern, heron = two_projects(notebook, monkeypatch)
    task = native.next_task(notebook)
    assert task["record"] == fern
    first = refuse(notebook, task, monkeypatch, 3)
    assert first["outcome"] == "refused", first
    second = refuse(notebook, task, monkeypatch, 4)
    assert second["outcome"] == "parked", second
    assert second["reason"].startswith("parked: refused twice for the same reason")
    following = native.next_task(notebook)
    assert following["outcome"] == "task" and following["id"] != task["id"]
    assert following["record"] == heron
    # Recorded, never silently dropped: the run log and the ledger both say why.
    saved = read_json(Path(task["material"]) / "task.json", {})
    assert saved["refusals"] == [first["reason"], second["reason"].split("same reason: ", 1)[1]]
    run = read_json(state_path(notebook, f"runs/{saved['run']['id']}.json"), {})
    assert run["outcome"] == "parked" and run["reason"].startswith("parked: ")
    assert run["refusals"] == saved["refusals"]
    entry = refusals.refused_for(notebook, fern)
    assert entry["parked"].startswith("parked: ")
    assert "dropped source ID [4]" in entry["parked"]


def test_three_refusals_park_even_when_the_reasons_differ():
    assert native._park_reason(["a", "b"]) is None
    assert native._park_reason(["a", "b", "c"]).startswith("refused 3 times")
    assert native._park_reason(["Citation [21] missing", "Citation [22] missing"]).startswith(
        "refused twice for the same reason")


def test_parked_page_waits_a_day_then_returns_as_a_retry(notebook):
    from datetime import datetime, timedelta, timezone
    refusals.remember_refusal(notebook, "projects/fern.md", ["codex:fern:1"], "parked: refused twice",
                              stage="parked", parked=True)
    assert "projects/fern.md" in refusals.parked_waiting(notebook)
    assert "projects/fern.md" not in refusals.due_for_retry(notebook)
    later = datetime.now(timezone.utc) + timedelta(hours=refusals.RETRY_HOURS + 1)
    assert "projects/fern.md" not in refusals.parked_waiting(notebook, now=later)
    assert "projects/fern.md" in refusals.due_for_retry(notebook, now=later)
    # A later refusal of the same page keeps the parked note.
    refusals.remember_refusal(notebook, "projects/fern.md", ["codex:fern:2"], "Cited-claim audit did not pass",
                              stage="investigation round")
    assert refusals.refused_for(notebook, "projects/fern.md")["parked"] == "parked: refused twice"


def test_status_and_logs_show_parked(notebook, monkeypatch):
    two_projects(notebook, monkeypatch)
    task = native.next_task(notebook)
    refuse(notebook, task, monkeypatch)
    refuse(notebook, task, monkeypatch)
    cli = CliRunner()
    status = cli.invoke(app, ["rem", "--root", str(notebook), "status"])
    assert "parked: refused twice for the same reason" in status.output, status.output
    logs = cli.invoke(app, ["rem", "--root", str(notebook), "logs"])
    assert "parked: refused twice for the same reason" in logs.output, logs.output


HUNG = textwrap.dedent("""
    import sys, time
    from datetime import datetime, timezone
    from pathlib import Path
    from connectonion.rem import daily, native, native_round, quota, service
    moment = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    service.now = lambda: moment
    daily.now = lambda: moment
    quota.read = lambda config: {"unknown": "fixture"}
    daily._clients = lambda sources: {}
    native.NEXT_DEADLINE_SECONDS = 8
    native.PROGRESS_SECONDS = 0.5
    native_round._project_task = lambda *a, **kw: time.sleep(30)
    native.next_task(Path(sys.argv[1]))
    print("NOT REACHED")
""")


def test_hung_preparation_hits_the_deadline_reports_it_and_the_next_call_moves_on(notebook, monkeypatch):
    fern, heron = two_projects(notebook, monkeypatch)
    result = subprocess.run([sys.executable, "-c", HUNG, str(notebook)], capture_output=True, text=True,
                            timeout=60, env={**os.environ, "OPENONION_API_KEY": "test-key"})
    assert result.returncode == native.DEADLINE_EXIT, result.stderr
    assert "NOT REACHED" not in result.stdout
    assert f"Still preparing {fern}" in result.stderr, result.stderr
    assert "passed its deadline" in result.stdout and "co rem next again" in result.stdout, result.stdout
    following = native.next_task(notebook)
    assert following["outcome"] == "task" and following["record"] == heron, following
    assert any(fern in notice and "deadline" in notice for notice in following["notices"])
    assert refusals.refused_for(notebook, fern)["parked"].startswith("parked: preparing it passed")


PASSED_OVER_THEN_HUNG = textwrap.dedent("""
    import sys, threading
    from datetime import datetime, timezone
    from pathlib import Path
    from connectonion.rem import daily, native, native_round, quota, service
    moment = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    service.now = lambda: moment
    daily.now = lambda: moment
    quota.read = lambda config: {"unknown": "fixture"}
    daily._clients = lambda sources: {}
    native.NEXT_DEADLINE_SECONDS = 3
    native.PROGRESS_SECONDS = 0.5

    def prepare(root, cursor, config, directory, record):
        if record == "projects/fern.md":  # nothing to do for this page: passed over, in memory
            cursor["job_index"] += 1
            return None
        native.preparation_stage("gathering fixture mail", 0, 4)
        threading.Event().wait()  # never finishes

    native_round._project_task = prepare
    native.next_task(Path(sys.argv[1]))
    print("NOT REACHED")
""")


def hang_on_heron(notebook):
    """One `co rem next` in a scheduled turn: it passes over Fern, then never finishes preparing Heron."""
    write_json(state_path(notebook, "last-turn.json"), {"turn_id": "fixture-turn", "result": "running",
                                                         "started_at": service.now().isoformat()})
    state_path(notebook, "turns").mkdir(exist_ok=True)
    return subprocess.run([sys.executable, "-c", PASSED_OVER_THEN_HUNG, str(notebook)], capture_output=True,
                          text=True, timeout=60,
                          env={**os.environ, "OPENONION_API_KEY": "test-key", "CO_REM_TURN_ID": "fixture-turn"})


def test_a_page_that_hangs_after_another_was_passed_over_is_parked_and_the_next_call_serves_other_work(
        notebook, monkeypatch):
    """11-16: the stall named job 98, the saved round said 97, and three calls prepared the same page."""
    fern, heron, ibis = two_projects(notebook, monkeypatch, ("fern", "heron", "ibis"))
    result = hang_on_heron(notebook)
    assert result.returncode == native.DEADLINE_EXIT, result.stderr
    assert "NOT REACHED" not in result.stdout
    following = native.next_task(notebook)
    assert following["outcome"] == "task" and following["record"] == ibis, following
    assert any(heron in notice and "deadline" in notice for notice in following["notices"])
    parked = refusals.refused_for(notebook, heron)["parked"]
    assert parked == "parked: preparing it passed the 10-minute deadline while gathering fixture mail"
    assert heron in refusals.parked_waiting(notebook) and heron not in refusals.due_for_retry(notebook)
    status = CliRunner().invoke(app, ["rem", "--root", str(notebook), "status"])
    assert heron in status.output and "preparing it passed" in status.output, status.output


def test_a_deadline_says_which_step_was_waited_on_and_logs_the_seconds_of_each(notebook, monkeypatch):
    fern, heron, _ = two_projects(notebook, monkeypatch, ("fern", "heron", "ibis"))
    result = hang_on_heron(notebook)
    step = f"preparing {heron}: gathering fixture mail"
    assert f"Still {step} (" in result.stderr and "s on this step" in result.stderr, result.stderr
    assert f"while {step}" in result.stdout, result.stdout
    where = next(line for line in result.stderr.splitlines() if line.startswith("Where the time went: "))
    assert f"preparing {fern} 0 s" in where and f"{step} " in where, where
    events = [json.loads(line) for line in
              state_path(notebook, "turns/fixture-turn.preparation.jsonl").read_text().splitlines()]
    assert [event["type"] for event in events] == ["rem.preparation_stalled"]
    assert events[0]["step"] == step and events[0]["timings"][step] >= 2
    assert "waiting for the maintenance lock" in events[0]["timings"]


def test_a_stall_recorded_past_the_saved_round_parks_the_page_and_keeps_the_rounds_place(notebook, monkeypatch):
    """The live shape: stalled-next.json at one job, round.json at the job before it."""
    fern, heron = two_projects(notebook, monkeypatch)
    cursor = read_json(state_path(notebook, "round.json"), {})
    write_json(state_path(notebook, native.STALLED), {
        "label": f"preparing {heron}", "at": service.now().isoformat(), "round": cursor["started_at"],
        "job_index": 1, "record": heron})
    assert native._skip_stalled(notebook) == [
        f"Skipped preparing {heron}: the last co rem next passed its deadline there"]
    assert read_json(state_path(notebook, "round.json"), {})["job_index"] == 0
    assert native.next_task(notebook)["record"] == fern
    native.next_task(notebook, discard=True)
    assert heron in refusals.parked_waiting(notebook)


def test_a_page_that_stalls_again_on_its_retry_keeps_its_count_towards_the_retry_limit(notebook, monkeypatch):
    from datetime import datetime, timedelta, timezone
    fern, heron = two_projects(notebook, monkeypatch)
    cursor = read_json(state_path(notebook, "round.json"), {})
    stall = {"label": f"preparing {fern}", "at": service.now().isoformat(), "round": cursor["started_at"],
             "job_index": 0, "record": fern}
    later = datetime.now(timezone.utc) + timedelta(hours=refusals.RETRY_HOURS + 1)
    for retries in range(refusals.MAX_RETRIES):
        write_json(state_path(notebook, native.STALLED), stall)
        native._skip_stalled(notebook)
        assert refusals.refused_for(notebook, fern).get("retries", 0) == retries
        assert fern in refusals.due_for_retry(notebook, now=later)
        refusals.mark_retried(notebook, fern)  # what the retry job does before it prepares the page
    write_json(state_path(notebook, native.STALLED), stall)
    native._skip_stalled(notebook)
    # The existing rule: three retries on the same material, then it waits for new material.
    assert fern not in refusals.due_for_retry(notebook, now=later)


def test_new_slot_reads_no_mail_while_a_page_is_open_and_reads_it_after(notebook, monkeypatch):
    """The owner's live round.json shape: an open investigation, no mail_slot, job 2 of 8."""
    from datetime import timedelta
    config = read_config(notebook)
    slot = service.latest_slot(config, service.now() + service.EARLY_FIRE)
    cursor = native_round.prepare(notebook, config, scheduled=False)
    cursor.update(batch={"done": True}, batch_index=0, summaries=[], job_index=2, investigation_left=2,
                  jobs=[{"record": f"people/fixture-{n}.md", "kind": "person"} for n in range(8)],
                  slot=(slot - timedelta(days=1)).isoformat(), pending=None, project_quote=None,
                  current={"record": "people/fixture-2.md", "number": 2, "parts": [[]], "tail": "quotes",
                           "inquiry": "plan", "finalized": False})
    cursor.pop("mail_slot", None)
    read = []
    monkeypatch.setattr(native_round, "read_new_mail", lambda root, cursor, config, slot: read.append(slot))
    monkeypatch.setattr(native, "_new_task", lambda *a, **kw: {"outcome": "task"})
    native._next_round(notebook, cursor, scheduled=True, notices=[])
    assert read == []
    cursor["current"] = None
    native._next_round(notebook, cursor, scheduled=True, notices=[])
    assert read == [slot]


def test_parking_an_investigation_round_leaves_the_page_for_the_next_job(notebook):
    """Discard alone keeps an investigation on the same page (its next round); parking moves on."""
    cursor = native_round.prepare(notebook, read_config(notebook), scheduled=False)
    cursor.update(jobs=[{"record": "people/fixture-a.md", "kind": "person"},
                        {"record": "people/fixture-b.md", "kind": "person"}], job_index=0,
                  current={"record": "people/fixture-a.md", "number": 2})
    write_json(state_path(notebook, "round.json"), cursor)
    native._leave_job(notebook, {"operation": "investigation", "record": "people/fixture-a.md"})
    cursor = read_json(state_path(notebook, "round.json"), {})
    assert cursor["job_index"] == 1 and cursor["current"] is None
    native._leave_job(notebook, {"operation": "batch", "record": "people/fixture-b.md"})
    assert read_json(state_path(notebook, "round.json"), {})["job_index"] == 1


# 2026-11-16: on the owner's notebook one rejected candidate ("Dropped source id the
# page had") stopped a whole `co rem catchup` night, and the task it left pending
# made the next catchup exit with "a native task is pending".
REJECTED = "Dropped source id the page had: codex:fern:1"


def exec_model(root, monkeypatch):
    """The exec runner writes a candidate for every task; review rejects Fern's every time."""
    from connectonion.rem import schedule
    calls = []

    def run(directory, prompt, config, stage, **options):
        task = read_json(Path(directory) / "task.json", {})
        calls.append({"record": task["record"], "stage": stage, "prompt": prompt})
        if task["record"]:
            Path(task["candidate"]).write_text(f"# Draft {len(calls)}\n", encoding="utf-8")
        return {"result": "", "usage": {"input_tokens": 1}}

    def check(root, task, output):
        if task["record"] == "projects/fern.md":
            raise RemError(f"Candidate rejected, kept at {task['candidate']}: {REJECTED}")
        if task["record"]:
            Notebook(root).write(task["record"], "# Heron\n\nReviewed the pilot.\n")
        return {"changed": [task["record"]] if task["record"] else [], "report": ""}

    monkeypatch.setattr(runner, "run_task", run)
    monkeypatch.setattr(runner, "ready", lambda config: ("", ""))
    monkeypatch.setattr(native_round, "check_task", check)
    monkeypatch.setattr(schedule, "deepen_round", lambda root, **kw: {"rounds": [], "stopped": ""})
    return calls


def catchup(root, *args):
    return CliRunner().invoke(app, ["rem", "--root", str(root), *args, "catchup"])


def test_exec_feeds_a_rejection_back_then_parks_the_page_and_writes_the_next(notebook, monkeypatch):
    from connectonion.rem import schedule
    fern, heron = two_projects(notebook, monkeypatch)
    calls = exec_model(notebook, monkeypatch)
    result = schedule.exec_round(notebook, scheduled=False)
    assert (result["outcome"], result["reason"]) == ("done", "round done"), result
    tried = [call for call in calls if call["record"] == fern]
    # The existing limit: refused twice for the same reason parks the task.
    assert len(tried) == native.PARK_SAME_REASON
    assert tried[1]["stage"].endswith("(repair)") and REJECTED in tried[1]["prompt"]
    assert tried[1]["prompt"].startswith("## Required corrections")
    assert Notebook(notebook).read(heron).startswith("# Heron\n\nReviewed the pilot.\n")
    entry = refusals.refused_for(notebook, fern)
    assert entry["parked"].startswith("parked: refused twice for the same reason") and REJECTED in entry["parked"]
    assert Path(entry["candidate"]).read_text(encoding="utf-8") == "# Draft 2\n"
    assert [row["record"] for row in result["parked"]] == [fern]
    assert not read_json(state_path(notebook, "round.json"), {}).get("pending")
    # The finished round's cleanup keeps what the owner needs to look at.
    runner.scrub_finished_tasks(state_path(notebook, "tasks"))
    assert Path(entry["candidate"]).is_file()
    assert not (Path(entry["candidate"]).parent / "material.json").exists()


def test_catchup_resumes_a_task_left_pending_and_says_what_it_parked(notebook, monkeypatch):
    fern, heron = two_projects(notebook, monkeypatch)
    task = native.next_task(notebook)
    exec_model(notebook, monkeypatch)
    assert native.submit(notebook, task["id"])["outcome"] == "refused"  # the stopped run
    gone = subprocess.Popen([sys.executable, "-c", ""])
    gone.wait()
    saved = Path(task["material"]) / "task.json"
    write_json(saved, {**read_json(saved, {}), "claimed_by": {"pid": gone.pid, "started_at": NEW}})
    result = catchup(notebook)
    assert result.exit_code == 0, result.output
    assert "a native task is pending" not in result.output
    night = next(line for line in result.stdout.splitlines() if line.startswith("Night 1:"))
    assert f"1 page parked ({fern}: refused twice for the same reason: {REJECTED}" in night
    assert f"candidate kept at {Path(task['material']) / 'candidate.md'}" in night
    done = result.stdout[result.stdout.index("Done: 1 night"):]
    assert f"1 page parked ({fern}: refused twice for the same reason: {REJECTED}" in done
    assert f"candidates kept under {state_path(notebook, 'tasks')}" in done
    assert Notebook(notebook).read(heron).startswith("# Heron\n\nReviewed the pilot.\n")
    status = CliRunner().invoke(app, ["rem", "--root", str(notebook), "status"]).output
    assert f"{fern} · parked: refused twice for the same reason: {REJECTED}" in " ".join(status.split())
    # The next night may retry it (the existing rule) and says so again when it parks again.
    data = json.loads(catchup(notebook, "--json").stdout)["data"]
    assert [row["record"] for row in data["parked"]] == [fern] == [row["record"] for row in data["nights"][0]["parked"]]
    assert data["parked"][0]["why"] == f"refused twice for the same reason: {REJECTED}"
    assert data["candidates"] == str(state_path(notebook, "tasks"))


def test_a_parked_page_is_not_tried_again_in_the_same_night(notebook, monkeypatch):
    from connectonion.rem import catchup as nights, schedule
    fern, _ = two_projects(notebook, monkeypatch)
    calls = exec_model(notebook, monkeypatch)
    with nights.scope(notebook, 1):
        schedule.exec_round(notebook, scheduled=False)
        tried = sum(call["record"] == fern for call in calls)
        assert fern in refusals.parked_waiting(notebook) and fern not in refusals.due_for_retry(notebook)
        schedule.exec_round(notebook, scheduled=False)
        assert sum(call["record"] == fern for call in calls) == tried
    with nights.scope(notebook, 2):  # the existing rule: a later night may retry it
        assert fern not in refusals.parked_waiting(notebook) and fern in refusals.due_for_retry(notebook)


def test_exec_parks_a_task_whose_review_keeps_asking_without_counting(notebook, monkeypatch):
    """A claim-audit "continue" is refused without a count; exec must still end it."""
    from connectonion.rem import schedule
    fern, heron = two_projects(notebook, monkeypatch)
    calls = exec_model(notebook, monkeypatch)
    accept = native_round.check_task
    monkeypatch.setattr(native_round, "check_task", lambda root, task, output: (
        {"needs_review": "audit", "candidate": task["candidate"], "continue_review": "Continue checking"}
        if task["record"] == fern else accept(root, task, output)))
    result = schedule.exec_round(notebook, scheduled=False)
    assert result["reason"] == "round done", result
    assert sum(call["record"] == fern for call in calls) == native.PARK_TOTAL
    assert refusals.refused_for(notebook, fern)["parked"].startswith("parked: refused 3 times")
    assert Notebook(notebook).read(heron).startswith("# Heron\n\nReviewed the pilot.\n")
