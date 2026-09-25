"""`co schedule`: what the CLI writes is what the running scheduler obeys (#1685).

The CLI never talks to the Host. It writes `paused` and `run_requested` into
schedule-state.json, and these tests drive the real tick to prove the Host
reads them — the only thing that makes the commands mean anything.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.network.host import http_router
from connectonion.network.host import schedule as sched

runner = CliRunner()
YAML = '- name: sync\n  every: 1h\n  run: "/sync"\n- name: weekly\n  at: "Mon 09:00"\n  run: "/weekly"\n'


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / ".co").mkdir()
    (tmp_path / ".co" / "schedule.yaml").write_text(YAML, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path / ".co"


def co(*args):
    return runner.invoke(app, ["schedule", *args], terminal_width=200)


async def tick(co_dir, monkeypatch, now):
    ran = []
    monkeypatch.setattr(http_router, "input_handler",
                        lambda *a, **k: ran.append(a[2]) or {"status": "done"})
    start, _ = sched.create_schedule_lifespan(co_dir, lambda: None, None, 86400)
    await start.tick_once(now=now)
    return ran


@pytest.mark.asyncio
async def test_a_paused_entry_does_not_fire_and_a_resumed_one_does(project, monkeypatch):
    now = datetime.now(timezone.utc)
    assert co("pause", "sync").exit_code == 0
    assert await tick(project, monkeypatch, now) == []
    assert co("resume", "sync").exit_code == 0
    assert await tick(project, monkeypatch, now) == ["/sync"]


@pytest.mark.asyncio
async def test_run_fires_once_even_when_not_due_or_paused(project, monkeypatch):
    now = datetime.now(timezone.utc)
    for name in ("sync", "weekly"):
        sched.record_run(project, name, when=now, status="done", session_id="s")
    co("pause", "weekly")
    assert co("run", "weekly").exit_code == 0
    assert await tick(project, monkeypatch, now + timedelta(minutes=1)) == ["/weekly"]
    assert await tick(project, monkeypatch, now + timedelta(minutes=2)) == []
    state = sched.load_state(project)["weekly"]
    assert state["paused"] is True and "run_requested" not in state, "the request is consumed; the pause is kept"


def test_list_shows_next_run_and_paused(project):
    co("pause", "weekly")
    rows = {row["name"]: row for row in json.loads(co("list", "--json").stdout)["entries"]}
    assert rows["weekly"]["paused"] is True and rows["weekly"]["next_run"] is None
    assert rows["sync"]["next_run"] is not None and rows["sync"]["when"] == "every 1h"


def test_check_exits_1_and_names_each_ignored_entry(project):
    (project / "schedule.yaml").write_text(YAML + "- every: 0m\n  run: x\n", encoding="utf-8")
    result = co("check")
    assert result.exit_code == 1
    assert "entry 3" in result.stdout and "co schedule check" in result.stdout


def test_an_unknown_name_lists_the_real_ones(project):
    result = co("pause", "nope")
    assert result.exit_code == 1
    assert "'sync'" in result.stdout and "'weekly'" in result.stdout
    assert "paused" not in json.dumps(sched.load_state(project))


def test_no_schedule_says_where_it_looked_and_how_to_start(tmp_path, monkeypatch):
    (tmp_path / ".co").mkdir()
    monkeypatch.chdir(tmp_path)
    result = co()
    assert result.exit_code == 1
    assert "schedule.yaml does not exist" in result.stdout and "at:" in result.stdout
    assert "Next: co schedule check" in result.stdout


def test_the_cli_never_writes_schedule_yaml(project):
    before = (project / "schedule.yaml").read_bytes()
    for args in (["pause", "sync"], ["resume", "sync"], ["run", "sync"], ["check"], ["list"]):
        co(*args)
    assert (project / "schedule.yaml").read_bytes() == before


def test_next_run_for_a_weekly_entry_is_the_coming_monday():
    entry = sched.Entry(name="w", run="x", at="Mon 09:00")
    friday = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    state = {"w": {"last_run": friday.isoformat()}}
    assert sched.next_run(entry, state, friday) == datetime(2026, 9, 28, 9, 0, tzinfo=timezone.utc)
