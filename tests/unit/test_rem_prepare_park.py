"""A job that can never be prepared is set aside with its reason; the round goes on (#3402).

2026-11-23 06:15 on the owner's notebook: a skill page whose skill is no longer installed has no
`- File:` line. `skill_runs.prepare` raised "has no installed source file; run co rem map-skills
first" (map-skills cannot add one), every scheduled turn was handed the same job, and Today said
"REM 会自动重试，不需要你做什么" while N climbed. Same class as #3376, which parked a task whose
inputs changed; this is a job that cannot be prepared at all.
"""

import json
import re

import pytest

from connectonion.rem import native, native_round, service, skill_runs
from connectonion.rem.files import Notebook, RemError, read_json, state_path
from connectonion.rem.refusals import REFUSED, parked_waiting
from tests.unit import test_rem_fetch_stalls as stalls
from tests.unit.test_rem_fetch_stalls import round_of

notebook = stalls.notebook  # the same fixture notebook the stall tests use


def _skill_page(book, record, *, source=None):
    text = f"# {record.rsplit('/', 1)[-1][:-3]}\n\nKind: Skill\n\n## What it does\n\n- Writes kiln notes.\n"
    if source:
        text += f"\n## Source\n\n- File: {source}\n"
    book.write(record, text)


def test_a_skill_whose_file_is_gone_is_skipped_and_the_round_serves_the_next_page(notebook, monkeypatch):
    round_of(notebook, monkeypatch, [])
    book = Notebook(notebook)
    record = "skills/catalog/kiln-notes.md"
    _skill_page(book, record)
    before = book.read(record)
    cursor = read_json(state_path(notebook, "round.json"), {})
    cursor["jobs"].insert(0, {"record": record, "kind": "skill"})
    from connectonion.rem.files import write_json
    write_json(state_path(notebook, "round.json"), cursor)

    task = native.next_task(notebook)

    assert task["outcome"] == "task" and task["record"] == "projects/heron.md", task
    assert book.read(record) == before   # nothing was written to the page before giving up on it
    skipped = read_json(state_path(notebook, "round.json"), {}).get("skipped", [])
    assert any(row["record"] == record and "no longer installed" in row["reason"] for row in skipped), skipped


def test_the_round_does_not_list_a_skill_whose_file_is_gone(notebook, tmp_path):
    book = Notebook(notebook)
    gone, here = "skills/catalog/kiln-notes.md", "skills/catalog/heron-notes.md"
    source = tmp_path / "SKILL.md"
    source.write_text("---\nname: heron-notes\n---\nWrite heron notes.\n")
    _skill_page(book, gone)
    _skill_page(book, here, source=source)
    assert not skill_runs.installed(book, gone)
    assert skill_runs.installed(book, here)
    rows = native_round._installed_skills_only(notebook, [{"record": gone, "kind": "skill"},
                                                         {"record": here, "kind": "skill"},
                                                         {"record": "people/ivy.md", "kind": "person"}])
    assert [row["record"] for row in rows] == [here, "people/ivy.md"]


def test_a_page_whose_preparation_raises_is_parked_with_its_reason_and_the_round_goes_on(notebook, monkeypatch):
    """Any deterministic RemError while preparing one job sets that job aside; it is not handed back next turn."""
    round_of(notebook, monkeypatch, ["people/ivy.md"])

    def broken(*args, **kwargs):
        raise RemError("people/ivy.md has a malformed Handles line")

    monkeypatch.setattr(native_round, "_prepare_investigation", broken)
    task = native.next_task(notebook)

    assert task["outcome"] == "task" and task["record"] == "projects/heron.md", task
    entry = read_json(state_path(notebook, REFUSED), {})["people/ivy.md"]
    assert "malformed Handles line" in entry["parked"]
    assert "people/ivy.md" in parked_waiting(notebook)
    assert any("people/ivy.md" in notice and "malformed Handles line" in notice for notice in task["notices"])


@pytest.mark.parametrize("error", ["MAINTENANCE_BUSY", "TaskFault", "RunFailed"])
def test_a_busy_lock_or_a_runner_failure_is_not_parked(notebook, monkeypatch, error):
    """These are the weather, not the page: the job stays where it is for the next turn."""
    round_of(notebook, monkeypatch, ["people/ivy.md"])
    from connectonion.rem.files import MAINTENANCE_BUSY
    from connectonion.rem.runner import RunFailed
    raised = {"MAINTENANCE_BUSY": RemError(MAINTENANCE_BUSY), "TaskFault": native.TaskFault("Task input changed"),
              "RunFailed": RunFailed("codex exited 1")}[error]

    def busy(*args, **kwargs):
        raise raised

    monkeypatch.setattr(native_round, "_prepare_investigation", busy)
    with pytest.raises(type(raised)):
        native.next_task(notebook)
    assert "people/ivy.md" not in read_json(state_path(notebook, REFUSED), {})


def _failed_turns(root, reasons):
    from connectonion.rem.files import write_json
    for index, reason in enumerate(reasons):
        turn = {"turn_id": str(index), "started_at": f"2026-09-0{index + 1}T00:00:00Z", "result": "failed",
                "exit_code": 0, "reason": reason, "accepted": 0}
        write_json(state_path(root, f"turns/{index:03}.json"), turn)
    write_json(state_path(root, "last-turn.json"), turn)


def test_the_same_error_three_turns_running_is_counted_as_stuck(tmp_path, rem_clock):
    _failed_turns(tmp_path, ["skills/catalog/a.md has no installed source file; run co rem map-skills first"] * 5)
    assert service.schedule_failure(tmp_path)["same_error"] == 5


@pytest.mark.parametrize("reasons", [
    ["Turn exceeded 3 hours; the next fire continues the round"] * 3,
    ["The turn produced nothing: co rem next passed its deadline 3 times"] * 3,
    ["MAINTENANCE_BUSY: waited 10 minutes total; maintenance lock holder pid 1: x"] * 3,
    ["people/a.md failed", "people/b.md broke", "people/c.md failed again"]])
def test_weather_and_different_errors_are_not_stuck(tmp_path, rem_clock, reasons):
    _failed_turns(tmp_path, reasons)
    assert not service.schedule_failure(tmp_path).get("same_error")


@pytest.mark.parametrize("language,said,calm", [
    ("zh", "最近 5 轮都停在同一个问题上", "不需要你做什么"),
    ("en", "the last 5 turns stopped on the same problem", "nothing is needed from you")], ids=["zh", "en"])
def test_today_does_not_promise_a_retry_will_fix_the_same_error(language, said, calm):
    from connectonion.rem.reader import TEMPLATE
    from tests.unit.test_rem_reader import _run_reader_js
    function = re.search(r"function turnTrouble\(.*?\n\}", TEMPLATE.read_text(), re.S)[0]
    script = f'uiLanguage = {json.dumps(language)}; const REM = {{status: {{timezone: "UTC"}}}};\n' + function
    script += '\nconsole.log(JSON.stringify(turnTrouble(' + json.dumps({
        "code": "repeated_failure", "failures": 5, "same_error": 5, "since": "2026-11-22T19:15:05+00:00",
        "evidence": "skills/catalog/a.md has no installed source file; run co rem map-skills first"}) + ')));'
    output = _run_reader_js(script)
    assert said in output and calm not in output
    assert "map-skills" not in output and "skills/catalog" not in output
