"""Unit tests for connectonion/useful_tools/codex.py

Tests cover:
- codex function: headless Codex CLI invocation with mocked subprocess
- Session resume: session_id round-trip and silent new-thread detection
- Error paths: missing CLI, timeout, bad sandbox, non-zero exit
"""

import json
import subprocess
from unittest.mock import patch, MagicMock

from connectonion.useful_tools.codex import codex


def _jsonl(*events):
    return "\n".join(json.dumps(e) for e in events)


def _completed_run(stdout="", stderr="", returncode=0):
    return MagicMock(stdout=stdout, stderr=stderr, returncode=returncode)


THREAD_ID = "0199a213-81c0-7800-8aa1-bbab2a035a53"

SUCCESS_STDOUT = _jsonl(
    {"type": "thread.started", "thread_id": THREAD_ID},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {"type": "reasoning", "text": "thinking"}},
    {"type": "item.completed", "item": {"type": "agent_message", "text": "Fixed the tests."}},
    {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}},
)


class TestCodexSuccess:
    @patch("connectonion.useful_tools.codex.shutil.which", return_value="/usr/bin/codex")
    @patch("connectonion.useful_tools.codex.subprocess.run")
    def test_returns_session_id_and_message(self, mock_run, _which):
        mock_run.return_value = _completed_run(stdout=SUCCESS_STDOUT)

        result = json.loads(codex("fix the tests"))

        assert result["provider"] == "codex"
        assert result["session_id"] == THREAD_ID
        assert result["last_message"] == "Fixed the tests."
        assert result["usage"]["output_tokens"] == 20
        assert result["exit_code"] == 0
        assert result["resumed"] is False
        assert "error" not in result

    @patch("connectonion.useful_tools.codex.shutil.which", return_value="/usr/bin/codex")
    @patch("connectonion.useful_tools.codex.subprocess.run")
    def test_builds_exec_command_with_json_and_sandbox(self, mock_run, _which):
        mock_run.return_value = _completed_run(stdout=SUCCESS_STDOUT)

        codex("do a task")

        cmd = mock_run.call_args[0][0]
        assert cmd[:2] == ["codex", "exec"]
        assert "--json" in cmd
        assert cmd[cmd.index("--sandbox") + 1] == "read-only"
        assert cmd[-1] == "do a task"

    @patch("connectonion.useful_tools.codex.shutil.which", return_value="/usr/bin/codex")
    @patch("connectonion.useful_tools.codex.subprocess.run")
    def test_cwd_model_and_sandbox_flags(self, mock_run, _which):
        mock_run.return_value = _completed_run(stdout=SUCCESS_STDOUT)

        codex("task", cwd="/repo", sandbox="workspace-write", model="gpt-5-codex")

        cmd = mock_run.call_args[0][0]
        assert cmd[cmd.index("--cd") + 1] == "/repo"
        assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"
        assert cmd[cmd.index("--model") + 1] == "gpt-5-codex"


class TestCodexResume:
    @patch("connectonion.useful_tools.codex.shutil.which", return_value="/usr/bin/codex")
    @patch("connectonion.useful_tools.codex.subprocess.run")
    def test_resume_uses_resume_subcommand(self, mock_run, _which):
        mock_run.return_value = _completed_run(stdout=SUCCESS_STDOUT)

        codex("continue", session_id=THREAD_ID)

        cmd = mock_run.call_args[0][0]
        assert cmd[:4] == ["codex", "exec", "resume", THREAD_ID]

    @patch("connectonion.useful_tools.codex.shutil.which", return_value="/usr/bin/codex")
    @patch("connectonion.useful_tools.codex.subprocess.run")
    def test_resumed_true_when_same_thread_id(self, mock_run, _which):
        mock_run.return_value = _completed_run(stdout=SUCCESS_STDOUT)

        result = json.loads(codex("continue", session_id=THREAD_ID))

        assert result["resumed"] is True
        assert result["session_id"] == THREAD_ID

    @patch("connectonion.useful_tools.codex.shutil.which", return_value="/usr/bin/codex")
    @patch("connectonion.useful_tools.codex.subprocess.run")
    def test_silent_new_thread_detected(self, mock_run, _which):
        # Codex silently starts a new thread when resuming an ephemeral session
        new_thread = _jsonl(
            {"type": "thread.started", "thread_id": "different-thread-id"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}},
            {"type": "turn.completed", "usage": {}},
        )
        mock_run.return_value = _completed_run(stdout=new_thread)

        result = json.loads(codex("continue", session_id=THREAD_ID))

        assert result["resumed"] is False
        assert result["session_id"] == "different-thread-id"


class TestCodexErrors:
    @patch("connectonion.useful_tools.codex.shutil.which", return_value=None)
    def test_missing_cli(self, _which):
        result = json.loads(codex("task"))
        assert "codex CLI not found" in result["error"]

    @patch("connectonion.useful_tools.codex.shutil.which", return_value="/usr/bin/codex")
    def test_invalid_sandbox(self, _which):
        result = json.loads(codex("task", sandbox="yolo"))
        assert "Invalid sandbox" in result["error"]

    @patch("connectonion.useful_tools.codex.shutil.which", return_value="/usr/bin/codex")
    @patch("connectonion.useful_tools.codex.subprocess.run",
           side_effect=subprocess.TimeoutExpired(cmd="codex", timeout=5))
    def test_timeout(self, _run, _which):
        result = json.loads(codex("task", timeout=5))
        assert "timed out after 5 seconds" in result["error"]

    @patch("connectonion.useful_tools.codex.shutil.which", return_value="/usr/bin/codex")
    @patch("connectonion.useful_tools.codex.subprocess.run")
    def test_nonzero_exit_includes_stderr(self, mock_run, _which):
        mock_run.return_value = _completed_run(stderr="401 Unauthorized", returncode=1)

        result = json.loads(codex("task"))

        assert result["exit_code"] == 1
        assert "401 Unauthorized" in result["error"]

    @patch("connectonion.useful_tools.codex.shutil.which", return_value="/usr/bin/codex")
    @patch("connectonion.useful_tools.codex.subprocess.run")
    def test_non_json_lines_ignored(self, mock_run, _which):
        stdout = "not json\n" + SUCCESS_STDOUT + "\ngarbage"
        mock_run.return_value = _completed_run(stdout=stdout)

        result = json.loads(codex("task"))

        assert result["session_id"] == THREAD_ID
        assert result["last_message"] == "Fixed the tests."
