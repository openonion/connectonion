"""Keep ACP stdio MCP security and operator boundaries visible in docs."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_cli_docs_explain_explicit_mcp_launch_authority():
    docs = (ROOT / "docs" / "cli" / "ai.md").read_text(encoding="utf-8")
    normalized = " ".join(docs.split())

    assert "co ai --acp --acp-mcp" in docs
    assert "stdio" in docs
    assert "not persisted" in normalized
    assert "Client-granted MCP approvals are not persisted" in normalized
    assert ".co/host.yaml" in docs
    assert "safe environment" in docs
    assert "HTTP" in docs


def test_mcp_design_decision_records_security_and_lifecycle_boundaries():
    decision = (
        ROOT / "docs" / "design-decisions" / "033-acp-stdio-mcp-authority.md"
    ).read_text(encoding="utf-8")

    assert "mcp>=2.0.0,<3" in decision
    assert "--acp-mcp" in decision
    assert "DD-030" in decision
    assert "DD-032" in decision
    assert "fail-closed" in decision
    assert "session/close" in decision
    assert "removed from durable snapshots" in decision
    assert "operator permissions" in decision
