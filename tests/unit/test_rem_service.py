"""Successive-pass orchestration tested with a synthetic, deterministic runner."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import Notebook, RemError, read_json, state_path, write_json
from connectonion.rem.service import approve_sources, run_sync, status, subscriptions, toggle_source
from tests.unit.test_rem_source import rollout
from tests.unit.test_rem_asana import asana_material

pytestmark = pytest.mark.usefixtures("rem_clock")


@pytest.mark.parametrize('results,last_message,blocked,visible', [
    (['failed', 'timed-out'], '', False, True),
    (['completed', 'completed'], 'The first attempt could not start; I retried and completed the round.', False, False),
    (['completed', 'completed'], 'Earlier MAINTENANCE_BUSY; retried and completed the round.', False, False),
    (['failed', 'completed'], '无法启动过，重试后已完成。', False, False),
    (['completed', 'completed'], 'MAINTENANCE_BUSY: waited 10 minutes total; maintenance lock holder pid 49443: co rem next --scheduled.', True, True),
    (['failed', 'completed'], 'Finished the work.', False, False),
    (['completed', 'failed'], '', False, False),
    (['failed', 'running'], '', False, False),
])
def test_status_today_surfaces_receipt_failures(rem, results, last_message, blocked, visible):
    from connectonion.cli.commands.rem_status import _today
    from connectonion.rem.reader import snapshot
    root, _ = rem
    for index, result in enumerate(results):
        last = state_path(root, f'turns/turn-{index}.last.md')
        last.parent.mkdir(exist_ok=True)
        last.write_text(last_message if index == 1 else '')
        turn = {'started_at': f'2026-11-0{index + 1}T03:00:00Z', 'result': result,
                'last_message': str(last), 'blocked': blocked if index == 1 else False,
                'reason': last_message if blocked else 'fictional timeout',
                **({'finished_at': f'2026-11-0{index + 1}T04:00:00Z'} if result != 'running' else {})}
        write_json(state_path(root, f'turns/turn-{index}.json'), turn)
    write_json(state_path(root, 'last-turn.json'), turn)
    value = status(root)
    line = value.get('schedule_failure', '')
    assert bool(line) == visible
    if visible:
        from rich.text import Text
        assert line == {'code': 'blocked' if blocked else 'repeated_failure',
                        'evidence': last_message if blocked else 'fictional timeout'}
        output = Text.from_markup(_today(root, value)[0]).plain
        assert output.startswith('Last scheduled turn did not finish:')
        assert ('run co rem start' if blocked else 'Retried automatically') in output
        assert line['evidence'] in output
        assert snapshot(root)['status']['schedule_failure'] == line


@pytest.mark.parametrize('message,blocked', [
    ('The first attempt could not start; I retried and completed the round.', False),
    ('Earlier MAINTENANCE_BUSY; the retry completed.', False),
    ('MAINTENANCE_BUSY: waited 10 minutes total; the earlier attempt failed, but the retry completed.', False),
    ('MAINTENANCE_BUSY: waited 10 minutes total; maintenance lock holder pid 49443: co rem next --scheduled. '
     'Report this message and end the turn without retrying.', True),
])
def test_turn_receipt_records_terminal_busy_outcome(rem, monkeypatch, message, blocked):
    from subprocess import CompletedProcess
    from connectonion.rem import codex_exec
    root, _ = rem
    monkeypatch.setattr(codex_exec, '_start_command', lambda root, last: ['fictional-codex', str(last)])
    monkeypatch.setattr('connectonion.rem.codex_schedule.CodexNative.recent_desktop_fire', lambda self, root: False)

    def run(command, **kwargs):
        from pathlib import Path
        Path(command[1]).write_text(message)
        return CompletedProcess(command, 0)

    codex_exec.run_turn(root, run=run)
    receipt = read_json(state_path(root, 'last-turn.json'), {})
    assert receipt['blocked'] is blocked
    assert bool(status(root).get('schedule_failure')) is blocked


@pytest.fixture
def rem(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.rem.service.claude_projects_root", lambda: tmp_path / "no-claude")
    monkeypatch.setattr("connectonion.rem.service._boot_time", lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    prepare(root)
    approve_sources(root)
    return root, sessions


def test_successive_correction_and_no_input_does_not_invoke_runner(rem):
    root, sessions = rem
    path = sessions / "rollout-a.jsonl"
    messages = [("user", "We choose SQL")]
    calls = []

    def runner(notebook, items, config, kind=""):
        calls.append(items)
        content = "# Storage\n" + items[-1]["text"]
        notebook.write("decisions/storage.md", content)
        return {"usage": {"input_tokens": 10, "output_tokens": 4},
                "changed": ["decisions/storage.md"]}

    rollout(path, messages)
    assert run_sync(root, runner=runner)["outcome"] == "completed"
    assert run_sync(root, runner=runner)["outcome"] == "no_change"
    rollout(path, messages + [("user", "Correction: choose Markdown")])
    assert run_sync(root, runner=runner)["outcome"] == "completed"
    assert len(calls) == 2
    assert "Correction: choose Markdown" in Notebook(root).read("decisions/storage.md")
    assert status(root)["runner_attempts_today"] == 2
    assert status(root)["usage_today"]["input_tokens"] == 20


def test_a_night_with_nothing_new_calls_no_model_and_leaves_no_run(rem):
    """Nights with nothing new each left a run in `co rem logs` and its usage
    count (#1846). Nothing was read and nothing was spent: nothing to record."""
    from connectonion.rem.service import run_logs
    root, sessions = rem
    rollout(sessions / "rollout-a.jsonl", [("user", "We choose SQL")])
    calls = []
    runner = lambda notebook, items, config, kind="": calls.append(items) or {"usage": {"input_tokens": 10}}
    worked = run_sync(root, runner=runner)
    assert worked["speed"] == "fast"
    assert worked["harness"] == read_config(root)["runner"]
    quiet = run_sync(root, runner=runner)
    assert quiet["outcome"] == "no_change" and len(calls) == 1
    assert [record["id"] for record in run_logs(root)] == [worked["id"]]


def test_changed_session_is_reported_while_safe_session_advances(rem):
    root, sessions = rem
    changed = sessions / "rollout-a.jsonl"
    rollout(changed, [("user", "first")])
    calls = []
    run_sync(root, runner=_runner_recording(calls))
    before = read_json(state_path(root, "progress.json"), {})["codex"]["rollout-a.jsonl"]

    rollout(changed, [("user", "rewritten")])
    rollout(sessions / "rollout-b.jsonl", [("user", "safe new request")])
    result = run_sync(root, runner=_runner_recording(calls))
    after = read_json(state_path(root, "progress.json"), {})["codex"]
    assert result["outcome"] == "completed" and len(calls) == 2
    assert result["source_skips"] == [{"source": "codex", "file": "rollout-a.jsonl",
                                       "reason": "processed prefix changed"}]
    assert "changed session file" in result["warning"]
    assert after["rollout-a.jsonl"] == before and "rollout-b.jsonl" in after


def test_status_warns_about_the_last_scheduled_source_skip(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "fake",
                                                "last_scheduled_outcome": "no_change",
                                                "last_scheduled_warning": "1 changed session file skipped"})
    shown = status(root)
    assert shown["state"].startswith("Background needs attention")
    assert "changed session file" in shown["state"] and shown["next_run"]


def test_failed_daily_investigation_takes_priority_over_source_warning(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "fake",
                                                "last_scheduled_outcome": "failed",
                                                "last_scheduled_reason": "the last scheduled investigation failed",
                                                "last_scheduled_warning": "1 changed session file skipped"})
    shown = status(root)
    assert "investigation failed" in shown["state"]


def _two_people(rem, monkeypatch):
    """Tally already cites the one message naming her; Kit has read nothing."""
    root, sessions = rem
    notebook = Notebook(root)
    notebook.stub_person("people/tally.md", "Tally Ho", [])
    notebook.stub_person("people/kit.md", "Kit Kite", [])
    rollout(sessions / "rollout-t.jsonl", [("user", "Tally Ho ships it friday")])
    offset = len((sessions / "rollout-t.jsonl").read_text().splitlines()[0]) + 1
    notebook.write("people/tally.md", notebook.read("people/tally.md").replace(
        "- (none yet)", f"- [1] codex:rollout-t:{offset} — 2026-09-07"))
    turns = []

    def one_turn(book, items, config, kind="", stage="maintain", maintenance_lock_held=False):
        turns.append(next(item["record"] for item in items if item.get("role") == "page"))
        return {"changed": [], "usage": {"input_tokens": 110_000}, "review_candidates": []}

    monkeypatch.setattr("connectonion.rem.runner.run_stage", one_turn)
    return root, sessions, turns


def test_a_page_already_written_from_its_material_gets_no_turn(rem, monkeypatch):
    """Two of three page turns in a measured batch changed nothing, at about
    110k tokens each (#1846). The page with something new still gets its turn."""
    root, sessions, turns = _two_people(rem, monkeypatch)
    rollout(sessions / "rollout-k.jsonl", [("user", "Kit Kite says the logo is late")])
    record = run_sync(root)
    assert turns == ["people/kit.md"]
    assert record["up_to_date"] == ["people/tally.md"] and record["runner_attempts"] == 1


def test_material_every_page_has_already_read_spends_nothing(rem, monkeypatch):
    root, sessions, turns = _two_people(rem, monkeypatch)
    record = run_sync(root)
    assert turns == [] and record["runner_attempts"] == 0 and record["usage"] is None
    assert record["outcome"] == "completed" and record["up_to_date"] == ["people/tally.md"]
    assert read_json(state_path(root, "progress.json"), {})   # read, so not read again tomorrow
    assert run_sync(root)["outcome"] == "no_change"


def test_a_project_with_folders_is_left_to_the_project_writer(rem, monkeypatch):
    """projects/connectonion was rewritten by the sync and the project writer in
    turn, 16 times in 5 days, shrinking each time the sync had it (2026-10-13/14).
    Its sessions are the project writer's; the sync spends nothing on them."""
    root, sessions = rem
    Notebook(root).stub_project("projects/kite.md", "kite", ["/work/kite"])
    monkeypatch.setattr("connectonion.rem.runner.run_stage", lambda *a, **k: pytest.fail("no sync turn"))
    rollout(sessions / "rollout-k.jsonl", [("user", "the logo is late")], project="/work/kite")
    record = run_sync(root)
    assert record["for_project_writer"] == ["projects/kite.md"] and record["runner_attempts"] == 0


def test_a_project_is_not_a_lead_for_a_word_in_its_title(rem, monkeypatch):
    """"browser" is in nearly every session (`co browser`): projects/browser got a
    turn on 12 of 26 syncs, 9 of them NO CHANGE, 5.36M tokens (2026-10-10..15)."""
    from connectonion.rem.leads import page_leads
    root, _ = rem
    notebook = Notebook(root)
    notebook.stub_project("projects/browser.md", "browser", ["/work/browser"])
    notebook.stub_project("projects/notes.md", "notes", [])
    items = [{"text": "open it with co browser and keep notes", "project": "/work/site", "source": "codex:a:1"}]
    assert page_leads(notebook, items) == ["projects/notes.md"]


def test_a_page_that_changed_nothing_rests_a_day(rem, monkeypatch):
    root, sessions, turns = _two_people(rem, monkeypatch)
    rollout(sessions / "rollout-k.jsonl", [("user", "Kit Kite says the logo is late")])
    run_sync(root)
    rollout(sessions / "rollout-k.jsonl", [("user", "Kit Kite says the logo is late"), ("user", "Kit Kite again")])
    record = run_sync(root)
    assert turns == ["people/kit.md"] and record["cooling"] == ["people/kit.md"]


