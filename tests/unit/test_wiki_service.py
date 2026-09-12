"""Successive-pass orchestration tested with a synthetic, deterministic runner."""

import json
from datetime import datetime, timezone

import pytest

from connectonion.wiki.config import prepare, set_config
from connectonion.wiki.files import Notebook, WikiError, read_json, state_path, write_json
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
    set_config(root, ["limits.items_per_batch", "2", "limits.extract_items_per_batch", "2",
                      "limits.runner_calls_per_day", "1"])
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


def test_outlook_source_flows_through_sync_with_its_own_progress(tmp_path, monkeypatch):
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
    assert [i["reference"] for i in seen] == ["outlook:m1"] and seen[0]["role"] == "other"
    assert seen[0]["correspondent"] == "alice@example.com"
    outlook = read_json(state_path(root, "progress.json"), {})["outlook"]
    assert outlook["scanned_until"] == "2026-09-02T09:00:00+00:00" and outlook["pending"] == {}
    assert run_sync(root, runner=runner)["outcome"] == "no_change"


def _extract_world(tmp_path, monkeypatch, n_messages):
    root, sessions = tmp_path / "wiki", tmp_path / "sessions"
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.wiki.service.claude_projects_root", lambda: tmp_path / "no-claude")
    monkeypatch.setattr("connectonion.wiki.service.now", lambda: datetime(2026, 9, 7, 12, tzinfo=timezone.utc))
    prepare(root)
    approve_sources(root)
    rollout(sessions / "rollout-a.jsonl", [("user", f"fact {i}") for i in range(n_messages)])
    return root


def test_a_large_batch_is_extracted_first_and_the_maintainer_reads_only_the_digest(tmp_path, monkeypatch):
    root = _extract_world(tmp_path, monkeypatch, 40)
    seen_by_extractor, seen_by_runner = [], []

    def extractor(items, config):
        seen_by_extractor.append(len(items))
        return {"notes": "## Decisions\n- fact 3 — user, codex:s:0", "usage": {"input_tokens": 100, "output_tokens": 10}}

    def runner(notebook, items, config):
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
    record = run_sync(root, runner=lambda nb, items, cfg: runner_items.extend(items) or {"usage": None, "changed": []},
                      extractor=lambda items, cfg: pytest.fail("extraction called for a small batch"))
    assert record["extracted"] is False and len(runner_items) == 3


def test_nothing_worth_keeping_skips_the_maintainer(tmp_path, monkeypatch):
    root = _extract_world(tmp_path, monkeypatch, 30)
    record = run_sync(root, runner=lambda *a: pytest.fail("maintainer called with an empty digest"),
                      extractor=lambda items, cfg: {"notes": "Nothing worth keeping.", "usage": None})
    assert record["outcome"] == "completed" and record["items"] == 30 and record["changed"] == []
    assert read_json(state_path(root, "progress.json"), {})  # the batch is consumed all the same


def test_older_config_without_extraction_limits_still_loads(tmp_path):
    import yaml

    from connectonion.wiki.config import read_config
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
    record = run_sync(root, runner=lambda nb, items, cfg: {"usage": {"input_tokens": 20, "output_tokens": 5}, "changed": []},
                      extractor=lambda items, cfg: {"notes": "## Decisions\n- fact 1 — user, codex:s:0",
                                                    "usage": {"input_tokens": 100, "output_tokens": 10}})
    assert record["usage_by_stage"] == {"extract": {"input_tokens": 100, "output_tokens": 10},
                                        "maintain": {"input_tokens": 20, "output_tokens": 5}}
    assert record["items_by_source"] == {"codex": 40}
    assert record["chars_in"] > 40 * 6 and record["seconds"] >= 0


def test_usage_report_aggregates_raw_records_by_stage_source_and_model(tmp_path):
    from connectonion.wiki.service import usage_report
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


def test_a_format_that_moved_is_reported_instead_of_looking_like_a_quiet_week(wiki):
    """Reading only the shape the user types fails closed, and closed is silent: the
    notebook would keep saying "nothing new" while the person talked all week. A pass
    that passes over a pile of unfamiliar user-slot messages says which source and how
    many, and the next command is the one that shows it."""
    root, sessions = wiki
    path = sessions / "rollout-a.jsonl"
    rows = [json.dumps({"type": "session_meta", "payload": {"id": "s1", "cwd": "/work", "originator": "codex_cli_rs"}})]
    rows += [json.dumps({"timestamp": "2026-09-07T05:00:00Z", "type": "response_item",
                         "payload": {"type": "message", "role": "user", "id": f"m{i}",
                                     "shape_we_have_never_seen": True,
                                     "content": [{"type": "input_text", "text": "Ship it on Friday."}]}})
             for i in range(25)]
    path.write_text("\n".join(rows) + "\n")
    record = run_sync(root, runner=lambda *args: pytest.fail("nothing was read, so nothing to maintain"))
    assert record["outcome"] == "no_change"
    assert record["unrecognised"] == {"codex": 25}
    assert "codex" in record["warning"] and "25" in record["warning"]


def test_a_window_is_coverage_not_a_replacement(wiki):
    """"At least three days of Claude Code" is what a person asks for, and it is not the
    same as "only three days". `--since` guarantees the window reaches back that far:
    it widens when it must and leaves a wider one alone. Narrowing is the destructive
    direction -- everything between the old edge and the new one is dropped unread and
    no cursor brings it back -- so that one asks first."""
    from connectonion.wiki.service import set_window, subscriptions
    root, _ = wiki
    default = subscriptions(root)["claude-code"]["since"]           # 60 days by default
    assert set_window(root, "claude-code", "3d")["changed"] is False  # already covered
    assert subscriptions(root)["claude-code"]["since"] == default

    widened = set_window(root, "outlook", "6m")
    assert widened["changed"] is True and widened["since"].startswith("2026-03-1")

    with pytest.raises(WikiError, match="180 days"):
        set_window(root, "codex", "2y")     # coding sessions are capped
    with pytest.raises(WikiError, match="7d"):
        set_window(root, "codex", "last tuesday")


def test_narrowing_a_window_needs_saying_so_twice(wiki):
    from connectonion.wiki.service import set_window
    root, _ = wiki
    with pytest.raises(WikiError, match="--force"):
        set_window(root, "codex", "3d", narrow=True)
    assert set_window(root, "codex", "3d", narrow=True, force=True)["since"].startswith("2026-09-04")
