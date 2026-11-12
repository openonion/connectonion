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


def two_projects(root, monkeypatch):
    """Fern and Heron each have one unread input, so an unchanged candidate is refused."""
    book, records = Notebook(root), ["projects/fern.md", "projects/heron.md"]
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