def test_each_sync_starts_at_the_source_after_the_one_read_last(tmp_path, monkeypatch):
    """26 syncs read only codex, which always had 40 items; claude-code, gmail and
    outlook never got a cursor (2026-10-10..15)."""
    from connectonion.rem.config import default_config
    from connectonion.rem.service import _sync_locked
    from tests.unit.test_rem_source import subscription
    monkeypatch.setattr("connectonion.rem.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    root = tmp_path / "rem"
    prepare(root)
    selected = {}
    for name in ("codex", "other"):
        rollout(tmp_path / name / "rollout-a.jsonl", [("user", f"one from {name}")])
        rollout(tmp_path / name / "rollout-b.jsonl", [("user", f"two from {name}")])
        selected[name] = {**subscription(tmp_path / name), "kind": "codex"}
    config = default_config()
    config["limits"]["extract_items_per_batch"] = 1
    progress, read = {}, []
    for _ in range(3):
        record = _sync_locked(root, selected, progress, config, lambda nb, items, c, kind="": {"changed": []})
        read += list(record["items_by_source"])
        progress = read_json(state_path(root, "progress.json"), {})
    assert read == ["codex", "other", "codex"]


def test_failure_preserves_progress_and_counts_attempt(rem):
    root, sessions = rem
    rollout(sessions / "rollout-a.jsonl", [("user", "private sample text")])

    def failing(*args):
        raise RuntimeError("private sample text must not enter logs")

    result = run_sync(root, runner=failing)
    assert result["outcome"] == "failed"
    assert result["usage"] is None
    assert "private sample" not in str(result)
    assert read_json(state_path(root, "progress.json"), {}) == {}
    assert status(root)["runner_attempts_today"] == 1


def test_natural_refusal_does_not_advance_source_progress(rem, monkeypatch):
    root, sessions = rem
    rollout(sessions / 'rollout-refusal.jsonl', [('user', 'Remember the Aurora decision')])
    monkeypatch.setattr('connectonion.rem.runner.run_task', lambda *args, **kwargs: {
        'outcome': 'natural', 'result': 'I could not read the material.',
        'usage': {'input_tokens': 7}})

    result = run_sync(root)
    assert result['outcome'] == 'failed'
    assert result['usage'] == {'input_tokens': 7}
    assert read_json(state_path(root, 'progress.json'), {}) == {}
    assert status(root)['runner_attempts_today'] == 1


def test_unsubscribe_survives_approval_and_does_not_erase(rem):
    root, sessions = rem
    Notebook(root).write("people/alice.md", "Keep this")
    toggle_source(root, "codex", False)
    approve_sources(root)
    assert subscriptions(root)["codex"]["enabled"] is False
    assert Notebook(root).read("people/alice.md") == "Keep this"
    assert run_sync(root, runner=lambda *args, **kw: pytest.fail("invoked"))["outcome"] == "no_change"


@pytest.mark.parametrize("options", [{}, {"all_pending": True}, {"scheduled": True}, {"all_pending": True, "scheduled": True}])
def test_dry_run_has_no_state_or_body_effects(rem, monkeypatch, options):
    root, sessions = rem
    rollout(sessions / "rollout-a.jsonl", [("user", "private")])
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    monkeypatch.setattr("connectonion.rem.service.collect", lambda *a, **kw: pytest.fail("dry-run collected bodies"))
    result = run_sync(root, dry_run=True, **options)
    assert result["dry_run"] is True
    after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert result["sources"]["codex"]["message_count"] is None


def test_unconsented_start_cannot_infer(tmp_path):
    prepare(tmp_path)
    with pytest.raises(RemError, match="start"):
        run_sync(tmp_path, runner=lambda *args, **kw: pytest.fail("invoked"))


def test_too_small_input_limit_is_not_called_no_change(rem):
    root, sessions = rem
    rollout(sessions / "rollout-a.jsonl", [("user", "pending")])
    set_config(root, ["limits.input_chars_per_batch", "1"])
    with pytest.raises(RemError, match="input limit"):
        run_sync(root, runner=lambda *args, **kw: pytest.fail("invoked"))


def test_budget_failure_does_not_acknowledge_pending_messages(rem):
    root, sessions = rem
    path = sessions / "rollout-a.jsonl"
    set_config(root, ["limits.runner_calls_per_day", "1"])
    rollout(path, [("user", "first")])
    run_sync(root, runner=lambda *args, **kw: {"usage": None})
    before = state_path(root, "progress.json").read_bytes()
    rollout(path, [("user", "first"), ("user", "second")])
    with pytest.raises(RemError, match="limit"):
        run_sync(root, runner=lambda *args, **kw: pytest.fail("invoked"))
    assert state_path(root, "progress.json").read_bytes() == before


def test_interruption_keeps_partial_writes_but_not_checkpoint(rem):
    root, sessions = rem
    rollout(sessions / "rollout-a.jsonl", [("user", "keep the rationale")])
    def interrupted(notebook, *args, **kw):
        notebook.write("notes/partial.md", "Partial but valid Markdown")
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run_sync(root, runner=interrupted)
    assert status(root)["last_run"]["outcome"] == "interrupted"
    assert not state_path(root, "progress.json").exists()
    assert Notebook(root).read("notes/partial.md") == "Partial but valid Markdown"


class FakeScheduler:
    def __init__(self):
        self.installed = []
        self.uninstalled = []

    def install(self, root, config):
        self.installed.append(root)
        return {"scheduler": "fake", "label": "fake.label", "plist": str(root / "fake.plist")}

    def uninstall(self, root):
        self.uninstalled.append(root)
        return True

    def describe(self, root):
        return {"installed": root in self.installed}


def _runner_recording(calls):
    def runner(notebook, items, config, kind=""):
        calls.append(items)
        notebook.write("notes/first.md", "# First\n" + items[0]["text"])
        return {"usage": None, "changed": ["notes/first.md"]}
    return runner


def test_systemd_start_enables_worker_and_status_then_stop_removes_timer(rem, tmp_path, monkeypatch):
    from connectonion.rem.service import start, stop, worker_state
    from tests.unit.test_rem_schedule import make_systemd
    root, sessions = rem
    scheduler, _ = make_systemd(tmp_path, monkeypatch)
    monkeypatch.setattr("connectonion.rem.service.sys.platform", "linux")
    monkeypatch.setattr("connectonion.rem.schedule.Systemd", lambda: scheduler)
    monkeypatch.setattr("connectonion.rem.codex_history.archive_history", lambda *a, **kw: {})
    state_path(root, "consent.json").unlink()  # exercise the first batch, not a previously approved start
    rollout(sessions / "rollout-a.jsonl", [("user", "remember this")])
    result = start(root, confirm=lambda s: True, scheduler=scheduler, runner=_runner_recording([]))
    assert result["started"] and result["first_batch"]["outcome"] == "completed"
    assert worker_state(root)["enabled"] is True and worker_state(root)["scheduler"] == "systemd"
    shown = status(root)
    assert "Scheduled with systemd" in shown["state"] and shown["next_run"]
    assert shown["last_run"]["outcome"] == "completed" and "awake" not in shown["state"]
    stop(root, scheduler=scheduler)
    assert worker_state(root)["enabled"] is False and not scheduler.installed(root)
    assert status(root)["state"].startswith("Stopped")


@pytest.mark.parametrize("missing", [True, False])
def test_systemd_status_does_not_claim_an_absent_or_inactive_timer_is_scheduled(rem, tmp_path, monkeypatch, missing):
    from tests.unit.test_rem_schedule import make_systemd
    root, _ = rem
    scheduler, _ = make_systemd(tmp_path, monkeypatch, active=False)
    monkeypatch.setattr("connectonion.rem.schedule.Systemd", lambda: scheduler)
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "systemd"})
    if not missing:
        scheduler.install(root, read_config(root))
    shown = status(root)
    assert shown["next_run"] is None and "co rem start" in shown["state"]
    assert ("Not scheduled here" if missing else "Background needs attention") in shown["state"]


@pytest.mark.parametrize("available", [True, False])
def test_linux_consent_names_systemd_without_mac_awake_wording(rem, monkeypatch, available):
    from connectonion.cli.commands.rem_output import render
    from connectonion.rem.service import consent_summary
    root, _ = rem
    monkeypatch.setattr("connectonion.rem.service.sys.platform", "linux")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/systemctl" if available else None)
    summary = consent_summary(root)
    text = render(summary, "start — source access and schedule")
    for shown in (summary["background"], text):
        if available:
            assert "systemd user timer" in shown and "loginctl enable-linger" in shown
        else:
            assert "manual sync or cron" in shown and "systemd user timer" not in shown
        assert "awake" not in shown and "launchd" not in shown


def test_declined_start_reads_nothing_and_installs_nothing(tmp_path, monkeypatch):
    from connectonion.rem.service import start
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    rollout(sessions / "rollout-a.jsonl", [("user", "private")])
    shown, calls, scheduler = [], [], FakeScheduler()
    result = start(root, confirm=lambda summary: shown.append(summary) or False,
                   scheduler=scheduler, runner=_runner_recording(calls))
    assert result["started"] is False
    assert str(sessions) in str(shown[0])  # the summary names the exact directory it would read
    assert not state_path(root, "consent.json").exists()
    assert scheduler.installed == [] and calls == []


def test_a_copied_notebook_does_not_claim_the_original_s_schedule(tmp_path, monkeypatch):
    """#1964: worker.json travels with a copy; status said "Running in background"
    and doctor "ok schedule" for a launchd job whose --root was the original."""
    from connectonion.rem.schedule import Launchd
    root = tmp_path / "copy"
    prepare(root)
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "launchd",
                                                 "label": "ai.openonion.co-wiki"})

    shown = status(root)
    assert shown["state"].startswith("Not scheduled here") and shown["next_run"] is None

    plist = Launchd().plist_path(root)
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text("<plist/>")
    monkeypatch.setattr(Launchd, "describe", lambda self, root: {"loaded": True, "last_exit_code": "0"})
    assert status(root)["state"].startswith("Running in background")


def test_a_loaded_job_with_failed_exit_is_not_reported_healthy(tmp_path, monkeypatch):
    from connectonion.rem.schedule import Launchd
    root = tmp_path / "rem"
    prepare(root)
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "launchd"})
    monkeypatch.setattr(Launchd, "installed", lambda self, root: True)
    monkeypatch.setattr(Launchd, "describe", lambda self, root: {"loaded": True, "last_exit_code": "1"})
    monkeypatch.setattr("connectonion.rem.service.sys.platform", "darwin")
    assert "last launchd exit code 1" in status(root)["state"]


def test_a_new_job_that_has_never_exited_is_healthy(tmp_path, monkeypatch):
    from connectonion.rem.schedule import Launchd
    root = tmp_path / "rem"
    prepare(root)
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "launchd"})
    monkeypatch.setattr(Launchd, "installed", lambda self, root: True)
    monkeypatch.setattr(Launchd, "describe", lambda self, root: {
        "loaded": True, "last_exit_code": "(never exited)"})
    monkeypatch.setattr("connectonion.rem.service.sys.platform", "darwin")
    assert status(root)["state"].startswith("Running in background")


def test_first_start_consents_installs_and_runs_one_batch_then_repeat_start_does_not_rerun(tmp_path, monkeypatch):
    from connectonion.rem.service import start
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.rem.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    calls, scheduler = [], FakeScheduler()
    result = start(root, confirm=lambda summary: True, scheduler=scheduler, runner=_runner_recording(calls))
    assert result["started"] is True and result["first_batch"]["outcome"] == "completed"
    assert state_path(root, "consent.json").is_file()
    assert scheduler.installed == [root.resolve()]
    assert read_json(state_path(root, "worker.json"), {})["enabled"] is True
    assert "Running" in status(root)["state"]
    again = start(root, confirm=lambda summary: pytest.fail("consent asked twice"),
                  scheduler=scheduler, runner=_runner_recording(calls))
    assert again["started"] is True and again["first_batch"] is None
    assert len(calls) == 1


def test_init_can_start_the_schedule_without_repeating_its_first_batch(tmp_path, monkeypatch):
    from connectonion.rem.service import start
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    calls, scheduler = [], FakeScheduler()
    result = start(root, confirm=lambda summary: True, scheduler=scheduler,
                   runner=_runner_recording(calls), run_first_batch=False)
    assert result["started"] is True and result["first_batch"] is None
    assert calls == [] and scheduler.installed == [root.resolve()]
    assert state_path(root, "consent.json").is_file()


def test_stop_disables_background_but_manual_sync_still_works(tmp_path, monkeypatch):
    from connectonion.rem.service import start, stop
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.rem.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    calls, scheduler = [], FakeScheduler()
    start(root, confirm=lambda s: True, scheduler=scheduler, runner=_runner_recording(calls))
    assert stop(root, scheduler=scheduler)["enabled"] is False
    assert scheduler.uninstalled == [root.resolve()]
    assert "Stopped" in status(root)["state"] and "start" in status(root)["state"]
    rollout(sessions / "rollout-a.jsonl", [("user", "hello"), ("user", "more")])
    assert run_sync(root, runner=_runner_recording(calls))["outcome"] == "completed"


def test_start_without_a_scheduler_keeps_consent_and_points_to_manual_sync(tmp_path, monkeypatch):
    from connectonion.rem.schedule import Unsupported
    from connectonion.rem.service import start
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    with pytest.raises(RemError, match="co rem sync"):
        start(root, confirm=lambda s: True, scheduler=Unsupported(), runner=lambda *a, **kw: pytest.fail("ran"))
    assert state_path(root, "consent.json").is_file()


def test_stop_does_not_wait_for_a_running_batch(tmp_path, monkeypatch):
    """launchd fires a batch the moment the job loads; stop must still work while it runs."""
    from connectonion.rem.service import start, stop
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    scheduler = FakeScheduler()
    start(root, confirm=lambda s: True, scheduler=scheduler, runner=_runner_recording([]))
    import os
    import subprocess  # noqa: E401 - a second process holds the lock, as a real batch would
    import sys
    import textwrap
    from pathlib import Path
    import connectonion
    # The child imports this checkout, not whatever is installed: with a
    # relative PYTHONPATH and another test's chdir, it imported an older
    # connectonion with no rem, died, and this failed at random under -n 8.
    checkout = str(Path(connectonion.__file__).resolve().parent.parent)
    holder = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import time
        from pathlib import Path
        from connectonion.rem.files import maintenance_lock
        with maintenance_lock(Path({str(root.resolve())!r})):
            print("held", flush=True); time.sleep(30)
    """)], stdout=subprocess.PIPE, text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [checkout, os.environ.get("PYTHONPATH")]))})
    try:
        assert holder.stdout.readline().strip() == "held"
        assert stop(root, scheduler=scheduler)["enabled"] is False
        assert scheduler.uninstalled == [root.resolve()]
    finally:
        holder.kill()


def test_first_batch_runs_before_the_clock_is_installed(tmp_path, monkeypatch, rem_sydney_slot):
    """Otherwise the job's run-at-load batch and the foreground batch race for the lock."""
    from connectonion.rem.service import start
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")], timestamp=rem_sydney_slot.isoformat())
    order = []

    class Ordered(FakeScheduler):
        def install(self, root, config):
            order.append("install")
            return super().install(root, config)

    def runner(notebook, items, config, kind=""):
        order.append("batch")
        return {"usage": None, "changed": []}
    start(root, confirm=lambda s: True, scheduler=Ordered(), runner=runner)
    assert order == ["batch", "install"]


@pytest.mark.parametrize("zone", ["UTC", "Australia/Sydney"])
@pytest.mark.parametrize("clock,items", [("04:59", 1), ("05:00", 1), ("05:01", 0),
                                         ("05:35", 0), ("05:51", 0), ("06:05", 0)])
def test_first_batch_respects_the_sixty_day_lookback_in_any_zone(tmp_path, monkeypatch, zone, clock, items):
    """September 7 05:00Z material expires after November 6 05:00Z, independently of slots."""
    from connectonion.rem.service import start

    moment = datetime.fromisoformat(f"2026-11-06T{clock}+00:00")
    monkeypatch.setattr("connectonion.rem.service.now", lambda: moment)
    monkeypatch.setattr("connectonion.rem.config.local_timezone", lambda: zone)
    sessions = tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    calls = []
    result = start(tmp_path / "rem", confirm=lambda summary: True, scheduler=FakeScheduler(),
                   runner=_runner_recording(calls))
    assert result["first_batch"]["items"] == items
    assert len(calls) == items


def test_sigterm_during_a_batch_is_recorded_as_interrupted(rem):
    """launchctl bootout terminates the job; the run must not stay 'running' forever."""
    import os
    import signal
    root, sessions = rem
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])

    def runner(notebook, items, config, kind=""):
        os.kill(os.getpid(), signal.SIGTERM)
        raise AssertionError("SIGTERM should have interrupted the batch")
    with pytest.raises(KeyboardInterrupt):
        run_sync(root, runner=runner)
    from connectonion.rem.service import run_logs
    assert run_logs(root)[0]["outcome"] == "interrupted"
    assert read_json(state_path(root, "progress.json"), {}) == {}


