"""Successive-pass orchestration tested with a synthetic, deterministic runner."""

from datetime import datetime, timezone

import pytest

from connectonion.wiki.config import prepare, set_config
from connectonion.wiki.files import Notebook, WikiError, read_json, state_path
from connectonion.wiki.service import approve_sources, run_sync, status, subscriptions, toggle_source
from tests.unit.test_wiki_source import rollout


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.wiki.service.claude_projects_root", lambda: tmp_path / "no-claude")
    monkeypatch.setattr("connectonion.wiki.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    prepare(root)
    approve_sources(root)
    return root, sessions


def test_successive_correction_and_no_input_does_not_invoke_runner(wiki):
    root, sessions = wiki
    path = sessions / "rollout-a.jsonl"
    messages = [("user", "We choose SQL")]
    calls = []

    def runner(notebook, items, config):
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


def test_failure_preserves_progress_and_counts_attempt(wiki):
    root, sessions = wiki
    rollout(sessions / "rollout-a.jsonl", [("user", "private sample text")])

    def failing(*args):
        raise RuntimeError("private sample text must not enter logs")

    result = run_sync(root, runner=failing)
    assert result["outcome"] == "failed"
    assert result["usage"] is None
    assert "private sample" not in str(result)
    assert read_json(state_path(root, "progress.json"), {}) == {}
    assert status(root)["runner_attempts_today"] == 1


def test_unsubscribe_survives_approval_and_does_not_erase(wiki):
    root, sessions = wiki
    Notebook(root).write("people/alice.md", "Keep this")
    toggle_source(root, "codex", False)
    approve_sources(root)
    assert subscriptions(root)["codex"]["enabled"] is False
    assert Notebook(root).read("people/alice.md") == "Keep this"
    assert run_sync(root, runner=lambda *args: pytest.fail("invoked"))["outcome"] == "no_change"


def test_dry_run_has_no_state_or_body_effects(wiki):
    root, sessions = wiki
    rollout(sessions / "rollout-a.jsonl", [("user", "private")])
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = run_sync(root, dry_run=True)
    after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert result["sources"]["codex"]["message_count"] is None


def test_unconsented_start_cannot_infer(tmp_path):
    prepare(tmp_path)
    with pytest.raises(WikiError, match="start"):
        run_sync(tmp_path, runner=lambda *args: pytest.fail("invoked"))


def test_too_small_input_limit_is_not_called_no_change(wiki):
    root, sessions = wiki
    rollout(sessions / "rollout-a.jsonl", [("user", "pending")])
    set_config(root, ["limits.input_chars_per_batch", "1"])
    with pytest.raises(WikiError, match="input limit"):
        run_sync(root, runner=lambda *args: pytest.fail("invoked"))


def test_budget_failure_does_not_acknowledge_pending_messages(wiki):
    root, sessions = wiki
    path = sessions / "rollout-a.jsonl"
    set_config(root, ["limits.runner_calls_per_day", "1"])
    rollout(path, [("user", "first")])
    run_sync(root, runner=lambda *args: {"usage": None})
    before = state_path(root, "progress.json").read_bytes()
    rollout(path, [("user", "first"), ("user", "second")])
    with pytest.raises(WikiError, match="limit"):
        run_sync(root, runner=lambda *args: pytest.fail("invoked"))
    assert state_path(root, "progress.json").read_bytes() == before


def test_interruption_keeps_partial_writes_but_not_checkpoint(wiki):
    root, sessions = wiki
    rollout(sessions / "rollout-a.jsonl", [("user", "keep the rationale")])
    def interrupted(notebook, *args):
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
    def runner(notebook, items, config):
        calls.append(items)
        notebook.write("notes/first.md", "# First\n" + items[0]["text"])
        return {"usage": None, "changed": ["notes/first.md"]}
    return runner


def test_declined_start_reads_nothing_and_installs_nothing(tmp_path, monkeypatch):
    from connectonion.wiki.service import start
    root, sessions = tmp_path / "wiki", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sessions)
    rollout(sessions / "rollout-a.jsonl", [("user", "private")])
    shown, calls, scheduler = [], [], FakeScheduler()
    result = start(root, confirm=lambda summary: shown.append(summary) or False,
                   scheduler=scheduler, runner=_runner_recording(calls))
    assert result["started"] is False
    assert str(sessions) in str(shown[0])  # the summary names the exact directory it would read
    assert not state_path(root, "consent.json").exists()
    assert scheduler.installed == [] and calls == []


