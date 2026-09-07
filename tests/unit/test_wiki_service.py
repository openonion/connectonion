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
