"""Unit-test policy for co rem's page review.

Every page about people and work is audited against its cited originals by a
model turn (`runner.run_claim_task`). No unit test may start one: by default
the audit passes, and a test about the audit replaces it with its own verdict.
The audit's own tests (test_rem_project_claim_review.py) exercise the real one.
"""

import json

import pytest


@pytest.fixture(autouse=True)
def _claim_audit_passes(request, monkeypatch):
    if request.module.__name__.endswith("test_rem_project_claim_review"):
        return
    from connectonion.rem import runner
    monkeypatch.setattr(runner, "run_claim_task", lambda *_args: {
        "result": json.dumps({"verdict": "PASS", "findings": []}), "usage": {}})