def test_first_start_consents_installs_and_runs_one_batch_then_repeat_start_does_not_rerun(tmp_path, monkeypatch):
    from connectonion.wiki.service import start
    root, sessions = tmp_path / "wiki", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.wiki.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
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


def test_stop_disables_background_but_manual_sync_still_works(tmp_path, monkeypatch):
    from connectonion.wiki.service import start, stop
    root, sessions = tmp_path / "wiki", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.wiki.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    calls, scheduler = [], FakeScheduler()
    start(root, confirm=lambda s: True, scheduler=scheduler, runner=_runner_recording(calls))
    assert stop(root, scheduler=scheduler)["enabled"] is False
    assert scheduler.uninstalled == [root.resolve()]
    assert "Stopped" in status(root)["state"] and "start" in status(root)["state"]
    rollout(sessions / "rollout-a.jsonl", [("user", "hello"), ("user", "more")])
    assert run_sync(root, runner=_runner_recording(calls))["outcome"] == "completed"


def test_start_without_a_scheduler_keeps_consent_and_points_to_manual_sync(tmp_path, monkeypatch):
    from connectonion.wiki.schedule import Unsupported
    from connectonion.wiki.service import start
    root, sessions = tmp_path / "wiki", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sessions)
    with pytest.raises(WikiError, match="co wiki sync"):
        start(root, confirm=lambda s: True, scheduler=Unsupported(), runner=lambda *a: pytest.fail("ran"))
    assert state_path(root, "consent.json").is_file()


def test_stop_does_not_wait_for_a_running_batch(tmp_path, monkeypatch):
    """launchd fires a batch the moment the job loads; stop must still work while it runs."""
    from connectonion.wiki.service import start, stop
    root, sessions = tmp_path / "wiki", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sessions)
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    scheduler = FakeScheduler()
    start(root, confirm=lambda s: True, scheduler=scheduler, runner=_runner_recording([]))
    import subprocess  # noqa: E401 - a second process holds the lock, as a real batch would
    import sys
    import textwrap
    holder = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import time
        from pathlib import Path
        from connectonion.wiki.files import maintenance_lock
        with maintenance_lock(Path({str(root.resolve())!r})):
            print("held", flush=True); time.sleep(30)
    """)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        assert stop(root, scheduler=scheduler)["enabled"] is False
        assert scheduler.uninstalled == [root.resolve()]
    finally:
        holder.kill()


def test_first_batch_runs_before_the_clock_is_installed(tmp_path, monkeypatch):
    """Otherwise the job's run-at-load batch and the foreground batch race for the lock."""
    from connectonion.wiki.service import start
    root, sessions = tmp_path / "wiki", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sessions)
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])
    order = []

    class Ordered(FakeScheduler):
        def install(self, root, config):
            order.append("install")
            return super().install(root, config)

    def runner(notebook, items, config):
        order.append("batch")
        return {"usage": None, "changed": []}
    start(root, confirm=lambda s: True, scheduler=Ordered(), runner=runner)
    assert order == ["batch", "install"]


def test_sigterm_during_a_batch_is_recorded_as_interrupted(wiki):
    """launchctl bootout terminates the job; the run must not stay 'running' forever."""
    import os
    import signal
    root, sessions = wiki
    rollout(sessions / "rollout-a.jsonl", [("user", "hello")])

    def runner(notebook, items, config):
        os.kill(os.getpid(), signal.SIGTERM)
        raise AssertionError("SIGTERM should have interrupted the batch")
    with pytest.raises(KeyboardInterrupt):
        run_sync(root, runner=runner)
    from connectonion.wiki.service import run_logs
    assert run_logs(root)[0]["outcome"] == "interrupted"
    assert read_json(state_path(root, "progress.json"), {}) == {}


