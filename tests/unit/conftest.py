"""Unit-test policy for co rem's page review.

Every page about people and work is audited against its cited originals by a
model turn (`runner.run_claim_task`). No unit test may start one: by default
the audit passes, and a test about the audit replaces it with its own verdict.
The audit's own tests (test_rem_project_claim_review.py) exercise the real one.
"""

import json
import sys

import pytest


@pytest.fixture
def rem_mail_threads(tmp_path):
    """Two cited mail threads with interleaved replies, including tied times."""
    from connectonion.rem.config import prepare
    from connectonion.rem.mail_archive import retain_message
    from connectonion.rem.store import refresh

    root = tmp_path / "mail-threads"
    prepare(root)
    for thread, days in (("alpha", (1, 3, 3)), ("beta", (1, 2, 3))):
        for number, day in enumerate(days):
            message_id = f"{thread}-{number}"
            retain_message(root, "gmail", {
                "id": message_id, "thread_id": thread, "subject": f"Pilot {thread}",
                "date": f"2026-11-{day:02d}T10:00:00Z",
                "from": "Avery Lin <avery@example.test>", "to": ["morgan@example.test"],
            }, f"Reply {message_id}.", fetched_at="2026-11-04T10:00:00Z")
    refresh(root)
    return root


@pytest.fixture(autouse=True)
def _claim_audit_passes(request, monkeypatch):
    if request.module.__name__.endswith("test_rem_project_claim_review"):
        return
    from connectonion.rem import runner
    original = runner.run_claim_task
    monkeypatch.setattr(runner, "run_claim_task", lambda *_args: {
        "result": json.dumps({"verdict": "PASS", "findings": []}), "usage": {}})
    return original


@pytest.fixture(autouse=True)
def _topic_proposal_is_offline(request, monkeypatch):
    """The nightly round asks the summary model to name topics once a week;
    unit tests of other features never make that call."""
    if request.module.__name__.endswith("test_rem_topic_map"):
        return
    from connectonion.rem import topic_map
    monkeypatch.setattr(topic_map, "_propose_topics", lambda notebook: {"topics": [], "usage": {}})


@pytest.fixture(autouse=True)
def _task_workers_never_start(request, monkeypatch):
    """No unit test starts a detached Codex worker; only test_rem_tasks, which brings a
    fake Codex, does. REM's task runner is POSIX-only (fcntl), so Windows has nothing to stub."""
    if request.module.__name__.endswith("test_rem_tasks") or sys.platform == "win32":
        return
    from connectonion.rem import tasks
    monkeypatch.setattr(tasks, "start", lambda root, task_id: tasks.status(root, task_id))


@pytest.fixture(autouse=True)
def _codex_onboarding_is_offline(request, monkeypatch):
    """Unit tests never install a CLI or open the operator's OAuth browser.

    Codex onboarding tests mock each external boundary themselves. Other CLI
    tests exercise their own behavior with that machine-setup step already ready.
    Desktop bundle discovery must not depend on applications on the test host.
    """
    from connectonion import codex_cli
    from connectonion.cli import codex_setup
    monkeypatch.setattr(codex_cli, "BUNDLED_CODEX", ())
    if request.module.__name__.endswith("test_init_codex"):
        return
    monkeypatch.setattr(codex_setup, "claude_ready", lambda: False)
    from connectonion.rem.quota import _codex_auth
    # Existing provider fixtures represent a synthetic signed-in CLI with this file.
    monkeypatch.setattr(codex_cli, "signed_in", lambda command: _codex_auth().is_file())
    monkeypatch.setattr(codex_setup, "setup_codex", lambda: {
        "ready": True, "summary": "Codex CLI: found at /test/codex",
        "undo": "rm -f /test/codex", "login_command": "/test/codex login", "next_action": ""})