def test_latest_slot_is_the_most_recent_saved_time_in_the_saved_zone():
    from datetime import datetime, timezone

    from connectonion.rem.service import latest_slot
    config = {"schedule": {"times": ["03:00", "17:00"], "timezone": "Australia/Sydney"}}
    # 2026-09-07 12:00 UTC is 22:00 in Sydney: the 17:00 slot of that day is the latest.
    slot = latest_slot(config, datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    assert slot.isoformat() == "2026-09-07T17:00:00+10:00"
    # 2026-09-07 06:30 UTC is 16:30 Sydney: 17:00 has not come, so 03:00 today is the latest.
    slot = latest_slot(config, datetime(2026, 9, 7, 6, 30, tzinfo=timezone.utc))
    assert slot.isoformat() == "2026-09-07T03:00:00+10:00"


def test_scheduled_sync_runs_once_per_slot_and_coalesces_missed_ones(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from connectonion.rem.service import start
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    clock = {"now": datetime(2026, 9, 7, 6, 30, tzinfo=timezone.utc)}  # 16:30 Sydney
    monkeypatch.setattr("connectonion.rem.service.now", lambda: clock["now"])
    set_config(root, ["schedule.timezone", "Australia/Sydney", "schedule.times", "03:00,17:00,18:00"])
    calls = []
    start(root, confirm=lambda s: True, scheduler=FakeScheduler(), runner=_runner_recording(calls))
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    # Installed after today's 03:00: that slot is not owed, so a tick before 17:00 does nothing.
    assert run_sync(root, scheduled=True, runner=_runner_recording(calls)) is None
    clock["now"] = datetime(2026, 9, 7, 7, 2, tzinfo=timezone.utc)   # 17:02 Sydney -> due
    assert run_sync(root, scheduled=True, runner=_runner_recording(calls))["outcome"] == "completed"
    assert run_sync(root, scheduled=True, runner=_runner_recording(calls)) is None  # same slot, served
    rollout(sessions / "rollout-a.jsonl", [("user", "hello"), ("user", "more")])
    clock["now"] = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)   # next day 11:00: 18:00 and 03:00 missed
    assert run_sync(root, scheduled=True, runner=_runner_recording(calls))["outcome"] == "completed"
    assert run_sync(root, scheduled=True, runner=_runner_recording(calls)) is None  # one catch-up, not two
    assert len(calls) == 2


def test_a_scheduled_tick_a_minute_early_serves_the_coming_slot(tmp_path, monkeypatch):
    """Codex fired the 03:00 slot at 02:59; REM saw last night's slot already served
    and skipped the run, so the slot was lost."""
    from datetime import datetime, timezone

    from connectonion.rem.service import start
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    clock = {"now": datetime(2026, 9, 7, 6, 30, tzinfo=timezone.utc)}  # 16:30 Sydney
    monkeypatch.setattr("connectonion.rem.service.now", lambda: clock["now"])
    set_config(root, ["schedule.timezone", "Australia/Sydney", "schedule.times", "17:00,18:00"])
    calls = []
    start(root, confirm=lambda s: True, scheduler=FakeScheduler(), runner=_runner_recording(calls))
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    clock["now"] = datetime(2026, 9, 7, 6, 59, tzinfo=timezone.utc)   # 16:59 Sydney, a minute early
    assert run_sync(root, scheduled=True, runner=_runner_recording(calls))["outcome"] == "completed"
    clock["now"] = datetime(2026, 9, 7, 7, 3, tzinfo=timezone.utc)    # 17:03: the same slot, served
    assert run_sync(root, scheduled=True, runner=_runner_recording(calls)) is None
    assert read_json(state_path(root, "worker.json"), {})["last_scheduled_slot"] == "2026-09-07T17:00:00+10:00"


@pytest.mark.parametrize("phase", ["sync", "daily-investigation", "daily-update"])
@pytest.mark.parametrize("alive", [True, False])
def test_scheduled_sync_leaves_slot_owed_while_a_local_run_is_alive(rem, monkeypatch, phase, alive):
    import os
    from connectonion.rem import service
    root, _ = rem
    set_config(root, ["schedule.timezone", "UTC", "schedule.times", "11:00,12:00"])
    worker = {"enabled": True, "last_scheduled_slot": "2026-09-07T11:00:00+00:00"}
    write_json(state_path(root, "worker.json"), worker)
    path = state_path(root, "runs/run_" + "a" * 32 + ".json")
    started = "2026-09-07T11:00:00+00:00"
    write_json(path, {"id": "run_" + "a" * 32, "started_at": started, "phase": phase,
                      "outcome": "running", **service.running_marker(),
                      "pid": os.getpid() if alive else 2 ** 22 + 7})
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a, **kw: pytest.fail("no model needed"))

    result = run_sync(root, scheduled=True)

    if alive:
        assert result == {"outcome": "busy", "reason": f"a scheduled sync started at {started} is still running"}
        assert service.worker_state(root) == worker
        assert read_json(path, {})["outcome"] == "running"
    else:
        assert result["outcome"] == "no_change"
        assert read_json(path, {})["outcome"] == "abandoned"
        assert service.worker_state(root)["last_scheduled_slot"] == "2026-09-07T12:00:00+00:00"


def test_scheduled_busy_cli_prints_reason_and_next_and_starts_no_daily_work(rem, monkeypatch):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.rem import service
    root, _ = rem
    set_config(root, ["schedule.timezone", "UTC", "schedule.times", "11:00,12:00"])
    write_json(state_path(root, "worker.json"), {"enabled": True, "last_scheduled_slot": "2026-09-07T11:00:00+00:00"})
    started = "2026-09-07T11:00:00+00:00"
    write_json(state_path(root, "runs/run_" + "b" * 32 + ".json"), {
        "started_at": started, "outcome": "running", "phase": "daily-investigation", **service.running_marker()})
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a, **kw: pytest.fail("busy must stop"))

    result = CliRunner().invoke(app, ["rem", "--root", str(root), "sync", "--scheduled"])

    assert result.exit_code == 0, result.output
    assert result.output.strip().splitlines() == [f"a scheduled sync started at {started} is still running",
                                                f"Next: co rem --root {root} logs"]


def test_scheduled_ownership_covers_gaps_between_stage_records_and_retries_next_tick(rem, monkeypatch):
    from connectonion.rem import service
    root, _ = rem
    set_config(root, ["schedule.timezone", "UTC", "schedule.times", "11:00,12:00,13:00"])
    worker = {"enabled": True, "last_scheduled_slot": "2026-09-07T11:00:00+00:00"}
    write_json(state_path(root, "worker.json"), worker)
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a, **kw: pytest.fail("no model needed"))

    def between_stages():
        monkeypatch.setattr(service, "now", lambda: datetime(2026, 9, 7, 13, tzinfo=timezone.utc))
        nested = run_sync(root, scheduled=True)
        assert nested == {"outcome": "busy", "reason": "a scheduled sync started at 2026-09-07T12:00:00+00:00 is still running"}
        assert service.worker_state(root)["last_scheduled_slot"] == worker["last_scheduled_slot"]
        return {"outcome": "completed"}

    assert service.run_scheduled(root, between_stages)["outcome"] == "completed"
    assert "scheduled_run" not in service.worker_state(root)
    assert run_sync(root, scheduled=True)["outcome"] == "no_change"
    assert service.worker_state(root)["last_scheduled_slot"] == "2026-09-07T13:00:00+00:00"


def test_two_scheduled_ticks_cannot_both_claim_the_same_slot(rem, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, local
    from connectonion.rem import service
    root, _ = rem
    set_config(root, ["schedule.timezone", "UTC", "schedule.times", "12:00"])
    write_json(state_path(root, "worker.json"), {"enabled": True})
    barrier, thread, due = Barrier(2), local(), service._scheduled_slot
    calls = []

    def simultaneous_tick(root):
        if not getattr(thread, "checked", False):
            thread.checked = True
            barrier.wait(timeout=5)
        return due(root)

    monkeypatch.setattr(service, "_scheduled_slot", simultaneous_tick)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ticks = [pool.submit(service.run_scheduled, root, lambda: calls.append("ran") or {"outcome": "no_change"})
                 for _ in range(2)]
        errors = [tick.exception(timeout=10) for tick in ticks]
        assert all(error is None or isinstance(error, RemError) and "busy" in str(error) for error in errors)
        results = [tick.result() for tick, error in zip(ticks, errors) if error is None]
    assert calls == ["ran"]
    assert sum(row is not None and row["outcome"] == "no_change" for row in results) == 1
    assert service.worker_state(root)["last_scheduled_slot"] == "2026-09-07T12:00:00+00:00"


def test_dead_scheduled_worker_claim_does_not_block_the_owed_slot(rem):
    from connectonion.rem import service
    root, _ = rem
    set_config(root, ["schedule.timezone", "UTC", "schedule.times", "12:00"])
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduled_run": {
        "phase": "daily-sync", "outcome": "running", "started_at": "2026-09-07T11:00:00+00:00",
        **service.running_marker(), "pid": 2 ** 22 + 7}})
    assert run_sync(root, scheduled=True)["outcome"] == "no_change"
    assert "scheduled_run" not in service.worker_state(root)


def test_lookback_defaults_to_two_months_and_is_capped_per_source_kind(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from connectonion.rem.service import subscriptions, toggle_source
    fixed = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    monkeypatch.setattr("connectonion.rem.service.now", lambda: fixed)
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: tmp_path / "sessions")
    root = tmp_path / "rem"
    prepare(root)
    since = datetime.fromisoformat(subscriptions(root)["codex"]["since"])
    assert since == fixed - timedelta(days=60)
    assert subscriptions(root)["gmail"]["max_lookback_days"] == 730
    assert subscriptions(root)["codex"]["max_lookback_days"] == 180
    toggle_source(root, "codex", True, project=str(tmp_path), since="180d")  # at the cap: fine
    with pytest.raises(RemError, match="180"):
        toggle_source(root, "codex", True, project=str(tmp_path / "other"), since="400d")


def test_sync_all_runs_batches_until_caught_up(rem):
    root, sessions = rem
    set_config(root, ["limits.items_per_batch", "2", "limits.extract_items_per_batch", "2"])
    rollout(sessions / "rollout-a.jsonl", [("user", f"fact {n}") for n in range(7)])
    calls, lines = [], []

    def runner(notebook, items, config, kind=""):
        calls.append(len(items))
        return {"usage": None, "changed": []}
    summary = run_sync(root, all_pending=True, runner=runner, on_batch=lambda n, record: lines.append(n))
    assert calls == [2, 2, 2, 1]
    assert summary["batches"] == 4 and summary["items"] == 7 and summary["outcome"] == "caught_up"
    assert lines == [1, 2, 3, 4]   # one progress report per batch, as each one finishes
    assert run_sync(root, all_pending=True, runner=runner)["batches"] == 0


def test_sync_all_stops_at_the_daily_cap_and_says_when_it_resets(rem):
    """On a real notebook `--all` ran 60 attempts against a cap of 30, silently,
    for 37 minutes (#1957). The backfill keeps the cap every other run keeps."""
    root, sessions = rem
    set_config(root, ["schedule.timezone", "Australia/Sydney", "limits.items_per_batch", "2",
                      "limits.extract_items_per_batch", "2", "limits.runner_calls_per_day", "2"])
    rollout(sessions / "rollout-a.jsonl", [("user", f"fact {n}") for n in range(7)])
    calls = []

    def runner(notebook, items, config, kind=""):
        calls.append(len(items))
        return {"usage": None, "changed": []}
    summary = run_sync(root, all_pending=True, runner=runner)
    assert calls == [2, 2]
    assert summary["outcome"] == "budget_exhausted" and summary["batches"] == 2 and summary["items"] == 4
    assert "2026-09-08T00:00+10:00" in summary["reason"]
    assert status(root)["runner_attempts_today"] == 2


def test_ctrl_c_during_sync_all_keeps_what_finished(rem):
    root, sessions = rem
    set_config(root, ["limits.items_per_batch", "2", "limits.extract_items_per_batch", "2"])
    rollout(sessions / "rollout-a.jsonl", [("user", f"fact {n}") for n in range(7)])
    finished = []

    def runner(notebook, items, config, kind=""):
        if finished:
            raise KeyboardInterrupt
        return {"usage": None, "changed": []}
    with pytest.raises(KeyboardInterrupt):
        run_sync(root, all_pending=True, runner=runner, on_batch=lambda n, record: finished.append(record))
    assert [record["outcome"] for record in finished] == ["completed"]


def test_dry_run_says_how_many_runner_attempts_are_left_and_when_they_reset(rem):
    """`status` said 30/30 while `sync --dry-run` said nothing of it (#1957)."""
    root, sessions = rem
    set_config(root, ["schedule.timezone", "Australia/Sydney", "limits.runner_calls_per_day", "1"])
    rollout(sessions / "rollout-a.jsonl", [("user", "first")])
    before = run_sync(root, dry_run=True)["daily_cap"]
    assert (before["used"], before["limit"], before["remaining"]) == (0, 1, 1)
    run_sync(root, runner=lambda *args, **kw: {"usage": None})
    spent = run_sync(root, dry_run=True)["daily_cap"]
    assert (spent["used"], spent["remaining"]) == (1, 0)
    assert spent["resets_at"] == "2026-09-08T00:00+10:00"   # 22:00 in Sydney: midnight there
    assert "limits.runner_calls_per_day" in spent["note"]


def test_a_run_refused_by_the_daily_cap_leaves_a_record(rem):
    """The refusal said "Next: logs", and logs had nothing to show (#1957)."""
    from connectonion.rem.service import run_logs
    root, sessions = rem
    set_config(root, ["schedule.timezone", "Australia/Sydney", "limits.runner_calls_per_day", "1"])
    rollout(sessions / "rollout-a.jsonl", [("user", "first")])
    run_sync(root, runner=lambda *args, **kw: {"usage": None})
    rollout(sessions / "rollout-a.jsonl", [("user", "first"), ("user", "second")])
    with pytest.raises(RemError, match="2026-09-08T00:00") as refusal:
        run_sync(root, runner=lambda *args, **kw: pytest.fail("invoked"))
    assert "`co rem config`" in str(refusal.value)
    # The clock is frozen, so both runs share a start time: find it by outcome.
    [refused] = [record for record in run_logs(root) if record["outcome"] == "refused"]
    assert refused["runner_attempts"] == 0
    assert "limits.runner_calls_per_day" in refused["reason"]
    assert status(root)["batches_today"] == 1   # a refusal is not a batch


def test_claude_code_is_a_real_default_source(tmp_path, monkeypatch):
    from connectonion.rem.service import subscriptions
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: tmp_path / "codex")
    monkeypatch.setattr("connectonion.rem.service.claude_projects_root", lambda: tmp_path / "claude")
    root = tmp_path / "rem"
    prepare(root)
    claude = subscriptions(root)["claude-code"]
    assert claude["adapter"] == "available" and claude["kind"] == "claude-code"
    assert claude["root"] == str(tmp_path / "claude")
    approve_sources(root)
    assert subscriptions(root)["claude-code"]["consented"] is True


def test_outlook_source_flows_through_sync_with_its_own_progress(tmp_path, monkeypatch):
    from connectonion.rem.service import subscriptions, toggle_source
    from tests.unit.test_rem_mail import FakeMail, mail
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: tmp_path / "codex")
    monkeypatch.setattr("connectonion.rem.service.claude_projects_root", lambda: tmp_path / "claude")
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: kind == "outlook")
    monkeypatch.setattr("connectonion.rem.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00", body="Alice: let's use Markdown for Aurora.")])
    monkeypatch.setattr("connectonion.rem.service.mail_client", lambda kind: client)
    root = tmp_path / "rem"
    prepare(root)
    assert subscriptions(root)["outlook"]["adapter"] == "available"
    assert subscriptions(root)["gmail"]["adapter"].startswith("waiting")
    toggle_source(root, "outlook", True)
    approve_sources(root)
    seen = []

    def runner(notebook, items, config, kind=""):
        seen.extend(items)
        return {"usage": None, "changed": []}
    assert run_sync(root, runner=runner)["outcome"] == "completed"
    assert [i["reference"] for i in seen] == ["outlook:m1"] and seen[0]["role"] == "other"
    assert seen[0]["correspondent"] == "alice@example.com"
    outlook = read_json(state_path(root, "progress.json"), {})["outlook"]
    assert outlook["scanned_until"] == "2026-09-02T09:00:00+00:00" and outlook["pending"] == {}
    assert run_sync(root, runner=runner)["outcome"] == "no_change"