def test_latest_slot_is_the_most_recent_saved_time_in_the_saved_zone():
    from datetime import datetime, timezone

    from connectonion.wiki.service import latest_slot
    config = {"schedule": {"times": ["03:00", "17:00"], "timezone": "Australia/Sydney"}}
    # 2026-09-07 12:00 UTC is 22:00 in Sydney: the 17:00 slot of that day is the latest.
    slot = latest_slot(config, datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    assert slot.isoformat() == "2026-09-07T17:00:00+10:00"
    # 2026-09-07 06:30 UTC is 16:30 Sydney: 17:00 has not come, so 03:00 today is the latest.
    slot = latest_slot(config, datetime(2026, 9, 7, 6, 30, tzinfo=timezone.utc))
    assert slot.isoformat() == "2026-09-07T03:00:00+10:00"


def test_scheduled_sync_runs_once_per_slot_and_coalesces_missed_ones(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from connectonion.wiki.service import start
    root, sessions = tmp_path / "wiki", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sessions)
    clock = {"now": datetime(2026, 9, 7, 6, 30, tzinfo=timezone.utc)}  # 16:30 Sydney
    monkeypatch.setattr("connectonion.wiki.service.now", lambda: clock["now"])
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


def test_lookback_defaults_to_two_months_and_is_capped_per_source_kind(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from connectonion.wiki.service import subscriptions, toggle_source
    fixed = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    monkeypatch.setattr("connectonion.wiki.service.now", lambda: fixed)
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: tmp_path / "sessions")
    root = tmp_path / "wiki"
    prepare(root)
    since = datetime.fromisoformat(subscriptions(root)["codex"]["since"])
    assert since == fixed - timedelta(days=60)
    assert subscriptions(root)["gmail"]["max_lookback_days"] == 730
    assert subscriptions(root)["codex"]["max_lookback_days"] == 180
    toggle_source(root, "codex", True, project=str(tmp_path), since="180d")  # at the cap: fine
    with pytest.raises(WikiError, match="180"):
        toggle_source(root, "codex", True, project=str(tmp_path / "other"), since="400d")


def test_sync_all_runs_batches_until_caught_up_regardless_of_the_daily_cap(wiki):
    root, sessions = wiki
    set_config(root, ["limits.items_per_batch", "2", "limits.runner_calls_per_day", "1"])
    rollout(sessions / "rollout-a.jsonl", [("user", f"fact {n}") for n in range(7)])
    calls = []

    def runner(notebook, items, config):
        calls.append(len(items))
        return {"usage": None, "changed": []}
    summary = run_sync(root, all_pending=True, runner=runner)
    assert calls == [2, 2, 2, 1]
    assert summary["batches"] == 4 and summary["items"] == 7 and summary["outcome"] == "caught_up"
    assert run_sync(root, all_pending=True, runner=runner)["batches"] == 0


def test_claude_code_is_a_real_default_source(tmp_path, monkeypatch):
    from connectonion.wiki.service import subscriptions
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: tmp_path / "codex")
    monkeypatch.setattr("connectonion.wiki.service.claude_projects_root", lambda: tmp_path / "claude")
    root = tmp_path / "wiki"
    prepare(root)
    claude = subscriptions(root)["claude-code"]
    assert claude["adapter"] == "available" and claude["kind"] == "claude-code"
    assert claude["root"] == str(tmp_path / "claude")
    approve_sources(root)
    assert subscriptions(root)["claude-code"]["consented"] is True


def test_outlook_source_flows_through_sync_with_its_own_cursor(tmp_path, monkeypatch):
    from connectonion.wiki.service import subscriptions, toggle_source
    from tests.unit.test_wiki_mail import FakeMail, mail
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: tmp_path / "codex")
    monkeypatch.setattr("connectonion.wiki.service.claude_projects_root", lambda: tmp_path / "claude")
    monkeypatch.setattr("connectonion.wiki.service.mail_available", lambda kind: kind == "outlook")
    monkeypatch.setattr("connectonion.wiki.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00", body="Alice: let's use Markdown for Aurora.")])
    monkeypatch.setattr("connectonion.wiki.service.mail_client", lambda kind: client)
    root = tmp_path / "wiki"
    prepare(root)
    assert subscriptions(root)["outlook"]["adapter"] == "available"
    assert subscriptions(root)["gmail"]["adapter"].startswith("waiting")
    toggle_source(root, "outlook", True)
    approve_sources(root)
    seen = []

    def runner(notebook, items, config):
        seen.extend(items)
        return {"usage": None, "changed": []}
    assert run_sync(root, runner=runner)["outcome"] == "completed"
    assert [i["source"] for i in seen] == ["outlook:m1"] and seen[0]["role"] == "other"
    assert read_json(state_path(root, "progress.json"), {})["outlook"]["cursor"] == "2026-09-02T09:00:00+00:00"
    assert run_sync(root, runner=runner)["outcome"] == "no_change"
