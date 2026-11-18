"""#3105: the reader's Investigate button: what a page's state is, and the run it starts."""

import json
from datetime import datetime, timezone

import pytest

from connectonion.rem import page_runs, page_versions
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError, state_path, write_json

PAGE = "people/avery.md"
INVESTIGATED = ("# Avery Lin\n\n## Facts\n- Email: avery@example.org [1]\n\n## Who they are\n- Avery leads design. [1]\n\n"
                "## Sources\n- [1] gmail:aaaaaaaaaaaa\n\nInvestigation: mapped 2026-09-01 · investigated 2026-10-01 (gmail)\n")


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write(PAGE, INVESTIGATED)
    return root


def _run(root, run_id, *, phase, record=PAGE, started="2026-10-01T00:00:00+00:00", **fields):
    write_json(state_path(root, f"runs/run_{run_id:032x}.json"),
               {"id": f"run_{run_id:032x}", "phase": phase, "record": record, "started_at": started,
                "speed": "fast", "outcome": "completed", **fields})


def test_state_names_the_last_investigation_new_mail_and_open_leads(root):
    mails = {PAGE: ["2026-09-20", "2026-10-03", "2026-10-05"]}
    _run(root, 1, phase="enrich", report="- followed | site | [1] | nothing\n- open | the SOW thread | [1] | why | how\n"
                                         "- open | the deck | [1] | why | how\n- blocked | login | [1] | paywall")
    _run(root, 2, phase="investigate", usage={"input_tokens": 3_100_000, "cached_input_tokens": 100_000,
                                              "output_tokens": 0})
    state = page_runs.states(root, [PAGE], mail_days=mails)[PAGE]
    assert state["last"] == "2026-10-01"
    assert state["new_mails"] == 2 and state["leads"] == 2
    assert state["label"] == "update"
    assert state["cost"]["quick"] == 0.5
    assert state["undo"] is False and state["rewrite"] is None and state["run"] is None


@pytest.mark.parametrize("text,mails,report,label", [
    ("# Avery Lin\n\nInvestigation: mapped 2026-09-01 · not investigated yet\n", [], "", "investigate"),
    (INVESTIGATED, ["2026-10-02"], "- open | x | y | z | w", "update"),
    (INVESTIGATED, [], "- open | x | y | z | w", "deeper"),
    (INVESTIGATED, ["2026-09-30"], "- followed | x | y | z", "current"),
])
def test_the_button_label_follows_the_page(root, text, mails, report, label):
    Notebook(root).write(PAGE, text)
    if report:
        _run(root, 1, phase="enrich", report=report)
    assert page_runs.states(root, [PAGE], mail_days={PAGE: mails})[PAGE]["label"] == label


def test_a_run_starts_one_detached_worker_and_says_which_steps(root, monkeypatch):
    started = []

    class Process:
        pid = 4242

    monkeypatch.setattr(page_runs.subprocess, "Popen", lambda command, **kw: started.append(command) or Process())
    monkeypatch.setattr(page_runs, "_alive", lambda receipt: receipt.get("pid") == 4242)
    receipt = page_runs.start(root, PAGE, "full")
    assert receipt["steps"] == ["append", "enrich"] and receipt["result"] == "running"
    assert started[0][-4:] == ["--record", PAGE, "--mode", "full"]
    again = page_runs.start(root, PAGE, "quick")
    assert again["mode"] == "full" and len(started) == 1  # one run per page at a time
    assert page_runs.status(root, PAGE)["result"] == "running"


def test_the_command_each_mode_runs(root):
    assert page_runs.command(root, PAGE, "full")[-3:] == ["investigate", PAGE, "--enrich"]
    assert page_runs.command(root, PAGE, "quick")[-2:] == ["investigate", PAGE]
    assert page_runs.command(root, PAGE, "rewrite")[-3:] == ["investigate", PAGE, "--rewrite"]
    with pytest.raises(RemError):
        page_runs.start(root, PAGE, "deep")
    with pytest.raises(RemError):
        page_runs.start(root, "decisions/x.md", "full")


def test_status_follows_the_run_logs_step_by_step_and_ends_with_what_changed(root, monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    write_json(page_runs.receipt_path(root, PAGE), {"record": PAGE, "mode": "full", "steps": ["append", "enrich"],
                                                    "result": "running", "pid": 1, "started_at": now,
                                                    "before_sha256": page_runs._sha(INVESTIGATED)})
    monkeypatch.setattr(page_runs, "_alive", lambda receipt: True)
    _run(root, 1, phase="investigate", started=now, outcome="completed", stage="recording result")
    _run(root, 2, phase="enrich", started=now, outcome="running", stage="following leads")
    status = page_runs.status(root, PAGE)
    assert [(step["step"], step["state"]) for step in status["progress"]] == [("append", "done"), ("enrich", "running")]
    assert status["progress"][1]["stage"] == "following leads"
    after = INVESTIGATED.replace("- Avery leads design. [1]", "- Avery leads design. [1]\n- Avery joined the board. [1]")
    Notebook(root).write(PAGE, after)
    page_versions.keep_previous(root, PAGE, INVESTIGATED, after)
    monkeypatch.setattr(page_runs, "_alive", lambda receipt: False)
    write_json(page_runs.receipt_path(root, PAGE), {**json.loads(page_runs.receipt_path(root, PAGE).read_text()),
                                                    "result": "completed", "exit_code": 0})
    done = page_runs.status(root, PAGE)
    assert done["result"] == "completed" and done["changed"] is True
    assert done["added_lines"] == ["- Avery joined the board."] and done["added_count"] == 1
    renumbered = after.replace("[1]", "[2]").replace("- [2] gmail", "- [2] gmail")
    assert page_runs._added(INVESTIGATED, renumbered) == ["- Avery joined the board."]
    assert done["undo"] is True
    page_runs.undo(root, PAGE)
    assert Notebook(root).read(PAGE) == INVESTIGATED


def test_a_worker_that_died_without_a_receipt_reads_as_failed(root, monkeypatch):
    write_json(page_runs.receipt_path(root, PAGE), {"record": PAGE, "mode": "quick", "steps": ["append"],
                                                    "result": "running", "pid": 1,
                                                    "started_at": datetime.now(timezone.utc).isoformat(),
                                                    "before_sha256": page_runs._sha(INVESTIGATED)})
    monkeypatch.setattr(page_runs, "_alive", lambda receipt: False)
    assert page_runs.status(root, PAGE)["result"] == "failed"




def test_your_own_page_has_no_button_and_cannot_be_started_from_it(root):
    write_json(state_path(root, "map.json"), {"owner": {"record": PAGE}})
    assert page_runs.states(root, [PAGE], mail_days={}) == {}
    with pytest.raises(RemError, match="investigate me"):
        page_runs.start(root, PAGE, "full")