def _extract_world(tmp_path, monkeypatch, n_messages):
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.rem.service.claude_projects_root", lambda: tmp_path / "no-claude")
    monkeypatch.setattr("connectonion.rem.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    prepare(root)
    approve_sources(root)
    rollout(sessions / "rollout-a.jsonl", [("user", f"fact {i}") for i in range(n_messages)])
    return root


def test_a_large_batch_is_extracted_first_and_the_maintainer_reads_only_the_digest(tmp_path, monkeypatch):
    root = _extract_world(tmp_path, monkeypatch, 40)
    seen_by_extractor, seen_by_runner = [], []

    def extractor(items, config, kind=""):
        seen_by_extractor.append(len(items))
        return {"notes": "## Decisions\n- fact 3 — user, codex:s:0", "usage": {"input_tokens": 100, "output_tokens": 10}}

    def runner(notebook, items, config, kind=""):
        seen_by_runner.extend(items)
        return {"usage": {"input_tokens": 20, "output_tokens": 5}, "changed": []}
    record = run_sync(root, runner=runner, extractor=extractor)
    assert record["outcome"] == "completed" and record["extracted"] is True
    assert seen_by_extractor == [40]  # the whole batch, well above items_per_batch=20
    assert len(seen_by_runner) == 1 and seen_by_runner[0]["role"] == "extract"
    assert "fact 3" in seen_by_runner[0]["text"] and seen_by_runner[0]["messages"] == 40
    assert record["runner_attempts"] == 2 and record["usage"]["input_tokens"] == 120
    assert run_sync(root, runner=runner, extractor=extractor)["outcome"] == "no_change"


def test_a_small_batch_goes_straight_to_the_maintainer(tmp_path, monkeypatch):
    root = _extract_world(tmp_path, monkeypatch, 3)
    runner_items = []
    record = run_sync(root, runner=lambda nb, items, cfg, kind="": runner_items.extend(items) or {"usage": None, "changed": []},
                      extractor=lambda items, cfg, kind="": pytest.fail("extraction called for a small batch"))
    assert record["extracted"] is False and len(runner_items) == 3


def test_nothing_worth_keeping_skips_the_maintainer(tmp_path, monkeypatch):
    root = _extract_world(tmp_path, monkeypatch, 30)
    record = run_sync(root, runner=lambda *a, **kw: pytest.fail("maintainer called with an empty digest"),
                      extractor=lambda items, cfg, kind="": {"notes": "Nothing worth keeping.", "usage": None})
    assert record["outcome"] == "completed" and record["items"] == 30 and record["changed"] == []
    assert read_json(state_path(root, "progress.json"), {})  # the batch is consumed all the same


def test_older_config_without_extraction_limits_still_loads(tmp_path):
    import yaml

    from connectonion.rem.config import read_config
    prepare(tmp_path)
    config = yaml.safe_load((tmp_path / "config.yaml").read_text())
    for key in ("extract_items_per_batch", "extract_chars_per_batch"):
        config["limits"].pop(key)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config))
    assert read_config(tmp_path)["limits"]["extract_items_per_batch"] == 40


def test_run_record_breaks_usage_down_by_stage_source_and_size(tmp_path, monkeypatch):
    """Where did the tokens go? A run must say per stage (extract / maintain), per source
    (how many items each contributed), and how many input characters it carried, so the
    cost of a source or a stage can be computed later from the raw records."""
    root = _extract_world(tmp_path, monkeypatch, 40)
    record = run_sync(root, runner=lambda nb, items, cfg, kind="": {"usage": {"input_tokens": 20, "output_tokens": 5}, "changed": []},
                      extractor=lambda items, cfg, kind="": {"notes": "## Decisions\n- fact 1 — user, codex:s:0",
                                                    "usage": {"input_tokens": 100, "output_tokens": 10}})
    assert record["usage_by_stage"] == {"extract": {"input_tokens": 100, "output_tokens": 10},
                                        "maintain": {"input_tokens": 20, "output_tokens": 5}}
    assert record["items_by_source"] == {"codex": 40}
    assert record["chars_in"] > 40 * 6 and record["seconds"] >= 0


def test_a_sync_record_carries_each_stage_s_instruction_size(tmp_path, monkeypatch):
    """#1959: only investigate recorded it, so logs --usage could not check the 15k
    ceiling for extract or maintain."""
    root = _extract_world(tmp_path, monkeypatch, 40)
    record = run_sync(root, runner=lambda nb, items, cfg, kind="": {"usage": {"input_tokens": 20}, "changed": [],
                                                                    "instructions_chars": 14_300},
                      extractor=lambda items, cfg, kind="": {"notes": "## Decisions\n- fact 1 — user, codex:s:0",
                                                             "usage": {"input_tokens": 100},
                                                             "instructions_chars": 9_500})
    assert record["instructions_chars"] == {"extract": 9_500, "maintain": 14_300}


def test_failed_maintain_keeps_extraction_usage_and_does_not_advance(tmp_path, monkeypatch):
    from connectonion.rem.runner import RunFailed
    root = _extract_world(tmp_path, monkeypatch, 40)

    def fail(*args, **kwargs):
        raise RunFailed("co ai unavailable", {"input_tokens": 3})

    record = run_sync(root, runner=fail, extractor=lambda *a, **kw: {
        "notes": "A durable fact", "usage": {"input_tokens": 100}})
    assert record["outcome"] == "failed" and record["usage"] == {"input_tokens": 103}
    assert record["usage_by_stage"] == {"extract": {"input_tokens": 100}, "maintain": {"input_tokens": 3}}
    assert not state_path(root, "progress.json").exists()


def test_two_stage_batch_cannot_spend_one_remaining_attempt(tmp_path, monkeypatch):
    from connectonion.rem.config import set_config
    root = _extract_world(tmp_path, monkeypatch, 40)
    set_config(root, ["limits.runner_calls_per_day", "1"])
    with pytest.raises(RemError, match="Daily"):
        run_sync(root, runner=lambda *a, **kw: pytest.fail("must not run"),
                 extractor=lambda *a, **kw: pytest.fail("must not run"))
    assert not state_path(root, "progress.json").exists()


