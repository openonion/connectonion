"""Unit-test policy for co rem's page review.

Every page about people and work is audited against its cited originals by a
model turn (`runner.run_claim_task`). No unit test may start one: by default
the audit passes, and a test about the audit replaces it with its own verdict.
The audit's own tests (test_rem_project_claim_review.py) exercise the real one.
"""

import json

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
