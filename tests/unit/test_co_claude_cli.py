"""The co claude CLI and Host delegation enter the same Claude runner."""

import importlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app


def test_co_claude_run_passes_a_bounded_workspace_and_resume_id(tmp_path, monkeypatch):
    claude = importlib.import_module("connectonion.useful_tools.claude_code")
    calls = []

    def run_claude(**kwargs):
        calls.append(kwargs)
        return json.dumps({"status": "completed", "session_id": "session-1"})

    monkeypatch.setattr(claude, "run_co_claude", run_claude)
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
        "run_co_claude",
        lambda **kwargs: json.dumps({"status": "error", "error": "Claude CLI unavailable"}),
    )

    result = CliRunner().invoke(app, ["claude", "run", "Fix the tests", "--cwd", str(tmp_path)])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == "Claude CLI unavailable"


def test_co_claude_launches_interactive_connector(tmp_path, monkeypatch):
    claude = importlib.import_module("connectonion.useful_tools.claude_code")
    calls = []

    def run_interactive(cwd, session_id, model):
        calls.append((cwd, session_id, model))
        return 0, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

    monkeypatch.setattr(claude, "run_interactive_claude", run_interactive)
    result = CliRunner().invoke(app, ["claude", "--no-share", "--cwd", str(tmp_path), "--model", "haiku"])

    assert result.exit_code == 0
    assert "Claude session: bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb" in result.output
    assert calls == [(str(tmp_path), "", "haiku")]


def _running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers signal 0, but it has exited.
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                           capture_output=True, text=True).stdout.strip()
    return bool(state) and not state.startswith("Z")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal delivery")
def test_sigterm_to_co_claude_run_ends_the_claude_child_before_its_hooks(tmp_path):
    """A re-tester sent SIGTERM to `co claude run`: co exited 143, but the
    `claude -p` child ran on in its own session, reparented to launchd, with
    its Hook bridge already deleted. co must end the child it started, and
    before the directory the child's Hooks point at is removed."""
    pid_file = tmp_path / "child.pid"
    seen = tmp_path / "settings-at-term.txt"
    shim = tmp_path / "claude"
    # The shim records whether its --settings file still existed when the
    # SIGTERM reached it, then sleeps like a long Claude turn.
    shim.write_text(f"""#!/bin/sh
settings=""
prev=""
for a in "$@"; do [ "$prev" = "--settings" ] && settings="$a"; prev="$a"; done
trap 'if [ -f "$settings" ]; then echo present; else echo gone; fi > {seen}; exit 0' TERM
echo $$ > {pid_file}
sleep 60 &
wait
""")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    workspace = tmp_path / "repo"
    workspace.mkdir()
    co = subprocess.Popen(
        [sys.executable, "-m", "connectonion.cli.main", "claude", "run",
         "--cwd", str(workspace), "x"],
        cwd=Path(__file__).resolve().parents[2],  # this checkout, not an installed copy
        env={**os.environ, "CLAUDE_CODE_CMD": str(shim)},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    child = None
    try:
        deadline = time.monotonic() + 40
        while child is None:
            assert co.poll() is None, co.communicate()
            assert time.monotonic() < deadline, "the Claude shim never started"
            text = pid_file.read_text().strip() if pid_file.exists() else ""
            child = int(text) if text else None
            time.sleep(0.05)
        co.send_signal(signal.SIGTERM)
        assert co.wait(timeout=15) == 128 + signal.SIGTERM
        deadline = time.monotonic() + 5
        while _running(child) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _running(child), "claude -p outlived the co that started it"
        assert seen.read_text().strip() == "present"
    finally:
        if co.poll() is None:
            co.kill()
            co.wait()
        co.stdout.close()
        co.stderr.close()
        if child is not None:
            try:
                os.killpg(child, signal.SIGKILL)
            except OSError:
                pass