def test_usage_report_aggregates_raw_records_by_stage_source_and_model(tmp_path):
    from connectonion.rem.service import usage_report
    prepare(tmp_path)
    runs = state_path(tmp_path, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    write_json(runs / "run_a.json", {"id": "run_a", "started_at": "2026-09-08T01:00:00+00:00", "outcome": "completed",
                                     "model": "gpt-5.6-luna", "items": 60, "chars_in": 120000, "seconds": 130.0,
                                     "usage": {"input_tokens": 250000, "output_tokens": 6000},
                                     "usage_by_stage": {"extract": {"input_tokens": 200000, "output_tokens": 4000},
                                                        "maintain": {"input_tokens": 50000, "output_tokens": 2000}},
                                     "items_by_source": {"outlook": 60}})
    write_json(runs / "run_b.json", {"id": "run_b", "started_at": "2026-09-08T02:00:00+00:00", "outcome": "completed",
                                     "model": "gpt-5.3-codex-spark", "items": 150, "chars_in": 500000, "seconds": 90.0,
                                     "usage": {"input_tokens": 900000, "output_tokens": 30000},
                                     "usage_by_stage": {"extract": {"input_tokens": 850000, "output_tokens": 25000},
                                                        "maintain": {"input_tokens": 50000, "output_tokens": 5000}},
                                     "items_by_source": {"codex": 100, "claude-code": 50}})
    report = usage_report(tmp_path)
    assert report["total"]["input_tokens"] == 1_150_000 and report["runs"] == 2
    assert report["by_stage"]["extract"]["input_tokens"] == 1_050_000
    assert report["by_model"]["gpt-5.3-codex-spark"]["input_tokens"] == 900_000
    # A run's tokens are attributed to its sources in proportion to the items each contributed.
    assert report["by_source"]["codex"]["input_tokens"] == 600_000
    assert report["by_source"]["claude-code"]["input_tokens"] == 300_000
    assert report["by_source"]["outlook"]["items"] == 60
    assert round(report["by_source"]["outlook"]["input_tokens_per_item"]) == round(250000 / 60)
    assert report["by_model"]["gpt-5.6-luna"]["input_tokens_per_1k_chars"] == round(250000 / 120, 1)


def test_usage_report_says_how_many_pages_the_tokens_changed(tmp_path):
    """What a run is worth is the pages it changed; 330k tokens for one page is the
    number #1846 was about, and it had to be worked out by hand."""
    from connectonion.rem.service import usage_report
    prepare(tmp_path)
    runs = state_path(tmp_path, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    for name, tokens, changed in (("a", 330_000, ["projects/kite.md"]), ("b", 70_000, ["people/a.md", "people/b.md"])):
        write_json(runs / f"run_{name}.json", {"id": f"run_{name}", "started_at": "2026-09-08T01:00:00+00:00",
                                               "usage": {"input_tokens": tokens}, "changed": changed})
    report = usage_report(tmp_path)
    assert report["pages_changed"] == 3 and report["pages_changed_per_100k_input_tokens"] == 0.75


def test_usage_report_names_each_stage_s_instruction_size_against_the_15k_target(tmp_path):
    """#1851: the composed Skill text is re-sent on every tool round, so its
    size per stage is reported where a regression would show."""
    from connectonion.rem.service import usage_report
    prepare(tmp_path)
    runs = state_path(tmp_path, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    base = {"outcome": "completed", "model": "m", "usage": {"input_tokens": 10}}
    write_json(runs / "run_a.json", {**base, "id": "run_a", "started_at": "2026-09-30T01:00:00+00:00",
                                     "instructions_chars": {"investigate": 14_000}})
    write_json(runs / "run_b.json", {**base, "id": "run_b", "started_at": "2026-09-30T02:00:00+00:00",
                                     "instructions_chars": {"investigate": 16_000, "maintain": 9_000}})
    write_json(runs / "run_c.json", {**base, "id": "run_c", "started_at": "2026-09-30T03:00:00+00:00"})

    stages = usage_report(tmp_path)["by_stage"]

    assert stages["investigate"]["instructions_chars_mean"] == 15_000
    assert stages["investigate"]["instructions_chars_max"] == 16_000
    assert stages["investigate"]["over_instructions_target"] is True
    assert stages["maintain"]["over_instructions_target"] is False


def test_a_format_that_moved_is_reported_instead_of_looking_like_a_quiet_week(rem):
    """Reading only the shape the user types fails closed, and closed is silent: the
    notebook would keep saying "nothing new" while the person talked all week. A pass
    that passes over a pile of unfamiliar user-slot messages says which source and how
    many, and the next command is the one that shows it."""
    root, sessions = rem
    path = sessions / "rollout-a.jsonl"
    rows = [json.dumps({"type": "session_meta", "payload": {"id": "s1", "cwd": "/work", "originator": "codex_cli_rs"}})]
    rows += [json.dumps({"timestamp": "2026-09-07T05:00:00Z", "type": "response_item",
                         "payload": {"type": "message", "role": "user", "id": f"m{i}",
                                     "shape_we_have_never_seen": True,
                                     "content": [{"type": "input_text", "text": "Ship it on Friday."}]}})
             for i in range(25)]
    path.write_text("\n".join(rows) + "\n")
    record = run_sync(root, runner=lambda *args, **kw: pytest.fail("nothing was read, so nothing to maintain"))
    assert record["outcome"] == "no_change"
    assert record["unrecognised"] == {"codex": 25}
    assert "codex" in record["warning"] and "25" in record["warning"]


def test_a_window_is_coverage_not_a_replacement(rem):
    """"At least three days of Claude Code" is what a person asks for, and it is not the
    same as "only three days". `--since` guarantees the window reaches back that far:
    it widens when it must and leaves a wider one alone. Narrowing is the destructive
    direction -- everything between the old edge and the new one is dropped unread and
    no cursor brings it back -- so that one asks first."""
    from connectonion.rem.service import set_window, subscriptions
    root, _ = rem
    default = subscriptions(root)["claude-code"]["since"]           # 60 days by default
    assert set_window(root, "claude-code", "3d")["changed"] is False  # already covered
    assert subscriptions(root)["claude-code"]["since"] == default

    widened = set_window(root, "outlook", "6m")
    assert widened["changed"] is True and widened["since"].startswith("2026-03-1")

    with pytest.raises(RemError, match="180 days"):
        set_window(root, "codex", "2y")     # coding sessions are capped
    with pytest.raises(RemError, match="7d"):
        set_window(root, "codex", "last tuesday")


def test_narrowing_a_window_needs_saying_so_twice(rem):
    from connectonion.rem.service import set_window
    root, _ = rem
    with pytest.raises(RemError, match="--force"):
        set_window(root, "codex", "3d", narrow=True)
    assert set_window(root, "codex", "3d", narrow=True, force=True)["since"].startswith("2026-09-04")


def test_a_scope_is_a_subscription_of_its_own_with_its_own_cursor(rem):
    """"Six months of the browser work" is a standing scope, not a one-off filter: it
    needs its own cursor, or it would either consume the main source's material or be
    re-read on every pass. Directory scopes already worked this way — for codex only,
    which is the source where directory means least."""
    from connectonion.rem.service import subscriptions, toggle_source
    root, sessions = rem
    rollout(sessions / "rollout-a.jsonl", [("user", "fix the browser build")])
    rollout(sessions / "rollout-b.jsonl", [("user", "write the Xiaohongshu post")])

    name = toggle_source(root, "codex", True, about="browser", since="6m")
    approve_sources(root)          # a new scope is a new consent, like any other source
    scope = subscriptions(root)[name]
    assert name == "codex-about-browser" and scope["about"] == "browser"
    assert scope["since"].startswith("2026-03-1")          # six months, within the 180-day cap
    assert subscriptions(root)["codex"]["since"] != scope["since"]   # the main source is untouched

    seen = []
    run_sync(root, source=name, runner=lambda notebook, items, config, kind="": seen.append(items) or {"usage": None})
    assert [i["text"] for i in seen[0]] == ["fix the browser build"]

    # the main source still has both sessions waiting: the scope consumed neither
    rest = []
    run_sync(root, source="codex", runner=lambda notebook, items, config, kind="": rest.append(items) or {"usage": None})
    assert sorted(i["text"] for i in rest[0]) == ["fix the browser build", "write the Xiaohongshu post"]


def test_a_directory_scope_works_for_both_coding_sources(rem):
    """It was refused for claude-code for no reason the code could state; collect has
    filtered claude-code transcripts by directory since they were added."""
    from connectonion.rem.service import subscriptions, toggle_source
    root, _ = rem
    name = toggle_source(root, "claude-code", True, project="/work/demo", since="30d")
    assert subscriptions(root)[name]["project"] == "/work/demo"
    assert subscriptions(root)[name]["kind"] == "claude-code"


def test_a_batch_is_drawn_from_one_source_and_names_it_to_the_extractor(tmp_path, monkeypatch):
    """Extraction reads a source's own Skill, so a batch cannot mix two sources.

    Mail and coding sessions hide the user's words in different places and lie
    differently about which messages are the user's. A batch holding both would
    have to be read through both Skills, or through neither.
    """
    root = _extract_world(tmp_path, monkeypatch, 25)
    seen = {}

    def extractor(items, config, kind=""):
        seen["kind"] = kind
        seen["prefixes"] = {item["source"].split(":")[0] for item in items}
        return {"notes": "## Decisions\n- one — user, codex:s:0", "usage": None}

    record = run_sync(root, runner=lambda nb, i, c, kind="": {"usage": None, "changed": []},
                      extractor=extractor)
    assert record["outcome"] == "completed"
    assert seen["prefixes"] == {"codex"}
    assert seen["kind"] == "codex"          # named, so the codex Skill is the one loaded
    assert list(record["items_by_source"]) == ["codex"]


def test_whatsapp_is_a_source_chat_by_chat_and_a_new_chat_asks_again(tmp_path, monkeypatch):
    """Subscribing a chat widens what is read, so it is consent the user has not
    given yet: the next `start` shows the summary again instead of reading on the
    strength of the first one. Before this, a repeated start never asked, and a
    source added after the first start could never be read at all."""
    from connectonion.rem.service import start, subscriptions, toggle_source
    inbox = tmp_path / "inbox" / "whatsapp"
    inbox.mkdir(parents=True)
    (inbox / "received.jsonl").write_text(json.dumps({
        "id": "m1", "chat": "120363411567190840@g.us", "sender": "61400000001@s.whatsapp.net",
        "sender_name": "John", "text": "the listing goes live on Friday", "kind": "text",
        "at": "2026-09-06T01:00:00Z"}) + "\n")
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: tmp_path / "none")
    monkeypatch.setattr("connectonion.rem.service.claude_projects_root", lambda: tmp_path / "none")
    monkeypatch.setattr("connectonion.rem.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    root = tmp_path / "rem"
    asked, seen = [], []
    def runner(notebook, items, config, *a, **k):
        seen.extend(items)
        return {"usage": None, "changed": []}
    scheduler = FakeScheduler()
    start(root, confirm=lambda summary: asked.append(summary) or True, scheduler=scheduler, runner=runner)
    assert subscriptions(root)["whatsapp"]["adapter"] == "available"
    assert not subscriptions(root)["whatsapp"]["enabled"]           # off until a chat is named

    toggle_source(root, "whatsapp", True, chats=["120363411567190840@g.us"])
    assert subscriptions(root)["whatsapp"]["consented"] is False
    start(root, confirm=lambda summary: asked.append(summary) or True, scheduler=scheduler, runner=runner)
    assert len(asked) == 2
    assert "120363411567190840@g.us" in json.dumps(asked[1]["sources"]["whatsapp"])
    assert subscriptions(root)["whatsapp"]["consented"] is True

    record = run_sync(root, source="whatsapp", runner=runner)
    assert record["outcome"] == "completed"
    assert [i["text"] for i in seen] == ["the listing goes live on Friday"]

    toggle_source(root, "whatsapp", False, chats=["120363411567190840@g.us"])
    assert subscriptions(root)["whatsapp"]["chats"] == []


@pytest.mark.parametrize("runner, flag", [("codex", "--sandbox danger-full-access"),
                                          ("claude-code", "--permission-mode bypassPermissions")])
def test_the_consent_summary_says_which_tools_unattended_investigations_can_use(tmp_path, runner, flag):
    """Approving `co rem start` is agreeing to runs nobody watches; the user
    should see what those runs may do before saying yes, and how to undo it."""
    from connectonion.rem.service import consent_summary
    prepare(tmp_path)
    set_config(tmp_path, ["runner", runner])
    summary = consent_summary(tmp_path)
    assert flag in summary["model_permissions"] and "local repository" in summary["model_permissions"]
    assert "co rem stop" in summary["background"]
    from connectonion.cli.commands.rem_output import render
    text = render(summary, "start — source access and schedule")
    assert flag in next(line for line in text.splitlines() if line.startswith("Permissions:"))
    assert "co rem stop" in next(line for line in text.splitlines() if line.startswith("Background:"))
    assert len(text.splitlines()) <= 25
    assert "Input chars per batch" not in text and "/inbox/whatsapp" not in text


def test_a_batch_that_wrote_its_pages_before_failing_is_not_run_and_paid_for_again(rem):
    """The maintainer wrote the page, then something after it failed. The run was
    recorded failed and the cursor held back, so every scheduled run fed the same
    material to the maintainer again and paid for it again."""
    root, sessions = rem
    rollout(sessions / "rollout-a.jsonl", [("user", "We choose SQL")])
    calls = []

    def writes_then_fails(notebook, items, config, kind=""):
        calls.append(items)
        notebook.write("decisions/storage.md", "# Storage\nWe choose SQL")
        raise OSError("disk hiccup after the page was written")

    first = run_sync(root, runner=writes_then_fails)
    assert first["outcome"] == "failed" and first["changed"] == ["decisions/storage.md"]
    assert first["progress_advanced"] is True
    assert run_sync(root, runner=writes_then_fails)["outcome"] == "no_change"
    assert len(calls) == 1


def test_a_failure_that_wrote_nothing_still_retries_the_same_material(rem):
    root, sessions = rem
    rollout(sessions / "rollout-a.jsonl", [("user", "We choose SQL")])

    def fails(*args, **kwargs):
        raise OSError("no pages written")

    record = run_sync(root, runner=fails)
    assert record["outcome"] == "failed" and record["progress_advanced"] is False
    assert read_json(state_path(root, "progress.json"), {}) == {}


def test_a_finished_extraction_is_reused_when_only_the_maintainer_failed(tmp_path, monkeypatch):
    """Extraction is the expensive pass. When it finished and the maintainer failed
    without writing, the retry read the same 40 messages through extraction again."""
    from connectonion.rem.runner import RunFailed
    root = _extract_world(tmp_path, monkeypatch, 40)
    extractions, maintained = [], []

    def extractor(items, config, kind=""):
        extractions.append(len(items))
        return {"notes": "## Decisions\n- fact 3 — user, codex:s:0", "usage": {"input_tokens": 100}}

    def fail(*args, **kwargs):
        raise RunFailed("co ai unavailable", {"input_tokens": 3})

    assert run_sync(root, runner=fail, extractor=extractor)["outcome"] == "failed"
    retry = run_sync(root, runner=lambda nb, items, cfg, kind="": maintained.extend(items) or {"usage": None, "changed": []},
                     extractor=extractor)
    assert retry["outcome"] == "completed" and extractions == [40]
    assert retry["runner_attempts"] == 1 and "fact 3" in maintained[0]["text"]
    assert run_sync(root, runner=fail, extractor=extractor)["outcome"] == "no_change"


@pytest.mark.parametrize("change", [
    ["runner", "coai"],   # never picked by a new notebook, whatever this machine has installed
    ["model", "gpt-other"],
    ["schedule.times", "03:00"],
])
def test_start_asks_again_when_what_the_summary_shows_has_changed(tmp_path, monkeypatch, change):
    """A re-tester approved Codex, stopped, switched the runner to Claude Code
    and answered `n` to start: it printed Started: Yes and reinstalled the job
    without showing the summary. Consent covers what was shown; if any of it
    changed -- runner, model, permissions, schedule, sources -- ask again."""
    from connectonion.rem.service import start, stop
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.rem.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    calls, scheduler = [], FakeScheduler()
    start(root, confirm=lambda s: True, scheduler=scheduler, runner=_runner_recording(calls))
    stop(root, scheduler=scheduler)
    set_config(root, change)
    shown = []
    declined = start(root, confirm=lambda s: shown.append(s) or False,
                     scheduler=scheduler, runner=_runner_recording(calls))
    assert declined["started"] is False and len(shown) == 1
    assert scheduler.installed == [root.resolve()]  # only the first start installed
    # Once agreed, the same summary is not asked about again.
    start(root, confirm=lambda s: True, scheduler=scheduler, runner=_runner_recording(calls))
    again = start(root, confirm=lambda s: pytest.fail("asked about an unchanged summary"),
                  scheduler=scheduler, runner=_runner_recording(calls))
    assert again["started"] is True


@pytest.mark.parametrize("runner, login", [("codex", "Codex"), ("claude-code", "Claude Code")])
def test_the_consent_summary_names_the_login_the_runner_actually_uses(tmp_path, runner, login):
    from connectonion.rem.service import consent_summary
    prepare(tmp_path)
    set_config(tmp_path, ["runner", runner])
    summary = consent_summary(tmp_path)
    receives = summary["model_receives"]
    assert f"your own {login} login" in receives
    other = "Claude Code" if login == "Codex" else "Codex"
    assert other not in receives
    from connectonion.cli.commands.rem_output import render
    model = next(line for line in render(summary, "start — source access and schedule").splitlines()
                 if line.startswith("Model:"))
    assert model == f"Model: {runner} · {summary['model']} · through your own {login} login (no API key)"


def test_a_spent_day_serves_the_slot_instead_of_retrying_it_every_tick(tmp_path, monkeypatch):
    """On a real notebook the day's calls ran out by 03:00, and every five-minute
    tick from then to midnight retried the owed slot and logged the same error."""
    from datetime import datetime, timezone

    from connectonion.rem.service import start
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    clock = {"now": datetime(2026, 9, 7, 6, 30, tzinfo=timezone.utc)}
    monkeypatch.setattr("connectonion.rem.service.now", lambda: clock["now"])
    set_config(root, ["schedule.timezone", "Australia/Sydney", "schedule.times", "17:00",
                      "limits.runner_calls_per_day", "1"])
    calls = []
    start(root, confirm=lambda s: True, scheduler=FakeScheduler(), runner=_runner_recording(calls))
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    assert run_sync(root, runner=_runner_recording(calls))["outcome"] == "completed"   # the day's one call
    rollout(sessions / "rollout-a.jsonl", [("user", "hello"), ("user", "again")])
    clock["now"] = datetime(2026, 9, 7, 7, 2, tzinfo=timezone.utc)      # 17:02 Sydney: due, but the day is spent
    first = run_sync(root, scheduled=True, runner=_runner_recording(calls))
    assert first["outcome"] == "budget_exhausted"
    assert run_sync(root, scheduled=True, runner=_runner_recording(calls)) is None   # served, not retried


def test_maintenance_works_one_page_per_turn_and_a_failure_costs_only_that_page(tmp_path, monkeypatch):
    """One turn over the whole notebook edited eight pages, took twenty minutes and
    timed out with nothing saved, twice on the same real batch (2026-09-27)."""
    from connectonion.rem.runner import RunFailed
    from connectonion.rem.service import _maintain_pages
    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    for name in ("a", "b", "c"):
        notebook.stub_person(f"people/{name}.md", name.upper(), [])
    seen = []

    def one_turn(book, items, config, kind="", stage="maintain", maintenance_lock_held=False):
        page = next(item for item in items if item.get("role") == "page")
        assert page["one_page"] and maintenance_lock_held and stage == "maintain"
        seen.append(page["record"])
        if page["record"] == "people/b.md":
            raise RunFailed("Candidate rejected: Citation has no identifiable source: 1", {"input_tokens": 5})
        return {"changed": [page["record"]], "usage": {"input_tokens": 10}, "review_candidates": [],
                "instructions_chars": {"people/a.md": 14_100, "people/c.md": 14_600}[page["record"]],
                "page_chars": {"people/a.md": [2_000, 2_400], "people/c.md": [3_000, 3_000]}[page["record"]]}

    monkeypatch.setattr("connectonion.rem.runner.run_stage", one_turn)
    material = [{"role": "extract", "text": "notes", "source": "codex:x +1", "timestamp": "2026-09-27"}]
    result = _maintain_pages(root, material, {}, "codex", ["people/a.md", "people/b.md", "people/c.md"])
    assert seen == ["people/a.md", "people/b.md", "people/c.md"]
    assert result["changed"] == ["people/a.md", "people/c.md"]
    assert result["refusals"] == [{"record": "people/b.md",
                                   "errors": ["Candidate rejected: Citation has no identifiable source: 1"]}]
    assert result["usage"] == {"input_tokens": 25}
    # #1959: the largest one-page turn, so logs --usage can check the 15k ceiling for maintain too.
    assert result["instructions_chars"] == 14_600
    # #1956: each page's size before and after, so a run that doubles a page shows it.
    assert result["page_chars"] == {"people/a.md": [2_000, 2_400], "people/c.md": [3_000, 3_000]}


# ------------------------------------------- #1974: the daily round reads mail


def test_status_says_a_connected_mailbox_the_round_does_not_read_and_the_fix(tmp_path, monkeypatch):
    """Notebooks made before #1946 had Gmail connected, Enabled: No, while doctor said "connected"."""
    prepare(tmp_path)
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: kind == "gmail")
    lines = status(tmp_path)["mailboxes"]
    assert "not read by the daily round" in lines["gmail"] and "co rem sources add gmail" in lines["gmail"]
    assert "not connected" in lines["outlook"] and "co auth microsoft" in lines["outlook"]


def test_start_offers_connected_mailboxes_and_only_an_approval_subscribes_them(tmp_path, monkeypatch):
    from connectonion.rem.service import start, subscriptions
    root, sessions = tmp_path / "rem", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: kind == "gmail")
    monkeypatch.setattr("connectonion.rem.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    shown = []
    declined = start(root, confirm=lambda summary: shown.append(summary) or False, scheduler=FakeScheduler(),
                     runner=_runner_recording([]))
    assert declined["started"] is False
    assert "read from now on if you approve" in shown[0]["sources"]["gmail"]["state"]
    assert subscriptions(root)["gmail"]["enabled"] is False

    monkeypatch.setattr("connectonion.rem.service.run_sync", lambda root, runner=None: {"outcome": "completed"})
    start(root, confirm=lambda summary: True, scheduler=FakeScheduler(), runner=_runner_recording([]))
    gmail = subscriptions(root)["gmail"]
    assert gmail["enabled"] is True and gmail["consented"] is True
    assert "read by the daily round" in status(root)["mailboxes"]["gmail"]


def test_a_mailbox_the_owner_removed_is_not_offered_again(tmp_path, monkeypatch):
    from connectonion.rem.service import consent_summary, toggle_source
    prepare(tmp_path)
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: kind == "gmail")
    toggle_source(tmp_path, "gmail", False)
    assert consent_summary(tmp_path)["sources"]["gmail"]["state"] == "unsubscribed"


def test_a_mailbox_never_connected_is_told_how_to_connect_not_called_unsubscribed(tmp_path, monkeypatch):
    """The consent prompt said "unsubscribed" for a mailbox the owner had simply not
    connected yet; nothing on that screen said `co auth google` was the step."""
    from connectonion.rem.service import consent_summary
    prepare(tmp_path)
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    assert consent_summary(tmp_path)["sources"]["gmail"]["state"] == "waiting for co auth google"
    assert consent_summary(tmp_path)["sources"]["outlook"]["state"] == "waiting for co auth microsoft"


def test_stale_running_records_are_marked_abandoned_by_the_next_writer(tmp_path, monkeypatch):
    """Two records said "running" for days on the owner's notebook."""
    import os
    from connectonion.rem.service import abandon_stale_runs, run_logs
    monkeypatch.setattr("connectonion.rem.service._boot_time", lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    prepare(tmp_path)
    runs = state_path(tmp_path, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    from connectonion.rem.service import now
    old = (now() - timedelta(days=3)).isoformat()
    fresh = now().isoformat()
    write_json(runs / f"run_{'a' * 32}.json", {"id": f"run_{'a' * 32}", "started_at": old, "outcome": "running",
                                              "runner_attempts": 1})
    write_json(runs / f"run_{'b' * 32}.json", {"id": f"run_{'b' * 32}", "started_at": fresh, "outcome": "running",
                                              "pid": 2 ** 22 + 7, "host": __import__("socket").gethostname()})
    write_json(runs / f"run_{'c' * 32}.json", {"id": f"run_{'c' * 32}", "started_at": fresh, "outcome": "running",
                                              "pid": os.getpid(), "host": __import__("socket").gethostname()})
    assert sorted(abandon_stale_runs(tmp_path)) == [f"run_{'a' * 32}", f"run_{'b' * 32}"]
    outcomes = {record["id"][4]: record for record in run_logs(tmp_path)}
    assert outcomes["a"]["outcome"] == "abandoned" and "timeout" in outcomes["a"]["reason"]
    assert outcomes["b"]["outcome"] == "abandoned" and "no longer running" in outcomes["b"]["reason"]
    assert outcomes["c"]["outcome"] == "running"


def test_usage_by_model_says_unrecorded_and_skips_per_1k_without_sizes(tmp_path):
    """logs --usage showed a model "?" and an absurd per-1k figure (tokens over 0 characters)."""
    from connectonion.rem.service import usage_report
    prepare(tmp_path)
    runs = state_path(tmp_path, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    write_json(runs / "run_a.json", {"id": "run_a", "started_at": "2026-09-08T01:00:00+00:00",
                                     "outcome": "completed", "usage": {"input_tokens": 900000}})
    write_json(runs / "run_b.json", {"id": "run_b", "started_at": "2026-09-08T02:00:00+00:00", "model": "m",
                                     "outcome": "completed", "usage": {"input_tokens": 1000}, "chars_in": 4000,
                                     "items_by_source": {"gmail": 1}})
    write_json(runs / "run_c.json", {"id": "run_c", "started_at": "2026-09-08T03:00:00+00:00", "model": "m",
                                     "outcome": "completed", "usage": {"input_tokens": 500000}})
    report = usage_report(tmp_path)
    assert "?" not in report["by_model"] and "unrecorded" in report["by_model"]
    assert "input_tokens_per_1k_chars" not in report["by_model"]["unrecorded"]
    assert report["by_model"]["m"]["input_tokens_per_1k_chars"] == 250.0


@pytest.mark.parametrize("approved", [False, True])
def test_stalled_archive_opens_only_approved_mailboxes(rem, monkeypatch, approved):
    from connectonion.rem import service
    root, _ = rem
    sources = {"gmail": {"enabled": True, "consented": True},
               "outlook": {"enabled": approved, "consented": approved}}
    monkeypatch.setattr(service, "subscriptions", lambda root: sources)
    monkeypatch.setattr(service, "archive_state", lambda *a, **kw: {"stalled": True})
    monkeypatch.setattr(service, "mail_available", lambda kind: True)
    monkeypatch.setattr(service, "mail_client", lambda kind: kind)
    monkeypatch.setattr(service, "resume_stalled", lambda root, clients, **kw: clients)
    assert set(service._resume_archive(root)) == ({"gmail", "outlook"} if approved else {"gmail"})


def test_a_sync_resumes_a_stalled_init_archive_and_status_stops_mentioning_it(rem, monkeypatch):
    """#2035: only `init` resumed the archive; a day of investigations asked the servers instead."""
    from connectonion.rem.mail_archive import archive_init
    from connectonion.rem.source import Batch
    from tests.unit.test_rem_mail_archive import T0, Bodies, Clock, _inventory
    root, _ = rem
    toggle_source(root, "gmail", True)
    approve_sources(root)
    archive_init(root, _inventory(root), {"gmail": Bodies()}, seconds=25, clock=Clock(), now=lambda: T0)
    mail = Bodies()
    monkeypatch.setattr("connectonion.rem.service.now", lambda: T0 + timedelta(hours=20))
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: kind == "gmail")
    monkeypatch.setattr("connectonion.rem.service.mail_client", lambda kind, **kw: mail)
    monkeypatch.setattr("connectonion.rem.service.collect_mail", lambda *a, **kw: Batch([], {}))
    assert status(root)["mail_archive"]["stalled"]                      # said before anything resumes it
    record = run_sync(root, runner=lambda *a, **kw: {"usage": {}})
    assert record["mail_archive"]["phase"] == "complete" and record["mail_archive"]["reused"] == 2
    assert mail.calls == ["m2", "m3", "m4", "m5"]
    assert "mail_archive" not in status(root)
    assert "mail_archive" not in run_sync(root, runner=lambda *a, **kw: {"usage": {}})


# ------------------------------------------- the 1.9.0a7 acceptance run (#2043)


def test_every_kind_of_run_has_a_stage_and_the_stages_add_up_to_the_total(tmp_path):
    """#2043: logs --usage said 5.23M tokens in total and listed only extract and
    maintain; 2.35M of investigation and project-page tokens had no stage."""
    from connectonion.rem.service import usage_report
    prepare(tmp_path)
    runs = state_path(tmp_path, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    kinds = [  # (phase, usage, usage_by_stage as each kind records it)
        (None, 100, {"extract": {"input_tokens": 60}, "maintain": {"input_tokens": 40}}),   # a sync batch
        ("investigate", 200, {"extract": {"input_tokens": 50}, "investigate": {"input_tokens": 150}}),
        ("investigate me", 300, None),                       # recorded before it split by stage
        ("projects write", 400, None),
        ("daily-investigation", 500, {"investigate": {"input_tokens": 500}}),
        ("daily-update", 600, {"investigate": {"input_tokens": 250}, "projects": {"input_tokens": 350}}),
        ("daily-update", 700, None),                         # an older daily record: no split
    ]
    for number, (phase, tokens, stages) in enumerate(kinds):
        write_json(runs / f"run_{number}.json", {
            "id": f"run_{number}", "started_at": f"2026-09-30T0{number}:00:00+00:00", "outcome": "completed",
            "model": "m", **({"phase": phase} if phase else {"items_by_source": {"gmail": 3}}),
            "usage": {"input_tokens": tokens}, **({"usage_by_stage": stages} if stages else {})})

    report = usage_report(tmp_path)

    stages = {stage: table.get("input_tokens", 0) for stage, table in report["by_stage"].items()}
    assert stages == {"extract": 110, "maintain": 40, "investigate": 1900, "projects": 750}
    assert sum(stages.values()) == report["total"]["input_tokens"] == 2800
    # Only the sync batch read a source's items; an investigation is not split across sources.
    assert report["by_source"]["gmail"]["input_tokens"] == 100


def test_tokens_per_1k_characters_is_measured_on_sync_batches_only(tmp_path):
    """#2043: 28,556.9 tokens per 1k characters: an investigation's material goes into
    files the model searches, so its characters are not what it read."""
    from connectonion.rem.service import usage_report
    prepare(tmp_path)
    runs = state_path(tmp_path, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    write_json(runs / "run_a.json", {"id": "run_a", "started_at": "2026-09-30T01:00:00+00:00", "model": "m",
                                     "outcome": "completed", "usage": {"input_tokens": 2000}, "chars_in": 4000,
                                     "items_by_source": {"gmail": 2}})
    write_json(runs / "run_b.json", {"id": "run_b", "started_at": "2026-09-30T02:00:00+00:00", "model": "m",
                                     "phase": "investigate", "outcome": "completed",
                                     "usage": {"input_tokens": 900_000}, "chars_in": 30})
    assert usage_report(tmp_path)["by_model"]["m"]["input_tokens_per_1k_chars"] == 500.0


def test_a_job_launchd_never_started_is_not_reported_as_a_failed_investigation(tmp_path, monkeypatch):
    # A real Mac, 2026-10-07 to 10-11: the job was loaded, `runs = 0`, 18 slots
    # passed, and status said "the last scheduled investigation failed; run co rem logs".
    from connectonion.rem.schedule import Launchd
    monkeypatch.setattr("connectonion.rem.service.now", lambda: datetime(2026, 10, 11, 12, tzinfo=timezone.utc))
    root = tmp_path / "rem"
    prepare(root)
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "launchd",
                                                 "installed_at": "2026-10-07T09:28:00+00:00",
                                                 "last_scheduled_outcome": "failed"})
    monkeypatch.setattr(Launchd, "installed", lambda self, root: True)
    monkeypatch.setattr(Launchd, "describe", lambda self, root: {
        "loaded": True, "last_exit_code": "(never exited)", "runs": 0})
    monkeypatch.setattr("connectonion.rem.service.sys.platform", "darwin")
    state = status(root)["state"]
    assert "has not started it once since 2026-10-07" in state
    assert "Allow in the Background" in state and "co rem logs" not in state


def test_launchd_describe_reads_how_many_times_the_job_ran(tmp_path):
    from connectonion.rem.schedule import Launchd
    printed = "\tstate = not running\n\truns = 0\n\tlast exit code = (never exited)\n"
    launcher = Launchd(run=lambda *a, **k: type("R", (), {"returncode": 0, "stdout": printed})())
    assert launcher.describe(tmp_path / "rem")["runs"] == 0


def test_usage_report_survives_a_run_whose_instruction_size_is_one_number(tmp_path):
    """`co rem logs --usage` crashed on a real 1.9.2b1 notebook: 156 skill
    investigations recorded `instructions_chars` as the number the runner
    returned, not a {stage: number} table (2026-10-10)."""
    from connectonion.rem.service import usage_report
    prepare(tmp_path)
    runs = state_path(tmp_path, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    base = {"outcome": "completed", "model": "m", "usage": {"input_tokens": 10}}
    write_json(runs / "run_a.json", {**base, "id": "run_a", "started_at": "2026-10-10T01:00:00+00:00",
                                     "phase": "investigate", "record": "skills/catalog/x.md",
                                     "instructions_chars": 12_000})
    write_json(runs / "run_b.json", {**base, "id": "run_b", "started_at": "2026-10-10T02:00:00+00:00",
                                     "instructions_chars": {"investigate": 14_000}})

    stages = usage_report(tmp_path)["by_stage"]

    assert stages["investigate"]["instructions_chars_mean"] == 13_000


@pytest.mark.parametrize("count", [2, 5])
def test_sync_reports_mail_still_queued_after_bounded_batch(rem, monkeypatch, count):
    from connectonion.rem.source import Batch
    root, _ = rem
    set_config(root, ["limits.extract_items_per_batch", "2"])
    monkeypatch.setattr("connectonion.rem.service._selected_sources", lambda *a: {
        "gmail": {"kind": "gmail", "enabled": True, "consented": True}})
    monkeypatch.setattr("connectonion.rem.service.mail_client", lambda kind: object())
    items = [{"source": f"gmail:{n}", "role": "user", "text": "Fictional project note"} for n in range(2)]
    monkeypatch.setattr("connectonion.rem.service.collect_mail", lambda *a, **kw: Batch(
        items, {"pending": {"rowan@example.org": [{"id": str(n)} for n in range(count - 2)]}}))
    record = run_sync(root, runner=lambda *a, **kw: {"changed": [], "usage": None})
    assert record["items"] == 2
    assert record["material_remaining"] == {"gmail": count - 2}


def test_not_due_reason_skips_the_slot_already_served_early(rem):
    from connectonion.rem.service import scheduled_skip
    root, _ = rem
    set_config(root, ["schedule.timezone", "UTC", "schedule.times", "03:00,19:00"])
    write_json(state_path(root, "worker.json"), {
        "enabled": True, "last_scheduled_slot": "2026-09-07T19:00:00+00:00"})
    result = scheduled_skip(root)
    assert "19:00 slot was already served" in result["reason"]
    assert "next slot 2026-09-08T03:00+00:00" in result["reason"]


@pytest.mark.parametrize("boot_known", [True, False])
def test_live_run_does_not_expire_without_progress(tmp_path, monkeypatch, boot_known):
    from connectonion.rem import service

    prepare(tmp_path)
    moment = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "now", lambda: moment)
    boot = moment - timedelta(days=4) if boot_known else None
    monkeypatch.setattr(service, "_boot_time", lambda: boot)
    record = {"id": "run_live", "started_at": (moment - timedelta(days=3)).isoformat(),
              "outcome": "running", **service.running_marker()}
    path = state_path(tmp_path, "runs/run_live.json")
    write_json(path, record)

    assert service.abandon_stale_runs(tmp_path) == []
    assert read_json(path, {}) == record


@pytest.mark.parametrize("progress", [False, True])
def test_live_pid_from_before_boot_is_abandoned_even_with_recent_progress(tmp_path, monkeypatch, progress):
    from connectonion.rem import service

    prepare(tmp_path)
    moment = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "now", lambda: moment)
    monkeypatch.setattr(service, "_boot_time", lambda: moment - timedelta(minutes=10))
    record = {"id": "run_reused", "started_at": (moment - timedelta(minutes=30)).isoformat(),
              "outcome": "running", **service.running_marker()}
    if progress:
        record["stage_updated_at"] = moment.isoformat()
    path = state_path(tmp_path, "runs/run_reused.json")
    write_json(path, record)

    assert service.abandon_stale_runs(tmp_path) == ["run_reused"]
    assert read_json(path, {})["outcome"] == "abandoned"
    assert "restart" in read_json(path, {})["reason"]


@pytest.mark.parametrize("minute", [49, 50, 59])
def test_next_slot_keeps_an_unserved_slot_during_its_early_window(monkeypatch, minute):
    from connectonion.rem import service

    monkeypatch.setattr(service, "now", lambda: datetime(2026, 11, 6, 2, minute, tzinfo=timezone.utc))
    config = {"schedule": {"times": ["03:00", "17:00"], "timezone": "UTC"}}
    assert service.next_slot(config, timezone.utc) == "2026-11-06T03:00+00:00"


@pytest.mark.parametrize("location", ["worker", "runs"])
def test_live_pid_from_before_boot_does_not_block_the_next_round(rem, monkeypatch, location):
    from connectonion.rem import service

    root, _ = rem
    moment = service.now()
    monkeypatch.setattr(service, "_boot_time", lambda: moment - timedelta(minutes=10))
    set_config(root, ["schedule.timezone", "UTC", "schedule.times", "11:00,12:00"])
    record = {"id": "run_reused", "phase": "daily-sync", "outcome": "running",
              "started_at": (moment - timedelta(minutes=30)).isoformat(), **service.running_marker()}
    worker = {"enabled": True, "last_scheduled_slot": "2026-09-07T11:00:00+00:00"}
    if location == "worker":
        worker["scheduled_run"] = record
    else:
        write_json(state_path(root, "runs/run_reused.json"), record)
    write_json(state_path(root, "worker.json"), worker)
    assert service.run_scheduled(root, lambda: {"outcome": "no_change"}) == {"outcome": "no_change"}
    assert "scheduled_run" not in service.worker_state(root)


@pytest.mark.parametrize("boot_known", [True, False])
def test_long_scheduled_round_keeps_its_claim_while_session_summaries_run(rem, monkeypatch, boot_known):
    from connectonion.rem import service

    root, _ = rem
    started = service.now()
    boot = started - timedelta(days=4) if boot_known else None
    monkeypatch.setattr(service, "_boot_time", lambda: boot)
    set_config(root, ["schedule.timezone", "UTC", "schedule.times", "12:00,14:00"])
    write_json(state_path(root, "worker.json"), {"enabled": True})

    def summarize():
        worker = service.worker_state(root)
        monkeypatch.setattr(service, "now", lambda: started + timedelta(minutes=150))
        summary = {"id": "run_summary", "phase": "sessions-summary", "outcome": "running",
                   "started_at": started.isoformat(), **service.running_marker()}
        path = state_path(root, "runs/run_summary.json")
        write_json(path, summary)
        result = service.run_scheduled(root, lambda: pytest.fail("overlapping scheduled round"))
        assert result["outcome"] == "busy"
        assert service.worker_state(root) == worker
        assert read_json(path, {}) == summary
        return {"outcome": "completed"}

    assert service.run_scheduled(root, summarize) == {"outcome": "completed"}
    assert service.worker_state(root)["last_scheduled_slot"] == "2026-09-07T12:00:00+00:00"


def test_next_slot_keeps_tomorrows_midnight_slot_after_its_early_window_opens(monkeypatch):
    from connectonion.rem import service

    monkeypatch.setattr(service, "now", lambda: datetime(2026, 11, 6, 23, 58, tzinfo=timezone.utc))
    config = {"schedule": {"times": ["00:05"], "timezone": "UTC"}}
    assert service.next_slot(config, timezone.utc) == "2026-11-07T00:05+00:00"


@pytest.mark.parametrize("served, expected", [(False, "03:00"), (True, "17:00")])
def test_status_next_run_respects_an_early_served_slot(tmp_path, monkeypatch, served, expected):
    from connectonion.rem import service

    prepare(tmp_path)
    set_config(tmp_path, ["schedule.timezone", "UTC", "schedule.times", "03:00,17:00"])
    monkeypatch.setattr(service, "now", lambda: datetime(2026, 11, 6, 2, 59, tzinfo=timezone.utc))
    write_json(state_path(tmp_path, "consent.json"), {})
    worker = {"enabled": True, "scheduler": "fake"}
    if served:
        worker["last_scheduled_slot"] = "2026-11-06T03:00:00+00:00"
    write_json(state_path(tmp_path, "worker.json"), worker)
    assert bool(service._scheduled_slot(tmp_path)) is not served
    assert service.status(tmp_path)["next_run"] == f"2026-11-06T{expected}+00:00"


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_boot_time_reads_the_platform_source(monkeypatch, platform):
    from subprocess import CompletedProcess
    from connectonion.rem import service

    moment = datetime(2026, 11, 6, 10, tzinfo=timezone.utc)
    seconds = int(moment.timestamp())
    monkeypatch.setattr(service.sys, "platform", platform)
    if platform == "darwin":
        def sysctl(args, **kwargs):
            assert args == ["sysctl", "-n", "kern.boottime"]
            return CompletedProcess(args, 0, f"{{ sec = {seconds}, usec = 123 }} Fri Nov 6 10:00:00 2026\n")
        monkeypatch.setattr(service.subprocess, "run", sysctl)
    else:
        def proc_stat(path):
            assert str(path) == "/proc/stat"
            return f"cpu 1 2 3 4\nbtime {seconds}\nprocesses 900\n"
        monkeypatch.setattr(service.Path, "is_file", lambda path: str(path) == "/proc/stat")
        monkeypatch.setattr(service.Path, "read_text", proc_stat)
    assert service._boot_time() == moment


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_boot_time_unavailable_leaves_live_pids_trusted(monkeypatch, platform):
    from connectonion.rem import service

    def never(*args, **kwargs):
        raise AssertionError("no boot-time source should be read")

    monkeypatch.setattr(service.sys, "platform", platform)
    monkeypatch.setattr(service.shutil, "which", lambda name: None)
    monkeypatch.setattr(service.Path, "is_file", lambda path: False)
    monkeypatch.setattr(service.subprocess, "run", never)
    monkeypatch.setattr(service.Path, "read_text", never)
    assert service._boot_time() is None


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_boot_time_missing_from_platform_output_is_unknown(monkeypatch, platform):
    from subprocess import CompletedProcess
    from connectonion.rem import service

    monkeypatch.setattr(service.sys, "platform", platform)
    monkeypatch.setattr(service.subprocess, "run", lambda *a, **kw: CompletedProcess(a, 1, ""))
    monkeypatch.setattr(service.shutil, "which", lambda name: "/usr/sbin/sysctl")
    monkeypatch.setattr(service.Path, "is_file", lambda path: True)
    monkeypatch.setattr(service.Path, "read_text", lambda *a: "cpu 1 2 3 4\n")
    assert service._boot_time() is None


@pytest.mark.parametrize("code,message,fix", [
    ("reauth_required", "Microsoft authorization expired or was revoked.", "co auth microsoft"),
    ("broker_auth_failed", "OpenOnion authentication failed while refreshing provider access.", "co auth"),
    ("record_changed", "The selected credential record changed during this operation.", "co status"),
    ("permission_denied", "Microsoft permission denied for this operation.", "co auth microsoft"),
    ("invalid_response", "Authorization service returned invalid credentials; saved record kept.", "co status"),
])
def test_source_read_preserves_credential_code_and_recovery(rem, monkeypatch, code, message, fix):
    from connectonion.rem import service
    from connectonion.provider_credentials import ProviderCredentialError
    root, _ = rem
    failure = service._collection_failure("outlook", ProviderCredentialError(code, message, fix))
    assert code in failure["error"] and message in failure["error"] and fix in failure["error"]
    service._record_source_read(root, "outlook", failure["error"])
    reason, _ = service._mailbox_read_failure(root, "outlook")
    assert code in reason and message in reason and fix in reason


# -- Asana source registration ----------------------------------

@pytest.fixture
def asana_registration(tmp_path, monkeypatch):
    """A private notebook with synthetic credentials and no source/model access."""
    import socket
    from pathlib import Path
    from connectonion import environment, secret_store
    from connectonion.rem import runner, service
    from connectonion.useful_tools import asana, asana_export

    root = tmp_path / "notebook"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / "config"))
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(environment, "_loaded", {})
    monkeypatch.setattr(environment, "_selected", None)
    monkeypatch.setattr(secret_store, "stored_names", lambda directory: [])
    monkeypatch.setattr(service, "mail_available", lambda kind: False)
    monkeypatch.setattr(service, "codex_sessions_root", lambda: tmp_path / "sessions")
    monkeypatch.setattr(service, "claude_projects_root", lambda: tmp_path / "claude")
    monkeypatch.setattr(service, "now", lambda: datetime(2026, 11, 1, 12, tzinfo=timezone.utc))
    attempts = []

    def refuse_access(*args, **kwargs):
        attempts.append(True)
        pytest.fail("Source registration must not read Asana tasks or run a model")

    monkeypatch.setattr(socket.socket, "connect", refuse_access)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse_access)
    monkeypatch.setattr(socket, "create_connection", refuse_access)
    monkeypatch.setattr(asana, "_http", refuse_access)
    for name in ("get_user", "list_tasks", "get_task", "list_stories"):
        monkeypatch.setattr(asana.Asana, name, refuse_access)
    monkeypatch.setattr(asana_export, "sync_tasks", refuse_access)
    monkeypatch.setattr(runner, "run_stage", refuse_access)
    yield root
    assert attempts == [], "An unexpected source read or model call was attempted"


