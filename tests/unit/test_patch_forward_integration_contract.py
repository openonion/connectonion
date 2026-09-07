"""Stable patches must never leave the active preview behind."""

import json
from pathlib import Path

import pytest

from scripts.check_forward_port_gate import (
    open_forward_port_issues,
    release_needs_clear_forward_ports,
)


REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("version", ["1.7.1", "1.7.12", "20.3.4"])
def test_a_stable_patch_can_publish_before_its_forward_ports(version):
    assert release_needs_clear_forward_ports(version) is False


@pytest.mark.parametrize(
    "version",
    ["1.8.0a2", "1.8.0b1", "1.8.0rc1", "1.8.0", "2.0.0"],
)
def test_every_newer_channel_requires_a_clear_forward_port_ledger(version):
    assert release_needs_clear_forward_ports(version) is True


def test_the_gate_preserves_issue_evidence():
    issues = [{"number": 42, "title": "carry 1.7.1 into 1.8", "url": "https://example/42"}]
    assert open_forward_port_issues(json.loads(json.dumps(issues))) == issues


def test_the_gate_rejects_a_non_list_github_payload():
    with pytest.raises(ValueError, match="must be a list"):
        open_forward_port_issues({"number": 42})


def test_release_guidance_and_templates_keep_the_contract_visible():
    files = [
        "VERSIONING.md",
        "docs/ai-implementation-contract.md",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
    ]
    for name in files:
        text = (REPO / name).read_text(encoding="utf-8")
        assert "forward-port-required" in text, name
        assert "preview" in text.lower(), name


def test_github_enforces_the_tracker_at_pr_and_release_boundaries():
    triage = (REPO / ".github/workflows/triage-metadata.yml").read_text(encoding="utf-8")
    release = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "const forwardTracker" in triage
    assert "tracker.data.state !== 'open'" in triage
    assert "forward-port-required" in triage
    assert "scripts/check_forward_port_gate.py" in release
    assert "issues: read" in release
