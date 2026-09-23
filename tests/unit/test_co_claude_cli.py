"""The co claude CLI and Host delegation enter the same Claude runner."""

import importlib
import json

from typer.testing import CliRunner

from connectonion.cli.main import app


def test_co_claude_run_passes_a_bounded_workspace_and_resume_id(tmp_path, monkeypatch):
    claude = importlib.import_module("connectonion.useful_tools.claude_code")
    calls = []

    def run_claude(**kwargs):
        calls.append(kwargs)
        return json.dumps({"status": "completed", "session_id": "session-1"})

    monkeypatch.setattr(claude, "_run_claude_code", run_claude)
    result = CliRunner().invoke(app, [
        "claude", "run", "Fix the tests", "--cwd", str(tmp_path),
        "--session", "session-1", "--timeout", "30",
    ])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"status": "completed", "session_id": "session-1"}
    assert calls == [{
        "prompt": "Fix the tests",
        "cwd": str(tmp_path),
        "session_id": "session-1",
        "model": "",
        "timeout": 30,
        "workspace": tmp_path,
    }]


def test_co_claude_run_exits_nonzero_on_provider_failure(tmp_path, monkeypatch):
    claude = importlib.import_module("connectonion.useful_tools.claude_code")
    monkeypatch.setattr(
        claude,
        "_run_claude_code",
        lambda **kwargs: json.dumps({"status": "error", "error": "Claude CLI unavailable"}),
    )

    result = CliRunner().invoke(app, ["claude", "run", "Fix the tests", "--cwd", str(tmp_path)])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == "Claude CLI unavailable"
