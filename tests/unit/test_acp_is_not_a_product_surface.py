"""ACP is absent; OIP keeps only native Codex and Claude Code adapters."""

from pathlib import Path

from typer.testing import CliRunner

import connectonion.useful_tools as useful_tools
from connectonion.cli.main import app


ROOT = Path(__file__).resolve().parents[2]


def test_distribution_does_not_depend_on_acp():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "agent-client-protocol" not in project


def test_production_package_has_no_acp_modules():
    modules = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "connectonion").rglob("*.py")
        if "acp" in path.name.lower()
    ]

    assert modules == []


def test_co_ai_rejects_removed_acp_option():
    result = CliRunner().invoke(app, ["ai", "--acp"])

    assert result.exit_code == 2
    assert "No such option" in result.output


def test_public_tools_keep_native_adapters_without_acp():
    assert hasattr(useful_tools, "codex")
    assert hasattr(useful_tools, "claude_code")
    assert not hasattr(useful_tools, "acp_agent")
    assert not hasattr(useful_tools, "ACPAgent")