def _saved_asana_consent(root):
    """Seed prior consent to test registration changes, independently of start/sync."""
    sources = subscriptions(root)
    sources["asana"]["consented"] = True
    write_json(state_path(root, "subscriptions.json"), sources)


def test_asana_source_is_off_before_any_project_is_selected(asana_registration, monkeypatch):
    root = asana_registration
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "synthetic-asana-token")
    source = subscriptions(root)["asana"]
    assert source["kind"] == "asana"
    assert source["project_gids"] == []
    assert source["enabled"] is False
    assert source["consented"] is False
    assert not root.exists()


@pytest.mark.parametrize("token", [None, "", " ", "\t\n"])
def test_asana_source_waits_for_missing_or_blank_token(asana_registration, monkeypatch, token):
    root = asana_registration
    if token is not None:
        monkeypatch.setenv("ASANA_ACCESS_TOKEN", token)
    toggle_source(root, "asana", True, project="120012345678901234567890")
    source = subscriptions(root)["asana"]
    assert source["project_gids"] == ["120012345678901234567890"]
    assert "waiting for token" in json.dumps(source).lower()
    assert source["consented"] is False


def test_asana_registration_is_persistent_and_does_not_save_credentials(asana_registration, monkeypatch):
    root = asana_registration
    token = "synthetic-asana-token-not-for-storage"
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", token)
    name = toggle_source(root, "asana", True, project="000120012345678901234567890")
    assert name == "asana"
    saved = read_json(state_path(root, "subscriptions.json"), {})["asana"]
    assert saved["project_gids"] == ["000120012345678901234567890"]
    assert saved["enabled"] is True
    assert saved["consented"] is False
    assert token not in json.dumps(saved)
    assert subscriptions(root)["asana"]["project_gids"] == saved["project_gids"]
    assert not state_path(root, "consent.json").exists()
    assert not (root / "worker.json").exists()


