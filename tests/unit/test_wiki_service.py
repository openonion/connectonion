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