def test_repeated_asana_add_accumulates_projects_without_duplicates(asana_registration):
    root = asana_registration
    for gid in ("200", "201", "200"):
        toggle_source(root, "asana", True, project=gid)
    assert set(subscriptions(root)["asana"]["project_gids"]) == {"200", "201"}
    assert len(subscriptions(root)["asana"]["project_gids"]) == 2


def test_same_asana_project_preserves_consent_and_existing_progress(asana_registration, monkeypatch):
    root = asana_registration
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "synthetic-asana-token")
    toggle_source(root, "asana", True, project="200")
    _saved_asana_consent(root)
    progress = {"asana": {"checkpoint": "synthetic-existing-progress"}}
    write_json(state_path(root, "progress.json"), progress)
    before = subscriptions(root)["asana"]
    assert before["consented"] is True
    toggle_source(root, "asana", True, project="200")
    assert subscriptions(root)["asana"] == before
    assert read_json(state_path(root, "progress.json"), {}) == progress


def test_new_asana_project_revokes_consent_and_changes_summary(asana_registration, monkeypatch):
    from connectonion.rem.service import consent_summary, summary_fingerprint
    root = asana_registration
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "synthetic-asana-token")
    toggle_source(root, "asana", True, project="200")
    _saved_asana_consent(root)
    fingerprint = summary_fingerprint(root)
    toggle_source(root, "asana", True, project="201")
    source = subscriptions(root)["asana"]
    assert source["consented"] is False
    assert set(source["project_gids"]) == {"200", "201"}
    summary = json.dumps(consent_summary(root)["sources"]["asana"])
    assert "200" in summary and "201" in summary
    assert summary_fingerprint(root) != fingerprint


@pytest.mark.parametrize("project", ["abc", "../project", "/work/project", "-1", "12 3", "0x123"])
def test_invalid_asana_project_cannot_change_saved_selection(asana_registration, project):
    root = asana_registration
    toggle_source(root, "asana", True, project="200")
    path = state_path(root, "subscriptions.json")
    before = path.read_bytes()
    with pytest.raises(RemError):
        toggle_source(root, "asana", True, project=project)
    assert path.read_bytes() == before


@pytest.mark.parametrize("kwargs", [{"about": "browser"}, {"chats": ["chat-1"]}])
def test_asana_rejects_other_sources_scope_options(asana_registration, kwargs):
    root = asana_registration
    toggle_source(root, "asana", True, project="200")
    before = state_path(root, "subscriptions.json").read_bytes()
    with pytest.raises(RemError):
        toggle_source(root, "asana", True, project="201", **kwargs)
    assert state_path(root, "subscriptions.json").read_bytes() == before


def test_asana_remove_one_project_keeps_the_other(asana_registration):
    root = asana_registration
    toggle_source(root, "asana", True, project="200")
    toggle_source(root, "asana", True, project="201")
    toggle_source(root, "asana", False, project="200")
    source = subscriptions(root)["asana"]
    assert source["project_gids"] == ["201"]
    assert source["enabled"] is True
    toggle_source(root, "asana", False, project="201")
    assert subscriptions(root)["asana"]["enabled"] is False
    assert subscriptions(root)["asana"]["project_gids"] == []


def test_asana_remove_all_stops_reads_without_erasing_saved_material(asana_registration, tmp_path):
    root = asana_registration
    toggle_source(root, "asana", True, project="200")
    material = tmp_path / "inbox/asana/daily/2026/11/01.jsonl"
    material.parent.mkdir(parents=True)
    material.write_text('{"synthetic":true}\n')
    before = material.read_bytes()
    toggle_source(root, "asana", False)
    assert subscriptions(root)["asana"]["enabled"] is False
    assert material.read_bytes() == before


def test_asana_token_status_is_refreshed_without_changing_selection(asana_registration, monkeypatch):
    root = asana_registration
    toggle_source(root, "asana", True, project="200")
    assert "waiting for token" in json.dumps(subscriptions(root)["asana"]).lower()
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "synthetic-asana-token")
    assert "waiting for token" not in json.dumps(subscriptions(root)["asana"]).lower()
    monkeypatch.delenv("ASANA_ACCESS_TOKEN")
    assert "waiting for token" in json.dumps(subscriptions(root)["asana"]).lower()
    assert subscriptions(root)["asana"]["project_gids"] == ["200"]


def test_asana_notebooks_have_independent_project_choices(asana_registration):
    root = asana_registration
    other = root.parent / "other-notebook"
    toggle_source(root, "asana", True, project="200")
    toggle_source(other, "asana", True, project="201")
    assert subscriptions(root)["asana"]["project_gids"] == ["200"]
    assert subscriptions(other)["asana"]["project_gids"] == ["201"]


def test_asana_registration_preserves_other_source_settings(asana_registration):
    root = asana_registration
    toggle_source(root, "codex", True, project="/work/demo")
    before = {name: value for name, value in subscriptions(root).items() if name != "asana"}
    toggle_source(root, "asana", True, project="200")
    after = {name: value for name, value in subscriptions(root).items() if name != "asana"}
    assert after == before
    assert any(source.get("project") == "/work/demo" for source in after.values())


def test_asana_corrupt_subscriptions_are_preserved(asana_registration):
    root = asana_registration
    toggle_source(root, "asana", True, project="200")
    path = state_path(root, "subscriptions.json")
    path.write_text('{"broken":')
    with pytest.raises(RemError):
        toggle_source(root, "asana", True, project="201")
    assert path.read_text() == '{"broken":'


def test_asana_failed_settings_publish_preserves_old_choices(asana_registration, monkeypatch):
    import os
    from pathlib import Path
    root = asana_registration
    toggle_source(root, "asana", True, project="200")
    path = state_path(root, "subscriptions.json")
    before = path.read_bytes()
    replace = os.replace

    def fail_settings(src, dst, *args, **kwargs):
        if Path(dst).name == "subscriptions.json":
            raise OSError("Synthetic settings failure")
        return replace(src, dst, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", fail_settings)
        with pytest.raises((OSError, RemError)):
            toggle_source(root, "asana", True, project="201")
    assert path.read_bytes() == before


def test_asana_source_changes_respect_the_existing_writer_lock(asana_registration):
    from connectonion.rem.files import maintenance_lock
    root = asana_registration
    toggle_source(root, "asana", True, project="200")
    before = state_path(root, "subscriptions.json").read_bytes()
    with maintenance_lock(root):
        with pytest.raises(RemError):
            toggle_source(root, "asana", True, project="201")
    assert state_path(root, "subscriptions.json").read_bytes() == before


def test_asana_add_and_inspection_do_not_create_collection_material(asana_registration, tmp_path):
    root = asana_registration
    toggle_source(root, "asana", True, project="200")
    subscriptions(root)
    assert not (tmp_path / "inbox").exists()
    assert not state_path(root, "progress.json").exists()
    assert not state_path(root, "worker.json").exists()
    assert not state_path(root, "consent.json").exists()


def test_asana_selection_excludes_unselected_project_from_consent(asana_registration, monkeypatch):
    from connectonion.rem.service import consent_summary
    root = asana_registration
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "synthetic-asana-token")
    toggle_source(root, "asana", True, project="200")
    summary = consent_summary(root)["sources"]["asana"]
    assert summary["project_gids"] == ["200"]
    toggle_source(root, "asana", True, project="201")
    toggle_source(root, "asana", False, project="200")
    assert consent_summary(root)["sources"]["asana"]["project_gids"] == ["201"]


def test_asana_add_without_new_project_restores_only_saved_scope(asana_registration):
    root = asana_registration
    toggle_source(root, "asana", True, project="200")
    toggle_source(root, "asana", False)
    toggle_source(root, "asana", True)
    source = subscriptions(root)["asana"]
    assert source["enabled"] is True
    assert source["project_gids"] == ["200"]


def test_asana_unapproved_source_cannot_start_reading(asana_registration, monkeypatch):
    root = asana_registration
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "synthetic-asana-token")
    toggle_source(root, "asana", True, project="200")
    prepare(root)
    with pytest.raises(RemError, match="start"):
        run_sync(root, runner=lambda *args, **kwargs: pytest.fail("Unapproved model run"))
    assert subscriptions(root)["asana"]["consented"] is False


def test_asana_dry_run_preserves_settings_and_collection_progress(asana_registration, monkeypatch):
    root = asana_registration
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "synthetic-asana-token")
    toggle_source(root, "asana", True, project="200")
    before = {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    result = run_sync(root, dry_run=True)
    assert result["dry_run"] is True
    assert {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("saved", [[], None, "not a mapping", 123])
def test_asana_invalid_subscription_document_is_not_overwritten(asana_registration, saved):
    root = asana_registration
    toggle_source(root, "asana", True, project="200")
    path = state_path(root, "subscriptions.json")
    path.write_text(json.dumps(saved))
    before = path.read_bytes()
    with pytest.raises(RemError):
        toggle_source(root, "asana", True, project="201")
    assert path.read_bytes() == before


def test_asana_declined_start_does_not_authorize_or_install_schedule(asana_registration, monkeypatch):
    from connectonion.rem.service import start
    root = asana_registration
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "synthetic-asana-token")
    toggle_source(root, "asana", True, project="200")
    shown = []
    scheduler = FakeScheduler()
    result = start(root, confirm=lambda summary: shown.append(summary) or False,
                   scheduler=scheduler, runner=lambda *a, **kw: pytest.fail("Declined model run"))
    assert result["started"] is False
    assert scheduler.installed == []
    assert shown[0]["sources"]["asana"]["project_gids"] == ["200"]
    assert subscriptions(root)["asana"]["consented"] is False


def test_asana_notebook_selection_does_not_change_when_another_is_removed(asana_registration):
    root = asana_registration
    other = root.parent / "second"
    toggle_source(root, "asana", True, project="200")
    toggle_source(other, "asana", True, project="201")
    before = subscriptions(root)["asana"]
    toggle_source(other, "asana", False)
    assert subscriptions(root)["asana"] == before


def test_asana_summary_and_status_do_not_persist_token(asana_registration, monkeypatch):
    from connectonion.rem.service import consent_summary
    root = asana_registration
    token = "synthetic-asana-summary-secret"
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", token)
    toggle_source(root, "asana", True, project="200")
    before = {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    summary = consent_summary(root)
    assert token not in json.dumps(summary)
    assert {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("value", [" 200 ", "\t200\n", "\r\n200\t"])
def test_asana_project_trims_surrounding_whitespace(asana_registration, value):
    root = asana_registration
    toggle_source(root, "asana", True, project=value)
    assert subscriptions(root)["asana"]["project_gids"] == ["200"]


@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_asana_first_blank_project_cannot_enable_source(asana_registration, value):
    root = asana_registration
    with pytest.raises(RemError):
        toggle_source(root, "asana", True, project=value)
    source = subscriptions(root)["asana"]
    assert source["enabled"] is False
    assert source["project_gids"] == []


# -- Asana sync acceptance --------------------------------------


@pytest.fixture
def asana_sync(asana_material, monkeypatch, tmp_path):
    """Exercise real collection and consumption with a fake upstream and runner."""
    from copy import deepcopy
    from connectonion.useful_tools import asana
    source, client = asana_material
    root = tmp_path / "rem"
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "synthetic-story26-token")
    monkeypatch.setattr(asana, "Asana", lambda: client)
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    prepare(root)
    toggle_source(root, "asana", True, project="200")
    approve_sources(root)
    calls = []

    def runner(notebook, items, config, kind=""):
        calls.append({"items": deepcopy(items), "kind": kind, "upstream": list(client.calls)})
        return {"changed": [], "usage": {"input_tokens": 10, "output_tokens": 2}}

    return root, client, calls, runner


def test_asana_sync_collects_before_delivering_new_material(asana_sync):
    root, client, calls, runner = asana_sync
    result = run_sync(root, source="asana", runner=runner)
    assert result["outcome"] == "completed" and result["items"] == 1
    assert len(calls) == 1 and calls[0]["kind"] == "asana"
    assert ("stories", "300") in calls[0]["upstream"]
    text = calls[0]["items"][0]["text"]
    assert all(name in text for name in ("Alice Assignee", "Bob Commenter", "Atlas Project"))


def test_asana_unchanged_sync_calls_no_runner_twice(asana_sync):
    root, client, calls, runner = asana_sync
    run_sync(root, source="asana", runner=runner)
    client.calls.clear()
    result = run_sync(root, source="asana", runner=runner)
    assert result["outcome"] == "no_change" and len(calls) == 1
    assert ("list", "200") in client.calls


def test_asana_sync_refreshes_saved_task_before_consumption(asana_sync):
    from pathlib import Path
    from connectonion.useful_tools import asana_export
    root, client, calls, runner = asana_sync
    source = subscriptions(root)["asana"]
    client.tasks["300"]["name"] = "Old saved title"
    asana_export.sync_tasks(client, Path(source["root"]), ["200"])
    client.tasks["300"]["name"] = "Fresh title from this sync"
    result = run_sync(root, source="asana", runner=runner)
    assert result["items"] == 1
    text = calls[0]["items"][0]["text"]
    assert "Fresh title from this sync" in text and "Old saved title" not in text


def test_asana_failed_runner_retries_same_saved_version(asana_sync):
    root, client, calls, runner = asana_sync
    before = read_json(state_path(root, "progress.json"), {})
    attempted = []

    def failing(notebook, items, config, kind=""):
        attempted.extend(item["source"] for item in items)
        raise RuntimeError("Synthetic maintenance failure")

    result = run_sync(root, source="asana", runner=failing)
    assert result["outcome"] == "failed"
    assert read_json(state_path(root, "progress.json"), {}) == before
    assert run_sync(root, source="asana", runner=runner)["outcome"] == "completed"
    assert [item["source"] for item in calls[0]["items"]] == attempted
    assert run_sync(root, source="asana", runner=runner)["items"] == 0


def test_asana_dry_run_counts_saved_latest_tasks_without_effects(asana_sync, monkeypatch):
    from pathlib import Path
    from connectonion.useful_tools import asana_export
    root, client, calls, runner = asana_sync
    assert run_sync(root, source="asana", dry_run=True)["sources"]["asana"]["pending_tasks"] is None
    assert client.calls == calls == []
    source = Path(subscriptions(root)["asana"]["root"])
    asana_export.sync_tasks(client, source, ["200"])
    client.tasks["300"]["name"] = "New saved version"
    asana_export.sync_tasks(client, source, ["200"])
    before = {p: p.read_bytes() for p in root.parent.rglob('*') if p.is_file()}
    client.calls.clear()
    monkeypatch.setattr(asana_export, "load_snapshots", lambda *a, **kw: pytest.fail("Dry-run read task body"))
    result = run_sync(root, source="asana", dry_run=True, all_pending=True)
    assert result["sources"]["asana"]["pending_tasks"] == 1
    assert result["sources"]["asana"]["body_reads"] is False
    assert client.calls == calls == []
    assert {p: p.read_bytes() for p in root.parent.rglob('*') if p.is_file()} == before


def test_asana_successful_consumption_clears_pending_count(asana_sync):
    root, client, calls, runner = asana_sync
    run_sync(root, source="asana", runner=runner)
    assert run_sync(root, source="asana", dry_run=True)["sources"]["asana"]["pending_tasks"] == 0


def test_asana_sync_never_fetches_unselected_project(asana_sync):
    from tests.unit.test_asana_export import _task
    root, client, calls, runner = asana_sync
    client.projects["201"] = ["301"]
    client.tasks["301"] = _task("301", name="Private task", projects=[{"gid": "201"}])
    run_sync(root, source="asana", runner=runner)
    assert ("list", "201") not in client.calls and ("task", "301") not in client.calls
    assert "Private task" not in json.dumps(calls)


def test_asana_all_drains_bounded_batches_without_collecting_each_time(asana_sync):
    from tests.unit.test_asana_export import _task
    root, client, calls, runner = asana_sync
    for gid in ("301", "302"):
        client.projects["200"].append(gid); client.tasks[gid] = _task(gid)
    set_config(root, ["limits.extract_items_per_batch", "1"])
    approve_sources(root)
    result = run_sync(root, source="asana", all_pending=True, runner=runner)
    assert result["outcome"] == "caught_up" and result["items"] == 3
    assert len(calls) == 3 and all(len(call["items"]) == 1 for call in calls)
    assert client.calls.count(("list", "200")) == 1
    assert len({item["source"] for call in calls for item in call["items"]}) == 3


@pytest.mark.parametrize("method", ["list", "task", "stories"])
def test_asana_first_collection_failure_never_sends_partial_material(asana_sync, method):
    root, client, calls, runner = asana_sync
    client.failure = (method, "200" if method == "list" else "300")
    result = run_sync(root, source="asana", runner=runner)
    assert calls == []
    assert result["collection"]["asana"]["collected"] is False
    assert "fail" in json.dumps(result).lower()


def test_asana_collection_failure_reports_saved_material_fallback(asana_sync):
    from pathlib import Path
    from connectonion.useful_tools import asana_export
    root, client, calls, runner = asana_sync
    asana_export.sync_tasks(client, Path(subscriptions(root)["asana"]["root"]), ["200"])
    client.failure = ("list", "200")
    result = run_sync(root, source="asana", runner=runner)
    assert result["items"] == 1 and len(calls) == 1
    assert result["collection"]["asana"]["collected"] is False
    assert "earlier" in json.dumps(result).lower()


def test_asana_wrong_account_blocks_cached_material(asana_sync):
    from pathlib import Path
    from connectonion.useful_tools import asana_export
    root, client, calls, runner = asana_sync
    asana_export.sync_tasks(client, Path(subscriptions(root)["asana"]["root"]), ["200"])
    client.account = "999"
    result = run_sync(root, source="asana", runner=runner)
    assert calls == []
    assert "asana" in result["not_read"]
    assert "account" in json.dumps(result).lower()


def test_unapproved_asana_does_not_collect_even_with_notebook_consent(asana_sync):
    root, client, calls, runner = asana_sync
    root = root.parent / "new-notebook"
    prepare(root)
    approve_sources(root)
    toggle_source(root, "asana", True, project="200")
    assert subscriptions(root)["asana"]["consented"] is False
    run_sync(root, source="asana", runner=runner)
    assert client.calls == calls == []


def test_sync_of_another_source_does_not_collect_asana(asana_sync):
    root, client, calls, runner = asana_sync
    run_sync(root, source="codex", runner=runner)
    assert client.calls == calls == []


def test_asana_all_stops_on_failed_batch_and_keeps_it_pending(asana_sync):
    root, client, calls, runner = asana_sync

    def failing(*args, **kwargs):
        calls.append("failed")
        raise RuntimeError("Synthetic failure before any page write")

    result = run_sync(root, source="asana", all_pending=True, runner=failing)
    assert result["outcome"] == "failed" and calls == ["failed"]
    assert run_sync(root, source="asana", dry_run=True)["sources"]["asana"]["pending_tasks"] == 1


@pytest.mark.parametrize("damage", ["missing_daily", "invalid_state"])
def test_asana_damaged_cache_is_reported_without_model_input(asana_sync, damage):
    from pathlib import Path
    from connectonion.useful_tools import asana_export
    root, client, calls, runner = asana_sync
    source = Path(subscriptions(root)["asana"]["root"])
    asana_export.sync_tasks(client, source, ["200"])
    if damage == "missing_daily":
        [daily] = list(source.glob('daily/*/*/*.jsonl'))
        daily.unlink()
    else:
        (source / 'state.json').write_text('not JSON', encoding='utf-8')
    result = run_sync(root, source="asana", runner=runner)
    assert calls == []
    assert "asana" in result["not_read"]
    assert result["collection"]["asana"]["collected"] is False


def test_asana_sync_does_not_persist_credentials_in_material_or_logs(asana_sync):
    root, client, calls, runner = asana_sync
    result = run_sync(root, source="asana", runner=runner)
    token = "synthetic-story26-token"
    assert token not in json.dumps(result) + json.dumps(calls)
    for path in root.parent.rglob('*'):
        if path.is_file():
            assert token.encode() not in path.read_bytes(), path
